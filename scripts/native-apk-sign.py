#!/usr/bin/env python3
"""Pre-sign target-files APKs with native host apksigner, in bounded parallel.

The plan and key paths are produced by plan-signing.py. Password JSON is read
from stdin and has group names as keys, for example
{"android-release-v1":"...","android-module-apps-v1":"..."}.
Passwords are passed to apksigner over stdin, never in process arguments.
"""
import argparse
import concurrent.futures
import copy
import gzip
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import tempfile
import zipfile


PARTITIONS = {"SYSTEM", "SYSTEM_EXT", "PRODUCT", "VENDOR", "ODM"}
GROUPS = {"android-release-v1", "android-module-apps-v1"}


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_sdk_tool(name):
    roots = []
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        if os.environ.get(variable):
            roots.append(pathlib.Path(os.environ[variable]))
    roots.append(pathlib.Path.home() / "Library/Android/sdk")
    roots.append(pathlib.Path.home() / "Android/Sdk")
    for root in roots:
        builds = sorted((root / "build-tools").glob("*"), reverse=True)
        for version in builds:
            candidate = version / ("lib/apksigner.jar" if name == "apksigner.jar" else name)
            if candidate.is_file():
                return candidate
    raise RuntimeError("Android SDK tool not found: " + name)


def metadata_rows(data):
    """Return parsed apkcerts metadata keyed by installed APK basename."""
    rows = {}
    for raw in data.decode("utf-8").splitlines():
        if not raw.strip():
            continue
        # Metadata values are emitted as quoted shell-style fields. shlex is
        # avoided here because preserving the original row is important.
        match = re.search(r'\bname="([^"]+)"', raw)
        cert = re.search(r'\bcertificate="([^"]*)"', raw)
        private = re.search(r'\bprivate_key="([^"]*)"', raw)
        compressed = re.search(r'\bcompressed="([^"]*)"', raw)
        if not (match and cert and private):
            raise RuntimeError("Cannot parse META/apkcerts.txt row: " + raw[:180])
        name = match.group(1)
        row = {
            "line": raw,
            "certificate": cert.group(1),
            "private_key": private.group(1),
            "compressed": compressed.group(1) if compressed else None,
        }
        if name in rows:
            fields = ("certificate", "private_key", "compressed")
            if any(rows[name][field] != row[field] for field in fields):
                raise RuntimeError("Conflicting APK signing metadata: " + name)
        else:
            rows[name] = row
    return rows


def cert_sha256(certificate, openssl):
    der = subprocess.run(
        [openssl, "x509", "-in", str(certificate), "-outform", "DER"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return hashlib.sha256(der).hexdigest()


def apk_verify(apksigner, java, apk):
    result = subprocess.run(
        [java, "-jar", str(apksigner), "verify", "--verbose", "--print-certs", str(apk)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if result.returncode:
        raise RuntimeError("apksigner verification failed for " + apk.name + ": " +
                           (result.stderr or result.stdout)[-1600:])
    digests = re.findall(r"Signer #\d+ certificate SHA-256 digest: ([0-9a-fA-F]+)", result.stdout)
    if not digests:
        raise RuntimeError("apksigner returned no signer certificate for " + apk.name)
    return [value.lower() for value in digests]


def extract_member(archive, member, destination, gzip_wrapped):
    with archive.open(member, "r") as source, open(destination, "wb") as raw:
        if gzip_wrapped:
            with gzip.GzipFile(fileobj=source, mode="rb") as unwrapped:
                shutil.copyfileobj(unwrapped, raw, 1024 * 1024)
        else:
            shutil.copyfileobj(source, raw, 1024 * 1024)


def min_sdk_for(apk, platform_api, codename_map, aapt2):
    # Historical releasetools force SHA-1 JAR signatures for pre-N products.
    # This also matches SignApk's --min-sdk-version 1 behavior.
    if platform_api <= 23:
        return 1
    output = subprocess.run(
        [str(aapt2), "dump", "badging", str(apk)], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    ).stdout
    # AOSP's aapt2 prints sdkVersion; newer SDK releases use minSdkVersion.
    match = re.search(r"^(?:sdkVersion|minSdkVersion):'([^']*)'", output, re.MULTILINE)
    if not match:
        raise RuntimeError("aapt2 did not report minSdkVersion for " + apk.name)
    version = match.group(1)
    try:
        return int(version)
    except ValueError:
        codename = version.split(".", 1)[0]
        if codename not in codename_map:
            raise RuntimeError("Unknown minSdkVersion codename " + repr(version) +
                               " in " + apk.name)
        return codename_map[codename]


def set_presigned(line):
    line, count = re.subn(r'\bcertificate="[^"]*"', 'certificate="PRESIGNED"', line, count=1)
    if count != 1:
        raise RuntimeError("Could not mark apkcerts row PRESIGNED")
    line, count = re.subn(r'\bprivate_key="[^"]*"', 'private_key=""', line, count=1)
    if count != 1:
        raise RuntimeError("Could not clear apkcerts private key")
    return line


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=pathlib.Path)
    parser.add_argument("--plan", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--report", type=pathlib.Path)
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--check-only", action="store_true", help="Check all input APKs and metadata without passwords or signing")
    parser.add_argument("--java", type=pathlib.Path)
    parser.add_argument("--apksigner", type=pathlib.Path)
    parser.add_argument("--aapt2", type=pathlib.Path)
    parser.add_argument("--openssl", default="openssl")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 4:
        parser.error("--jobs must be from 1 through 4")
    if args.input.resolve() == args.output.resolve():
        parser.error("output must differ from input")
    if args.output.exists():
        parser.error("refusing to overwrite output: " + str(args.output))
    if platform.system() != "Darwin" or platform.machine() not in ("arm64", "aarch64"):
        parser.error("native APK signing helper requires macOS on Apple Silicon")

    java = args.java or pathlib.Path(shutil.which("java") or "")
    if not str(java) or not java.is_file():
        parser.error("Java runtime not found; pass --java")
    apksigner = args.apksigner or find_sdk_tool("apksigner.jar")
    aapt2 = args.aapt2 or find_sdk_tool("aapt2")
    plan = json.loads(args.plan.read_text())
    with args.input.open("rb") as stream:
        input_digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if plan.get("target_files_sha256") != input_digest:
        parser.error("plan target-files SHA-256 does not match input")
    key_map = plan.get("key_map")
    if not isinstance(key_map, dict) or not key_map:
        parser.error("plan has no APK key mappings")
    for source, destination in key_map.items():
        if source.endswith(".x509.pem"):
            parser.error("plan certificate key must be the certificate stem: " + source)
        key = pathlib.Path(destination)
        if not pathlib.Path(str(key) + ".pk8").is_file() or not pathlib.Path(str(key) + ".x509.pem").is_file():
            parser.error("missing signing key pair for mapping: " + source)
    passwords = {group:"preflight-only" for group in GROUPS} if args.check_only else json.load(__import__("sys").stdin)
    if not isinstance(passwords, dict) or set(passwords) != GROUPS or any(not isinstance(v, str) or not v for v in passwords.values()):
        parser.error("stdin must contain nonempty passwords for both signing key groups")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report = args.report or args.output.parent / "native-signing-report.json"
    if args.report.exists():
        parser.error("refusing to overwrite report: " + str(args.report))
    report = {
        "status": "native APK pre-signing completed; target-files signing and release validation remain required",
        "input": str(args.input), "input_sha256": input_digest,
        "output": str(args.output), "workers": args.jobs,
        "apks": [],
    }
    with tempfile.TemporaryDirectory(prefix="native-apk-sign-", dir=args.output.parent) as temporary:
        work = pathlib.Path(temporary)
        with zipfile.ZipFile(args.input, "r") as archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)):
                raise RuntimeError("target-files ZIP contains duplicate member names")
            if "META/apkcerts.txt" not in names:
                raise RuntimeError("target-files ZIP has no META/apkcerts.txt")
            if any(name.endswith((".apex", ".capex")) and name.split("/", 1)[0] in PARTITIONS for name in names):
                raise RuntimeError("packaged APEX files require separate signing support")
            rows = metadata_rows(archive.read("META/apkcerts.txt"))
            sdk_props = archive.read("SYSTEM/build.prop").decode("utf-8", "replace")
            props = dict(line.split("=", 1) for line in sdk_props.splitlines()
                         if "=" in line and not line.lstrip().startswith("#"))
            platform_api = int(props["ro.build.version.sdk"])
            codename_map = {part.strip(): platform_api for part in
                            props.get("ro.build.version.all_codenames", "").split(",") if part.strip()}
            cert_sources = {pathlib.Path(source).name: (source, dest)
                            for source, dest in key_map.items()}
            presigned_paths = []

            work_items = []
            seen_apks = set()
            for info in infos:
                name = info.filename
                base_partition = name.split("/", 1)[0]
                if base_partition not in PARTITIONS:
                    continue
                if not (name.endswith(".apk") or name.endswith(".apk.gz")):
                    continue
                basename = pathlib.PurePosixPath(name).name
                compressed = basename.endswith(".apk.gz")
                if compressed:
                    raise RuntimeError("Compressed APK signing is not supported by this pipeline: " + name)
                apk_basename = basename[:-3] if compressed else basename
                # Flattened APEX directories may ship the same APK basename.
                # The shared metadata above must agree on its signing identity.
                seen_apks.add(apk_basename)
                row = rows.get(apk_basename)
                if not row:
                    raise RuntimeError("missing apkcerts row for " + name)
                if compressed and row["compressed"] != "gz":
                    raise RuntimeError("compressed APK metadata is not gzip for " + name)
                if not compressed and row["compressed"]:
                    raise RuntimeError("apkcerts compression metadata conflicts with " + name)
                cert_name = row["certificate"]
                if cert_name == "PRESIGNED":
                    presigned_paths.append(name)
                    work_items.append((name, apk_basename, None, None, True, compressed))
                    continue
                mapped = cert_sources.get(pathlib.Path(cert_name).name.removesuffix(".x509.pem"))
                if not mapped or mapped[0] + ".x509.pem" != cert_name:
                    raise RuntimeError("APK certificate has no exact plan mapping: " + cert_name)
                source, destination = mapped
                key = pathlib.Path(destination)
                group = next((group for group in GROUPS if group in key.parts), None)
                if not group:
                    raise RuntimeError("key is outside an approved signing group: " + str(key))
                work_items.append((name, apk_basename, key, group, False, compressed))
            expected_presigned = set(plan.get("presigned_apks", []))
            if expected_presigned != set(presigned_paths):
                raise RuntimeError("PRESIGNED APK paths differ from signing plan inventory")

        if args.check_only:
            for member, basename, key, group, presigned, compressed in work_items:
                apk = work / (hashlib.sha256(member.encode()).hexdigest()[:20] + ".apk")
                with zipfile.ZipFile(args.input) as archive:
                    extract_member(archive, member, apk, compressed)
                if presigned:
                    apk_verify(apksigner, java, apk)
                else:
                    cert_sha256(str(key) + ".x509.pem", args.openssl)
                    min_sdk_for(apk, platform_api, codename_map, aapt2)
                apk.unlink()
            print("Full input preflight passed:", len(work_items), "APK paths; no passwords or private keys read.")
            return

        changed = {}
        completed = []

        def prepare(item):
            member, basename, key, group, presigned, compressed = item
            token = hashlib.sha256(member.encode()).hexdigest()[:20]
            unsigned = work / (token + ".apk")
            signed = work / (token + ".signed.apk")
            with zipfile.ZipFile(args.input, "r") as archive:
                extract_member(archive, member, unsigned, compressed)
            if presigned:
                output_apk = unsigned
                expected = None
            else:
                expected = cert_sha256(str(key) + ".x509.pem", args.openssl)
                minimum = min_sdk_for(unsigned, platform_api, codename_map, aapt2)
                command = [str(java), "-jar", str(apksigner), "sign",
                           "--key", str(key) + ".pk8", "--cert", str(key) + ".x509.pem",
                           "--key-pass", "stdin", "--min-sdk-version", str(minimum),
                           "--v1-signing-enabled", "true", "--v2-signing-enabled", "true",
                           "--v3-signing-enabled", "false", "--v4-signing-enabled", "false",
                           "--alignment-preserved",
                           "--in", str(unsigned), "--out", str(signed)]
                result = subprocess.run(command, input=(passwords[group] + "\n").encode(),
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode:
                    raise RuntimeError("apksigner failed for " + member + ": " +
                                       (result.stderr or result.stdout).decode("utf-8", "replace")[-1600:])
                output_apk = signed
            actual = apk_verify(apksigner, java, output_apk)
            if expected and actual != [expected]:
                raise RuntimeError("certificate mismatch after signing " + member)
            if len(actual) != 1:
                raise RuntimeError("expected exactly one APK signer for " + member)
            result = {"path": member, "certificate_sha256": actual[0],
                      "signature_verified": True, "presigned_input": presigned,
                      "preserved_verbatim": presigned,
                      "input_payload_sha256": sha256_file(unsigned),
                      "signed_payload_sha256": sha256_file(output_apk)}
            return member, output_apk, result

        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
            futures = [pool.submit(prepare, item) for item in work_items]
            for future in concurrent.futures.as_completed(futures):
                member, path, result = future.result()
                completed.append(result)
                print(f"APK {len(completed)}/{len(work_items)} verified: {member}", flush=True)
                if not result["presigned_input"]:
                    changed[member] = path

        # Only after every APK signature has been verified, update the metadata
        # so the stock releasetools pass skips these already signed APKs.
        new_rows = []
        with zipfile.ZipFile(args.input, "r") as archive:
            metadata_text = archive.read("META/apkcerts.txt").decode("utf-8")
        signed_basenames = {pathlib.PurePosixPath(path).name[:-3] if path.endswith(".apk.gz")
                            else pathlib.PurePosixPath(path).name for path in changed}
        for raw in metadata_text.splitlines():
            match = re.search(r'\bname="([^"]+)"', raw)
            if match and match.group(1) in signed_basenames:
                raw = set_presigned(raw)
            new_rows.append(raw)
        metadata_out = ("\n".join(new_rows) + "\n").encode("utf-8")
        staged_output = work / "pre-signed-target-files.zip"

        with zipfile.ZipFile(args.input, "r") as source, zipfile.ZipFile(staged_output, "w", allowZip64=True) as output:
            output.comment = source.comment
            for info in source.infolist():
                out_info = copy.copy(info)
                if info.filename == "META/apkcerts.txt":
                    with output.open(out_info, "w", force_zip64=True) as target:
                        target.write(metadata_out)
                elif info.filename in changed:
                    with open(changed[info.filename], "rb") as input_apk, output.open(out_info, "w", force_zip64=True) as target:
                        shutil.copyfileobj(input_apk, target, 1024 * 1024)
                else:
                    with source.open(info, "r") as input_member, output.open(out_info, "w", force_zip64=True) as target:
                        shutil.copyfileobj(input_member, target, 1024 * 1024)

        os.replace(staged_output, args.output)
        report["apks"] = sorted(completed, key=lambda row: row["path"])
        report["signed_apk_count"] = len(changed)
        report["presigned_apk_count"] = len(completed) - len(changed)
        report["output_sha256"] = sha256_file(args.output)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        os.chmod(args.report, 0o600)
    print("Native APK pre-sign complete:", len(changed), "signed;",
          report["presigned_apk_count"], "existing PRESIGNED APKs verified.")
    print("Pre-signed target-files:", args.output)
    print("Verification report:", args.report)


if __name__ == "__main__":
    main()
