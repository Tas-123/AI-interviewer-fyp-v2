/** API helpers for Recruiter Dashboard (same origin as FastAPI). */

async function request(path, options = {}) {
  const res = await fetch(path, {
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
  if (!res.ok) {
    const detail = data?.detail || res.statusText || "Request failed";
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export function fetchRoles() {
  return request("/api/roles");
}

export function fetchInterviews() {
  return request("/api/interviews");
}

export function createInterview({ target_role, label }) {
  return request("/api/interviews", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_role, label: label || null }),
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
