import { api, setToken } from "./api.js";
import { redirectAuthed } from "./guard.js";

await redirectAuthed();

const form = document.querySelector("#signupForm");
const error = document.querySelector("#formError");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  error.hidden = true;
  const data = new FormData(form);
  const password = String(data.get("password") || "");
  if (password.length < 8) {
    error.hidden = false;
    error.textContent = "Use at least 8 characters.";
    return;
  }
  try {
    const body = await api("/api/auth/signup", {
      method: "POST",
      json: {
        email: String(data.get("email") || ""),
        password,
      },
    });
    setToken(body.access_token);
    window.location.replace("app.html");
  } catch (err) {
    error.hidden = false;
    error.textContent = err.status === 429
      ? `Too many attempts. Try again in ${err.retryAfter || 60} seconds.`
      : (err.message || "Could not create the account");
  }
});
