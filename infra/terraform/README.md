# infra/terraform/

Terraform-managed mirror of the InfluxDB + Grafana stack that lives under `infra/influxdb/` and `infra/grafana/`. **Both setups describe the same containers** — pick one and stick with it. The compose files are kept for reference and as the rollback path; this directory is the new source of truth.

## What's managed

| Provider / mechanism | Resources |
|---|---|
| `kreuzwerker/docker` | `influxdb` + `grafana` containers, their volumes, the `influxdb_default` network |
| `scripts/influx-bootstrap.py` (via `terraform_data` + `local-exec`) | Buckets (`tempest_archive`, `zigbee_archive`); write tokens for tempest-bridge and home-assistant; read token for Grafana |
| `grafana/grafana` | Two InfluxDB datasources (`tempest_archive`, `home_assistant`); the `tempest-basic` dashboard |

The Tempest launchd bridge and the daily backup cron are **not** managed here — they're host-level launchd agents, not docker resources. See `../launchd/` and `../tempest-bridge/`.

### Why a bootstrap script instead of an InfluxDB Terraform provider

The only InfluxDB v2 community provider (`lancey-energy-storage/influxdb-v2`) doesn't ship `darwin_arm64` binaries — that's a hard stop on the Mac Mini M1 host. Rather than force `arch -x86_64 terraform` everywhere, this module shells out to `docker exec influxdb influx ...`, which is the same CLI flow the operator already uses by hand. Idempotency is handled by the script (get-or-create buckets; reuse tokens when the previous secret still authenticates).

## Quick start (fresh install)

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # then fill in admin creds + token
terraform init
terraform apply
```

On a clean machine this does the full bootstrap: pulls images, creates containers, waits for them to come up, then provisions buckets, tokens, datasources, and the dashboard. The Influx admin token you set in tfvars becomes the container's first-boot admin token via `DOCKER_INFLUXDB_INIT_ADMIN_TOKEN`.

After apply, harvest the generated service tokens:

```sh
terraform output -raw influx_tempest_token   # for ~/.local/share/tempest-bridge/.env
terraform output -raw influx_ha_token        # for the future HA integration
terraform output -raw influx_grafana_token   # already wired into the datasources
```

Then update `~/.local/share/tempest-bridge/.env` with the new tempest token and `launchctl kickstart -k gui/$UID/dev.tommydoerr.tempest-bridge`.

## Adopting the running stack (import)

The InfluxDB volume already holds real data; the existing tokens are wired into the Grafana datasources and the tempest-bridge `.env`. Don't `terraform apply` blind — you'll either fail (name collisions) or replace containers and lose state. Import first.

```sh
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Fill terraform.tfvars with the EXACT values from /Volumes/dev/influxdb/.env
# and /Volumes/dev/grafana/.env. The admin token must match the value baked
# into the running container; if it doesn't, the bootstrap script will fail
# at the first `influx` CLI call.

terraform init

# Containers + volumes + network
terraform import docker_network.influxdb_default     influxdb_default
terraform import docker_volume.influxdb_data         influxdb_influxdb_data
terraform import docker_volume.influxdb_config       influxdb_influxdb_config
terraform import docker_volume.grafana_data          grafana_grafana_data
terraform import docker_container.influxdb          "$(docker inspect -f '{{.ID}}' influxdb)"
terraform import docker_container.grafana           "$(docker inspect -f '{{.ID}}' grafana)"

# Grafana datasources — uid is stable
terraform import grafana_data_source.tempest_archive   uid:tempest_archive
terraform import grafana_data_source.home_assistant    uid:home_assistant

# Grafana dashboard
terraform import grafana_dashboard.tempest_basic       uid:tempest-basic
```

The bucket/token bootstrap doesn't need an import step — the script reconciles by name/description on the next apply:

- Existing `tempest_archive` / `zigbee_archive` buckets are kept (get-or-create by name).
- Existing tokens whose description doesn't match our `(tf)` suffix are left alone. Three new tokens get minted; rotate the consumers and delete the old ones once nothing references them.

After the imports, `terraform plan` should be a no-op for containers/volumes/network/datasources. Expect a `terraform_data.influx_bootstrap` create and three `secure_json_data_encoded` diffs on the datasources (because Terraform doesn't see the old token's plaintext, only the new one it's about to mint). Address any unexpected diff before the first `apply`.

### Rotating the consumers post-import

After the first `apply` mints the new `(tf)`-suffixed tokens:

```sh
# Tempest bridge
terraform output -raw influx_tempest_token \
  | xargs -I{} sed -i '' 's|^INFLUX_TEMPEST_TOKEN=.*|INFLUX_TEMPEST_TOKEN={}|' \
    ~/.local/share/tempest-bridge/.env
launchctl kickstart -k gui/$UID/dev.tommydoerr.tempest-bridge

# Old non-tf tokens — list and delete once you've confirmed nothing uses them
source /Volumes/dev/influxdb/.env
docker exec influxdb influx auth list --org "$INFLUX_ORG" --token "$INFLUX_ADMIN_TOKEN"
docker exec influxdb influx auth delete --id <old token id> --token "$INFLUX_ADMIN_TOKEN"
```

## State

Local state in this directory (`terraform.tfstate`). Single operator, single machine, not worth a remote backend. **Both the state file and `.state/influx.json` contain secrets in plaintext** — they're gitignored along with `terraform.tfvars` and `.terraform/`. Back them up out-of-band with the other host secrets.

If `.state/influx.json` is lost, the next apply will re-mint the three `(tf)` tokens (the old ones get deleted by description). Datasources auto-update. The tempest-bridge `.env` will need its token updated by hand.

## Drift / divergence from the compose files

The compose files under `../influxdb/` and `../grafana/` are intentionally a near-perfect mirror of this Terraform — they encode the same image versions, ports, volumes, env vars, and healthchecks. If you change one, change the other (or delete the compose files when you're confident Terraform owns the stack). The provisioning yaml/json under `../grafana/provisioning/` is NOT used once Terraform is in charge: the `grafana_data_source` and `grafana_dashboard` resources push the same config via Grafana's HTTP API.

The dashboard JSON is the one exception — `grafana_dashboard.tempest_basic` reads `../grafana/provisioning/dashboards/tempest-basic.json` via `file()`, so editing the checked-in JSON and re-applying is the supported edit path.
