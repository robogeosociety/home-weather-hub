locals {
  tempest_basic_dashboard = merge(
    jsondecode(file("${path.module}/../grafana/provisioning/dashboards/tempest-basic.json")),
    { uid = "tempest-basic" },
  )
}

resource "grafana_dashboard" "tempest_basic" {
  config_json = jsonencode(local.tempest_basic_dashboard)
  overwrite   = true

  depends_on = [
    grafana_data_source.tempest_archive,
    grafana_data_source.home_assistant,
  ]
}
