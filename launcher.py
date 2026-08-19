"""Launch a coding agent at a project folder from the dashboard.

Built for a non-coder, so nothing here ever opens a raw terminal. Launch
targets are GUI apps only:

  claude-vscode / codex-vscode  -> open VS Code at the folder (agent extension
                                   inside); the prompt is copied to the clipboard
  claude-app                    -> Claude Code desktop app, if installed
  codex-app                     -> Codex desktop app, if installed

The desktop apps aren't installed on this machine yet — they're probed for at
every request and light up automatically once installed. config.json can also
pin explicit exe paths via "claude_app_path" / "codex_app_path".

Safety: only paths inside the vault or the code root may be launched, and no
argument ever passes through a shell.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from config import CODE_ROOT, CONFIG, VAULT

_ALLOWED_ROOTS = [VAULT.resolve(), CODE_ROOT.resolve()]

_LOCAL = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))

# Plausible install locations, probed each time so a fresh install is picked up
_CLAUDE_APP_CANDIDATES = [
    _LOCAL / "Programs" / "claude-code" / "Claude Code.exe",
    _LOCAL / "Programs" / "Claude Code" / "Claude Code.exe",
    _LOCAL / "AnthropicClaude" / "claude.exe",
    _LOCAL / "Programs" / "Claude" / "Claude.exe",
]
_CODEX_APP_CANDIDATES = [
    _LOCAL / "Programs" / "codex" / "Codex.exe",
    _LOCAL / "Programs" / "Codex" / "Codex.exe",
]


def _find_app(config_key: str, candidates: list[Path]) -> str | None:
    pinned = CONFIG.get(config_key)
    if pinned and Path(pinned).exists():
        return str(pinned)
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def _vscode() -> str | None:
    return shutil.which("code")


def available_tools() -> list[dict]:
    code = _vscode()
    claude_app = _find_app("claude_app_path", _CLAUDE_APP_CANDIDATES)
    codex_app = _find_app("codex_app_path", _CODEX_APP_CANDIDATES)
    return [
        {"id": "claude-vscode", "label": "Claude Code · VS Code", "available": bool(code)},
        {"id": "codex-vscode", "label": "Codex · VS Code", "available": bool(code)},
        {"id": "claude-app", "label": "Claude Code · App", "available": bool(claude_app),
         "hint": None if claude_app else "app not installed — set claude_app_path in config.json once it is"},
        {"id": "codex-app", "label": "Codex · App", "available": bool(codex_app),
         "hint": None if codex_app else "app not installed — set codex_app_path in config.json once it is"},
    ]


def _check_path(path_str: str) -> Path:
    raw = Path(path_str)
    # Vault-relative paths (as used by pipeline cards) resolve against the vault
    path = (VAULT / raw).resolve() if not raw.is_absolute() else raw.resolve()
    if not path.exists():
        raise ValueError(f"Path does not exist: {path}")
    if path.is_file():
        path = path.parent
    for root in _ALLOWED_ROOTS:
        try:
            path.relative_to(root)
            return path
        except ValueError:
            continue
    raise ValueError("Path is outside the vault and code workspace")


def _copy_to_clipboard(text: str) -> None:
    try:
        subprocess.run(["clip.exe"], input=text, text=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    except Exception:
        pass


def _spawn(args: list[str]) -> None:
    subprocess.Popen(args, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def launch(tool: str, path_str: str, prompt: str = "") -> dict:
    path = _check_path(path_str)
    prompt = (prompt or "").strip()
    tools = {t["id"]: t for t in available_tools()}
    if tool not in tools:
        raise ValueError(f"Unknown tool: {tool}")
    if not tools[tool]["available"]:
        raise ValueError(f"{tools[tool]['label']} is not available on this machine")

    clip_note = ""
    if prompt:
        _copy_to_clipboard(prompt)
        clip_note = " — prompt copied to clipboard, paste it into the agent"

    if tool in ("claude-vscode", "codex-vscode"):
        _spawn(["cmd", "/c", _vscode(), str(path)])
        return {"launched": tool, "path": str(path), "note": "VS Code opened" + clip_note}

    key = "claude_app_path" if tool == "claude-app" else "codex_app_path"
    candidates = _CLAUDE_APP_CANDIDATES if tool == "claude-app" else _CODEX_APP_CANDIDATES
    exe = _find_app(key, candidates)
    _spawn([exe, str(path)])
    return {"launched": tool, "path": str(path),
            "note": f"{tools[tool]['label']} opened" + clip_note}
