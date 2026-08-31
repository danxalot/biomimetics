/**
 * ChatPanelPuterAI - Puter.js AI-Powered Chat Component
 * PROTOTYPE: Uses Puter AI SDK instead of backend agent service
 */
class ChatPanelPuterAI extends BaseComponent {
    constructor(containerId = '#chat-panel') {
        super(containerId);
        this.state = {
            messages: [],
            isProcessing: false,
            sessionId: null
        };

        // Puter AI instance
        this.ai = null;
        this.mcpApiUrl = 'http://localhost:8086';  // MCP server URL
        this.apiToken = null;  // Will be set via auth

        // Initialize Puter AI
        this.initializePuterAI();

        // Load chat history
        this.loadHistory();
    }

    async initializePuterAI() {
        try {
            // Check if running in Puter environment
            if (typeof puter === 'undefined') {
                console.warn('Puter.js not available, using mock AI');
                this.ai = new MockPuterAI();
                return;
            }

            // Initialize Puter AI with ARCA configuration
            this.ai = await puter.ai.create({
                model: 'gemini-2.0-flash-exp',  // or 'claude-3-5-sonnet', 'gpt-4'
                temperature: 0.7,
                systemPrompt: this.getARCASystemPrompt(),
                tools: this.getMCPTools()
            });

            console.log('✅ Puter AI initialized with MCP tools');
        } catch (e) {
            console.error('Failed to initialize Puter AI:', e);
            this.ai = new MockPuterAI();
        }
    }

    getARCASystemPrompt() {
        return `You are ARCA (Agentic Research & Collaboration Assistant), a sophisticated AI assistant with access to powerful system tools.

IDENTITY & CAPABILITIES:
- You have access to Neo4j graph database, pgvector memory, and Redis geometry kernel
- You can discover infrastructure, generate diagrams, search code, and analyze systems
- You speak with technical precision and proactive problem-solving

TOOLS AVAILABLE:
- discover_infrastructure: Map Docker services and configuration
- discover_logic: Analyze MCP tools and functions
- discover_agents: Map LangGraph agent workflows
- generate_mermaid: Create visualization diagrams
- crawl_codebase: Build dependency graphs
- semantic_graph_search: Search across all system knowledge
- embed_graph: Add vector embeddings to nodes

BEHAVIOR:
- Be concise and actionable
- Proactively use tools to answer questions
- Explain your reasoning when using tools
- Suggest next steps or related queries

Always prioritize using your tools to provide accurate, data-driven responses.`;
    }

    getMCPTools() {
        // Define MCP tools for Puter AI
        return [
            {
                name: 'discover_infrastructure',
                description: 'Discover and map Docker infrastructure from docker-compose to Neo4j (Services, Ports, Volumes)',
                parameters: {
                    type: 'object',
                    properties: {
                        compose_path: {
                            type: 'string',
                            description: 'Path to docker-compose.yml (optional)'
                        }
                    }
                },
                execute: async (args) => {
                    return await this.callMCPTool('discover_infrastructure', args);
                }
            },
            {
                name: 'discover_logic',
                description: 'Discover and map MCP Tools/Skills from codebase to Neo4j Logic Graph',
                parameters: {
                    type: 'object',
                    properties: {
                        tools_dir: {
                            type: 'string',
                            description: 'Path to tools directory (optional)'
                        }
                    }
                },
                execute: async (args) => {
                    return await this.callMCPTool('discover_logic', args);
                }
            },
            {
                name: 'generate_mermaid',
                description: 'Generate Mermaid diagram for graph visualization',
                parameters: {
                    type: 'object',
                    properties: {
                        focus: {
                            type: 'string',
                            description: 'Entity to focus on (e.g., mcp_server, postgres)'
                        },
                        graph_type: {
                            type: 'string',
                            enum: ['infrastructure', 'logic', 'full'],
                            description: 'Type of graph to generate'
                        }
                    },
                    required: ['focus']
                },
                execute: async (args) => {
                    return await this.callMCPTool('generate_mermaid', args);
                }
            },
            {
                name: 'query_infrastructure',
                description: 'Run a Cypher query against the Infrastructure graph in Neo4j',
                parameters: {
                    type: 'object',
                    properties: {
                        query: {
                            type: 'string',
                            description: 'Cypher query to execute'
                        }
                    },
                    required: ['query']
                },
                execute: async (args) => {
                    return await this.callMCPTool('query_infrastructure', args);
                }
            },
            {
                name: 'semantic_graph_search',
                description: 'Semantic search across Neo4j graph using vector embeddings',
                parameters: {
                    type: 'object',
                    properties: {
                        query: {
                            type: 'string',
                            description: 'Natural language query'
                        },
                        limit: {
                            type: 'integer',
                            description: 'Max results (default: 5)'
                        },
                        use_hse: {
                            type: 'boolean',
                            description: 'Use HSE vectors instead of standard'
                        }
                    },
                    required: ['query']
                },
                execute: async (args) => {
                    return await this.callMCPTool('semantic_graph_search', args);
                }
            }
        ];
    }

    async callMCPTool(toolName, args) {
        try {
            const response = await fetch(`${this.mcpApiUrl}/mcp`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...(this.apiToken && { 'Authorization': `Bearer ${this.apiToken}` })
                },
                body: JSON.stringify({
                    method: 'tools/call',
                    params: {
                        name: toolName,
                        arguments: args
                    }
                })
            });

            if (!response.ok) {
                throw new Error(`MCP call failed: ${response.statusText}`);
            }

            const data = await response.json();
            return data.result || data;
        } catch (e) {
            console.error(`MCP tool ${toolName} failed:`, e);
            return { error: e.message };
        }
    }

    template() {
        return `
            <div class="chat-container">
                <div class="chat-header">
                    <div class="chat-title">
                        ${this.ai instanceof MockPuterAI ? '⚠️ Mock AI' : '🤖 Puter AI'} 
                        ARCA Terminal
                    </div>
                    <div class="chat-controls">
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
                            placeholder="Ask ARCA anything... (powered by Puter AI)" 
                            rows="2"
                            ${this.state.isProcessing ? 'disabled' : ''}
                        ></textarea>
                        <button class="btn-primary" id="sendBtn" ${this.state.isProcessing ? 'disabled' : ''}>
                            Send
                        </button>
                    </div>
                    <div class="ai-status">
                        ${this.ai instanceof MockPuterAI ?
                'Using mock AI (Puter.js not detected)' :
                'Powered by Puter AI with MCP tools'}
                    </div>
                </div>
            </div>
        `;
    }

    renderMessages() {
        return this.state.messages.map(msg => `
            <div class="message ${msg.role}">
                <div class="message-content">${this.formatContent(msg.content)}</div>
                <div class="message-time">${msg.timestamp}</div>
            </div>
        `).join('');
    }

    formatContent(content) {
        // Handle markdown, code blocks, etc.
        const escaped = this.escapeHtml(content);

        // Simple markdown formatting
        return escaped
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    attachEventListeners() {
        const sendBtn = this.container.querySelector('#sendBtn');
        if (sendBtn) {
            sendBtn.addEventListener('click', () => this.sendMessage());
        }

        const input = this.container.querySelector('#chatInput');
        if (input) {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });
        }

        const clearBtn = this.container.querySelector('#clearChat');
        if (clearBtn) {
            clearBtn.addEventListener('click', () => this.clearHistory());
        }
    }

    async sendMessage() {
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

        // Set processing state
        this.setState({ isProcessing: true });

        // Add thinking indicator
        this.addMessage({
            role: 'system',
            content: '🤔 Thinking...',
            timestamp: new Date().toLocaleTimeString()
        });

        try {
            // Call Puter AI
            const response = await this.ai.chat(message);

            // Remove thinking indicator
            this.state.messages = this.state.messages.filter(m =>
                !(m.role === 'system' && m.content.includes('Thinking'))
            );

            // Add AI response
            this.addMessage({
                role: 'assistant',
                content: response,
                timestamp: new Date().toLocaleTimeString()
            });
        } catch (e) {
            // Remove thinking indicator
            this.state.messages = this.state.messages.filter(m =>
                !(m.role === 'system' && m.content.includes('Thinking'))
            );

            // Show error
            this.addMessage({
                role: 'system',
                content: `Error: ${e.message}`,
                timestamp: new Date().toLocaleTimeString()
            });
        }

        this.setState({ isProcessing: false });
    }

    addMessage(message) {
        this.state.messages.push(message);
        this.render();
        this.attachEventListeners();
        this.scrollToBottom();
        this.saveHistory();
    }

    scrollToBottom() {
        const messagesDiv = this.container.querySelector('#chatMessages');
        if (messagesDiv) {
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    }

    loadHistory() {
        try {
            const saved = localStorage.getItem('arca_puter_chat_history');
            if (saved) {
                this.state.messages = JSON.parse(saved);
            }
        } catch (e) {
            console.error('Failed to load chat history:', e);
        }
    }

    saveHistory() {
        try {
            localStorage.setItem('arca_puter_chat_history', JSON.stringify(this.state.messages));
        } catch (e) {
            console.error('Failed to save chat history:', e);
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

/**
 * MockPuterAI - Fallback when Puter.js is not available
 */
class MockPuterAI {
    async chat(message) {
        // Simulate AI response
        await new Promise(resolve => setTimeout(resolve, 1000));

        if (message.toLowerCase().includes('infrastructure')) {
            return 'I can help you discover infrastructure using the `discover_infrastructure` tool. However, Puter.js AI is not available in this environment. Please deploy to puter.com to use real AI.';
        }

        return `Mock AI Response to: "${message}"\n\nTo use real AI, deploy this app to Puter.js. The AI would have access to all MCP tools and provide intelligent responses.`;
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ChatPanelPuterAI;
}
