# Install LineageOS 22.2 on the Nexus 5X

Unofficial build for the LG Nexus 5X (`bullhead`) only.

## Before you start

- Installing **erases everything on the phone**. Back up your data first.
- On your computer, install Google's [Android platform tools](https://developer.android.com/tools/releases/platform-tools) (`adb` and `fastboot`).
- The phone must run Google's last firmware (Android 8.1, bootloader `BHZ32c`). If it doesn't, flash Google's [last factory image for bullhead](https://developers.google.com/android/images#bullhead) first.
- From the [latest release](https://github.com/rthery/android_builds/releases/latest), download the `.zip` package and the `-recovery.img`, with their `.sha256` files, and check them:

  ```bash
  shasum -a 256 -c *.sha256
  ```

## First install

1. On the phone, open **Settings > About phone** and tap **Build number** seven times. Then in **Settings > System > Developer options**, turn on **OEM unlocking** and **USB debugging**.
2. Connect the phone to your computer and unlock the bootloader. Confirm on the phone with the volume keys and the power button. This erases the phone.

   ```bash
   adb reboot bootloader
   fastboot flashing unlock
   ```

3. Flash the recovery, then start it: on the phone, pick **Recovery mode** with the volume keys and press the power button.

   ```bash
   fastboot flash recovery lineage-22.2-<date>-UNOFFICIAL-bullhead-recovery.img
   ```

4. In the recovery, choose **Factory reset > Format data / factory reset**.
5. Choose **Apply update > Apply from ADB**, then on your computer:

   ```bash
   adb sideload lineage-22.2-<date>-UNOFFICIAL-bullhead.zip
   ```

6. Choose **Reboot system now**. The first boot takes a few minutes.

Keep the bootloader unlocked: locking it again with this ROM installed stops the phone from booting.

## Updates

New releases arrive over the air, with your data kept:

1. When a new release is out, the phone shows a notification. To check yourself, open **Settings > System > Updates** and tap the refresh button.
2. Tap **Download**, then **Install**. The phone reboots to the recovery, installs the update and starts again.

The phone checks for updates once a week by default; you can change that in the Updates screen.
