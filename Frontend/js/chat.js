import { api } from "./api.js";
import { requireUser } from "./guard.js";
import { clear, el, emptyState, errorBox, formatScore, limitMessage } from "./render.js";

const user = await requireUser();
if (user) start();

function start() {
  const log = document.querySelector("#chatLog");
  const form = document.querySelector("#chatForm");
  const error = document.querySelector("#chatError");
  loadHistory(log);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    clear(error);
    const message = form.elements.message.value.trim();
    if (!message) return;
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    form.elements.message.value = "";
    const empty = log.querySelector(".empty");
    if (empty) empty.remove();
    const mine = bubble("user", message);
    log.append(mine);
    const reply = bubble("assistant", "");
    log.append(reply);
    reply.append(el("p", { className: "helper", text: "Sending..." }));
    try {
      const body = await api("/api/chat", { method: "POST", json: { message } });
      if (!body || !body.text) throw new Error("The reply was empty.");
      fillReply(reply, body);
    } catch (err) {
      mine.remove();
      reply.remove();
      error.hidden = false;
      const text = err.status === 429 ? limitMessage(err) : (err.message || "Could not send the message.");
      error.append(errorBox(text, () => {
        form.elements.message.value = message;
        form.requestSubmit();
      }));
    } finally {
      button.disabled = false;
    }
  });
}

async function loadHistory(log) {
  clear(log);
  log.append(el("p", { className: "helper", text: "Loading..." }));
  let rows;
  try {
    rows = await api("/api/chat");
  } catch (err) {
    clear(log);
    log.append(errorBox(err.message || "Could not load chat history.", () => loadHistory(log)));
    return;
  }
  clear(log);
  if (!rows.length) {
    log.append(emptyState("No messages yet. Ask about your latest analysis."));
    return;
  }
  for (const row of rows) log.append(bubble(row.role, row.content));
}

function fillReply(reply, body) {
  clear(reply);
  reply.append(el("p", { className: "helper", text: "SkillProof" }));
  reply.append(el("p", { className: "chat-text", text: body.text }));
  if (typeof body.before === "number" && typeof body.after === "number") {
    reply.append(el("p", {
      className: "helper",
      text: `Score ${formatScore(body.before)} to ${formatScore(body.after)}.`,
    }));
  }
}

function bubble(role, content) {
  const node = el("article", { className: role === "user" ? "chat-bubble chat-user" : "chat-bubble" });
  node.append(el("p", { className: "helper", text: role === "user" ? "You" : "SkillProof" }));
  node.append(el("p", { className: "chat-text", text: content }));
  return node;
}
