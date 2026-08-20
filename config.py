"""Configuration for the AI Command Center.

All paths and flags live in config.json next to this file so the app can be
relocated without touching code. Missing keys fall back to DEFAULTS.
"""
from __future__ import annotations

import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent

DEFAULTS: dict = {
    "vault": r"C:\path\to\your\vault",
    "vault_name": "YourVault",
    "pa_db": r"C:\path\to\your\personal-assistant-agent\data\pa_agent.sqlite3",
    "secondbrain_dir": r"C:\path\to\your\vault\.second-brain",
    "capture_log": r"C:\path\to\your\second-brain\capture.log",
    "code_root": r"C:\path\to\your\code\workspace",
    "port": 5150,
    "enable_actions": False,
    "cache_ttl_seconds": 15,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    cfg_path = _HERE / "config.json"
    if cfg_path.exists():
        try:
            cfg.update(json.loads(cfg_path.read_text(encoding="utf-8")))
        except Exception as exc:  # malformed config should not kill the app
            print(f"[config] failed to read config.json, using defaults: {exc}")
    return cfg


CONFIG = load_config()

VAULT = Path(CONFIG["vault"])
VAULT_NAME = CONFIG["vault_name"]
PA_DB = Path(CONFIG["pa_db"])
SECONDBRAIN_DIR = Path(CONFIG["secondbrain_dir"])
CAPTURE_LOG = Path(CONFIG["capture_log"])
CODE_ROOT = Path(CONFIG["code_root"])
PORT = int(CONFIG["port"])
ENABLE_ACTIONS = bool(CONFIG["enable_actions"])
CACHE_TTL = float(CONFIG["cache_ttl_seconds"])
