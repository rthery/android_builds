# Build /e/OS for Nexus 5X

## Build environment

Use a Linux amd64 environment with the Android build dependencies, the Android `repo` tool, Git LFS, Java, Python 3 and ccache.

The /e/OS build container provides these dependencies:

```text
registry.gitlab.e.foundation:5000/e/os/docker-lineage-cicd@sha256:786a3e13b33249109e74741abef42bcc2fdf00ca0b619145b82eabe7f3ad4d84
```

## Download sources

```bash
git clone https://github.com/rthery/android_builds.git build-recipe
mkdir android
cd android
repo init -u https://github.com/rthery/android_builds.git -b main -m devices/bullhead/manifest.xml --git-lfs -g 'default,-darwin'
repo sync -c -j4 --no-clone-bundle --no-tags --fail-fast
```

The [manifest](manifest.xml) pins /e/OS 4.4 and the device compatibility changes to specific commits. See [device status](STATUS.md) for working features and known issues.

## Extract vendor blobs

From the Android source directory:

```bash
BLOBS="$(mktemp -d)"
git -C vendor/lge/bullhead archive 3bce2e142f622a354ae248214e31b6b4424fdfef proprietary | tar -x -C "$BLOBS"
device/lge/bullhead/extract-files.sh "$BLOBS/proprietary"
```

`extract-files.sh` copies the blobs listed in `device/lge/bullhead/proprietary-files.txt` into `vendor/lge/bullhead`, applies the Android 13 compatibility fixes in its `blob_fixup` function and regenerates the vendor makefiles with `setup-makefiles.sh`. Each fix checks the original bytes it replaces and stops on an unexpected input. It runs on Linux and needs Java, `xxd` and `zip`; `patchelf` and Smali come from the source tree.

The script rewrites the vendor checkout, so it reads the pinned upstream blobs from a separate copy. Run it again after `repo sync` restores the vendor checkout.

## Compile

```bash
export RELEASE_TYPE=UNOFFICIAL
export USE_CCACHE=1
export CCACHE_EXEC="$(command -v ccache)"
export CCACHE_DIR="$HOME/.cache/ccache-bullhead"
export CCACHE_BASEDIR="$PWD"
export CCACHE_COMPILERCHECK=content
source build/envsetup.sh
lunch lineage_bullhead-userdebug
mka -j6 bacon
```

`lineage_bullhead-userdebug` is the device product name used for this /e/OS build. Build outputs are in `out/target/product/bullhead/`.

## Hosts without working MAP_32BIT support

Some emulated amd64 build environments require the [MAP_32BIT helper](../../scripts/map32.c). Compile and enable it before building:

```bash
gcc -shared -fPIC -o /tmp/libmap32.so ../build-recipe/scripts/map32.c -ldl
export LD_PRELOAD=/tmp/libmap32.so
export ALLOW_NINJA_ENV=true
```

`ALLOW_NINJA_ENV` is needed because the build system otherwise removes `LD_PRELOAD` from build steps such as dex2oat.

Use this only on hosts affected by that limitation. The helper runs on the build host and is not included in the ROM.
