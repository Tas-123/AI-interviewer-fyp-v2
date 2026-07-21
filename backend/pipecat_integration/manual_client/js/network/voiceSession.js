import { createBargeInController } from "../audio/bargeInController.js";
import { createPlaybackController } from "../audio/playbackController.js";

function computeRms(channel) {
    let sum = 0;
    let isSilent = true;
    for (let i = 0; i < channel.length; i += 1) {
        sum += channel[i] * channel[i];
        if (channel[i] !== 0) isSilent = false;
    }
    return {
        rms: Math.sqrt(sum / channel.length),
        isSilent,
    };
}

function floatToPcm16(channel, gain) {
    const pcm = new Int16Array(channel.length);
    for (let i = 0; i < channel.length; i += 1) {
        let val = Math.floor(channel[i] * 32767 * gain);
        val = Math.max(-32768, Math.min(32767, val));
        pcm[i] = val;
    }
    return pcm;
}

export function createVoiceSession(config, ui, hooks = {}) {
    const {
        wsUrl,
        micGain = 2.5,
        suppressMicWhileBotSpeaking = true,
        bargeIn = {},
        targetRole = "junior_ai_engineer",
    } = config;
    const onSessionEnded = typeof hooks.onSessionEnded === "function"
        ? hooks.onSessionEnded
        : null;
    const onSessionStarted = typeof hooks.onSessionStarted === "function"
        ? hooks.onSessionStarted
        : null;
    const onPreambleLine = typeof hooks.onPreambleLine === "function"
        ? hooks.onPreambleLine
        : null;
    const onInstructionsComplete = typeof hooks.onInstructionsComplete === "function"
        ? hooks.onInstructionsComplete
        : null;

    let audioContext = null;
    let micStream = null;
    let micSource = null;
    let scriptProcessor = null;
    let ws = null;
    let isConnected = false;
    let botChunksReceived = 0;
    let sessionEndNotified = false;
    let activeSessionId = "";
    let preambleMode = false;
    let micUploadEnabled = true;

    const bargeInCtrl = createBargeInController(bargeIn, {
        onUserSpeaking: (speaking) => ui.status.setUserSpeaking(speaking),
    });

    let playback = null;

    function getStartPayload() {
        const displayName = ui.refs.inputName?.value?.trim() || "";
        const resumeText = ui.refs.inputResume?.value?.trim() || "";
        const role =
            (typeof targetRole === "string" && targetRole.trim()) ||
            "junior_ai_engineer";
        const payload = { type: "start", target_role: role };
        if (displayName) payload.display_name = displayName;
        if (resumeText) payload.resume_text = resumeText;
        const skills = Array.isArray(ui.refs?._selectedSkills)
            ? ui.refs._selectedSkills
            : [];
        if (skills.length) payload.skills = skills;
        return payload;
    }

    function sendJson(payload) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            throw new Error("WebSocket is not connected.");
        }
        ws.send(JSON.stringify(payload));
    }

    function attachMicPipeline() {
        micSource = audioContext.createMediaStreamSource(micStream);
        scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

        let chunksSent = 0;
        let bytesSent = 0;
        let nonSilentChunks = 0;
        let lastLogTime = Date.now();

        scriptProcessor.onaudioprocess = (event) => {
            if (!isConnected || !ws || ws.readyState !== WebSocket.OPEN) return;

            const channel = event.inputBuffer.getChannelData(0);
            const { rms, isSilent } = computeRms(channel);
            let allowMic = micUploadEnabled;

            if (suppressMicWhileBotSpeaking && playback?.isPlaying()) {
                ui.visualizer.updateFromRms(rms);
                if (preambleMode) {
                    // No barge-in during pre-interview instructions.
                    allowMic = false;
                } else {
                    const result = bargeInCtrl.processFrameWhileBotSpeaking(rms);
                    if (result.bargeInEvent) {
                        ui.debug.log(
                            `CLIENT_BARGE_IN_DETECTED: RMS=${rms.toFixed(4)}`,
                            "info"
                        );
                        playback.stopAll("user_barge_in");
                        ws.send(JSON.stringify({ type: "interrupt", reason: "user_barge_in" }));
                    }
                    allowMic = result.allowMic && micUploadEnabled;
                }
            } else {
                ui.visualizer.updateFromRms(rms);
                ui.status.setUserSpeaking(false);
            }

            if (!allowMic) return;

            const pcm = floatToPcm16(channel, micGain);
            ws.send(pcm.buffer);

            chunksSent += 1;
            bytesSent += pcm.byteLength;
            if (!isSilent) nonSilentChunks += 1;

            const now = Date.now();
            if (now - lastLogTime >= 1000) {
                ui.debug.log(
                    `Audio stream: ${chunksSent} chunks (${bytesSent} bytes), ` +
                        `non-silent ${nonSilentChunks}/${chunksSent}, RMS=${rms.toFixed(4)}`,
                    "info"
                );
                chunksSent = 0;
                bytesSent = 0;
                nonSilentChunks = 0;
                lastLogTime = now;
            }
        };

        micSource.connect(scriptProcessor);
        const silentGain = audioContext.createGain();
        silentGain.gain.value = 0;
        scriptProcessor.connect(silentGain);
        silentGain.connect(audioContext.destination);
    }

    async function handleBinaryMessage(arrayBuffer) {
        if (bargeInCtrl.shouldDiscardBotAudio()) {
            botChunksReceived += 1;
            if (botChunksReceived % 10 === 0) {
                ui.debug.log("Discarding stale bot audio after barge-in.", "info");
            }
            return;
        }

        botChunksReceived += 1;
        const shouldLog = botChunksReceived === 1 || botChunksReceived % 20 === 0;
        if (shouldLog) {
            ui.debug.log(
                `Received bot audio chunk #${botChunksReceived}: ${arrayBuffer.byteLength} bytes`,
                "server"
            );
        }

        try {
            const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
            playback.scheduleBuffer(audioBuffer);
            if (shouldLog) {
                ui.debug.log("Bot audio playback scheduled.", "success");
            }
        } catch (err) {
            ui.debug.log(`Bot audio decode/playback error: ${err.message || err}`, "error");
        }
    }

    function handleTextMessage(raw) {
        try {
            const msg = JSON.parse(raw);
            if (msg.type === "conversation_event") {
                if (msg.session_id && !activeSessionId) {
                    activeSessionId = msg.session_id;
                }

                if (preambleMode) {
                    if (msg.kind === "message" && msg.role === "assistant" && msg.text) {
                        if (onPreambleLine) onPreambleLine(msg.text);
                        ui.debug.log(`Instructions: "${msg.text}"`, "server");
                        return;
                    }
                    if (msg.kind === "session" && msg.action === "instructions_complete") {
                        if (onInstructionsComplete) onInstructionsComplete();
                        ui.debug.log("Pre-interview instructions complete.", "success");
                        return;
                    }
                    // Ignore other preamble-phase events for the live chat panel.
                    return;
                }

                if (ui.conversationStore) {
                    ui.conversationStore.applyEvent(msg);
                }
                if (msg.kind === "session" && msg.action === "started" && msg.session_id) {
                    activeSessionId = msg.session_id;
                    if (onSessionStarted) {
                        onSessionStarted(msg.session_id);
                    }
                }
                if (msg.kind === "message" && msg.text) {
                    const who =
                        msg.role === "user"
                            ? "You"
                            : msg.role === "assistant"
                              ? "Interviewer"
                              : "System";
                    ui.debug.log(`${who}: "${msg.text}"`, "server");
                } else if (msg.kind === "phase") {
                    ui.debug.log(`Phase: ${msg.phase}`, "info");
                }
            } else if (msg.type === "text") {
                if (!preambleMode) {
                    ui.conversation.addBotMessage(msg.text);
                }
                ui.debug.log(`Bot says: "${msg.text}"`, "server");
            } else if (msg.type === "transcript" || msg.type === "user_text") {
                const text = msg.text || msg.transcript || "";
                if (text && !preambleMode) ui.conversation.addUserMessage(text);
            } else if (msg.type === "end") {
                ui.debug.log("Session wrap-up signal received from server.", "info");
                disconnect();
            } else {
                ui.debug.log(`Control message: ${raw}`, "info");
            }
        } catch {
            ui.debug.log(`Raw text message: ${raw}`, "info");
        }
    }

    function waitForOpen(socket, timeoutMs = 15000) {
        return new Promise((resolve, reject) => {
            if (socket.readyState === WebSocket.OPEN) {
                resolve();
                return;
            }
            const timer = setTimeout(() => {
                reject(new Error("WebSocket connect timed out."));
            }, timeoutMs);
            socket.addEventListener("open", () => {
                clearTimeout(timer);
                resolve();
            }, { once: true });
            socket.addEventListener("error", () => {
                clearTimeout(timer);
                reject(new Error("WebSocket connection error."));
            }, { once: true });
        });
    }

    /**
     * Open WebSocket (+ optional mic) without starting the interview.
     * @param {{ preamble?: boolean, enableMicUpload?: boolean, needMic?: boolean }} options
     */
    async function connect(options = {}) {
        const forPreamble = options.preamble === true;
        const needMic = options.needMic !== false && !forPreamble;
        const enableMic = options.enableMicUpload !== false && needMic;

        ui.debug.log("Initializing AudioContext…", "info");
        bargeInCtrl.reset();
        botChunksReceived = 0;
        sessionEndNotified = false;
        activeSessionId = "";
        preambleMode = forPreamble;
        micUploadEnabled = enableMic;

        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000,
        });
        try {
            await audioContext.resume();
        } catch {
            // ignore — some browsers resume on first audio
        }
        playback = createPlaybackController(audioContext, config, {
            onPlaybackStarted: (wasEmpty) => {
                ui.status.setBotSpeaking(true);
                if (wasEmpty) bargeInCtrl.onBotSpeechStart();
            },
            onPlaybackIdle: () => ui.status.setBotSpeaking(false),
            onPlaybackStopped: () => ui.status.setBotSpeaking(false),
        });
        playback.reset();

        ui.debug.log(`AudioContext sample rate: ${audioContext.sampleRate} Hz`, "info");

        if (needMic) {
            ui.debug.log("Requesting microphone permissions…", "info");
            micStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true,
                },
            });
            ui.debug.log("Microphone access granted.", "success");
        } else {
            ui.debug.log("Skipping microphone for pre-interview instructions.", "info");
        }

        ui.status.setConnection(false, true);
        ui.debug.log(`Connecting to ${wsUrl}…`, "info");

        ws = new WebSocket(wsUrl);

        ws.onmessage = async (event) => {
            if (event.data instanceof Blob) {
                const arrayBuffer = await event.data.arrayBuffer();
                await handleBinaryMessage(arrayBuffer);
                return;
            }
            handleTextMessage(event.data);
        };

        ws.onerror = () => {
            ui.debug.log("WebSocket connection error.", "error");
        };

        ws.onclose = () => {
            ui.debug.log("WebSocket connection closed.", "info");
            disconnect();
        };

        await waitForOpen(ws);
        isConnected = true;
        ui.status.setConnection(true);
        ui.status.setPhase(forPreamble ? "setup" : "live");
        ui.debug.log("WebSocket connection established.", "success");
        if (micStream) {
            attachMicPipeline();
            ui.debug.log(
                forPreamble
                    ? "Connected for instructions (mic muted until Ready)."
                    : "Microphone stream is live.",
                "success"
            );
        } else {
            ui.debug.log("Connected for instructions (no mic yet).", "success");
        }
    }

    /** Request mic after preamble, before live interview. */
    async function ensureMicrophone() {
        if (micStream) {
            micUploadEnabled = true;
            if (!scriptProcessor) attachMicPipeline();
            return;
        }
        if (!audioContext) {
            throw new Error("Audio is not initialized. Start the interview from the welcome screen.");
        }
        ui.debug.log("Requesting microphone permissions…", "info");
        micStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                sampleRate: 16000,
                echoCancellation: true,
                noiseSuppression: true,
            },
        });
        ui.debug.log("Microphone access granted.", "success");
        micUploadEnabled = true;
        attachMicPipeline();
    }

    /** Connect and immediately start the interview (lab Connect button). */
    async function connectAndStart() {
        await connect({ preamble: false, enableMicUpload: true, needMic: true });
        sendStart();
    }

    function sendInstructions() {
        preambleMode = true;
        micUploadEnabled = false;
        ui.debug.log("Requesting Cartesia instruction preamble…", "info");
        sendJson({ type: "instructions" });
    }

    function sendStart() {
        preambleMode = false;
        micUploadEnabled = true;
        ui.status.setPhase("live");
        ui.debug.log("Sending interview start handshake…", "info");
        sendJson(getStartPayload());
    }

    function disconnect() {
        isConnected = false;
        preambleMode = false;
        micUploadEnabled = true;
        ui.status.setConnection(false);
        ui.status.setPhase("ended");
        ui.status.setBotSpeaking(false);
        ui.status.setUserSpeaking(false);
        ui.visualizer.reset();
        ui.debug.log("Disconnecting and cleaning up audio…", "info");

        if (ws) {
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                try {
                    ws.close();
                } catch {
                    // ignore
                }
            }
            ws = null;
        }

        if (scriptProcessor) {
            try {
                scriptProcessor.disconnect();
            } catch {
                // ignore
            }
            scriptProcessor = null;
        }

        if (micSource) {
            try {
                micSource.disconnect();
            } catch {
                // ignore
            }
            micSource = null;
        }

        if (micStream) {
            micStream.getTracks().forEach((track) => track.stop());
            micStream = null;
        }

        if (playback) {
            playback.reset();
            playback = null;
        }

        if (audioContext) {
            try {
                audioContext.close();
            } catch {
                // ignore
            }
            audioContext = null;
        }

        bargeInCtrl.reset();
        botChunksReceived = 0;
        ui.debug.log("Session concluded.", "success");

        if (onSessionEnded && !sessionEndNotified) {
            sessionEndNotified = true;
            try {
                onSessionEnded(activeSessionId);
            } catch (err) {
                ui.debug.log(`onSessionEnded failed: ${err.message || err}`, "error");
            }
        }
    }

    return {
        connect,
        connectAndStart,
        ensureMicrophone,
        sendInstructions,
        sendStart,
        disconnect,
        isConnected: () => isConnected,
        getSessionId: () => activeSessionId,
    };
}
