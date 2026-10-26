#!/bin/busybox sh
# Optional, pre-Android display configuration for the exact 83NY OLED panel.
# Adds one display_id file in a RAM view; original EROFS bytes stay unchanged.
gbos_display_config_stage() (
 S=$1; V=$2; R=$3; X=$4
 D=$V/etc/displayconfig
 if grep -qw 'androidboot.gbos_display=legacy' /proc/cmdline; then echo 'Legacy display mode requested; panel configuration not staged'; return 1; fi
 [ "$(cat "$S/class/dmi/id/sys_vendor" 2>/dev/null)" = MOTOROLA ] && [ "$(cat "$S/class/dmi/id/product_name" 2>/dev/null)" = 83NY ] || return 1
 edid=
 for f in "$S"/class/drm/card*-eDP-*/edid; do [ -f "$f" ] && edid=$f && break; done
 [ -n "$edid" ] || { echo 'No eDP EDID'; return 1; }
 # Luminance values in the XML come from this EDID; any other panel keeps defaults.
 echo "2b3879acc4e51f3290cc39f9c1980fa6d2e791566f70dd4a76bea3daef4fa036  $edid" | sha256sum -c - || return 1
 echo "140f2e4f02410868cd592684f8922fe6460918d6e65c89f92b64a86eff0d0877  $D/display_id_4633222797882641664.xml" | sha256sum -c - || return 1
 [ ! -e "$D/${X##*/}" ] && [ ! -e "$R" ] || return 1
 mkdir -p "$R" || return 1
 cp -a "$D/." "$R/" || return 1
 cp "$X" "$R/${X##*/}" || return 1
 chmod 0755 "$R" && chmod 0644 "$R/${X##*/}" || return 1
 for file in "$D"/*; do cmp -s "$file" "$R/${file##*/}" || return 1; done
 mount --bind "$R" "$D" || return 1
 if ! cmp -s "$X" "$D/${X##*/}"; then umount "$D"; return 1; fi
 echo "Display configuration staged: ${X##*/} (1107 nit peak, 497 nit SDR, HDR headroom enabled)"
 for b in "$S"/class/backlight/*; do
  [ -d "$b" ] && echo "backlight ${b##*/}: type=$(cat "$b/type" 2>/dev/null) max_brightness=$(cat "$b/max_brightness" 2>/dev/null) brightness=$(cat "$b/brightness" 2>/dev/null)"
 done
 return 0
)
