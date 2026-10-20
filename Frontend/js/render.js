const FIELDS = [
  "className",
  "type",
  "id",
  "name",
  "placeholder",
  "maxLength",
  "minLength",
  "value",
  "rows",
  "rel",
  "target",
  "htmlFor",
  "hidden",
  "disabled",
  "required",
  "checked",
];

export function el(tag, options = {}) {
  const node = document.createElement(tag);
  for (const key of FIELDS) {
    if (options[key] !== undefined) node[key] = options[key];
  }
  if (options.text !== undefined) node.textContent = options.text;
  return node;
}

export function clear(node) {
  node.replaceChildren();
}

export function fillList(parent, lines, emptyText) {
  if (!lines.length) {
    parent.append(el("p", { className: "helper", text: emptyText }));
    return;
  }
  const list = el("ul", { className: "plain-list" });
  for (const line of lines) list.append(el("li", { text: line }));
  parent.append(list);
}

export function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") return url.href;
  } catch {
    return "";
  }
  return "";
}

export function externalLink(href, text) {
  const safe = safeHttpUrl(href);
  if (!safe) return el("span", { text });
  const link = el("a", { text, rel: "noopener noreferrer", target: "_blank" });
  link.href = safe;
  return link;
}

export function formatScore(score) {
  if (typeof score !== "number") return "—";
  if (score <= 1) return `${Math.round(score * 100)}%`;
  return String(Math.round(score));
}

export function formatWhen(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString();
}

export function limitMessage(err) {
  const seconds = err && err.retryAfter != null ? err.retryAfter : 60;
  return `Too many requests. Try again in ${seconds} seconds.`;
}

export function loadingNote(text) {
  const wrap = el("div", { className: "loading" });
  wrap.append(el("p", { className: "helper", text: text || "Analysing..." }));
  wrap.append(el("div", { className: "progress-line" }));
  return wrap;
}

export function emptyState(sentence, buttonText, onClick) {
  const wrap = el("div", { className: "empty" });
  wrap.append(el("p", { text: sentence }));
  if (!buttonText) return wrap;
  const button = el("button", { type: "button", className: "button button-primary", text: buttonText });
  button.addEventListener("click", onClick);
  wrap.append(button);
  return wrap;
}

export function errorBox(message, onRetry) {
  const box = el("div", { className: "banner banner-error" });
  box.append(el("p", { text: message || "Something went wrong." }));
  if (!onRetry) return box;
  const button = el("button", { type: "button", className: "button button-quiet", text: "Retry" });
  button.addEventListener("click", onRetry);
  box.append(button);
  return box;
}
