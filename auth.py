"""Local dashboard auth.

This is a single-user, localhost-only Flask app, so this is belt-and-braces
rather than a real auth system: a random per-install token gates every
state-changing endpoint, and the token never leaves the machine (it lives in
a gitignored local file and is only ever sent in a request header from the
page itself).
"""
from __future__ import annotations

import secrets
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOKEN_FILE = _HERE / ".dashboard_token"

TOKEN_HEADER = "X-Dashboard-Token"


def load_or_create_token() -> str:
    if _TOKEN_FILE.exists():
        token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    _TOKEN_FILE.write_text(token, encoding="utf-8")
    return token


DASHBOARD_TOKEN = load_or_create_token()


def token_matches(supplied: str | None) -> bool:
    return secrets.compare_digest(supplied or "", DASHBOARD_TOKEN)
