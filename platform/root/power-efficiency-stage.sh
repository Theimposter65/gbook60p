#!/bin/busybox sh
# Require the existing preserved RAM vendor/etc view before any replacements.
[ -d /gbos/gbrunch/peripherals/vendor-etc ] || return 1
echo 'c8e4d2dddc1ca490eb8d6f162de31e13e1172eaa95028f74819c82374dfc001c  /new/vendor/bin/hw/android.hardware.power-service.pixel-libperfmgr' | sha256sum -c - || return 1
echo 'b46ee33a65b48d00dd1495cd7c561271a97c12b442399774b5cc13f67b24903b  /new/vendor/etc/init/android.hardware.power-service.pixel-libperfmgr.rc' | sha256sum -c - || return 1
echo '18981d1764a9d1e1dbeebe11e663db9ee5acf3dcd30a4f87e48d48afdfbab121  /new/vendor/etc/powerhint.json' | sha256sum -c - || return 1
echo 'acfa7e4eb54f14dbbc461dcac6707865b8c0ae2d82cde99e54e5dc54f000162b  /new/vendor/etc/init/powertool.rc' | sha256sum -c - || return 1
cp /power-efficiency-hal.rc /gbos/gbrunch/peripherals/vendor-etc/init/android.hardware.power-service.pixel-libperfmgr.rc || return 1
cp /powerhint-generator /gbos/gbrunch/powerhint-generator || return 1
chmod 0755 /gbos/gbrunch/powerhint-generator
cp /power-efficiency-apply.sh /gbos/gbrunch/power-efficiency-apply.sh || return 1
cp /power-efficiency.rc /gbos/gbrunch/power-efficiency.rc || return 1
chmod 0644 /gbos/gbrunch/power-efficiency-apply.sh /gbos/gbrunch/power-efficiency.rc
cp /power-policy-powertool.rc /gbos/gbrunch/peripherals/vendor-etc/init/powertool.rc || return 1
