# gbook60p

Googlebook OS installation kit for the **Motorola Motobook 60 Pro**. Uses the precompiled Google x86-64 kernel, matching Xe modules, and the Motobook Wi-Fi, audio, camera, battery and power fixes. Android boots natively alongside Windows.

Supported profile: **MOTOROLA 83NY, Intel GPU 8086:7d51, at least 16 GB RAM**. The existing installation was tested on a Core Ultra 5 225H with Realtek RTL8922AE. The kit checks each laptop rather than using the maintainer's drive IDs. Other Motobook CPU/GPU variants need review before support can be claimed.

**v0.1.0 is an installer preview.** The hardware fixes come from a working installation; the new portable installer has offline build and file-fixture validation, and has not yet completed a fresh physical installation. Read [hardware status](docs/HARDWARE.md) before installing.

## Install

1. Back up Windows and save your BitLocker/device-encryption recovery key. Use **Windows Disk Management** to create one contiguous **128 GiB unallocated extent** for the default 120 GiB Android storage. Leave it unformatted. The installer never shrinks or formats an existing partition.
2. Prepare an Ubuntu 24.04 or newer live USB. Disable Windows Fast Startup and Secure Boot, then press **F12** at startup and boot the USB in UEFI mode. Choose **Try Ubuntu**. Keep the kit and its build files on a **separate external ext4 filesystem with 25 GiB free**; FAT32 cannot hold the preparation files.
3. Install the host tools, authenticate GitHub CLI with access to this private repository, and clone:

   ```sh
   sudo apt update
   sudo apt install git gh python3 gcc e2fsprogs dosfstools mtools util-linux parted efibootmgr mokutil
   gh auth login
   gh repo clone theimposter65/gbook60p
   cd gbook60p
   chmod +x gbook60p
   ./gbook60p setup
   ```

4. The guide checks the hardware, asks before downloading the pinned **59 MB precompiled assets** and **7.73 GB Google recovery ZIP**, builds locally, and lists disks with serials. Select the destination disk and storage size. Review the plan and type the complete target disk serial to install. After success, restart manually and choose **Googlebook OS (Motobook 60 Pro)** in F12. Windows keeps its existing boot priority.

The default allocation is a new 512 MiB EFI partition, 6 GiB system partition and 121.5 GiB backing partition containing 120 GiB of fresh Android storage. Smaller Android sizes (16–512 GiB) are supported; total unallocated space needed is the requested size plus 8 GiB. Build time is typically several minutes after downloading. Full disk write and readback can take longer; progress is shown. No automatic restart occurs.

Private repository access is required to clone and download its release. A repository collaborator can use their own GitHub login; no maintainer token is included.

## Already downloaded the inputs?

```sh
./gbook60p assets --archive /media/USB/gbook60p-assets-v0.1.0.tar.gz
./gbook60p build --recovery /media/USB/lapis-16452207-recovery.zip
./gbook60p doctor
sudo ./gbook60p plan --disk /dev/nvme1n1 --userdata-gib 120
sudo ./gbook60p install --plan work/install-plan.json --backup /media/USB/gbook-install-backup
```

Replace `/dev/nvme1n1` with the disk you identified by **model and serial**. `plan` is read-only. `install` rechecks the hardware, disk identity, original GPT, free-space boundaries and payload hashes, then requires a serial typed in a terminal. It stops if the destination has mounted partitions, active swap or mapped volumes. All images are prepared as regular files first. Only new extents receive payload writes; existing partition entries are preserved. Both GPT copies are backed up before changes. Keep the backup directory.

Neither installation from Windows/WSL, whole-disk erasure nor replacing/updating an existing Googlebook installation is supported by this installer. It refuses an existing `GB6P_` layout.

## Source and assets

Git contains source, configuration, hash pins, tests and documentation. The precompiled kernel/modules/helpers, GRUB and AOSP compatibility components are a separate pinned release asset. Google init and Minigbm modifications are derived locally from the verified recovery; Google system/vendor images, accounts, disk IDs, bugreports, signing keys and build caches are excluded.

See [build and validation](docs/BUILD.md), [kernel provenance](docs/KERNEL.md), [recovery](docs/RECOVERY.md) and [NOTICE](NOTICE). To run the offline regression tests:

```sh
./gbook60p test
```

Independent project; not affiliated with Google or Motorola.
