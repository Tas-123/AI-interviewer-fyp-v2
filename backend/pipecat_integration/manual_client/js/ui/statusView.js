const PHASE_LABELS = {
    setup: "Ready to connect",
    live: "Interview in progress",
    ended: "Session ended — see confirmation below",
};

export function createStatusView(refs) {
    function setConnection(connected, connecting = false) {
        if (connecting) {
            refs.connectionStatus.innerHTML =
                '<span class="indicator connecting"></span> Connecting…';
            return;
        }

        if (connected) {
            refs.connectionStatus.innerHTML =
                '<span class="indicator online"></span> Connected';
            refs.micStatus.textContent = "Streaming";
            return;
        }

        refs.connectionStatus.innerHTML =
            '<span class="indicator offline"></span> Disconnected';
        refs.micStatus.textContent = "Inactive";
    }

    function setPhase(phase) {
        if (!refs.sessionPhase) return;
        refs.sessionPhase.textContent = PHASE_LABELS[phase] || phase;
    }

    function setBotSpeaking(speaking) {
        if (!refs.micStatus) return;
        if (speaking) {
            refs.micStatus.innerHTML =
                '<span class="indicator speaking"></span> Bot speaking';
            return;
        }
        refs.micStatus.textContent = "Streaming";
    }

    function setUserSpeaking(speaking) {
        if (!refs.visualizer) return;
        refs.visualizer.classList.toggle("speaking", speaking);
        if (refs.visualizerLabel) {
            refs.visualizerLabel.textContent = speaking
                ? "You are speaking (mic active)"
                : "Microphone level";
        }
    }

    return { setConnection, setPhase, setBotSpeaking, setUserSpeaking };
}
