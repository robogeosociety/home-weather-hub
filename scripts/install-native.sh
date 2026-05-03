#!/usr/bin/env bash
# Idempotent installer for the home-weather-hub ingest stack on macOS.
#
# Brings up everything as a launchd / brew-services managed service:
#   - Mosquitto via brew services        (broker on 1883 + 9001)
#   - Zigbee2MQTT via launchd agent      (~/zigbee2mqtt, native Node @24)
#   - zigbee-subscriber via launchd      (this repo, uv run zigbee-subscriber)
#   - tempest-listener via launchd       (this repo, uv run tempest-listener)
#
# Re-running is safe: each step checks for the desired end state before acting.
#
# Usage:
#   scripts/install-native.sh                          # default Sonoff dongle path
#   ZIGBEE_ADAPTER_PATH=/dev/cu.usbserial-XXX scripts/install-native.sh
#
# Prerequisites:
#   - Homebrew installed
#   - The Sonoff ZBDongle-E (or compatible ember adapter) plugged in

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ZIGBEE_ADAPTER_PATH="${ZIGBEE_ADAPTER_PATH:-/dev/cu.usbserial-220}"
Z2M_DIR="$HOME/zigbee2mqtt"
Z2M_FRONTEND_PORT="${Z2M_FRONTEND_PORT:-8088}"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
NODE_PREFIX="/opt/homebrew/opt/node@24"

note()  { printf "\033[34m▸\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m✓\033[0m %s\n" "$*"; }
warn()  { printf "\033[33m!\033[0m %s\n" "$*"; }
die()   { printf "\033[31m✗\033[0m %s\n" "$*" >&2; exit 1; }

[ -e "$ZIGBEE_ADAPTER_PATH" ] || die "Zigbee adapter not found at $ZIGBEE_ADAPTER_PATH (set ZIGBEE_ADAPTER_PATH=...)"
command -v brew >/dev/null || die "Homebrew not found — install from https://brew.sh first"

# 1. brew dependencies -------------------------------------------------------
note "checking brew packages: node@24, mosquitto"
for pkg in node@24 mosquitto; do
  if brew list --formula | grep -qx "$pkg"; then
    ok "$pkg already installed"
  else
    note "installing $pkg"
    brew install "$pkg"
  fi
done

# 2. corepack-managed pnpm ---------------------------------------------------
note "ensuring pnpm is available via corepack (node@24)"
PATH="$NODE_PREFIX/bin:$PATH"
if ! command -v pnpm >/dev/null 2>&1 || ! pnpm --version >/dev/null 2>&1; then
  corepack enable
  corepack prepare pnpm@10.18.3 --activate
fi
ok "pnpm $(pnpm --version)"

# 3. Mosquitto config + service ---------------------------------------------
note "writing Mosquitto config"
MOSQ_CONF="/opt/homebrew/etc/mosquitto/mosquitto.conf"
mkdir -p "$(dirname "$MOSQ_CONF")" /opt/homebrew/var/lib/mosquitto
cat > "$MOSQ_CONF" <<'EOF'
# home-weather-hub Mosquitto config (managed via brew services).
# LAN-only home broker; do NOT expose 1883/9001 to the internet.

persistence true
persistence_location /opt/homebrew/var/lib/mosquitto/
log_dest stdout

listener 1883 0.0.0.0
allow_anonymous true

listener 9001 0.0.0.0
protocol websockets
allow_anonymous true
EOF

if brew services info mosquitto --json | grep -q '"running":true'; then
  note "restarting mosquitto to pick up config"
  brew services restart mosquitto >/dev/null
else
  brew services start mosquitto >/dev/null
fi
ok "mosquitto running on :1883 + :9001"

# 4. Zigbee2MQTT clone + build ----------------------------------------------
if [ ! -d "$Z2M_DIR/.git" ]; then
  note "cloning Zigbee2MQTT to $Z2M_DIR"
  git clone --depth 1 https://github.com/Koenkk/zigbee2mqtt.git "$Z2M_DIR"
else
  ok "$Z2M_DIR already cloned"
fi

note "installing Z2M dependencies (pnpm install)"
( cd "$Z2M_DIR" && pnpm install --frozen-lockfile >/dev/null )
note "building Z2M (pnpm build)"
( cd "$Z2M_DIR" && pnpm build >/dev/null )
ok "Z2M built"

# 5. Z2M configuration -------------------------------------------------------
mkdir -p "$Z2M_DIR/data"
Z2M_CONF="$Z2M_DIR/data/configuration.yaml"
if [ ! -f "$Z2M_CONF" ]; then
  note "writing initial Z2M configuration"
  cat > "$Z2M_CONF" <<EOF
version: 5
homeassistant:
  enabled: false
mqtt:
  base_topic: zigbee2mqtt
  server: mqtt://127.0.0.1:1883
serial:
  port: $ZIGBEE_ADAPTER_PATH
  adapter: ember
  baudrate: 115200
frontend:
  enabled: true
  port: $Z2M_FRONTEND_PORT
  # 127.0.0.1 only — external access lives behind tailscale serve.
  # Binding 0.0.0.0 triggers a dual-stack IPv4+IPv6 listen that races
  # under launchd and crashes Z2M with EADDRINUSE on every restart.
  host: 127.0.0.1
advanced:
  output: json
  log_level: info
device_options:
  retain: false
EOF
else
  ok "Z2M config already exists at $Z2M_CONF (leaving in place)"
fi

# 6. uv-managed Python deps for the subscriber ------------------------------
note "syncing Python deps for the subscriber"
( cd "$REPO_DIR" && uv sync >/dev/null )

# 7. launchd agents ----------------------------------------------------------
mkdir -p "$LAUNCH_AGENTS_DIR" "$REPO_DIR/data"
UV_BIN="$(command -v uv || true)"
[ -n "$UV_BIN" ] || die "uv not found on PATH; install from https://docs.astral.sh/uv/getting-started/installation/"

install_agent() {
  local src="$1" dst="$2" label
  label="$(basename "$dst" .plist)"

  note "installing $label"
  sed -e "s|@@HOME@@|$HOME|g" \
      -e "s|@@REPO_DIR@@|$REPO_DIR|g" \
      -e "s|@@UV_BIN@@|$UV_BIN|g" \
      "$src" > "$dst"

  # bootout fails harmlessly if it wasn't loaded; ignore.
  # Wait until the previous instance fully releases its sockets (TIME_WAIT)
  # before bootstrapping a fresh one — otherwise Z2M's frontend bind races.
  if launchctl print "gui/$UID/$label" >/dev/null 2>&1; then
    launchctl bootout "gui/$UID" "$dst" 2>/dev/null || true
    sleep 2
  fi
  launchctl bootstrap "gui/$UID" "$dst"
  launchctl enable "gui/$UID/$label"
  ok "loaded $label"
}

install_agent \
  "$REPO_DIR/scripts/launchd/com.zigbee2mqtt.plist" \
  "$LAUNCH_AGENTS_DIR/com.zigbee2mqtt.plist"

install_agent \
  "$REPO_DIR/scripts/launchd/com.home-weather-hub.zigbee-subscriber.plist" \
  "$LAUNCH_AGENTS_DIR/com.home-weather-hub.zigbee-subscriber.plist"

install_agent \
  "$REPO_DIR/scripts/launchd/com.home-weather-hub.tempest-listener.plist" \
  "$LAUNCH_AGENTS_DIR/com.home-weather-hub.tempest-listener.plist"

# 8. Smoke check -------------------------------------------------------------
sleep 4
note "verifying agents are running"
launchctl print "gui/$UID/com.zigbee2mqtt" >/dev/null \
  && ok "com.zigbee2mqtt loaded" \
  || warn "com.zigbee2mqtt not loaded — check $Z2M_DIR/data/launchd.log"
launchctl print "gui/$UID/com.home-weather-hub.zigbee-subscriber" >/dev/null \
  && ok "com.home-weather-hub.zigbee-subscriber loaded" \
  || warn "subscriber not loaded — check $REPO_DIR/data/zigbee-subscriber.launchd.log"
launchctl print "gui/$UID/com.home-weather-hub.tempest-listener" >/dev/null \
  && ok "com.home-weather-hub.tempest-listener loaded" \
  || warn "tempest-listener not loaded — check $REPO_DIR/data/tempest-listener.launchd.log"

cat <<EOF

Done. Next steps:
  - Z2M web UI:        http://localhost:$Z2M_FRONTEND_PORT
  - Pair sensors:      toggle "Permit join" in the Z2M UI, then reset the device
  - Inspect data:      sqlite3 $REPO_DIR/data/weather.db
  - Stop a service:    launchctl bootout gui/$UID ~/Library/LaunchAgents/<plist>
  - Tail Z2M:          tail -f $Z2M_DIR/data/launchd.log
  - Tail subscriber:   tail -f $REPO_DIR/data/zigbee-subscriber.launchd.log
  - Tail Tempest:      tail -f $REPO_DIR/data/tempest-listener.launchd.log
EOF
