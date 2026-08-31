/**
 * ResourceMonitor - System Monitoring & Graph Visualization Component
 * FIXED: Added Mermaid diagram rendering for infrastructure and logic graphs
 */
class ResourceMonitor extends BaseComponent {
    constructor(containerId = '#resource-panel') {
        super(containerId);
        this.state = {
            view: 'graphs', // 'graphs', 'metrics', 'logs'
            mermaidDiagram: null,
            metrics: {},
            logs: []
        };

        // Load Mermaid library if not already loaded
        this.loadMermaid();
    }

    template() {
        return `
            <div class="resource-container">
                <div class="resource-header">
                    <span>Resource Monitor</span>
                    <div class="view-tabs">
                        <button class="tab ${this.state.view === 'graphs' ? 'active' : ''}" data-view="graphs">Graphs</button>
                        <button class="tab ${this.state.view === 'metrics' ? 'active' : ''}" data-view="metrics">Metrics</button>
                        <button class="tab ${this.state.view === 'logs' ? 'active' : ''}" data-view="logs">Logs</button>
                    </div>
                </div>
                
                <div class="resource-content">
                    ${this.renderContent()}
                </div>
            </div>
        `;
    }

    renderContent() {
        switch (this.state.view) {
            case 'graphs':
                return this.renderGraphView();
            case 'metrics':
                return this.renderMetricsView();
            case 'logs':
                return this.renderLogsView();
            default:
                return '<div>Unknown view</div>';
        }
    }

    renderGraphView() {
        return `
            <div class="graph-view">
                <div class="graph-controls">
                    <select id="graphFocus">
                        <option value="mcp_server">mcp_server</option>
                        <option value="postgres">postgres</option>
                        <option value="neo4j">neo4j</option>
                        <option value="redis">redis</option>
                    </select>
                    
                    <select id="graphType">
                        <option value="infrastructure">Infrastructure</option>
                        <option value="logic">Logic</option>
                        <option value="full">Full</option>
                    </select>
                    
                    <button class="btn-primary" id="generateGraph">Generate Graph</button>
                </div>
                
                <div class="mermaid-container" id="mermaidContainer">
                    ${this.state.mermaidDiagram ?
                `<div class="mermaid">${this.state.mermaidDiagram}</div>` :
                '<div class="placeholder">Select entity and click "Generate Graph"</div>'
            }
                </div>
            </div>
        `;
    }

    renderMetricsView() {
        return `
            <div class="metrics-view">
                <div class="metric-card">
                    <div class="metric-label">CPU</div>
                    <div class="metric-value">${this.state.metrics.cpu || '0'}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Memory</div>
                    <div class="metric-value">${this.state.metrics.memory || '0'}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Services</div>
                    <div class="metric-value">${this.state.metrics.services || '0'}/25</div>
                </div>
            </div>
        `;
    }

    renderLogsView() {
        return `
            <div class="logs-view">
                ${this.state.logs.map(log => `
                    <div class="log-entry ${log.level}">
                        <span class="log-time">${log.timestamp}</span>
                        <span class="log-message">${log.message}</span>
                    </div>
                `).join('')}
            </div>
        `;
    }

    attachEventListeners() {
        // View tabs
        const tabs = this.container.querySelectorAll('.tab');
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                this.setState({ view: tab.dataset.view });
            });
        });

        // Generate graph button
        const generateBtn = this.container.querySelector('#generateGraph');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.generateMermaidGraph());
        }
    }

    async generateMermaidGraph() {
        const focusSelect = this.container.querySelector('#graphFocus');
        const typeSelect = this.container.querySelector('#graphType');

        const focus = focusSelect.value;
        const graphType = typeSelect.value;

        try {
            // Call backend API to generate Mermaid diagram
            const response = await fetch(`/api/graph/mermaid?focus=${focus}&type=${graphType}`);
            const data = await response.json();

            this.setState({ mermaidDiagram: data.mermaid });

            // Render Mermaid diagram
            this.renderMermaid();

        } catch (e) {
            console.error('Failed to generate Mermaid graph:', e);

            // Fallback to demo graph
            this.setState({
                mermaidDiagram: this.getDemoGraph(focus)
            });
            this.renderMermaid();
        }
    }

    getDemoGraph(focus) {
        return `
graph TD
    A[${focus}] -->|EXPOSES| B[Port 8086]
    A -->|MOUNTS| C[Volume]
    A -->|USES| D[Environment Vars]
    style A fill:#f9f,stroke:#333,stroke-width:3px
    style B fill:#bbf,stroke:#333
    style C fill:#afa,stroke:#333
    style D fill:#ffa,stroke:#333
        `;
    }

    async loadMermaid() {
        if (typeof mermaid !== 'undefined') {
            this.initializeMermaid();
            return;
        }

        // Load Mermaid library dynamically
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js';
        script.onload = () => this.initializeMermaid();
        document.head.appendChild(script);
    }

    initializeMermaid() {
        if (typeof mermaid !== 'undefined') {
            mermaid.initialize({
                startOnLoad: false,
                theme: 'dark',
                themeVariables: {
                    primaryColor: '#4ec9b0',
                    primaryTextColor: '#fff',
                    primaryBorderColor: '#3e3e42',
                    lineColor: '#4ec9b0',
                    secondaryColor: '#007acc',
                    tertiaryColor: '#1e1e1e'
                }
            });
        }
    }

    async renderMermaid() {
        const container = this.container.querySelector('#mermaidContainer');
        if (!container || !this.state.mermaidDiagram) return;

        if (typeof mermaid !== 'undefined') {
            try {
                // Clear previous diagram
                container.innerHTML = `<div class="mermaid">${this.state.mermaidDiagram}</div>`;

                // Render with Mermaid
                await mermaid.run({
                    querySelector: '.mermaid'
                });
            } catch (e) {
                console.error('Mermaid rendering error:', e);
                container.innerHTML = `<pre>${this.state.mermaidDiagram}</pre>`;
            }
        } else {
            // Fallback: show as code
            container.innerHTML = `<pre>${this.state.mermaidDiagram}</pre>`;
        }
    }

    handleMessage(data) {
        if (data.type === 'metrics_update') {
            this.setState({ metrics: data.metrics });
        } else if (data.type === 'log_entry') {
            this.state.logs.unshift(data.log);
            if (this.state.logs.length > 100) {
                this.state.logs = this.state.logs.slice(0, 100);
            }
            if (this.state.view === 'logs') {
                this.render();
                this.attachEventListeners();
            }
        }
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ResourceMonitor;
}
