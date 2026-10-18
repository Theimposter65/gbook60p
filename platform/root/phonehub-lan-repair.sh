#!/system/bin/sh
# User requested Phone Hub repair. Repair only the new LAN permission omitted
# from this exact updated privileged system app; preserve explicit user denials.
base=/postinstall/gbrunch-backing/.gbrunch-native/logs
[ -d "$base" ] || exit 0
umask 077
exec >> "$base/phonehub-lan-repair.txt" 2>&1
user=$(am get-current-user 2>/dev/null)
case "$user" in ''|*[!0-9]*) echo 'Cannot identify current Android user'; exit 0;; esac
[ "$user" -gt 0 ] || { echo 'Headless system user; no permission change'; exit 0; }
marker=$base/phonehub-lan-repair-v1-user$user.done
[ ! -e "$marker" ] || { echo 'One-time LAN repair already completed'; exit 0; }
package=com.google.ambient.streaming
info=$(dumpsys package "$package")
echo "$info" | grep -q 'versionCode=100137340 .*targetSdk=37' || { echo 'App version differs; inspect latest report before applying'; exit 0; }
echo "$info" | grep -q 'flags=\[ SYSTEM .*UPDATED_SYSTEM_APP' || { echo 'Not the reviewed updated system app'; exit 0; }
permission_line() {
 echo "$1" | awk -v user="$user" '
  $0 ~ "^[[:space:]]*User " user ":" {active=1; next}
  active && /^[[:space:]]*User [0-9]+:/ {exit}
  active && /android.permission.ACCESS_LOCAL_NETWORK:/ {print; exit}'
}
line=$(permission_line "$info")
case "$line" in
 *USER_SET*|*USER_FIXED*|*POLICY_FIXED*|*SYSTEM_FIXED*) echo 'Explicit permission decision retained'; exit 0;;
 *granted=true*) echo 'LAN permission already allowed'; exit 0;;
 *granted=false*) ;;
 *) echo 'No matching runtime LAN permission'; exit 0;;
esac
if pm grant --user "$user" "$package" android.permission.ACCESS_LOCAL_NETWORK; then
 after=$(permission_line "$(dumpsys package "$package")")
 case "$after" in
  *granted=true*) echo 'Cross-Device Services LAN permission repaired for current user'; : > "$marker";;
  *) echo 'Grant not confirmed; inspect package permission state';;
 esac
else
 echo 'LAN permission grant failed; no other permissions or settings changed'
fi
