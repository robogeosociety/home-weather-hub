# Flash Raspberry Pi 4 with Home Assistant OS

Task list for bootstrapping a Raspberry Pi 4 (4GB) with Home Assistant OS on a
Samsung MUF-128DA USB-C flash drive, flashed from `tommys-mac-mini` (macOS,
Apple Silicon). Tracks GitHub issue #9.

## Hardware

- **Target media:** Samsung Type-C USB Flash Drive 128GB (MUF-128DA/AM)
- **Target host:** Raspberry Pi 4 Model B, 4GB RAM (CanaKit Starter PRO Kit)
- **Connection:** USB-C drive into a USB-A port via adapter, into a blue USB 3.0 port on the Pi
- **Network:** Pi on wired Ethernet for first boot
- **Workstation:** `tommys-mac-mini` (macOS, Apple Silicon)
- **Image:** `haos_rpi4-64-17.3.img.xz` (HAOS 17.3, latest stable as of 2026-05-28)

## Tasks

### 1. Download HAOS image

- [x] Fetch latest stable HAOS rpi4-64 image (`haos_rpi4-64-17.3.img.xz`) into `~/Downloads/`
      — 354 MB, downloaded 2026-05-28.
- [x] Record integrity digest. HAOS 17.3 ships **no** `.sha256` asset on the GitHub
      release, so the local sha256 is recorded here for re-verification before flashing:
      `371af52e378d94bbe0391ad7fb49848a94443336c168c5848cbff66923afbb25`

### 2. Pre-flight checks

- [ ] Confirm `rpi-imager` is installed: `brew list raspberry-pi-imager || brew install --cask raspberry-pi-imager` (ask before installing)
- [ ] Confirm workstation has network connectivity
- [ ] Ask Tommy to plug the Samsung USB-C drive into the Mac (via USB-C-to-A adapter or a USB-C port directly)
- [ ] Wait for confirmation that the drive is connected

### 3. Identify the target drive

- [ ] Run `diskutil list external` and parse output
- [ ] Identify the Samsung drive by size (~128GB) and vendor string
- [ ] **Confirm with Tommy** before proceeding: print the device identifier (e.g. `/dev/disk4`) plus reported name/size; require explicit `yes` before any write
- [ ] If multiple external drives are present, list them and ask which one
- [ ] **NEVER write without explicit confirmation of the target device** — flashing the wrong drive is destructive

### 4. Flash the drive

- [ ] Unmount first: `diskutil unmountDisk <device>` (not `eject`)
- [ ] Decompress + write. Prefer `rpi-imager` CLI; fall back to `xz -d` then
      `sudo dd if=<image> of=/dev/rdiskN bs=4m status=progress` using the **raw**
      device path (`/dev/rdiskN`) for ~5× speed on macOS
- [ ] Print every privileged (`sudo`) command and what it does before running it
- [ ] On completion: `sync`, then `diskutil eject <device>`

### 5. Install and power on

- [ ] Print clear instructions:
  - Unplug the USB drive from the Mac
  - Plug it into the USB-C-to-A adapter, then into a **blue** USB 3.0 port on the Pi 4
  - Confirm the Pi is on Ethernet
  - Plug in the Pi's power
  - First boot takes 5–15 min (HAOS pulls an OTA update) — do not interrupt power
- [ ] Wait for Tommy to confirm the Pi is powered on

### 6. Wait for HAOS to come online

- [ ] Poll `http://homeassistant.local:8123` every 30s, 5s timeout per request, up to 20 min:
      `curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://homeassistant.local:8123`
- [ ] Show elapsed-time progress
- [ ] Success = HTTP 200 or redirect to `/onboarding/`

### 7. Troubleshooting (if unreachable after 20 min)

- [ ] `ping -c 4 homeassistant.local` — mDNS resolution
- [ ] `arp -a | grep -i 'b8:27:eb\|dc:a6:32\|e4:5f:01\|d8:3a:dd'` — Pi Foundation MAC prefixes
- [ ] Check Pi status LED (solid red = power; green flashing = disk activity)
- [ ] Check router DHCP client list for `homeassistant` / `HASSOS`

### 8. Hand off URL

- [ ] Print detected URL `http://homeassistant.local:8123`
- [ ] Resolve IP (`dig +short homeassistant.local @224.0.0.251 -p 5353` or `arp -a`) and print `http://<IP>:8123` as backup
- [ ] Tommy completes onboarding manually (account, location, timezone)
- [ ] Remind Tommy to set a DHCP reservation for the Pi's MAC after onboarding

## Acceptance criteria

- [ ] HAOS image downloaded and integrity recorded/verified
- [ ] Samsung drive flashed without writing to any other disk
- [ ] Pi physically connected and powered on (confirmed by Tommy)
- [ ] `http://homeassistant.local:8123` returns HTTP 200 within 20 min
- [ ] Both `.local` and IP-based URLs printed
- [ ] No automated interaction with the onboarding wizard

## Safety notes

- **Destructive:** flashing wipes the target drive. Require explicit confirmation of the device identifier before any `dd` / `rpi-imager` write.
- Print every `sudo` command and its effect before running.
- Do not modify `/etc/hosts` or other system config.
- Do not assume tools are installed — check, and ask before `brew install`.

## Out of scope

- Onboarding wizard completion
- HACS installation
- hass-kumo integration setup
- Any HAOS config beyond reaching the login screen
