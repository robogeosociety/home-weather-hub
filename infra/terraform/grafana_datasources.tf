locals {
  influx_datasource_url = "http://influxdb:8086"
}

resource "grafana_data_source" "tempest_archive" {
  type       = "influxdb"
  name       = "InfluxDB - tempest_archive"
  uid        = "tempest_archive"
  url        = local.influx_datasource_url
  is_default = true

  json_data_encoded = jsonencode({
    version       = "Flux"
    organization  = var.influx_org
    defaultBucket = "tempest_archive"
    tlsSkipVerify = true
  })

  secure_json_data_encoded = jsonencode({
    token = local.influx_grafana_token
  })

  depends_on = [time_sleep.grafana_ready]
}

resource "grafana_data_source" "home_assistant" {
  type = "influxdb"
  name = "InfluxDB - home_assistant"
  uid  = "home_assistant"
  url  = local.influx_datasource_url

  json_data_encoded = jsonencode({
    version       = "Flux"
    organization  = var.influx_org
    defaultBucket = var.influx_initial_bucket
    tlsSkipVerify = true
  })

  secure_json_data_encoded = jsonencode({
    token = local.influx_grafana_token
  })

  depends_on = [time_sleep.grafana_ready]
}
