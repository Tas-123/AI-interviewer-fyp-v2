import { SESSION_PHASES } from "./core/appState.js";
import { createConversationStore } from "./core/conversationStore.js";
import { getDomRefs } from "./ui/dom.js";
import { createStatusView } from "./ui/statusView.js";
import { createVisualizerView } from "./ui/visualizerView.js";
import { createConversationView } from "./ui/conversationView.js";
import { createDebugLogView } from "./ui/debugLogView.js";
import { createPreInterviewFlow } from "./ui/preInterviewFlow.js";
import {
    renderCompletionMessage,
    renderCompletionMessageImmediate,
    showReportError,
    showReportLoading,
} from "./ui/report/renderReport.js?v=20260719c";
import { fetchLatestReportMatched } from "./network/reportClient.js?v=20260719c";
import { createVoiceSession } from "./network/voiceSession.js?v=20260719c";
import {
    bindInviteSession,
    resolveInvite,
} from "./network/inviteClient.js?v=20260720a";
import {
    applyInterviewMeta,
    getSelectedSkills,
    metaForRole,
    syncSelectedSkillsToShell,
} from "./ui/interviewMeta.js?v=20260720d";

const cfg = window.MANUAL_CLIENT_CONFIG || {};
const DEFAULT_HTML =
    cfg.reportHtmlUrl || "http://localhost:8766/latest-report.html";

/** Resolved at bootstrap; used for start payload + session bind. */
let resolvedTargetRole = cfg.targetRole || "junior_ai_engineer";
let resolvedDisplayTitle = "";
let activeInviteToken = (cfg.inviteToken || "").trim();

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

async function loadCompletion(ui, expectedSessionId = null) {
    const htmlOpts = { reportHtmlUrl: DEFAULT_HTML };
    // Always show thank-you + link first (do not wait on HTTP).
    renderCompletionMessageImmediate(ui.refs.reportPanel, DEFAULT_HTML);
    try {
        const data = await fetchLatestReportMatched(cfg.reportUrl, expectedSessionId);
        renderCompletionMessage(ui.refs.reportPanel, data, htmlOpts);
        const reportSessionId =
            data?.report?.report_meta?.session_id ||
            data?.report_meta?.session_id ||
            "unknown";
        ui.debug.log(
            `Session finalized — completion message shown (report session ${reportSessionId}).`,
            "success"
        );
    } catch (err) {
        showReportError(
            ui.refs.reportPanel,
            `Recruiter report link may be unavailable: ${err.message}`
        );
        ui.debug.log(`Report fetch failed: ${err.message}`, "error");
    }
}

function scheduleReportLoad(ui, expectedSessionId = null) {
    // Show thank-you immediately on disconnect; refresh link after short delay.
    renderCompletionMessageImmediate(ui.refs.reportPanel, DEFAULT_HTML);
    setTimeout(() => loadCompletion(ui, expectedSessionId), 1500);
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

    refs._syncSkills = () => syncSelectedSkillsToShell(refs);
    // Paint lobby from role query param immediately; invite may refine later.
    applyInterviewMeta(refs, metaForRole(resolvedTargetRole));

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

    const finishBootstrap = () => {
        const session = createVoiceSession(
            {
                wsUrl: cfg.wsUrl || "ws://localhost:8765",
                reportUrl: cfg.reportUrl || "http://localhost:8766/latest-report",
                micGain: Number(cfg.micGain) > 0 ? Number(cfg.micGain) : 2.5,
                suppressMicWhileBotSpeaking: cfg.suppressMicWhileBotSpeaking !== false,
                botAudioJitterBufferSec: cfg.botAudioJitterBufferSec ?? 0.15,
                bargeIn: cfg.bargeIn || {},
                targetRole: resolvedTargetRole,
            },
            ui,
            {
                onSessionStarted: (sessionId) => {
                    expectedSessionId = sessionId;
                    ui.debug.log(`Voice session started (${sessionId}).`, "info");
                    if (activeInviteToken && cfg.recruiterApiUrl) {
                        bindInviteSession(
                            cfg.recruiterApiUrl,
                            activeInviteToken,
                            sessionId
                        )
                            .then(() => {
                                ui.debug.log(
                                    `Invite bound to session ${sessionId}.`,
                                    "success"
                                );
                            })
                            .catch((err) => {
                                ui.debug.log(
                                    `Invite bind skipped: ${err.message}`,
                                    "info"
                                );
                            });
                    }
                },
                onSessionEnded: (sessionId) => {
                    ui.debug.log("Session ended — showing completion message…", "info");
                    // Paint thank-you + link immediately (before the 1.5s report poll).
                    renderCompletionMessageImmediate(ui.refs.reportPanel, DEFAULT_HTML);
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
    };

    if (activeInviteToken && cfg.recruiterApiUrl) {
        ui.debug.log(`Resolving invite ${activeInviteToken}…`, "info");
        resolveInvite(cfg.recruiterApiUrl, activeInviteToken)
            .then((invite) => {
                if (invite?.target_role) {
                    resolvedTargetRole = invite.target_role;
                }
                resolvedDisplayTitle = invite?.display_title || "";
                applyInterviewMeta(refs, {
                    display_title:
                        invite?.display_title ||
                        metaForRole(resolvedTargetRole).display_title,
                    description:
                        invite?.description ||
                        metaForRole(resolvedTargetRole).description,
                    suggested_skills:
                        invite?.suggested_skills?.length
                            ? invite.suggested_skills
                            : metaForRole(resolvedTargetRole).suggested_skills,
                });
                ui.debug.log(
                    `Invite OK — ${resolvedDisplayTitle || resolvedTargetRole}.`,
                    "success"
                );
            })
            .catch((err) => {
                applyInterviewMeta(refs, metaForRole(resolvedTargetRole));
                ui.debug.log(
                    `Invite resolve failed (${err.message}); using role ${resolvedTargetRole}.`,
                    "info"
                );
            })
            .finally(() => finishBootstrap());
    } else {
        applyInterviewMeta(refs, metaForRole(resolvedTargetRole));
        finishBootstrap();
    }
}

bootstrap();
