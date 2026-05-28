#!/bin/zsh
# Sync local InfluxDB backups to Cloudflare R2.
#
# Runs daily at 04:00 via LaunchAgent (dev.tommydoerr.influxdb-backup-r2-sync),
# 30 minutes after backup.sh has finished its 03:30 local snapshot.
#
# Strategy: `rclone copy` — uploads anything in $BACKUP_ROOT that isn't already
# in R2. Never deletes from R2, so the bucket retains every snapshot ever
# made, even after backup.sh's 30-day local prune removes them from disk.
# Backups are tiny (~16KB/day), so unbounded growth costs nothing in R2's free
# tier for years.
#
# Credentials live in /Volumes/dev/influxdb/.env (chmod 600):
#   R2_ACCOUNT_ID         — Cloudflare account ID (32-char hex)
#   R2_ACCESS_KEY_ID      — R2 API token, Object Read & Write on this bucket
#   R2_SECRET_ACCESS_KEY  — secret half of the token
#   R2_BUCKET             — bucket name (default: influxdb-backups)

set -eu

ENV_FILE="/Volumes/dev/influxdb/.env"
BACKUP_ROOT="/Volumes/dev/influxdb/backups"

RCLONE="/opt/homebrew/bin/rclone"
[[ -x "$RCLONE" ]] || RCLONE="/usr/local/bin/rclone"
[[ -x "$RCLONE" ]] || RCLONE="$(/usr/bin/env which rclone)"

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID missing from $ENV_FILE}"
: "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID missing from $ENV_FILE}"
: "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY missing from $ENV_FILE}"
R2_BUCKET="${R2_BUCKET:-influxdb-backups}"

# Define the rclone remote inline via env vars so we don't need a separate
# rclone.conf with credentials in it.
export RCLONE_CONFIG_R2_TYPE=s3
export RCLONE_CONFIG_R2_PROVIDER=Cloudflare
export RCLONE_CONFIG_R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID"
export RCLONE_CONFIG_R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY"
export RCLONE_CONFIG_R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
export RCLONE_CONFIG_R2_NO_CHECK_BUCKET=true
export RCLONE_CONFIG_R2_ACL=private

echo "[$(date)] syncing $BACKUP_ROOT → r2:$R2_BUCKET"

"$RCLONE" copy \
  --immutable \
  --transfers 4 \
  --checkers 8 \
  --include "20*/**" \
  "$BACKUP_ROOT" "r2:$R2_BUCKET"

echo "[$(date)] r2 contents (top-level): $("$RCLONE" lsf "r2:$R2_BUCKET" --dirs-only | wc -l | tr -d ' ') snapshot dirs"
echo "[$(date)] done"
