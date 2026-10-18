#!/bin/busybox sh
# Preserve live native sysfs attributes as file/directory bind mounts. Android
# libbase battery reads use O_NOFOLLOW, so symlink aliases are not compatible.
# All generated charge/current values live in RAM; no hardware value is written.
gbos_battery_view() (
 gb_t=$1
 gb_bat=$2
 gb_helper=$3
 [ -d "$gb_bat" ] && [ ! -f "$gb_bat/charge_full" ] && [ -f "$gb_bat/energy_full" ] || return 0
 mkdir -p "$gb_t/battery-source" "$gb_t/battery-view" || return 1
 mount --bind "$gb_bat" "$gb_t/battery-source" || return 1
 gb_ok=1
 : > "$gb_t/battery-view-mounts"
 for gb_attr in "$gb_t/battery-source"/*; do
  [ -e "$gb_attr" ] || [ -L "$gb_attr" ] || continue
  gb_name=${gb_attr##*/}
  if [ -L "$gb_attr" ]; then
   # Retain original optional directory links. Battery data files themselves
   # must be native regular sysfs files, never symlinked telemetry aliases.
   ln -s "$(readlink "$gb_attr")" "$gb_t/battery-view/$gb_name" || gb_ok=0
  elif [ -f "$gb_attr" ]; then
   : > "$gb_t/battery-view/$gb_name" || { gb_ok=0; break; }
   if mount --bind "$gb_attr" "$gb_t/battery-view/$gb_name"; then
    echo "$gb_name" >> "$gb_t/battery-view-mounts"
   else gb_ok=0; break; fi
  elif [ -d "$gb_attr" ]; then
   mkdir -p "$gb_t/battery-view/$gb_name" || { gb_ok=0; break; }
   if mount --bind "$gb_attr" "$gb_t/battery-view/$gb_name"; then
    echo "$gb_name" >> "$gb_t/battery-view-mounts"
   else gb_ok=0; break; fi
  fi
 done
 if [ "$gb_ok" = 1 ] && "$gb_helper" --battery "$gb_t/battery-source" "$gb_t/battery-view" && "$gb_helper" --check-battery-view "$gb_t/battery-view"; then
  # Include all native attribute submounts, not only the RAM parent directory.
  if mount -o rbind "$gb_t/battery-view" "$gb_bat"; then
   if "$gb_helper" --check-battery-view "$gb_bat"; then
    touch "$gb_t/battery-ready"
    echo 'Battery view: native attributes stay live and O_NOFOLLOW-readable; derived values in RAM only'
    return 0
   fi
   while IFS= read -r gb_name; do
    [ -n "$gb_name" ] && umount "$gb_bat/$gb_name"
   done < "$gb_t/battery-view-mounts"
   umount "$gb_bat" || return 1
  fi
 fi
 # No incomplete view is exposed to Android. All paths below are our new RAM
 # staging mounts; user data and physical power-supply values remain intact.
 while IFS= read -r gb_name; do
  [ -n "$gb_name" ] && umount "$gb_t/battery-view/$gb_name"
 done < "$gb_t/battery-view-mounts"
 umount "$gb_t/battery-source"
 echo 'Battery compatibility unavailable; original battery view retained'
 return 1
)
