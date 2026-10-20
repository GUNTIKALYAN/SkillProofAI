import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, emptyState, errorBox, formatScore, formatWhen, loadingNote } from "./render.js";

const user = await requireUser();
if (user && user.role !== "admin") window.location.replace("app.html");
if (user && user.role === "admin") start();

function start() {
  document.querySelectorAll("[data-panel]").forEach((button) => {
    button.addEventListener("click", () => openPanel(button.dataset.panel));
  });
  openPanel("overview");
}

async function openPanel(name) {
  const main = document.querySelector("#adminMain");
  document.querySelectorAll("[data-panel]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.panel === name);
    button.setAttribute("aria-current", button.dataset.panel === name ? "page" : "false");
  });
  clear(main);
  main.append(loadingNote("Loading..."));
  try {
    if (name === "overview") renderOverview(main, await api("/api/admin/overview"));
    if (name === "users") renderUsers(main, await api("/api/admin/users"));
    if (name === "traces") renderTraces(main, await api("/api/admin/traces"));
  } catch (err) {
    clear(main);
    main.append(errorBox(err.message || "Could not load this panel.", () => openPanel(name)));
  }
}

function renderOverview(main, body) {
  clear(main);
  main.append(el("h1", { text: "Overview" }));
  const grid = el("div", { className: "stat-grid" });
  const tiles = [
    ["Users", String(body.users)],
    ["Analyses", String(body.analyses)],
    ["Average score", formatScore(body.average_score)],
    ["Failed runs", String(body.failed)],
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
  clear(main);
  main.append(el("h1", { text: "Users" }));
  main.append(el("p", { className: "helper", text: "Admin accounts cannot be blocked or deleted." }));
  const label = el("label", { text: "Search by email", htmlFor: "userSearch" });
  const search = el("input", { id: "userSearch", type: "search", placeholder: "Email" });
  search.addEventListener("change", () => searchUsers(main, search.value));
  main.append(label, search);
  main.append(userTable(rows));
}

async function searchUsers(main, query) {
  const old = main.querySelector("table");
  try {
    const found = await api(`/api/admin/users?q=${encodeURIComponent(query)}`);
    const next = userTable(found);
    if (old) old.replaceWith(next);
    else main.append(next);
  } catch (err) {
    main.append(errorBox(err.message || "Could not search users.", () => searchUsers(main, query)));
  }
}

function userTable(rows) {
  const table = el("table", { className: "data-table" });
  table.append(rowEl("th", ["Email", "Role", "Status", "Analyses", "Chats", ""]));
  if (!rows.length) {
    const line = document.createElement("tr");
    const cell = el("td", { text: "No users found." });
    cell.colSpan = 6;
    line.append(cell);
    table.append(line);
    return table;
  }
  for (const person of rows) {
    const action = el("td");
    if (person.role === "admin") {
      action.append(el("span", { className: "helper", text: "Protected" }));
    } else {
      const block = el("button", {
        type: "button",
        className: "button button-quiet",
        text: person.status === "blocked" ? "Unblock" : "Block",
      });
      const remove = el("button", { type: "button", className: "button button-danger", text: "Delete" });
      block.addEventListener("click", () => changeUser(person, person.status === "blocked" ? "unblock" : "block"));
      remove.addEventListener("click", () => changeUser(person, "delete"));
      action.append(block, remove);
    }
    const line = rowEl("td", [
      person.email,
      person.role,
      person.status,
      String(person.analyses),
      String(person.chats),
    ]);
    line.append(action);
    table.append(line);
  }
  return table;
}

async function changeUser(person, action) {
  if (action === "delete") {
    const confirmed = window.confirm(`Delete ${person.email}? This cannot be undone.`);
    if (!confirmed) return;
  }
  const main = document.querySelector("#adminMain");
  try {
    if (action === "delete") {
      await api(`/api/admin/users/${person.id}`, { method: "DELETE" });
    } else {
      await api(`/api/admin/users/${person.id}/${action}`, { method: "POST" });
    }
    openPanel("users");
  } catch (err) {
    main.prepend(errorBox(err.message || "Could not update the user.", () => changeUser(person, action)));
  }
}

function renderTraces(main, rows) {
  clear(main);
  main.append(el("h1", { text: "Traces" }));
  if (!rows.length) {
    main.append(emptyState("No runs yet."));
    return;
  }
  const table = el("table", { className: "data-table" });
  table.append(rowEl("th", ["When", "User", "Status", ""]));
  for (const run of rows) {
    const open = el("button", { type: "button", className: "button button-quiet", text: "Open" });
    open.addEventListener("click", () => showTrace(run.id));
    const line = rowEl("td", [formatWhen(run.created_at), run.email, run.status]);
    const cell = el("td");
    cell.append(open);
    line.append(cell);
    table.append(line);
  }
  main.append(table);
  main.append(el("section", { id: "traceDetail", className: "card" }));
}

async function showTrace(id) {
  const detail = document.querySelector("#traceDetail");
  if (!detail) return;
  clear(detail);
  detail.append(loadingNote("Loading..."));
  let body;
  try {
    body = await api(`/api/admin/traces/${id}`);
  } catch (err) {
    clear(detail);
    detail.append(errorBox(err.message || "Could not open this trace.", () => showTrace(id)));
    return;
  }
  clear(detail);
  detail.append(el("h2", { text: body.status }));
  detail.append(el("p", { className: "file-name", text: body.skill_hash || "" }));
  const steps = body.steps || [];
  if (!steps.length) {
    detail.append(el("p", { text: "This run has no steps." }));
    return;
  }
  for (const step of steps) {
    const tool = step.tool ? ` / ${step.tool}` : "";
    detail.append(el("h3", { text: `${step.node}${tool}` }));
    detail.append(el("p", {
      className: "helper",
      text: `Attempt ${step.attempt}. ${step.tokens} tokens, ${step.latency_ms} ms.`,
    }));
    if (step.error) detail.append(el("p", { text: step.error }));
    if (step.output) detail.append(el("pre", { className: "file-name", text: JSON.stringify(step.output) }));
  }
}

function rowEl(tag, values) {
  const line = document.createElement("tr");
  for (const value of values) line.append(el(tag, { text: value }));
  return line;
}
