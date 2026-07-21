/** API helpers for Recruiter Dashboard (same origin as FastAPI). */

function redirectToLogin() {
  if (window.location.pathname === "/login") return;
  window.location.href = "/login";
}

async function request(path, options = {}) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { raw: text };
    }
  }
  if (res.status === 401) {
    redirectToLogin();
    throw new Error("Recruiter login required.");
  }
  if (!res.ok) {
    const detail = data?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export function fetchMe() {
  return request("/api/auth/me");
}

export function logout() {
  return request("/api/auth/logout", { method: "POST" });
}

export function fetchRoles() {
  return request("/api/roles");
}

export function fetchInterviews() {
  return request("/api/interviews");
}

export function createInterview(payload) {
  return request("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchEmailStatus() {
  return request("/api/email/status");
}

export function sendInvitation(token, payload = {}) {
  return request(`/api/interviews/${encodeURIComponent(token)}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function fetchReports() {
  return request("/api/reports");
}

export function fetchReport(sessionId) {
  return request(`/api/reports/${encodeURIComponent(sessionId)}`);
}

export function reportHtmlUrl(sessionId) {
  return `/api/reports/${encodeURIComponent(sessionId)}/html`;
}

/** Same HTML file with Content-Disposition: attachment */
export function reportHtmlDownloadUrl(sessionId) {
  return `/api/reports/${encodeURIComponent(sessionId)}/html?download=1`;
}
