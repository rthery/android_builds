# LineageOS 22.2 for the Nexus 5X: changes

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): add a line under "Unreleased" with each change that ships, and rename that section to the release tag before approving the release. The testing prerelease shows "Unreleased" until then. Each tag's section is copied into the release description, with the security patch level line added second after an "Android:" line, first otherwise. Every line reads "Area: plain sentence."

## Unreleased

- Wi-Fi calling: comes back within seconds when the network closes the Wi-Fi calling connection while the phone sleeps. Before, the reconnect waited for the next wake, up to 17 minutes without Wi-Fi calling.

## 22.2-20261117-UNOFFICIAL-bullhead

- Wi-Fi calling: works on carriers that require SHA-2, such as SFR, and is switched on from the SIM settings, with no adb step. It now runs in Android instead of the modem: outgoing and incoming calls and SMS over Wi-Fi. When it is off or not registered, calls and SMS go over the mobile network as before. Emergency calls never go over Wi-Fi.
- Kernel: IPsec tunnel interfaces (VTI) and the XFRM output mark are backported for Wi-Fi calling.
- Kernel: upstream kernfs and cgroup fixes (races when a sysfs or cgroup file is released, cgroup socket and mount option handling) and the bpf_ktime_get_boot_ns eBPF helper, so the optional tethering offload programs that record flow activity now load.
- Wi-Fi hotspot: tethered devices stay fast while the screen is off. The phone no longer suspends between bursts of hotspot traffic; it stays awake for 1 second after each one and still sleeps when the connected devices are idle.
- Storage: writes to shared storage (photos, downloads, files) are about 1.7 times faster and use less CPU. The kernel now sends them to the storage service in batches (FUSE writepages, backported from Linux 3.13).
- Memory:
  - Zygote: only the 64-bit zygote runs, which frees about 40 MB at idle. WebView now runs as a 64-bit process. Apps that only ship 32-bit native code can no longer be installed, and one that is already installed is removed by the update.
  - Swap: swappiness is set to 100, so idle app memory is compressed before cached files are dropped. About 22 MB more stays free with 18 apps open.
- Mobile data: an SFR preferred APN setting that never took effect is removed. SFR SIMs still use sl2sfr, the only internet APN they match.
- Wi-Fi calling: when Wi-Fi goes away, calls and SMS move to the mobile network within seconds instead of failing until the next registration refresh, up to 30 minutes later. Calls over Wi-Fi are now marked as Wi-Fi calls in the dialer and the call log.
- Wi-Fi calling: stays registered while mobile data is on. SFR keeps one calling registration per SIM, so the modem's own registration over LTE is switched off while Wi-Fi calling is in use and back on when Wi-Fi goes away. Before, the Wi-Fi calling connection was dropped every minute, or silently replaced.
- Wi-Fi calling: a mobile call no longer drops when Wi-Fi comes back during it; Wi-Fi calling takes over once the call ends.
- Wi-Fi calling: a Wi-Fi call the network rejects after ringing now ends properly. Before, the phone stayed in a call that blocked new calls until a reboot.
- Wi-Fi calling: when the network ends the registration, the phone registers again instead of showing Wi-Fi calling as available while incoming calls were lost.
- Emergency calls: calls placed over the mobile network, outside VoLTE, now reach the modem. The radio service dropped them and they stayed on "Dialing"; this applied while Wi-Fi calling was registered and whenever VoLTE was not. Checked with a test emergency number, not a real emergency call.

## 22.2-20261106-UNOFFICIAL-bullhead

- Kernel:
  - Wi-Fi: networks with protected management frames (PMF optional, or WPA2/WPA3 mixed mode) now connect.
  - Binder: the driver is updated to the Android 4.19 common kernel version.
  - eBPF: the arm64 JIT compiler and the eBPF features Android expects from 4.19 and 5.4 kernels are backported, in preparation for Android 16.
  - Memory: background apps can be compacted (MADV_PAGEOUT and process_madvise are backported).
  - Storage: eMMC clock scaling is stopped before suspend, a fix from the Qualcomm kernel.
  - Encryption: file decryption runs on an unbound workqueue, which makes random reads on encrypted storage slightly faster.
  - Stability: a kernel panic when an app renames one of its threads is fixed.
- Performance:
  - App launches: the CPUs are boosted while an app starts.
  - UI: the foreground app's UI threads run with real-time priority.
  - Storage: the ROW I/O scheduler is used after boot.
  - Vendor daemons: they run on the background CPU set.
  - App start: 64-bit apps start from a pool of pre-forked processes.
- Memory: background apps are compacted when memory runs low, so more of them stay in memory instead of restarting.
- Factory reset protection: after a reset, setup asks for the previous screen lock when protection is still on, so moving from a GApps install to one without GApps no longer leaves it stuck. Settings no longer crashes when OEM unlocking is tapped while protection is on.
- Setup: the time zone detected on the date page is kept.
- Wi-Fi QR codes: the scanner preview is no longer grey after the first boot.

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
