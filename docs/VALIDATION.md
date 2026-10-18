# Release validation

Offline validation on 2026-10-18, with no VM/Android boot test or physical disk writes:

| Check | Result |
| --- | --- |
| Tracked source | 95 files, approximately 0.92 MiB before this evidence note; credential/generated-payload scan passed |
| Regression suite | 13 tests: GPT corruption, Windows entry/content preservation, guarded writes, serial quoting, initramfs directory ordering, battery refresh and CPU topology |
| Local payload build | Six pinned cached EROFS inputs; vendor overlay and compatibility-image readbacks passed |
| Installation image preparation | Both FAT boot copies, boot-tool directory paths, fresh sparse userdata/metadata/misc/log images, ownership, backing-directory mode and shell syntax passed |
| Driver comparison | 588 kernel modules, 10 firmware files, 3 GPU patch files/config and 7 platform helpers are byte-identical to the installed production payload |
| Earlier boot-confirmed comparison | 613 driver/firmware/GPU-related files are byte-identical to the prior boot-confirmed CPU-clock build |

Reference kernel SHA-256: `7816c5d5b3500093e597b7362ecab103d5a32141b100d3eb7a8b33221fce7f41`.

Earlier boot-confirmed initrd SHA-256: `8f6e4ae68bcad26e45a03deecb9de004910987f14c73fad5510373d19252240d`.

Installed production initrd SHA-256: `0148f9144120e665c0d4c7bbcca2257045d8552235e272ce0c8e0d1b17ab838c`.

Compared with that production initrd, 651 file contents are unchanged. The portable kit intentionally changes stage0 labels/storage size, the serial/GPT/boundary guard and compatibility-image hash config. It removes personal target/protected GUID configs; installation generates new ones. The compatibility image contains the same runtime init directly, so its hash differs from the old base-plus-RAM-overlay arrangement.

This comparison confirms reuse of the working drivers and graphics patches. It does **not** establish a successful physical boot of the new per-install storage path, latest battery/headset fixes, or support for every Motobook variant. Those limits are also documented in HARDWARE.md.
