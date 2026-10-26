/**
 * AIO Analytics Builder — Chat bot widget
 */

let chatOpen = false;
let chatHistory = [];
let chatStreaming = false;

function toggleChat() {
    chatOpen = !chatOpen;
    document.getElementById('chat-panel').classList.toggle('hidden', !chatOpen);
    document.getElementById('chat-fab-icon').classList.toggle('hidden', chatOpen);
    document.getElementById('chat-fab-close').classList.toggle('hidden', !chatOpen);
    document.getElementById('chat-fab-wrapper').classList.toggle('chat-open', chatOpen);

    if (chatOpen) {
        document.getElementById('chat-input').focus();
    }
}

async function initChatFab() {
    // Show the sidebar chat button if an API key (or Bedrock gateway) is configured
    try {
        const r = await fetch('/api/chat/status');
        const j = await r.json();
        if (j.available) {
            const sidebarBtn = document.getElementById('sidebar-chat-btn');
            if (sidebarBtn) sidebarBtn.classList.remove('hidden');
        }
    } catch (e) {
        // Button stays hidden if status check fails
    }
}

function chatKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChat();
    }
}

async function sendChat() {
    if (chatStreaming) return;

    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';
    autoResizeInput();

    appendMessage('user', text);
    chatHistory.push({role: 'user', content: text});

    chatStreaming = true;
    document.getElementById('chat-send-btn').disabled = true;

    const botBubble = appendMessage('bot', '');
    const textEl = botBubble.querySelector('.chat-bubble');
    textEl.innerHTML = '<span class="chat-typing">Thinking...</span>';

    try {
        // Build page context so the assistant knows where the user is
        const pageContext = {
            page: document.title,
            url: window.location.pathname,
            activeNav: document.querySelector('.nav-links .active')?.textContent?.trim() || '',
        };

        const r = await fetch('/api/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({messages: chatHistory, page_context: pageContext}),
        });

        if (!r.ok) {
            const err = await r.json();
            textEl.textContent = err.error || 'Something went wrong.';
            chatStreaming = false;
            document.getElementById('chat-send-btn').disabled = false;
            return;
        }

        const reader = r.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';
        let buffer = '';
        textEl.textContent = '';

        while (true) {
            const {done, value} = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, {stream: true});
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                try {
                    const msg = JSON.parse(line.slice(6));
                    if (msg.type === 'text') {
                        fullText += msg.text;
                        textEl.innerHTML = renderMarkdown(fullText);
                        scrollChat();
                    } else if (msg.type === 'error') {
                        textEl.textContent = fullText + '\n\n' + msg.text;
                    }
                } catch (e) {
                    // skip malformed
                }
            }
        }

        if (fullText) {
            chatHistory.push({role: 'assistant', content: fullText});
        }
    } catch (e) {
        textEl.textContent = 'Connection error: ' + e.message;
    }

    chatStreaming = false;
    document.getElementById('chat-send-btn').disabled = false;
}

function appendMessage(role, text) {
    const container = document.getElementById('chat-messages');
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-msg chat-msg-' + role;

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    if (text) bubble.innerHTML = role === 'bot' ? renderMarkdown(text) : escapeHtml(text);

    wrapper.appendChild(bubble);
    container.appendChild(wrapper);
    scrollChat();
    return wrapper;
}

function scrollChat() {
    const el = document.getElementById('chat-messages');
    el.scrollTop = el.scrollHeight;
}

function renderMarkdown(text) {
    // Minimal markdown: bold, code, inline code, paragraphs
    let html = escapeHtml(text);
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');
    return '<p>' + html + '</p>';
}

function escapeHtml(text) {
    const el = document.createElement('div');
    el.textContent = text;
    return el.innerHTML;
}

function autoResizeInput() {
    const el = document.getElementById('chat-input');
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 100) + 'px';
}

document.addEventListener('DOMContentLoaded', () => {
    const input = document.getElementById('chat-input');
    if (input) input.addEventListener('input', autoResizeInput);
    initChatFab();
});
