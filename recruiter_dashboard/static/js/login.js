async function login(username, password) {
  const res = await fetch("/api/auth/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data?.detail || res.statusText || "Login failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

const form = document.getElementById("login-form");
const errEl = document.getElementById("login-error");
const btn = document.getElementById("btn-login");

form?.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (errEl) {
    errEl.hidden = true;
    errEl.textContent = "";
  }
  if (btn) btn.disabled = true;
  const username = document.getElementById("username")?.value || "";
  const password = document.getElementById("password")?.value || "";
  try {
    await login(username, password);
    window.location.href = "/";
  } catch (err) {
    if (errEl) {
      errEl.textContent = err.message || "Login failed";
      errEl.hidden = false;
    }
  } finally {
    if (btn) btn.disabled = false;
  }
});
