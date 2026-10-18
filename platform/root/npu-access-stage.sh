#!/bin/busybox sh
# Correct only the matching Intel NPU's device naming/permissions in the
# existing retained RAM vendor/etc overlay. Match the stock fatcat access mode.
gb_npu_pci=/sys/bus/pci/devices/0000:00:0b.0
gb_npu_class=/sys/class/accel/accel0
gb_npu_node=/dev/accel/accel0
gb_npu_etc=/gbos/gbrunch/peripherals/vendor-etc
if [ "$(cat "$gb_npu_pci/vendor" 2>/dev/null)" != 0x8086 ] || [ "$(cat "$gb_npu_pci/device" 2>/dev/null)" != 0x7d1d ]; then
 echo 'NPU access: different hardware; skipped' >> "$L/npu-access.txt"
 return 0
fi
if [ "$(readlink -f "$gb_npu_pci/driver")" != /sys/bus/pci/drivers/intel_vpu ] || [ "$(readlink -f "$gb_npu_class/device")" != "$(readlink -f "$gb_npu_pci")" ]; then
 echo 'NPU access: driver/class mismatch; skipped' >> "$L/npu-access.txt"
 return 0
fi
[ -d "$gb_npu_etc" ] && [ "$(stat -c '%d:%i' "$gb_npu_etc")" = "$(stat -c '%d:%i' /new/vendor/etc)" ] || return 1
echo '97f335fe664be21691a74728b03ada98e9ced5913d83c360cf6b14df0956281f  '"$gb_npu_etc/ueventd.rc" | sha256sum -c - >> "$L/npu-access.txt" 2>&1 || return 1
echo '272dede06177f39eff6ff61bae85a6f4da458c51b89c46020d6b7d8522433b16  '"$gb_npu_etc/ueventd/ueventd.fatcat.rc" | sha256sum -c - >> "$L/npu-access.txt" 2>&1 || return 1
# Refuse a symlink, wrong node type or a node belonging to another accelerator.
[ -c "$gb_npu_node" ] && [ ! -L "$gb_npu_node" ] || return 1
gb_npu_number=$(cat "$gb_npu_class/dev" 2>/dev/null)
gb_npu_major=${gb_npu_number%:*}; gb_npu_minor=${gb_npu_number#*:}
case "$gb_npu_major:$gb_npu_minor" in *[!0-9:]*|:*|*:|*:*:*) return 1;; esac
[ "$(stat -c '%t:%T' "$gb_npu_node")" = "$(printf '%x:%x' "$gb_npu_major" "$gb_npu_minor")" ] || return 1
cat "$gb_npu_etc/ueventd.rc" > "$gb_npu_etc/ueventd.gbos-npu.tmp" || return 1
cat >> "$gb_npu_etc/ueventd.gbos-npu.tmp" <<'GBOS_NPU_RULE'

# Intel 8086:7d1d: preserve the kernel DEVNAME=accel/accel0 path.
subsystem accel
    devname uevent_devname
    dirname /dev
/dev/accel/accel0 0666 system system
GBOS_NPU_RULE
chmod 0644 "$gb_npu_etc/ueventd.gbos-npu.tmp" || return 1
mv "$gb_npu_etc/ueventd.gbos-npu.tmp" "$gb_npu_etc/ueventd.rc" || return 1
# mdev created the node before Android's coldplug. Apply the same exact rule
# now; ueventd maintains it when handling the accelerator's later events.
chown 1000:1000 "$gb_npu_node" && chmod 0666 "$gb_npu_node" || return 1
{
 echo 'NPU access: applied stock system:system 0666 mode to validated accel/accel0 in RAM'
 ls -l "$gb_npu_node"
} >> "$L/npu-access.txt" 2>&1
