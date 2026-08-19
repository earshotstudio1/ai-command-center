"""Shared helpers: time formatting and frontmatter parsing."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import yaml


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso(value: str) -> datetime | None:
    """Parse an ISO timestamp (with or without timezone) to an aware UTC datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def from_mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def rel_time(dt: datetime | None) -> str:
    if dt is None:
        return "unknown"
    seconds = (now_utc() - dt).total_seconds()
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def display_name(path: Path) -> str:
    return path.stem.replace("-", " ").replace("_", " ").title()


def parse_frontmatter(path: Path) -> tuple[dict, str]:
    """Return (frontmatter, body). Tolerates missing/malformed frontmatter."""
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except Exception:
        return {}, ""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1])
        if not isinstance(fm, dict):
            fm = {}
        return fm, parts[2].strip()
    except Exception:
        return {}, text
