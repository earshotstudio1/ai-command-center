/* AI Command Center v2 */
"use strict";

const VAULT_NAME = document.body.dataset.vault;
const ACTIONS_ON = document.body.dataset.actions === "on";
const REFRESH_MS = 30000;
const TOKEN_STORAGE_KEY = "cc-dashboard-token";

/* The launcher opens the dashboard with ?token=... on the URL. Pick it up
   once, remember it in localStorage, then scrub it from the address bar so
   it doesn't linger in browser history. */
(function initToken() {
  const params = new URLSearchParams(location.search);
  const token = params.get("token");
  if (token) {
    localStorage.setItem(TOKEN_STORAGE_KEY, token);
    params.delete("token");
    const rest = params.toString();
    const clean = location.pathname + (rest ? `?${rest}` : "") + location.hash;
    history.replaceState(null, "", clean);
  }
})();

function dashboardToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || "";
}

let drawerOpen = false;
let currentTaskId = null;
let pipelineSource = "live";
let pipelineData = null;
let selectedTool = localStorage.getItem("cc-tool") || null;
let toolList = [];

/* ── helpers ─────────────────────────────── */
const $ = (sel) => document.querySelector(sel);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function obsidianLink(path) {
  const file = path.replace(/\.md$/, "");
  return `obsidian://open?vault=${encodeURIComponent(VAULT_NAME)}&file=${encodeURIComponent(file)}`;
}

async function getJSON(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Dashboard-Token": dashboardToken(),
    },
    body: JSON.stringify(body || {}),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function setStatus(msg, isError) {
  const el = $("#status-msg");
  el.textContent = msg;
  el.style.color = isError ? "var(--rose)" : "";
}

function empty(msg) { return `<div class="empty">${esc(msg)}</div>`; }

/* ── topbar ──────────────────────────────── */
function renderSummary(s) {
  const needs = $("#needs-you");
  needs.textContent = s.needs_you > 0 ? `${s.needs_you} need you` : "all clear";
  needs.classList.toggle("zero", s.needs_you === 0);
  const lights = Object.entries(s.agents).map(([name, a]) =>
    `<div class="light ${esc(a.state)}" title="${esc(name)}: ${esc(a.state)}"></div>`);
  $("#agent-lights").innerHTML = lights.join("");
}

/* ── home ────────────────────────────────── */
function renderToolSelect() {
  if (!toolList.length) return;
  if (!selectedTool || !toolList.find((t) => t.id === selectedTool && t.available)) {
    selectedTool = (toolList.find((t) => t.available) || {}).id || null;
  }
  $("#tool-select").innerHTML = toolList.map((t) => `
    <button class="tool-opt ${t.id === selectedTool ? "active" : ""}"
            data-tool="${esc(t.id)}" ${t.available ? "" : "disabled"}
            title="${t.available ? esc(t.label) : esc(t.hint || t.label + " (not installed)")}">
      ${esc(t.label)}</button>`).join("");
  document.querySelectorAll(".tool-opt").forEach((btn) =>
    btn.addEventListener("click", () => {
      selectedTool = btn.dataset.tool;
      localStorage.setItem("cc-tool", selectedTool);
      renderToolSelect();
    }));
}

async function launchAgent(path, prompt) {
  if (!selectedTool) { setStatus("no launch tool available", true); return; }
  try {
    const r = await postJSON("/api/launch", { tool: selectedTool, path, prompt });
    setStatus(r.note);
  } catch (e) { setStatus(e.message, true); }
}

function renderHome(d) {
  const now = new Date();
  const hour = now.getHours();
  const word = hour < 12 ? "Morning" : hour < 18 ? "Afternoon" : "Evening";
  $("#home-greeting").innerHTML = `${word}.
    <span class="sub">${esc(now.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" }))}
    · ${d.next_steps.length} next step${d.next_steps.length !== 1 ? "s" : ""} queued</span>`;

  const icon = { commit: "⌥", note: "📝", agent: "🤖", capture: "📥" };
  $("#home-lastdone").innerHTML = d.last_done.length ? d.last_done.map((e) => `
    <div class="card ${e.summary ? "has-peek" : ""}">
      <div class="card-title"><span>${icon[e.kind] || "•"}</span>
        ${e.path ? `<a href="${obsidianLink(e.path)}">${esc(e.title)}</a>` : esc(e.title)}
        <span class="time">${esc(e.time_str)}</span></div>
      ${e.detail ? `<div class="card-sub">${esc(e.detail)}</div>` : ""}
      ${e.summary ? `<div class="hover-peek">${esc(e.summary)}</div>` : ""}
    </div>`).join("") : empty("nothing recorded yet");

  $("#home-nextsteps").innerHTML = d.next_steps.length ? d.next_steps.map((s, i) => `
    <div class="step-card">
      <div class="step-title"><span class="step-kind ${esc(s.kind)}">${esc(s.kind)}</span>
        ${esc(s.title)}
        ${s.priority ? `<span class="badge hi">${esc(s.priority)}</span>` : ""}</div>
      <div class="step-detail">${esc(s.detail)}</div>
      <div class="step-actions">
        ${s.action && ACTIONS_ON ? `<button class="btn action" data-step="${i}">▶ action</button>` : ""}
        ${s.review && s.review.obsidian ? `<a class="btn" href="${obsidianLink(s.review.obsidian)}">review note</a>` : ""}
        ${s.review && s.review.view ? `<button class="btn" data-goto="${esc(s.review.view)}">review</button>` : ""}
        ${s.review && s.review.github ? `<a class="btn" href="${esc(s.review.github)}" target="_blank" rel="noopener">github</a>` : ""}
      </div>
    </div>`).join("") : empty("no next steps — add next_action to a project note");

  document.querySelectorAll("[data-step]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const s = d.next_steps[Number(btn.dataset.step)];
      launchAgent(s.action.path, s.action.prompt);
    }));
  document.querySelectorAll("[data-goto]").forEach((btn) =>
    btn.addEventListener("click", () => switchView(btn.dataset.goto)));
}

/* ── overview panels ─────────────────────── */
function renderInbox(items) {
  $("#inbox-count").textContent = items.length;
  if (!items.length) { $("#inbox-list").innerHTML = empty("inbox zero — nice"); return; }
  $("#inbox-list").innerHTML = items.map((i) => `
    <div class="card">
      <div class="card-title">
        ${i.ext === ".md"
          ? `<a href="${obsidianLink("Inbox/" + i.file)}">${esc(i.title)}</a>`
          : esc(i.title)}
        <span class="time">${esc(i.time_str)}</span>
      </div>
      ${i.snippet ? `<div class="card-sub">${esc(i.snippet)}</div>` : ""}
      <div class="card-meta">
        <span class="badge">${esc(i.ext)}</span>
        ${ACTIONS_ON ? `<button class="btn" data-archive="${esc(i.file)}">archive</button>` : ""}
      </div>
    </div>`).join("");

  document.querySelectorAll("[data-archive]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      try {
        await postJSON("/api/inbox/archive", { file: btn.dataset.archive });
        setStatus(`archived ${btn.dataset.archive}`);
        loadAll();
      } catch (e) { setStatus(e.message, true); }
    });
  });
}

function projectCard(p, clickIdx) {
  const clickable = typeof clickIdx === "number";
  return `
    <div class="card ${clickable ? `clickable" data-project="${clickIdx}` : ""}">
      <div class="card-title">
        <span class="dot ${esc(p.stage || p.status)}"></span>
        <a href="${obsidianLink(p.path)}">${esc(p.title)}</a>
        <span class="time">${esc(p.time_str)}</span>
      </div>
      <div class="card-meta">
        ${p.stage ? `<span class="badge ${esc(p.stage)}">${esc(p.stage)}</span>` : ""}
        ${p.decision ? `<span class="badge">${esc(p.decision)}</span>` : ""}
        ${p.priority_tag ? `<span class="badge hi">${esc(p.priority_tag)}</span>` : ""}
      </div>
    </div>`;
}

function renderProjects(projects) {
  $("#projects-count").textContent = projects.length;
  $("#projects-list").innerHTML =
    projects.length ? projects.map((p) => projectCard(p)).join("") : empty("no projects found");
  const prio = projects.filter((p) => p.next_action);
  $("#priorities-list").innerHTML = prio.length
    ? prio.map((p) => `
      <div class="card">
        <div class="card-title">
          <a href="${obsidianLink(p.path)}">${esc(p.title)}</a>
          ${p.priority_tag ? `<span class="badge hi">${esc(p.priority_tag)}</span>` : ""}
        </div>
        <div class="card-sub">→ ${esc(p.next_action)}</div>
      </div>`).join("")
    : empty("add next_action: to a project note");
}

function renderAgentsMini(a) {
  const rows = [
    ["PA Agent", a.pa.available ? "ok" : "down",
      a.pa.available
        ? `${a.pa.pending_approvals} approvals · ${a.pa.pending_clarifications} clarifications pending`
        : a.pa.error],
    ["Capture Bot", a.capture.state, a.capture.detail],
    ["Maintenance", a.maintenance.state, a.maintenance.detail],
    ["Orchestrator", "planned", "not built — see Pipeline view"],
  ];
  const agentKey = { "PA Agent": "pa", "Capture Bot": "capture",
                     "Maintenance": "maintenance", "Orchestrator": "orchestrator" };
  $("#agents-mini").innerHTML = rows.map(([name, state, detail]) => `
    <div class="card clickable" data-agent-goto="${esc(agentKey[name])}">
      <div class="card-title"><span class="light ${esc(state)}"></span>${esc(name)}
        <span class="time">${esc(state)}</span></div>
      <div class="card-sub">${esc(detail || "")}</div>
    </div>`).join("");
  document.querySelectorAll("[data-agent-goto]").forEach((el) =>
    el.addEventListener("click", () => {
      selectAgent(el.dataset.agentGoto);
      switchView("agents");
    }));
}

function renderActivity(events) {
  const icon = { vault: "📝", pa: "🤖", capture: "📥" };
  $("#activity-list").innerHTML = events.length ? events.map((e) => `
    <div class="card">
      <div class="card-title">
        <span>${icon[e.kind] || "•"}</span>
        ${e.path ? `<a href="${obsidianLink(e.path)}">${esc(e.title)}</a>` : esc(e.title)}
        <span class="time">${esc(e.time_str)}</span>
      </div>
      ${e.detail ? `<div class="card-sub">${esc(e.detail)}</div>` : ""}
    </div>`).join("") : empty("no recent activity");
}

/* ── pipeline ────────────────────────────── */
function renderPipeline(board) {
  pipelineData = board || pipelineData;
  if (!pipelineData) return;
  const flat = [];
  $("#pipeline-board").innerHTML = pipelineData.columns.map((col) => {
    const cards = pipelineSource === "all"
      ? col.cards : col.cards.filter((c) => c.source === pipelineSource);
    const body = cards.map((c) => {
      flat.push(c);
      return projectCard(c, flat.length - 1);
    }).join("");
    return `
    <div class="board-col">
      <div class="board-col-head">
        <h3>${esc(col.label)} <span class="pill">${cards.length}</span></h3>
        <span class="hint">${esc(col.hint)}</span>
      </div>
      <div class="board-col-body">
        ${cards.length ? body : empty("—")}
      </div>
    </div>`;
  }).join("");
  document.querySelectorAll("#pipeline-board [data-project]").forEach((el) =>
    el.addEventListener("click", (ev) => {
      if (ev.target.closest("a")) return;  // let Obsidian links work normally
      openProject(flat[Number(el.dataset.project)]);
    }));
}

/* project drawer (pipeline cards) */
async function openProject(card) {
  drawerOpen = true;
  document.body.classList.add("drawer-open");
  $("#drawer-title").textContent = card.title;
  $("#drawer-body").innerHTML = empty("loading…");
  let note = null;
  try {
    note = await getJSON(`/api/note?path=${encodeURIComponent(card.path)}`);
  } catch (e) {
    $("#drawer-body").innerHTML = empty(e.message);
    return;
  }
  const paused = note.status === "paused";
  const launchPrompt =
    `Continue working on the project "${note.title}". The project note is at ` +
    `${card.path} in my Obsidian vault.` +
    (note.next_action ? ` The next action is: ${note.next_action}` : "");
  $("#drawer-body").innerHTML = `
    <div class="drawer-section">
      <h3>Project</h3>
      <div class="card">
        <div class="card-meta">
          ${note.stage ? `<span class="badge ${esc(note.stage)}">${esc(note.stage)}</span>` : ""}
          <span class="badge">${esc(note.status)}</span>
          ${note.decision ? `<span class="badge">${esc(note.decision)}</span>` : ""}
          ${paused && note.paused_from_status ? `<span class="badge hi">was: ${esc(note.paused_from_status)}</span>` : ""}
          <span class="time">${esc(note.time_str)}</span>
        </div>
        ${note.next_action ? `<div class="card-sub">→ ${esc(note.next_action)}</div>` : ""}
      </div>
    </div>
    ${note.snippet ? `<div class="drawer-section"><h3>Preview</h3>
      <div class="draft-text">${esc(note.snippet)}…</div></div>` : ""}
    <div class="drawer-section">
      <h3>Actions</h3>
      <div class="step-actions">
        <a class="btn" href="${obsidianLink(card.path)}">open in Obsidian</a>
        ${ACTIONS_ON ? `
          <button class="btn action" id="proj-launch">▶ take into agent</button>
          ${paused
            ? `<button class="btn approve" id="proj-unpause">unpause</button>`
            : `<button class="btn reject" id="proj-pause">pause</button>`}
        ` : ""}
      </div>
      <div class="card-sub" style="margin-top:8px">
        “take into agent” opens ${esc((toolList.find((t) => t.id === selectedTool) || {}).label || "your selected tool")}
        at the note's folder with a ready-made prompt.
      </div>
    </div>`;

  const launchBtn = $("#proj-launch");
  if (launchBtn) launchBtn.addEventListener("click", () =>
    launchAgent(card.path, launchPrompt));
  const pauseBtn = $("#proj-pause");
  if (pauseBtn) pauseBtn.addEventListener("click", async () => {
    try {
      await postJSON("/api/project/pause", { path: card.path });
      setStatus(`paused ${note.title}`);
      closeDrawer();
      loadAll();
    } catch (e) { setStatus(e.message, true); }
  });
  const unpauseBtn = $("#proj-unpause");
  if (unpauseBtn) unpauseBtn.addEventListener("click", async () => {
    try {
      const r = await postJSON("/api/project/unpause", { path: card.path });
      setStatus(`unpaused ${note.title} — back to ${r.status}`);
      closeDrawer();
      loadAll();
    } catch (e) { setStatus(e.message, true); }
  });
}

document.querySelectorAll("#pipeline-toggle .seg").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll("#pipeline-toggle .seg").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    pipelineSource = btn.dataset.source;
    renderPipeline(null);
  }));

/* ── agents view ─────────────────────────── */
function renderAgentsGrid(a) {
  const pa = a.pa;
  $("#agents-grid").innerHTML = `
    <div class="agent-card">
      <h3><span class="light ${pa.available ? "ok" : "down"}"></span>PA Agent
        <span class="agent-state">${pa.available ? "online" : "down"}</span></h3>
      <div class="agent-detail">last event ${esc(pa.last_event_str)}</div>
      <div class="agent-stats">
        <div class="stat"><b>${pa.total}</b>tasks</div>
        <div class="stat ${pa.pending_approvals ? "warn" : ""}"><b>${pa.pending_approvals}</b>approvals</div>
        <div class="stat ${pa.pending_clarifications ? "warn" : ""}"><b>${pa.pending_clarifications}</b>clarifications</div>
      </div>
    </div>
    <div class="agent-card">
      <h3><span class="light ${esc(a.capture.state)}"></span>Capture Bot
        <span class="agent-state">${esc(a.capture.state)}</span></h3>
      <div class="agent-detail">${esc(a.capture.detail)}</div>
    </div>
    <div class="agent-card">
      <h3><span class="light ${esc(a.maintenance.state)}"></span>Maintenance
        <span class="agent-state">${esc(a.maintenance.state)}</span></h3>
      <div class="agent-detail">${esc(a.maintenance.detail)}</div>
    </div>
    <div class="agent-card">
      <h3><span class="light planned"></span>Orchestrator
        <span class="agent-state">planned</span></h3>
      <div class="agent-detail">${esc(a.orchestrator.detail)}</div>
      <ul>${a.orchestrator.needs_building.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
    </div>`;
}

/* per-agent task panes */
let selectedAgent = "pa";
const agentPaneData = { tasks: [], captures: [], maintRuns: [], agents: null };

function selectAgent(key) {
  selectedAgent = key;
  document.querySelectorAll("#agent-switch .seg").forEach((b) =>
    b.classList.toggle("active", b.dataset.agent === key));
  renderAgentPane();
}
document.querySelectorAll("#agent-switch .seg").forEach((btn) =>
  btn.addEventListener("click", () => selectAgent(btn.dataset.agent)));

function renderAgentPane() {
  const pane = $("#agent-pane");
  const hint = $("#agent-pane-hint");

  if (selectedAgent === "pa") {
    hint.textContent = "click a task for detail";
    const tasks = agentPaneData.tasks;
    pane.innerHTML = tasks.length ? tasks.map((t) => `
      <div class="card clickable" data-task="${esc(t.task_id)}">
        <div class="card-title">${esc(t.user_request)}
          <span class="time">${esc(t.updated_str)}</span></div>
        <div class="card-meta">
          <span class="badge">${esc(t.stage)}</span>
          <span class="badge">${esc(t.status)}</span>
          ${t.pending_drafts ? `<span class="badge hi">${t.pending_drafts} pending</span>` : ""}
          <span class="hint">${t.approved_drafts || 0} approved · ${t.rejected_drafts || 0} rejected · ${t.total_drafts || 0} drafts</span>
        </div>
      </div>`).join("") : empty("no PA tasks yet");
    pane.querySelectorAll("[data-task]").forEach((el) =>
      el.addEventListener("click", () => openTask(el.dataset.task)));

  } else if (selectedAgent === "capture") {
    hint.textContent = "items processed by the second brain pipeline";
    const caps = agentPaneData.captures;
    pane.innerHTML = caps.length ? caps.map((c) => `
      <div class="card">
        <div class="card-title">
          ${c.output_path ? `<a href="${obsidianLink(vaultRel(c.output_path))}">${esc(c.output || c.name)}</a>` : esc(c.output || c.name)}
          <span class="time">${esc(c.time_str)}</span></div>
        <div class="card-sub">source: ${esc(c.name)}</div>
      </div>`).join("") : empty("no captures processed yet");

  } else if (selectedAgent === "maintenance") {
    hint.textContent = "vault maintenance runs";
    const runs = agentPaneData.maintRuns;
    pane.innerHTML = runs.length ? runs.map((r) => `
      <div class="card">
        <div class="card-title">Maintenance run
          ${r.dry_run ? `<span class="badge">dry run</span>` : ""}
          <span class="time">${esc(r.time_str)}</span></div>
        <div class="card-sub">scanned ${r.scanned} · ${r.issues} issues · fixed ${r.changed} · ${r.duplicates} duplicate groups</div>
        ${r.report_rel ? `<div class="card-meta"><a class="btn" href="${obsidianLink(r.report_rel)}">open report</a></div>` : ""}
      </div>`).join("") : empty("no maintenance runs recorded");

  } else {
    hint.textContent = "not built yet";
    const o = agentPaneData.agents ? agentPaneData.agents.orchestrator : null;
    pane.innerHTML = o ? `
      <div class="card"><div class="card-sub">${esc(o.detail)}</div></div>
      ${o.needs_building.map((n) => `<div class="card"><div class="card-title">${esc(n)}</div></div>`).join("")}`
      : empty("loading…");
  }
}

function vaultRel(absPath) {
  // second-brain records absolute output paths; strip the vault prefix
  const norm = absPath.replace(/\\/g, "/");
  const idx = norm.toLowerCase().indexOf("obsidianvault/");
  return idx >= 0 ? norm.slice(idx + "obsidianvault/".length) : norm;
}

/* ── code view ───────────────────────────── */
function renderCode(repos) {
  $("#code-grid").innerHTML = repos.length ? repos.map((r, i) => `
    <div class="repo-card">
      <h3>${esc(r.name)}
        ${r.branch ? `<span class="repo-branch">⎇ ${esc(r.branch)}</span>` : ""}</h3>
      ${r.last_commit
        ? `<div class="repo-commit">“${esc(r.last_commit)}” · ${esc(r.last_commit_str)}</div>`
        : `<div class="repo-commit">${r.is_git ? "no commits" : "not a git repo"}</div>`}
      <div class="repo-meta">
        ${r.is_git ? (r.dirty
          ? `<span class="badge dirty">${r.dirty} uncommitted</span>`
          : `<span class="badge clean">clean</span>`) : ""}
        ${r.github_url ? `<span class="badge"><a href="${esc(r.github_url)}" target="_blank" rel="noopener">github ↗</a></span>` : ""}
        ${ACTIONS_ON ? `<button class="btn" data-vscode="${i}">vs code</button>
        <button class="btn action" data-agent="${i}">▶ agent</button>` : ""}
      </div>
    </div>`).join("") : empty("no folders found in code root");

  document.querySelectorAll("[data-vscode]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const r = repos[Number(btn.dataset.vscode)];
      try {
        const res = await postJSON("/api/launch", { tool: "claude-vscode", path: r.path, prompt: "" });
        setStatus(res.note);
      } catch (e) { setStatus(e.message, true); }
    }));
  document.querySelectorAll("[data-agent]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const r = repos[Number(btn.dataset.agent)];
      launchAgent(r.path, "");
    }));
}

/* ── task drawer ─────────────────────────── */
async function openTask(taskId) {
  currentTaskId = taskId;
  drawerOpen = true;
  document.body.classList.add("drawer-open");
  $("#drawer-body").innerHTML = empty("loading…");
  try {
    const b = await getJSON(`/api/pa/task/${encodeURIComponent(taskId)}`);
    renderDrawer(b);
  } catch (e) {
    $("#drawer-body").innerHTML = empty(e.message);
  }
}

function draftBlock(d) {
  const actions = ACTIONS_ON && d.status === "pending" ? `
    <div class="card-meta">
      <button class="btn approve" data-approve="${esc(d.draft_id)}">approve</button>
      <button class="btn reject" data-reject="${esc(d.draft_id)}">reject</button>
    </div>` : "";
  return `
    <div class="card">
      <div class="card-title">${esc(d.contact_name || d.contact_id)}
        <span class="badge">${esc(d.channel)}</span>
        <span class="badge ${d.status === "approved" ? "shipped" : ""}">${esc(d.status)}</span>
        <span class="time">v${d.version}</span>
      </div>
      ${d.contact_org ? `<div class="card-sub">${esc(d.contact_org)}</div>` : ""}
      <div class="draft-text">${esc(d.status === "approved" ? d.approved_text : d.text)}</div>
      ${actions}
    </div>`;
}

function renderDrawer(b) {
  const t = b.task;
  $("#drawer-title").textContent = t.task_id;
  $("#drawer-body").innerHTML = `
    <div class="drawer-section">
      <h3>Request</h3>
      <div class="card"><div class="card-sub">${esc(t.user_request)}</div>
        <div class="card-meta"><span class="badge">${esc(t.stage)}</span>
        <span class="badge">${esc(t.status)}</span></div></div>
    </div>
    ${b.clarifications.length ? `<div class="drawer-section"><h3>Clarifications</h3>
      ${b.clarifications.map((c) => `<div class="card">
        <div class="card-sub">Q: ${esc(c.question)}</div>
        <div class="card-sub">A: ${esc(c.answer || "(awaiting answer)")}</div></div>`).join("")}</div>` : ""}
    <div class="drawer-section">
      <h3>Drafts (${b.drafts.length})</h3>
      ${b.drafts.length ? b.drafts.map(draftBlock).join("") : empty("no drafts")}
    </div>
    ${b.contacts.length ? `<div class="drawer-section"><h3>Contacts</h3>
      ${b.contacts.map((c) => `<div class="card">
        <div class="card-title">${esc(c.name)}<span class="time">${esc(c.confidence)}</span></div>
        <div class="card-sub">${esc([c.organization, c.email, c.phone, c.whatsapp].filter(Boolean).join(" · "))}</div>
      </div>`).join("")}</div>` : ""}
    ${b.sources.length ? `<div class="drawer-section"><h3>Sources (${b.sources.length})</h3>
      ${b.sources.map((s) => `<div class="card"><div class="card-title">
        <a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title || s.url)}</a>
        <span class="time">${esc(s.reliability)}</span></div></div>`).join("")}</div>` : ""}
    <div class="drawer-section">
      <h3>Audit Trail</h3>
      ${b.audit_events.map((e) => `<div class="audit-row">
        <span>${esc(e.action)}</span><span>${esc(e.actor)}</span>
        <span class="time">${esc(e.time_str)}</span></div>`).join("")}
    </div>
    ${t.obsidian_path ? `<div class="drawer-section">
      <a class="btn" href="${obsidianLink(t.obsidian_path)}">open task note in Obsidian</a></div>` : ""}
  `;

  document.querySelectorAll("[data-approve]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      if (!confirm("Approve this draft? The approved text becomes immutable.")) return;
      try {
        await postJSON(`/api/pa/draft/${btn.dataset.approve}/approve`);
        setStatus("draft approved");
        openTask(currentTaskId);
        loadAll();
      } catch (e) { setStatus(e.message, true); }
    }));
  document.querySelectorAll("[data-reject]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      const reason = prompt("Reason for rejection (optional):") ?? "";
      try {
        await postJSON(`/api/pa/draft/${btn.dataset.reject}/reject`, { reason });
        setStatus("draft rejected");
        openTask(currentTaskId);
        loadAll();
      } catch (e) { setStatus(e.message, true); }
    }));
}

function closeDrawer() {
  drawerOpen = false;
  currentTaskId = null;
  document.body.classList.remove("drawer-open");
}
$("#drawer-close").addEventListener("click", closeDrawer);
$("#drawer-scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

/* ── vault graph ─────────────────────────── */
const PALETTE = ["#00b8ff", "#00e676", "#a45af7", "#f5a623", "#f43f5e",
                 "#14b8a6", "#4d8ef8", "#f97316", "#eab308", "#ec4899"];
const TAG_COLOR = "#5a6a85";
let fg = null;            // ForceGraph instance
let rawGraph = null;      // data as served by the API
let folderColor = {};
let hoverNode = null;
let neighborIds = new Map();   // id -> Set(ids)
let showTags = true;

function graphSlice() {
  const nodes = rawGraph.nodes
    .filter((n) => showTags || n.type === "note")
    .map((n) => ({ ...n }));
  const links = rawGraph.links
    .filter((l) => showTags || l.type === "wiki")
    .map((l) => ({ ...l }));
  neighborIds = new Map();
  links.forEach((l) => {
    if (!neighborIds.has(l.source)) neighborIds.set(l.source, new Set());
    if (!neighborIds.has(l.target)) neighborIds.set(l.target, new Set());
    neighborIds.get(l.source).add(l.target);
    neighborIds.get(l.target).add(l.source);
  });
  return { nodes, links };
}

function nodeColorFor(n) {
  const base = n.type === "tag" ? TAG_COLOR : (folderColor[n.folder] || "#888");
  if (!hoverNode) return base;
  if (n.id === hoverNode.id) return "#ffffff";
  const nbrs = neighborIds.get(hoverNode.id);
  return nbrs && nbrs.has(n.id) ? base : base + "22";
}

function linkColorFor(l) {
  const sid = typeof l.source === "object" ? l.source.id : l.source;
  const tid = typeof l.target === "object" ? l.target.id : l.target;
  if (hoverNode && (sid === hoverNode.id || tid === hoverNode.id)) return "#00b8ffcc";
  return hoverNode ? "#2e3a5822" : "#2e3a5866";
}

function initGraph() {
  const el = $("#graph");
  fg = ForceGraph()(el)
    .backgroundColor("rgba(0,0,0,0)")
    .nodeId("id")
    .nodeLabel((n) => `${n.name}  ·  ${n.type === "tag" ? "tag" : n.folder}`)
    .nodeVal((n) => Math.max(1, Math.min(n.degree, 20)) * (n.type === "tag" ? 0.7 : 1))
    .nodeColor(nodeColorFor)
    .linkColor(linkColorFor)
    .linkWidth((l) => {
      const sid = typeof l.source === "object" ? l.source.id : l.source;
      const tid = typeof l.target === "object" ? l.target.id : l.target;
      return hoverNode && (sid === hoverNode.id || tid === hoverNode.id) ? 2 : 1;
    })
    .onNodeHover((n) => {
      hoverNode = n || null;
      el.style.cursor = n ? "pointer" : "";
      // continuous redraw only while hovering, so highlights animate
      // but an idle graph doesn't burn CPU
      fg.autoPauseRedraw(!n);
    })
    .onNodeClick((n) => {
      if (n.type === "note") window.location.href = obsidianLink(n.id);
      else fg.centerAt(n.x, n.y, 600);
    })
    .cooldownTicks(200)
    .onEngineStop(() => {
      if (!initGraph.fitted) { fg.zoomToFit(500, 40); initGraph.fitted = true; }
    });
  fg.d3Force("charge").strength(-45);

  const holder = $("#graph-holder");
  new ResizeObserver(() => {
    fg.width(holder.clientWidth).height(holder.clientHeight);
  }).observe(holder);
  fg.width(holder.clientWidth).height(holder.clientHeight);

  $("#graph-fit").addEventListener("click", () => fg.zoomToFit(500, 40));
  $("#graph-tags").addEventListener("change", (e) => {
    showTags = e.target.checked;
    fg.graphData(graphSlice());
    setTimeout(() => fg.zoomToFit(500, 40), 600);
  });
}

async function loadGraph() {
  rawGraph = await getJSON("/api/graph");
  rawGraph.folders.forEach((f, i) => { folderColor[f] = PALETTE[i % PALETTE.length]; });
  $("#graph-stats").textContent =
    `${rawGraph.note_count} notes · ${rawGraph.link_count} links · ${rawGraph.tag_count} tags`;
  $("#graph-legend").innerHTML = rawGraph.folders.map((f) => `
    <div class="legend-row"><span class="legend-swatch" style="background:${folderColor[f]}"></span>${esc(f)}</div>`)
    .join("") +
    `<div class="legend-row"><span class="legend-swatch" style="background:${TAG_COLOR}"></span>#tags</div>`;
  if (!fg) initGraph();
  fg.graphData(graphSlice());
  setTimeout(() => fg.zoomToFit(500, 40), 900);
}

/* ── vault health ────────────────────────── */
function renderHealth(rows) {
  $("#health-grid").innerHTML = rows.map((r) => `
    <div class="health-cell">
      <h4>${esc(r.folder)}</h4>
      <div class="stat"><b>${r.files}</b> files</div>
      <div class="stat">last activity ${esc(r.time_str)}</div>
    </div>`).join("");
}

/* ── tabs ────────────────────────────────── */
function switchView(view) {
  document.querySelectorAll(".nav-tab").forEach((t) =>
    t.classList.toggle("active", t.dataset.view === view));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  $(`#view-${view}`).classList.add("active");
  if (view === "vault" && !rawGraph) {
    loadGraph().catch((e) => setStatus(`graph failed: ${e.message}`, true));
  }
}
document.querySelectorAll(".nav-tab").forEach((tab) =>
  tab.addEventListener("click", () => switchView(tab.dataset.view)));

/* ── refresh loop ────────────────────────── */
async function loadAll() {
  try {
    const [summary, homeDigest, projects, inbox, board, agents, tasks, feed,
           health, code, captures, maintRuns] =
      await Promise.all([
        getJSON("/api/summary"), getJSON("/api/home"), getJSON("/api/projects"),
        getJSON("/api/inbox"), getJSON("/api/pipeline"), getJSON("/api/agents"),
        getJSON("/api/pa/tasks"), getJSON("/api/activity"), getJSON("/api/health"),
        getJSON("/api/code"), getJSON("/api/captures"), getJSON("/api/maintenance/runs"),
      ]);
    agentPaneData.tasks = tasks;
    agentPaneData.captures = captures;
    agentPaneData.maintRuns = maintRuns;
    agentPaneData.agents = agents;
    renderSummary(summary);
    renderHome(homeDigest);
    renderProjects(projects);
    renderInbox(inbox);
    renderPipeline(board);
    renderAgentsMini(agents);
    renderAgentsGrid(agents);
    renderAgentPane();
    renderActivity(feed);
    renderHealth(health);
    renderCode(code);
    $("#last-refresh").textContent = `refreshed ${new Date().toLocaleTimeString()}`;
    setStatus("ready");
  } catch (e) {
    setStatus(`refresh failed: ${e.message}`, true);
  }
}

function tickClock() {
  $("#clock").textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

async function boot() {
  try { toolList = await getJSON("/api/tools"); renderToolSelect(); }
  catch (e) { /* tools optional */ }
  loadAll();
}

setInterval(() => { if (!drawerOpen) loadAll(); }, REFRESH_MS);
setInterval(tickClock, 10000);
tickClock();
boot();
