import { SESSION_PHASES } from "./core/appState.js";
import { createConversationStore } from "./core/conversationStore.js";
import { getDomRefs } from "./ui/dom.js";
import { createStatusView } from "./ui/statusView.js";
import { createVisualizerView } from "./ui/visualizerView.js";
import { createConversationView } from "./ui/conversationView.js";
import { createDebugLogView } from "./ui/debugLogView.js";
import { createPreInterviewFlow } from "./ui/preInterviewFlow.js";
import {
    renderInterviewReport,
    showReportError,
    showReportLoading,
} from "./ui/report/renderReport.js";
import { fetchLatestReportMatched } from "./network/reportClient.js";
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

async function loadReport(ui, expectedSessionId = null) {
    showReportLoading(ui.refs.reportPanel);
    try {
        const data = await fetchLatestReportMatched(cfg.reportUrl, expectedSessionId);
        renderInterviewReport(ui.refs.reportPanel, data);
        const reportSessionId = data?.report_meta?.session_id || "unknown";
        ui.debug.log(
            `Final interview report loaded (session ${reportSessionId}).`,
            "success"
        );
    } catch (err) {
        showReportError(
            ui.refs.reportPanel,
            `Could not fetch report: ${err.message}. Is the report HTTP server running?`
        );
        ui.debug.log(`Report fetch failed: ${err.message}`, "error");
    }
}

function scheduleReportLoad(ui, expectedSessionId = null) {
    setTimeout(() => loadReport(ui, expectedSessionId), 1500);
}

async function connectAndStartSession(session, ui) {
    const { btnConnect, btnDisconnect } = ui.refs;
    if (btnConnect) btnConnect.disabled = true;
    if (btnDisconnect) btnDisconnect.disabled = true;
    try {
        ui.conversationStore?.reset();
        ui.conversation.clear();
        showReportLoading(ui.refs.reportPanel);
        await session.connectAndStart();
        if (btnConnect) btnConnect.disabled = true;
        if (btnDisconnect) btnDisconnect.disabled = false;
    } catch (err) {
        ui.debug.log(`Failed to start session: ${err.message}`, "error");
        if (btnConnect) btnConnect.disabled = false;
        if (btnDisconnect) btnDisconnect.disabled = true;
        throw err;
    }
}

function wireControls(session, ui) {
    const { btnConnect, btnDisconnect } = ui.refs;

    btnConnect?.addEventListener("click", async () => {
        try {
            await connectAndStartSession(session, ui);
        } catch (_) {
            /* logged in connectAndStartSession */
        }
    });

    btnDisconnect?.addEventListener("click", () => {
        session.disconnect();
        if (btnConnect) btnConnect.disabled = false;
        if (btnDisconnect) btnDisconnect.disabled = true;
    });
}

function bootstrap() {
    const refs = getDomRefs();
    const ui = buildUiBundle(refs);

    ui.status.setPhase(SESSION_PHASES.SETUP);
    ui.conversation.showEmpty(
        "Complete the welcome steps, then your conversation with the interviewer will appear here."
    );
    ui.debug.log("Welcome screen ready. Click Start Interview to begin.", "info");

    let reportLoadScheduled = false;
    let expectedSessionId = null;
    let preInterview = null;

    const scheduleOnce = (sessionId) => {
        if (reportLoadScheduled) return;
        reportLoadScheduled = true;
        scheduleReportLoad(ui, sessionId || expectedSessionId);
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
            onSessionStarted: (sessionId) => {
                expectedSessionId = sessionId;
                ui.debug.log(`Voice session started (${sessionId}).`, "info");
            },
            onSessionEnded: (sessionId) => {
                ui.debug.log("Session ended — loading interview report…", "info");
                scheduleOnce(sessionId);
                const { btnConnect, btnDisconnect } = ui.refs;
                if (btnConnect) btnConnect.disabled = false;
                if (btnDisconnect) btnDisconnect.disabled = true;
            },
            onPreambleLine: (text) => preInterview?.onPreambleLine(text),
            onInstructionsComplete: () => preInterview?.onInstructionsComplete(),
        }
    );

    wireControls(session, ui);

    preInterview = createPreInterviewFlow(refs, {
        onLog: (msg, level) => ui.debug.log(msg, level),
        onStartInstructions: async () => {
            const { btnConnect, btnDisconnect } = ui.refs;
            if (btnConnect) {
                btnConnect.disabled = true;
                btnConnect.hidden = true;
            }
            if (btnDisconnect) btnDisconnect.disabled = false;
            ui.conversationStore?.reset();
            ui.conversation.clear();
            // No mic yet — only Cartesia playback for instructions.
            await session.connect({
                preamble: true,
                enableMicUpload: false,
                needMic: false,
            });
            session.sendInstructions();
        },
        onReadyStart: async () => {
            const { btnConnect, btnDisconnect } = ui.refs;
            ui.conversationStore?.reset();
            ui.conversation.clear();
            showReportLoading(ui.refs.reportPanel);
            await session.ensureMicrophone();
            session.sendStart();
            if (btnConnect) {
                btnConnect.disabled = true;
                btnConnect.hidden = false;
            }
            if (btnDisconnect) btnDisconnect.disabled = false;
        },
    });
    preInterview.wire();
}

bootstrap();
