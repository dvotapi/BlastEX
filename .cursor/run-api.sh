#!/usr/bin/env bash
# Launches the BlastEX FastAPI backend for local/Cloud Agent development.
# Injects dev-only auth configuration when the deployment secrets are absent so
# the React UI can authenticate out of the box. These values are for local
# development only and must never be used in production.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
. .venv/bin/activate

export BLASTEX_COOKIE_SECURE="${BLASTEX_COOKIE_SECURE:-false}"
export BLASTEX_SESSION_SECRET="${BLASTEX_SESSION_SECRET:-blastex-dev-session-secret}"
export BLASTEX_CORS_ORIGINS="${BLASTEX_CORS_ORIGINS:-http://127.0.0.1:5173}"

# Dev-only internal account: admin@blastex.dev / blastex
if [ -z "${BLASTEX_USERS_JSON:-}" ]; then
  BLASTEX_USERS_JSON="$(python - <<'PY'
import json
from cost.auth import hash_password

print(json.dumps([{
    "email": "admin@blastex.dev",
    "password_hash": hash_password("blastex"),
    "role": "admin",
    "display_name": "Dev Admin",
    "organization_id": "default",
    "organization_name": "BlastEX Dev",
    "active": True,
}]))
PY
)"
  export BLASTEX_USERS_JSON
fi

exec uvicorn api.main:app --reload --host 127.0.0.1 --port 8000
