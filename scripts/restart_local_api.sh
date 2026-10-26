#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
RUN_DIR="$ROOT/.local/run"
LOG_DIR="$ROOT/.local/logs"
CONTACT_FILE="$ROOT/.local/wikipedia-contact"
mkdir -p "$RUN_DIR" "$LOG_DIR"
chmod 700 "$ROOT/.local" "$RUN_DIR" "$LOG_DIR"
fail() { echo "API restart stopped: $*" >&2; exit 1; }

[[ -x backend/.venv/bin/python && -x backend/.venv/bin/alembic ]] || fail "backend/.venv is missing."
[[ -f .env ]] || fail "local .env is missing; no configuration was changed."
command -v lsof >/dev/null 2>&1 || fail "lsof is required to verify process ownership."
command -v curl >/dev/null 2>&1 || fail "curl is required for local readiness checks."
curl -fsS --max-time 3 http://127.0.0.1:11434/api/tags | python3 -c 'import json,sys; sys.exit(0 if any(m.get("name")=="qwen3:8b" for m in json.load(sys.stdin).get("models",[])) else 1)' || fail "Ollama or the already-cached qwen3:8b model is unavailable. No model download was attempted."

API_PID="$(lsof -nP -t -iTCP:8000 -sTCP:LISTEN 2>/dev/null | head -n 1 || true)"
[[ -n "$API_PID" ]] || fail "no API is listening on port 8000; use scripts/start_local.sh."
API_CWD="$(lsof -a -p "$API_PID" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
API_CMD="$(ps -p "$API_PID" -o command= 2>/dev/null || true)"
[[ "$API_CWD" == "$ROOT" && "$API_CMD" == *uvicorn* ]] || fail "port 8000 is not owned by the verified project API (PID $API_PID); it was left untouched."
curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/config | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("app_name")=="ResearchForge AI" and d.get("execution_mode")=="local" and d.get("model")=="qwen3:8b" else 1)' || fail "the process does not report the expected local ResearchForge configuration."

# Refuse to interrupt an active graph run. Pending saved questions without a run are safe.
python3 - <<'PY' || fail "a local research run is active or its status could not be checked; wait for it to finish."
import json
from urllib.error import HTTPError
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8000/api/v1/research/sessions?limit=50&offset=0", timeout=3) as response:
    sessions = json.load(response)["items"]
for session in sessions:
    if session["status"] != "running":
        continue
    try:
        with urlopen(f"http://127.0.0.1:8000/api/v1/research/sessions/{session['id']}/run", timeout=3) as response:
            run = json.load(response)
    except HTTPError as error:
        if error.code == 404:
            continue
        raise
    if run.get("status") in {"queued", "running"}:
        raise SystemExit(1)
PY

# Signal only after project path, command, provider, and idle workflow are verified.
kill -TERM "$API_PID" || fail "could not request a graceful stop for verified API PID $API_PID."
for _ in {1..15}; do
  if ! kill -0 "$API_PID" 2>/dev/null; then break; fi
  sleep 1
done
kill -0 "$API_PID" 2>/dev/null && fail "API PID $API_PID is still stopping; no force-kill was sent."

unset RF_PUBLIC_SEARCH_CONTACT RF_OPENAI_API_KEY RF_BRAVE_API_KEY
export RF_LLM_PROVIDER=ollama RF_OLLAMA_URL=http://127.0.0.1:11434 RF_OLLAMA_MODEL=qwen3:8b RF_LIVE_CALLS_APPROVED=false
if [[ -f "$CONTACT_FILE" ]]; then
  [[ "$(stat -f '%Lp' "$CONTACT_FILE")" == 600 ]] || fail "private contact file must have 600 permissions; run its setup script again."
  IFS= read -r RF_PUBLIC_SEARCH_CONTACT < "$CONTACT_FILE"
  [[ -n "$RF_PUBLIC_SEARCH_CONTACT" ]] || fail "private contact file is empty."
  printf '%s' "$RF_PUBLIC_SEARCH_CONTACT" | backend/.venv/bin/python -c 'import sys; from app.core.config import Settings; Settings.validate_public_search_contact(sys.stdin.read())' || fail "private contact file does not contain a valid HTTPS page or mailto address. Reconfigure it privately."
  export RF_PUBLIC_SEARCH_CONTACT RF_SEARCH_PROVIDER=wikipedia RF_FREE_SEARCH_ENABLED=true
else
  export RF_SEARCH_PROVIDER=disabled RF_FREE_SEARCH_ENABLED=false
fi

backend/.venv/bin/alembic -c backend/alembic.ini upgrade head || fail "database forward migration check failed."
nohup backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --no-access-log >"$LOG_DIR/backend.log" 2>&1 &
NEW_PID=$!
printf '%s\n' "$NEW_PID" > "$RUN_DIR/backend.pid"
chmod 600 "$RUN_DIR/backend.pid" "$LOG_DIR/backend.log"
for _ in {1..45}; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/ready >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS --max-time 3 http://127.0.0.1:8000/ready >/dev/null || fail "API did not become ready. Review ignored .local/logs/backend.log."
curl -fsS --max-time 3 http://127.0.0.1:8000/api/v1/config | python3 -c 'import json,sys; d=json.load(sys.stdin); print("execution_mode="+str(d.get("execution_mode"))+" model="+str(d.get("model"))+" search_provider="+str(d.get("search_provider"))+" hosted_calls="+str(d.get("live_calls_approved")))'
echo "FastAPI restarted with PID $NEW_PID. No public search was made."
