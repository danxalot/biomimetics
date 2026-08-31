/**
 * ARCA Project Visualization Module
 * 
 * Provides:
 * 1. Mermaid Graph pane for Neo4j layered architecture
 * 2. Redis Document Breakdown visualization
 * 3. 3D Project representation integration
 */

// ===== STATE =====
let mermaidInitialized = false;
let redisVisualizationActive = false;
let documentBreakdownData = null;

// ===== MERMAID ARCHITECTURE GRAPH =====

/**
 * Generate comprehensive Mermaid diagram from Neo4j layered representation
 */
function generateProjectMermaidDiagram() {
    return `
%%{init: {'theme': 'dark', 'themeVariables': { 'primaryColor': '#ffd700', 'primaryTextColor': '#fff', 'lineColor': '#4ec9b0', 'secondaryColor': '#1e1e1e'}}}%%
flowchart TB
    subgraph Infrastructure["🏗️ INFRASTRUCTURE LAYER"]
        direction LR
        OCI_VM["OCI A1 Workhorse<br/>24GB ARM"]
        MAC_LOCAL["macOS Dev<br/>Local Services"]
        GCP_HOT["GCP Hot Layer<br/>Cloud Run"]
    end

    subgraph Services["⚙️ SERVICES LAYER"]
        direction TB
        subgraph CoreServices["Core Services"]
            REDIS[("🔴 Redis<br/>Blackboard")]
            NEO4J[("🟢 Neo4j<br/>Knowledge Graph")]
            POSTGRES[("🐘 PostgreSQL<br/>Persistent Store")]
            OLLAMA["🦙 Ollama<br/>Local LLM"]
        end
        
        subgraph AgentServices["Agent Services"]
            AGENT_SVC["Agent Service<br/>:8088"]
            MCP_SERVER["MCP Server<br/>:8080"]
            UI_AGENT["User Interaction<br/>:8089"]
            LLM_GW["LLM Gateway<br/>:8000"]
        end
        
        subgraph MonitoringServices["Monitoring"]
            RES_MON["Resource Monitor<br/>:9090"]
            OTEL["OTel Collector"]
            LOKI["Loki Logs"]
            GRAFANA["Grafana<br/>:3000"]
        end
    end

    subgraph Workflow["🔄 WORKFLOW LAYER"]
        direction LR
        subgraph GenesisChain["Genesis Chain"]
            ARCHITECT["Architect<br/>Tier 3"]
            PLANNER["Planner<br/>Tier 2"]
            ENGINEER["Engineer<br/>Tier 1"]
            REVIEWER["Reviewer<br/>Tier 1"]
            OPS["Ops Controller<br/>Tier 1"]
        end
        
        subgraph SerenaChain["Serena Agent"]
            SERENA_CORE["Serena Core"]
            CODE_TOOLS["Code Tools"]
            SKILL_BANK["Skill Bank"]
        end
    end

    subgraph Code["💻 CODE LAYER"]
        direction TB
        LANGGRAPH["LangGraph<br/>Workflows"]
        MCP_TOOLS["MCP Tools<br/>57 Skills"]
        GEOMETRY["Geometry Kernel<br/>3D State"]
        HDC["HDC Encoder<br/>Vectors"]
    end

    subgraph Functions["🎯 FUNCTIONS LAYER"]
        direction LR
        NEO4J_QUERY["neo4j_query()"]
        REDIS_BLACKBOARD["blackboard_read/write()"]
        LLM_INVOKE["llm_invoke()"]
        SKILL_EXECUTE["skill_execute()"]
        GEOMETRY_TICK["geometry_tick()"]
    end

    %% Connections
    OCI_VM --> CoreServices
    MAC_LOCAL --> AgentServices
    GCP_HOT --> LLM_GW

    AGENT_SVC --> GenesisChain
    AGENT_SVC --> SerenaChain
    MCP_SERVER --> MCP_TOOLS
    
    ARCHITECT --> PLANNER --> ENGINEER --> REVIEWER --> OPS
    
    LANGGRAPH --> GenesisChain
    MCP_TOOLS --> Functions
    GEOMETRY --> REDIS
    
    NEO4J_QUERY --> NEO4J
    REDIS_BLACKBOARD --> REDIS
    LLM_INVOKE --> OLLAMA
    LLM_INVOKE --> LLM_GW
    SKILL_EXECUTE --> MCP_TOOLS
    GEOMETRY_TICK --> GEOMETRY

    %% Styling
    style OCI_VM fill:#ff6b35,stroke:#fff
    style MAC_LOCAL fill:#007aff,stroke:#fff
    style GCP_HOT fill:#34c759,stroke:#fff
    
    style REDIS fill:#dc382d,stroke:#fff,color:#fff
    style NEO4J fill:#008cc1,stroke:#fff,color:#fff
    style POSTGRES fill:#336791,stroke:#fff,color:#fff
    
    style ARCHITECT fill:#ffd700,stroke:#333,color:#000
    style PLANNER fill:#ffd700,stroke:#333,color:#000
    style ENGINEER fill:#ffd700,stroke:#333,color:#000
    
    style GEOMETRY fill:#af52de,stroke:#fff,color:#fff
    style HDC fill:#ff9500,stroke:#fff,color:#fff
`;
}

function generateOracleDiagram() {
    return `
flowchart LR
    subgraph Input
        U[User Intent] -->|Vector| I[Intention Field]
        T[Telemetry] -->|State| S[System Context]
    end
    
    subgraph Oracle["PYTHIA (Learning Engine)"]
        direction TB
        JEPA[Holographic JEPA]
        PRED[Predictive Model]
        CUR[Curiosity Engine]
        
        I & S --> JEPA
        JEPA -->|Latent| PRED
        PRED -->|Forecast| CUR
        CUR -->|Novelty?| ACTION
    end
    
    subgraph Output
        ACTION -->|Adjustment| SYS[System Config]
        ACTION -->|Suggestion| GEN[Genesis Agent]
    end
    
    style Oracle fill:#00ffff,stroke:#333,color:#000
    style JEPA fill:#af52de
    style CUR fill:#ff9500
`;
}

function generatePythagorusDiagram() {
    return `
flowchart TD
    subgraph Kernel["THE MOUNT (Geometry Kernel)"]
        direction TB
        MAN[Riemannian Manifold]
        ATT[Attractors]
        TRAJ[Trajectory]
        
        MAN -->|Curvature| ATT
        ATT -->|Pull| TRAJ
    end
    
    subgraph Agents
        GEN[Genesis]
        SER[Serena]
    end
    
    subgraph State
        V[Vector State]
        E[Energy Surface]
    end
    
    GEN -->|Force| MAN
    SER -->|Constraint| MAN
    
    TRAJ -->|Update| V
    V -->|Feedback| E
    
    style Kernel fill:#9370db,stroke:#333
    style MAN fill:#4b0082,color:#fff
    style ATT fill:#ffd700,color:#000
`;
}

/**
 * Initialize the Mermaid graph pane
 */
async function initMermaidGraphPane(containerId = 'mermaidGraphPane') {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn('Mermaid container not found:', containerId);
        return;
    }

    // Ensure Mermaid is loaded
    if (!window.mermaid) {
        await loadMermaidLibrary();
    }

    // Configure Mermaid
    window.mermaid.initialize({
        startOnLoad: false,
        theme: 'dark',
        themeVariables: {
            primaryColor: '#ffd700',
            primaryTextColor: '#ffffff',
            lineColor: '#4ec9b0',
            secondaryColor: '#2d2d30',
            tertiaryColor: '#1e1e1e'
        },
        flowchart: {
            curve: 'basis',
            padding: 15,
            nodeSpacing: 50,
            rankSpacing: 50,
            useMaxWidth: false,
            htmlLabels: true
        },
        securityLevel: 'loose'
    });

    const diagramFull = generateProjectMermaidDiagram();

    container.innerHTML = `
        <div class="mermaid-header">
            <span class="mermaid-title">🗺️ Project Architecture</span>
            <div class="mermaid-controls">
                <select id="mermaidMapSelector" onchange="renderMermaidMap(this.value)" style="background:#3c3c3c; color:#ccc; border:1px solid #5a5a5a; font-size:11px; margin-right:8px;">
                    <option value="full">Full System</option>
                    <option value="oracle">Pythia (Learning)</option>
                    <option value="pythagorus">The Mount (Geometry)</option>
                </select>
                <button class="btn-tiny" onclick="refreshMermaidGraph()">🔄</button>
                <button class="btn-tiny" onclick="zoomMermaidGraph(1.2)">➕</button>
                <button class="btn-tiny" onclick="zoomMermaidGraph(0.8)">➖</button>
                <button class="btn-tiny" onclick="toggleMermaidFullscreen()">⛶</button>
            </div>
        </div>
        <div class="mermaid-content" id="mermaidContent" style="overflow: auto; display: flex; justify-content: center;">
            <div class="mermaid" id="mermaidTarget" style="transform: scale(1.2); transform-origin: top center;">${diagramFull}</div>
        </div>
    `;

    try {
        await window.mermaid.run({
            nodes: container.querySelectorAll('.mermaid')
        });
        mermaidInitialized = true;
    } catch (e) {
        console.error('Mermaid render error:', e);
    }
}

window.renderMermaidMap = async function (type) {
    const container = document.getElementById('mermaidTarget');
    if (!container) return;

    let chart = '';
    if (type === 'oracle') chart = generateOracleDiagram();
    else if (type === 'pythagorus') chart = generatePythagorusDiagram();
    else chart = generateProjectMermaidDiagram();

    container.innerHTML = chart;
    container.removeAttribute('data-processed'); // Reset mermaid processing

    try {
        await window.mermaid.run({
            nodes: [container]
        });
    } catch (e) {
        container.innerHTML = `<div style="color:red">Render Error: ${e.message}</div>`;
    }
};

function loadMermaidLibrary() {
    return new Promise((resolve, reject) => {
        if (window.mermaid) {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js';
        script.onload = resolve;
        script.onerror = reject;
        document.head.appendChild(script);
    });
}

let mermaidZoom = 1;
function zoomMermaidGraph(factor) {
    mermaidZoom *= factor;
    const content = document.querySelector('.mermaid-content');
    if (content) {
        content.style.transform = `scale(${mermaidZoom})`;
        content.style.transformOrigin = 'top left';
    }
}

function refreshMermaidGraph() {
    initMermaidGraphPane('mermaidGraphPane');
}

function toggleMermaidFullscreen() {
    const pane = document.getElementById('mermaidGraphPane');
    if (pane) {
        pane.classList.toggle('fullscreen');
    }
}


// ===== REDIS DOCUMENT BREAKDOWN VISUALIZATION =====

/**
 * Visualize how a document is broken down through the kernel
 */
function initRedisDocumentPane(containerId = 'redisDocumentPane') {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn('Redis document container not found:', containerId);
        return;
    }

    container.innerHTML = `
        <div class="redis-doc-header">
            <span class="redis-doc-title">📄 Document Processing Pipeline</span>
            <div class="redis-doc-controls">
                <button class="btn-tiny" onclick="fetchDocumentBreakdown()">🔄 Refresh</button>
                <button class="btn-tiny" onclick="clearDocumentView()">🗑️ Clear</button>
            </div>
        </div>
        <div class="redis-doc-content" id="redisDocContent">
            <div class="redis-stages">
                <div class="stage-card" id="stage-input">
                    <div class="stage-header">📥 INPUT</div>
                    <div class="stage-body">
                        <div class="placeholder">Awaiting document...</div>
                    </div>
                </div>
                <div class="stage-arrow">→</div>
                <div class="stage-card" id="stage-chunks">
                    <div class="stage-header">✂️ CHUNKS</div>
                    <div class="stage-body">
                        <div class="placeholder">No chunks yet</div>
                    </div>
                </div>
                <div class="stage-arrow">→</div>
                <div class="stage-card" id="stage-vectors">
                    <div class="stage-header">🧬 VECTORS</div>
                    <div class="stage-body">
                        <div class="placeholder">No embeddings</div>
                    </div>
                </div>
                <div class="stage-arrow">→</div>
                <div class="stage-card" id="stage-redis">
                    <div class="stage-header">🔴 REDIS</div>
                    <div class="stage-body">
                        <div class="placeholder">No keys stored</div>
                    </div>
                </div>
            </div>
            <div class="redis-keys-panel" id="redisKeysPanel">
                <div class="keys-header">Redis Blackboard Keys</div>
                <div class="keys-list" id="redisKeysList">
                    <div class="key-item">arca:state:global</div>
                    <div class="key-item">arca:blackboard:*</div>
                    <div class="key-item">arca:doc:chunks:*</div>
                </div>
            </div>
        </div>
    `;

    // Start WebSocket listener for document events
    startDocumentBreakdownListener();

    console.log('📄 Redis Document Pane initialized');
}

/**
 * Update visualization when a document is processed
 */
function updateDocumentBreakdown(data) {
    documentBreakdownData = data;

    // Update Input Stage
    const inputStage = document.querySelector('#stage-input .stage-body');
    if (inputStage && data.input) {
        inputStage.innerHTML = `
            <div class="doc-info">
                <span class="doc-name">${data.input.filename || 'document'}</span>
                <span class="doc-size">${formatBytes(data.input.size || 0)}</span>
            </div>
            <div class="doc-preview">${(data.input.preview || '').substring(0, 200)}...</div>
        `;
    }

    // Update Chunks Stage
    const chunksStage = document.querySelector('#stage-chunks .stage-body');
    if (chunksStage && data.chunks) {
        const chunksList = data.chunks.slice(0, 5).map((chunk, i) =>
            `<div class="chunk-item">
                <span class="chunk-id">Chunk ${i + 1}</span>
                <span class="chunk-tokens">${chunk.tokens || '?'} tokens</span>
            </div>`
        ).join('');
        chunksStage.innerHTML = `
            <div class="chunks-count">${data.chunks.length} chunks created</div>
            ${chunksList}
            ${data.chunks.length > 5 ? `<div class="more-chunks">+${data.chunks.length - 5} more...</div>` : ''}
        `;
    }

    // Update Vectors Stage
    const vectorsStage = document.querySelector('#stage-vectors .stage-body');
    if (vectorsStage && data.vectors) {
        vectorsStage.innerHTML = `
            <div class="vector-info">
                <span class="vector-count">${data.vectors.count || 0} embeddings</span>
                <span class="vector-dim">dim: ${data.vectors.dimensions || 384}</span>
            </div>
            <div class="vector-model">${data.vectors.model || 'nomic-embed-text'}</div>
        `;
    }

    // Update Redis Stage
    const redisStage = document.querySelector('#stage-redis .stage-body');
    if (redisStage && data.redis_keys) {
        const keysList = data.redis_keys.slice(0, 5).map(key =>
            `<div class="redis-key">${key}</div>`
        ).join('');
        redisStage.innerHTML = `
            <div class="redis-count">${data.redis_keys.length} keys stored</div>
            ${keysList}
        `;
    }

    // Update Keys Panel
    const keysPanel = document.getElementById('redisKeysList');
    if (keysPanel && data.redis_keys) {
        keysPanel.innerHTML = data.redis_keys.map(key =>
            `<div class="key-item" onclick="inspectRedisKey('${key}')">${key}</div>`
        ).join('');
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Listen for document processing events via WebSocket
 */
function startDocumentBreakdownListener() {
    // Hook into existing WebSocket if available
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        const originalOnMessage = window.ws.onmessage;
        window.ws.onmessage = function (event) {
            const data = JSON.parse(event.data);

            // Handle document breakdown events
            if (data.type === 'document_breakdown' || data.type === 'kernel_process') {
                updateDocumentBreakdown(data);
            }

            // Call original handler
            if (originalOnMessage) {
                originalOnMessage.call(window.ws, event);
            }
        };
    }
}

async function fetchDocumentBreakdown() {
    try {
        const response = await fetch('/api/kernel/document-state');
        if (response.ok) {
            const data = await response.json();
            updateDocumentBreakdown(data);
        }
    } catch (e) {
        console.log('Document state fetch:', e.message);
    }
}

function clearDocumentView() {
    documentBreakdownData = null;
    initRedisDocumentPane('redisDocumentPane');
}

function inspectRedisKey(key) {
    // Send inspection request
    if (window.ws && window.ws.readyState === WebSocket.OPEN) {
        window.ws.send(JSON.stringify({
            type: 'redis_inspect',
            key: key
        }));
    }
}


// ===== 3D PROJECT VIEW INTEGRATION =====

/**
 * Initialize 3D view in the document viewer pane
 */
function init3DProjectView(containerId = 'docContent') {
    const container = document.getElementById(containerId);
    if (!container) {
        console.warn('3D container not found:', containerId);
        return;
    }

    // Ensure container has height - get from parent if needed
    const parentHeight = container.parentElement?.clientHeight || 350;
    const containerHeight = Math.max(container.clientHeight || 0, parentHeight - 40, 350);

    // Check if dashboard is available with retry
    const tryInit = (attempts = 0) => {
        if (typeof window.initSciFiDashboard === 'function') {
            container.innerHTML = `<div id="project3DContainer" style="width:100%;height:${containerHeight}px;min-height:350px;"></div>`;

            setTimeout(() => {
                const target = document.getElementById('project3DContainer');
                if (target) {
                    try {
                        console.log('🎮 Starting 3D Project View Init...');
                        window.initSciFiDashboard(target);
                        console.log('🎮 3D Project View initialized success');
                    } catch (e) {
                        console.error('3D Project View Init Failed:', e);
                        target.innerHTML = `<div class="error" style="padding:10px; color:red;">
                            <strong>3D View Error:</strong><br>${e.message}
                         </div>`;
                    }
                }
            }, 100);
        } else if (attempts < 5) {
            // Retry a few times in case scripts are still loading
            console.log(`Waiting for 3D dashboard script... (attempt ${attempts + 1})`);
            setTimeout(() => tryInit(attempts + 1), 500);
        } else {
            container.innerHTML = `
                <div style="padding:20px; color:#ccc; text-align:center;">
                    <h3>3D Dashboard Loading...</h3>
                    <p>The 3D visualization module is initializing.</p>
                    <button class="btn secondary" onclick="init3DProjectView('${containerId}')" style="margin-top:10px;">
                        🔄 Retry
                    </button>
                </div>`;
        }
    };

    tryInit();
}

/**
 * Dock 3D view to the document viewer (bottom pane)
 */
window.dock3DViewDown = function () {
    const docViewer = document.getElementById('docViewer');
    const docContent = document.getElementById('docContent');
    const dynamicPane = document.getElementById('dynamicViewPane');

    if (docViewer && docContent) {
        // Expand doc viewer
        docViewer.classList.remove('collapsed', 'hidden');
        docViewer.style.height = '50vh';

        // Update title
        const titleEl = document.getElementById('docTitle');
        if (titleEl) titleEl.textContent = '🎮 3D System Visualization';

        // Initialize 3D in the doc viewer
        init3DProjectView('docContent');

        // Hide the dynamic overlay pane
        if (dynamicPane) {
            dynamicPane.classList.add('hidden');
        }
    }
};


// ===== LAYER TOGGLE FOR 3D VIEW =====

window.update3DLayers = function () {
    const layers = {
        prompt: document.getElementById('layerPrompt')?.checked ?? true,
        system: document.getElementById('layerSystem')?.checked ?? true,
        concept: document.getElementById('layerConcept')?.checked ?? true,
        oracle: document.getElementById('layerOracle')?.checked ?? true,
        knowledge: document.getElementById('layerKnowledge')?.checked ?? true
    };

    // Apply to 3D scene if available
    if (typeof updateDashboardLayers === 'function') {
        updateDashboardLayers(layers);
    }

    console.log('Layer visibility updated:', layers);
};


// ===== PANE MANAGER =====

/**
 * Create a new resizable pane
 */
function createResizablePane(id, title, position = 'left') {
    const pane = document.createElement('div');
    pane.id = id;
    pane.className = `resizable-pane pane-${position}`;
    pane.innerHTML = `
        <div class="pane-header">
            <span class="pane-title">${title}</span>
            <div class="pane-controls">
                <button class="btn-tiny" onclick="minimizePane('${id}')">_</button>
                <button class="btn-tiny" onclick="maximizePane('${id}')">□</button>
                <button class="btn-tiny" onclick="closePane('${id}')">×</button>
            </div>
        </div>
        <div class="pane-content" id="${id}Content"></div>
        <div class="pane-resizer ${position === 'left' ? 'resizer-right' : 'resizer-left'}"></div>
    `;

    // Add resize handler
    const resizer = pane.querySelector('.pane-resizer');
    initPaneResizer(pane, resizer, position);

    return pane;
}

function initPaneResizer(pane, resizer, position) {
    let startX, startWidth;

    resizer.addEventListener('mousedown', (e) => {
        startX = e.clientX;
        startWidth = pane.offsetWidth;

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
        document.body.style.cursor = 'col-resize';
        resizer.classList.add('active');
    });

    function onMouseMove(e) {
        const delta = position === 'left' ? e.clientX - startX : startX - e.clientX;
        const newWidth = Math.max(200, Math.min(startWidth + delta, window.innerWidth * 0.6));
        pane.style.width = `${newWidth}px`;
    }

    function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        document.body.style.cursor = '';
        resizer.classList.remove('active');
        window.dispatchEvent(new Event('resize'));
    }
}

function minimizePane(id) {
    const pane = document.getElementById(id);
    if (pane) pane.classList.toggle('minimized');
}

function maximizePane(id) {
    const pane = document.getElementById(id);
    if (pane) pane.classList.toggle('maximized');
}

function closePane(id) {
    const pane = document.getElementById(id);
    if (pane) pane.classList.add('hidden');
}


// ===== EXPORTS =====

window.initMermaidGraphPane = initMermaidGraphPane;
window.initRedisDocumentPane = initRedisDocumentPane;
window.init3DProjectView = init3DProjectView;
window.updateDocumentBreakdown = updateDocumentBreakdown;
window.createResizablePane = createResizablePane;
window.generateProjectMermaidDiagram = generateProjectMermaidDiagram;

console.log('📦 Project Visualization Module loaded');
