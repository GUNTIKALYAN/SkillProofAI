import { api } from "./api.js";
import { requireUser } from "./guard.js";
import {
  clear,
  el,
  emptyState,
  errorBox,
  externalLink,
  fillList,
  formatScore,
  formatWhen,
  limitMessage,
  loadingNote,
  safeHttpUrl,
} from "./render.js";

const MAX_BYTES = 5 * 1024 * 1024;
const MAX_JOBS = 10;
const POLL_MS = 2000;
const POLL_LIMIT = 150;
const VIEWS = ["new", "results", "history", "compare"];
const STEPS = ["GitHub", "Match score", "Experience check", "Skill audit", "Action plan"];

let currentId = "";

const user = await requireUser();
if (user) start();

function start() {
  const form = document.querySelector("#analyzeForm");
  const fileInput = document.querySelector("#resumeFile");
  fileInput.addEventListener("change", () => {
    document.querySelector("#fileName").textContent = fileInput.files[0] ? fileInput.files[0].name : "";
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAnalysis(form);
  });
  document.querySelectorAll("[data-view]").forEach((button) => {
    button.addEventListener("click", () => openView(button.dataset.view));
  });
  const fields = document.querySelector("#jobFields");
  addJobField(fields);
  addJobField(fields);
  document.querySelector("#addJob").addEventListener("click", () => {
    if (fields.querySelectorAll("textarea").length < MAX_JOBS) addJobField(fields);
  });
  document.querySelector("#compareForm").addEventListener("submit", (event) => {
    event.preventDefault();
    rankJobs(fields);
  });
  window.addEventListener("popstate", showFromLocation);
  showFromLocation();
}

function showFromLocation() {
  const id = new URLSearchParams(window.location.search).get("id");
  if (id) {
    currentId = id;
    showView("results");
    watch(id);
    return;
  }
  const hash = window.location.hash.replace("#", "");
  showView(VIEWS.includes(hash) ? hash : "new");
}

function openView(name) {
  if (name === "results" && currentId) {
    window.history.pushState(null, "", `app.html?id=${encodeURIComponent(currentId)}`);
    showView("results");
    return;
  }
  window.history.pushState(null, "", `app.html#${name}`);
  showView(name);
}

function showView(name) {
  for (const view of VIEWS) {
    document.querySelector(`#view-${view}`).hidden = view !== name;
    document.querySelector(`[data-view="${view}"]`).setAttribute("aria-selected", view === name ? "true" : "false");
  }
  if (name === "history") loadHistory();
  if (name === "results" && !currentId) showResultsEmpty();
}

async function submitAnalysis(form) {
  const error = document.querySelector("#formError");
  hideNote(error);
  const file = form.elements.resume.files[0];
  const jd = form.elements.jd_text.value.trim();
  const username = form.elements.github_username.value.trim();
  const problem = validate(file, jd, username);
  if (problem) {
    showNote(error, errorBox(problem));
    return;
  }
  const body = new FormData();
  body.append("resume", file);
  body.append("jd_text", jd);
  body.append("github_username", username);
  const button = form.querySelector("button[type=submit]");
  button.disabled = true;
  try {
    const accepted = await api("/api/analyses", { method: "POST", body });
    currentId = accepted.job_id;
    window.history.replaceState(null, "", `app.html?id=${encodeURIComponent(currentId)}`);
    showView("results");
    await watch(currentId);
  } catch (err) {
    const message = err.status === 429 ? limitMessage(err) : (err.message || "Could not start the analysis.");
    showNote(error, errorBox(message, () => submitAnalysis(form)));
  } finally {
    button.disabled = false;
  }
}

function validate(file, jd, username) {
  if (!file) return "Choose a PDF or DOCX resume.";
  const name = file.name.toLowerCase();
  if (!name.endsWith(".pdf") && !name.endsWith(".docx")) return "Resume must be a PDF or DOCX file.";
  if (file.size > MAX_BYTES) return "Resume must be 5 MB or smaller.";
  if (jd.length < 10) return "Paste a job description of at least 10 characters.";
  if (!username) return "Enter a GitHub username.";
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(username)) return "GitHub username is invalid.";
  return "";
}

async function watch(id) {
  const progress = document.querySelector("#progress");
  const results = document.querySelector("#results");
  clear(results);
  for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
    let row;
    try {
      row = await api(`/api/analyses/${encodeURIComponent(id)}`);
    } catch (err) {
      progress.hidden = false;
      clear(progress);
      progress.append(errorBox(err.message || "Could not load this analysis.", () => watch(id)));
      return;
    }
    if (row.status === "completed" || row.status === "failed") {
      progress.hidden = true;
      clear(progress);
      renderResult(id, row);
      return;
    }
    progress.hidden = false;
    clear(progress);
    progress.append(loadingNote("Analysing..."));
    progress.append(el("p", {
      text: row.status === "running" ? "The checks below are running." : "Your analysis is queued.",
    }));
    const list = el("ul", { className: "plain-list" });
    for (const step of STEPS) list.append(el("li", { text: step }));
    progress.append(list);
    await delay(POLL_MS);
  }
  clear(progress);
  progress.append(errorBox("This is taking longer than expected.", () => watch(id)));
}

function showResultsEmpty() {
  const results = document.querySelector("#results");
  document.querySelector("#progress").hidden = true;
  clear(results);
  results.append(emptyState("No analysis open. Run your first one.", "New analysis", () => openView("new")));
}

async function renderResult(id, row) {
  const root = document.querySelector("#results");
  clear(root);
  const result = row.result || {};
  root.append(el("p", { className: "helper", text: formatWhen(row.created_at) }));
  if (row.status === "failed" || result.error) {
    root.append(errorBox(result.error || "Analysis failed.", () => openView("new")));
  }
  if (result.partial) {
    root.append(el("p", { className: "banner banner-warn", text: "Some checks could not run." }));
  }
  const layout = el("div", { className: "results-layout" });
  const score = scoreCard(result);
  score.classList.add("span-2");
  layout.append(score);
  layout.append(auditCard(result.audit || []));
  layout.append(planCard(id, result.action_plan, result.checked_steps || []));
  const experience = experienceCard(id, result);
  experience.classList.add("span-2");
  layout.append(experience);
  layout.append(githubCard(result));
  root.append(layout);
  await showScoreChange(root, id, row.score);
}

async function showScoreChange(root, id, score) {
  if (typeof score !== "number") return;
  let rows;
  try {
    rows = await api("/api/analyses");
  } catch {
    return;
  }
  const done = rows.filter((item) => item.status === "completed" && typeof item.score === "number");
  const index = done.findIndex((item) => item.id === id);
  const previous = done[index + 1];
  if (!previous) return;
  root.append(el("p", {
    className: "helper",
    text: `Previous score ${formatScore(previous.score)}. This score ${formatScore(score)}.`,
  }));
}

function scoreCard(result) {
  const card = el("section", { className: "card" });
  card.append(el("h2", { text: "JD Match Score" }));
  const score = result.jd_match_score || {};
  const value = typeof score.score === "number" ? score.score : null;
  const row = el("div", { className: "score-row" });
  row.append(el("p", { className: "score", text: formatScore(value) }));
  const track = el("div", { className: "score-track" });
  const fill = el("div", { className: "score-fill" });
  fill.style.width = `${barPercent(value)}%`;
  track.append(fill);
  row.append(track);
  card.append(row);
  card.append(el("p", {
    className: "helper",
    text: "This is a match against this job description. It is not an employer ATS score.",
  }));
  const lines = (score.breakdown || []).map((item) => {
    const points = typeof item.points === "number" ? item.points : "";
    return `${item.skill || "Skill"} (${item.priority || "skill"}, ${points}): ${item.reason || ""}`;
  });
  fillList(card, lines, "No skill breakdown was saved.");
  return card;
}

function barPercent(score) {
  if (typeof score !== "number") return 0;
  if (score <= 1) return Math.round(score * 100);
  return Math.min(100, Math.round(score));
}

function auditCard(items) {
  const card = el("section", { className: "card" });
  card.append(el("h2", { text: "Skill audit" }));
  const grid = el("div", { className: "grid" });
  for (const status of ["matched", "partial", "missing"]) {
    const column = el("div");
    column.append(el("h3", { text: status[0].toUpperCase() + status.slice(1) }));
    const skills = items.filter((item) => item.status === status && item.skill !== "experience");
    if (!skills.length) column.append(el("p", { className: "helper", text: "None" }));
    for (const item of skills) {
      const line = el("div", { className: "skill-row" });
      line.append(el("span", { className: `badge badge-${status}`, text: status }));
      line.append(el("strong", { text: item.skill || "Skill" }));
      line.append(el("p", { className: "helper", text: item.reason || "" }));
      column.append(line);
    }
    grid.append(column);
  }
  card.append(grid);
  return card;
}

function planCard(id, plan, checks) {
  const card = el("section", { className: "card" });
  card.append(el("h2", { text: "Action plan" }));
  const items = (plan && plan.items) || [];
  if (!items.length) {
    card.append(el("p", { className: "helper", text: "No gaps, so no action plan was created." }));
    return card;
  }
  for (const item of items) {
    const skill = item.skill || "Skill";
    card.append(el("h3", { text: skill }));
    for (const step of item.steps || []) card.append(stepCheck(id, skill, step, checks));
    const resources = item.resources || [];
    if (!resources.length) continue;
    const list = el("ul", { className: "plain-list" });
    for (const resource of resources) {
      const line = el("li");
      line.append(resourceNode(String(resource)));
      list.append(line);
    }
    card.append(list);
  }
  card.append(el("p", {
    className: "helper",
    text: "Ticking a step does not change the score. Run a new analysis after you do the work.",
  }));
  const again = el("button", { type: "button", className: "button button-quiet", text: "New analysis" });
  again.addEventListener("click", () => openView("new"));
  card.append(again);
  return card;
}

function stepCheck(id, skill, step, checks) {
  const label = el("label", { className: "check" });
  const box = el("input", {
    type: "checkbox",
    checked: checks.some((item) => item.skill === skill && item.step === step),
  });
  const note = el("span", { className: "helper", text: "" });
  box.addEventListener("change", async () => {
    try {
      await api(`/api/analyses/${encodeURIComponent(id)}/plan`, {
        method: "PATCH",
        json: { skill, step, done: box.checked },
      });
      note.textContent = box.checked ? "Saved." : "";
    } catch (err) {
      box.checked = !box.checked;
      note.textContent = err.message || "Could not save this step.";
    }
  });
  label.append(box, el("span", { text: step }), note);
  return label;
}

function resourceNode(resource) {
  if (safeHttpUrl(resource)) return externalLink(resource, resource);
  return el("span", { text: resource });
}

function experienceCard(id, result) {
  const card = el("section", { className: "card" });
  card.append(el("h2", { text: "Experience signals" }));
  card.append(el("p", {
    className: "helper",
    text: "Dates, bullet claims, and company names are signals. They do not change the JD Match Score.",
  }));
  if (result.experience_error) {
    card.append(el("p", { text: "The experience check could not run." }));
  } else if (result.experience_skipped) {
    card.append(el("p", { text: "This resume has no Experience section, so the check was skipped." }));
  }
  card.append(el("h3", { text: "Date checks" }));
  fillList(card, dateIssues(result), "No date issues.");
  card.append(el("h3", { text: "Bullet claims" }));
  fillList(card, unsupportedClaims(result), "No bullet claims lacked supporting evidence.");
  card.append(el("h3", { text: "Companies" }));
  const companies = (result.experience && result.experience.companies) || result.companies || [];
  if (!companies.length) {
    card.append(el("p", { className: "helper", text: "No companies were checked." }));
    if (!result.experience_skipped && !result.experience_error) card.append(urlForm(id, ""));
    return card;
  }
  for (const company of companies) {
    const block = el("div", { className: "company" });
    block.append(el("strong", { text: company.name || "Company" }));
    block.append(el("p", { className: "helper", text: companyStatus(company.status) }));
    const saved = savedUrl(result, company.name);
    if (saved) block.append(externalLink(saved, saved));
    card.append(block);
    card.append(urlForm(id, company.name || ""));
  }
  return card;
}

function dateIssues(result) {
  const experience = result.experience;
  if (experience && Array.isArray(experience.flags)) {
    return experience.flags.filter((flag) => flag.kind === "date").map((flag) => flag.detail || "");
  }
  return (result.audit || [])
    .filter((item) => item.skill === "experience" && !/not supported/i.test(item.reason || ""))
    .map((item) => item.reason || "");
}

function unsupportedClaims(result) {
  const fromFlags = ((result.experience || {}).flags || [])
    .filter((flag) => flag.kind === "unsupported")
    .map((flag) => flag.detail || "");
  const fromAudit = (result.audit || [])
    .filter((item) => item.skill === "experience" && /not supported/i.test(item.reason || ""))
    .map((item) => item.reason || "");
  return [...new Set([...fromFlags, ...fromAudit])];
}

function companyStatus(status) {
  if (status === "found") return "A public page mentions this name. That is not proof of employment.";
  if (status === "not_found") return "No public page was found for this name. The score is unchanged.";
  if (status === "ambiguous") return "Public results for this name were not clear. The score is unchanged.";
  return "The company check did not run. The score is unchanged.";
}

function savedUrl(result, name) {
  const key = String(name || "").trim().toLowerCase();
  const match = (result.company_urls || []).find((item) => String(item.name || "").trim().toLowerCase() === key);
  return match ? match.url : "";
}

function urlForm(id, name) {
  const form = el("form", { className: "url-form" });
  let nameInput = null;
  if (!name) {
    const nameLabel = el("label", { text: "Company name" });
    nameInput = el("input", { type: "text", maxLength: 120 });
    nameLabel.append(nameInput);
    form.append(nameLabel);
  }
  const urlLabel = el("label", { text: name ? `Website for ${name}` : "Company website" });
  const urlInput = el("input", { type: "url", placeholder: "https://", maxLength: 300 });
  urlLabel.append(urlInput);
  const button = el("button", { type: "submit", className: "button button-quiet", text: "Save URL" });
  const note = el("p", {
    className: "helper",
    text: "Saved with this analysis only. It does not change the JD Match Score.",
  });
  form.append(urlLabel, button, note);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const companyName = (name || (nameInput ? nameInput.value : "")).trim();
    const url = urlInput.value.trim();
    if (!companyName || !url) {
      note.textContent = "Enter a company name and an http(s) URL.";
      return;
    }
    try {
      await api(`/api/analyses/${encodeURIComponent(id)}/company-url`, {
        method: "PATCH",
        json: { name: companyName, url },
      });
      note.textContent = "Saved.";
    } catch (err) {
      note.textContent = err.message || "Could not save the URL.";
    }
  });
  return form;
}

function githubCard(result) {
  const card = el("section", { className: "card" });
  card.append(el("h2", { text: "GitHub signal" }));
  card.append(el("p", { className: "helper", text: "Public repository activity is a signal, not proof." }));
  if (result.github_error) {
    card.append(el("p", { text: "GitHub could not be read for this run." }));
    return card;
  }
  if (result.github_skipped) {
    card.append(el("p", { text: "GitHub was not included." }));
    return card;
  }
  if (!result.github) {
    card.append(el("p", { text: "No GitHub signal was saved for this run." }));
    return card;
  }
  const repos = result.github.repos || [];
  const lines = repos.map((repo) => {
    const language = repo.language ? ` (${repo.language})` : "";
    return `${repo.name || "Repository"}${language}`;
  });
  fillList(card, lines, "No public repositories were returned.");
  return card;
}

async function loadHistory() {
  const list = document.querySelector("#historyList");
  const trend = document.querySelector("#trend");
  clear(list);
  list.append(loadingNote("Loading..."));
  let rows;
  try {
    rows = await api("/api/analyses");
  } catch (err) {
    clear(list);
    list.append(errorBox(err.message || "Could not load history.", loadHistory));
    return;
  }
  renderTrend(trend, rows);
  clear(list);
  if (!rows.length) {
    list.append(emptyState("No analyses yet. Run your first one.", "New analysis", () => openView("new")));
    return;
  }
  for (const row of rows) list.append(historyRow(row));
}

function renderTrend(trend, rows) {
  clear(trend);
  const scored = rows.filter((row) => typeof row.score === "number").slice().reverse();
  const note = document.querySelector("#trendNote");
  if (scored.length < 2) {
    note.textContent = "Run another analysis to see a trend.";
  } else {
    note.textContent = "Oldest to newest. Each bar is that analysis's JD Match Score.";
  }
  for (const row of scored) {
    const track = el("div", { className: "bar-track" });
    const bar = el("div", { className: "bar" });
    bar.style.height = `${barPercent(row.score)}%`;
    bar.title = `${formatScore(row.score)} on ${formatWhen(row.created_at)}`;
    track.append(bar);
    trend.append(track);
  }
}

function historyRow(row) {
  const link = el("a", { className: "history-row" });
  link.href = `app.html?id=${encodeURIComponent(row.id)}`;
  const status = ["queued", "running", "completed", "failed"].includes(row.status) ? row.status : "queued";
  link.append(el("span", { text: formatWhen(row.created_at) }));
  link.append(el("span", { className: `badge badge-${status}`, text: status }));
  link.append(el("span", { text: formatScore(row.score) }));
  link.append(el("span", { className: "helper", text: row.github_username || "No GitHub" }));
  return link;
}

function addJobField(fields) {
  const index = fields.querySelectorAll("textarea").length + 1;
  const label = el("label", { text: `Job ${index}` });
  const input = el("textarea", { name: "job", required: true, placeholder: "Paste a job description." });
  label.append(input);
  fields.append(label);
}

async function rankJobs(fields) {
  const error = document.querySelector("#compareError");
  const result = document.querySelector("#compareResult");
  hideNote(error);
  const jobs = [...fields.querySelectorAll("textarea")].map((node) => node.value.trim()).filter(Boolean);
  if (jobs.length < 2) {
    showNote(error, errorBox("Add at least two job descriptions."));
    return;
  }
  try {
    const body = await api("/api/compare", { method: "POST", json: { job_descriptions: jobs } });
    result.hidden = false;
    clear(result);
    result.append(el("h2", { text: "Ranked by JD Match Score" }));
    const list = el("ol", { className: "plain-list" });
    for (const job of body.ranked) {
      list.append(el("li", { text: `${formatScore(job.score)} — ${job.preview}` }));
    }
    result.append(list);
    const unlock = body.unlock_skill
      ? `${body.unlock_skill} is the skill that unlocks the most of these jobs (${body.unlock_jobs}).`
      : "No missing skill is shared across these jobs.";
    result.append(el("p", { text: unlock }));
  } catch (err) {
    const message = err.status === 429 ? limitMessage(err) : (err.message || "Could not compare these jobs.");
    showNote(error, errorBox(message, () => rankJobs(fields)));
  }
}

function showNote(node, child) {
  clear(node);
  node.hidden = false;
  node.append(child);
}

function hideNote(node) {
  node.hidden = true;
  clear(node);
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
