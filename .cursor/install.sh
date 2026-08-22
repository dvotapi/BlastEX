#!/usr/bin/env bash
# Idempotent repository bootstrap for BlastEX Cloud Agents.
# Prepares the Python virtualenv (API + Streamlit + tests) and the React
# frontend dependencies. Safe to run repeatedly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# The default image ships Python 3.12 but not the venv/ensurepip module.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

# Python virtualenv with REST API, Streamlit UI and test dependencies.
if [ ! -x ".venv/bin/python" ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-api.txt pytest

# React frontend dependencies.
cd frontend
npm ci
