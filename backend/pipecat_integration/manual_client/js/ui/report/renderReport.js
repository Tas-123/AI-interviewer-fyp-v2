/**
 * Candidate-facing completion panel.
 * Detailed scores belong in the recruiter HTML assessment — not here.
 */

const DEFAULT_HTML_URL = "http://localhost:8766/latest-report.html";

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function resolveHtmlUrl(payload, defaultHtmlUrl) {
    if (payload?.html_url) return payload.html_url;
    if (defaultHtmlUrl) return defaultHtmlUrl;
    return DEFAULT_HTML_URL;
}

/**
 * Show thank-you message after the interview ends.
 * @param {HTMLElement} panel
 * @param {object} [payload] - Optional /latest-report envelope ({ report, html_url, file })
 * @param {{ reportHtmlUrl?: string }} [options]
 */
export function renderCompletionMessage(panel, payload = null, options = {}) {
    if (!panel) return;

    const htmlUrl = resolveHtmlUrl(payload, options.reportHtmlUrl);
    const meta = payload?.report?.report_meta || payload?.report_meta || {};
    const candidate = meta.candidate_display_name
        ? `<p class="completion-meta">Session recorded for <strong>${escapeHtml(meta.candidate_display_name)}</strong>.</p>`
        : "";

    panel.innerHTML = `
        <div class="completion-card" data-completion="1">
            <h3 class="completion-title">Thank you</h3>
            <p class="completion-body">
                Thank you for completing the interview. Your responses have been recorded
                successfully. Our recruitment team will review your interview, and you will
                be informed about the next steps.
            </p>
            ${candidate}
            <p class="completion-demo-note">
                FYP demo only — recruiters would open this assessment from a dashboard.
                Candidates do not normally see scores.
            </p>
            <a
                class="btn btn-primary completion-report-link"
                href="${escapeHtml(htmlUrl)}"
                target="_blank"
                rel="noopener noreferrer"
            >
                Open recruiter assessment
            </a>
        </div>
    `;
}

/** Immediate thank-you before /latest-report returns (always shows the link). */
export function renderCompletionMessageImmediate(panel, reportHtmlUrl = DEFAULT_HTML_URL) {
    renderCompletionMessage(panel, null, { reportHtmlUrl });
}

/** @deprecated Prefer renderCompletionMessage */
export function renderInterviewReport(panel, payload, options = {}) {
    renderCompletionMessage(panel, payload, options);
}

export function showReportPlaceholder(panel, message) {
    if (!panel) return;
    panel.innerHTML = `<div class="report-placeholder">${escapeHtml(message)}</div>`;
}

export function showReportLoading(panel) {
    showReportPlaceholder(panel, "Finalizing your session…");
}

export function showReportError(panel, message) {
    renderCompletionMessage(panel, null, {});
    if (!panel) return;
    const err = document.createElement("p");
    err.className = "log-entry error";
    err.textContent = String(message || "");
    panel.querySelector(".completion-card")?.appendChild(err);
}
