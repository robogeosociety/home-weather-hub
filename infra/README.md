# infra/

Snapshot of the live home-stack infrastructure on `tommys-mac-mini`. **These files are checked-in copies** — the running services read from the runtime paths below, not from this directory. If you edit a file here, you also need to copy it to its runtime path (and vice versa, if you change a runtime file).

> A Terraform-managed mirror of this same stack lives in `terraform/`. It's the long-term source of truth; the compose files here are the rollback path. See `terraform/README.md` for the import workflow that adopts the running containers without losing data.

## What runs where

| Service | Image / runtime | Runtime path | Port |
|---|---|---|---|
| InfluxDB 2.7 | `influxdb:2.7-alpine` (OrbStack) | `/Volumes/dev/influxdb/` | `8086` |
| Grafana 11.3 | `grafana/grafana-oss:11.3.0` (OrbStack) | `/Volumes/dev/grafana/` | host `3001` → container `3000` |
| ~~Tempest UDP→InfluxDB bridge~~ **(retired 2026-06-14)** | Python 3 via launchd | `~/.local/share/tempest-bridge/` (plist now `.retired`) | superseded by HA weatherflow→influxdb |
| InfluxDB daily backup | shell script via launchd | `/Volumes/dev/influxdb/backup.sh` | n/a (03:30 daily) |
| InfluxDB → R2 off-host sync | shell script via launchd | `/Volumes/dev/influxdb/backup-r2-sync.sh` | n/a (04:00 daily) |

LaunchAgents are loaded from `~/Library/LaunchAgents/`. Service plists in `launchd/` are committed copies; load with `launchctl bootstrap gui/$UID <path>`.

## Layout

```
infra/
├── influxdb/
│   ├── docker-compose.yml      # InfluxDB 2.7 + named volumes
│   ├── backup.sh               # daily backup via docker exec/cp (03:30)
│   ├── backup-r2-sync.sh       # rclone copy backups/ → Cloudflare R2 (04:00)
│   └── .env.example            # admin creds, service tokens, R2 creds (real .env gitignored)
├── grafana/
│   ├── docker-compose.yml      # Grafana on shared influxdb_default network
│   ├── provisioning/
│   │   ├── datasources/influxdb.yml   # 2 datasources (tempest_archive, home_assistant)
│   │   └── dashboards/
│   │       ├── provider.yml           # file-based dashboard provider config
│   │       └── tempest-basic.json     # 7-panel dashboard, uid tempest-basic
│   ├── playwright/             # validation suite (5 tests)
│   └── .env.example
├── tempest-bridge/
│   ├── bridge.sh               # launchd wrapper: sources .env, exec python
│   ├── tempest_to_influx.py    # UDP listener → InfluxDB line protocol
│   └── .env.example
└── launchd/
    ├── dev.tommydoerr.tempest-bridge.plist
    ├── dev.tommydoerr.influxdb-backup.plist
    └── dev.tommydoerr.influxdb-backup-r2-sync.plist
```

## Setup from scratch

Assuming OrbStack is running and you've got the admin credentials.

```sh
# InfluxDB
cp infra/influxdb/.env.example /Volumes/dev/influxdb/.env  # then fill in
cp -r infra/influxdb/* /Volumes/dev/influxdb/
cd /Volumes/dev/influxdb && docker compose up -d
# After it's healthy, mint tokens — see "Minting service tokens" below.

# Grafana (after InfluxDB tokens exist)
cp infra/grafana/.env.example /Volumes/dev/grafana/.env
cp -r infra/grafana/* /Volumes/dev/grafana/
cd /Volumes/dev/grafana && docker compose up -d

# Tempest bridge
mkdir -p ~/.local/share/tempest-bridge
cp infra/tempest-bridge/* ~/.local/share/tempest-bridge/
cp infra/tempest-bridge/.env.example ~/.local/share/tempest-bridge/.env
chmod 700 ~/.local/share/tempest-bridge/{bridge.sh,tempest_to_influx.py}
chmod 600 ~/.local/share/tempest-bridge/.env

# LaunchAgents (auto-restart bridge + daily backups + R2 off-host sync)
cp infra/launchd/*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.tempest-bridge.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.influxdb-backup.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.influxdb-backup-r2-sync.plist
```

The R2 sync also needs `rclone` on the host (`brew install rclone`) and R2 credentials in `/Volumes/dev/influxdb/.env`. See "Cloudflare R2 off-host backup" below.

## Minting service tokens

After InfluxDB's first boot:

```sh
source /Volumes/dev/influxdb/.env

# Tempest write token (one bucket, write-only)
docker exec influxdb influx auth create --org "$INFLUX_ORG" --token "$INFLUX_ADMIN_TOKEN" \
  --write-bucket $(docker exec influxdb influx bucket list --org "$INFLUX_ORG" \
    --token "$INFLUX_ADMIN_TOKEN" --hide-headers --name tempest_archive | awk '{print $1}') \
  --description "tempest-bridge write"

# Grafana read token (all archive buckets)
docker exec influxdb influx auth create --org "$INFLUX_ORG" --token "$INFLUX_ADMIN_TOKEN" \
  --read-bucket <tempest_archive id> --read-bucket <home_assistant id> --read-bucket <zigbee_archive id> \
  --description "grafana read"
```

## Cloudflare R2 off-host backup

`backup-r2-sync.sh` runs daily at 04:00 (30 minutes after `backup.sh`) and uses `rclone copy` to push everything in `/Volumes/dev/influxdb/backups/` to the `influxdb-backups` R2 bucket. `copy` (not `sync`) means R2 never deletes — once a snapshot is up there it stays, even after the local 30-day prune removes it from disk. Backups are ~16KB/day; thousands of years' worth fit in R2's free tier.

One-time setup on a fresh host:

```sh
# 1. rclone — single static binary, ~50 MB.
brew install rclone

# 2. Mint an R2 API token in the Cloudflare dashboard:
#    https://dash.cloudflare.com/?to=/:account/r2/api-tokens
#    Permission: Object Read & Write
#    Scope: bucket = influxdb-backups
#    Note the Access Key ID and Secret Access Key — the secret is shown once.

# 3. Append the three R2_* keys (see .env.example) to /Volumes/dev/influxdb/.env.

# 4. Smoke-test the sync manually before scheduling it.
/Volumes/dev/influxdb/backup-r2-sync.sh

# 5. Schedule.
cp infra/launchd/dev.tommydoerr.influxdb-backup-r2-sync.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.influxdb-backup-r2-sync.plist
```

Logs land at `/Volumes/dev/influxdb/backup-r2-sync.log`. To inspect what's in R2:

```sh
source /Volumes/dev/influxdb/.env
export RCLONE_CONFIG_R2_TYPE=s3 RCLONE_CONFIG_R2_PROVIDER=Cloudflare \
  RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
  RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
  RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
rclone lsf r2:influxdb-backups --dirs-only       # one entry per snapshot
rclone size r2:influxdb-backups                   # total stored bytes
```

## Validating

```sh
cd infra/grafana/playwright
PATH="/opt/homebrew/opt/node@24/bin:$PATH" npm install
PATH="/opt/homebrew/opt/node@24/bin:$PATH" npx playwright install chromium
PATH="/opt/homebrew/opt/node@24/bin:$PATH" npx playwright test
```

## Caveats

- **The `.env` files at runtime paths are not in this repo.** Three of them exist on the host (`/Volumes/dev/influxdb/.env`, `/Volumes/dev/grafana/.env`, `~/.local/share/tempest-bridge/.env`) — secrets, chmod 600, gitignored. Back them up out-of-band.
- **launchd cannot exec from `/Volumes/*`.** macOS's TCC sandbox blocks LaunchAgent program paths under `/Volumes`. That's why `bridge.sh` lives in `~/.local/share/` even though everything else lives on the dev volume.
- **OrbStack port forwards can wedge on restart.** Grafana publishes host port `3001` → container `3000` because port `3000` got stuck in a "bind: address already in use" loop after an earlier restart. Switch back when convenient.
- **Drift risk.** Changes made in-place at runtime paths won't update this repo. Best practice: edit here, copy to runtime, restart the affected service.

## Migration target — Tempest done (2026-06-14)

The whole stack is a stopgap until Home Assistant on the Raspberry Pi takes over outdoor/indoor sensor capture.

**Tempest handoff complete:** HA's `weatherflow` integration (device `st_00204728`) now exports to InfluxDB's `home_assistant` bucket via HA's `influxdb` integration (`measurement_attr: entity_id`, so each metric is `sensor.st_00204728_<x>`/`value`, in HA display units). The `tempest-bridge` launchd job was **retired** (booted out + disabled; plist kept as `.retired`). The Grafana `Tempest — Basic` dashboard, the `freshness-tempest` alert, and the ops freshness/status panels were repointed to `home_assistant`. The `tempest_archive` bucket is now a **frozen historical archive** (no backfill; R2-backed) — only the two per-strike lightning panels still read it.

**Indoor/Zigbee — done (2026-06-20):** ZHA (Sonoff dongle) climate sensors are paired in HA and export to the **`home_assistant`** bucket via HA's `influxdb` integration (allowlist globs `sensor.*_temp_temperature` / `_humidity` / `_battery`; a sensor named `<room> temp` auto-exports). The **Indoor Climate** Grafana dashboard reads them. `zigbee_archive` stays an **empty reserved bucket** — HA's single `influxdb` integration writes every sensor (Zigbee included) to `home_assistant`, so routing Zigbee to its own bucket would need a second integration instance (not worth it).
