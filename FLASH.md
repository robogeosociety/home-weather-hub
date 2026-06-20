# Migrate running HAOS from SD card to USB storage drive

Task list for migrating the **live** Home Assistant OS instance off its current
Raspberry Pi SD card and onto the newly-arrived USB storage drive, driven from
`tommys-mac-mini` (macOS, Apple Silicon). The strategy is backup-flash-restore:
take a full HA backup off-device, flash a **clean** HAOS image to the new drive,
swap hardware, and restore the backup during onboarding. The SD card stays intact
as the rollback path until the new drive is verified.

> Sibling doc: `flash_pi.md` covers a from-scratch HAOS bootstrap. This doc reuses
> its flashing mechanics (§4 there) but adds the backup/restore wrapper that makes
> it a *migration* rather than a clean install.

## Hardware

- **Current boot media:** microSD card running HAOS (to be retired, kept as rollback)
- **Target media:** **Raspberry Pi-branded 128 GB USB storage drive** — detected
  2026-06-07 at `/dev/disk7`, USB (negotiated 480 Mb/s / USB 2.0), factory
  MBR/`Windows_NTFS` format (volume `Untitled`), VID:PID `2e8a:0030`,
  serial `0325900001DA`. Capacity 128.4 GB (128,379,256,832 bytes).
  > Device node (`disk7`) can change across re-plugs — match on the size/format/serial
  > signature above, never on the number alone. **Re-run §5's `diskutil list external`
  > and re-confirm before writing.**
- **DO NOT TOUCH:** `/dev/disk4` = `WD_BLACK SN850X 2000GB` (2 TB NVMe) is the
  `/Volumes/dev` workspace disk. It is never a flash target. Flashing it destroys this
  entire workspace.
- **Target host:** Raspberry Pi 4 Model B, 4GB RAM
- **Connection:** new drive into a **blue** USB 3.0 port on the Pi for first boot
  (the drive itself negotiates USB 2.0 speed, so first-boot OTA will be on the slower side)
- **Workstation:** `tommys-mac-mini` (macOS, Apple Silicon)
- **Network:** Pi on wired Ethernet; `homeassistant.local` → **192.168.4.101**,
  web UI at `http://homeassistant.local:8123` (confirmed reachable)
- **Image:** reuse `~/Downloads/haos_rpi4-64-17.3.img.xz`
  (sha256 `371af52e378d94bbe0391ad7fb49848a94443336c168c5848cbff66923afbb25`),
  or fetch a newer stable if one has shipped — match the **running** instance's
  major version or newer, never older (restore won't downgrade cleanly).

## SSH / access (probed 2026-06-07)

| Endpoint | Port | State | Use |
|---|---|---|---|
| Web UI | `8123` | **open** | Backups UI, onboarding, restore |
| SSH add-on (Terminal & SSH / Web Terminal) | `22` | **open** | `ssh root@homeassistant.local` → `ha` CLI + `/backup` access |
| HAOS host debug SSH | `22222` | **closed** | Not enabled — don't rely on it |

So the CLI/scp paths below go through the **SSH add-on on port 22** (login user is
typically `root` with the key/password configured in the add-on options), **not** the
host debug port `22222`. If port 22 auth fails, the add-on may use a non-`root` username
or key-only auth — check the add-on's configuration. Everything here can also be done
entirely from the **web UI** if SSH is inconvenient.

## Guiding principle — order of operations is the safety net

**Nothing destructive happens until a verified backup is sitting on the Mac (and
off-host in R2).** The SD card is never wiped during this migration; it is the
rollback. If anything goes wrong, re-insert the SD card and power on — you are
back to the known-good state in two minutes.

## Tasks

### 1. Create a full backup on the running Pi

- [ ] Confirm HA is reachable: `curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://homeassistant.local:8123`
- [ ] Trigger a **full** backup (config + add-ons + add-on data + media). Pick one:
  - **UI:** Settings → System → Backups → **Create backup** → *Full backup*.
  - **CLI** (via the SSH add-on on port 22): `ssh root@homeassistant.local`, then
    `ha backups new --name "pre-ssd-migration"` and `ha backups list`.
- [ ] Note the resulting backup **slug** and filename (`<slug>.tar` under `/backup`).
- [ ] Record the backup's reported size and the entity/add-on count shown in the UI
      so the post-restore verification (§8) has something to check against.

### 2. Pull the backup down to the Mac ("sync to this machine")

- [ ] Choose a transport (recommended first):
  - **UI download (simplest):** in the Backups list, ⋮ → **Download backup** → lands
    in `~/Downloads/`. Then move it: `mv ~/Downloads/<slug>.tar /Volumes/dev/home-weather-hub/data/haos-backups/`.
  - **scp over the SSH add-on** (port 22 — host debug `22222` is disabled):
    `scp root@homeassistant.local:/backup/<slug>.tar /Volumes/dev/home-weather-hub/data/haos-backups/`
    (the add-on maps the `backup` share, so `/backup/<slug>.tar` is reachable)
  - **Samba add-on share:** mount `\\homeassistant\backup`, copy `<slug>.tar` off.
- [ ] Create the local landing dir if missing: `mkdir -p /Volumes/dev/home-weather-hub/data/haos-backups`
      (this lives under the gitignored `data/` tree — backups are never committed).
- [ ] **Verify the copy is intact**, not truncated:
  - `ls -lh /Volumes/dev/home-weather-hub/data/haos-backups/<slug>.tar` (size matches §1)
  - `tar tf <slug>.tar >/dev/null && echo "archive OK"` (lists without error)
  - Record `shasum -a 256 <slug>.tar` for later re-verification.

### 3. Push a copy off-host (the "remotely" leg)

- [ ] Mirror the existing InfluxDB→R2 pattern (`infra/influxdb/backup-r2-sync.sh`):
      push the backup to a Cloudflare R2 bucket so a copy survives loss of both the
      Pi and the Mac.
- [ ] If no `haos-backups` bucket exists yet, create one and reuse the R2 creds
      already in `/Volumes/dev/influxdb/.env` (Object Read & Write):
  ```sh
  source /Volumes/dev/influxdb/.env
  export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
    RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
  rclone copy /Volumes/dev/home-weather-hub/data/haos-backups/<slug>.tar r2:haos-backups
  rclone lsf r2:haos-backups        # confirm it's up there
  ```
- [ ] **Gate:** do not advance past this step until the backup is confirmed in
      **both** places (Mac + R2). This is the point of no concern — from here, even a
      botched flash can't lose data.

### 4. Pre-flight the flash

- [ ] Confirm `rpi-imager` present: `brew list raspberry-pi-imager || brew install --cask raspberry-pi-imager` (ask before installing).
- [ ] Re-verify the image digest before writing:
      `shasum -a 256 ~/Downloads/haos_rpi4-64-17.3.img.xz` matches the recorded sha256.
- [ ] Ask Tommy to confirm the new storage drive is plugged into the Mac; wait for confirmation.

### 5. Identify the target drive — **destructive, confirm explicitly**

- [ ] `diskutil list external` and parse output.
- [ ] **Expected target signature** (re-verify, device node may have changed):
      128.4 GB · USB · MBR/`Windows_NTFS` (volume `Untitled`) · Manufacturer
      `Raspberry Pi` · serial `0325900001DA`. As of 2026-06-07 this was `/dev/disk7`.
      Confirm with: `diskutil info /dev/diskN | grep -Ei 'Media Name|Disk Size|Protocol'`
      and `system_profiler SPUSBDataType | grep -A6 'Flash Drive'` (serial should match).
- [ ] **Hard exclusion:** `/dev/disk4` (`WD_BLACK SN850X 2000GB`, 2 TB, PCI-Express) is
      `/Volumes/dev` — **never** a target. If the candidate is 2 TB or PCI-Express, STOP.
- [ ] **Print the resolved device identifier plus name/size and require an explicit
      `yes` before any write.**
- [ ] If multiple external drives are present, list them and ask which one.
- [ ] **NEVER write without explicit confirmation of the target device.** The Mac's
      internal disk, the 2 TB workspace disk, and any backup drives must never be candidates.

### 6. Flash the new drive

- [ ] Unmount first: `diskutil unmountDisk <device>` (not `eject`).
- [ ] Write the image. Prefer `rpi-imager` CLI; fall back to `xz -dc <image> | sudo dd of=/dev/rdiskN bs=4m status=progress`
      using the **raw** device (`/dev/rdiskN`) for ~5× speed on macOS.
- [ ] Print every `sudo` command and its effect before running it.
- [ ] On completion: `sync`, then `diskutil eject <device>`.

### 7. Swap — power-down order matters

Do these **in order**. Do not skip the graceful shutdown; pulling power on a live
HAOS risks a corrupt filesystem on the SD card you may still need.

1. [ ] **Graceful software shutdown of HA** — UI: Settings → System → top-right
       power icon → **Shut down system** (or `ha host shutdown` over SSH).
2. [ ] **Wait for the Pi's green activity LED to go dark** (disk flushed). Give it ~30s.
3. [ ] **Unplug the Pi's power** (no soft power button — pulling power is the off switch,
       but only *after* the shutdown above has quiesced the disk).
4. [ ] **Remove the microSD card.** Set it aside, label it "HAOS rollback — DO NOT WIPE".
       Removing it is required: a Pi 4 with an SD card present will boot the SD, not USB.
5. [ ] **Connect the freshly-flashed USB drive** to a **blue USB 3.0** port on the Pi.
6. [ ] Confirm Ethernet is connected.
7. [ ] **Plug the Pi's power back in.** First boot pulls an OTA update and resizes the
       filesystem — 5–15 min, **do not interrupt power**.

> USB-boot caveat: Pi 4 USB mass-storage boot needs a reasonably current bootloader
> EEPROM (standard since 2020; if HAOS already runs on this Pi it's almost certainly
> fine). If it doesn't boot with the SD removed, re-insert the SD to recover, then
> update the EEPROM (`rpi-eeprom`) before retrying — and reach for `flash_pi.md`'s
> troubleshooting (§7 there).

### 8. Bring it online and restore

- [ ] Poll for HAOS: `curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://homeassistant.local:8123`
      every 30s, up to 20 min. Success = 200 or redirect to `/onboarding/`.
- [ ] At the onboarding screen, choose **"Restore from backup"** → upload the
      `<slug>.tar` from `/Volumes/dev/home-weather-hub/data/haos-backups/` (or restore
      from the Pi's `/backup` share if you copied it back). Select **full** restore.
- [ ] Wait for the restore + reboot to complete.

### 9. Verify the migration

- [ ] HA reachable and you can log in with the **existing** credentials (not a fresh account — restore brings them).
- [ ] **Confirm it booted from USB, not SD:** the SD is physically out, so simply
      being online proves USB boot. Optionally check Settings → System → Storage (or
      `ha host info`) shows the larger drive's capacity.
- [ ] Entity count / dashboards / add-ons match the pre-migration figures from §1.
- [ ] Add-ons are **running** (Settings → Add-ons) — not just installed.
- [ ] Integrations reconnected: MQTT/Zigbee sensors reporting, recorder writing history.
- [ ] If the InfluxDB integration is in use (see `infra/README.md` migration target),
      confirm it's still pushing to the Mac's InfluxDB buckets.
- [ ] Set a DHCP reservation for the Pi's MAC if not already done.

## Acceptance criteria

- [ ] Full backup created, pulled to the Mac, **and** mirrored to R2 — verified intact in both.
- [ ] New drive flashed without writing to any other disk.
- [ ] Pi gracefully shut down, SD removed and preserved, booted from the USB drive.
- [ ] `http://homeassistant.local:8123` returns 200 within 20 min of power-on.
- [ ] Backup restored; entities, add-ons, and integrations match the pre-migration state.
- [ ] SD card retained untouched as rollback.

## Safety notes

- **The SD card is the rollback — never wipe it during this migration.** Retire it
  only after the new drive has run clean for a few days.
- **Verified backup before any flash.** §3's gate is non-negotiable.
- **Destructive flash:** require explicit confirmation of the target device identifier
  before any `dd` / `rpi-imager` write. Print every `sudo` command first.
- **Graceful shutdown before pulling power** — protects the SD's filesystem.
- Use the official Pi PSU; a USB SSD can draw more than a flash stick and brownouts
  cause boot loops.

## Rollback

If the new drive fails to boot or the restore is bad:

1. Pull Pi power, remove the USB drive.
2. Re-insert the original SD card.
3. Power on — back to the pre-migration instance within a couple of minutes.
4. Investigate (EEPROM, drive health, image integrity) before retrying §6.

## Out of scope

- Onboarding a *new* HA instance from scratch (that's `flash_pi.md`).
- HACS / integration setup beyond what the restore brings back.
- Repurposing or wiping the old SD card.
