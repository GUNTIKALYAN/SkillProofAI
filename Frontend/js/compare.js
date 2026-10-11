import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, formatScore } from "./render.js";

const MAX_JOBS = 10;

const user = await requireUser();
if (user) start();

function start() {
  const fields = document.querySelector("#jobFields");
  const form = document.querySelector("#compareForm");
  addField(fields);
  addField(fields);
  document.querySelector("#addJob").addEventListener("click", () => {
    if (fields.children.length < MAX_JOBS) addField(fields);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    rank(form, fields);
  });
}

function addField(fields) {
  const index = fields.children.length + 1;
  const label = el("label", { text: `Job ${index}` });
  const input = el("textarea", { placeholder: "Paste a job description." });
  input.name = "job";
  input.required = true;
  fields.append(label, input);
}

async function rank(form, fields) {
  const error = document.querySelector("#compareError");
  const result = document.querySelector("#compareResult");
  error.hidden = true;
  const jobs = [...fields.querySelectorAll("textarea")].map((node) => node.value.trim()).filter(Boolean);
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
    error.hidden = false;
    error.textContent = err.status === 429
      ? `Too many analyses. Try again in ${err.retryAfter || 60} seconds.`
      : (err.message || "Could not compare these jobs.");
  }
}
