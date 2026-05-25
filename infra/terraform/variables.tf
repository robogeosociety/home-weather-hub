variable "influx_admin_user" {
  type        = string
  description = "InfluxDB initial admin username. Only consulted on the container's first boot."
  default     = "admin"
}

variable "influx_admin_password" {
  type        = string
  description = "InfluxDB initial admin password. Only consulted on the container's first boot."
  sensitive   = true
}

variable "influx_admin_token" {
  type        = string
  description = "InfluxDB admin token. Set on first boot via DOCKER_INFLUXDB_INIT_ADMIN_TOKEN and reused by the influxdb-v2 provider for all subsequent API calls."
  sensitive   = true
}

variable "influx_org" {
  type        = string
  description = "InfluxDB organization name."
  default     = "home"
}

variable "influx_initial_bucket" {
  type        = string
  description = "Bucket created by DOCKER_INFLUXDB_INIT_BUCKET on first boot. The other buckets are created by Terraform."
  default     = "home_assistant"
}

variable "influx_host_port" {
  type        = number
  description = "Host port the InfluxDB container publishes to."
  default     = 8086
}

variable "grafana_admin_user" {
  type        = string
  description = "Grafana admin username."
  default     = "admin"
}

variable "grafana_admin_password" {
  type        = string
  description = "Grafana admin password."
  sensitive   = true
}

variable "grafana_host_port" {
  type        = number
  description = "Host port the Grafana container publishes to. Container always listens on 3000."
  default     = 3001
}

variable "influxdb_image" {
  type        = string
  description = "InfluxDB Docker image tag."
  default     = "influxdb:2.7-alpine"
}

variable "grafana_image" {
  type        = string
  description = "Grafana Docker image tag."
  default     = "grafana/grafana-oss:11.3.0"
}

variable "archive_buckets" {
  type        = list(string)
  description = "Additional buckets Terraform should manage. The DOCKER_INFLUXDB_INIT_BUCKET value is created out-of-band by the container on first boot and managed via a separate import."
  default     = ["tempest_archive", "zigbee_archive"]
}
