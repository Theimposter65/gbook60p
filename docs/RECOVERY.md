# Installation recovery

Keep the external `--backup` directory. It contains the original primary and backup GPT sectors, the reviewed plan, firmware entries before/after registration, prepared images and `status.json`. These records identify your hardware and stay out of Git.

If copying or readback fails **before** GPT commit, the original partition table remains in place. Only previously unallocated extents received writes. Do not repeatedly retry a controller that resets; return to Windows and inspect its health and firmware first.

If GPT commit fails while the installer is still running, it attempts to restore the original two GPT copies and verifies the restored checksum. An abrupt power failure can interrupt that process. Keep the saved GPT files and use a Linux live environment for reviewed recovery; never restore a GPT to another disk or after changing partition geometry.

If payload installation succeeds but UEFI registration fails, `status.json` says so. Do not reinstall blindly. The **new** EFI partition contains `\EFI\BOOT\BOOTX64.EFI`, which firmware's boot-from-file menu can select. From Linux, identify its GPT slot using the saved plan and register that new EFI partition with `efibootmgr`. Do not copy over Windows boot files. Existing Windows boot priority is retained by normal registration.

For Googlebook boot failure, select **Windows Boot Manager** with F12. The normal boot is quiet and retains bounded Android logs in the backing filesystem; it has no automatic debug shell or tracing sampler. Do not reformat a backing partition to investigate a display or Google-login problem.

This preview has no automated uninstall or update tool. To reclaim its space later, first verify the three `GB6P_` entries against your own saved plan, remove only the matching Googlebook firmware entry/partitions, and keep all existing Windows entries/partitions. Never use a plan from someone else's laptop.
