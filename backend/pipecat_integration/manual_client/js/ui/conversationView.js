export function createConversationView(refs) {
    const panel = refs.conversationPanel;
    let emptyNode = null;
    const nodesById = new Map();

    function ensurePanel() {
        if (!panel) return false;
        if (emptyNode && emptyNode.parentNode === panel) {
            emptyNode.remove();
            emptyNode = null;
        }
        return true;
    }

    function showEmpty(message) {
        if (!panel) return;
        panel.innerHTML = "";
        nodesById.clear();
        emptyNode = document.createElement("div");
        emptyNode.className = "conversation-empty";
        emptyNode.textContent = message;
        panel.appendChild(emptyNode);
    }

    function clear() {
        showEmpty("Waiting for the interview to begin…");
    }

    function addMessage({ role, text, time = new Date(), messageId = "" }) {
        if (!ensurePanel()) return null;

        const wrapper = document.createElement("article");
        wrapper.className = `message ${role}`;
        if (messageId) {
            wrapper.dataset.messageId = messageId;
            nodesById.set(messageId, wrapper);
        }

        const meta = document.createElement("div");
        meta.className = "message-meta";
        const roleLabel =
            role === "bot" ? "Interviewer" : role === "user" ? "You" : "System";
        const when = time instanceof Date ? time : new Date(time);
        meta.textContent = `${roleLabel} · ${when.toLocaleTimeString()}`;

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = text;

        wrapper.append(meta, bubble);
        panel.appendChild(wrapper);
        panel.scrollTop = panel.scrollHeight;
        return wrapper;
    }

    function updateMessage(messageId, { text, time } = {}) {
        const node = nodesById.get(messageId);
        if (!node) return false;
        const bubble = node.querySelector(".message-bubble");
        if (bubble && typeof text === "string") {
            bubble.textContent = text;
        }
        if (time) {
            const meta = node.querySelector(".message-meta");
            if (meta) {
                const roleLabel = node.classList.contains("bot")
                    ? "Interviewer"
                    : node.classList.contains("user")
                      ? "You"
                      : "System";
                const when = time instanceof Date ? time : new Date(time);
                meta.textContent = `${roleLabel} · ${when.toLocaleTimeString()}`;
            }
        }
        panel.scrollTop = panel.scrollHeight;
        return true;
    }

    function addBotMessage(text, opts = {}) {
        return addMessage({
            role: "bot",
            text,
            time: opts.time,
            messageId: opts.messageId,
        });
    }

    function addUserMessage(text, opts = {}) {
        return addMessage({
            role: "user",
            text,
            time: opts.time,
            messageId: opts.messageId,
        });
    }

    function addSystemMessage(text, opts = {}) {
        return addMessage({
            role: "system",
            text,
            time: opts.time,
            messageId: opts.messageId,
        });
    }

    return {
        showEmpty,
        clear,
        addBotMessage,
        addUserMessage,
        addSystemMessage,
        updateMessage,
    };
}
