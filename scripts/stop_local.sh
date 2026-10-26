#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN_DIR="$ROOT/.local/run"
[[ -d "$RUN_DIR" ]] || { echo 'No application-managed processes are recorded.'; exit 0; }
if ! find "$RUN_DIR" -maxdepth 1 -type f -name '*.pid' -print -quit | grep -q .; then
  echo 'No application-managed processes are recorded.'
  echo 'PostgreSQL, Qdrant, and Ollama were not stopped.'
  exit 0
fi

stop_recorded() {
  name="$1" file="$RUN_DIR/$1.pid" expected="$2"
  [[ -f "$file" ]] || return 0
  pid="$(cat "$file")"
  if [[ ! "$pid" =~ ^[0-9]+$ ]] || ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$file"
    echo "$name: stale PID record removed."
    return 0
  fi
  cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1)"
  cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
  [[ "$cwd" == "$ROOT" || "$cwd" == "$ROOT/frontend" ]] && [[ "$cmd" == *"$expected"* ]] || {
    echo "$name: PID $pid no longer matches the recorded project process; left untouched."
    return 0
  }
  kill -TERM "$pid"
  for _ in {1..10}; do
    if ! kill -0 "$pid" 2>/dev/null; then rm -f "$file"; echo "$name stopped."; return 0; fi
    sleep 1
  done
  echo "$name: shutdown is still in progress for PID $pid; no force-kill was sent."
}

stop_recorded backend backend/.venv/bin/python
stop_recorded frontend node_modules/next/dist/bin/next
echo 'PostgreSQL, Qdrant, and Ollama were not stopped.'
