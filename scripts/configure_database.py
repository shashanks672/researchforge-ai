"""Append a server-only URL from existing Compose settings without printing credentials."""

import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy.engine import URL

root = Path(__file__).resolve().parents[1]
path = root / ".env"
values = dotenv_values(path)
if not values.get("RF_DATABASE_URL") and not os.environ.get("RF_DATABASE_URL"):
    url = URL.create(
        "postgresql+psycopg",
        username=os.environ.get("POSTGRES_USER") or values.get("POSTGRES_USER"),
        password=os.environ.get("POSTGRES_PASSWORD") or values.get("POSTGRES_PASSWORD"),
        host="127.0.0.1",
        port=5432,
        database=os.environ.get("POSTGRES_DB") or values.get("POSTGRES_DB"),
    )
    with path.open("a") as file:
        file.write(f"\nRF_DATABASE_URL='{url.render_as_string(hide_password=False)}'\n")
    path.chmod(0o600)
    print(
        "Configured server-only RF_DATABASE_URL in ignored .env (credentials hidden)."
    )
else:
    print("Existing RF_DATABASE_URL preserved.")
