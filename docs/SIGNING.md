# Local candidate signing

Local full candidates can use the same stable signing identity as public releases. Keep ordinary builds incremental, then sign their target-files in a separate protected step. Do not place private keys or passwords inside the Android checkout, GitHub runner, repository or build logs. A system APK tested on a release-signed installation also needs its matching signing identity; an ordinary test-key APK is not a compatible replacement.

## Profiles

The helper reads `ro.build.version.sdk` and `ro.lineage.build.version` from `SYSTEM/build.prop` and picks exactly one profile, or refuses the input. Each profile has its own pinned toolchain, device tree, key groups and metadata allowances (`scripts/signing_profiles.py`):

- `eos-t` (/e/OS T, SDK 33): flattened APEX, key groups `android-release-v1` and `android-module-apps-v1`, two passwords.
- `lineage-22.2` (LineageOS 22.2, SDK 35): packaged APEX, one key group `lineage-release-v1` (core keys, `apps/` module app keys, `apex/` APEX keys), one password.

The /e/OS T target uses flattened APEX, seven core app certificate families, eight additional app identities and some PRESIGNED third-party packages. The signer preserves PRESIGNED packages and maps each other identity to its own private replacement. Testkey maps to releasekey. Catalog APEX entries do not imply that packaged APEX payloads are shipped.

The helper signs APKs with native macOS ARM64 Java/apksigner using two workers, verifies each signature and certificate, then passes a ZIP with verified APKs marked PRESIGNED to the isolated Linux image/OTA packaging step. The original signing plan still drives SELinux certificate and OTA trust replacement. The Linux step verifies the pre-signed ZIP hash and report before processing.

The isolated helper is:

```bash
bash scripts/sign-local-candidate.sh /absolute/path/to/target-files.zip /absolute/path/to/new-candidate-directory --jobs 2
```

Run from an interactive terminal; it asks for the two key passwords with hidden input first, then runs the checks and signing without further input. Do not run it in public CI, and do not pass passwords as arguments or paste them into chat. Native APK signing passes each key password over stdin; the packaging password file exists only in the container's memory-backed `/dev/shm` and is removed on completion/error. No key password is passed as a process argument or uploaded to GitHub.

## Signing toolchain

Packaging never runs tools from `out/`, which Actions jobs can write. Build `otatools.zip` in the local build container with its own output directory (not mounted in the runner) and ccache off, then install it once on the host:

```bash
docker exec eos-bullhead-work bash /eos/public/android_builds/scripts/build-signing-toolchain.sh lineage_bullhead-userdebug
python3 scripts/install-signing-toolchain.py /Volumes/eOS-Build/src/android/out-signing/target/product/bullhead/otatools.zip
docker exec -u 1000:1000 -e HOME=/tmp/build-home eos-bullhead-work bash /eos/public/android_builds/scripts/build-signing-toolchain.sh lineage_bullhead-bp1a-userdebug /eos/src/lineage-22.2 /eos/src/lineage-22.2/out-signing
python3 scripts/install-signing-toolchain.py --profile lineage-22.2 /Volumes/eOS-Build/src/lineage-22.2/out-signing/target/product/bullhead/otatools.zip
```

The install step unpacks it read-only into `.local/signing-toolchain/<zip sha256>/`, writes a per-file SHA256 manifest and pins the manifest hash in the profile's pin file (`current.json` for `eos-t`, `current-lineage-22.2.json` for `lineage-22.2`). After asking for the passwords, the host helper checks every file against the manifest and refuses missing, extra, changed or linked files. The packaging container mounts only that toolchain, with `PATH` and `LD_LIBRARY_PATH` limited to it and the image's `/usr/bin:/bin`. Rebuild and reinstall the toolchain after updating `build/make` or host tool sources.

The input target-files also carries code: `META/releasetools.py` and command names in `META/misc_info.txt`. The helper passes the device tree's `releasetools.py` with `-s` and refuses an input whose embedded copy differs from it. It refuses any `misc_info.txt` key outside the set this pipeline expects, command keys other than the expected `ext_mkuserimg` and `lpmake` values, and `*_args` values holding anything but flags and numbers. Add a key to that list only after checking how the release tools use it. Signing still trusts the content of the target-files; only device testing and source review cover that.

Android 15 target-files add a SHA-256 zip extra field (0x4967) from soong_zip, `META/fastboot-info.txt`, `virtual_ab_cow_version=2`, optionally `board_non_ab_ota_disable_compression=true`, and libncurses terminfo names under `SYSTEM/system_ext/etc/terminfo/` that differ only in case. The `lineage-22.2` profile accepts exactly these. It still refuses `ab_update=true` with its A/B files (`META/liblz4.so` would be preloaded into OTA tools): Android 15 defaults `AB_OTA_UPDATER` to true, so a non-A/B device must set it to false. It accepts `extra_recovery_keys` only as LineageOS sets it, to its official OTA certificate, and checks that recovery trusts exactly the release key plus that certificate from the pinned toolchain while system trusts only the release key.

## Packaging runtime

Linux packaging runs in a pinned arm64 image by default (`--runtime arm64`): Ubuntu 24.04 with the same OpenJDK 21 build as the previous x86 image, run natively, while the x86 otatools binaries run through Rosetta (`libc6:amd64`). The only Java step is signapk (APEX containers, APKs inside APEX, the OTA package). signapk requires Conscrypt's JNI library, which otatools ship for x86 only, so `scripts/install-signing-arm64.py --profile <name>` builds `libconscrypt_openjdk_jni.so` for arm64 offline from the same tree's `external/boringssl` and `external/conscrypt` (`scripts/signing-arm64/`), stores it next to that toolchain and pins it with the image ID and Java version in `.local/signing-toolchain/runtime-arm64.json`. The helper runs the image by ID and checks the library hash. `--runtime amd64` keeps the previous x86 image.

## Packaging

The packaging helper uses the pinned build image and nonroot user, no network or Docker socket, read-only toolchain/tools/keys/input mounts, a separate writable output directory and the shared build lock. Builds take that lock with Linux `flock` inside the Docker VM, which a macOS `flock` does not see, so the host helper also holds it from a small container for the whole run. It inventories the input, checks supported key mappings, verifies passwords, invokes `sign_target_files_apks -o`, checks both system/recovery OTA certificate stores and calls `ota_from_target_files` to generate a local ZIP and SHA256. It refuses pre-existing output directories and unsupported compressed APKs, packaged APEX outside an APEX profile, or image-signing configurations.

For packaged APEX, each module uses `apex/<name>` as container key and, decrypted to a PEM in the container's `/dev/shm`, as payload key (avbtool takes no password). After signing, the helper checks every APEX container and compressed inner container certificate, the payload public key, and that every APK inside each payload is signed by a planned key.

Current validation covers inventory, mapping, refusal paths and key backup restoration. Native synthetic APK signing, PRESIGNED preservation and report generation passed. A regression check confirmed upstream certificate ZIP writing works on disposable copies. The first old run signed APKs but failed when upstream ZipWrite tried chmod/utime on a read-only certificate; persistent keys now stay read-only while disposable copies allow this operation. A resulting ZIP is a local test candidate, not a verified release. It must undergo independent APK/OTA signature checks, installation and runtime validation before publication.

Bullhead user builds add legacy dm-verity and boot signing. These require a separate explicit verity key and public-key replacement plan; the current development signer deliberately refuses such inputs. This is separate from AVB, and nothing here enables bootloader locking. Retain rooted debugging and rollback until a separately tested release policy is chosen.

The installed development ROM currently uses a different signing identity. Signing local and public candidates consistently helps after a tested migration, but does not make the initial migration automatically data preserving. Recovery trust and system-app/package-manager data need migration testing before OTA advertisement.

`scripts/migrate-package-signatures.py` moves an existing installation's `/data/system/packages.xml` from the development identities to the release ones. It takes the candidate's `signing-plan.json` and `native-signing-report.json`, replaces only the mapped certificates and keyset public keys, keeps third-party certificates, and gives packages the candidate still ships with an old certificate (PRESIGNED CtsShim) their own certificate index. It refuses binary ABX files, a database that already holds a release certificate, packages whose candidate APK certificate is missing or different, and shared UIDs that would mix identities. Run it on a copy pulled while Android is not running, then restore the result with the original owner, mode and SELinux label before booting the candidate. It renumbers certificate entries in first-use order, because Android appends each defining entry rather than storing it at its index, and checks that the result reads back that way. Tested on bullhead: flashing a release-signed candidate over a test-key install from TWRP, then installing the migrated database before first boot, kept all 209 packages and their data with no signature warnings.

Progress is printed for each APK. `signing.log` captures the host/native run and packaging output; `packaging.log` separately retains Linux tool output and failures. `native-signing-report.json` contains input/output SHA256 and verified per-APK signer fingerprints. Passwords are excluded from logs. The pre-signed ZIP uses extra temporary disk space, but does not duplicate the Android source tree.

Before any key is used, a full-input preflight parses metadata, validates all installed APK mappings and minimum SDKs, and verifies existing PRESIGNED APKs. Repeated metadata names are accepted only when their signing fields agree. Repeated installed basenames in separate flattened APEX paths are processed separately under the same validated identity.

## LineageOS key set

`scripts/make-signing-keys.py --profile lineage-22.2 --target-files <input> <keys>/lineage-release-v1` generates the set like `development/tools/make_key` (RSA-2048 core and app keys, RSA-4096 APEX keys, PKCS#8 encrypted with PBE-SHA1-3DES, certificates valid 10000 days) in the pinned arm64 image, offline. It asks for one password twice with hidden input, checks each key against its certificate, and writes `fingerprints.json` and `source-mapping.json`. The APEX list comes from the target-files; a build that adds an APEX needs a key for it before signing.
