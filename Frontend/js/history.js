import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, formatScore, formatWhen } from "./render.js";

const user = await requireUser();
if (user) loadHistory();

async function loadHistory() {
  const trend = document.querySelector("#trend");
  const list = document.querySelector("#historyList");
  const empty = document.querySelector("#historyEmpty");
  let rows;
  try {
    rows = await api("/api/analyses");
  } catch (err) {
    empty.hidden = false;
    empty.textContent = err.message || "Could not load history.";
    return;
  }
  renderTrend(trend, rows);
  clear(list);
  if (!rows.length) {
    empty.hidden = false;
    empty.textContent = "No analyses yet.";
    return;
  }
  empty.hidden = true;
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
    const percent = row.score <= 1 ? Math.round(row.score * 100) : Math.min(100, Math.round(row.score));
    const track = el("div", { className: "bar-track" });
    const bar = el("div", { className: "bar" });
    bar.style.height = `${percent}%`;
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
