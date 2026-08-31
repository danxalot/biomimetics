/**
 * SerenaPanel - Serena Code Agent Interface Component
 * Handles interaction with Serena self-healing agent
 * FIXED: Auto-scroll to latest message
 */
class SerenaPanel extends BaseComponent {
    constructor(containerId = '#serena-panel') {
        super(containerId);
        this.state = {
            messages: [],
            isProcessing: false,
            sessionId: null,
            skills: []
        };

        this.loadHistory();
    }

    template() {
        return `
            <div class="serena-container">
                <div class="chat-header">
                    <div class="chat-title">
                        🔮 Serena Code Agent
                        <span class="version">v3.3 - Fixes Active</span>
                    </div>
                    <div class="chat-controls">
                        <button class="btn-secondary" id="serenaSkills">Skills</button>
                        <button class="btn-secondary" id="serenaClear">Clear</button>
                        <button class="btn-secondary" id="serenaReset">Reset</button>
                    </div>
                </div>
                
                <div class="chat-messages" id="serenaMessages">
                    ${this.renderMessages()}
                </div>
                
                <div class="chat-input-area">
                    <div class="input-row">
                        <textarea 
                            class="chat-input" 
                            id="serenaInput" 
                            placeholder="Ask Serena about code, skills, or dispatch repair jobs..." 
                            rows="2"
                            ${this.state.isProcessing ? 'disabled' : ''}
                        ></textarea>
                        <button class="btn-primary" id="serenaSendBtn" ${this.state.isProcessing ? 'disabled' : ''}>
                            Send
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    renderMessages() {
        return this.state.messages.map(msg => `
            <div class="message ${msg.role} ${msg.role === 'assistant' ? 'serena' : ''}">
                <div class="message-content">${this.escapeHtml(msg.content)}</div>
                <div class="message-time">${msg.timestamp}</div>
            </div>
        `).join('');
    }

    attachEventListeners() {
        const sendBtn = this.container.querySelector('#serenaSendBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        const input = this.container.querySelector('#serenaInput');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        const clearBtn = this.container.querySelector('#serenaClear');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearHistory());
        }

        const skillsBtn = this.container.querySelector('#serenaSkills');
        if (skillsBtn) {
            skillsBtn.addEventListener('click', () => this.showSkills());
        }

        const resetBtn = this.container.querySelector('#serenaReset');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => this.reset());
        }
    }

    sendMessage() {
        const input = this.container.querySelector('#serenaInput');
        const message = input.value.trim();

        if (!message || this.state.isProcessing) return;

        this.addMessage({
            role: 'user',
            content: message,
            timestamp: new Date().toLocaleTimeString()
        });

        input.value = '';

        if (wsManager) {
            wsManager.send({
                type: 'serena_message',
                content: message,
                session_id: this.state.sessionId
            });
        }

        this.setState({ isProcessing: true });
    }

    addMessage(message) {
        this.state.messages.push(message);
        this.render();
        this.attachEventListeners(); // Re-attach after render

        // FIXED: Robust auto-scroll implementation
        this.scrollToBottom();

        this.saveHistory();
    }

    scrollToBottom() {
        const messagesDiv = this.container.querySelector('#serenaMessages');
        if (!messagesDiv) return;

        // Multiple strategies to ensure scroll works
        const scroll = () => {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Force reflow
            messagesDiv.offsetHeight;
            messagesDiv.scrollTop = messagesDiv.scrollHeight;

            // Fallback: scrollIntoView on last message
            const lastMessage = messagesDiv.lastElementChild;
            if (lastMessage) {
                lastMessage.scrollIntoView({ behavior: 'smooth', block: 'end' });
            }
        };

        // Immediate scroll
        scroll();

        // Delayed scrolls to handle rendering delays
        requestAnimationFrame(() => {
            scroll();
            setTimeout(scroll, 10);
            setTimeout(scroll, 50);
            setTimeout(scroll, 100);
        });
    }

    handleMessage(data) {
        if (data.type === 'serena_message') {
            // Remove "thinking" indicators
            if (data.role === 'assistant') {
                this.removeThinkingMessages();
            }

            this.addMessage({
                role: data.role,
                content: data.content,
                timestamp: new Date().toLocaleTimeString()
            });

            if (data.role === 'assistant') {
                this.setState({ isProcessing: false });
            }
        }
    }

    removeThinkingMessages() {
        this.state.messages = this.state.messages.filter(msg =>
            !(msg.role === 'system' && msg.content.includes('thinking'))
        );
    }

    showSkills() {
        if (wsManager) {
            wsManager.send({
                type: 'serena_command',
                command: 'list_skills'
            });
        }
    }

    reset() {
        if (wsManager) {
            wsManager.send({
                type: 'serena_command',
                command: 'reset'
            });
        }
        this.clearHistory();
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem('serena_chat_history');
            if (saved) {
                this.state.messages = JSON.parse(saved);
            }
        } catch (e) {
            console.error('Failed to load Serena history:', e);
        }
    }

    saveHistory() {
        try {
            localStorage.setItem('serena_chat_history', JSON.stringify(this.state.messages));
        } catch (e) {
            console.error('Failed to save Serena history:', e);
        }
    }

    clearHistory() {
        this.state.messages = [];
        this.render();
        this.attachEventListeners();
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
    module.exports = SerenaPanel;
}
