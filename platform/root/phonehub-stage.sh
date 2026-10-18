#!/bin/busybox sh
cp /phonehub-lan-repair.sh /gbos/gbrunch/phonehub-lan-repair.sh || return 1
cp /phonehub-repair.rc /gbos/gbrunch/phonehub-repair.rc || return 1
chmod 0644 /gbos/gbrunch/phonehub-lan-repair.sh /gbos/gbrunch/phonehub-repair.rc
