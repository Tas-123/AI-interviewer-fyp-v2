// Pipecat WebSocket Manual Client Logic

const cfg = window.MANUAL_CLIENT_CONFIG || {};
const WS_URL = cfg.wsUrl || "ws://localhost:8765";
const REPORT_URL = cfg.reportUrl || "http://localhost:8766/latest-report";
const bargeCfg = cfg.bargeIn || {};

// UI Elements
const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const connectionStatusText = document.getElementById("connection-status");
const micStatusText = document.getElementById("mic-status");
const logPanel = document.getElementById("log-panel");
const visualizerBars = document.querySelectorAll(".bar");
const reportPanel = document.getElementById("report-panel");

// Audio state variables
let audioContext = null;
let micStream = null;
let micSource = null;
let scriptProcessor = null;
let ws = null;
let isConnected = false;

// Audio output queuing variables (prevents overlaps/gaps)
let nextBotAudioTime = 0;
let botAudioQueueDepth = 0;
let isBotAudioPlaying = false;
const suppressMicWhileBotSpeaking = cfg.suppressMicWhileBotSpeaking !== false;
const BOT_AUDIO_JITTER_BUFFER_SEC = cfg.botAudioJitterBufferSec ?? 0.15;
let botAudioCooldownTimeout = null;
let botChunksReceived = 0;

// Barge-in detection constants (from config.js)
const BARGE_IN_RMS_THRESHOLD = bargeCfg.rmsThreshold ?? 0.035;
const BARGE_IN_MIN_FRAMES = bargeCfg.minFrames ?? 3;
const BARGE_IN_IGNORE_AFTER_BOT_START_MS = bargeCfg.ignoreAfterBotStartMs ?? 400;
const BARGE_IN_MIC_ALLOW_MS = bargeCfg.micAllowMs ?? 2500;
const BARGE_IN_DISCARD_BOT_AUDIO_MS = bargeCfg.discardBotAudioMs ?? 1200;

// Barge-in state variables
const activeBotSources = new Set();
let bargeInConsecutiveFrames = 0;
let botSpeechStartedAt = 0;
let bargeInMicAllowUntil = 0;
let bargeInDiscardBotAudioUntil = 0;
let bargeInTriggered = false;

// Log to panel helper
function log(msg, type = "info") {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = `log-entry ${type}`;
    entry.innerHTML = `[${time}] ${msg}`;
    logPanel.appendChild(entry);
    logPanel.scrollTop = logPanel.scrollHeight;
}

// UI State management
function setUIState(connected, connecting = false) {
    isConnected = connected;
    btnConnect.disabled = connected || connecting;
    btnDisconnect.disabled = !connected;

    if (connecting) {
        connectionStatusText.innerHTML = `<span class="indicator connecting"></span> Connecting...`;
    } else if (connected) {
        connectionStatusText.innerHTML = `<span class="indicator online"></span> Connected to Bot`;
        micStatusText.innerText = "Active (Streaming)";
    } else {
        connectionStatusText.innerHTML = `<span class="indicator offline"></span> Disconnected`;
        micStatusText.innerText = "Inactive";
        // Reset visualizer bars
        visualizerBars.forEach(bar => bar.style.height = "8px");
    }
}

// Start bot session
async function startSession() {
    log("Initializing local AudioContext...", "info");
    // Reset queue variables on reconnect
    nextBotAudioTime = 0;
    botAudioQueueDepth = 0;
    isBotAudioPlaying = false;
    botChunksReceived = 0;
    if (botAudioCooldownTimeout) {
        clearTimeout(botAudioCooldownTimeout);
        botAudioCooldownTimeout = null;
    }
    // Reset barge-in state
    bargeInConsecutiveFrames = 0;
    botSpeechStartedAt = 0;
    bargeInMicAllowUntil = 0;
    bargeInDiscardBotAudioUntil = 0;
    bargeInTriggered = false;
    activeBotSources.clear();
    try {
        // Initialize AudioContext at 16kHz mono (STT standard)
        audioContext = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        log(`AudioContext initialized. Actual sample rate: ${audioContext.sampleRate} Hz`, "info");
        
        // Request Mic permission
        log("Requesting microphone permissions...", "info");
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true
            }
        });
        log("Microphone access granted.", "success");

        setUIState(false, true); // Connecting state
        log(`Connecting to Pipecat WebSocket Bot at ${WS_URL}...`, "info");
        
        ws = new WebSocket(WS_URL);

        ws.onopen = () => {
            log("WebSocket connection established successfully.", "success");
            setUIState(true);

            // Send start control trigger to pipeline (optional resume profile)
            log("Sending startup handshake control frame...", "info");
            const displayName = document.getElementById("input-name")?.value?.trim() || "";
            const resumeText = document.getElementById("input-resume")?.value?.trim() || "";
            const startPayload = { type: "start", target_role: "junior_ai_engineer" };
            if (displayName) startPayload.display_name = displayName;
            if (resumeText) startPayload.resume_text = resumeText;
            ws.send(JSON.stringify(startPayload));

            // Setup mic processing nodes
            micSource = audioContext.createMediaStreamSource(micStream);
            
            // ScriptProcessorNode chunk sizes: 4096 (standard, highly compatible)
            scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

            let chunksSent = 0;
            let bytesSent = 0;
            let nonSilentChunks = 0;
            let lastLogTime = Date.now();

            scriptProcessor.onaudioprocess = (e) => {
                if (!isConnected || ws.readyState !== WebSocket.OPEN) return;

                const inputChannel = e.inputBuffer.getChannelData(0); // Float32Array [-1.0, 1.0]

                // Calculate volume RMS FIRST (before any suppression) for barge-in detection
                let sum = 0;
                let isSilent = true;
                for (let i = 0; i < inputChannel.length; i++) {
                    sum += inputChannel[i] * inputChannel[i];
                    if (inputChannel[i] !== 0) {
                        isSilent = false;
                    }
                }
                const rms = Math.sqrt(sum / inputChannel.length);

                // If bot is speaking, handle barge-in detection instead of blanket suppression
                if (suppressMicWhileBotSpeaking && isBotAudioPlaying) {
                    // Always update visualizer so user sees their mic level
                    updateVisualizer(rms);

                    const now = Date.now();

                    // If we already triggered barge-in and are in the mic-allow window, send audio
                    if (bargeInTriggered && now < bargeInMicAllowUntil) {
                        // Fall through to send mic audio below
                    } else if (bargeInTriggered) {
                        // Mic-allow window expired, stop sending
                        bargeInTriggered = false;
                        bargeInConsecutiveFrames = 0;
                        return;
                    } else {
                        // Not yet barge-in — check for one
                        const msSinceBotStart = now - botSpeechStartedAt;

                        // Ignore early echo right after bot starts
                        if (msSinceBotStart < BARGE_IN_IGNORE_AFTER_BOT_START_MS) {
                            bargeInConsecutiveFrames = 0;
                            return;
                        }

                        if (rms > BARGE_IN_RMS_THRESHOLD) {
                            bargeInConsecutiveFrames++;
                        } else {
                            bargeInConsecutiveFrames = 0;
                            return;
                        }

                        if (bargeInConsecutiveFrames >= BARGE_IN_MIN_FRAMES) {
                            // Barge-in confirmed!
                            log(`CLIENT_BARGE_IN_DETECTED: RMS=${rms.toFixed(4)}, consecutive=${bargeInConsecutiveFrames}`, "info");
                            stopBotAudioPlayback("user_barge_in");
                            bargeInTriggered = true;
                            bargeInMicAllowUntil = now + BARGE_IN_MIC_ALLOW_MS;

                            // Notify server
                            if (ws && ws.readyState === WebSocket.OPEN) {
                                ws.send(JSON.stringify({ type: "interrupt", reason: "user_barge_in" }));
                            }
                            // Fall through to send current mic chunk
                        } else {
                            // Not enough consecutive frames yet
                            return;
                        }
                    }
                } else {
                    // Bot not speaking — normal visualizer update
                    updateVisualizer(rms);
                }

                // Convert Float32 values to signed 16-bit PCM Integers
                const pcmData = new Int16Array(inputChannel.length);
                for (let i = 0; i < inputChannel.length; i++) {
                    let val = Math.floor(inputChannel[i] * 32767);
                    val = Math.max(-32768, Math.min(32767, val));
                    pcmData[i] = val;
                }

                // Send raw PCM bytes to bot
                ws.send(pcmData.buffer);

                chunksSent++;
                bytesSent += pcmData.byteLength;
                if (!isSilent) {
                    nonSilentChunks++;
                }

                const now_log = Date.now();
                if (now_log - lastLogTime >= 1000) {
                    log(`Audio stream: Sent ${chunksSent} chunks (${bytesSent} bytes) to server. Non-silent: ${nonSilentChunks}/${chunksSent}.`, "info");
                    chunksSent = 0;
                    bytesSent = 0;
                    nonSilentChunks = 0;
                    lastLogTime = now_log;
                }
            };

            micSource.connect(scriptProcessor);
            scriptProcessor.connect(audioContext.destination);
            log("Microphone stream is live and routing audio.", "success");
        };

        ws.onmessage = async (event) => {
            if (event.data instanceof Blob) {
                // Discard stale bot audio chunks after barge-in
                if (Date.now() < bargeInDiscardBotAudioUntil) {
                    botChunksReceived++;
                    if (botChunksReceived % 10 === 0) {
                        log("Discarding stale bot audio after barge-in.", "info");
                    }
                    return;
                }

                const arrayBuffer = await event.data.arrayBuffer();
                botChunksReceived++;
                
                const shouldLog = (botChunksReceived % 20 === 0 || botChunksReceived === 1);

                if (shouldLog) {
                    log(`Received bot audio chunk #${botChunksReceived}: ${arrayBuffer.byteLength} bytes`, "server");
                }

                try {
                    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
                    
                    if (shouldLog) {
                        const queueDuration = Math.max(0, nextBotAudioTime - audioContext.currentTime);
                        log(
                            `Decoded bot audio: duration=${audioBuffer.duration.toFixed(2)}s. Queue depth: ${botAudioQueueDepth}, remaining queue duration: ${queueDuration.toFixed(2)}s (Jitter Buffer: ${BOT_AUDIO_JITTER_BUFFER_SEC}s)`,
                            "server"
                        );
                    }

                    playOutputBuffer(audioBuffer);
                    
                    if (shouldLog) {
                        log("Bot audio playback scheduled.", "success");
                    }
                } catch (err) {
                    log(`Bot audio decode/playback error: ${err.message || err}`, "error");
                    console.error("WAV playback decoding error:", err);
                }
            } else {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === "text") {
                        log(`Bot says: "${msg.text}"`, "server");
                    } else if (msg.type === "end") {
                        log("Session wrap-up signal received from server.", "info");
                        disconnectSession();
                    } else {
                        log(`Control message: ${event.data}`, "info");
                    }
                } catch (e) {
                    log(`Raw Text Message: ${event.data}`, "info");
                }
            }
        };

        ws.onerror = (err) => {
            log(`WebSocket connection error encountered.`, "error");
            console.error("WS Error:", err);
        };

        ws.onclose = () => {
            log("WebSocket connection closed.", "info");
            disconnectSession();
        };

    } catch (err) {
        log(`Failed to initiate voice session: ${err.message}`, "error");
        disconnectSession();
    }
}

// Stop all active bot audio sources (for barge-in)
function stopBotAudioPlayback(reason) {
    log(`Barge-in detected: stopped bot audio playback. Reason: ${reason}`, "info");
    activeBotSources.forEach((src) => {
        try {
            src.stop();
        } catch (e) {
            // Already stopped or invalid state — safe to ignore
        }
    });
    activeBotSources.clear();
    nextBotAudioTime = 0;
    botAudioQueueDepth = 0;
    isBotAudioPlaying = false;
    bargeInConsecutiveFrames = 0;
    if (botAudioCooldownTimeout) {
        clearTimeout(botAudioCooldownTimeout);
        botAudioCooldownTimeout = null;
    }
    bargeInDiscardBotAudioUntil = Date.now() + BARGE_IN_DISCARD_BOT_AUDIO_MS;
}

// Play incoming audio chunks consecutively without overlap gaps using AudioContext scheduling
function playOutputBuffer(audioBuffer) {
    if (!audioContext || audioContext.state === "closed") return;

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    const currentTime = audioContext.currentTime;
    const startAt = Math.max(currentTime + BOT_AUDIO_JITTER_BUFFER_SEC, nextBotAudioTime);
    
    source.start(startAt);
    nextBotAudioTime = startAt + audioBuffer.duration;

    // Track playing state and queue depth
    const wasEmpty = botAudioQueueDepth === 0;
    botAudioQueueDepth++;
    isBotAudioPlaying = true;
    activeBotSources.add(source);

    // Record when bot speech starts for barge-in grace period
    if (wasEmpty) {
        botSpeechStartedAt = Date.now();
        bargeInConsecutiveFrames = 0;
        bargeInTriggered = false;
    }

    if (botAudioCooldownTimeout) {
        clearTimeout(botAudioCooldownTimeout);
        botAudioCooldownTimeout = null;
    }

    source.onended = () => {
        activeBotSources.delete(source);
        botAudioQueueDepth--;
        if (botAudioQueueDepth <= 0) {
            botAudioQueueDepth = 0;
            if (!botAudioCooldownTimeout) {
                botAudioCooldownTimeout = setTimeout(() => {
                    isBotAudioPlaying = false;
                    botAudioCooldownTimeout = null;
                }, 300);
            }
        }
    };
}

// Animate visualizer height dynamically based on mic RMS volume
function updateVisualizer(rms) {
    // scale RMS to a readable height percentage
    const maxVolume = 0.25;
    const percentage = Math.min(100, Math.max(10, (rms / maxVolume) * 100));
    
    visualizerBars.forEach((bar, idx) => {
        // Add dynamic micro-animations/fluctuations to look premium
        const noise = (Math.sin(Date.now() * 0.05 + idx) + 1) * 5; 
        bar.style.height = `${percentage + noise}%`;
    });
}


// Render final report in the browser UI
function renderReport(payload) {
    if (!reportPanel) return;

    const report = payload.report || payload;

    const ws = report.weighted_score_summary || {};
    const consistency = report.consistency_rating || {};
    const metadata = report.interview_metadata || {};
    const trend = report.performance_trend_analysis || {};
    const behavior = report.behavioral_profile || {};
    const recruiter = report.recruiter_summary || {};
    const skillMap = report.skill_coverage_map || {};
    const adaptiveTrace = report.adaptive_questioning_trace || [];

    const listHtml = (items, emptyText = "No items available.") => {
        if (!items || items.length === 0) {
            return `<div class="report-muted">${emptyText}</div>`;
        }
        return `<ul class="report-list">${items.map(item => `<li>${item}</li>`).join("")}</ul>`;
    };

    const skillHtml = Object.entries(skillMap).length === 0
        ? `<div class="report-muted">No skill coverage data available.</div>`
        : Object.entries(skillMap).map(([skill, data]) => {
            const status = data.status || "unknown";
            return `
                <div class="report-item">
                    <div class="report-label">${skill}</div>
                    <div class="report-value">${status}</div>
                    <div class="report-muted">
                        Mentions: ${data.mentions ?? 0} |
                        Avg Score: ${data.avg_score ?? 0} |
                        Turns: ${(data.evidence_turns || []).join(", ") || "None"}
                    </div>
                </div>
            `;
        }).join("");

    const traceHtml = adaptiveTrace.length === 0
        ? `<div class="report-muted">No adaptive questioning trace available.</div>`
        : adaptiveTrace.map(item => `
            <div class="trace-card">
                <div class="report-label">Turn ${item.turn || "N/A"} | ${item.decision_type || "N/A"} | Skill: ${item.skill_focus || "N/A"}</div>
                <div class="trace-section"><strong>Question Answered:</strong> ${item.question_answered || "N/A"}</div>
                <div class="trace-section"><strong>Candidate Answer:</strong> ${item.candidate_answer || "N/A"}</div>
                <div class="trace-section"><strong>Detected Weakness:</strong> ${item.weakest_dimension || "N/A"}</div>
                <div class="trace-section"><strong>Why Follow-up Was Asked:</strong> ${item.follow_up_reason || "N/A"}</div>
                <div class="trace-section"><strong>Next Question:</strong> ${item.next_question || "N/A"}</div>
                <div class="trace-section"><strong>Weighted Score:</strong> ${(item.scores || {}).weighted_overall_score ?? 0}</div>
            </div>
        `).join("");

    reportPanel.innerHTML = `
        <div class="report-grid">
            <div class="report-item">
                <div class="report-label">Hire Signal</div>
                <div class="report-value">${ws.final_hire_signal || recruiter.final_signal || "N/A"}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Average Score</div>
                <div class="report-value">${ws.avg_weighted_overall ?? recruiter.average_weighted_score ?? 0}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Consistency</div>
                <div class="report-value">${consistency.consistency_rating || "N/A"}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Total Turns</div>
                <div class="report-value">${metadata.total_turns ?? 0}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Trend</div>
                <div class="report-value">${trend.performance_trend_label || "N/A"}</div>
            </div>
            <div class="report-item">
                <div class="report-label">Thinking Style</div>
                <div class="report-value">${behavior.thinking_style || "N/A"}</div>
            </div>
        </div>

        <div class="report-section">
            <div class="report-section-title">Recruiter Summary</div>
            <div class="report-text">${recruiter.overall_observation || "No recruiter summary available."}</div>
            <div class="report-muted">${recruiter.interview_decision_note || ""}</div>
        </div>

        <div class="report-section">
            <div class="report-section-title">Main Strengths</div>
            ${listHtml(recruiter.main_strengths, "No clear strengths detected yet.")}
        </div>

        <div class="report-section">
            <div class="report-section-title">Main Concerns</div>
            ${listHtml(recruiter.main_concerns, "No major concerns detected yet.")}
        </div>

        <div class="report-section">
            <div class="report-section-title">Recommended Follow-up Areas</div>
            ${listHtml(recruiter.recommended_follow_up_areas, "No follow-up areas available.")}
        </div>

        <div class="report-section">
            <div class="report-section-title">Skill Coverage Map</div>
            <div class="report-grid">
                ${skillHtml}
            </div>
        </div>

        <div class="report-section">
            <div class="report-section-title">Adaptive Questioning Trace</div>
            ${traceHtml}
        </div>

        <details class="report-section">
            <summary class="report-section-title">Full JSON Debug Report</summary>
            <div class="report-json">${JSON.stringify(report, null, 2)}</div>
        </details>
    `;
}

// Fetch latest report after interview ends
async function fetchLatestReport() {
    if (!reportPanel) return;

    reportPanel.innerHTML = `<div class="log-entry info">Loading final report...</div>`;

    try {
        const res = await fetch(REPORT_URL, { cache: "no-store" });
        const data = await res.json();

        if (!res.ok) {
            reportPanel.innerHTML = `<div class="log-entry error">Report not ready: ${data.error || "Unknown error"}</div>`;
            log(`Report fetch failed: ${data.error || "Unknown error"}`, "error");
            return;
        }

        renderReport(data);
        log("Final interview report loaded in UI.", "success");
    } catch (err) {
        reportPanel.innerHTML = `<div class="log-entry error">Could not fetch report. Is the report HTTP server running?</div>`;
        log(`Could not fetch report: ${err.message}`, "error");
    }
}

// Conclude bot session
function disconnectSession() {
    setUIState(false);
    
    log("Disconnecting and cleaning up audio components...", "info");
    
    if (ws) {
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
            try {
                ws.send(JSON.stringify({ type: "end" }));
                ws.close();
            } catch(e) {}
        }
        ws = null;
    }

    if (scriptProcessor) {
        try {
            scriptProcessor.disconnect();
        } catch(e) {}
        scriptProcessor = null;
    }

    if (micSource) {
        try {
            micSource.disconnect();
        } catch(e) {}
        micSource = null;
    }

    if (micStream) {
        try {
            micStream.getTracks().forEach(track => track.stop());
        } catch(e) {}
        micStream = null;
    }

    if (audioContext) {
        try {
            audioContext.close();
        } catch(e) {}
        audioContext = null;
    }

    nextBotAudioTime = 0;
    botAudioQueueDepth = 0;
    isBotAudioPlaying = false;
    botChunksReceived = 0;
    if (botAudioCooldownTimeout) {
        clearTimeout(botAudioCooldownTimeout);
        botAudioCooldownTimeout = null;
    }
    // Reset barge-in state
    bargeInConsecutiveFrames = 0;
    botSpeechStartedAt = 0;
    bargeInMicAllowUntil = 0;
    bargeInDiscardBotAudioUntil = 0;
    bargeInTriggered = false;
    activeBotSources.clear();
    log("Session concluded. Local ports released.", "success");

    // Give the server a moment to generate/save the final report, then fetch it.
    setTimeout(fetchLatestReport, 1500);
}

// Event Bindings
btnConnect.addEventListener("click", startSession);
btnDisconnect.addEventListener("click", disconnectSession);
