#!/bin/busybox sh
# Optional NPU bring-up for this laptop's Intel 8086:7d1d only. No PCI rebind,
# module unloading, clock overrides or persistent system-image writes.
gb_npu_pci=/sys/bus/pci/devices/0000:00:0b.0
if [ "$(cat "$gb_npu_pci/vendor" 2>/dev/null)" != 0x8086 ] || [ "$(cat "$gb_npu_pci/device" 2>/dev/null)" != 0x7d1d ]; then
 echo 'NPU: different device; optional preload skipped' >> "$L/npu-early.txt"
 return 0
fi
if ! echo '4078ca4af807e3f28b095df0c7539482ec79afc8c69160ef0480e6d7b67722e6  '"$G/firmware/intel/vpu/vpu_37xx_v1.bin" | sha256sum -c - >> "$L/npu-early.txt" 2>&1; then
 echo 'NPU: approved firmware checksum differs; optional preload skipped' >> "$L/npu-early.txt"
 return 1
fi
modprobe intel_vpu >> "$L/npu-early.txt" 2>&1 || true
mdev -s
{
 echo '== NPU PCI driver'; readlink -f "$gb_npu_pci/driver"
 echo '== NPU accelerator nodes'; ls -l /sys/class/accel /dev/accel
 echo '== NPU firmware status'; dmesg | grep -E 'intel_vpu|ivpu|vpu_37' | tail -n 35
} >> "$L/npu-early.txt" 2>&1
