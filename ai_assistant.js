/* =========================================
   CareerAI Gemini Assistant
========================================= */

document.addEventListener("DOMContentLoaded", function () {
    const launcher = document.getElementById("careerai-chat-launcher");
    const chatWindow = document.getElementById("careerai-chat-window");
    const closeButton = document.getElementById("careerai-chat-close");
    const clearButton = document.getElementById("careerai-chat-clear");

    const messagesContainer = document.getElementById(
        "careerai-chat-messages"
    );

    const chatForm = document.getElementById("careerai-chat-form");
    const chatInput = document.getElementById("careerai-chat-input");
    const sendButton = document.getElementById("careerai-chat-send");

    if (
        !launcher ||
        !chatWindow ||
        !messagesContainer ||
        !chatForm ||
        !chatInput ||
        !sendButton
    ) {
        return;
    }

    let conversationHistory = [];
    let isSending = false;

    const welcomeMessage = `
        Hi! I'm your CareerAI Assistant. 👋

        <br><br>

        I can help you improve your resume, prepare for interviews,
        explore career options, and plan your next steps.

        <br><br>

        What would you like help with?
    `;

    // -----------------------------------------
    // Open and close chat
    // -----------------------------------------

    function openChat() {
        chatWindow.classList.add("open");
        chatWindow.setAttribute("aria-hidden", "false");

        launcher.setAttribute("aria-expanded", "true");

        chatInput.focus();
    }

    function closeChat() {
        chatWindow.classList.remove("open");
        chatWindow.setAttribute("aria-hidden", "true");

        launcher.setAttribute("aria-expanded", "false");
    }

    launcher.addEventListener("click", function () {
        if (chatWindow.classList.contains("open")) {
            closeChat();
        } else {
            openChat();
        }
    });

    closeButton.addEventListener("click", closeChat);

    // -----------------------------------------
    // Add message to chat
    // -----------------------------------------

    function addMessage(message, sender, allowHTML = false) {
        const messageRow = document.createElement("div");

        messageRow.className = `careerai-message ${sender}`;

        const avatar = document.createElement("div");

        avatar.className = "careerai-message-avatar";
        avatar.textContent = sender === "assistant" ? "✦" : "";

        const content = document.createElement("div");

        content.className = "careerai-message-content";

        const bubble = document.createElement("div");

        bubble.className = "careerai-message-bubble";

        if (allowHTML) {
            bubble.innerHTML = message;
        } else {
            // textContent prevents HTML/script injection.
            bubble.textContent = message;
        }

        content.appendChild(bubble);

        messageRow.appendChild(avatar);
        messageRow.appendChild(content);

        messagesContainer.appendChild(messageRow);

        messagesContainer.scrollTop = messagesContainer.scrollHeight;

        return messageRow;
    }

    // -----------------------------------------
    // Typing indicator
    // -----------------------------------------

    function showTypingIndicator() {
        const typingRow = document.createElement("div");

        typingRow.className = "careerai-message assistant";
        typingRow.id = "careerai-typing-indicator";

        typingRow.innerHTML = `
            <div class="careerai-message-avatar">✦</div>

            <div class="careerai-message-content">
                <div class="careerai-message-bubble">
                    <div class="careerai-typing">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            </div>
        `;

        messagesContainer.appendChild(typingRow);

        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function removeTypingIndicator() {
        const typingIndicator = document.getElementById(
            "careerai-typing-indicator"
        );

        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    // -----------------------------------------
    // Send message to Flask/Gemini
    // -----------------------------------------

    async function sendMessage(message) {
        message = message.trim();

        if (!message || isSending) {
            return;
        }

        isSending = true;

        sendButton.disabled = true;
        chatInput.disabled = true;

        addMessage(message, "user");

        chatInput.value = "";
        chatInput.style.height = "42px";

        showTypingIndicator();

        try {
            const response = await fetch("/api/ai-assistant", {
                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    message: message,
                    history: conversationHistory
                })
            });

            const data = await response.json();

            removeTypingIndicator();

            if (!response.ok) {
                throw new Error(
                    data.error || "Something went wrong."
                );
            }

            const reply = data.reply || "I couldn't generate a response.";

            addMessage(reply, "assistant");

            // Add the exchange to the short conversation history.
            conversationHistory.push({
                role: "user",
                content: message
            });

            conversationHistory.push({
                role: "model",
                content: reply
            });

            // Keep only the most recent 10 messages.
            conversationHistory = conversationHistory.slice(-10);

        } catch (error) {
            removeTypingIndicator();

            addMessage(
                error.message ||
                "Unable to connect to the AI assistant. Please try again.",
                "assistant"
            );

        } finally {
            isSending = false;

            sendButton.disabled = false;
            chatInput.disabled = false;

            chatInput.focus();
        }
    }

    // -----------------------------------------
    // Submit message
    // -----------------------------------------

    chatForm.addEventListener("submit", function (event) {
        event.preventDefault();

        sendMessage(chatInput.value);
    });

    // -----------------------------------------
    // Enter to send, Shift + Enter for new line
    // -----------------------------------------

    chatInput.addEventListener("keydown", function (event) {
        if (
            event.key === "Enter" &&
            !event.shiftKey
        ) {
            event.preventDefault();

            chatForm.requestSubmit();
        }
    });

    // -----------------------------------------
    // Auto-resize textarea
    // -----------------------------------------

    chatInput.addEventListener("input", function () {
        chatInput.style.height = "42px";

        chatInput.style.height = Math.min(
            chatInput.scrollHeight,
            100
        ) + "px";
    });

    // -----------------------------------------
    // Suggested prompts
    // -----------------------------------------

    document
        .querySelectorAll(".careerai-suggestion")
        .forEach(function (button) {
            button.addEventListener("click", function () {
                const prompt = button.dataset.prompt;

                if (prompt) {
                    openChat();
                    sendMessage(prompt);
                }
            });
        });

    // -----------------------------------------
    // Clear conversation
    // -----------------------------------------

    clearButton.addEventListener("click", function () {
        conversationHistory = [];

        messagesContainer.innerHTML = "";

        addMessage(welcomeMessage, "assistant", true);

        chatInput.value = "";
        chatInput.style.height = "42px";
    });
});