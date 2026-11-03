# Android builds

Device-specific build manifests and compatibility fixes for LineageOS.

## Devices

To install a ROM, follow the **Install** link for your device. The rest of this page is for people who build the ROMs.

| Device | Version | Install and update | Build instructions | Manifest |
| --- | --- | --- | --- | --- |
| Nexus 5X (`bullhead`) | LineageOS 22.2, Android 15 (unofficial) | [Install](devices/bullhead/lineage-22.2/INSTALL.md) | [Build](devices/bullhead/lineage-22.2/README.md) | [Local manifest](devices/bullhead/lineage-22.2/bullhead.xml) |

Builds start from the LineageOS manifest plus the device's local manifest, which pins every changed project to an exact commit; the build instructions show the steps. Each `devices/<codename>/<version>/` directory holds that local manifest, the build and install instructions and the release notes.

See [repository organization](docs/REPOSITORIES.md) for component sources and adding devices.

## Automated builds

See [build automation](docs/BUILD_AUTOMATION.md) for manual GitHub Actions builds using a shared self-hosted builder.

## Support

Builds and sources are free. If you want to support the work, see [how to support it](docs/SUPPORT.md).
