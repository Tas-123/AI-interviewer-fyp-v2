/**
 * Legacy report section builders — neutralized.
 *
 * Older cached copies of renderReport.js still imported these and painted
 * Hire Signal / skill map / adaptive trace. Those exports now return the
 * candidate thank-you panel (or empty) so a stale browser cache cannot
 * bring the recruiter score UI back into the candidate page.
 */

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function buildCompletionHtml(htmlUrl = "http://localhost:8766/latest-report.html") {
    return `
        <div class="completion-card" data-completion="1">
            <h3 class="completion-title">Thank you</h3>
            <p class="completion-body">
                Thank you for completing the interview. Your responses have been recorded
                successfully. Our recruitment team will review your interview, and you will
                be informed about the next steps.
            </p>
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

/** @deprecated Old cached UIs called this for the hire-signal grid. */
export function hireSignalClass() {
    return "";
}

export function renderList() {
    return "";
}

/** Replaces legacy summary grid with thank-you + report link. */
export function renderSummaryGrid() {
    return buildCompletionHtml();
}

export function renderRecruiterSection() {
    return "";
}

export function renderSkillCoverage() {
    return "";
}

export function renderAdaptiveTrace() {
    return "";
}
