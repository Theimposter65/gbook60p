#!/bin/busybox sh
# This port supports ordinary KVM guests, not Google's Trusty-backed service.
# Do not advertise an unavailable Secretkeeper: AVF otherwise waits forever
# while allocating an instance ID, before its Linux guest can start.
# The overlay is private RAM; Android data and source images stay unchanged.
gb_sk_manifest=/new/vendor/etc/vintf/manifest/android.hardware.security.secretkeeper.trusty.xml
if echo '971716db36d6c50cf01942618a626571c14bf365d16973283a78b1e2f33a62c2  '"$gb_sk_manifest" | sha256sum -c -; then
 mkdir -p /gbos/gbrunch/terminal || return 1
 cp /terminal-no-secretkeeper.xml /gbos/gbrunch/terminal/no-secretkeeper.xml || return 1
 chmod 0644 /gbos/gbrunch/terminal/no-secretkeeper.xml || return 1
 mount --bind /gbos/gbrunch/terminal/no-secretkeeper.xml "$gb_sk_manifest" || return 1
 echo 'Terminal: unavailable Trusty Secretkeeper declaration hidden; ordinary KVM unchanged' >> "$L/terminal-early.txt"
else
 echo 'Terminal: Secretkeeper manifest differs; original declaration retained' >> "$L/terminal-early.txt"
 return 1
fi
