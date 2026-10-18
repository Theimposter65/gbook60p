# Precompiled kernel and matching drivers

Installation uses the existing precompiled kernel; no VM or kernel build is required.

| Input | Pin/source |
| --- | --- |
| Kernel | `6.18.21-android17-5-g3938c8d97142-ab16302624` |
| Kernel SHA-256 | `7816c5d5b3500093e597b7362ecab103d5a32141b100d3eb7a8b33221fce7f41` |
| Kernel source | [Android common kernel 3938c8d97142](https://android.googlesource.com/kernel/common/+/3938c8d97142) |
| Realtek driver source | [Same tree's rtw89 stack](https://android.googlesource.com/kernel/common/+/3938c8d97142/drivers/net/wireless/realtek/rtw89/) |
| Linux firmware baseline | [linux-firmware](https://gitlab.com/kernel-firmware/linux-firmware), commit `d5455717ead0affc6116809d8c6e71f95c63e8e1` |
| SOF ARL firmware/topology | [sof-bin v2026.09.2](https://github.com/thesofproject/sof-bin/tree/v2026.09.2) |
| Compatibility/GRUB/tool baseline | [GBRUNCH](https://github.com/danbyumagic/gbrunch), commit `a8936fd33e50efda3f1b36e332ab30b67b709ab1`, V7 asset archive SHA-256 `ba6eac2e2c1482bb3b0e4f4c1aee658b1dc488cce54e5ccbb2726e01fa3376c3` |

`platform.cpio.gz` in the release contains the matched module tree, firmware and precompiled owned helpers. Google init and Minigbm libraries are excluded; they are derived locally from recovery. `MANIFEST.json` hashes each asset; `SOURCES.json` records provenance. Per-component licenses are retained. The source repository contains the owned C helpers, charge-module source and resource overlay XML. The private APK signing key is not needed for installation and is not distributed.

The Wi-Fi stack replaces only `cfg80211`, `mac80211` and the four `rtw89` modules in the RAM module tree. They were built against the same Google source release and reviewed for the stock ABI/CFI requirements. Rebuilding requires the exact kernel configuration, exported symbols, Clang/CFI settings and matching generated headers; matching `vermagic` alone is insufficient. The full historical build workspace is deliberately not included, so this kit does **not** claim a one-command reproducible kernel/module build. Reuse the pinned tested binaries for installation. A new kernel requires a fresh ABI review and hardware testing.

The small `gbos-motobook-charge.ko` is GPL-2.0-only and its corresponding source is `platform/src/gbos-motobook-charge.c`. The remaining owned C helpers use the repository MIT license unless their source says otherwise. AOSP, firmware, BusyBox, GRUB and host-tool licenses remain with their upstream owners; this repository's commit attribution does not change them.
