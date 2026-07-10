import {
    renderAdaptiveTrace,
    renderRecruiterSection,
    renderSkillCoverage,
    renderSummaryGrid,
} from "./sections.js";

export function renderInterviewReport(panel, payload) {
    if (!panel) return;

    const report = payload?.report || payload || {};

    panel.innerHTML = `
        ${renderSummaryGrid(report)}
        ${renderRecruiterSection(report.recruiter_summary || {})}
        <div class="report-section">
            <div class="report-section-title">Skill Coverage Map</div>
            ${renderSkillCoverage(report.skill_coverage_map)}
        </div>
        <div class="report-section">
            <div class="report-section-title">Adaptive Questioning Trace</div>
            ${renderAdaptiveTrace(report.adaptive_questioning_trace)}
        </div>
        <details class="report-section">
            <summary class="report-section-title">Full JSON Debug Report</summary>
            <div class="report-json">${JSON.stringify(report, null, 2)}</div>
        </details>
    `;
}

export function showReportPlaceholder(panel, message) {
    if (!panel) return;
    panel.innerHTML = `<div class="report-placeholder">${message}</div>`;
}

export function showReportLoading(panel) {
    showReportPlaceholder(panel, "Loading final report…");
}

export function showReportError(panel, message) {
    if (!panel) return;
    panel.innerHTML = `<div class="log-entry error">${message}</div>`;
}
