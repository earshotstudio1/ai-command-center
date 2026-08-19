"""AI Command Center v2 — local dashboard for the personal AI infrastructure.

Run:  python app.py   (or start.bat)
URL:  http://127.0.0.1:5150
"""
from __future__ import annotations

from functools import wraps

from flask import Flask, jsonify, render_template, request

import activity
import code_projects
import graph
import home
import launcher
import pa
import pipeline
import secondbrain
import vault
from config import ENABLE_ACTIONS, PA_DB, PORT, VAULT, VAULT_NAME

app = Flask(__name__)


def api(fn):
    """Uniform JSON error handling for API routes."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return jsonify(fn(*args, **kwargs))
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500
    return wrapper


def require_actions():
    if not ENABLE_ACTIONS:
        raise ValueError("Actions are disabled in config.json (enable_actions)")


@app.route("/")
def index():
    return render_template("index.html", vault_name=VAULT_NAME,
                           actions_enabled=ENABLE_ACTIONS)


@app.route("/api/summary")
@api
def api_summary():
    projects = vault.list_projects()
    inbox = vault.list_inbox()
    pa_sum = pa.summary()
    capture = secondbrain.capture_status()
    maintenance = secondbrain.maintenance_status()
    return {
        "projects_total": len(projects),
        "projects_active": sum(1 for p in projects if p["status"] == "active"),
        "inbox_count": len(inbox),
        "needs_you": pa_sum["pending_approvals"] + pa_sum["pending_clarifications"],
        "agents": {
            "pa": {"state": "ok" if pa_sum["available"] else "down",
                   "pending_approvals": pa_sum["pending_approvals"],
                   "pending_clarifications": pa_sum["pending_clarifications"]},
            "capture": {"state": capture["state"]},
            "maintenance": {"state": maintenance["state"]},
            "orchestrator": {"state": "planned"},
        },
        "actions_enabled": ENABLE_ACTIONS,
    }


@app.route("/api/projects")
@api
def api_projects():
    return vault.list_projects()


@app.route("/api/inbox")
@api
def api_inbox():
    return vault.list_inbox()


@app.route("/api/inbox/archive", methods=["POST"])
@api
def api_inbox_archive():
    require_actions()
    payload = request.get_json(force=True, silent=True) or {}
    filename = payload.get("file", "")
    if not filename:
        raise ValueError("Missing 'file' in request body")
    return vault.archive_inbox_item(filename)


@app.route("/api/pipeline")
@api
def api_pipeline():
    return pipeline.pipeline_board()


@app.route("/api/agents")
@api
def api_agents():
    pa_sum = pa.summary()
    return {
        "pa": pa_sum,
        "capture": secondbrain.capture_status(),
        "maintenance": secondbrain.maintenance_status(),
        "orchestrator": {
            "state": "planned",
            "detail": "Not built yet — pipeline view models its lifecycle from vault frontmatter",
            "needs_building": [
                "Triage cron (inbox classification)",
                "Research agent (idea → proposed plan)",
                "Deep review layer (pressure-test plans)",
                "/promote-project workflow",
                "TDD gate skill",
                "PM agent interface (Telegram)",
                "Maintenance mode",
            ],
        },
    }


@app.route("/api/pa/tasks")
@api
def api_pa_tasks():
    return pa.list_tasks()


@app.route("/api/pa/task/<task_id>")
@api
def api_pa_task(task_id: str):
    return pa.task_bundle(task_id)


@app.route("/api/pa/draft/<draft_id>/approve", methods=["POST"])
@api
def api_pa_approve(draft_id: str):
    require_actions()
    return pa.approve_draft(draft_id)


@app.route("/api/pa/draft/<draft_id>/reject", methods=["POST"])
@api
def api_pa_reject(draft_id: str):
    require_actions()
    payload = request.get_json(force=True, silent=True) or {}
    return pa.reject_draft(draft_id, payload.get("reason", ""))


@app.route("/api/home")
@api
def api_home():
    return home.digest()


@app.route("/api/graph")
@api
def api_graph():
    return graph.build_graph()


@app.route("/api/code")
@api
def api_code():
    return code_projects.list_repos()


@app.route("/api/tools")
@api
def api_tools():
    return launcher.available_tools()


@app.route("/api/launch", methods=["POST"])
@api
def api_launch():
    require_actions()
    payload = request.get_json(force=True, silent=True) or {}
    tool = payload.get("tool", "")
    path = payload.get("path", "")
    if not tool or not path:
        raise ValueError("Missing 'tool' or 'path' in request body")
    return launcher.launch(tool, path, payload.get("prompt", ""))


@app.route("/api/captures")
@api
def api_captures():
    return secondbrain.recent_captures(30)


@app.route("/api/maintenance/runs")
@api
def api_maintenance_runs():
    return secondbrain.maintenance_runs(20)


@app.route("/api/note")
@api
def api_note():
    rel = request.args.get("path", "")
    if not rel:
        raise ValueError("Missing 'path' query parameter")
    return vault.note_preview(rel)


@app.route("/api/project/pause", methods=["POST"])
@api
def api_project_pause():
    require_actions()
    payload = request.get_json(force=True, silent=True) or {}
    rel = payload.get("path", "")
    if not rel:
        raise ValueError("Missing 'path' in request body")
    return vault.pause_project(rel)


@app.route("/api/project/unpause", methods=["POST"])
@api
def api_project_unpause():
    require_actions()
    payload = request.get_json(force=True, silent=True) or {}
    rel = payload.get("path", "")
    if not rel:
        raise ValueError("Missing 'path' in request body")
    return vault.unpause_project(rel)


@app.route("/api/activity")
@api
def api_activity():
    return activity.unified_feed()


@app.route("/api/health")
@api
def api_health():
    return vault.folder_health()


if __name__ == "__main__":
    print(f"\n{'=' * 56}")
    print(f"  AI COMMAND CENTER v2  --  http://127.0.0.1:{PORT}")
    print(f"  Vault:   {VAULT}  (exists: {VAULT.exists()})")
    print(f"  PA DB:   {PA_DB}  (exists: {PA_DB.exists()})")
    print(f"  Actions: {'enabled' if ENABLE_ACTIONS else 'disabled'}")
    print(f"{'=' * 56}\n")
    app.run(debug=False, port=PORT, host="127.0.0.1")
