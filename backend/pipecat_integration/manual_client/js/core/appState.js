/** Shared session flags used across audio + network layers. */
export function createAppState() {
    return {
        isConnected: false,
        phase: "setup", // setup | live | ended
        botSpeaking: false,
        userSpeaking: false,
    };
}

export const SESSION_PHASES = {
    SETUP: "setup",
    LIVE: "live",
    ENDED: "ended",
};
