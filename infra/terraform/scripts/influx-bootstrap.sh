#!/usr/bin/env bash
# Thin shim: just exec the Python bootstrapper. Terraform's local-exec
# provisioner invokes this so the runtime dependency from .tf files is shell,
# but the actual logic lives in influx-bootstrap.py for sanity.
set -euo pipefail
exec python3 "$(dirname "$0")/influx-bootstrap.py" "$@"
