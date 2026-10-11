const FIELDS = ["className", "type", "id", "placeholder", "maxLength", "value", "rel", "target"];

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
