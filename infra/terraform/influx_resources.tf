locals {
  influx_state_file = "${path.module}/.state/influx.json"
}

# Bootstrap script creates buckets + tokens via `docker exec influxdb influx`.
# Idempotent: re-applying with the same state file reuses tokens; if the state
# file is wiped or the InfluxDB volume is reset, fresh tokens are minted and
# Grafana datasources get re-keyed automatically downstream.
resource "terraform_data" "influx_bootstrap" {
  triggers_replace = {
    org             = var.influx_org
    initial_bucket  = var.influx_initial_bucket
    archive_buckets = join(",", var.archive_buckets)
    container_id    = docker_container.influxdb.id
  }

  provisioner "local-exec" {
    command     = "${path.module}/scripts/influx-bootstrap.sh"
    working_dir = path.module
    environment = {
      INFLUX_CONTAINER      = docker_container.influxdb.name
      INFLUX_ORG            = var.influx_org
      INFLUX_ADMIN_TOKEN    = var.influx_admin_token
      INFLUX_INITIAL_BUCKET = var.influx_initial_bucket
      ARCHIVE_BUCKETS       = join(" ", var.archive_buckets)
      INFLUX_STATE_FILE     = local.influx_state_file
    }
  }

  depends_on = [time_sleep.influxdb_ready]
}

data "local_file" "influx_state" {
  filename   = local.influx_state_file
  depends_on = [terraform_data.influx_bootstrap]
}

locals {
  influx_state         = jsondecode(data.local_file.influx_state.content)
  influx_bucket_ids    = local.influx_state.buckets
  influx_tempest_token = local.influx_state.tokens.tempest_bridge
  influx_ha_token      = local.influx_state.tokens.home_assistant
  influx_grafana_token = local.influx_state.tokens.grafana_read
}
