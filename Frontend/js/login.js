import { api, setToken } from "./api.js";
import { redirectAuthed } from "./guard.js";

await redirectAuthed();

const form = document.querySelector("#loginForm");
const error = document.querySelector("#formError");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  const data = new FormData(form);
  try {
    const body = await api("/api/auth/login", {
      method: "POST",
      json: {
        email: String(data.get("email") || ""),
        password: String(data.get("password") || ""),
      },
    });
    setToken(body.access_token);
    window.location.replace("app.html");
  } catch (err) {
    showError(error, err);
  }
});

function showError(node, err) {
  node.hidden = false;
  node.textContent = err.status === 429
    ? `Too many attempts. Try again in ${err.retryAfter || 60} seconds.`
    : (err.message || "Could not log in");
}
