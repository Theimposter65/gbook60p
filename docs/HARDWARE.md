# Hardware status

The reference machine is MOTOROLA DMI product **83NY** (Motobook 60 Pro), Intel Core Ultra 5 225H, 16 GB RAM and Intel GPU **8086:7d51**. Only this profile is enabled. Disk models, serials, partition GUIDs and partition numbers are detected per install. Other storage models are allowed; other laptop/GPU profiles are refused.

| Component | Implementation / evidence | Remaining limits |
| --- | --- | --- |
| Graphics | Matching stock **xe**, native render node, Intel Vulkan/ANGLE; 2880×1800 at 120 Hz observed on the prior installation | No i915 fallback or blanket software renderer. A one-device Minigbm classifier addition is pinned to the exact library hashes. Stock Google HWC colour pipeline, BT.2020 output and persistent HDR are now kept (needs a native retest); `androidboot.gbos_display=legacy` restores the previous SDR-only handling. Widevine L1 is not provided. |
| Wi-Fi | Realtek RTL8922AE stack rebuilt for the exact stock Google kernel ABI; native Wi-Fi previously worked | Different wireless hardware is not validated. |
| Speakers, USB audio, mic | SOF ARL firmware/topology, HDA mixer helper and audio config; all previously worked | Latest BE02T false-charging filter needs a native retest. The exact device quirk never changes electrical USB roles. |
| Camera | Stock USB camera provider plus DMA-BUF heap and legacy-provider exclusion | Reference USB camera previously worked; other cameras are untested. |
| Brightness | Native Intel panel/backlight; EDID-pinned ATNA40HQ01 display configuration (1107 nit peak, 497 nit SDR) staged in RAM | Nits map and HDR headroom enable SDR dimming; needs a native retest. Other panels keep framework defaults. |
| Battery | Energy-to-charge/current aliases and periodic IHealth update; stable alias inodes | Latest refresh needs a native retest. Unknown cycle count/current/temp values are not invented. |
| Power / ADPF | Runtime core detection (hybrid PMU sysfs, then topology/CPUID), foreground on all available CPUs, efficient-core background sets, finite launch/interaction hints including Xe RPe/RP0 GPU minimum-frequency floors | EPP defaults preserve the previous turbo fix. No raised thermal/power limits or fabricated frequency tables. No benchmark improvement promised. |
| Thermal | Native Intel package sensor mapped to Android telemetry | Existing protection/trips and cooling are retained. |
| Charge control | Exact 83NY ACPI conservation interface, no fan/EC/general platform driver | Unsupported policies return errors. |
| NPU | Native Intel module, firmware and device-access staging | Successful Gemini/AI Core inference is **not established**. AI Core patches were removed. |
| Phone Hub / Terminal | Local discovery/Secretkeeper compatibility staging retained | Phone app streaming, proactive assistance and Terminal are not established as working. |
| DRM | Software security compatibility services | Widevine **L3**, not L1. No hardware certification or provisioning bypass is included. |

The kernel and x86-64 Android run natively. Android may translate ARM-only applications using its own translation components; that does not emulate the laptop CPU for the OS.

SELinux is **permissive**. Software KeyMint/Gatekeeper replace unavailable Google hardware services. Android userdata is **not encrypted** by this kit. OTA installation is not supported. These are material properties of this experimental port, not equivalent to a factory Googlebook security configuration.

The new installer has no completed physical-install validation yet. Offline fixtures validate GPT preservation, write boundaries, image construction, hash guards and platform helpers. They do not establish firmware bootability, suspend/battery life, Google login or reliable operation on every Motobook 60 Pro variant.
