"""Vault knowledge graph: nodes are markdown notes, links are [[wikilinks]].

Obsidian resolves wikilinks by filename, so we index every note by its stem
(case-insensitive) and match link targets against that. Frontmatter
related_notes entries are plain '[[...]]' strings, so scanning the raw file
text catches both body links and frontmatter links in one pass.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from config import VAULT
from vault import SKIP_DIRS
from util import display_name, parse_frontmatter

_WIKILINK = re.compile(r"\[\[([^\]|#\n]+)")

_cache: tuple[float, dict] | None = None
GRAPH_TTL = 60.0


def _walk_all_md():
    for dirpath, dirnames, filenames in os.walk(VAULT):
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if name.endswith(".md"):
                yield Path(dirpath) / name


def build_graph() -> dict:
    global _cache
    if _cache and _cache[0] > time.monotonic():
        return _cache[1]

    files: list[Path] = list(_walk_all_md())
    nodes: list[dict] = []
    stem_index: dict[str, str] = {}  # lowercase stem -> node id (rel path)

    for f in files:
        rel = str(f.relative_to(VAULT)).replace("\\", "/")
        parts = rel.split("/")
        folder = parts[0] if len(parts) > 1 else "(root)"
        nodes.append({"id": rel, "name": display_name(f), "folder": folder,
                      "type": "note", "degree": 0})
        stem_index.setdefault(f.stem.lower(), rel)

    node_by_id = {n["id"]: n for n in nodes}
    links: list[dict] = []
    seen: set[tuple[str, str]] = set()
    tag_nodes: dict[str, dict] = {}

    for f in files:
        rel = str(f.relative_to(VAULT)).replace("\\", "/")
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        # Tag hub nodes (Obsidian "show tags" style) from frontmatter tags
        fm, _ = parse_frontmatter(f)
        tags = fm.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        for tag in tags:
            if not isinstance(tag, str) or not tag.strip():
                continue
            tag = tag.strip()
            tag_id = f"#{tag}"
            hub = tag_nodes.get(tag_id)
            if hub is None:
                hub = {"id": tag_id, "name": tag_id, "folder": "#tags",
                       "type": "tag", "degree": 0}
                tag_nodes[tag_id] = hub
            links.append({"source": rel, "target": tag_id, "type": "tag"})
            node_by_id[rel]["degree"] += 1
            hub["degree"] += 1

        for raw in _WIKILINK.findall(text):
            # Targets may be paths ("../Active/foo") or bare names ("foo")
            stem = raw.strip().split("/")[-1].split("\\")[-1].lower()
            target = stem_index.get(stem)
            if not target or target == rel:
                continue
            key = (rel, target) if rel < target else (target, rel)
            if key in seen:
                continue
            seen.add(key)
            links.append({"source": rel, "target": target, "type": "wiki"})
            node_by_id[rel]["degree"] += 1
            node_by_id[target]["degree"] += 1

    all_nodes = nodes + list(tag_nodes.values())
    folders = sorted({n["folder"] for n in nodes})
    result = {"nodes": all_nodes, "links": links, "folders": folders,
              "note_count": len(nodes), "tag_count": len(tag_nodes),
              "link_count": len(links)}
    _cache = (time.monotonic() + GRAPH_TTL, result)
    return result
