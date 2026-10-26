# Build and validation

The normal path uses `./gbook60p setup`. A local Linux build also works without hardware or root:

```sh
./gbook60p assets --archive /path/gbook60p-assets-v0.1.0.tar.gz
./gbook60p build --recovery /path/lapis-16452207-recovery.zip --out work/payload
```

`profiles/recovery.json` pins the official Lapis 16452207 ZIP by size and SHA-256. The ZIP is streamed to extract six logical partitions without unpacking the 19 GB disk image. `profiles/parts.json` checks every extracted logical image again. A maintainer with those exact cached parts can use `--parts-dir DIR` instead of `--recovery ZIP`; their hashes must still match.

`profiles/assets.json` pins the separate precompiled archive and its internal file manifest. Extraction refuses symlinks, absolute paths, traversal, duplicate names and mismatched hashes. The runtime includes its matching loader/libraries; it does not replace Linux host packages. Kernel compilation is not needed.

The v0.1.0 archive still contains the original precompiled C helpers. Changes to `platform/src/gbos-powerhint.c` and `platform/src/gbos-charge-hal.c` are source updates only until a rebuilt asset archive is published and its pins are updated. The payload builder overlays shell, XML and init files from this checkout, but does not compile those C helpers.

Build steps:

1. Verify all cached assets and Google input hashes.
2. Concatenate the immutable EROFS logical images and generate `super.layout` for stage0 and dmctl.
3. Derive a separate vendor image with scoped compatibility policy and disabled Google-board firmware maintenance tools. Preserve inode metadata and SELinux labels.
4. Derive a fresh AOSP compatibility image containing the pinned software-security services, runtime init and a fstab without physical disk formatting or encryption entries.
5. Apply two exact-byte Google init changes for requested permissive mode and the reviewed one-device Minigbm mask addition. Original recovery images remain unchanged; only RAM copies are bound at boot.
6. Assemble a base ramdisk containing matching modules/firmware and the owned hardware fixes. Emit `payload.json` with all output hashes.

Installation adds a serial/GPT/boundary guard to that base ramdisk, creates unique filesystem labels and updates GRUB's same-size embedded label redirect. Both new EFI and system FAT images contain identical boot files. Android data, metadata, boot-control misc and logs are bounded files on a separate new ext4 partition. Boot does not format missing userdata; it stops instead.

`./gbook60p test` runs regular-file GPT corruption, partition-preservation and write-boundary fixtures, plus compiled battery and power-helper fixtures. Tests never boot a VM or Android and never open a physical disk for writing. CI runs these without downloading OS images or binary assets.

For local full file-image validation after building:

```sh
sudo python3 tools/validate_build.py --payload work/payload --out work/validation
```

This verifies the built payload and constructs new FAT/ext4 images with synthetic disk IDs; it does not install them. `--out` must be new. Retain only outputs needed for a local installation; all build inputs/outputs, caches, install plans and backup directories are ignored by Git. Do not upload generated Google images, personal logs, keys or populated userdata.
