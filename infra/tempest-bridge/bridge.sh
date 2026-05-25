#!/bin/zsh
# Tempest UDP → InfluxDB bridge wrapper. Runs as a LaunchAgent.
# Must live inside ~ because launchd's sandbox blocks /Volumes/* program paths.

set -eu

ENV_FILE="$HOME/.local/share/tempest-bridge/.env"
SCRIPT="$HOME/.local/share/tempest-bridge/tempest_to_influx.py"

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

export INFLUX_URL="${INFLUX_URL:-http://localhost:8086}"
export INFLUX_BUCKET="tempest_archive"
export INFLUX_TOKEN="$INFLUX_TEMPEST_TOKEN"

exec /usr/bin/python3 "$SCRIPT"
