output "influx_tempest_token" {
  description = "Write-bucket token for the tempest-bridge launchd service. Drop into ~/.local/share/tempest-bridge/.env as INFLUX_TEMPEST_TOKEN."
  value       = local.influx_tempest_token
  sensitive   = true
}

output "influx_ha_token" {
  description = "Write-bucket token for the home_assistant bucket."
  value       = local.influx_ha_token
  sensitive   = true
}

output "influx_grafana_token" {
  description = "Read token covering every managed bucket. Wired into both Grafana datasources by Terraform; surfaced here for out-of-stack consumers."
  value       = local.influx_grafana_token
  sensitive   = true
}

output "influx_bucket_ids" {
  description = "Map of bucket name → InfluxDB bucket ID, as discovered/created by the bootstrap script."
  value       = local.influx_bucket_ids
}

output "influxdb_url" {
  value = "http://localhost:${var.influx_host_port}"
}

output "grafana_url" {
  value = "http://localhost:${var.grafana_host_port}"
}
