// ================= CONFIG =================
const API_BASE = "http://127.0.0.1:8000/api";

// ================= DOM ELEMENTS =================
const fileDropZone = document.getElementById("fileDropZone");
const resumeFileInput = document.getElementById("resumeFile");
const uploadPlaceholder = document.getElementById("uploadPlaceholder");
const fileSelected = document.getElementById("fileSelected");
const fileName = document.getElementById("fileName");
const removeFileBtn = document.getElementById("removeFile");

const analyzeForm = document.getElementById("analyzeForm");
const analyzeBtn = document.getElementById("analyzeBtn");

const errorMessage = document.getElementById("errorMessage");
const errorText = document.getElementById("errorText");

const emptyState = document.getElementById("emptyState");
const resultsContent = document.getElementById("resultsContent");

// ================= FILE UPLOAD =================
fileDropZone.addEventListener("click", () => resumeFileInput.click());

fileDropZone.addEventListener("dragover", e => {
  e.preventDefault();
  fileDropZone.classList.add("drag-over");
});

fileDropZone.addEventListener("dragleave", () => {
  fileDropZone.classList.remove("drag-over");
});

fileDropZone.addEventListener("drop", e => {
  e.preventDefault();
  fileDropZone.classList.remove("drag-over");
  if (e.dataTransfer.files.length) {
    handleFileSelect(e.dataTransfer.files[0]);
  }
});

resumeFileInput.addEventListener("change", e => {
  if (e.target.files.length) {
    handleFileSelect(e.target.files[0]);
  }
});

removeFileBtn.addEventListener("click", e => {
  e.stopPropagation();
  resumeFileInput.value = "";
  uploadPlaceholder.style.display = "flex";
  fileSelected.style.display = "none";
});

function handleFileSelect(file) {
  const allowed = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  ];

  if (!allowed.includes(file.type)) {
    return showError("Only PDF or DOCX files allowed");
  }

  if (file.size > 5 * 1024 * 1024) {
    return showError("File must be under 5MB");
  }

  fileName.textContent = file.name;
  uploadPlaceholder.style.display = "none";
  fileSelected.style.display = "flex";
  hideError();
}

// ================= FORM SUBMIT =================
analyzeForm.addEventListener("submit", async e => {
  e.preventDefault();

  const resume = resumeFileInput.files[0];
  const jdText = document.getElementById("jobDescription").value.trim();
  const githubUsername = document.getElementById("githubUsername").value.trim();
  const includeGithub = document.getElementById("includeGithub").checked;

  if (!resume) return showError("Resume is required");
  if (!jdText) return showError("Job Description is required");

  setLoading(true);
  hideError();

  const formData = new FormData();
  formData.append("resume", resume);
  formData.append("jd_text", jdText);
  formData.append("include_github", includeGithub ? "true" : "false");
  if (githubUsername) {
    formData.append("github_username", githubUsername);
  }

  try {
    const res = await fetch(`${API_BASE}/analyze`, {
      method: "POST",
      body: formData
    });

    if (!res.ok) {
      const err = await res.text();
      throw new Error(err || "Analysis failed");
    }

    const data = await res.json();

    // ✅ DEBUG: Log the full response
    console.log("FULL API RESPONSE:", data);
    console.log("ATS DATA:", data.ats_data);

    renderResults(data);
    emptyState.style.display = "none";
    resultsContent.style.display = "block";

  } catch (err) {
    showError(err.message);
  } finally {
    setLoading(false);
  }
});

// ================= UI HELPERS =================
function setLoading(state) {
  const text = analyzeBtn.querySelector(".btn-text");
  const loader = analyzeBtn.querySelector(".btn-loader");

  analyzeBtn.disabled = state;
  text.style.display = state ? "none" : "inline";
  loader.style.display = state ? "flex" : "none";
}

function showError(msg) {
  errorText.textContent = msg;
  errorMessage.style.display = "flex";
}

function hideError() {
  errorMessage.style.display = "none";
}

// ================= RENDER RESULTS =================
function renderResults(data) {
  if (!data) return;

  renderSkillSummary(data.skill_mapping);
  renderSkillTable(data.skill_mapping);
  renderEvidence(data.evidence_validation);

  if (data.ai_analysis) {
    renderSkillAudit(data.ai_analysis.skill_audit || {});
    renderGapAnalysis(data.ai_analysis.gap_analysis || {});
    renderATSImpact(
      data.ai_analysis.ats_impact || {},
      data.ats_data  // ✅ Pass the ats_data object
    );
    renderActionPlan(data.ai_analysis.action_plan?.actions || []);
  }
}


// ================= SKILL SUMMARY =================
function renderSkillSummary(mapping) {
  const matched = mapping.matched.length;
  const missing = mapping.missing.length;
  const overclaimed = mapping.overclaimed.length;
  const total = matched + missing;
  const percent = total ? Math.round((matched / total) * 100) : 0;

  document.getElementById("matchedCount").textContent = matched;
  document.getElementById("missingCount").textContent = missing;
  document.getElementById("overclaimedCount").textContent = overclaimed;
  document.getElementById("matchPercentage").textContent = percent + "%";
  document
    .getElementById("matchCircle")
    .setAttribute("stroke-dasharray", `${percent}, 100`);
}

// ================= SKILL TABLE =================
function renderSkillTable(mapping) {
  const tbody = document.getElementById("skillTableBody");
  tbody.innerHTML = "";

  mapping.matched.forEach(s => tbody.innerHTML += row(s, "matched", "Resume + GitHub"));
  mapping.missing.forEach(s => tbody.innerHTML += row(s, "missing", "JD Required"));
  mapping.overclaimed.forEach(s => tbody.innerHTML += row(s, "overclaimed", "Resume Only"));
}

function row(skill, status, source) {
  return `
    <tr>
      <td>${skill}</td>
      <td><span class="status-badge ${status}">${status}</span></td>
      <td>${source}</td>
    </tr>
  `;
}

// ================= EVIDENCE =================
function renderEvidence(evidence) {
  const container = document.getElementById("evidenceList");
  container.innerHTML = "";

  Object.entries(evidence).forEach(([skill, info]) => {
    container.innerHTML += `
      <div class="evidence-item">
        <div class="evidence-header">
          <span class="skill-name">${skill}</span>
          <span class="evidence-badge ${info.status}">${info.status}</span>
        </div>
        <p class="evidence-reason">${info.reason}</p>
      </div>
    `;
  });
}

// ================= SKILL AUDIT =================
function renderSkillAudit(audit) {
  const acc = document.getElementById("skillAuditAccordion");
  acc.innerHTML = "";

  Object.entries(audit).forEach(([skill, data], i) => {
    acc.innerHTML += `
      <div class="accordion-item">
        <button class="accordion-trigger" data-target="audit-${i}">
          <span>${skill}</span>
          <span class="credibility ${data.credibility}">
            ${data.credibility}
          </span>
        </button>
        <div class="accordion-content" id="audit-${i}">
          <p>${data.reason}</p>
        </div>
      </div>
    `;
  });

  attachAccordion();
}

function attachAccordion() {
  document.querySelectorAll(".accordion-trigger").forEach(btn => {
    btn.onclick = () => {
      const id = btn.dataset.target;
      const content = document.getElementById(id);
      const open = btn.classList.contains("active");

      document.querySelectorAll(".accordion-trigger").forEach(b => {
        b.classList.remove("active");
        document.getElementById(b.dataset.target).style.maxHeight = "0";
      });

      if (!open) {
        btn.classList.add("active");
        content.style.maxHeight = content.scrollHeight + "px";
      }
    };
  });
}

// ================= GAP ANALYSIS =================
function renderGapAnalysis(gaps) {
  document.getElementById("criticalGaps").innerHTML =
    (gaps.critical_gaps || []).map(g =>
      `<li><strong>${g.skill}</strong> — ${g.reason}</li>`
    ).join("");

  document.getElementById("secondaryGaps").innerHTML =
    (gaps.secondary_gaps || []).map(g =>
      `<li><strong>${g.skill}</strong> — ${g.reason}</li>`
    ).join("");
}

// ================= ATS IMPACT ================= 
// ✅ FIXED VERSION
function renderATSImpact(atsImpact, atsData) {
  console.log("renderATSImpact called with:", { atsImpact, atsData });

  // ATS Risk Level
  const riskLevel = atsImpact.ats_risk || "medium";
  document.getElementById("atsRiskIndicator").innerHTML =
    `<span class="risk-level ${riskLevel}">${riskLevel.toUpperCase()}</span>`;

  // Score Gain
  const scoreGain = atsImpact.estimated_score_gain || 0;
  document.getElementById("scoreGain").textContent = `+${scoreGain}`;

  // ✅ CRITICAL FIX: Get keyword_match_rate from atsData
  let keywordMatchRate = 0;
  
  if (atsData && typeof atsData.keyword_match_rate === "number") {
    keywordMatchRate = atsData.keyword_match_rate;
  } else if (atsData && typeof atsData.keyword_match_rate === "string") {
    keywordMatchRate = parseInt(atsData.keyword_match_rate, 10);
  }

  console.log("Keyword Match Rate:", keywordMatchRate);
  document.getElementById("keywordMatchRate").textContent = `${keywordMatchRate}%`;

  // Rejection Reasons
  const rejectionReasons = atsImpact.rejection_reasons || [];
  document.getElementById("rejectionReasons").innerHTML =
    rejectionReasons.map(r => `<li>${r}</li>`).join("") || "<li>No rejection triggers detected</li>";
}

// ================= ACTION PLAN =================
function renderActionPlan(actions) {
  const list = document.getElementById("actionPlanList");
  list.innerHTML = "";

  actions.forEach((a, i) => {
    list.innerHTML += `
      <div class="action-item">
        <div class="action-week">Step ${i + 1}</div>
        <div class="action-content">
          <div class="action-skill">${a.skill}</div>
          <div class="action-task">${a.action}</div>
          <div class="action-evidence">📌 ${a.expected_evidence}</div>
        </div>
      </div>
    `;
  });
}