#!/system/bin/sh
# Runs once after Android cgroups exist and before enabling the Power HAL.
base=/postinstall/gbrunch
logs=/postinstall/gbrunch-backing/.gbrunch-native/logs
umask 077
exec >> "$logs/power-efficiency.txt" 2>&1
echo "Power profile generation at $(cat /proc/uptime)"
# Complete the stock platform default setup before the HAL becomes the only
# EPP owner. The matching vendor RC no longer repeats this after boot.
if echo 'cebf688e04873249f1f8d3a3c5898d2fdcd44952f27bebcea60bbbbcb1d85531  /vendor/bin/powertool' | sha256sum -c -; then
 timeout 5 /vendor/bin/powertool set-default-power-preference || echo 'Optional stock default setup returned an error'
fi
# Native CPU-policy comparison completed and retained; no repeat startup probe.
if "$base/powerhint-generator" > "$base/powerhint-generated.json"; then
 echo 'Generated hardware-specific performance power hints'
else
 # system_server and SurfaceFlinger block waiting for IPower; never leave it
 # unstarted. This minimal configuration has no hardware nodes at all.
 echo 'Generator refused unsupported topology; using minimal hint-free configuration'
 echo '{"Nodes":[{"Name":"ProfileState","Path":"vendor.powerhal.gbos.profile","Values":["battery","boost","performance"],"DefaultIndex":2,"ResetOnInit":true,"Type":"Property"}],"Actions":[]}' > "$base/powerhint-generated.json"
fi
chmod 0644 "$base/powerhint-generated.json"
cp "$base/powerhint-generated.json" /vendor/etc/powerhint.json || echo 'Configuration copy failed; Power HAL keeps the existing file'
setprop vendor.powerhal.gbos.ready 1
echo 'Enabling native Power HAL'
