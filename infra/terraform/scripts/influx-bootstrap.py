#!/usr/bin/env python3
"""Get-or-create InfluxDB buckets and service tokens for the home stack.

Called by terraform_data.influx_bootstrap during `terraform apply`. Writes the
resulting state to "$INFLUX_STATE_FILE" as JSON:

    {
      "buckets": { "<name>": "<id>", ... },
      "tokens":  {
        "tempest_bridge": "<secret>",
        "home_assistant": "<secret>",
        "grafana_read":   "<secret>"
      }
    }

Idempotency:
  - Buckets: looked up by name; created if missing. IDs are stable.
  - Tokens: looked up by description. `influx auth list --json` returns each
    token's plaintext secret, so we adopt an existing token by description
    instead of minting a duplicate. New tokens are only minted when no
    matching description exists.

All inputs are env vars passed by Terraform.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path


def env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: env var {name} is required")
    return value


CONTAINER = env("INFLUX_CONTAINER")
ORG = env("INFLUX_ORG")
ADMIN_TOKEN = env("INFLUX_ADMIN_TOKEN")
INITIAL_BUCKET = env("INFLUX_INITIAL_BUCKET")
ARCHIVE_BUCKETS = env("ARCHIVE_BUCKETS").split()
STATE_FILE = Path(env("INFLUX_STATE_FILE"))

TOKEN_DESCRIPTIONS = {
    "tempest_bridge": "tempest-bridge write",
    "home_assistant": "home-assistant write",
    "grafana_read": "grafana read",
}


def influx(*args: str) -> str:
    """Run `influx` inside the container, return stdout (raises on non-zero)."""
    cmd = [
        "docker",
        "exec",
        "-i",
        CONTAINER,
        "influx",
        *args,
        "--token",
        ADMIN_TOKEN,
        "--org",
        ORG,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return result.stdout


def influx_json(*args: str) -> object:
    return json.loads(influx(*args, "--json"))


def bucket_id(name: str) -> str | None:
    """Return bucket ID or None if it doesn't exist."""
    try:
        buckets = influx_json("bucket", "list", "--name", name)
    except subprocess.CalledProcessError:
        return None
    for b in buckets or []:
        if b.get("name") == name:
            return b.get("id")
    return None


def ensure_bucket(name: str) -> str:
    existing = bucket_id(name)
    if existing:
        return existing
    created = influx_json("bucket", "create", "--name", name)
    if isinstance(created, list) and created:
        created = created[0]
    return created["id"]


def list_authorizations() -> list[dict]:
    try:
        return influx_json("auth", "list") or []
    except subprocess.CalledProcessError:
        return []


def find_token_by_description(auths: list[dict], description: str) -> str | None:
    for auth in auths:
        if auth.get("description") == description:
            return auth.get("token")
    return None


def create_auth(description: str, bucket_perms: Iterable[tuple[str, str]]) -> str:
    """bucket_perms: iterable of (action, bucket_id) where action is read/write."""
    args = ["auth", "create", "--description", description]
    for action, bucket in bucket_perms:
        flag = "--write-bucket" if action == "write" else "--read-bucket"
        args.extend([flag, bucket])
    result = influx_json(*args)
    if isinstance(result, list) and result:
        result = result[0]
    return result["token"]


def main() -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

    # 1. Resolve / create buckets.
    buckets: dict[str, str] = {}
    initial_id = bucket_id(INITIAL_BUCKET)
    if not initial_id:
        sys.exit(
            f"error: initial bucket '{INITIAL_BUCKET}' not found — "
            "expected the influxdb container to have created it on first boot"
        )
    buckets[INITIAL_BUCKET] = initial_id
    for name in ARCHIVE_BUCKETS:
        buckets[name] = ensure_bucket(name)

    # 2. Resolve / mint tokens (adopt existing by description; create if absent).
    existing_auths = list_authorizations()
    tokens: dict[str, str] = {}

    def resolve_token(key: str, perms: list[tuple[str, str]]) -> str:
        description = TOKEN_DESCRIPTIONS[key]
        adopted = find_token_by_description(existing_auths, description)
        if adopted:
            return adopted
        return create_auth(description, perms)

    tokens["tempest_bridge"] = resolve_token(
        "tempest_bridge",
        [("write", buckets["tempest_archive"])],
    )
    tokens["home_assistant"] = resolve_token(
        "home_assistant",
        [("write", buckets[INITIAL_BUCKET])],
    )
    tokens["grafana_read"] = resolve_token(
        "grafana_read",
        [("read", bucket_id_) for bucket_id_ in buckets.values()],
    )

    # 3. Write state atomically.
    payload = {"buckets": buckets, "tokens": tokens}
    tmp = STATE_FILE.with_suffix(STATE_FILE.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.chmod(0o600)
    tmp.replace(STATE_FILE)


if __name__ == "__main__":
    main()
