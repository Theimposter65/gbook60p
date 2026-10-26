#!/bin/busybox sh
# Only this laptop; all configuration/views are retained in RAM. Optional
# failure must never prevent the original working Android boot.
[ "$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null)" = MOTOROLA ] && [ "$(cat /sys/class/dmi/id/product_name 2>/dev/null)" = 83NY ] || return 0
T=/gbos/gbrunch/telemetry
[ -d /gbos/gbrunch/peripherals/vendor-etc ] && [ "$(stat -c '%d:%i' /gbos/gbrunch/peripherals/vendor-etc)" = "$(stat -c '%d:%i' /new/vendor/etc)" ] || return 1
mkdir -p "$T" || return 1
cp /gbos-telemetry /gbos/gbrunch/gbos-telemetry || return 1
chmod 0755 /gbos/gbrunch/gbos-telemetry
# The copy above is the Android (NDK) build for the runtime service; it needs
# /system/bin/linker64. Pre-Android steps here use the static build.
TB=/gbos-telemetry-static
[ -x "$TB" ] || TB=/gbos-telemetry
cp /platform-telemetry.rc /gbos/gbrunch/platform-telemetry.rc || return 1
modprobe x86_pkg_temp_thermal >> "$L/platform-telemetry.txt" 2>&1 || true
if "$TB" --thermal '' "$T/thermal_info_config.json"; then
 if echo 'b5de8e2c47ee9b4d0d7b730deb0500e8e36f606adef4bd941597c26d5de6868d  /new/vendor/etc/thermal_info_config.json' | sha256sum -c - >> "$L/platform-telemetry.txt" 2>&1 && echo 'd40c791fac016b823c192b51c4816f8e43187f01e7b03920de7662e36d072ed7  /new/vendor/etc/thermal/lapis/thermal_info_config.json' | sha256sum -c - >> "$L/platform-telemetry.txt" 2>&1; then
  cp "$T/thermal_info_config.json" /gbos/gbrunch/peripherals/vendor-etc/thermal_info_config.json
  cp "$T/thermal_info_config.json" /gbos/gbrunch/peripherals/vendor-etc/thermal/lapis/thermal_info_config.json
  echo 'Mapped actual Intel package sensor; no cooling or trip-point changes' >> "$L/platform-telemetry.txt"
 fi
else
 echo 'No valid Intel package sensor; original thermal config retained' >> "$L/platform-telemetry.txt"
fi
. /battery-view-stage.sh
gbos_battery_view "$T" /sys/class/power_supply/BAT0 "$TB" >> "$L/platform-telemetry.txt" 2>&1 || true
# UCSI online describes a connected port, including source-mode earphones.
# Preserve the physical source view; Android sees incoming power only while
# that connector's actual Type-C power role is sink. Audio/data paths stay live.
for index in 0 1; do
 connector=$((index+1))
 psy="/sys/class/power_supply/ucsi-source-psy-USBC000:00$connector"
 port="/sys/class/typec/port$index"
 [ "$(cat "$psy/scope" 2>/dev/null)" = Device ] && [ -f "$port/power_role" ] || continue
 controller=$(readlink -f "$psy/device")
 portpath=$(readlink -f "$port")
 case "$portpath" in "$controller"/*) ;; *) echo "USB-C $index: controller mapping unproven; supply untouched" >> "$L/platform-telemetry.txt"; continue;; esac
 mkdir -p "$T/usb$index-source"
 if mount --bind "$psy" "$T/usb$index-source"; then
  if "$TB" --usb-online "$T/usb$index-source" "$port/power_role" "$T/usb$index-online" && mount --bind "$T/usb$index-online" "$psy/online"; then
   echo "$port/power_role" > "$T/usb$index-role"
   touch "$T/platform-ready"
   echo "USB-C $index: charging online filtered by actual sink power role" >> "$L/platform-telemetry.txt"
  fi
 fi
done
# Expose only the standard, exact-device ACPI conservation methods. No mode is
# changed on load, and the full input/rfkill/fan platform driver is not loaded.
for acpi in /sys/bus/acpi/devices/VPC2004:*; do
 [ -d "$acpi" ] || continue
 if [ ! -L "$acpi/driver" ]; then insmod /gbos-motobook-charge.ko >> "$L/platform-telemetry.txt" 2>&1 || true; fi
 break
done
if echo 'ba47544b8a12c344384c00386597e3fe0446565ba0ed7e7492ebc9ae2bdd6dc5  /new/vendor/bin/hw/vendor.google.desktop.charge-control-hal' | sha256sum -c - >> "$L/platform-telemetry.txt" 2>&1 && echo 'cbb4569ab234b1473d47d49ee356617a05842f2a41ef1cd5cdcbbaef7df27463  /new/vendor/etc/init/hal_desktop_charge_control_default.rc' | sha256sum -c - >> "$L/platform-telemetry.txt" 2>&1; then
 cp /gbos-charge-hal /gbos/gbrunch/gbos-charge-hal
 chmod 0755 /gbos/gbrunch/gbos-charge-hal
 cp /gbos-charge-hal.rc /gbos/gbrunch/peripherals/vendor-etc/init/hal_desktop_charge_control_default.rc
 echo 'Native charging HAL staged; unsupported policies return explicit errors' >> "$L/platform-telemetry.txt"
fi
return 0
