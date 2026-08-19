"""Personal Assistant agent integration.

Reads open the PA SQLite database in read-only mode so the dashboard can never
corrupt agent state by accident. The two write actions (approve / reject)
replicate the PA agent's own Store semantics exactly, with actor "dashboard"
so the audit trail shows where the decision came from.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from config import PA_DB
from util import parse_iso, rel_time, now_utc


def _connect_ro() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{PA_DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_rw() -> sqlite3.Connection:
    conn = sqlite3.connect(str(PA_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _utc_now_str() -> str:
    return now_utc().isoformat()


def available() -> bool:
    return PA_DB.exists()


def summary() -> dict:
    result: dict[str, Any] = {
        "available": False, "error": None,
        "stage_counts": {}, "status_counts": {},
        "total": 0, "pending_approvals": 0, "pending_clarifications": 0,
        "last_event_iso": None, "last_event_str": "never",
    }
    if not available():
        result["error"] = "PA database not found"
        return result
    try:
        with _connect_ro() as conn:
            cur = conn.cursor()
            cur.execute("SELECT stage, COUNT(*) c FROM tasks GROUP BY stage")
            result["stage_counts"] = {r["stage"]: r["c"] for r in cur.fetchall()}
            cur.execute("SELECT status, COUNT(*) c FROM tasks GROUP BY status")
            result["status_counts"] = {r["status"]: r["c"] for r in cur.fetchall()}
            result["total"] = cur.execute("SELECT COUNT(*) c FROM tasks").fetchone()["c"]
            result["pending_approvals"] = cur.execute(
                "SELECT COUNT(*) c FROM drafts WHERE status = 'pending'").fetchone()["c"]
            result["pending_clarifications"] = cur.execute(
                "SELECT COUNT(*) c FROM clarifications WHERE answer = ''").fetchone()["c"]
            last = cur.execute(
                "SELECT created_at FROM audit_events ORDER BY event_id DESC LIMIT 1").fetchone()
            if last:
                dt = parse_iso(last["created_at"])
                result["last_event_iso"] = dt.isoformat() if dt else last["created_at"]
                result["last_event_str"] = rel_time(dt)
            result["available"] = True
    except Exception as exc:
        result["error"] = str(exc)
    return result


def list_tasks() -> list[dict]:
    if not available():
        return []
    with _connect_ro() as conn:
        rows = conn.execute(
            """
            SELECT t.task_id, t.user_request, t.status, t.stage, t.created_at, t.updated_at,
                   SUM(CASE WHEN d.status = 'pending'  THEN 1 ELSE 0 END) AS pending_drafts,
                   SUM(CASE WHEN d.status = 'approved' THEN 1 ELSE 0 END) AS approved_drafts,
                   SUM(CASE WHEN d.status = 'rejected' THEN 1 ELSE 0 END) AS rejected_drafts,
                   COUNT(d.draft_id) AS total_drafts
            FROM tasks t LEFT JOIN drafts d ON d.task_id = t.task_id
            GROUP BY t.task_id
            ORDER BY t.updated_at DESC
            """
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["updated_str"] = rel_time(parse_iso(d["updated_at"]))
        out.append(d)
    return out


def task_bundle(task_id: str) -> dict:
    with _connect_ro() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        task = dict(task)
        try:
            task["research_brief"] = json.loads(task["research_brief"] or "{}")
        except json.JSONDecodeError:
            pass
        contacts = {c["contact_id"]: dict(c) for c in conn.execute(
            "SELECT * FROM contacts WHERE task_id = ? ORDER BY name", (task_id,))}
        drafts = []
        for row in conn.execute(
                "SELECT * FROM drafts WHERE task_id = ? ORDER BY created_at", (task_id,)):
            d = dict(row)
            contact = contacts.get(d["contact_id"], {})
            d["contact_name"] = contact.get("name", "")
            d["contact_org"] = contact.get("organization", "")
            drafts.append(d)
        audit = []
        for row in conn.execute(
                "SELECT * FROM audit_events WHERE task_id = ? ORDER BY event_id", (task_id,)):
            e = dict(row)
            try:
                e["payload"] = json.loads(e.pop("payload_json") or "{}")
            except json.JSONDecodeError:
                e["payload"] = {}
            e["time_str"] = rel_time(parse_iso(e["created_at"]))
            audit.append(e)
        return {
            "task": task,
            "clarifications": [dict(r) for r in conn.execute(
                "SELECT * FROM clarifications WHERE task_id = ? ORDER BY id", (task_id,))],
            "sources": [dict(r) for r in conn.execute(
                "SELECT * FROM sources WHERE task_id = ? ORDER BY retrieved_at", (task_id,))],
            "contacts": list(contacts.values()),
            "drafts": drafts,
            "audit_events": audit,
        }


def recent_audit_events(limit: int = 30, with_payload: bool = False) -> list[dict]:
    if not available():
        return []
    try:
        with _connect_ro() as conn:
            rows = conn.execute(
                """
                SELECT a.action, a.actor, a.created_at, a.task_id, a.payload_json, t.user_request
                FROM audit_events a LEFT JOIN tasks t ON t.task_id = a.task_id
                ORDER BY a.event_id DESC LIMIT ?
                """, (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            raw = d.pop("payload_json", "")
            if with_payload:
                try:
                    d["payload"] = json.loads(raw or "{}")
                except json.JSONDecodeError:
                    d["payload"] = {}
            out.append(d)
        return out
    except Exception:
        return []


def _recompute_task_stage(conn: sqlite3.Connection, task_id: str) -> None:
    # Mirrors pa_agent.db.Store.recompute_task_stage
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM drafts WHERE task_id = ? GROUP BY status",
        (task_id,)).fetchall()
    counts = {r["status"]: r["count"] for r in rows}
    if not counts:
        return
    if counts.get("pending", 0) > 0:
        stage = "awaiting_approval"
    elif counts.get("approved", 0) > 0:
        stage = "manual_send_ready"
    else:
        stage = "closed_no_send"
    conn.execute("UPDATE tasks SET stage = ?, updated_at = ? WHERE task_id = ?",
                 (stage, _utc_now_str(), task_id))


def _add_audit_event(conn: sqlite3.Connection, task_id: str, draft_id: str,
                     action: str, payload: dict) -> None:
    conn.execute(
        """
        INSERT INTO audit_events (task_id, draft_id, action, actor, payload_json, created_at)
        VALUES (?, ?, ?, 'dashboard', ?, ?)
        """,
        (task_id, draft_id, action, json.dumps(payload, ensure_ascii=False), _utc_now_str()),
    )


def approve_draft(draft_id: str) -> dict:
    with _connect_rw() as conn:
        draft = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        if draft["status"] == "approved":
            raise ValueError("Draft is already approved")
        conn.execute(
            "UPDATE drafts SET status = 'approved', approved_text = text, updated_at = ? WHERE draft_id = ?",
            (_utc_now_str(), draft_id))
        _add_audit_event(conn, draft["task_id"], draft_id, "draft_approved", {
            "recipient": draft["contact_id"],
            "channel": draft["channel"],
            "approved_text": draft["text"],
        })
        _recompute_task_stage(conn, draft["task_id"])
        conn.commit()
        return dict(conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone())


def reject_draft(draft_id: str, reason: str = "") -> dict:
    with _connect_rw() as conn:
        draft = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
        if draft is None:
            raise ValueError(f"Draft not found: {draft_id}")
        if draft["status"] == "approved":
            raise ValueError("Approved drafts cannot be rejected from the dashboard")
        conn.execute("UPDATE drafts SET status = 'rejected', updated_at = ? WHERE draft_id = ?",
                     (_utc_now_str(), draft_id))
        _add_audit_event(conn, draft["task_id"], draft_id, "draft_rejected", {"reason": reason})
        _recompute_task_stage(conn, draft["task_id"])
        conn.commit()
        return dict(conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone())
