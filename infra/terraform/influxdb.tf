resource "docker_image" "influxdb" {
  name         = var.influxdb_image
  keep_locally = true
}

resource "docker_volume" "influxdb_data" {
  name = "influxdb_influxdb_data"
}

resource "docker_volume" "influxdb_config" {
  name = "influxdb_influxdb_config"
}

resource "docker_container" "influxdb" {
  name    = "influxdb"
  image   = docker_image.influxdb.image_id
  restart = "unless-stopped"

  ports {
    internal = 8086
    external = var.influx_host_port
  }

  volumes {
    volume_name    = docker_volume.influxdb_data.name
    container_path = "/var/lib/influxdb2"
  }

  volumes {
    volume_name    = docker_volume.influxdb_config.name
    container_path = "/etc/influxdb2"
  }

  networks_advanced {
    name = docker_network.influxdb_default.name
  }

  env = [
    "DOCKER_INFLUXDB_INIT_MODE=setup",
    "DOCKER_INFLUXDB_INIT_USERNAME=${var.influx_admin_user}",
    "DOCKER_INFLUXDB_INIT_PASSWORD=${var.influx_admin_password}",
    "DOCKER_INFLUXDB_INIT_ORG=${var.influx_org}",
    "DOCKER_INFLUXDB_INIT_BUCKET=${var.influx_initial_bucket}",
    "DOCKER_INFLUXDB_INIT_RETENTION=0",
    "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=${var.influx_admin_token}",
  ]

  healthcheck {
    test         = ["CMD", "influx", "ping"]
    interval     = "30s"
    timeout      = "5s"
    retries      = 5
    start_period = "30s"
  }

  lifecycle {
    # Env mutations would force-replace the container and destroy the named
    # volumes' contents on rollback. Setup env vars only matter on first boot,
    # so ignore them once the container exists.
    ignore_changes = [env]
  }
}

# Give InfluxDB a moment to finish booting before the influxdb-v2 provider
# starts talking to it. The healthcheck above doesn't gate the provider.
resource "time_sleep" "influxdb_ready" {
  depends_on      = [docker_container.influxdb]
  create_duration = "15s"
}
