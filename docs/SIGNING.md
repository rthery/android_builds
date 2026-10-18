# Local candidate signing

Local full candidates can use the same stable signing identity as public releases. Keep ordinary builds incremental, then sign their target-files in a separate protected step. Do not place private keys or passwords inside the Android checkout, GitHub runner, repository or build logs. A system APK tested on a release-signed installation also needs its matching signing identity; an ordinary test-key APK is not a compatible replacement.

The currently audited bullhead development target uses flattened APEX, seven core app certificate families, eight additional app identities and some PRESIGNED third-party packages. The signer preserves PRESIGNED packages and maps each other identity to its own private replacement. Testkey maps to releasekey. Catalog APEX entries do not imply that packaged APEX payloads are shipped.

The helper signs APKs with native macOS ARM64 Java/apksigner using two workers, verifies each signature and certificate, then passes a ZIP with verified APKs marked PRESIGNED to the isolated Linux image/OTA packaging step. The original signing plan still drives SELinux certificate and OTA trust replacement. The Linux step verifies the pre-signed ZIP hash and report before processing.

The isolated helper is:

```bash
bash scripts/sign-local-candidate.sh /absolute/path/to/target-files.zip /absolute/path/to/new-candidate-directory --jobs 2
```

Run from an interactive terminal; it asks for the two key passwords with hidden input. Do not run it in public CI, and do not pass passwords as arguments or paste them into chat. Native APK signing passes each key password over stdin; the packaging password file exists only in the container's memory-backed `/dev/shm` and is removed on completion/error. No key password is passed as a process argument or uploaded to GitHub.

## Signing toolchain

Packaging never runs tools from `out/`, which Actions jobs can write. Build `otatools.zip` in the local build container with its own output directory (not mounted in the runner) and ccache off, then install it once on the host:

```bash
docker exec eos-bullhead-work bash /eos/public/android_builds/scripts/build-signing-toolchain.sh lineage_bullhead-userdebug
python3 scripts/install-signing-toolchain.py /Volumes/eOS-Build/src/android/out-signing/target/product/bullhead/otatools.zip
```

The install step unpacks it read-only into `.local/signing-toolchain/<zip sha256>/`, writes a per-file SHA256 manifest and pins the manifest hash in `.local/signing-toolchain/current.json`. Before asking for passwords, the host helper checks every file against the manifest and refuses missing, extra, changed or linked files. The packaging container mounts only that toolchain, with `PATH` and `LD_LIBRARY_PATH` limited to it and the image's `/usr/bin:/bin`. Rebuild and reinstall the toolchain after updating `build/make` or host tool sources.

The input target-files also carries code: `META/releasetools.py` and command names in `META/misc_info.txt`. The helper passes the device tree's `releasetools.py` with `-s` and refuses an input whose embedded copy differs from it. It refuses any `misc_info.txt` key outside the set this pipeline expects, command keys other than the expected `ext_mkuserimg` and `lpmake` values, and `*_args` values holding anything but flags and numbers. Add a key to that list only after checking how the release tools use it. Signing still trusts the content of the target-files; only device testing and source review cover that.

## Packaging

The packaging helper uses the pinned build image and nonroot user, no network or Docker socket, read-only toolchain/tools/keys/input mounts, a separate writable output directory and the shared build lock. It inventories the input, checks supported key mappings, verifies passwords, invokes `sign_target_files_apks -o`, checks both system/recovery OTA certificate stores and calls `ota_from_target_files` to generate a local ZIP and SHA256. It refuses pre-existing output directories and unsupported compressed APKs, packaged APEX or image-signing configurations.

Current validation covers inventory, mapping, refusal paths and key backup restoration. Native synthetic APK signing, PRESIGNED preservation and report generation passed. A regression check confirmed upstream certificate ZIP writing works on disposable copies. The first old run signed APKs but failed when upstream ZipWrite tried chmod/utime on a read-only certificate; persistent keys now stay read-only while disposable copies allow this operation. A resulting ZIP is a local test candidate, not a verified release. It must undergo independent APK/OTA signature checks, installation and runtime validation before publication.

Bullhead user builds add legacy dm-verity and boot signing. These require a separate explicit verity key and public-key replacement plan; the current development signer deliberately refuses such inputs. This is separate from AVB, and nothing here enables bootloader locking. Retain rooted debugging and rollback until a separately tested release policy is chosen.

The installed development ROM currently uses a different signing identity. Signing local and public candidates consistently helps after a tested migration, but does not make the initial migration automatically data preserving. Recovery trust and system-app/package-manager data need migration testing before OTA advertisement.

`scripts/migrate-package-signatures.py` moves an existing installation's `/data/system/packages.xml` from the development identities to the release ones. It takes the candidate's `signing-plan.json` and `native-signing-report.json`, replaces only the mapped certificates and keyset public keys, keeps third-party certificates, and gives packages the candidate still ships with an old certificate (PRESIGNED CtsShim) their own certificate index. It refuses binary ABX files, a database that already holds a release certificate, packages whose candidate APK certificate is missing or different, and shared UIDs that would mix identities. Run it on a copy pulled while Android is not running, then restore the result with the original owner, mode and SELinux label before booting the candidate. It renumbers certificate entries in first-use order, because Android appends each defining entry rather than storing it at its index, and checks that the result reads back that way. Tested on bullhead: flashing a release-signed candidate over a test-key install from TWRP, then installing the migrated database before first boot, kept all 209 packages and their data with no signature warnings.

Progress is printed for each APK. `signing.log` captures the host/native run and packaging output; `packaging.log` separately retains Linux tool output and failures. `native-signing-report.json` contains input/output SHA256 and verified per-APK signer fingerprints. Passwords are excluded from logs. The pre-signed ZIP uses extra temporary disk space, but does not duplicate the Android source tree.

Before asking for passwords, a full-input preflight parses metadata, validates all installed APK mappings and minimum SDKs, and verifies existing PRESIGNED APKs. Repeated metadata names are accepted only when their signing fields agree. Repeated installed basenames in separate flattened APEX paths are processed separately under the same validated identity.
