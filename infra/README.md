# infra/

Snapshot of the live home-stack infrastructure on `tommys-mac-mini`. **These files are checked-in copies** — the running services read from the runtime paths below, not from this directory. If you edit a file here, you also need to copy it to its runtime path (and vice versa, if you change a runtime file).

> A Terraform-managed mirror of this same stack lives in `terraform/`. It's the long-term source of truth; the compose files here are the rollback path. See `terraform/README.md` for the import workflow that adopts the running containers without losing data.

## What runs where

| Service | Image / runtime | Runtime path | Port |
|---|---|---|---|
| InfluxDB 2.7 | `influxdb:2.7-alpine` (OrbStack) | `/Volumes/dev/influxdb/` | `8086` |
| Grafana 11.3 | `grafana/grafana-oss:11.3.0` (OrbStack) | `/Volumes/dev/grafana/` | host `3001` → container `3000` |
| Tempest UDP→InfluxDB bridge | Python 3 via launchd | `~/.local/share/tempest-bridge/` | UDP `50222` listener |
| InfluxDB daily backup | shell script via launchd | `/Volumes/dev/influxdb/backup.sh` | n/a (03:30 daily) |

LaunchAgents are loaded from `~/Library/LaunchAgents/`. Service plists in `launchd/` are committed copies; load with `launchctl bootstrap gui/$UID <path>`.

## Layout

```
infra/
├── influxdb/
│   ├── docker-compose.yml      # InfluxDB 2.7 + named volumes
│   ├── backup.sh               # daily backup via docker exec/cp
│   └── .env.example            # admin creds + service tokens (real .env gitignored)
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
    └── dev.tommydoerr.influxdb-backup.plist
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

# LaunchAgents (auto-restart bridge + daily backups)
cp infra/launchd/*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.tempest-bridge.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/dev.tommydoerr.influxdb-backup.plist
```

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

## Migration target

The whole stack is a stopgap until Home Assistant on the Raspberry Pi takes over outdoor/indoor sensor capture. At that point: tear down the Tempest bridge, point HA's InfluxDB integration at the existing InfluxDB on this Mac, and let HA push to the `home_assistant` and `zigbee_archive` buckets. The Grafana datasources are already pre-wired for that handoff.
