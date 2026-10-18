#!/bin/busybox sh
# Optional, pre-Android resource overlay. No original EROFS or sysfs writes.
gbos_power_profile_stage() (
 S=$1; V=$2; F=$3; R=$4; A=$5
 [ "$(cat "$S/class/dmi/id/sys_vendor" 2>/dev/null)" = MOTOROLA ] && [ "$(cat "$S/class/dmi/id/product_name" 2>/dev/null)" = 83NY ] || return 1
 [ "$(cat "$S/devices/system/cpu/online" 2>/dev/null)" = 0-13 ] || return 1
 [ "$(cat "$S/class/power_supply/BAT0/voltage_min_design" 2>/dev/null)" = 11310000 ] && [ "$(cat "$S/class/power_supply/BAT0/energy_full_design" 2>/dev/null)" = 60000000 ] || return 1
 count=0
 for policy in "$S"/devices/system/cpu/cpufreq/policy*; do
  [ -d "$policy" ] || continue
  id=${policy##*/policy}
  case "$id" in 0|1|2|3|4|5|6|7|8|9|10|11|12|13) ;; *) return 1;; esac
  [ "$(cat "$policy/related_cpus" 2>/dev/null)" = "$id" ] || return 1
  count=$((count+1))
 done
 [ "$count" = 14 ] || return 1
 # A newer image/config needs a fresh review; never replace its configuration.
 [ -d "$V/overlay" ] && [ ! -e "$V/overlay/config" ] && [ ! -e "$V/overlay/gbos-power-profile.apk" ] || return 1
 echo "912d33b8117a4bf0b2060af4b0fde0380562daf048775adeede5976b2b07e801  $V/overlay/framework-res__lapis__auto_generated_rro_vendor.apk" | sha256sum -c - || return 1
 echo "06bfd7957974117a58c7b4e2f51a1e09a932715a17522a03f84c3a369eafb6e5  $F" | sha256sum -c - || return 1
 echo "85605e9d107abef2df1dc9f9decbe6a0cdd2deba456d2a1342a5865530e883e3  $A" | sha256sum -c - || return 1
 [ ! -e "$R/vendor-overlay" ] || return 1
 mkdir -p "$R/vendor-overlay" || return 1
 cp -a "$V/overlay/." "$R/vendor-overlay/" || return 1
 for file in "$V/overlay/"*; do
  [ -f "$file" ] && [ ! -L "$file" ] || return 1
  cmp -s "$file" "$R/vendor-overlay/${file##*/}" || return 1
 done
 cp "$A" "$R/vendor-overlay/gbos-power-profile.apk" || return 1
 chmod 0755 "$R" "$R/vendor-overlay" || return 1
 chmod 0644 "$R/vendor-overlay/gbos-power-profile.apk" || return 1
 cmp -s "$A" "$R/vendor-overlay/gbos-power-profile.apk" || return 1
 # Publish the complete RAM view only after all checks have succeeded.
 mount --bind "$R/vendor-overlay" "$V/overlay" || return 1
 if ! cmp -s "$A" "$V/overlay/gbos-power-profile.apk"; then
  umount "$V/overlay"
  return 1
 fi
 echo 'PowerProfile RAM overlay staged: design5305.039788mAh/11310mV,14 single-CPU policies; frequency/current curves unknown'
 for policy in "$S"/devices/system/cpu/cpufreq/policy*; do
  echo "== ${policy##*/}"
  for name in related_cpus scaling_driver cpuinfo_min_freq cpuinfo_max_freq scaling_available_frequencies scaling_min_freq scaling_max_freq energy_performance_preference; do
   [ -f "$policy/$name" ] && echo "$name=$(cat "$policy/$name")"
  done
 done
 return 0
)
