export function createConversationView(refs) {
    const panel = refs.conversationPanel;
    let emptyNode = null;

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
        emptyNode = document.createElement("div");
        emptyNode.className = "conversation-empty";
        emptyNode.textContent = message;
        panel.appendChild(emptyNode);
    }

    function addMessage({ role, text, time = new Date() }) {
        if (!ensurePanel()) return;

        const wrapper = document.createElement("article");
        wrapper.className = `message ${role}`;

        const meta = document.createElement("div");
        meta.className = "message-meta";
        const roleLabel = role === "bot" ? "Interviewer" : role === "user" ? "You" : "System";
        meta.textContent = `${roleLabel} · ${time.toLocaleTimeString()}`;

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.textContent = text;

        wrapper.append(meta, bubble);
        panel.appendChild(wrapper);
        panel.scrollTop = panel.scrollHeight;
    }

    function addBotMessage(text) {
        addMessage({ role: "bot", text });
    }

    function addUserMessage(text) {
        addMessage({ role: "user", text });
    }

    function addSystemMessage(text) {
        addMessage({ role: "system", text });
    }

    return {
        showEmpty,
        addBotMessage,
        addUserMessage,
        addSystemMessage,
    };
}
