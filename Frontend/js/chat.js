import { api, readEvents } from "./api.js";
import { requireUser } from "./guard.js";
import { el, formatScore } from "./render.js";

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
    const message = form.elements.message.value.trim();
    if (!message) return;
    form.elements.message.value = "";
    log.append(bubble("user", message));
    const reply = bubble("assistant", "");
    log.append(reply);
    const text = reply.querySelector(".chat-text");
    try {
      await readEvents("/api/chat", { method: "POST", json: { message } }, (item) => {
        if (item.text) text.textContent += item.text;
        if (typeof item.before === "number" && typeof item.after === "number") {
          reply.append(el("p", {
            className: "helper",
            text: `Score ${formatScore(item.before)} to ${formatScore(item.after)}.`,
          }));
        }
      });
    } catch (err) {
      reply.remove();
      error.hidden = false;
      error.textContent = err.status === 429
        ? (err.message || "Too many messages.")
        : (err.message || "Could not send the message.");
    }
  });
}

async function loadHistory(log) {
  let rows;
  try {
    rows = await api("/api/chat");
  } catch (err) {
    log.append(el("p", { className: "helper", text: err.message || "Could not load chat history." }));
    return;
  }
  for (const row of rows) log.append(bubble(row.role, row.content));
}

function bubble(role, content) {
  const node = el("article", { className: role === "user" ? "chat-bubble chat-user" : "chat-bubble" });
  node.append(el("p", { className: "helper", text: role === "user" ? "You" : "SkillProof" }));
  node.append(el("p", { className: "chat-text", text: content }));
  return node;
}
