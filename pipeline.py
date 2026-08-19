"""Orchestrator pipeline view.

The AI Project Orchestrator isn't built yet, but its lifecycle state already
lives in vault frontmatter (stage / decision / status) and folder placement.
This module projects that state onto the orchestrator's lifecycle columns so
the dashboard is the orchestrator's cockpit from day one.
"""
from __future__ import annotations

from vault import list_projects

COLUMNS = [
    ("captured",   "Captured",    "New ideas awaiting triage"),
    ("developing", "Developing",  "Being researched / pressure-tested"),
    ("building",   "Building",    "Promoted — actively being built"),
    ("paused",     "Paused",      "On hold or backlog"),
    ("shipped",    "Shipped",     "Done and in maintenance"),
]


def _column_for(project: dict) -> str:
    status = (project.get("status") or "").lower()
    stage = (project.get("stage") or "").lower()
    folder = (project.get("folder") or "").lower()
    if status in ("paused", "backlog") or folder in ("paused", "backlog"):
        return "paused"
    if status == "shipped" or stage == "shipped" or folder == "shipped":
        return "shipped"
    if folder == "active" or status == "active" and stage == "active":
        return "building"
    if stage == "building":
        return "building"
    if stage in ("developing", "researching", "planning"):
        return "developing"
    return "captured"


def pipeline_board() -> dict:
    columns = {key: {"key": key, "label": label, "hint": hint, "cards": []}
               for key, label, hint in COLUMNS}
    for p in list_projects():
        col = _column_for(p)
        # "live" = committed to build (or beyond); "idea" = still germinating in
        # the orchestrator's background loops until it reaches a decision
        is_live = (p["decision"] == "build"
                   or p["stage"] in ("building", "shipped")
                   or p["folder"] in ("Active", "Shipped"))
        columns[col]["cards"].append({
            "source": "live" if is_live else "idea",
            "title": p["title"],
            "path": p["path"],
            "status": p["status"],
            "stage": p["stage"],
            "decision": p["decision"],
            "area": p["area"],
            "next_action": p["next_action"],
            "priority_tag": p["priority_tag"],
            "time_str": p["time_str"],
            "mtime_iso": p["mtime_iso"],
        })
    for col in columns.values():
        col["cards"].sort(key=lambda c: c["mtime_iso"], reverse=True)
        col["count"] = len(col["cards"])
    return {"columns": [columns[key] for key, _, _ in COLUMNS]}
