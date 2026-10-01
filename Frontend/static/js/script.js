function apiBase() {
  const host = window.location.hostname;
  if (host === "localhost" || host === "127.0.0.1") {
    return "http://127.0.0.1:8000/api";
  }
  if (host.endsWith(".onrender.com")) {
    return `${window.location.origin}/api`;
  }
  return "https://skillproofai.onrender.com/api";
}

const API_BASE = apiBase();

const STATUS_LABEL = {
  supported: "Supported",
  partially_supported: "Partial evidence",
  unsupported: "Not found",
  needs_review: "Needs review"
};

const STATUS_ORDER = {
  unsupported: 0,
  needs_review: 1,
  partially_supported: 2,
  supported: 3
};

const fileDropZone = document.getElementById("fileDropZone");
const resumeFileInput = document.getElementById("resumeFile");
const fileSelected = document.getElementById("fileSelected");
const fileName = document.getElementById("fileName");
const removeFileBtn = document.getElementById("removeFile");
const resumeError = document.getElementById("resumeError");
const jobDescription = document.getElementById("jobDescription");
const jdError = document.getElementById("jdError");
const jdCount = document.getElementById("jdCount");
const analyzeForm = document.getElementById("analyzeForm");
const analyzeBtn = document.getElementById("analyzeBtn");
const formError = document.getElementById("formError");
const formErrorText = document.getElementById("formErrorText");
const inputView = document.getElementById("inputView");
const loadingView = document.getElementById("loadingView");
const reportView = document.getElementById("reportView");

let selectedFile = null;
let skillRows = [];
let activeFilter = "all";
let lastGithubUsed = false;

fileDropZone.addEventListener("click", event => {
  if (event.target === resumeFileInput || event.target.closest("#removeFile")) return;
  resumeFileInput.click();
});

fileDropZone.addEventListener("keydown", event => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    resumeFileInput.click();
  }
});

["dragover", "dragenter"].forEach(name => {
  fileDropZone.addEventListener(name, event => {
    event.preventDefault();
    fileDropZone.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach(name => {
  fileDropZone.addEventListener(name, event => {
    event.preventDefault();
    fileDropZone.classList.remove("drag-over");
  });
});

fileDropZone.addEventListener("drop", event => {
  const file = event.dataTransfer.files[0];
  if (file) acceptFile(file);
});

resumeFileInput.addEventListener("change", () => {
  const file = resumeFileInput.files[0];
  if (file) acceptFile(file);
});

removeFileBtn.addEventListener("click", event => {
  event.stopPropagation();
  clearFile();
});

jobDescription.addEventListener("input", () => {
  jdCount.textContent = `${jobDescription.value.length.toLocaleString()} characters`;
  setFieldError(jdError, "");
  updateSubmitState();
});

analyzeForm.addEventListener("submit", event => {
  event.preventDefault();
  runAnalysis();
});

document.getElementById("retryBtn").addEventListener("click", () => runAnalysis());
document.getElementById("newAnalysisBtn").addEventListener("click", showInput);
document.getElementById("aboutBtn").addEventListener("click", () => {
  document.getElementById("aboutDialog").showModal();
});
document.getElementById("aboutClose").addEventListener("click", () => {
  document.getElementById("aboutDialog").close();
});
document.getElementById("skillDialogClose").addEventListener("click", () => {
  document.getElementById("skillDialog").close();
});

document.getElementById("skillSearch").addEventListener("input", renderSkillList);
document.getElementById("skillSort").addEventListener("change", renderSkillList);

setupTabs();
updateSubmitState();

function acceptFile(file) {
  const name = file.name.toLowerCase();
  const allowedType = name.endsWith(".pdf") || name.endsWith(".docx");
  if (!allowedType) {
    setFieldError(resumeError, "Use a PDF or DOCX file.");
    clearFile();
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    setFieldError(resumeError, "Use a file under 5 MB.");
    clearFile();
    return;
  }
  selectedFile = file;
  fileName.textContent = file.name;
  document.getElementById("dropzoneTitle").textContent = "Replace resume";
  fileSelected.hidden = false;
  setFieldError(resumeError, "");
  hideFormError();
  updateSubmitState();
}

function clearFile() {
  selectedFile = null;
  resumeFileInput.value = "";
  fileName.textContent = "";
  document.getElementById("dropzoneTitle").textContent = "Drop a resume here, or browse";
  fileSelected.hidden = true;
  updateSubmitState();
}

function updateSubmitState() {
  const ready = Boolean(selectedFile) && jobDescription.value.trim().length > 0;
  analyzeBtn.disabled = !ready;
}

function setFieldError(node, message) {
  node.hidden = !message;
  node.textContent = message;
}

async function runAnalysis() {
  const jdText = jobDescription.value.trim();
  const githubUsername = document.getElementById("githubUsername").value.trim();
  const includeGithub = document.getElementById("includeGithub").checked;
  let valid = true;

  if (!selectedFile) {
    setFieldError(resumeError, "Add a PDF or DOCX resume to continue.");
    valid = false;
  }
  if (!jdText) {
    setFieldError(jdError, "Paste the job description to continue.");
    valid = false;
  }
  if (!valid) return;

  const useGithub = includeGithub && Boolean(githubUsername);
  lastGithubUsed = useGithub;
  const formData = new FormData();
  formData.append("resume", selectedFile);
  formData.append("jd_text", jdText);
  formData.append("include_github", useGithub ? "true" : "false");
  if (useGithub) formData.append("github_username", githubUsername);

  showLoading();
  hideFormError();

  try {
    const response = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      body: formData
    });
    if (!response.ok) {
      const raw = await response.text();
      throw new Error(cleanError(raw) || "The analysis did not finish.");
    }
    const data = await response.json();
    renderReport(data, {
      filename: selectedFile.name,
      githubUsername: useGithub ? githubUsername : "",
      generatedAt: new Date()
    });
    showReport();
  } catch (error) {
    const message = error.message || "The analysis did not finish.";
    const githubHint = /github/i.test(message)
      ? " You can remove the GitHub username and run the analysis again."
      : "";
    formErrorText.textContent = `${message} Your resume and job description are still here.${githubHint}`;
    formError.hidden = false;
    showInput();
  }
}

function cleanError(raw) {
  const text = String(raw || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
  return text.slice(0, 280);
}

function hideFormError() {
  formError.hidden = true;
  formErrorText.textContent = "";
}

function showInput() {
  inputView.hidden = false;
  loadingView.hidden = true;
  reportView.hidden = true;
  setButtonLoading(false);
}

function showLoading() {
  inputView.hidden = true;
  loadingView.hidden = false;
  reportView.hidden = true;
  setButtonLoading(true);
}

function showReport() {
  inputView.hidden = true;
  loadingView.hidden = true;
  reportView.hidden = false;
  setButtonLoading(false);
  document.getElementById("tab-overview").focus();
}

function setButtonLoading(loading) {
  analyzeBtn.disabled = loading || !selectedFile || !jobDescription.value.trim();
  analyzeBtn.querySelector(".btn-text").hidden = loading;
  analyzeBtn.querySelector(".btn-loader").hidden = !loading;
}

function renderReport(data, meta) {
  const mapping = data.skill_mapping || {};
  const evidence = data.evidence_validation || {};
  const audit = data.ai_analysis && data.ai_analysis.skill_audit ? data.ai_analysis.skill_audit : {};
  const gaps = data.ai_analysis && data.ai_analysis.gap_analysis ? data.ai_analysis.gap_analysis : null;
  const actions = data.ai_analysis && data.ai_analysis.action_plan ? data.ai_analysis.action_plan.actions : null;
  const hasEvidence = evidence && Object.keys(evidence).length > 0;
  const missingPieces = [];
  if (!hasEvidence) missingPieces.push("skill evidence");
  if (!data.ai_analysis) missingPieces.push("the written audit");
  if (!data.ats_data) missingPieces.push("keyword coverage");

  document.getElementById("resumeMeta").textContent = `Resume: ${meta.filename}`;
  document.getElementById("githubMeta").textContent = meta.githubUsername
    ? `GitHub: ${meta.githubUsername}`
    : "GitHub: not included";
  document.getElementById("generatedMeta").textContent = `Generated ${meta.generatedAt.toLocaleString()}`;

  const partialBanner = document.getElementById("partialBanner");
  if (missingPieces.length) {
    partialBanner.hidden = false;
    partialBanner.textContent = `This report is incomplete. Missing: ${missingPieces.join(", ")}.`;
  } else {
    partialBanner.hidden = true;
    partialBanner.textContent = "";
  }

  skillRows = buildSkillRows(mapping, evidence, audit, Array.isArray(actions) ? actions : []);
  renderMetrics(skillRows, hasEvidence);
  document.getElementById("summaryNarrative").textContent = buildNarrative(skillRows, hasEvidence, meta.githubUsername);
  document.getElementById("overviewNote").textContent = overviewNote(meta.githubUsername);
  renderChips(document.getElementById("overclaimedList"), mapping.overclaimed || [], "None for this job description.");
  renderFilters();
  renderSkillList();
  renderGaps(gaps);
  renderActions(actions);
  renderCoverage(data.ats_data, data.ai_analysis && data.ai_analysis.ats_impact, mapping);
  selectTab("overview");
}

function buildSkillRows(mapping, evidence, audit, actions) {
  const matched = new Set(mapping.matched || []);
  const missing = new Set(mapping.missing || []);
  return Object.entries(evidence).map(([skill, info]) => {
    const rawStatus = info && info.status;
    const status = STATUS_LABEL[rawStatus] ? rawStatus : "needs_review";
    let resume = "Not found in the scanned resume text";
    if (matched.has(skill)) resume = "Mentioned";
    else if (missing.has(skill)) resume = "Not mentioned";
    const action = actions.find(item => item && item.skill === skill) || null;
    return {
      skill,
      status,
      label: STATUS_LABEL[status],
      reason: (info && info.reason) || "No explanation was returned for this skill.",
      resume,
      auditReason: (audit[skill] && audit[skill].reason) || "",
      action
    };
  });
}

function renderMetrics(rows, hasEvidence) {
  const grid = document.getElementById("metricGrid");
  if (!hasEvidence) {
    grid.innerHTML = "";
    return;
  }
  const counts = {
    reviewed: rows.length,
    supported: rows.filter(row => row.status === "supported").length,
    partial: rows.filter(row => row.status === "partially_supported").length,
    notFound: rows.filter(row => row.status === "unsupported").length
  };
  const cards = [
    ["Skills reviewed", counts.reviewed],
    ["Supported by evidence", counts.supported],
    ["Partial evidence", counts.partial],
    ["Not found in reviewed sources", counts.notFound]
  ];
  grid.innerHTML = cards.map(([label, value]) => `
    <article class="metric">
      <span class="metric-value">${value}</span>
      <span class="metric-label">${escapeHtml(label)}</span>
    </article>
  `).join("");
}

function buildNarrative(rows, hasEvidence, githubUsername) {
  if (!hasEvidence) {
    return "No role skills were identified from the job description, so there is no evidence review to summarize. Paste a description that names specific skills, then run the analysis again.";
  }
  const supported = rows.filter(row => row.status === "supported").length;
  const partial = rows.filter(row => row.status === "partially_supported").length;
  const notFound = rows.filter(row => row.status === "unsupported").length;
  const sentences = [
    `${supported} of ${rows.length} reviewed skills are supported by the sources that were checked.`
  ];
  if (partial) sentences.push(`${partial} have only partial evidence.`);
  if (notFound) {
    sentences.push(`${notFound} were not found in the reviewed sources. That means those sources did not show the skill. It is not proof that you lack it.`);
  }
  sentences.push(githubUsername
    ? "Public GitHub evidence was requested. Private repositories and work that is not on GitHub are not represented."
    : "GitHub was not included, so public repository evidence was not checked.");
  return sentences.join(" ");
}

function overviewNote(githubUsername) {
  const github = githubUsername
    ? "Public repositories for the username you entered were eligible for review."
    : "GitHub was not included in this run.";
  return `${github} This report does not list individual repositories, resume quotes, or file paths, because the analysis response does not include them. Each skill shows the status and the explanation that were returned.`;
}

function renderFilters() {
  const host = document.getElementById("skillFilters");
  const options = [
    ["all", "All skills"],
    ["supported", "Supported"],
    ["partially_supported", "Partial evidence"],
    ["unsupported", "Not found"]
  ];
  if (skillRows.some(row => row.status === "needs_review")) {
    options.push(["needs_review", "Needs review"]);
  }
  activeFilter = "all";
  host.innerHTML = options.map(([value, label], index) => `
    <button type="button" class="filter" data-filter="${value}" aria-pressed="${index === 0 ? "true" : "false"}">${label}</button>
  `).join("");
  host.querySelectorAll(".filter").forEach(button => {
    button.addEventListener("click", () => {
      activeFilter = button.dataset.filter;
      host.querySelectorAll(".filter").forEach(item => {
        item.setAttribute("aria-pressed", String(item === button));
      });
      renderSkillList();
    });
  });
}

function renderSkillList() {
  const query = document.getElementById("skillSearch").value.trim().toLowerCase();
  const sort = document.getElementById("skillSort").value;
  const visible = skillRows
    .filter(row => activeFilter === "all" || row.status === activeFilter)
    .filter(row => row.skill.toLowerCase().includes(query))
    .sort((a, b) => {
      if (sort === "name") return a.skill.localeCompare(b.skill);
      return STATUS_ORDER[a.status] - STATUS_ORDER[b.status] || a.skill.localeCompare(b.skill);
    });

  const list = document.getElementById("skillList");
  const empty = document.getElementById("skillEmpty");
  empty.hidden = visible.length > 0;
  list.innerHTML = visible.map(row => `
    <article class="skill-row">
      <div class="skill-name">${escapeHtml(row.skill)}</div>
      <div class="status status-${row.status}">${escapeHtml(row.label)}</div>
      <p class="reason-preview">${escapeHtml(row.resume)}. ${escapeHtml(row.reason)}</p>
      <button type="button" class="button button-secondary" data-skill="${escapeHtml(row.skill)}">Details</button>
    </article>
  `).join("");

  list.querySelectorAll("button[data-skill]").forEach(button => {
    button.addEventListener("click", () => openSkill(button.dataset.skill, button));
  });
}

function openSkill(skill, trigger) {
  const row = skillRows.find(item => item.skill === skill);
  if (!row) return;
  const dialog = document.getElementById("skillDialog");
  document.getElementById("skillDialogTitle").textContent = row.skill;
  const followUp = row.action
    ? `${row.action.action || ""}${row.action.expected_evidence ? ` ${row.action.expected_evidence}` : ""}`
    : "Add a concrete, truthful example of this skill on your resume or in a public project you can point to. Do not claim work you cannot substantiate.";
  document.getElementById("skillDialogBody").innerHTML = `
    <p class="detail-label">Status</p>
    <p class="status status-${row.status}">${escapeHtml(row.label)}</p>
    <p class="detail-label">Resume</p>
    <p>${escapeHtml(row.resume)}. The report does not include a resume quote or page number.</p>
    <p class="detail-label">Validation</p>
    <p>${escapeHtml(row.reason)}</p>
    ${row.auditReason ? `<p class="detail-label">Written audit</p><p>${escapeHtml(row.auditReason)}</p>` : ""}
    <p class="detail-label">What was inspected</p>
    <p>The job description and resume were scanned for known skill names. ${lastGithubUsed ? "Public GitHub text was eligible when a username was included." : "GitHub was not included."} Repository names, file paths, and private work were not returned.</p>
    <p class="detail-label">Suggested follow-up</p>
    <p>${escapeHtml(followUp.trim())}</p>
  `;
  dialog.showModal();
  dialog.addEventListener("close", () => trigger.focus(), { once: true });
}

function renderGaps(gaps) {
  const host = document.getElementById("gapContent");
  const critical = asList(gaps && gaps.critical_gaps);
  const secondary = asList(gaps && gaps.secondary_gaps);
  if (!gaps || (!critical.length && !secondary.length)) {
    host.innerHTML = `<h3>Gap analysis</h3><p class="empty-copy">No gap groups were returned. If every reviewed skill is supported, this section stays empty.</p>`;
    return;
  }
  host.innerHTML = `
    <h3>Gap analysis</h3>
    <p class="helper">These groups come from the analysis. “Not found” means the reviewed sources did not show the skill.</p>
    ${gapBlock("Higher-impact gaps", "Returned as critical gaps.", critical)}
    ${gapBlock("Other gaps", "Returned as secondary gaps.", secondary)}
  `;
}

function gapBlock(title, definition, items) {
  if (!items.length) {
    return `<div class="gap-block"><h3 class="section-gap">${escapeHtml(title)}</h3><p class="empty-copy">None returned.</p></div>`;
  }
  return `
    <div class="gap-block">
      <h3 class="section-gap">${escapeHtml(title)}</h3>
      <p class="helper">${escapeHtml(definition)}</p>
      ${items.map(raw => {
        const item = typeof raw === "string" ? { skill: raw, reason: "" } : (raw || {});
        const explanation = item.reason || item.evidence;
        return `
        <article class="gap-item">
          <h4>${escapeHtml(item.skill || "Gap")}</h4>
          ${item.importance ? `<p>Importance: ${escapeHtml(item.importance)}</p>` : ""}
          ${explanation ? `<p>${escapeHtml(explanation)}</p>` : ""}
        </article>
      `;
      }).join("")}
    </div>
  `;
}

function renderActions(actions) {
  const host = document.getElementById("actionContent");
  const items = asList(actions);
  if (!items.length) {
    host.innerHTML = `<h3>Action plan</h3><p class="empty-copy">No actions were returned. Actions are only created for skills the audit marks as weakly supported.</p>`;
    return;
  }
  host.innerHTML = `
    <h3>Action plan</h3>
    <p class="helper">Use these to make true evidence easier to find. Do not add a skill you cannot substantiate.</p>
    <div class="stack">
      ${items.map((item, index) => `
        <article class="action-item">
          <h4>${escapeHtml(item.action || `Action ${index + 1}`)}</h4>
          ${item.skill ? `<p>Related skill: ${escapeHtml(item.skill)}</p>` : ""}
          ${item.expected_evidence ? `<p>Evidence to aim for: ${escapeHtml(item.expected_evidence)}</p>` : ""}
        </article>
      `).join("")}
    </div>
  `;
}

function renderCoverage(atsData, atsImpact, mapping) {
  const host = document.getElementById("coverageContent");
  if (!atsData) {
    host.innerHTML = `<h3>Keyword coverage estimate</h3><p class="empty-copy">Keyword coverage was not included in this response.</p>`;
    return;
  }
  const rate = formatPercent(atsData.keyword_match_rate);
  const lexical = formatPercent(atsData.bm25_match_rate);
  const semantic = formatPercent(atsData.semantic_match_rate);
  const similarities = atsData.semantic_similarities && typeof atsData.semantic_similarities === "object"
    ? Object.entries(atsData.semantic_similarities)
    : [];
  const impact = atsImpact && typeof atsImpact === "object" ? atsImpact : null;
  host.innerHTML = `
    <h3>Keyword coverage estimate</h3>
    <p>This is an overlap estimate between job-description terms and the resume text. It is not an employer's applicant-tracking score, and it does not predict whether an application will pass screening.</p>
    <div class="coverage-stats">
      ${stat("Hybrid overlap", rate)}
      ${stat("Lexical overlap", lexical)}
      ${stat("Semantic overlap", semantic)}
    </div>
    <p class="helper">Hybrid overlap counts a term when either the lexical match or the semantic match found it. ${numberOrDash(atsData.matched_keywords)} matched terms out of ${numberOrDash(atsData.total_keywords)}.</p>
    ${atsData.semantic_available === false ? `<p class="helper">Semantic overlap was not calculated. Windows blocked the local scikit-learn library, so this run used lexical matching only.</p>` : ""}
    <h3 class="section-gap">Matched terms</h3>
    ${termList(atsData.hybrid_matched_skills, "No matched terms were returned.")}
    <h3 class="section-gap">Required skills not in the resume scan</h3>
    ${termList(mapping.missing, "None.")}
    ${impactBlock(impact)}
    ${similarities.length ? `
      <details>
        <summary>Semantic similarity scores</summary>
        <ul class="similarity-list">
          ${similarities.map(([skill, score]) => `<li><span>${escapeHtml(skill)}</span><span>${escapeHtml(score)}</span></li>`).join("")}
        </ul>
      </details>
    ` : ""}
  `;
}

function stat(label, value) {
  return `<div><strong>${escapeHtml(value)}</strong><span class="helper">${escapeHtml(label)}</span></div>`;
}

function impactBlock(impact) {
  if (!impact) return "";
  const reasons = asList(impact.rejection_reasons).map(item => typeof item === "string" ? item : item.skill || "");
  const gain = impact.estimated_score_gain;
  return `
    <h3 class="section-gap">Model notes</h3>
    <p class="helper">These notes are the model's reading of the keyword overlap. They are not an employer decision.</p>
    ${impact.ats_risk ? `<p>Model risk label: ${escapeHtml(impact.ats_risk)}</p>` : ""}
    ${gain === 0 || gain ? `<p>Model estimate if missing terms were addressed: ${escapeHtml(gain)}. This is not a measured employer score.</p>` : ""}
    ${reasons.length ? `<ul>${reasons.filter(Boolean).map(reason => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>` : ""}
  `;
}

function termList(values, emptyText) {
  const items = Array.isArray(values) ? values : [];
  if (!items.length) return `<p class="empty-copy">${escapeHtml(emptyText)}</p>`;
  return `<ul class="term-list">${items.map(item => `<li class="term">${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderChips(host, values, emptyText) {
  const items = Array.isArray(values) ? values : [];
  host.innerHTML = items.length
    ? items.map(item => `<li class="chip">${escapeHtml(item)}</li>`).join("")
    : `<li class="helper">${escapeHtml(emptyText)}</li>`;
}

function asList(value) {
  return Array.isArray(value) ? value : [];
}

function formatPercent(value) {
  if (typeof value === "number" && Number.isFinite(value)) return `${Math.round(value)}%`;
  if (typeof value === "string" && value.trim() && !Number.isNaN(Number(value))) return `${Math.round(Number(value))}%`;
  return "—";
}

function numberOrDash(value) {
  return typeof value === "number" ? String(value) : "—";
}

function setupTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach(tab => {
    tab.addEventListener("click", () => selectTab(tab.id.replace("tab-", "")));
    tab.addEventListener("keydown", event => {
      const index = tabs.indexOf(tab);
      if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
        event.preventDefault();
        const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
        tabs[next].focus();
        selectTab(tabs[next].id.replace("tab-", ""));
      }
    });
  });
}

function selectTab(name) {
  document.querySelectorAll(".tab").forEach(tab => {
    const selected = tab.id === `tab-${name}`;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
  });
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.hidden = panel.id !== `panel-${name}`;
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
