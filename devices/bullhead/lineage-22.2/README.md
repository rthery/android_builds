# Build LineageOS 22.2 for Nexus 5X

Unofficial LineageOS 22.2 (Android 15) for `bullhead`, on the 3.10 kernel with an eBPF backport. Tested with LineageOS manifest commit `10ba61c`.

## Download sources

Use a Linux environment with the LineageOS build dependencies, `repo`, Git LFS and Python 3.

```bash
mkdir lineage-22.2
cd lineage-22.2
repo init -u https://github.com/LineageOS/android.git -b lineage-22.2 --git-lfs
mkdir -p .repo/local_manifests
curl -fsSL -o .repo/local_manifests/bullhead.xml https://raw.githubusercontent.com/rthery/android_builds/main/devices/bullhead/lineage-22.2/bullhead.xml
repo sync -c -j4 --no-clone-bundle --no-tags --fail-fast
```

[`bullhead.xml`](bullhead.xml) pins the device, kernel and the forked components below to exact commits:

| Path | Change |
| --- | --- |
| `build/soong` | Lets a device turn off the shadow call stack: the 8.1 Adreno blobs use x18 as a scratch register. |
| `frameworks/av` | MediaDrm reports "not provisioned" for the Oreo Widevine HAL, so apps can provision Widevine. |
| `frameworks/base` | SystemUI keeps the SIM PIN bouncer visible when a heads-up notification appears (it blinked at boot). |
| `frameworks/opt/telephony` | Drops WAP push messages whose header length exceeds the message, instead of crashing the phone process. |
| `hardware/interfaces` | Audio service sizes the binder threadpool before starting it. |
| `hardware/lineage/interfaces` | Restores the legacy Wi-Fi and GNSS HALs (from Ultra-Legacy-Hippeastrum). |
| `hardware/qcom/audio` | Ultra-Legacy-Hippeastrum base, skips undeclared AIDL power services. |
| `hardware/qcom/bt`, `hardware/qcom/gps` | Restore msm8992 support. |
| `hardware/qcom/display`, `hardware/qcom/media` | Ultra-Legacy-Hippeastrum, which keeps msm8994 and msm8974. |
| `hardware/sony/timekeep` | Restores the clock before the first unlock. |

## Extract vendor blobs

From the source directory:

```bash
BLOBS="$(mktemp -d)"
git -C vendor/lge/bullhead archive 3bce2e142f622a354ae248214e31b6b4424fdfef proprietary | tar -x -C "$BLOBS"
device/lge/bullhead/extract-files.py "$BLOBS/proprietary"
```

`extract-files.py` copies the blobs in `device/lge/bullhead/proprietary-files.txt` into `vendor/lge/bullhead`, applies the Android 15 fixes in its `blob_fixups` (each pinned by input and output SHA-1) and regenerates the vendor tree. Run it again after `repo sync` restores the vendor checkout.

## Compile

```bash
source build/envsetup.sh
lunch lineage_bullhead-bp1a-userdebug
m target-files-package otatools-package
```

Sign the target-files with your own keys (see [signing](../../../docs/SIGNING.md)) before installing.
