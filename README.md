# Android builds

Device-specific build manifests and compatibility fixes for /e/OS.

## Devices

| Device | Version | Build instructions | Status | Manifest |
| --- | --- | --- | --- | --- |
| Nexus 5X (`bullhead`) | /e/OS 4.4, Android 13 | [Build](devices/bullhead/README.md) | [Status](devices/bullhead/STATUS.md) | [Manifest](devices/bullhead/manifest.xml) |

Select the device manifest when initializing an Android source checkout. For example:

```bash
repo init -u https://github.com/rthery/android_builds.git -b main -m devices/bullhead/manifest.xml --git-lfs -g 'default,-darwin'
```

Each `devices/<codename>/` directory contains its manifest, build instructions, device status and any device-specific build files. Manifests pin exact source commits. There is no default device.

See [repository organization](docs/REPOSITORIES.md) for component sources and adding devices.

## Automated builds

See [build automation](docs/BUILD_AUTOMATION.md) for manual GitHub Actions builds using a shared self-hosted builder.

## Support

Builds and sources are free. If you want to support the work, see [how to support it](docs/SUPPORT.md).
