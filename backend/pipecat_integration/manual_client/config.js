/**
 * Manual client configuration — URLs and barge-in thresholds.
 * Override via query string: ?ws=ws://host:8765&report=http://host:8766/latest-report
 */
(function () {
    const params = new URLSearchParams(window.location.search);

    window.MANUAL_CLIENT_CONFIG = {
        wsUrl: params.get("ws") || "ws://localhost:8765",
        reportUrl: params.get("report") || "http://localhost:8766/latest-report",
        bargeIn: {
            rmsThreshold: parseFloat(params.get("barge_rms") || "0.035"),
            minFrames: parseInt(params.get("barge_frames") || "3", 10),
            ignoreAfterBotStartMs: parseInt(params.get("barge_ignore_ms") || "400", 10),
            micAllowMs: parseInt(params.get("barge_mic_ms") || "2500", 10),
            discardBotAudioMs: parseInt(params.get("barge_discard_ms") || "1200", 10),
        },
        botAudioJitterBufferSec: parseFloat(params.get("jitter") || "0.15"),
        suppressMicWhileBotSpeaking: params.get("suppress_mic") !== "0",
    };
})();
