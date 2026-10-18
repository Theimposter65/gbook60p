# Per-install NVMe guard. No formatter, no wildcard writable target.
. /hy-targets.cfg
hy_tool() { hy_program=$1; shift; "$G/installer/lib/ld-musl-x86_64.so.1" --library-path "$G/installer/lib" "$G/installer/bin/$hy_program" "$@"; }
hy_check_partition() {
 hy_n=$1; hy_g=$2; hy_s=$3; hy_z=$4
 [ "$(hy_tool sfdisk --part-uuid "$HY_DISK" "$hy_n" | tr A-F a-f)" = "$hy_g" ] || ssd_stop 'Partition GUID changed'
 [ "$(cat /sys/class/block/${HY_NODE}p${hy_n}/start)" = "$hy_s" ] || ssd_stop 'Partition start changed'
 [ "$(cat /sys/class/block/${HY_NODE}p${hy_n}/size)" = "$hy_z" ] || ssd_stop 'Partition size changed'
}
hy_validate_and_hold_power() {
 DEV=$(readlink -f "$DEV") || ssd_stop 'Cannot resolve system partition'
 case "$DEV" in /dev/nvme[0-9]*n[0-9]*p[0-9]*) ;; *) ssd_stop 'Not an NVMe partition';; esac
 HY_SYS_NODE=${DEV##*/}
 [ -r /sys/class/block/$HY_SYS_NODE/partition ] || ssd_stop 'System is not a partition'
 HY_NODE=$(basename "$(dirname "$(readlink -f /sys/class/block/$HY_SYS_NODE)")")
 HY_DISK=/dev/$HY_NODE; HY_CTRL=${HY_NODE%n*}
 [ "$(cat /sys/class/block/$HY_NODE/device/serial | sed 's/^ *//;s/ *$//')" = "$HY_SERIAL" ] || ssd_stop 'Disk serial changed'
 [ "$(hy_tool sfdisk --disk-id "$HY_DISK" | tr A-F a-f)" = "$HY_DISK_GUID" ] || ssd_stop 'Disk GUID changed'
 [ "$(cat /sys/class/block/$HY_NODE/size)" = "$HY_DISK_SECTORS" ] || ssd_stop 'Disk capacity changed'
 [ "$(cat /sys/class/block/$HY_SYS_NODE/partition)" = "$HY_SYS_NUMBER" ] || ssd_stop 'System partition number changed'
 hy_count=0
 for hy_p in /sys/class/block/${HY_NODE}p*; do [ -r "$hy_p/partition" ] && hy_count=$((hy_count+1)); done
 [ "$hy_count" = "$HY_PARTITION_COUNT" ] || ssd_stop 'Partition count changed'
 while read hy_n hy_g hy_s hy_z; do
  [ -n "$hy_n" ] || continue
  hy_check_partition "$hy_n" "$hy_g" "$hy_s" "$hy_z"
  [ "$hy_n" != "$HY_DATA_NUMBER" ] || ssd_stop 'Data role overlaps protected partition'
 done < /gbook-protected.cfg
 hy_check_partition "$HY_DATA_NUMBER" "$HY_DATA_GUID" "$HY_DATA_START" "$HY_DATA_SECTORS"
 HY_DATA=${HY_DISK}p${HY_DATA_NUMBER}
 HY_PCI=$(readlink -f /sys/class/nvme/$HY_CTRL/device); HY_PORT=$(dirname "$HY_PCI")
 # Keep the controller awake for this storage-stability profile. Never change
 # electrical roles or identify a drive by PCI vendor/product alone.
 for hy_d in "$HY_PCI" "$HY_PORT"; do
  if [ -w "$hy_d/power/control" ]; then echo on > "$hy_d/power/control" || ssd_stop 'Storage power control failed'; fi
  if [ -w "$hy_d/d3cold_allowed" ]; then echo 0 > "$hy_d/d3cold_allowed" || ssd_stop 'Storage D3 guard failed'; fi
 done
 hy_qos=/sys/class/nvme/$HY_CTRL/power/pm_qos_latency_tolerance_us
 if [ -w "$hy_qos" ]; then echo 0 > "$hy_qos" || ssd_stop 'APST guard failed'; fi
 echo 0 > /sys/class/block/$HY_NODE/queue/discard_max_bytes || ssd_stop 'Discard guard failed'
 HY_IDENTITIES_OK=1
 log 'Per-install NVMe serial, disk GUID and all partition boundaries verified'
}
