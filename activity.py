"""Unified activity feed: vault note changes + PA agent audit trail + captures."""
from __future__ import annotations

import pa
import secondbrain
from util import parse_iso, rel_time
from vault import scan_project_notes

ACTION_LABELS = {
    "task_created": "Task created",
    "clarification_answered": "Clarification answered",
    "draft_approved": "Draft approved",
    "draft_rejected": "Draft rejected",
    "draft_redrafted": "Draft redrafted",
}


def unified_feed(limit: int = 40) -> list[dict]:
    events: list[dict] = []

    for note in scan_project_notes()[:30]:
        events.append({
            "kind": "vault",
            "title": note["title"],
            "detail": note["path"],
            "path": note["path"],
            "time_iso": note["mtime_iso"],
            "time_str": note["time_str"],
        })

    for e in pa.recent_audit_events(30):
        dt = parse_iso(e.get("created_at", ""))
        request = (e.get("user_request") or "")[:80]
        label = ACTION_LABELS.get(e["action"], e["action"].replace("_", " ").capitalize())
        actor = e.get("actor", "")
        events.append({
            "kind": "pa",
            "title": f"{label}" + (f" · {actor}" if actor not in ("", "system") else ""),
            "detail": request,
            "path": None,
            "time_iso": dt.isoformat() if dt else "",
            "time_str": rel_time(dt),
        })

    for c in secondbrain.recent_captures(20):
        dt = parse_iso(c.get("processed_at", ""))
        events.append({
            "kind": "capture",
            "title": f"Processed: {c['output'] or c['name']}",
            "detail": c["name"],
            "path": None,
            "time_iso": dt.isoformat() if dt else "",
            "time_str": c["time_str"],
        })

    events.sort(key=lambda ev: ev["time_iso"] or "", reverse=True)
    return events[:limit]
