#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export NEXT_TELEMETRY_DISABLED=1
backend/.venv/bin/ruff check backend scripts
backend/.venv/bin/ruff format --check backend scripts
backend/.venv/bin/mypy --config-file backend/pyproject.toml backend/app backend/tests scripts
backend/.venv/bin/python -m pytest -c backend/pyproject.toml backend/tests -m "not database"
(
  cd frontend
  npm run lint
  npm run format:check
  npm run typecheck
  npm test
  npm run build
)
if command -v docker >/dev/null; then
  docker compose --env-file .env.example --profile infrastructure config --quiet
else
  echo 'Docker CLI unavailable; Compose configuration check skipped.'
fi
