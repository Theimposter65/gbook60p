#!/bin/busybox sh
# Sourced only after original vendor and OEM compatibility mounts exist.
# All overlays below live in retained RAM; original images/data stay intact.
P=/gbos/gbrunch/peripherals
mkdir -p "$P" || return 1
cp /gbrunch-audio-controls /gbos/gbrunch/audio-controls || return 1
chmod 0755 /gbos/gbrunch/audio-controls
. /gbrunch-peripheral-hashes.cfg
echo "$GB_AUDIO_DEFAULT_HASH  /new/vendor/etc/data/hal_configs/audio_default.xml" | sha256sum -c - || return 1
# The HAL's fallback StartupOptions reads these files directly in /vendor/etc.
# Retain every original config and symlink in a RAM copy before adding files.
cp -a /new/vendor/etc "$P/vendor-etc" || return 1
mount --bind "$P/vendor-etc" /new/vendor/etc || return 1
card=
for attempt in 1 2 3 4 5; do
 for candidate in /sys/class/sound/card[0-9]*; do
  [ -f "$candidate/id" ] || continue
  device=$(readlink -f "$candidate/device")
  case "$device:$(cat "$candidate/id")" in */0000:00:1f.3:*|*/skl_hda_dsp_generic:sofhdadsp|*/0000:00:1f.3/*:sofhdadsp) card=$candidate; break;; esac
 done
 [ -n "$card" ] && break
 sleep 1
done
{
 echo '== ALSA cards'; cat /proc/asound/cards
 echo '== PCM devices'; cat /proc/asound/pcm
 echo '== codec IDs'; grep -h -E 'Codec:|Vendor Id:|Subsystem Id:' /proc/asound/card*/codec* 2>/dev/null
} > "$L/audio-early.txt" 2>&1
if [ -n "$card" ]; then
 cid=$(cat "$card/id")
 case "$cid" in ''|*[!A-Za-z0-9_-]*) echo 'Unsupported card ID; original audio config retained' >> "$L/audio-early.txt";;
 *)
  cname=$(sed -n "s/^ *${card##*card} \[.* - //p" /proc/asound/cards | head -n 1)
  [ -n "$cname" ] || cname='HDA Intel PCH'
  case "$cname" in *[\&\<\>\#\/]* ) cname='HDA Intel PCH';; esac
  cnum=${card##*card}
  case "$cnum" in [0-9]) pcm_prefix=0$cnum;; *) pcm_prefix=$cnum;; esac
  dmic=$(awk -v prefix="$pcm_prefix-" 'index($1,prefix)==1 && /DMIC/ && /capture/ {split($1,a,"-"); print a[2]+0; exit}' /proc/asound/pcm)
  if [ -z "$dmic" ]; then dmic=0; echo 'No digital microphone PCM registered; internal mic remains unverified' >> "$L/audio-early.txt"; fi
  hpjack='HDA Intel PCH Headphone'; micjack='HDA Intel PCH Mic'
  hdmi1jack='HDA Intel PCH HDMI/DP,pcm=3'; hdmi2jack='HDA Intel PCH HDMI/DP,pcm=7'; hdmi3jack='HDA Intel PCH HDMI/DP,pcm=8'
  hdmi1=3; hdmi2=7; hdmi3=8
  if [ "$cid" = sofhdadsp ]; then
   hpjack='sof-hda-dsp Headphone'; micjack='sof-hda-dsp Mic'
   hdmi1=3; hdmi2=4; hdmi3=5
   hdmi1jack='sof-hda-dsp HDMI/DP,pcm=3'; hdmi2jack='sof-hda-dsp HDMI/DP,pcm=4'; hdmi3jack='sof-hda-dsp HDMI/DP,pcm=5'
  fi
  for input in /sys/class/input/input*/name; do
   [ -f "$input" ] || continue
   iname=$(cat "$input")
   case "$iname" in *[\&\<\>\#\/]* ) continue;; esac
   case "$iname" in
    'sof-hda-dsp Headphone'*|'HDA Intel PCH Headphone'*) hpjack=$iname;;
    'sof-hda-dsp Mic'*|'HDA Intel PCH Mic'*) micjack=$iname;;
    'sof-hda-dsp HDMI/DP,pcm=3'*|'HDA Intel PCH HDMI/DP,pcm=3'*) hdmi1jack=$iname;;
    'sof-hda-dsp HDMI/DP,pcm=4'*|'HDA Intel PCH HDMI/DP,pcm=7'*) hdmi2jack=$iname;;
    'sof-hda-dsp HDMI/DP,pcm=5'*|'HDA Intel PCH HDMI/DP,pcm=8'*) hdmi3jack=$iname;;
   esac
  done
  mkdir -p "$P/vendor-etc/audio/gbos-sn6140" || return 1
  for name in audio_config.xml mixer_paths.xml volume_curves.xml; do
   sed -e "s/PCH/$cid/g" -e "s/@GB_DMIC_PCM@/$dmic/g" -e "s#@GB_HEADPHONE_JACK@#$hpjack#g" -e "s#@GB_MIC_JACK@#$micjack#g" -e "s/@GB_HDMI1@/$hdmi1/g" -e "s/@GB_HDMI2@/$hdmi2/g" -e "s/@GB_HDMI3@/$hdmi3/g" -e "s#@GB_HDMI_JACK1@#$hdmi1jack#g" -e "s#@GB_HDMI_JACK2@#$hdmi2jack#g" -e "s#@GB_HDMI_JACK3@#$hdmi3jack#g" /gbrunch-audio/$name > "$P/vendor-etc/audio/gbos-sn6140/$name" || return 1
   cp "$P/vendor-etc/audio/gbos-sn6140/$name" "$P/vendor-etc/$name" || return 1
  done
  # Read only the validated codec's actual ALSA dB scales. Initialize the
  # speaker's dedicated DAC gain and SOF playback gains in its UCM route;
  # preserve microphone/USB settings and do not guess unsupported controls.
  if /gbrunch-audio-controls --speaker-xml "$cnum" > "$P/speaker-gains.xml" 2>> "$L/audio-early.txt"; then
   sed '/<path name="Speaker">/r '"$P/speaker-gains.xml" "$P/vendor-etc/mixer_paths.xml" > "$P/mixer_paths.xml" || return 1
   cp "$P/mixer_paths.xml" "$P/vendor-etc/mixer_paths.xml" || return 1
   cp "$P/mixer_paths.xml" "$P/vendor-etc/audio/gbos-sn6140/mixer_paths.xml" || return 1
  fi
  sed "s/<soundcard>PCH/<soundcard>$cid/" /gbrunch-audio/audio_default.xml > "$P/audio_default.xml" || return 1
  mount --bind "$P/audio_default.xml" /new/vendor/etc/data/hal_configs/audio_default.xml || return 1
  echo "Selected native audio card $cid ($cname), internal mic PCM=$dmic; configs also installed in /vendor/etc" >> "$L/audio-early.txt"
 ;;
 esac
else
 echo 'No PCI audio card initialized; original audio config retained' >> "$L/audio-early.txt"
fi
# Unsupported Google legacy camera HAL exits 237 repeatedly. Keep usb/0 and
# its original configuration; disable only the hash-pinned legacy/0 provider.
echo "$GB_CAMERA_RC_HASH  /new/vendor/etc/init/android.hardware.camera.provider@2.7-service-legacy-wrapper.rc" | sha256sum -c - || return 1
echo "$GB_CAMERA_VINTF_HASH  /new/vendor/etc/vintf/manifest/android.hardware.camera.provider@2.7-service-legacy-wrapper.xml" | sha256sum -c - || return 1
cp /gbrunch-camera-legacy.rc "$P/vendor-etc/init/android.hardware.camera.provider@2.7-service-legacy-wrapper.rc" || return 1
cp /gbrunch-camera-legacy.xml "$P/vendor-etc/vintf/manifest/android.hardware.camera.provider@2.7-service-legacy-wrapper.xml" || return 1
ls -l /dev/dma_heap /sys/class/dma_heap > "$L/camera-early.txt" 2>&1
# Replace Google's Cros-EC port keys with the actual ACPI Type-C and supply
# paths. Keep each port's controller-side host links and capabilities.
port0=$(readlink -f /sys/class/typec/port0)
port1=$(readlink -f /sys/class/typec/port1)
psy0=$(readlink -f /sys/class/power_supply/ucsi-source-psy-USBC000:001)
psy1=$(readlink -f /sys/class/power_supply/ucsi-source-psy-USBC000:002)
if [ -d "$port0" ] && [ -d "$port1" ] && [ -d "$psy0" ] && [ -d "$psy1" ]; then
 case "$port0$port1$psy0$psy1" in *[!A-Za-z0-9/:_.-]*) echo 'Unexpected USB sysfs path; original port map retained' >> "$L/audio-early.txt";;
 *)
  echo "$GB_USB_PORTS_HASH  /new/vendor/etc/usb/usb_ports_static_info.json" | sha256sum -c - || return 1
  sed -e "s#@GBOS_PORT0@#$port0#g" -e "s#@GBOS_PORT1@#$port1#g" -e "s#@GBOS_PSY0@#$psy0#g" -e "s#@GBOS_PSY1@#$psy1#g" /gbrunch-usb-ports-template.json > "$P/usb_ports_static_info.json" || return 1
  mount --bind "$P/usb_ports_static_info.json" /new/vendor/etc/usb/usb_ports_static_info.json || return 1
 ;;
 esac
fi
# Keep normal vendor linker namespace rules; clone only the existing small
# sound-effects directory, then add the private HAL read-only role shim.
if [ -d /new/vendor/lib64/soundfx ]; then
 cp -a /new/vendor/lib64/soundfx "$P/soundfx" || return 1
 cp /gbrunch-usb-role.so "$P/soundfx/libgbos_usb_role.so" || return 1
 chmod 0644 "$P/soundfx/libgbos_usb_role.so"
 echo "$GB_HEALTH_RC_HASH  /new/vendor/etc/init/android.hardware.health-service.android-desktop.rc" | sha256sum -c - || return 1
 echo "$GB_USB_RC_HASH  /new/vendor/etc/init/android.hardware.usb-service.desktop.rc" | sha256sum -c - || return 1
 mount --bind "$P/soundfx" /new/vendor/lib64/soundfx || return 1
 for name in android.hardware.health-service.android-desktop.rc android.hardware.usb-service.desktop.rc; do
  cp /gbrunch-peripheral-rc/$name "$P/$name" || return 1
  mount --bind "$P/$name" /new/vendor/etc/init/$name || return 1
 done
else
 echo 'No soundfx library directory; original health/USB services retained' >> "$L/audio-early.txt"
fi
