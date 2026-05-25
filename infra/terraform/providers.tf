provider "docker" {
  # Uses DOCKER_HOST from environment. With OrbStack running, the default
  # unix socket at ~/.orbstack/run/docker.sock is auto-selected by the CLI.
}

provider "grafana" {
  url  = "http://localhost:${var.grafana_host_port}"
  auth = "${var.grafana_admin_user}:${var.grafana_admin_password}"
}
