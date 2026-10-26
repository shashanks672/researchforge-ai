#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x backend/.venv/bin/python ]]; then
  echo 'The project Python environment is missing. Run the documented bootstrap first.' >&2
  exit 1
fi

backend/.venv/bin/python - <<'PY'
from getpass import getpass
import os
from pathlib import Path
import sys
import tempfile

from app.core.config import Settings

try:
    # Refuse getpass's insecure stdin fallback if this is not an interactive terminal.
    tty_fd = os.open("/dev/tty", os.O_RDWR)
    os.close(tty_fd)
    contact = getpass("Enter email, mailto email, or HTTPS contact page (hidden): ").strip()
    if not contact:
        print("No contact entered; nothing was changed. Enter an email, mailto: email, or HTTPS contact page.", file=sys.stderr)
        raise SystemExit(1)
    contact = Settings.validate_public_search_contact(contact)
    directory = Path(".local")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=".contact-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            target.write(contact + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary_name, directory / "wikipedia-contact")
        os.chmod(directory / "wikipedia-contact", 0o600)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
except (ValueError, OSError) as error:
    # Validation messages are deliberately generic and never include the input.
    message = str(error)
    if "Public search contact is invalid" in message:
        print(f"Contact was not saved: {message}", file=sys.stderr)
    elif isinstance(error, OSError) and error.filename == "/dev/tty":
        print("Contact was not saved: run this command in a private interactive Mac Terminal so input stays hidden.", file=sys.stderr)
    else:
        print("Contact was not saved because local private storage could not be accessed. Nothing was printed or transmitted.", file=sys.stderr)
    raise SystemExit(1) from None
print("Private Wikimedia contact saved locally with restricted permissions.")
print("The contact is sent in Wikimedia request identification when Web search is used.")
print("No public search was performed. Restart ResearchForge to apply this setting.")
PY
