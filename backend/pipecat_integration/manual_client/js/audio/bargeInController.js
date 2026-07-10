export function createBargeInController(config, hooks) {
    const {
        rmsThreshold = 0.055,
        minFrames = 4,
        ignoreAfterBotStartMs = 500,
        micAllowMs = 2500,
        discardBotAudioMs = 900,
    } = config;

    let consecutiveFrames = 0;
    let botSpeechStartedAt = 0;
    let micAllowUntil = 0;
    let discardBotAudioUntil = 0;
    let triggered = false;

    function reset() {
        consecutiveFrames = 0;
        botSpeechStartedAt = 0;
        micAllowUntil = 0;
        discardBotAudioUntil = 0;
        triggered = false;
    }

    function onBotSpeechStart() {
        botSpeechStartedAt = Date.now();
        consecutiveFrames = 0;
        triggered = false;
    }

    function shouldDiscardBotAudio() {
        return Date.now() < discardBotAudioUntil;
    }

    function processFrameWhileBotSpeaking(rms) {
        const now = Date.now();

        if (triggered && now < micAllowUntil) {
            hooks.onUserSpeaking?.(true);
            return { allowMic: true, bargeInEvent: false };
        }

        if (triggered) {
            triggered = false;
            consecutiveFrames = 0;
            hooks.onUserSpeaking?.(false);
            return { allowMic: false, bargeInEvent: false };
        }

        const msSinceBotStart = now - botSpeechStartedAt;
        if (msSinceBotStart < ignoreAfterBotStartMs) {
            consecutiveFrames = 0;
            return { allowMic: false, bargeInEvent: false };
        }

        if (rms > rmsThreshold) {
            consecutiveFrames += 1;
        } else {
            consecutiveFrames = 0;
            return { allowMic: false, bargeInEvent: false };
        }

        if (consecutiveFrames < minFrames) {
            return { allowMic: false, bargeInEvent: false };
        }

        triggered = true;
        micAllowUntil = now + micAllowMs;
        discardBotAudioUntil = now + discardBotAudioMs;
        consecutiveFrames = 0;
        hooks.onUserSpeaking?.(true);
        return { allowMic: true, bargeInEvent: true, rms, frames: minFrames };
    }

    return {
        reset,
        onBotSpeechStart,
        shouldDiscardBotAudio,
        processFrameWhileBotSpeaking,
    };
}
