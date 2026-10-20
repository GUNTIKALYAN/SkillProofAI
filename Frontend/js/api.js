const OPEN = new Set(["/api/auth/login", "/api/auth/signup", "/api/auth/refresh"]);

let accessToken = null;

export class ApiError extends Error {
  constructor(status, detail, retryAfter) {
    super(detail);
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function setToken(token) {
  accessToken = token;
}

export function clearToken() {
  accessToken = null;
}

export function getToken() {
  return accessToken;
}

export async function api(path, options = {}) {
  const response = await authorized(path, options);
  if (response.status === 204) return null;
  const type = response.headers.get("content-type") || "";
  if (!type.includes("application/json")) return null;
  return response.json();
}

async function send(path, options) {
  const headers = new Headers(options.headers || {});
  if (accessToken && !OPEN.has(path)) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  const init = {
    method: options.method || "GET",
    headers,
    credentials: "include",
  };
  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    init.body = JSON.stringify(options.json);
  } else if (options.body !== undefined) {
    init.body = options.body;
  }
  return fetch(path, init);
}

async function authorized(path, options) {
  let response = await send(path, options);
  if (response.status === 401 && !options.retried && !OPEN.has(path)) {
    const refreshed = await send("/api/auth/refresh", { method: "POST" });
    if (!refreshed.ok) {
      accessToken = null;
      throw await readError(refreshed);
    }
    const body = await refreshed.json();
    accessToken = body.access_token;
    response = await send(path, { ...options, retried: true });
  }
  if (!response.ok) throw await readError(response);
  return response;
}

async function readError(response) {
  let detail = "Request failed";
  try {
    const body = await response.json();
    if (typeof body.detail === "string") detail = body.detail;
    else if (Array.isArray(body.detail)) {
      detail = body.detail.map((item) => item.msg || "Invalid input").join("; ");
    }
  } catch {
    detail = response.statusText || detail;
  }
  const retry = Number(response.headers.get("retry-after"));
  return new ApiError(response.status, detail, Number.isFinite(retry) ? retry : null);
}
