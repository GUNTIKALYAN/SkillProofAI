import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, externalLink, fillList, formatScore, formatWhen, safeHttpUrl } from "./render.js";

const MAX_BYTES = 5 * 1024 * 1024;
const POLL_MS = 2000;
const POLL_LIMIT = 150;

const user = await requireUser();
if (user) start();

function start() {
  const params = new URLSearchParams(window.location.search);
  const existing = params.get("id");
  const form = document.querySelector("#analyzeForm");
  const fileInput = document.querySelector("#resumeFile");
  fileInput.addEventListener("change", () => {
    document.querySelector("#fileName").textContent = fileInput.files[0] ? fileInput.files[0].name : "";
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    submitAnalysis(form);
  });
  if (existing) {
    document.querySelector("#composer").hidden = true;
    watch(existing);
  }
}

async function submitAnalysis(form) {
  const error = document.querySelector("#formError");
  error.hidden = true;
  const file = form.elements.resume.files[0];
  const jd = form.elements.jd_text.value.trim();
  const username = form.elements.github_username.value.trim();
  const problem = validate(file, jd, username);
  if (problem) {
    error.hidden = false;
    error.textContent = problem;
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
    window.history.replaceState(null, "", `app.html?id=${encodeURIComponent(accepted.job_id)}`);
    document.querySelector("#composer").hidden = true;
    await watch(accepted.job_id);
  } catch (err) {
    error.hidden = false;
    error.textContent = err.status === 429
      ? `Too many analyses. Try again in ${err.retryAfter || 60} seconds.`
      : (err.message || "Could not start the analysis");
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
  if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(username)) {
    return "GitHub username is invalid.";
  }
  return "";
}

async function watch(id) {
  const progress = document.querySelector("#progress");
  const status = document.querySelector("#progressStatus");
  for (let attempt = 0; attempt < POLL_LIMIT; attempt += 1) {
    let row;
    try {
      row = await api(`/api/analyses/${encodeURIComponent(id)}`);
    } catch (err) {
      progress.hidden = false;
      status.textContent = err.message || "Could not load this analysis.";
      return;
    }
    if (row.status === "completed" || row.status === "failed") {
      progress.hidden = true;
      renderResult(id, row);
      return;
    }
    progress.hidden = false;
    status.textContent = row.status === "running"
      ? "Reading the resume, scoring skills, and writing the plan."
      : "Your analysis is queued.";
    await delay(POLL_MS);
  }
  status.textContent = "This is taking longer than expected. Open History to check it later.";
}

async function renderResult(id, row) {
  const root = document.querySelector("#results");
  root.hidden = false;
  clear(root);
  const result = row.result || {};
  root.append(el("p", { className: "helper", text: formatWhen(row.created_at) }));
  if (row.status === "failed" || result.error) {
    const banner = el("p", { className: "banner banner-error", text: result.error || "Analysis failed" });
    root.append(banner);
  }
  if (result.partial) {
    root.append(el("p", { className: "banner", text: "This result is incomplete." }));
  }
  root.append(scoreCard(result));
  await showScoreChange(root, id, row.score);
  root.append(auditCard(result.audit || []));
  root.append(planCard(id, result.action_plan, result.checked_steps || []));
  root.append(experienceCard(id, result));
  root.append(githubCard(result));
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
  card.append(el("p", { className: "score", text: formatScore(score.score) }));
  card.append(el("p", { className: "helper", text: "This is a match against this job description. It is not an employer ATS score." }));
  const lines = (score.breakdown || []).map((item) => {
    const points = typeof item.points === "number" ? item.points : "";
    return `${item.skill || "Skill"} (${item.priority || "skill"}, ${points}): ${item.reason || ""}`;
  });
  fillList(card, lines, "No skill breakdown was saved.");
  return card;
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
      const row = el("div", { className: "skill-row" });
      row.append(el("strong", { text: item.skill || "Skill" }));
      row.append(el("p", { className: "helper", text: item.reason || "" }));
      column.append(row);
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
    text: "Ticking a step does not change the score. Re-analyse after you do the work.",
  }));
  const again = el("a", { className: "button button-quiet", text: "Re-analyse" });
  again.href = "app.html";
  card.append(again);
  return card;
}

function stepCheck(id, skill, step, checks) {
  const label = el("label", { className: "check" });
  const box = document.createElement("input");
  box.type = "checkbox";
  box.checked = checks.some((item) => item.skill === skill && item.step === step);
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
  if (result.experience_skipped) {
    card.append(el("p", { text: "This resume has no Experience section, so the check was skipped." }));
  }
  card.append(el("h3", { text: "Date issues" }));
  fillList(card, dateIssues(result), "No date issues.");
  card.append(el("h3", { text: "Unsupported bullet claims" }));
  fillList(card, unsupportedClaims(result), "No unsupported bullet claims.");
  card.append(el("h3", { text: "Companies" }));
  const companies = (result.experience && result.experience.companies) || result.companies || [];
  if (!companies.length) {
    card.append(el("p", { className: "helper", text: "No companies were checked." }));
    if (!result.experience_skipped) card.append(urlForm(id, ""));
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
  if (status === "found") return "A public web page was found.";
  if (status === "not_found") return "Couldn't find a public web presence.";
  if (status === "ambiguous") return "Public results were ambiguous.";
  return "The company check was skipped.";
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
    nameInput = el("input", { type: "text", placeholder: "Company name", maxLength: 120 });
    form.append(nameInput);
  }
  const urlInput = el("input", { type: "url", placeholder: "Company website (optional)", maxLength: 300 });
  const button = el("button", { type: "submit", className: "button button-quiet", text: "Save URL" });
  const note = el("p", {
    className: "helper",
    text: "Saved with this analysis. It does not change the JD Match Score.",
  });
  form.append(urlInput, button, note);
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
  if (result.github_skipped) {
    card.append(el("p", { text: "GitHub was not included." }));
    return card;
  }
  if (!result.github) {
    card.append(el("p", { text: "No GitHub signal was saved for this run." }));
    return card;
  }
  card.append(el("p", { className: "helper", text: "Public repository activity is a signal, not verification." }));
  const repos = (result.github && result.github.repos) || [];
  const lines = repos.map((repo) => {
    const language = repo.language ? ` (${repo.language})` : "";
    return `${repo.name || "Repository"}${language}`;
  });
  fillList(card, lines, "No public repositories were returned.");
  return card;
}

function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
