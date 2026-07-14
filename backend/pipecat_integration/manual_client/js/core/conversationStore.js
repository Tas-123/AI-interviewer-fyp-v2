/**
 * Apply versioned conversation_event messages to the chat UI.
 * Append-only by message_id so interim→final updates can land later without
 * rewiring the voice pipeline.
 */
export function createConversationStore(conversationView, hooks = {}) {
    const byMessageId = new Map();
    const onPhase = typeof hooks.onPhase === "function" ? hooks.onPhase : null;
    const onSession = typeof hooks.onSession === "function" ? hooks.onSession : null;

    function reset() {
        byMessageId.clear();
    }

    function applyMessage(event) {
        const messageId = event.message_id || event.event_id;
        if (!messageId || !event.text) return;

        const existing = byMessageId.get(messageId);
        if (existing && existing.status === "final") {
            return;
        }

        const time = event.ts ? new Date(event.ts) : new Date();
        const payload = {
            text: event.text,
            time,
            messageId,
            turnId: event.turn_id || "",
            status: event.status || "final",
        };

        if (existing && existing.status === "interim" && event.status === "final") {
            conversationView.updateMessage(messageId, payload);
            byMessageId.set(messageId, event);
            return;
        }

        if (existing) {
            return;
        }

        byMessageId.set(messageId, event);
        const role = event.role || "system";
        if (role === "assistant") {
            conversationView.addBotMessage(event.text, payload);
        } else if (role === "user") {
            conversationView.addUserMessage(event.text, payload);
        } else {
            conversationView.addSystemMessage(event.text, payload);
        }
    }

    function applyEvent(event) {
        if (!event || event.type !== "conversation_event") return;

        if (event.kind === "message") {
            applyMessage(event);
            return;
        }
        if (event.kind === "phase" && onPhase) {
            onPhase(event.phase, event);
            return;
        }
        if (event.kind === "session" && onSession) {
            onSession(event.action, event);
        }
    }

    return {
        applyEvent,
        reset,
    };
}
