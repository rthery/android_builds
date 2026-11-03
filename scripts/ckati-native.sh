#!/bin/sh
# Mounted over prebuilts/build-tools/linux-x86/bin/ckati on arm64 hosts: runs the tree's aarch64 ckati
# natively instead of the x86 one under emulation. Soong always calls the linux-x86 path.
exec "$(dirname "$0")/../../linux_musl-arm64/bin/ckati" "$@"
