"""Homepage digest: what happened last, and what to do next.

"Last done" merges the freshest signals from all three surfaces:
git commits (code), vault note edits, and PA agent audit events.

"Next steps" collects actionable items, each carrying enough context to launch
a coding agent at the right folder with the right prompt, or review the source.
"""
from __future__ import annotations

import code_projects
import pa
import secondbrain
from config import VAULT
from util import parse_iso, rel_time
from vault import list_projects, scan_vault_files

PRIORITY_ORDER = {"High Impact": 0, "High Leverage": 1, "User Value": 2}


def _note_summary(note: dict) -> str:
    """Hover summary for a vault note: what state it's in and what's next."""
    from vault import note_preview
    fm = note["fm"]
    bits = []
    if fm.get("stage") or fm.get("status"):
        bits.append(f"now: {fm.get('stage', '')}/{fm.get('status', '')}".rstrip("/"))
    if fm.get("decision"):
        bits.append(f"decision: {fm['decision']}")
    if fm.get("next_action"):
        bits.append(f"next: {fm['next_action']}")
    try:
        snippet = note_preview(note["path"], snippet_len=220)["snippet"]
        if snippet:
            bits.append(snippet)
    except Exception:
        pass
    return " — ".join(bits)


def _pa_event_summary(e: dict) -> str:
    """Hover summary for a PA audit event, built from its payload."""
    p = e.get("payload") or {}
    action = e.get("action", "")
    if action == "draft_approved":
        return f"approved text: “{(p.get('approved_text') or '')[:180]}…”"
    if action == "draft_rejected":
        return f"reason: {p.get('reason') or '(none given)'}"
    if action == "draft_redrafted":
        return f"instructions: {p.get('instructions', '')} → new v{p.get('new_version', '?')}"
    if action == "clarification_answered":
        return f"Q: {p.get('question', '')} — A: {p.get('answer', '')}"
    if action == "task_created":
        return p.get("user_request", "")
    return ", ".join(f"{k}: {str(v)[:60]}" for k, v in list(p.items())[:3])


def last_done(limit: int = 7) -> list[dict]:
    events: list[dict] = []

    for c in code_projects.recent_commits(3)[:6]:
        events.append({
            "kind": "commit",
            "title": c["message"],
            "detail": f"committed in {c['repo']}",
            "summary": c.get("summary", ""),
            "time_iso": c["time_iso"], "time_str": c["time_str"],
        })

    for note in scan_vault_files()[:10]:
        is_note = note.get("ext") == ".md"
        events.append({
            "kind": "vault" if is_note else "file",
            "title": note["title"],
            "detail": f"{'vault note' if is_note else 'vault file'} updated · {note['path']}",
            "summary": _note_summary(note) if is_note else f"modified file: {note['path']}",
            "path": note["path"],
            "time_iso": note["mtime_iso"], "time_str": note["time_str"],
        })

    for e in pa.recent_audit_events(5, with_payload=True):
        dt = parse_iso(e.get("created_at", ""))
        events.append({
            "kind": "agent",
            "title": e["action"].replace("_", " ").capitalize(),
            "detail": (e.get("user_request") or "")[:90],
            "summary": _pa_event_summary(e),
            "time_iso": dt.isoformat() if dt else "", "time_str": rel_time(dt),
        })

    for c in secondbrain.recent_captures(3):
        dt = parse_iso(c.get("processed_at", ""))
        events.append({
            "kind": "capture",
            "title": f"Captured: {c['output'] or c['name']}",
            "detail": "second brain pipeline",
            "summary": f"source: {c['name']} → note: {c['output']}",
            "time_iso": dt.isoformat() if dt else "", "time_str": c["time_str"],
        })

    events.sort(key=lambda ev: ev["time_iso"] or "", reverse=True)
    return events[:limit]


def next_steps() -> list[dict]:
    steps: list[dict] = []

    # 1. PA agent work waiting on the human
    pa_sum = pa.summary()
    if pa_sum["available"] and (pa_sum["pending_approvals"] or pa_sum["pending_clarifications"]):
        n_a, n_c = pa_sum["pending_approvals"], pa_sum["pending_clarifications"]
        parts = []
        if n_a:
            parts.append(f"{n_a} draft{'s' if n_a != 1 else ''} awaiting approval")
        if n_c:
            parts.append(f"{n_c} clarification{'s' if n_c != 1 else ''} pending")
        steps.append({
            "kind": "pa",
            "title": "Review PA agent drafts",
            "detail": " · ".join(parts),
            "priority": "High Impact",
            "review": {"view": "agents"},
            "action": None,  # reviewing happens in the Agents tab, not via a coding agent
        })

    # 2. Ideas sitting at the approval gate (orchestrator loop: decision still open)
    undecided = [p for p in list_projects()
                 if p["folder"] == "Ideas" and p["decision"] in ("undecided", "")
                 and p["status"] == "active"]
    for p in undecided[:3]:
        steps.append({
            "kind": "idea",
            "title": f"Decide: {p['title']}",
            "detail": "idea awaiting build / park / drop decision",
            "priority": p["priority_tag"] or "",
            "review": {"obsidian": p["path"]},
            "action": {
                "path": str(VAULT / p["path"].replace("/", "\\")),
                "prompt": f"Review the project idea note '{p['title']}' at {p['path']} in my Obsidian vault. "
                          f"Help me pressure-test it and reach a build/park/drop decision.",
            },
        })

    # 3. Projects with an explicit next_action
    with_action = [p for p in list_projects() if p["next_action"]]
    with_action.sort(key=lambda p: PRIORITY_ORDER.get(p["priority_tag"], 3))
    for p in with_action:
        steps.append({
            "kind": "project",
            "title": p["title"],
            "detail": p["next_action"],
            "priority": p["priority_tag"] or "",
            "review": {"obsidian": p["path"]},
            "action": {
                "path": str(VAULT / p["path"].replace("/", "\\")),
                "prompt": f"Project '{p['title']}': the next action is — {p['next_action']}. "
                          f"The project note is at {p['path']} in my Obsidian vault. Let's do it.",
            },
        })

    # 4. Repos with uncommitted work
    for r in code_projects.list_repos():
        if r["is_git"] and r["dirty"] > 10:
            steps.append({
                "kind": "repo",
                "title": f"Uncommitted work in {r['name']}",
                "detail": f"{r['dirty']} changed files — review and commit or discard",
                "priority": "",
                "review": {"github": r["github_url"]} if r["github_url"] else {},
                "action": {
                    "path": r["path"],
                    "prompt": f"The repo {r['name']} has {r['dirty']} uncommitted changed files. "
                              f"Review the diff and help me commit the work in sensible chunks.",
                },
            })

    return steps[:8]


def digest() -> dict:
    return {"last_done": last_done(), "next_steps": next_steps()}
