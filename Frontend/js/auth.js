import { api, setToken } from "./api.js";
import { redirectAuthed } from "./guard.js";
import { clear, errorBox, limitMessage } from "./render.js";

const error = document.querySelector("#formError");
const tabs = document.querySelectorAll("[data-tab]");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => showTab(tab.dataset.tab));
});

document.querySelector("#loginForm").addEventListener("submit", (event) => {
  event.preventDefault();
  submit("login", new FormData(event.currentTarget));
});

document.querySelector("#signupForm").addEventListener("submit", (event) => {
  event.preventDefault();
  submit("signup", new FormData(event.currentTarget));
});

if (window.location.hash === "#signup") showTab("signup");

await redirectAuthed();

function showTab(name) {
  const signup = name === "signup";
  document.querySelector("#loginPanel").hidden = signup;
  document.querySelector("#signupPanel").hidden = !signup;
  document.querySelector("#tab-login").setAttribute("aria-selected", signup ? "false" : "true");
  document.querySelector("#tab-signup").setAttribute("aria-selected", signup ? "true" : "false");
  error.hidden = true;
  clear(error);
}

async function submit(kind, data) {
  error.hidden = true;
  clear(error);
  const password = String(data.get("password") || "");
  if (kind === "signup" && password.length < 8) {
    showError({ message: "Use at least 8 characters." });
    return;
  }
  const path = kind === "signup" ? "/api/auth/signup" : "/api/auth/login";
  try {
    const body = await api(path, {
      method: "POST",
      json: {
        email: String(data.get("email") || ""),
        password,
      },
    });
    setToken(body.access_token);
    window.location.replace("app.html");
  } catch (err) {
    showError(err);
  }
}

function showError(err) {
  error.hidden = false;
  clear(error);
  const message = err.status === 429 ? limitMessage(err) : (err.message || "Could not continue.");
  error.append(errorBox(message));
}
