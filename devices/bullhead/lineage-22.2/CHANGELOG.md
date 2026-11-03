# LineageOS 22.2 for the Nexus 5X: changes

Each section is copied into the release description of the build with the same tag, with the security patch level line added second after an "Android:" line, first otherwise. Every line reads "Area: plain sentence."

## 22.2-20261103-UNOFFICIAL-bullhead

- Android: LineageOS 22.2, based on Android 15, with SELinux enforcing and file-based encryption.
- Kernel:
  - eBPF: backported, so the Android 15 network stack, data usage and tethering counters work.
  - Security fixes: backported for binder, the GPU driver and core dumps.
- Performance: the CPU is boosted until boot completes, memory management is tuned for this phone, and the GPU minimum clock is raised while the screen is touched.
- Bootloop of death (BLOD): an optional 4-core mode can be switched on in recovery and is shown in About phone.
- VoLTE and Wi-Fi calling: can be turned on for carriers that support them; see the [test report](https://rthery.github.io/android_builds/lineage-22.2/22.2-20261103-UNOFFICIAL-bullhead/) for what was tested.
- Wi-Fi QR codes: scanning works; the scanner read the wrong part of the camera image.
- Factory reset protection: works, and OEM unlocking can be turned off in Developer options.
- Mobile data icon: no longer shows "!" after a SIM is inserted or unlocked while the phone is on.
- Camera: the video preview no longer freezes.
- Updater: importing a local update no longer fails when the screen turns off.
- USB tethering: uses NCM, which macOS and Linux support without extra drivers.
- MMS: malformed notifications can no longer crash the phone.
- SIM PIN screen: stays visible over notifications.
- Widevine DRM: works with the original HALs.
- Translations: updated from LineageOS.
