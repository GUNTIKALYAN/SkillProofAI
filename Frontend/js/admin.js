import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, formatScore, formatWhen } from "./render.js";

const user = await requireUser();
if (user && user.role !== "admin") window.location.replace("app.html");
if (user && user.role === "admin") start();

function start() {
  const main = document.querySelector("#adminMain");
  document.querySelectorAll("[data-panel]").forEach((button) => {
    button.addEventListener("click", () => openPanel(main, button.dataset.panel));
  });
  openPanel(main, "overview");
}

async function openPanel(main, name) {
  clear(main);
  const error = el("p", { className: "banner banner-error", text: "" });
  error.hidden = true;
  main.append(error);
  try {
    if (name === "overview") renderOverview(main, await api("/api/admin/overview"));
    if (name === "users") renderUsers(main, await api("/api/admin/users"));
    if (name === "traces") renderTraces(main, await api("/api/admin/traces"));
    if (name === "limits") renderLimits(main, await api("/api/admin/rate-limits"));
    if (name === "skills") renderSkills(main, await api("/api/admin/unknown-skills"));
    if (name === "audit") renderAudit(main, await api("/api/admin/audit"));
    if (name === "agents") renderAgents(main, await api("/api/admin/agents"));
  } catch (err) {
    error.hidden = false;
    error.textContent = err.message || "Could not load this panel.";
  }
}

function renderOverview(main, body) {
  main.append(el("h1", { text: "Overview" }));
  const grid = el("div", { className: "stat-grid" });
  const tiles = [
    ["Users", String(body.users)],
    ["Analyses today", String(body.analyses_today)],
    ["Average score", formatScore(body.average_score)],
    ["Error rate", `${Math.round(body.error_rate * 100)}%`],
    ["Tokens", String(body.tokens)],
    ["p95 latency", `${body.p95_latency_ms} ms`],
  ];
  for (const [label, value] of tiles) {
    const card = el("section", { className: "card" });
    card.append(el("p", { className: "helper", text: label }));
    card.append(el("p", { className: "stat-value", text: value }));
    grid.append(card);
  }
  main.append(grid);
}

function renderUsers(main, rows) {
  main.append(el("h1", { text: "Users" }));
  const search = el("input", { type: "search", placeholder: "Search email" });
  search.addEventListener("change", async () => {
    const found = await api(`/api/admin/users?q=${encodeURIComponent(search.value)}`);
    const old = main.querySelector("table");
    if (old) old.replaceWith(userTable(found));
  });
  main.append(search, userTable(rows));
}

function userTable(rows) {
  const table = el("table", { className: "data-table" });
  table.append(rowEl("th", ["Email", "Role", "Status", "Analyses", "Chats", "Tokens", ""]));
  for (const user of rows) {
    const action = el("td");
    if (user.role !== "admin") {
      const block = el("button", {
        type: "button",
        className: "button button-quiet",
        text: user.status === "blocked" ? "Unblock" : "Block",
      });
      const remove = el("button", { type: "button", className: "button button-quiet", text: "Delete" });
      block.addEventListener("click", () => changeUser(user, block.textContent === "Block" ? "block" : "unblock"));
      remove.addEventListener("click", () => changeUser(user, "delete"));
      action.append(block, remove);
    }
    const line = rowEl("td", [
      user.email,
      user.role,
      user.status,
      String(user.analyses),
      String(user.chats),
      String(user.tokens),
    ]);
    line.append(action);
    table.append(line);
  }
  return table;
}

async function changeUser(user, action) {
  const main = document.querySelector("#adminMain");
  try {
    if (action === "delete") {
      await api(`/api/admin/users/${user.id}`, { method: "DELETE" });
    } else {
      await api(`/api/admin/users/${user.id}/${action}`, { method: "POST" });
    }
    openPanel(main, "users");
  } catch (err) {
    main.prepend(el("p", { className: "banner banner-error", text: err.message || "Could not update the user." }));
  }
}

function renderTraces(main, rows) {
  main.append(el("h1", { text: "Traces" }));
  const table = el("table", { className: "data-table" });
  table.append(rowEl("th", ["When", "User", "Status", ""]));
  for (const run of rows) {
    const open = el("button", { type: "button", className: "button button-quiet", text: "Open" });
    open.addEventListener("click", () => showTrace(main, run.id));
    const line = rowEl("td", [formatWhen(run.created_at), run.email, run.status]);
    const cell = el("td");
    cell.append(open);
    line.append(cell);
    table.append(line);
  }
  main.append(table);
  main.append(el("section", { id: "traceDetail", className: "card" }));
}

async function showTrace(main, id) {
  const detail = main.querySelector("#traceDetail");
  clear(detail);
  const body = await api(`/api/admin/traces/${id}`);
  detail.append(el("h2", { text: body.status }));
  detail.append(el("p", { className: "helper", text: body.skill_hash }));
  for (const step of body.steps) {
    const tool = step.tool ? ` / ${step.tool}` : "";
    detail.append(el("h3", { text: `${step.node}${tool}` }));
    detail.append(el("p", { className: "helper", text: `${step.tokens} tokens, ${step.latency_ms} ms` }));
    if (step.error) detail.append(el("p", { text: step.error }));
    if (step.output) detail.append(el("p", { text: JSON.stringify(step.output) }));
  }
}

function renderLimits(main, body) {
  main.append(el("h1", { text: "Rate limits" }));
  main.append(el("h2", { text: "Top users" }));
  const list = el("ul", { className: "plain-list" });
  for (const row of body.top_users) list.append(el("li", { text: `${row.email}: ${row.hits}` }));
  if (!body.top_users.length) list.append(el("li", { text: "No limit hits yet." }));
  main.append(list);
  main.append(el("h2", { text: "Recent hits" }));
  for (const hit of body.hits) {
    main.append(el("p", { text: `${formatWhen(hit.at)} ${hit.target || ""}` }));
  }
}

function renderSkills(main, rows) {
  main.append(el("h1", { text: "Unknown skills" }));
  main.append(el("p", { className: "helper", text: "Approve adds a skill. Alias and merge point the name at a skill already in the graph." }));
  for (const skill of rows) {
    const card = el("section", { className: "card" });
    card.append(el("h2", { text: skill.name }));
    card.append(el("p", { className: "helper", text: `${skill.status}, seen ${skill.seen_count}` }));
    if (skill.alias_of) card.append(el("p", { text: skill.alias_of }));
    if (skill.status === "pending") card.append(skillActions(skill));
    main.append(card);
  }
}

function skillActions(skill) {
  const wrap = el("div");
  const canonical = el("input", { type: "text", placeholder: "Existing skill name", maxLength: 80 });
  const approve = el("button", { type: "button", className: "button button-primary", text: "Approve" });
  const alias = el("button", { type: "button", className: "button button-quiet", text: "Alias" });
  const merge = el("button", { type: "button", className: "button button-quiet", text: "Merge" });
  const note = el("p", { className: "helper", text: "" });
  approve.addEventListener("click", () => review(skill, "approve", "", note));
  alias.addEventListener("click", () => review(skill, "alias", canonical.value, note));
  merge.addEventListener("click", () => review(skill, "merge", canonical.value, note));
  wrap.append(canonical, approve, alias, merge, note);
  return wrap;
}

async function review(skill, action, canonical, note) {
  try {
    const options = { method: "POST" };
    if (action !== "approve") options.json = { canonical };
    await api(`/api/admin/unknown-skills/${skill.id}/${action}`, options);
    openPanel(document.querySelector("#adminMain"), "skills");
  } catch (err) {
    note.textContent = err.message || "Could not update this skill.";
  }
}

function renderAudit(main, rows) {
  main.append(el("h1", { text: "Audit log" }));
  const table = el("table", { className: "data-table" });
  table.append(rowEl("th", ["When", "Action", "Target"]));
  for (const row of rows) table.append(rowEl("td", [formatWhen(row.at), row.action, row.target || ""]));
  main.append(table);
}

function renderAgents(main, rows) {
  main.append(el("h1", { text: "Agents" }));
  for (const skill of rows) {
    const card = el("section", { className: "card" });
    card.append(el("h2", { text: skill.name }));
    card.append(el("p", { text: skill.description }));
    card.append(el("p", { className: "helper", text: skill.tools.join(", ") }));
    card.append(el("p", { className: "file-name", text: skill.hash }));
    main.append(card);
  }
}

function rowEl(tag, values) {
  const line = document.createElement("tr");
  for (const value of values) line.append(el(tag, { text: value }));
  return line;
}
