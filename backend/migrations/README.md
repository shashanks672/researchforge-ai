# Migrations

`0001_sessions` adds the research-session table, constraints and history index.
From the repository root run `backend/.venv/bin/alembic -c backend/alembic.ini upgrade head`.
Use `current`, `history` and `check` with the same configuration path to inspect state.
The URL comes from private server settings, never from this file or `alembic.ini`.

Application startup does not create tables. Migrations are additive to unrelated tables;
autogeneration excludes tables outside the application's metadata. Deliberate removal of
an application table must be written and reviewed explicitly. Do not downgrade an existing
development database to test rollback; `scripts/test_database.py` does so in a disposable DB.
