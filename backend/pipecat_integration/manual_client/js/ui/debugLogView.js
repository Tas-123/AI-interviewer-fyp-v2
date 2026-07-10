export function createDebugLogView(refs) {
    const panel = refs.debugLogPanel;

    function log(msg, type = "info") {
        if (!panel) return;
        const time = new Date().toLocaleTimeString();
        const entry = document.createElement("div");
        entry.className = `log-entry ${type}`;
        entry.textContent = `[${time}] ${msg}`;
        panel.appendChild(entry);
        panel.scrollTop = panel.scrollHeight;
    }

    return { log };
}
