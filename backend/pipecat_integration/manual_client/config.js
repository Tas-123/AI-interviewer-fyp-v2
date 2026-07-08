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
            // Raised defaults (Phase 6) to cut false barge-ins from noise / echo.
            // Override via ?barge_rms= &barge_frames= &barge_ignore_ms=
            rmsThreshold: parseFloat(params.get("barge_rms") || "0.09"),
            minFrames: parseInt(params.get("barge_frames") || "6", 10),
            ignoreAfterBotStartMs: parseInt(params.get("barge_ignore_ms") || "1000", 10),
            micAllowMs: parseInt(params.get("barge_mic_ms") || "2500", 10),
            discardBotAudioMs: parseInt(params.get("barge_discard_ms") || "900", 10),
        },
        botAudioJitterBufferSec: parseFloat(params.get("jitter") || "0.15"),
        suppressMicWhileBotSpeaking: params.get("suppress_mic") !== "0",
        micGain: parseFloat(params.get("mic_gain") || "2.5"),
    };
})();
