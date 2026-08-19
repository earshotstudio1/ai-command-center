---
title: AI Command Center v2 — Audit & Design
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

# AI Command Center v2 — Audit & Design

Date: 2026-07-03
Status: approved for build (autonomous session — decisions documented below)

## 1. Audit of v1 (`~/dashboard`)

v1 is a solid read-only glance surface: Flask + single 943-line HTML file, four API endpoints
(projects / inbox / agent / activity), dark Syne + JetBrains Mono aesthetic, 30s auto-refresh.

### What holds it back

| # | Finding | Impact |
|---|---------|--------|
| 1 | **Read-only.** No actions at all — you can see a PA draft is `awaiting_approval` but must switch to Telegram to act. | It is a *viewer*, not a *command* centre. The highest-leverage moment in the PA workflow (human approval) is invisible to it. |
| 2 | **Shallow PA integration.** Only stage/status counts + 8 recent task rows. The PA DB contains research briefs, sourced contacts, versioned drafts, and a full audit trail — none surfaced. | The "task detail drawer" on the v1 wish list is exactly this gap. |
| 3 | **No Orchestrator surface.** The Orchestrator isn't built yet, but its *state already exists in the vault* — every idea note carries `stage` / `decision` / `status` frontmatter that maps directly onto the orchestrator lifecycle (capture → triage → research → promote → execute → maintain). | The dashboard can render the pipeline today and become the orchestrator's cockpit the day it ships. v1 misses this entirely. |
| 4 | **Second Brain agent invisible.** The capture bot + maintenance pipeline emit rich liveness signals (`capture.log` mtime, `processed.jsonl`, `maintenance_runs.jsonl`, `telegram_offset.json`) but v1 shows placeholder cards. | Two of the three real agents in the infrastructure report no health. |
| 5 | **Weak liveness checks.** "PA DB file exists" ≠ "PA agent is alive". | False confidence. |
| 6 | **Performance.** Full vault `rglob` on every request, 4 endpoints × every 30s, no caching. Vault has 700+ files and grows. | Wasted IO; will degrade as vault grows. |
| 7 | **Hardcoded config.** Vault path, PA DB path, port all baked into `app.py`. | Brittle; can't relocate anything. |
| 8 | **Activity feed = file mtimes only.** PA audit events and capture-pipeline events are absent. | The feed shows *files changed*, not *what the agents did*. |
| 9 | **Monolith.** One 943-line HTML file, one `app.py`. | Hard to extend per-panel. |
| 10 | **Wish-list items unshipped:** inbox triage actions, task drawer, vault health panel. | — |

## 2. How the three projects connect

- **Second Brain** (capture) feeds `Inbox/` → notes with frontmatter. It is the *intake* agent.
- **Personal Assistant Agent** executes admin tasks; state in SQLite; human-in-the-loop approval is its core gate.
- **AI Project Orchestrator** (idea stage) will drive ideas from capture to executed project. Its future state store *is the vault frontmatter + Projects folder structure*.
- **Command Center** is the shared pane of glass across all three — and, where safe, the shared *control* surface.

The single most effective upgrade: make the Command Center the place where human-in-the-loop
moments across all agents become visible **and actionable** (approve/reject PA drafts, triage inbox),
while modelling the orchestrator pipeline from existing frontmatter so the orchestrator plugs in later
with zero dashboard rework.

## 3. v2 Design decisions (made autonomously, easy to reverse)

- **Location:** `ObsidianVault/Projects/Active/ai-command-center/` — matches where the PA agent lives; inside my writable scope. Movable: all paths live in `config.json`.
- **Stack unchanged:** Python 3.11 + Flask + PyYAML (already installed), vanilla no-build frontend. Keep v1's visual language.
- **Port 5150** to avoid common local dev-server conflicts.
- **Write-back is opt-in by config** (`enable_actions`, default on): approve/reject PA drafts using the exact semantics of the PA `Store` (status + `approved_text` + audit event, actor `dashboard`); archive inbox items (move to `Inbox/Archive/` — reversible).
- **Reads open SQLite in read-only mode** (`mode=ro`); only the two action endpoints open read-write.
- **TTL cache (15s)** on vault scans; one scan feeds projects, pipeline, activity, and health.

## 4. Architecture

```
ai-command-center/
├── app.py            # Flask routes only
├── config.json       # paths, port, flags
├── config.py         # config load + defaults
├── vault.py          # cached vault scan, frontmatter parse, inbox, health, archive
├── pa.py             # PA SQLite: summary, task list, task bundle, approve/reject
├── secondbrain.py    # capture bot + maintenance health from logs/jsonl
├── pipeline.py       # orchestrator lifecycle view from frontmatter
├── activity.py       # unified feed: file changes + PA audit + capture events
├── templates/index.html
├── static/style.css
├── static/app.js
├── start.bat
└── README.md
```

### API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/summary` | GET | Topline counts + agent health lights for the header |
| `/api/projects` | GET | Projects with stage/status/next_action (v1 parity, cached) |
| `/api/inbox` | GET | Inbox items + content snippet |
| `/api/inbox/archive` | POST | Move an inbox file to `Inbox/Archive/` |
| `/api/pipeline` | GET | Ideas grouped by orchestrator lifecycle stage |
| `/api/agents` | GET | Real health for PA / Capture / Maintenance / Orchestrator(planned) |
| `/api/pa/tasks` | GET | All PA tasks with pending-approval counts |
| `/api/pa/task/<id>` | GET | Full bundle: clarifications, sources, contacts, drafts, audit |
| `/api/pa/draft/<id>/approve` | POST | Approve draft (PA semantics, actor=dashboard) |
| `/api/pa/draft/<id>/reject` | POST | Reject draft with reason |
| `/api/activity` | GET | Unified feed (vault + PA audit + capture pipeline) |
| `/api/health` | GET | Vault folder health: counts + last activity |

### Frontend

Four views in one page (tab bar, no build step): **Overview** (v1-style 3-column),
**Pipeline** (lifecycle board), **Agents** (health cards + PA task drawer with approve/reject),
**Vault** (folder health). Obsidian deep links (`obsidian://open?...`) everywhere a note is shown.
Auto-refresh 30s, paused while a drawer is open.

### Agent liveness model

- **Capture bot:** `capture.log` mtime < 10 min → `live`; < 24h → `idle`; else `down`.
- **Maintenance:** last entry of `maintenance_runs.jsonl` + its stats.
- **PA agent:** DB reachable + latest task/audit timestamps; pending approvals & clarifications counted as "needs you".
- **Orchestrator:** static `planned` card listing what its note says needs building, so the gap stays visible.

## 5. v2.1 additions (2026-07-03, same day)

Requested after first use of v2:

- **Home view (new default).** Calm digest instead of the busy Overview: *Last Done* (git
  commits across the code workspace + vault note edits + PA audit events + captures, merged
  newest-first) and *Next Steps* (PA approvals waiting, ideas at the decision gate, projects
  with `next_action:`, repos with heavy uncommitted work). Each step has **▶ action** — which
  launches the selected coding agent at the right folder with a pre-built prompt — and a
  review link (Obsidian note / dashboard tab / GitHub).
- **Agent launcher** (`launcher.py`, `POST /api/launch`). Tools: Claude Code · VS Code,
  Claude Code · Terminal, Codex · VS Code, Codex · Terminal — availability detected at runtime
  (`codex` CLI not installed → shown disabled). VS Code launches copy the prompt to the
  clipboard; terminal launches pass it as the CLI's initial prompt. Only paths inside the
  vault or code root may be launched; the choice persists in localStorage.
- **Code view** (`code_projects.py`). Every folder in `VS Code I Guess`: branch, last commit,
  dirty-file count, GitHub deep link, plus open-in-VS-Code / launch-agent buttons.
- **Interactive knowledge graph** (`graph.py` + force-graph) on the Vault tab, Folder Health
  beneath it. Nodes = every vault note (colored by top-level folder, sized by degree) plus
  Obsidian-style tag hubs (toggleable). Links = `[[wikilinks]]` (body + frontmatter) and
  note→tag edges. Zoom/pan, hover highlights the node's neighborhood and dims the rest,
  click opens the note in Obsidian. Redraw pauses when idle so the canvas costs nothing.
- **Pipeline toggle** — Live Projects / Ideas / All. "Live" = `decision: build` or
  `stage: building/shipped`; everything still germinating in the orchestrator's background
  loops stays under Ideas until it reaches its decision gate.

## 6. v2.2 — feedback round (2026-07-04)

All five items from FEEDBACK.md:

1. **No-terminal launcher.** Terminal launch paths removed. Tools are now Claude Code · VS Code,
   Codex · VS Code (both work today; prompt goes to the clipboard), and Claude Code · App /
   Codex · App — probed on every request against known install paths, shown disabled until the
   desktop apps are installed. `claude_app_path` / `codex_app_path` in config.json pin an exe
   explicitly. Launch paths may now be vault-relative (resolved against the vault root).
2. **Home hover summaries.** Every Last Done card carries a server-built `summary`, shown in a
   hover popover: commits list their changed files (`git log --name-only`), notes show
   stage/decision/next-action plus a prose snippet of the note body, PA events show their audit
   payload (approved text, redraft instructions, Q&A), captures show source → output note.
3. **Overview → Agents click-through.** The agent mini-cards navigate to the Agents tab with
   that agent pre-selected.
4. **Per-agent task panes.** Agents tab has a pill switcher: PA Agent (task list + drawer, as
   before), Capture Bot (processed captures with Obsidian links), Maintenance (run history from
   `maintenance_runs.jsonl` with per-run stats + report links), Orchestrator (build plan).
   New endpoints: `/api/captures`, `/api/maintenance/runs`.
5. **Actionable pipeline cards.** Clicking a card opens a project drawer: status badges,
   next action, note preview (`/api/note`), open-in-Obsidian, ▶ take into agent (launches the
   selected tool at the note's folder with a ready-made prompt), and **pause / unpause**.
   Pause stashes the current status in `paused_from_status:` frontmatter and sets
   `status: paused`; unpause restores the stashed status and removes the stash, so the card
   returns to exactly the column it came from. Frontmatter write-back
   (`vault.update_frontmatter`) preserves key order and the note body verbatim (round-trip
   tested byte-identical; BOM-tolerant reads).

## 7. Non-goals

- No auth (localhost, single user).
- No WebSockets — polling is fine at this scale.
- No orchestrator *execution* logic — the dashboard models its state; building the orchestrator is its own project.
- No edits to PA agent code; v2 only speaks to its DB with identical semantics.
