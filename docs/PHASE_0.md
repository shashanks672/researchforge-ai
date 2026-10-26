# Phase 0 learning guide

## What we built and why

The API and dashboard are independent programs. FastAPI is the validated Python HTTP
boundary. Next.js serves the workspace and proxies a fixed health request so backend
configuration stays server-side. There is no research engine or persistence yet.
The connection card is a small real integration to prove the programs communicate.

`backend/app/main.py` constructs the API and middleware. `core/config.py` validates
environment settings. `api/system.py` implements liveness and public capabilities.
`schemas/research.py` defines a first research request contract without executing it.
`frontend/src/app/page.tsx` is the workspace shell. `components/system-check.tsx` handles
loading, success, failure and retry. `app/api/system/route.ts` and `lib/system.ts` are the
server proxy. Tests exercise boundaries rather than making paid network calls.

`backend/uv.lock` and `frontend/package-lock.json` record the resolved dependency graph.
`pyproject.toml` and `package.json` describe intended direct dependencies and commands.
Ruff/Prettier enforce formatting, mypy/TypeScript catch type mistakes, and Pytest/Vitest
exercise behavior. Playwright drives a real browser against both running services.

## Run and inspect

From the repository root:

```bash
bash scripts/bootstrap.sh
```

In terminal 1:

```bash
cd /path/to/researchforge-ai
backend/.venv/bin/python -m uvicorn app.main:app --app-dir backend --reload --reload-dir backend/app --host 127.0.0.1 --port 8000 --no-access-log
```

In terminal 2:

```bash
cd /path/to/researchforge-ai/frontend
npm run dev
```

Expected: Uvicorn reports application startup complete on port 8000; Next.js reports
ready on port 3000. Open <http://127.0.0.1:3000>. The connection card should change from
“Checking backend…” to “Backend connected”. This checks the API, not a database or model.
The research composer is disabled and explains which phases enable it.

Open <http://127.0.0.1:8000/docs> to inspect interactive API documentation. Try `/health`
and `/api/v1/config`; neither needs a key. In browser developer tools, inspect the
request to `/api/system`. Stop the backend with Ctrl+C and use “Check connection” to
observe the honest offline state; restart it and retry.

## Test

```bash
cd /path/to/researchforge-ai
bash scripts/check.sh
cd frontend
npm run test:e2e
```

Run the first command before browser tests because the latter starts the production
frontend build. Browser tests start and stop both servers when the ports are free.
Close development servers first to ensure the production build is what gets tested.
Tests use installed Google Chrome locally, avoiding a browser download. If Chrome is
unavailable, use `npx playwright install chromium`, then
`PLAYWRIGHT_CHANNEL=chromium npm run test:e2e`. This is an optional sizable download.
CI uses that Chromium path. No research provider calls occur in these tests.

## Common errors

| Symptom | Root cause and fix |
| --- | --- |
| `python3.12: command not found` | Install Python 3.12 or select its installed Homebrew path. Do not use the default 3.14 for this project. |
| `code: command not found` | Open VS Code manually → File → Open Folder. The `code` shell launcher is optional. |
| `ModuleNotFoundError: app` | Run the documented command from the root with `--app-dir backend`. |
| “Backend offline” | Start Uvicorn; check `curl http://127.0.0.1:8000/health`. Verify `frontend/.env.local` has the local URL and restart Next.js after changing it. |
| Address already in use | Stop the old process in its terminal. Do not kill unrelated processes; inspect `lsof -i :8000` or `lsof -i :3000`. |
| Invalid CORS settings | Use a JSON array of exact local origins, without trailing slashes or wildcards. |
| Playwright missing executable | Install Chrome, or explicitly install Playwright Chromium with the command above. |
| Package downloads fail | Check network access and disk space; rerun bootstrap. Never work around certificate errors by disabling verification. |
| Format check fails | Run `backend/.venv/bin/ruff format backend` and `(cd frontend && npm run format)`, then rerun checks. |

## VS Code

Open `/path/to/researchforge-ai` using File → Open Folder. The shell
launcher `code .` is optional and was not detected during inspection. Accept the listed
extension recommendations if desired. Use Python: Select Interpreter and select
`backend/.venv/bin/python`; choose the workspace TypeScript version. Open two integrated
terminals for the commands above. Do not install application dependencies globally.

## Complete versus future work

See `IMPLEMENTATION_LOG.md` for executed commands and measured outcomes. Phase 0 tests
do not validate PostgreSQL, Qdrant, LLM quality, live search, ingestion or a research run.
Those systems have no implementation yet. CI configuration exists but a hosted CI run
requires a GitHub repository and push, which has not been authorized or performed.

Next: Phase 1 adds SQLAlchemy/Alembic, PostgreSQL readiness, persistent research request
creation and history, and a functioning submission form. It still must not pretend to
perform web research before a real provider workflow exists in Phase 2.
