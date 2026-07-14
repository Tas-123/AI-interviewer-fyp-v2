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
    } = config;
    const onSessionEnded = typeof hooks.onSessionEnded === "function"
        ? hooks.onSessionEnded
        : null;

    let audioContext = null;
    let micStream = null;
    let micSource = null;
    let scriptProcessor = null;
    let ws = null;
    let isConnected = false;
    let botChunksReceived = 0;
    let sessionEndNotified = false;

    const bargeInCtrl = createBargeInController(bargeIn, {
        onUserSpeaking: (speaking) => ui.status.setUserSpeaking(speaking),
    });

    let playback = null;

    function getStartPayload() {
        const displayName = ui.refs.inputName?.value?.trim() || "";
        const resumeText = ui.refs.inputResume?.value?.trim() || "";
        const payload = { type: "start", target_role: "junior_ai_engineer" };
        if (displayName) payload.display_name = displayName;
        if (resumeText) payload.resume_text = resumeText;
        return payload;
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
            let allowMic = true;

            if (suppressMicWhileBotSpeaking && playback?.isPlaying()) {
                ui.visualizer.updateFromRms(rms);
                const result = bargeInCtrl.processFrameWhileBotSpeaking(rms);
                if (result.bargeInEvent) {
                    ui.debug.log(
                        `CLIENT_BARGE_IN_DETECTED: RMS=${rms.toFixed(4)}`,
                        "info"
                    );
                    playback.stopAll("user_barge_in");
                    ws.send(JSON.stringify({ type: "interrupt", reason: "user_barge_in" }));
                }
                allowMic = result.allowMic;
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
            if (msg.type === "text") {
                ui.conversation.addBotMessage(msg.text);
                ui.debug.log(`Bot says: "${msg.text}"`, "server");
            } else if (msg.type === "transcript" || msg.type === "user_text") {
                const text = msg.text || msg.transcript || "";
                if (text) ui.conversation.addUserMessage(text);
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

    async function connect() {
        ui.debug.log("Initializing AudioContext…", "info");
        bargeInCtrl.reset();
        botChunksReceived = 0;
        sessionEndNotified = false;

        audioContext = new (window.AudioContext || window.webkitAudioContext)({
            sampleRate: 16000,
        });
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

        ui.status.setConnection(false, true);
        ui.debug.log(`Connecting to ${wsUrl}…`, "info");

        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            isConnected = true;
            ui.status.setConnection(true);
            ui.status.setPhase("live");
            ui.debug.log("WebSocket connection established.", "success");
            ui.debug.log("Sending startup handshake…", "info");
            ws.send(JSON.stringify(getStartPayload()));
            attachMicPipeline();
            ui.debug.log("Microphone stream is live.", "success");
        };

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
    }

    function disconnect() {
        isConnected = false;
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
                onSessionEnded();
            } catch (err) {
                ui.debug.log(`onSessionEnded failed: ${err.message || err}`, "error");
            }
        }
    }

    return { connect, disconnect, isConnected: () => isConnected };
}
