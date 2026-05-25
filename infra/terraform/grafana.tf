resource "docker_image" "grafana" {
  name         = var.grafana_image
  keep_locally = true
}

resource "docker_volume" "grafana_data" {
  name = "grafana_grafana_data"
}

resource "docker_container" "grafana" {
  name    = "grafana"
  image   = docker_image.grafana.image_id
  restart = "unless-stopped"

  ports {
    internal = 3000
    external = var.grafana_host_port
  }

  volumes {
    volume_name    = docker_volume.grafana_data.name
    container_path = "/var/lib/grafana"
  }

  networks_advanced {
    name = docker_network.influxdb_default.name
  }

  env = [
    "GF_SECURITY_ADMIN_USER=${var.grafana_admin_user}",
    "GF_SECURITY_ADMIN_PASSWORD=${var.grafana_admin_password}",
    "GF_USERS_ALLOW_SIGN_UP=false",
    "GF_AUTH_ANONYMOUS_ENABLED=false",
    "GF_ANALYTICS_REPORTING_ENABLED=false",
    "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
  ]

  healthcheck {
    test         = ["CMD-SHELL", "wget -qO- http://localhost:3000/api/health | grep -q 'ok' || exit 1"]
    interval     = "30s"
    timeout      = "5s"
    retries      = 5
    start_period = "30s"
  }
}

resource "time_sleep" "grafana_ready" {
  depends_on      = [docker_container.grafana]
  create_duration = "20s"
}
