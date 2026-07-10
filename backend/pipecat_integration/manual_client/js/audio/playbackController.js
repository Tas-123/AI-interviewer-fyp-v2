export function createPlaybackController(audioContext, config, hooks) {
    const jitterBufferSec = config.botAudioJitterBufferSec ?? 0.15;
    let nextStartTime = 0;
    let queueDepth = 0;
    let isPlaying = false;
    let cooldownTimeout = null;
    const activeSources = new Set();

    function reset() {
        stopAll("session_reset");
        nextStartTime = 0;
        queueDepth = 0;
        isPlaying = false;
        if (cooldownTimeout) {
            clearTimeout(cooldownTimeout);
            cooldownTimeout = null;
        }
    }

    function stopAll(reason) {
        activeSources.forEach((src) => {
            try {
                src.stop();
            } catch {
                // already stopped
            }
        });
        activeSources.clear();
        nextStartTime = 0;
        queueDepth = 0;
        isPlaying = false;
        if (cooldownTimeout) {
            clearTimeout(cooldownTimeout);
            cooldownTimeout = null;
        }
        hooks.onPlaybackStopped?.(reason);
    }

    function scheduleBuffer(audioBuffer) {
        if (!audioContext || audioContext.state === "closed") return;

        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);

        const currentTime = audioContext.currentTime;
        const startAt = Math.max(currentTime + jitterBufferSec, nextStartTime);
        source.start(startAt);
        nextStartTime = startAt + audioBuffer.duration;

        const wasEmpty = queueDepth === 0;
        queueDepth += 1;
        isPlaying = true;
        activeSources.add(source);
        hooks.onPlaybackStarted?.(wasEmpty);

        if (cooldownTimeout) {
            clearTimeout(cooldownTimeout);
            cooldownTimeout = null;
        }

        source.onended = () => {
            activeSources.delete(source);
            queueDepth -= 1;
            if (queueDepth <= 0) {
                queueDepth = 0;
                if (!cooldownTimeout) {
                    cooldownTimeout = setTimeout(() => {
                        isPlaying = false;
                        cooldownTimeout = null;
                        hooks.onPlaybackIdle?.();
                    }, 300);
                }
            }
        };
    }

    return {
        reset,
        stopAll,
        scheduleBuffer,
        isPlaying: () => isPlaying,
    };
}
