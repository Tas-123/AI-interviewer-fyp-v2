function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

export function renderList(items, emptyText = "No items available.") {
    if (!items || items.length === 0) {
        return `<div class="report-muted">${escapeHtml(emptyText)}</div>`;
    }
    return `<ul class="report-list">${items
        .map((item) => `<li>${escapeHtml(item)}</li>`)
        .join("")}</ul>`;
}

export function hireSignalClass(signal) {
    const normalized = String(signal || "").toLowerCase();
    if (normalized.includes("strong") || normalized.includes("hire")) {
        return "hire-signal-strong";
    }
    if (normalized.includes("weak") || normalized.includes("no")) {
        return "hire-signal-weak";
    }
    return "hire-signal-borderline";
}

export function renderSummaryGrid(report) {
    const ws = report.weighted_score_summary || {};
    const consistency = report.consistency_rating || {};
    const metadata = report.interview_metadata || {};
    const trend = report.performance_trend_analysis || {};
    const behavior = report.behavioral_profile || {};
    const recruiter = report.recruiter_summary || {};
    const hireSignal = ws.final_hire_signal || recruiter.final_signal || "N/A";

    return `
        <div class="report-grid">
            <div class="report-item">
                <div class="report-label">Hire Signal</div>
                <div class="report-value ${hireSignalClass(hireSignal)}">${escapeHtml(hireSignal)}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Average Score</div>
                <div class="report-value">${escapeHtml(ws.avg_weighted_overall ?? recruiter.average_weighted_score ?? 0)}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Consistency</div>
                <div class="report-value">${escapeHtml(consistency.consistency_rating || "N/A")}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Total Turns</div>
                <div class="report-value">${escapeHtml(metadata.total_turns ?? 0)}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Trend</div>
                <div class="report-value">${escapeHtml(trend.performance_trend_label || "N/A")}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Thinking Style</div>
                <div class="report-value">${escapeHtml(behavior.thinking_style || "N/A")}</div>
            </div>
        </div>
    `;
}

export function renderRecruiterSection(recruiter) {
    return `
        <div class="report-section">
            <div class="report-section-title">Recruiter Summary</div>
            <div class="report-text">${escapeHtml(recruiter.overall_observation || "No recruiter summary available.")}</div>
            <div class="report-muted">${escapeHtml(recruiter.interview_decision_note || "")}</div>
        </div>
        <div class="report-section">
            <div class="report-section-title">Main Strengths</div>
            ${renderList(recruiter.main_strengths, "No clear strengths detected yet.")}
        </div>
        <div class="report-section">
            <div class="report-section-title">Main Concerns</div>
            ${renderList(recruiter.main_concerns, "No major concerns detected yet.")}
        </div>
        <div class="report-section">
            <div class="report-section-title">Recommended Follow-up Areas</div>
            ${renderList(recruiter.recommended_follow_up_areas, "No follow-up areas available.")}
        </div>
    `;
}

export function renderSkillCoverage(skillMap) {
    const entries = Object.entries(skillMap || {});
    if (entries.length === 0) {
        return `<div class="report-muted">No skill coverage data available.</div>`;
    }

    return `
        <div class="report-grid">
            ${entries
                .map(([skill, data]) => {
                    const status = data.status || "unknown";
                    return `
                        <div class="report-item">
                            <div class="report-label">${escapeHtml(skill)}</div>
                            <div class="report-value">${escapeHtml(status)}</div>
                            <div class="report-muted">
                                Mentions: ${escapeHtml(data.mentions ?? 0)} |
                                Avg Score: ${escapeHtml(data.avg_score ?? 0)} |
                                Turns: ${escapeHtml((data.evidence_turns || []).join(", ") || "None")}
                            </div>
                        </div>
                    `;
                })
                .join("")}
        </div>
    `;
}

export function renderAdaptiveTrace(adaptiveTrace) {
    if (!adaptiveTrace || adaptiveTrace.length === 0) {
        return `<div class="report-muted">No adaptive questioning trace available.</div>`;
    }

    return adaptiveTrace
        .map(
            (item) => `
            <div class="trace-card">
                <div class="report-label">Turn ${escapeHtml(item.turn || "N/A")} | ${escapeHtml(item.decision_type || "N/A")} | Skill: ${escapeHtml(item.skill_focus || "N/A")}</div>
                <div class="trace-section"><strong>Question Answered:</strong> ${escapeHtml(item.question_answered || "N/A")}</div>
                <div class="trace-section"><strong>Candidate Answer:</strong> ${escapeHtml(item.candidate_answer || "N/A")}</div>
                <div class="trace-section"><strong>Detected Weakness:</strong> ${escapeHtml(item.weakest_dimension || "N/A")}</div>
                <div class="trace-section"><strong>Why Follow-up Was Asked:</strong> ${escapeHtml(item.follow_up_reason || "N/A")}</div>
                <div class="trace-section"><strong>Next Question:</strong> ${escapeHtml(item.next_question || "N/A")}</div>
                <div class="trace-section"><strong>Weighted Score:</strong> ${escapeHtml((item.scores || {}).weighted_overall_score ?? 0)}</div>
            </div>
        `
        )
        .join("");
}
