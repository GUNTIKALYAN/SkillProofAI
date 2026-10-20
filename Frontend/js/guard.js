import { api, clearToken, getToken } from "./api.js";

export async function requireUser() {
  if (!getToken()) {
    try {
      await api("/api/auth/refresh", { method: "POST" });
    } catch {
      window.location.replace("auth.html");
      return null;
    }
  }
  try {
    const user = await api("/api/auth/me");
    bindSession(user);
    return user;
  } catch {
    clearToken();
    window.location.replace("auth.html");
    return null;
  }
}

export async function redirectAuthed() {
  try {
    await api("/api/auth/refresh", { method: "POST" });
  } catch {
    return;
  }
  window.location.replace("app.html");
}

function bindSession(user) {
  const email = document.querySelector("[data-email]");
  if (email) email.textContent = user.email;
  const adminLink = document.querySelector("[data-admin]");
  if (adminLink) adminLink.hidden = user.role !== "admin";
  const remove = document.querySelector("[data-delete-account]");
  if (remove) {
    remove.addEventListener("click", () => {
      const confirmed = window.confirm("Delete your account and saved analyses? This cannot be undone.");
      if (!confirmed) return;
      api("/api/auth/me", { method: "DELETE" })
        .then(() => {
          clearToken();
          window.location.replace("auth.html");
        })
        .catch((err) => {
          window.alert(err.message || "Could not delete your data");
        });
    });
  }
  const button = document.querySelector("[data-logout]");
  if (!button) return;
  button.addEventListener("click", () => {
    api("/api/auth/logout", { method: "POST" })
      .catch(() => {
        // The cookie may already be gone. Leave the page either way.
      })
      .finally(() => {
        clearToken();
        window.location.replace("auth.html");
      });
  });
}
