/** Central DOM references — update index.html ids here when layout changes. */
export function getDomRefs() {
    return {
        btnConnect: document.getElementById("btn-connect"),
        btnDisconnect: document.getElementById("btn-disconnect"),
        connectionStatus: document.getElementById("connection-status"),
        micStatus: document.getElementById("mic-status"),
        sessionPhase: document.getElementById("session-phase"),
        conversationPanel: document.getElementById("conversation-panel"),
        debugLogPanel: document.getElementById("debug-log-panel"),
        visualizer: document.getElementById("visualizer"),
        visualizerBars: document.querySelectorAll("#visualizer .bar"),
        visualizerLabel: document.getElementById("visualizer-label"),
        reportPanel: document.getElementById("report-panel"),
        inputName: document.getElementById("input-name"),
        inputResume: document.getElementById("input-resume"),
    };
}
