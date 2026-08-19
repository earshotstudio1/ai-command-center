"""Second Brain pipeline health: capture bot, processing, and vault maintenance.

Liveness is inferred from the artifacts the pipeline already writes:
- capture.log mtime          -> is the Telegram capture bot running?
- processed.jsonl            -> what has the processor turned into notes?
- maintenance_runs.jsonl     -> when did vault maintenance last run, and what did it do?
"""
from __future__ import annotations

import json
from pathlib import Path

from config import CAPTURE_LOG, SECONDBRAIN_DIR
from util import from_mtime, now_utc, parse_iso, rel_time

PROCESSED = SECONDBRAIN_DIR / "processed.jsonl"
MAINTENANCE = SECONDBRAIN_DIR / "maintenance_runs.jsonl"

LIVE_WINDOW_S = 10 * 60        # heartbeat within 10 min -> live
IDLE_WINDOW_S = 24 * 3600      # within 24h -> idle


def _tail_jsonl(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    except Exception:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    out.reverse()  # newest first
    return out


def capture_status() -> dict:
    if not CAPTURE_LOG.exists():
        return {"state": "unknown", "detail": "capture.log not found",
                "last_seen_iso": None, "time_str": "never"}
    last = from_mtime(CAPTURE_LOG)
    age = (now_utc() - last).total_seconds()
    if age < LIVE_WINDOW_S:
        state = "live"
    elif age < IDLE_WINDOW_S:
        state = "idle"
    else:
        state = "down"
    return {"state": state, "detail": f"capture.log last written {rel_time(last)}",
            "last_seen_iso": last.isoformat(), "time_str": rel_time(last)}


def recent_captures(limit: int = 20) -> list[dict]:
    out = []
    for entry in _tail_jsonl(PROCESSED, limit):
        dt = parse_iso(entry.get("processed_at", ""))
        output = entry.get("output", "")
        out.append({
            "name": entry.get("name", ""),
            "output": Path(output).name if output else "",
            "output_path": output,
            "processed_at": entry.get("processed_at", ""),
            "time_str": rel_time(dt),
        })
    return out


def maintenance_runs(limit: int = 20) -> list[dict]:
    """Run history for the Agents tab — each run is one 'task' row."""
    from config import VAULT
    out = []
    for run in _tail_jsonl(MAINTENANCE, limit):
        dt = parse_iso(run.get("run_at", ""))
        report = run.get("report_path", "")
        report_rel = ""
        if report:
            try:
                report_rel = str(Path(report).relative_to(VAULT)).replace("\\", "/")
            except ValueError:
                pass
        out.append({
            "run_at": run.get("run_at", ""),
            "time_str": rel_time(dt),
            "dry_run": bool(run.get("dry_run")),
            "scanned": run.get("scanned_count", 0),
            "issues": run.get("issue_count", 0),
            "changed": run.get("changed_count", 0),
            "duplicates": run.get("duplicate_group_count", 0),
            "report_rel": report_rel,
        })
    return out


def maintenance_status() -> dict:
    runs = _tail_jsonl(MAINTENANCE, 1)
    if not runs:
        return {"state": "unknown", "detail": "no maintenance runs recorded",
                "last_run_iso": None, "time_str": "never", "stats": {}}
    run = runs[0]
    dt = parse_iso(run.get("run_at", ""))
    age_days = (now_utc() - dt).days if dt else None
    state = "ok" if age_days is not None and age_days <= 8 else "stale"
    return {
        "state": state,
        "detail": f"last run {rel_time(dt)} — scanned {run.get('scanned_count', '?')}, "
                  f"fixed {run.get('changed_count', '?')} notes",
        "last_run_iso": dt.isoformat() if dt else None,
        "time_str": rel_time(dt),
        "stats": {k: run.get(k) for k in
                  ("scanned_count", "issue_count", "changed_count", "duplicate_group_count")},
        "report_path": run.get("report_path", ""),
    }
