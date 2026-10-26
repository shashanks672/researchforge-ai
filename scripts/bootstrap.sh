#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v python3.12 >/dev/null; then
  echo 'Python 3.12 is required. On macOS: brew install python@3.12'
  exit 1
fi
node -e 'const [major, minor] = process.versions.node.split(".").map(Number); if (major !== 22 || minor < 13) { console.error("Use Node 22.13+ within the Node 22 release line; see .nvmrc"); process.exit(1); }'
if [[ ! -f .env ]]; then cp .env.example .env; fi
if [[ ! -f frontend/.env.local ]]; then cp frontend/.env.example frontend/.env.local; fi
if [[ ! -d backend/.venv ]]; then python3.12 -m venv backend/.venv; fi
if [[ ! -x backend/.venv/bin/uv ]]; then
  backend/.venv/bin/python -m pip install 'uv==0.13.1'
fi
backend/.venv/bin/uv sync --project backend --locked
backend/.venv/bin/python scripts/configure_database.py
(cd frontend && npm ci)
echo 'Setup complete. See README.md for the two development server commands.'
