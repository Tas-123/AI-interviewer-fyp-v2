export async function fetchLatestReport(reportUrl) {
    const res = await fetch(reportUrl, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) {
        throw new Error(data.error || "Report not ready");
    }
    return data;
}
