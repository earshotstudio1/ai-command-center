---
title: AI Command Center
date: '2026-08-19'
type: project-note
domain: project
stage: active
decision: undecided
source: manual
status: active
tags: []
created: '2026-08-19'
updated: '2026-08-19'
workflow: capture_telegram
---

# AI Command Center

A local dashboard that puts every AI system I run on one screen.

<!-- Daniel: take and add these two screenshots manually before publishing.
     1. docs/screenshot-graph.png — the Vault tab's knowledge graph
     2. docs/screenshot-pipeline.png — the Pipeline tab's kanban board
     Check note titles in both for anything personal or client-related before saving,
     then uncomment the two image lines below. -->
<!-- ![Vault knowledge graph](docs/screenshot-graph.png) -->

## Why it exists

I had four things running: a capture bot, a transcript processor, a maintenance sweep and an assistant agent. Each had its own log file, its own state directory and its own way of telling me whether it was alive. Checking on them meant opening four terminals.

This is the one screen instead.

## What it does

- **Home** — what happened last across code repos, vault and agents, and what to do next, with buttons that launch a coding agent at the right folder with a prepared prompt.
- **Vault** — an interactive knowledge graph of the whole vault: zoom, pan, hover to highlight a note's neighbourhood, toggle tag hubs, click through to open in Obsidian. Folder health sits beneath it.
- **Pipeline** — a kanban board over the project lifecycle (Captured, Developing, Building, Paused, Shipped) with a drawer per card for preview, pause and unpause. Unpause returns a project to exactly where it left off.

<!-- ![Pipeline board](docs/screenshot-pipeline.png) -->

- **Agents** — real health for each agent, the assistant's task list, the capture bot's processed items, maintenance run history with report links.
- **Code** — every repo in the workspace with branch, last commit, uncommitted count and a link out.

## Architecture

- **Read-only by default over other systems' data** — the assistant's SQLite database is opened in `mode=ro` for every read path, so the dashboard cannot corrupt the agent's own state.
- **Write paths replicate the agent's own semantics exactly** — approving a draft from the dashboard goes through the same rules as approving it in the agent, writing an audit event with actor `dashboard`. Approved drafts stay immutable.
- **One kill switch** — `enable_actions: false` in config turns the whole thing into a strictly read-only viewer.
- **Module per data source** (`vault.py`, `pa.py`, `secondbrain.py`, `code_projects.py`) with a thin Flask layer over them, so a new system becomes a new module rather than a change to the app.
- **Cached vault scans** with a configurable TTL, because walking a vault of that size on every request is the obvious way to make a local dashboard feel slow.

## Status

Around 1,800 lines across 12 modules. Runs locally on port 5150, no build step, no dependencies beyond Flask and PyYAML. Single-user by design and not hardened for anything else: it binds to localhost, has no authentication, and should not be exposed. The v1 audit and the full v2 design are in [DESIGN.md](DESIGN.md).

## Setup

Python 3.11 with `flask` and `pyyaml`. Copy `config.example.json` to `config.json` and point it at your own vault and agent paths, then `python app.py` and open `http://127.0.0.1:5150`.

MIT licensed.
