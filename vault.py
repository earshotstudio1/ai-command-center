"""Vault access: cached scans, inbox, folder health, and the archive action."""
from __future__ import annotations

import os
import time
from pathlib import Path

from config import CACHE_TTL, VAULT
from util import display_name, from_mtime, parse_frontmatter, rel_time

PROJECTS_DIR = VAULT / "Projects"
INBOX_DIR = VAULT / "Inbox"
ARCHIVE_DIR = INBOX_DIR / "Archive"

# Directories never descended into during scans
SKIP_DIRS = {".venv", "venv", "__pycache__", "node_modules", ".git", ".obsidian",
             ".second-brain", ".pytest_cache", ".stfolder", "static", "templates"}

_cache: dict[str, tuple[float, object]] = {}


def _cached(key: str, builder):
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    value = builder()
    _cache[key] = (time.monotonic() + CACHE_TTL, value)
    return value


def _walk_md(root: Path):
    """Yield .md paths under root, pruning noisy directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(".md"):
                yield Path(dirpath) / name


def scan_project_notes() -> list[dict]:
    """Every markdown note under Projects/ with parsed frontmatter (cached)."""
    def build():
        notes = []
        if not PROJECTS_DIR.exists():
            return notes
        for md in _walk_md(PROJECTS_DIR):
            try:
                mtime = from_mtime(md)
            except OSError:
                continue
            fm, _ = parse_frontmatter(md)
            rel = str(md.relative_to(VAULT)).replace("\\", "/")
            notes.append({
                "path": rel,
                "title": fm.get("title") or display_name(md),
                "fm": fm,
                "mtime_iso": mtime.isoformat(),
                "time_str": rel_time(mtime),
                "folder": rel.split("/")[1] if "/" in rel else "",
            })
        notes.sort(key=lambda n: n["mtime_iso"], reverse=True)
        return notes
    return _cached("project_notes", build)


def scan_vault_notes() -> list[dict]:
    """Every markdown note in the vault, newest first."""
    def build():
        notes = []
        for md in _walk_md(VAULT):
            try:
                mtime = from_mtime(md)
                fm, _ = parse_frontmatter(md)
                rel = str(md.relative_to(VAULT)).replace("\\", "/")
            except OSError:
                continue
            notes.append({
                "path": rel,
                "title": fm.get("title") or display_name(md),
                "fm": fm,
                "mtime_iso": mtime.isoformat(),
                "time_str": rel_time(mtime),
                "folder": rel.split("/")[0] if "/" in rel else "",
            })
        notes.sort(key=lambda n: n["mtime_iso"], reverse=True)
        return notes
    return _cached("vault_notes", build)


def scan_vault_files() -> list[dict]:
    """Recent files in the vault, excluding noisy generated folders."""
    def build():
        files = []
        for dirpath, dirnames, filenames in os.walk(VAULT):
            dirnames[:] = [d for d in dirnames
                           if d not in SKIP_DIRS and not d.startswith(".")]
            for name in filenames:
                path = Path(dirpath) / name
                if path.suffix in (".pyc", ".sqlite3", ".db"):
                    continue
                try:
                    mtime = from_mtime(path)
                    rel = str(path.relative_to(VAULT)).replace("\\", "/")
                except OSError:
                    continue
                fm = {}
                if path.suffix == ".md":
                    fm, _ = parse_frontmatter(path)
                files.append({
                    "path": rel,
                    "title": fm.get("title") or display_name(path),
                    "fm": fm,
                    "mtime_iso": mtime.isoformat(),
                    "time_str": rel_time(mtime),
                    "folder": rel.split("/")[0] if "/" in rel else "",
                    "ext": path.suffix,
                })
        files.sort(key=lambda n: n["mtime_iso"], reverse=True)
        return files
    return _cached("vault_files", build)


def is_project(note: dict) -> bool:
    fm = note["fm"]
    return fm.get("domain") == "project" or fm.get("type") in ("project-idea", "project")


def _promoted_target_exists(promoted_to: str) -> bool:
    if not promoted_to:
        return False
    rel = promoted_to.strip().strip("'\"").replace("\\", "/")
    target = VAULT / rel
    return (target.exists()
            or target.with_suffix(".md").exists()
            or (target / "README.md").exists()
            or (target / "PROGRESS.md").exists())


def _project_row(note: dict, *, title: str | None = None, path: str | None = None,
                 mtime_iso: str | None = None, time_str: str | None = None,
                 fm_updates: dict | None = None) -> dict:
    fm = dict(note["fm"])
    if fm_updates:
        fm.update({k: v for k, v in fm_updates.items() if v not in (None, "")})
    return {
        "title": title or note["title"],
        "path": path or note["path"],
        "folder": note["path"].split("/")[1] if "/" in note["path"] else "",
        "stage": fm.get("stage", ""),
        "status": fm.get("status", note["path"].split("/")[1].lower().rstrip("s") if "/" in note["path"] else "idea"),
        "decision": fm.get("decision", ""),
        "area": fm.get("area", ""),
        "tags": list(fm.get("tags") or []),
        "next_action": fm.get("next_action", ""),
        "priority_tag": fm.get("priority_tag", ""),
        "updated": str(fm.get("updated", "")),
        "mtime_iso": mtime_iso or note["mtime_iso"],
        "time_str": time_str or note["time_str"],
    }


def list_projects() -> list[dict]:
    """Canonical project records for dashboard cards.

    Active project folders often contain README, PROGRESS, DESIGN and FEEDBACK notes.
    Those are one project, not four pipeline cards. Promoted idea notes are also kept in
    Ideas for traceability, so hide them when their Active project exists.
    """
    active: dict[str, dict] = {}
    ideas: list[dict] = []

    def group_for(name: str) -> dict:
        return active.setdefault(name, {"base": None, "progress": None, "latest": None})

    for note in scan_project_notes():
        if not is_project(note):
            continue
        fm = note["fm"]
        parts = note["path"].split("/")
        if len(parts) < 2 or parts[0] != "Projects":
            continue

        if parts[1] == "Ideas":
            if _promoted_target_exists(str(fm.get("promoted_to", ""))):
                continue
            ideas.append(_project_row(note))
            continue

        if parts[1] != "Active":
            continue

        if len(parts) >= 3 and parts[2] == "Personal Assistant Agent Tasks":
            continue
        if fm.get("type") == "pa-agent-task":
            continue

        group_name = Path(parts[2]).stem if len(parts) == 3 and parts[2].endswith(".md") else parts[2]
        group = group_for(group_name)
        if group["latest"] is None or note["mtime_iso"] > group["latest"]["mtime_iso"]:
            group["latest"] = note

        if len(parts) == 3 and parts[2].endswith(".md"):
            group["base"] = note
        elif len(parts) >= 4 and parts[3] == "README.md":
            group["base"] = note
        elif len(parts) >= 4 and parts[3] == "PROGRESS.md":
            group["progress"] = note

    out = []
    for group in active.values():
        base = group["base"] or group["progress"]
        if not base:
            continue
        progress = group["progress"]
        latest = group["latest"] or base
        fm_updates = {}
        path = base["path"]
        if progress:
            pfm = progress["fm"]
            fm_updates = {
                "next_action": pfm.get("next_action"),
                "status": pfm.get("status"),
                "stage": pfm.get("stage"),
            }
            path = progress["path"]
        title = base["title"].replace(" - Progress", "").replace(" — Progress", "")
        out.append(_project_row(base, title=title, path=path,
                                mtime_iso=latest["mtime_iso"],
                                time_str=latest["time_str"],
                                fm_updates=fm_updates))
    out.extend(ideas)
    out.sort(key=lambda p: p["mtime_iso"], reverse=True)
    return out


def list_inbox() -> list[dict]:
    def build():
        items = []
        if not INBOX_DIR.exists():
            return items
        for f in INBOX_DIR.iterdir():
            if not f.is_file() or f.suffix not in (".md", ".txt"):
                continue
            mtime = from_mtime(f)
            fm, body = ({}, "")
            if f.suffix == ".md":
                fm, body = parse_frontmatter(f)
            else:
                try:
                    body = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    body = ""
            title = fm.get("title") or display_name(f)
            if f.suffix == ".txt" and title.lower().startswith(("notes ", "app ideas")):
                title = "Voice Note"
            snippet = " ".join(body.split())[:180]
            items.append({
                "file": f.name,
                "title": title,
                "snippet": snippet,
                "tags": list(fm.get("tags") or []),
                "type": fm.get("type", ""),
                "ext": f.suffix,
                "mtime_iso": mtime.isoformat(),
                "time_str": rel_time(mtime),
            })
        items.sort(key=lambda i: i["mtime_iso"], reverse=True)
        return items
    return _cached("inbox", build)


def archive_inbox_item(filename: str) -> dict:
    """Move an inbox file into Inbox/Archive. Reversible by moving it back."""
    target = (INBOX_DIR / filename).resolve()
    if target.parent != INBOX_DIR.resolve():
        raise ValueError("File is not directly inside the Inbox folder")
    if not target.exists() or target.suffix not in (".md", ".txt"):
        raise ValueError(f"Not an archivable inbox file: {filename}")
    ARCHIVE_DIR.mkdir(exist_ok=True)
    dest = ARCHIVE_DIR / target.name
    if dest.exists():
        stem, suffix = dest.stem, dest.suffix
        dest = ARCHIVE_DIR / f"{stem}-{int(time.time())}{suffix}"
    target.rename(dest)
    _cache.pop("inbox", None)
    return {"archived": filename, "to": str(dest.relative_to(VAULT)).replace("\\", "/")}


def note_preview(rel_path: str, snippet_len: int = 400) -> dict:
    """Frontmatter + body snippet for one vault note (for drawers/popovers)."""
    target = (VAULT / rel_path).resolve()
    try:
        target.relative_to(VAULT.resolve())
    except ValueError:
        raise ValueError("Path is outside the vault")
    if not target.exists() or target.suffix != ".md":
        raise ValueError(f"Not a vault note: {rel_path}")
    fm, body = parse_frontmatter(target)
    # Drop markdown noise so the snippet reads like prose
    lines = [ln.strip() for ln in body.splitlines()
             if ln.strip() and not ln.strip().startswith(("#", "|", "```", "---"))]
    snippet = " ".join(" ".join(lines).split())[:snippet_len]
    return {
        "path": rel_path,
        "title": fm.get("title") or display_name(target),
        "stage": fm.get("stage", ""),
        "status": fm.get("status", ""),
        "decision": fm.get("decision", ""),
        "next_action": fm.get("next_action", ""),
        "paused_from_status": fm.get("paused_from_status", ""),
        "tags": list(fm.get("tags") or []),
        "snippet": snippet,
        "time_str": rel_time(from_mtime(target)),
    }


def update_frontmatter(rel_path: str, updates: dict, remove: list[str] = ()) -> dict:
    """Read-modify-write a note's frontmatter, preserving the body verbatim.

    Only key order is preserved (these notes are machine-generated and carry no
    frontmatter comments). The scan caches are invalidated so the change shows
    up on the next refresh.
    """
    import yaml

    target = (VAULT / rel_path).resolve()
    try:
        target.relative_to(VAULT.resolve())
    except ValueError:
        raise ValueError("Path is outside the vault")
    if not target.exists() or target.suffix != ".md":
        raise ValueError(f"Not a vault note: {rel_path}")

    text = target.read_text(encoding="utf-8-sig")
    if not text.startswith("---"):
        raise ValueError("Note has no frontmatter to update")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Note has malformed frontmatter")
    fm = yaml.safe_load(parts[1])
    if not isinstance(fm, dict):
        raise ValueError("Note frontmatter is not a mapping")

    fm.update(updates)
    for key in remove:
        fm.pop(key, None)

    fm_text = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True,
                             default_flow_style=False)
    target.write_text(f"---\n{fm_text}---{parts[2]}", encoding="utf-8")
    _cache.clear()
    return fm


def pause_project(rel_path: str) -> dict:
    preview = note_preview(rel_path)
    if preview["status"] == "paused":
        raise ValueError("Project is already paused")
    fm = update_frontmatter(rel_path, {
        "paused_from_status": preview["status"] or "active",
        "status": "paused",
    })
    return {"paused": rel_path, "status": fm["status"],
            "was": fm["paused_from_status"]}


def unpause_project(rel_path: str) -> dict:
    preview = note_preview(rel_path)
    if preview["status"] != "paused":
        raise ValueError("Project is not paused")
    restored = preview["paused_from_status"] or "active"
    update_frontmatter(rel_path, {"status": restored},
                       remove=["paused_from_status"])
    return {"unpaused": rel_path, "status": restored}


def folder_health() -> list[dict]:
    """File counts and last activity for each visible top-level vault folder."""
    def build():
        rows = []
        for folder in sorted(VAULT.iterdir()):
            if not folder.is_dir() or folder.name.startswith(".") or folder.name in SKIP_DIRS:
                continue
            count = 0
            latest = None
            for dirpath, dirnames, filenames in os.walk(folder):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
                for name in filenames:
                    count += 1
                    try:
                        mt = os.path.getmtime(os.path.join(dirpath, name))
                    except OSError:
                        continue
                    if latest is None or mt > latest:
                        latest = mt
            from datetime import datetime, timezone
            latest_dt = datetime.fromtimestamp(latest, tz=timezone.utc) if latest else None
            rows.append({
                "folder": folder.name,
                "files": count,
                "last_activity_iso": latest_dt.isoformat() if latest_dt else None,
                "time_str": rel_time(latest_dt),
            })
        rows.sort(key=lambda r: r["last_activity_iso"] or "", reverse=True)
        return rows
    return _cached("folder_health", build)
