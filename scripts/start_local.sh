#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUN_DIR="$ROOT/.local/run"
LOG_DIR="$ROOT/.local/logs"
CONTACT_FILE="$ROOT/.local/wikipedia-contact"
mkdir -p "$RUN_DIR" "$LOG_DIR"
chmod 700 "$ROOT/.local" "$RUN_DIR" "$LOG_DIR"

fail() { echo "Startup stopped: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || fail "required command '$1' is missing; install/configure it using the README."; }
need docker
need curl
need lsof
need ollama
[[ -f .env ]] || fail "the local .env file is missing; follow the README setup first. No files were overwritten."
[[ -x backend/.venv/bin/python && -x backend/.venv/bin/alembic ]] || fail "backend/.venv is missing; run the documented bootstrap."
[[ -x frontend/node_modules/.bin/next ]] || fail "frontend dependencies are missing; run the documented bootstrap."
node -e 'const [major,minor]=process.versions.node.split(".").map(Number); if(major!==22||minor<13){console.error("Node 22.13+ is required; see .nvmrc");process.exit(1)}' || fail "unsupported Node.js version."

if ! docker info >/dev/null 2>&1; then fail "Docker Desktop is not ready. Start Docker Desktop and retry."; fi
docker compose --profile infrastructure up -d --pull never --wait postgres qdrant || fail "PostgreSQL/Qdrant could not start from existing local images. No image downloads were requested."

OLLAMA_TAGS="$(curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags)" || fail "Ollama is not responding at 127.0.0.1:11434. Start its existing local runtime; this script will not download a model."
python3 -c 'import json,sys; tags=json.load(sys.stdin).get("models",[]); sys.exit(0 if any(x.get("name")=="qwen3:8b" for x in tags) else 1)' <<<"$OLLAMA_TAGS" || fail "cached Ollama model qwen3:8b was not found. No model was downloaded."

# The database is kept intact. Upgrade only through the repository's forward migrations.
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head || fail "database migration check/forward upgrade failed; review your local database before retrying."

# Force the local provider and disable all hosted calls. The private contact is read
# from a 0600 ignored file; it is never printed or placed in command-line arguments.
unset RF_PUBLIC_SEARCH_CONTACT RF_OPENAI_API_KEY RF_BRAVE_API_KEY
export RF_LLM_PROVIDER=ollama RF_OLLAMA_URL=http://127.0.0.1:11434 RF_OLLAMA_MODEL=qwen3:8b RF_LIVE_CALLS_APPROVED=false
SEARCH_EXPECTED=disabled
if [[ -f "$CONTACT_FILE" ]]; then
  permissions="$(stat -f '%Lp' "$CONTACT_FILE")"
  [[ "$permissions" == 600 ]] || fail "private contact file permissions are not 600. Run scripts/configure_wikipedia_contact.sh again."
  IFS= read -r RF_PUBLIC_SEARCH_CONTACT < "$CONTACT_FILE"
  [[ -n "$RF_PUBLIC_SEARCH_CONTACT" ]] || fail "private contact file is empty. Reconfigure it privately."
  printf '%s' "$RF_PUBLIC_SEARCH_CONTACT" | backend/.venv/bin/python -c 'import sys; from app.core.config import Settings; Settings.validate_public_search_contact(sys.stdin.read())' || fail "private contact file does not contain a valid HTTPS page or mailto address. Reconfigure it privately."
  export RF_PUBLIC_SEARCH_CONTACT RF_SEARCH_PROVIDER=wikipedia RF_FREE_SEARCH_ENABLED=true
  SEARCH_EXPECTED=wikipedia
else
  export RF_SEARCH_PROVIDER=disabled RF_FREE_SEARCH_ENABLED=false
fi

pid_for_port() { lsof -nP -t -iTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -n 1 || true; }
process_cwd() { lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1; }
process_cmd() { ps -p "$1" -o command= 2>/dev/null || true; }
is_project_process() { [[ "$(process_cwd "$1")" == "$ROOT" || "$(process_cwd "$1")" == "$ROOT/frontend" ]]; }
safe_config() {
  python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("execution_mode",""),d.get("model",""),d.get("search_provider",""),str(d.get("free_search_enabled",False)).lower(),str(d.get("live_calls_approved",True)).lower())'
}

api_pid="$(pid_for_port 8000)"
if [[ -n "$api_pid" ]]; then
  cmd="$(process_cmd "$api_pid")"
  is_project_process "$api_pid" && [[ "$cmd" == *uvicorn* ]] || fail "port 8000 is occupied by a process not verified as this project's API (PID $api_pid). It was left untouched."
  api_config="$(curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/config 2>/dev/null)" || fail "the project process on port 8000 is not a healthy ResearchForge API; it was left untouched."
  read -r mode model search free hosted <<<"$(printf '%s' "$api_config" | safe_config)"
  [[ "$mode" == local && "$model" == qwen3:8b && "$search" == "$SEARCH_EXPECTED" && "$free" == "$([[ "$SEARCH_EXPECTED" == wikipedia ]] && echo true || echo false)" && "$hosted" == false ]] || fail "the existing API has a different provider configuration. PID $api_pid was left running; stop/restart it deliberately, then retry."
  echo "Reusing verified ResearchForge API (PID $api_pid): LOCAL qwen3:8b, search=$search."
else
  chmod 600 "$LOG_DIR"/backend.log 2>/dev/null || true
  nohup backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log >"$LOG_DIR/backend.log" 2>&1 &
  api_pid=$!
  printf '%s\n' "$api_pid" > "$RUN_DIR/backend.pid"
  chmod 600 "$RUN_DIR/backend.pid" "$LOG_DIR/backend.log"
  for _ in {1..45}; do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/ready >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -fsS --max-time 3 http://127.0.0.1:8000/ready >/dev/null || fail "FastAPI did not become ready. See the private local log at .local/logs/backend.log; contact values are not intentionally logged."
  api_config="$(curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/config)"
  read -r mode model search free hosted <<<"$(printf '%s' "$api_config" | safe_config)"
  [[ "$mode" == local && "$model" == qwen3:8b && "$search" == "$SEARCH_EXPECTED" && "$hosted" == false ]] || fail "FastAPI started with an unexpected provider configuration; review the local setup."
  echo "Started FastAPI (PID $api_pid): LOCAL qwen3:8b, search=$search."
fi

ui_pid="$(pid_for_port 3000)"
if [[ -n "$ui_pid" ]]; then
  cmd="$(process_cmd "$ui_pid")"
  [[ "$(process_cwd "$ui_pid")" == "$ROOT/frontend" && "$cmd" == *next* ]] || fail "port 3000 is occupied by a process not verified as this project's Next.js UI (PID $ui_pid). It was left untouched."
  curl -fsS --max-time 5 http://127.0.0.1:3000/ >/dev/null || fail "the verified Next.js process is not responding; it was left untouched."
  echo "Reusing verified Next.js UI (PID $ui_pid)."
else
  (cd frontend && nohup node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3000 >"$LOG_DIR/frontend.log" 2>&1 & echo $! > "$RUN_DIR/frontend.pid")
  chmod 600 "$RUN_DIR/frontend.pid" "$LOG_DIR/frontend.log"
  ui_pid="$(cat "$RUN_DIR/frontend.pid")"
  for _ in {1..60}; do
    if curl -fsS --max-time 2 http://127.0.0.1:3000/ >/dev/null 2>&1; then break; fi
    sleep 1
  done
  curl -fsS --max-time 5 http://127.0.0.1:3000/ >/dev/null || fail "Next.js did not become ready. See .local/logs/frontend.log."
  echo "Started Next.js UI (PID $ui_pid)."
fi

echo "Ready: http://127.0.0.1:3000"
echo "Local API readiness: http://127.0.0.1:8000/ready"
echo "Run mode: LOCAL qwen3:8b; hosted calls disabled; public search: $SEARCH_EXPECTED."
[[ "$SEARCH_EXPECTED" == wikipedia ]] || echo "Web modes need your private Wikimedia contact; run bash scripts/configure_wikipedia_contact.sh, then bash scripts/restart_local_api.sh."
echo "Use bash scripts/stop_local.sh to stop only services this script started. PostgreSQL, Qdrant, and Ollama stay running."
