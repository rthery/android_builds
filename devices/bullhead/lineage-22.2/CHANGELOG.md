# LineageOS 22.2 for the Nexus 5X: changes

Each section is copied into the release description of the build with the same tag.

## 22.2-20261103-UNOFFICIAL-bullhead

- Android 15 (LineageOS 22.2) on the Nexus 5X, with SELinux enforcing, file-based encryption and the 2026-10-01 security patch level.
- The 3.10 kernel carries an eBPF backport, so the Android 15 network stack, data usage and tethering counters work. Kernel security fixes backported for binder, the GPU driver and core dumps.
- Faster and smoother: CPU boost until boot completes, tuned memory management, GPU boost while touching the screen. The first boot after an update takes about 40 seconds.
- Optional 4-core mode for phones with the bootloop of death (BLOD), switched in recovery and shown in About phone.
- VoLTE and Wi-Fi calling can be turned on for carriers that support them; see the test report.
- Wi-Fi QR codes scan again: the scanner decoded the wrong part of the camera image on this phone's rear camera.
- Factory reset protection works: OEM unlocking can be turned off in Developer options again.
- The mobile data icon no longer shows "!" after a SIM is inserted or unlocked while the phone is on.
- Camera: the video preview in the camera app no longer freezes.
- Updater: importing a local update no longer fails when the screen turns off.
- USB tethering uses NCM, which macOS and Linux support without extra drivers.
- Fixes: malformed MMS notifications can no longer crash the phone, the SIM PIN screen stays visible over notifications, and Widevine DRM works with the original HALs.
- Updated translations from LineageOS.
