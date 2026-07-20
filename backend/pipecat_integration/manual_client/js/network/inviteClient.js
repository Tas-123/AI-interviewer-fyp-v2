/**
 * Resolve a recruiter invite token and optionally bind a voice session_id.
 * Talks only to the Recruiter Dashboard API — not the interview engine.
 */

export async function resolveInvite(recruiterApiUrl, inviteToken) {
    const base = (recruiterApiUrl || "").replace(/\/$/, "");
    const token = (inviteToken || "").trim();
    if (!base || !token) {
        return null;
    }
    const res = await fetch(`${base}/api/interviews/${encodeURIComponent(token)}`, {
        headers: { Accept: "application/json" },
    });
    if (!res.ok) {
        const text = await res.text();
        let detail = res.statusText;
        try {
            detail = JSON.parse(text)?.detail || detail;
        } catch {
            /* keep statusText */
        }
        throw new Error(
            typeof detail === "string" ? detail : "Invite not found"
        );
    }
    return res.json();
}

export async function bindInviteSession(recruiterApiUrl, inviteToken, sessionId) {
    const base = (recruiterApiUrl || "").replace(/\/$/, "");
    const token = (inviteToken || "").trim();
    const sid = (sessionId || "").trim();
    if (!base || !token || !sid) {
        return null;
    }
    const res = await fetch(
        `${base}/api/interviews/${encodeURIComponent(token)}/bind`,
        {
            method: "POST",
            headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
            },
            body: JSON.stringify({ session_id: sid }),
        }
    );
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text || res.statusText || "Bind failed");
    }
    return res.json();
}
