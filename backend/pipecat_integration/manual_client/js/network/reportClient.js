export async function fetchLatestReport(reportUrl) {
    const res = await fetch(reportUrl, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.error || "Report not ready");
    }
    return data;
}

function extractReportSessionId(report) {
    if (!report || typeof report !== "object") return "";
    const meta = report.report_meta || {};
    const legacy = report.interview_metadata || {};
    return meta.session_id || legacy.session_id || "";
}

/**
 * Poll /latest-report until report_meta.session_id matches the active voice session.
 * Falls back to the latest report if matching fails after retries.
 */
export async function fetchLatestReportMatched(
    reportUrl,
    expectedSessionId,
    { maxAttempts = 8, intervalMs = 400 } = {}
) {
    if (!expectedSessionId) {
        return fetchLatestReport(reportUrl);
    }

    let lastMismatch = null;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        try {
            const data = await fetchLatestReport(reportUrl);
            const reportSessionId = extractReportSessionId(data);
            if (reportSessionId === expectedSessionId) {
                return data;
            }
            lastMismatch = new Error(
                `Report session mismatch (expected ${expectedSessionId}, got ${reportSessionId || "unknown"})`
            );
        } catch (err) {
            lastMismatch = err;
        }

        if (attempt < maxAttempts - 1) {
            await new Promise((resolve) => setTimeout(resolve, intervalMs));
        }
    }

    // Fallback: show newest report rather than failing the UI entirely.
    try {
        return await fetchLatestReport(reportUrl);
    } catch (err) {
        throw lastMismatch || err;
    }
}
