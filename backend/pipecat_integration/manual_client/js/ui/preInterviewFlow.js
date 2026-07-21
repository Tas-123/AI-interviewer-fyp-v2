/**
 * Pre-interview lobby: welcome → instructions (Cartesia) → Ready → start.
 * Leaves the name screen immediately on Start; never auto-starts the interview.
 */

const CONNECT_HINT = "Connecting to the interviewer…";
const LISTENING_HINT = "Listening to instructions…";
const READY_HINT = "Instructions complete. Click Ready when you want to begin.";
const INSTRUCTIONS_FALLBACK_MS = 90000;

function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

function showPanel(refs, panelKey) {
    const panels = {
        welcome: refs.prePanelWelcome,
        loading: refs.prePanelLoading,
        instructions: refs.prePanelInstructions,
    };
    Object.entries(panels).forEach(([key, el]) => {
        if (!el) return;
        const active = key === panelKey;
        el.hidden = !active;
        el.classList.toggle("is-active", active);
    });
    // Keep overlay visible for all pre-interview phases.
    if (refs.preInterviewOverlay) {
        refs.preInterviewOverlay.hidden = false;
        refs.preInterviewOverlay.removeAttribute("aria-hidden");
    }
    document.body.classList.add("pre-interview-active");
    document.body.dataset.prePhase = panelKey;
}

function syncProfileToShell(refs) {
    if (refs.inputName && refs.preInputName) {
        refs.inputName.value = refs.preInputName.value.trim();
    }
    // Imported sync for skills+notes lives on refs via interviewMeta
    if (typeof refs._syncSkills === "function") {
        refs._syncSkills();
    } else if (refs.inputResume && refs.preInputResume) {
        refs.inputResume.value = refs.preInputResume.value.trim();
    }
}

function validateDisplayName(refs) {
    const name = refs.preInputName?.value?.trim() || "";
    const ok = name.length > 0;
    if (refs.preNameError) refs.preNameError.hidden = ok;
    if (refs.preInputName) {
        refs.preInputName.classList.toggle("is-invalid", !ok);
    }
    return ok;
}

/**
 * @param {object} refs
 * @param {{
 *   onStartInstructions: () => Promise<void>,
 *   onReadyStart: () => Promise<void>,
 *   onLog?: (msg: string, level?: string) => void
 * }} handlers
 */
export function createPreInterviewFlow(refs, handlers) {
    const {
        onStartInstructions,
        onReadyStart,
        onLog = () => {},
    } = handlers;
    let started = false;
    let readyArmed = false;
    let fallbackTimer = null;

    function clearInstructionList() {
        if (refs.preInstructionsList) {
            refs.preInstructionsList.innerHTML = "";
        }
        if (refs.preInstructionsSpoken) {
            refs.preInstructionsSpoken.textContent = "";
        }
    }

    function appendInstructionLine(text, { status = false } = {}) {
        const line = (text || "").trim();
        if (!line || !refs.preInstructionsList) return;
        const li = document.createElement("li");
        li.textContent = line;
        if (status) li.classList.add("pre-status-line");
        refs.preInstructionsList.appendChild(li);
        if (!status && refs.preInstructionsSpoken) {
            const prev = refs.preInstructionsSpoken.textContent.trim();
            refs.preInstructionsSpoken.textContent = prev ? `${prev} ${line}` : line;
        }
        // Scroll newest line into view inside the card.
        li.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function removeStatusLines() {
        if (!refs.preInstructionsList) return;
        refs.preInstructionsList
            .querySelectorAll(".pre-status-line")
            .forEach((el) => el.remove());
    }

    function setReadyEnabled(enabled) {
        if (!refs.btnReady) return;
        refs.btnReady.disabled = !enabled;
        readyArmed = enabled;
        if (refs.preSpeakingHint) {
            refs.preSpeakingHint.textContent = enabled ? READY_HINT : LISTENING_HINT;
        }
        if (enabled && fallbackTimer) {
            clearTimeout(fallbackTimer);
            fallbackTimer = null;
        }
    }

    function hideOverlay() {
        document.body.classList.remove("pre-interview-active");
        delete document.body.dataset.prePhase;
        if (refs.preInterviewOverlay) {
            refs.preInterviewOverlay.hidden = true;
            refs.preInterviewOverlay.setAttribute("aria-hidden", "true");
        }
    }

    function onPreambleLine(text) {
        removeStatusLines();
        appendInstructionLine(text);
    }

    function onInstructionsComplete() {
        removeStatusLines();
        setReadyEnabled(true);
        onLog("Pre-interview: Ready button enabled.", "info");
    }

    async function runInitializeAndInstructions() {
        if (started) return;
        if (!validateDisplayName(refs)) {
            onLog("Display name is required.", "info");
            refs.preInputName?.focus();
            return;
        }
        started = true;

        syncProfileToShell(refs);
        if (refs.btnStartInterview) refs.btnStartInterview.disabled = true;

        // Leave the name screen immediately so the user never stays on welcome.
        clearInstructionList();
        showPanel(refs, "instructions");
        setReadyEnabled(false);
        appendInstructionLine(CONNECT_HINT, { status: true });
        if (refs.preSpeakingHint) {
            refs.preSpeakingHint.textContent = CONNECT_HINT;
        }
        onLog("Pre-interview: showing instructions panel, connecting…", "info");

        try {
            await onStartInstructions();
            if (refs.preSpeakingHint) {
                refs.preSpeakingHint.textContent = LISTENING_HINT;
            }
            fallbackTimer = setTimeout(() => {
                if (!readyArmed) {
                    onLog("Pre-interview: enabling Ready after fallback timeout.", "info");
                    setReadyEnabled(true);
                }
            }, INSTRUCTIONS_FALLBACK_MS);
        } catch (err) {
            onLog(`Pre-interview: instruction connect failed — ${err.message}`, "error");
            removeStatusLines();
            appendInstructionLine(
                `Could not connect (${err.message}). Restart the voice bot, then click Start Interview again.`,
                { status: true }
            );
            started = false;
            if (refs.btnStartInterview) refs.btnStartInterview.disabled = false;
            // Stay on instructions — do NOT bounce back to the name screen.
            showPanel(refs, "instructions");
            setReadyEnabled(false);
        }
    }

    async function runReadyHandoff() {
        if (!readyArmed) return;
        readyArmed = false;
        if (refs.btnReady) refs.btnReady.disabled = true;
        if (fallbackTimer) {
            clearTimeout(fallbackTimer);
            fallbackTimer = null;
        }

        syncProfileToShell(refs);
        showPanel(refs, "loading");
        if (refs.preLoadingMessage) {
            refs.preLoadingMessage.textContent = "Starting interview…";
        }
        onLog("Pre-interview: Ready clicked — starting interview…", "info");
        await delay(1200);

        try {
            await onReadyStart();
            hideOverlay();
            onLog("Pre-interview: handed off to live interview.", "success");
        } catch (err) {
            onLog(`Pre-interview: start failed — ${err.message}`, "error");
            showPanel(refs, "instructions");
            setReadyEnabled(true);
            started = true;
        }
    }

    function wire() {
        clearInstructionList();
        showPanel(refs, "welcome");
        setReadyEnabled(false);

        refs.btnStartInterview?.addEventListener("click", () => {
            runInitializeAndInstructions().catch((err) => {
                onLog(`Pre-interview init failed: ${err.message}`, "error");
                showPanel(refs, "instructions");
                started = false;
                if (refs.btnStartInterview) refs.btnStartInterview.disabled = false;
            });
        });

        refs.btnReady?.addEventListener("click", () => {
            runReadyHandoff().catch((err) => {
                onLog(`Pre-interview ready failed: ${err.message}`, "error");
            });
        });
    }

    return {
        wire,
        hideOverlay,
        syncProfileToShell,
        onPreambleLine,
        onInstructionsComplete,
    };
}
