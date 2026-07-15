import { SESSION_PHASES } from "./core/appState.js";
import { createConversationStore } from "./core/conversationStore.js";
import { getDomRefs } from "./ui/dom.js";
import { createStatusView } from "./ui/statusView.js";
import { createVisualizerView } from "./ui/visualizerView.js";
import { createConversationView } from "./ui/conversationView.js";
import { createDebugLogView } from "./ui/debugLogView.js";
import {
    renderInterviewReport,
    showReportError,
    showReportLoading,
} from "./ui/report/renderReport.js";
import { fetchLatestReport } from "./network/reportClient.js";
import { createVoiceSession } from "./network/voiceSession.js";

const cfg = window.MANUAL_CLIENT_CONFIG || {};

function buildUiBundle(refs) {
    const conversation = createConversationView(refs);
    const status = createStatusView(refs);
    const conversationStore = createConversationStore(conversation, {
        onPhase: (phase) => {
            if (phase === "speaking") status.setBotSpeaking(true);
            else if (phase === "listening" || phase === "thinking") {
                status.setBotSpeaking(false);
            }
        },
    });
    return {
        refs,
        status,
        visualizer: createVisualizerView(refs),
        conversation,
        conversationStore,
        debug: createDebugLogView(refs),
    };
}

async function loadReport(ui) {
    showReportLoading(ui.refs.reportPanel);
    try {
        const data = await fetchLatestReport(cfg.reportUrl);
        renderInterviewReport(ui.refs.reportPanel, data);
        ui.debug.log("Final interview report loaded.", "success");
    } catch (err) {
        showReportError(
            ui.refs.reportPanel,
            `Could not fetch report: ${err.message}. Is the report HTTP server running?`
        );
        ui.debug.log(`Report fetch failed: ${err.message}`, "error");
    }
}

function scheduleReportLoad(ui) {
    // Server writes report on WebSocket disconnect; give it a moment.
    setTimeout(() => loadReport(ui), 1500);
}

function wireControls(session, ui) {
    const { btnConnect, btnDisconnect } = ui.refs;

    btnConnect.addEventListener("click", async () => {
        btnConnect.disabled = true;
        btnDisconnect.disabled = true;
        try {
            ui.conversationStore?.reset();
            ui.conversation.clear();
            await session.connect();
            btnConnect.disabled = true;
            btnDisconnect.disabled = false;
        } catch (err) {
            ui.debug.log(`Failed to start session: ${err.message}`, "error");
            btnConnect.disabled = false;
            btnDisconnect.disabled = true;
        }
    });

    btnDisconnect.addEventListener("click", () => {
        session.disconnect();
        btnConnect.disabled = false;
        btnDisconnect.disabled = true;
        // Report fetch is handled by onSessionEnded (natural end + Disconnect).
    });
}

function bootstrap() {
    const refs = getDomRefs();
    const ui = buildUiBundle(refs);

    ui.status.setPhase(SESSION_PHASES.SETUP);
    ui.conversation.showEmpty(
        "Connect your microphone to begin. Your conversation with the interviewer will appear here."
    );
    ui.debug.log("Ready. Click Connect to begin the voice interview.", "info");

    let reportLoadScheduled = false;
    const scheduleOnce = () => {
        if (reportLoadScheduled) return;
        reportLoadScheduled = true;
        scheduleReportLoad(ui);
        // Allow a new load after the next reconnect.
        setTimeout(() => {
            reportLoadScheduled = false;
        }, 5000);
    };

    const session = createVoiceSession(
        {
            wsUrl: cfg.wsUrl || "ws://localhost:8765",
            reportUrl: cfg.reportUrl || "http://localhost:8766/latest-report",
            micGain: Number(cfg.micGain) > 0 ? Number(cfg.micGain) : 2.5,
            suppressMicWhileBotSpeaking: cfg.suppressMicWhileBotSpeaking !== false,
            botAudioJitterBufferSec: cfg.botAudioJitterBufferSec ?? 0.15,
            bargeIn: cfg.bargeIn || {},
        },
        ui,
        {
            onSessionEnded: () => {
                ui.debug.log("Session ended — loading interview report…", "info");
                scheduleOnce();
                const { btnConnect, btnDisconnect } = ui.refs;
                if (btnConnect) btnConnect.disabled = false;
                if (btnDisconnect) btnDisconnect.disabled = true;
            },
        }
    );

    wireControls(session, ui);
}

bootstrap();
