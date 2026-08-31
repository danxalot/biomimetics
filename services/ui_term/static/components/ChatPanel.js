/**
 * ChatPanel - Genesis/ARCA Chat Interface Component
 * Handles user interaction with the main ARCA agent
 */
class ChatPanel extends BaseComponent {
    constructor(containerId = '#chat-panel') {
        super(containerId);
        this.state = {
            messages: [],
            isProcessing: false,
            sessionId: null
        };

        // Load chat history from localStorage
        this.loadHistory();
    }

    template() {
        return `
            <div class="chat-container">
                <div class="chat-header">
                    <div class="chat-title">ARCA</div>
                    <div class="chat-controls">
                        <button class="btn-secondary" id="pauseChat">Pause</button>
                        <button class="btn-secondary" id="clearChat">Clear</button>
                    </div>
                </div>
                
                <div class="chat-messages" id="chatMessages">
                    ${this.renderMessages()}
                </div>
                
                <div class="chat-input-area">
                    <div class="input-row">
                        <textarea 
                            class="chat-input" 
                            id="chatInput" 
                            placeholder="Enter message or objective..." 
                            rows="2"
                            ${this.state.isProcessing ? 'disabled' : ''}
                        ></textarea>
                        <button class="btn-primary" id="sendBtn" ${this.state.isProcessing ? 'disabled' : ''}>
                            Send
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    renderMessages() {
        return this.state.messages.map(msg => `
            <div class="message ${msg.role}">
                <div class="message-content">${this.escapeHtml(msg.content)}</div>
                <div class="message-time">${msg.timestamp}</div>
            </div>
        `).join('');
    }

    attachEventListeners() {
        // Send button
        const sendBtn = this.container.querySelector('#sendBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        // Enter to send (Shift+Enter for newline)
        const input = this.container.querySelector('#chatInput');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        // Clear button
        const clearBtn = this.container.querySelector('#clearChat');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearHistory());
        }
    }

    sendMessage() {
        const input = this.container.querySelector('#chatInput');
        const message = input.value.trim();

        if (!message || this.state.isProcessing) return;

        // Add user message
        this.addMessage({
            role: 'user',
            content: message,
            timestamp: new Date().toLocaleTimeString()
        });

        // Clear input
        input.value = '';

        // Send via WebSocket
        if (wsManager) {
            wsManager.send({
                type: 'genesis_message',
                content: message,
                session_id: this.state.sessionId
            });
        }

        // Update state
        this.setState({ isProcessing: true });
    }

    addMessage(message) {
        this.state.messages.push(message);
        this.render();
        this.scrollToBottom();
        this.saveHistory();
    }

    handleMessage(data) {
        // Handle incoming WebSocket messages
        if (data.type === 'session_created') {
            this.state.sessionId = data.session_id;
        } else if (data.type === 'genesis_message' || data.type === 'message') {
            this.addMessage({
                role: data.role,
                content: data.content,
                timestamp: new Date().toLocaleTimeString()
            });

            if (data.role === 'assistant') {
                this.setState({ isProcessing: false });
            }
        } else if (data.type === 'status') {
            // Show processing status
            this.addMessage({
                role: 'system',
                content: data.content,
                timestamp: new Date().toLocaleTimeString()
            });
        }
    }

    scrollToBottom() {
        const messagesDiv = this.container.querySelector('#chatMessages');
        if (messagesDiv) {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem('arca_chat_history');
            if (saved) {
                this.state.messages = JSON.parse(saved);
            }
        } catch (e) {
            console.error('Failed to load chat history:', e);
        }
    }

    saveHistory() {
        try {
            localStorage.setItem('arca_chat_history', JSON.stringify(this.state.messages));
        } catch (e) {
            console.error('Failed to save chat history:', e);
        }
    }

    clearHistory() {
        this.state.messages = [];
        this.render();
        this.saveHistory();
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatPanel;
}
