"""Code workspace integration: git repos in the configured code_root folder.

Uses the git CLI directly (already on PATH) — branch, last commit, dirty file
count, and the GitHub remote so the dashboard can deep-link to the repo page.
"""
from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from config import CODE_ROOT
from util import rel_time

_cache: tuple[float, list] | None = None
CODE_TTL = 30.0


def _git(repo: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


def _github_url(remote: str | None) -> str | None:
    if not remote:
        return None
    url = remote.strip()
    if url.startswith("git@github.com:"):
        url = "https://github.com/" + url.split(":", 1)[1]
    if url.endswith(".git"):
        url = url[:-4]
    return url if url.startswith("https://github.com/") else None


def list_repos() -> list[dict]:
    global _cache
    if _cache and _cache[0] > time.monotonic():
        return _cache[1]

    repos: list[dict] = []
    if not CODE_ROOT.exists():
        return repos
    for folder in sorted(CODE_ROOT.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        is_git = (folder / ".git").exists()
        entry: dict = {
            "name": folder.name,
            "path": str(folder),
            "is_git": is_git,
            "branch": None, "last_commit": None, "last_commit_time_iso": None,
            "last_commit_str": None, "dirty": 0, "github_url": None,
        }
        if is_git:
            entry["branch"] = _git(folder, "rev-parse", "--abbrev-ref", "HEAD")
            log = _git(folder, "log", "-1", "--format=%s%x1f%ct")
            if log and "\x1f" in log:
                msg, epoch = log.split("\x1f", 1)
                dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
                entry["last_commit"] = msg
                entry["last_commit_time_iso"] = dt.isoformat()
                entry["last_commit_str"] = rel_time(dt)
            status = _git(folder, "status", "--porcelain")
            entry["dirty"] = len(status.splitlines()) if status else 0
            entry["github_url"] = _github_url(_git(folder, "remote", "get-url", "origin"))
        repos.append(entry)
    repos.sort(key=lambda r: (not r["is_git"], r["last_commit_time_iso"] or ""), reverse=False)
    _cache = (time.monotonic() + CODE_TTL, repos)
    return repos


_commit_cache: tuple[float, list] | None = None


def recent_commits(limit_per_repo: int = 3) -> list[dict]:
    """Recent commits across all repos, for the homepage 'last done' digest.

    Includes a per-commit file-change summary (from --shortstat + name-only)
    so the dashboard can show *what* a commit touched on hover.
    """
    global _commit_cache
    if _commit_cache and _commit_cache[0] > time.monotonic():
        return _commit_cache[1]

    commits: list[dict] = []
    for repo in list_repos():
        if not repo["is_git"]:
            continue
        log = _git(Path(repo["path"]), "log", f"-{limit_per_repo}",
                   "--format=%x1e%h%x1f%s%x1f%ct", "--name-only")
        if not log:
            continue
        for record in log.split("\x1e"):
            record = record.strip()
            if "\x1f" not in record:
                continue
            head, _, files_blob = record.partition("\n")
            sha, msg, epoch = head.split("\x1f", 2)
            files = [f for f in files_blob.strip().splitlines() if f.strip()]
            shown = files[:6]
            summary = f"{len(files)} file{'s' if len(files) != 1 else ''} changed"
            if shown:
                summary += ": " + ", ".join(shown)
                if len(files) > len(shown):
                    summary += f" … +{len(files) - len(shown)} more"
            dt = datetime.fromtimestamp(int(epoch), tz=timezone.utc)
            commits.append({
                "repo": repo["name"],
                "sha": sha,
                "message": msg,
                "summary": summary,
                "time_iso": dt.isoformat(),
                "time_str": rel_time(dt),
            })
    commits.sort(key=lambda c: c["time_iso"], reverse=True)
    _commit_cache = (time.monotonic() + CODE_TTL, commits)
    return commits
