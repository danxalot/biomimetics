/**
 * ARCA System Views - View Router & Manager
 * 
 * Responsibilities:
 * 1. Initialize View Tabs (Left Panel)
 * 2. Handle Drag & Drop for Panels
 * 3. Switch between Views (Unified, Library, Services, etc.)
 * 4. Delegate 3D rendering to system-3d-dashboard-v2.js
 * 5. Handle Mermaid rendering for topological diagrams
 */

// View Configuration and State
let currentView = 'unified';
const viewers = {
    unified: false,
    library: false,
    services: false,
    workflows: false,
    living: false,
    vectors: false
};

// Initialize System Views (Called by index.html on load)
function initSystemViews() {
    console.log("Initializing System Views Router...");
    try {
        createViewTabs();
        createViewContainers();
        initDragAndDrop(); // Initialize Panel Drag & Drop

        // Start with Unified view by default
        switchView('unified');

        // Initialize Resizers
        initResizers();

        console.log("System Views Initialized");
    } catch (e) {
        console.error("System Views Initialization Failed:", e);
    }
}

// --- 1. Tab & Container Management ---

function createViewTabs() {
    const panelHeader = document.querySelector('.panel-header');
    if (!panelHeader || !panelHeader.parentElement || panelHeader.parentElement.id !== 'leftPanel') return;

    // Reset Header
    panelHeader.innerHTML = '';

    // Drag Handle
    const dragHandle = document.createElement('span');
    dragHandle.className = 'drag-handle';
    dragHandle.title = 'Drag to reorder';
    dragHandle.textContent = ':::';
    panelHeader.appendChild(dragHandle);

    panelHeader.classList.add('view-tabs');

    // Define Tabs
    const tabs = [
        { id: 'unified', label: 'Unified System' },
        { id: 'living', label: 'Living System' },
        { id: 'library', label: 'Library' },
        // { id: 'vectors', label: 'Vector Space' }, // Merged into Unified
        { id: 'services', label: 'Services' },
        { id: 'workflows', label: 'Workflows' }
    ];

    tabs.forEach(tab => {
        const btn = document.createElement('button');
        btn.className = `tab-btn ${tab.id === 'unified' ? 'active' : ''}`;
        btn.textContent = tab.label;
        btn.dataset.view = tab.id; // Add data attribute for reliable matching
        btn.onclick = () => switchView(tab.id);
        panelHeader.appendChild(btn);
    });
}

function createViewContainers() {
    const leftPanel = document.getElementById('leftPanel');
    if (!leftPanel) return;

    // Ensure Library exists
    let libraryContent = document.getElementById('view-library');
    // If original HTML structure is used, wrap it or identify it
    // The original HTML has library toolbar/content directly in panel-content usually
    // But our switch logic needs distinct containers. 
    // For now, we assume the structure from the viewed index.html lines 457+ is correct.

    // Create Layout ID check
    const viewIds = ['unified', 'living', 'services', 'workflows', 'vectors'];

    viewIds.forEach(view => {
        const id = `view-${view}`;
        if (!document.getElementById(id)) {
            const container = document.createElement('div');
            container.id = id;
            container.className = 'view-content hidden';
            container.style.cssText = "flex: 1; height: 100%; width: 100%; overflow: hidden; position: relative;";

            if (view === 'unified') {
                container.innerHTML = '<div id="unified-canvas-container" style="width:100%; height:100%;"></div>';
            } else {
                container.innerHTML = `<div class="placeholder-view">Initializing ${view}...</div>`;
            }
            leftPanel.appendChild(container);
        }
    });
}

function switchView(viewId) {
    currentView = viewId;

    // Update Tab UI - use data-view attribute for reliable matching
    document.querySelectorAll('.tab-btn').forEach(btn => {
        const btnViewId = btn.dataset.view || '';
        btn.classList.toggle('active', btnViewId === viewId);
    });

    // Toggle Container Visibility
    ['library', 'unified', 'living', 'vectors', 'services', 'workflows'].forEach(id => {
        const container = document.getElementById(`view-${id}`);
        if (container) {
            if (id === viewId) {
                container.classList.remove('hidden');
                container.style.display = 'block'; // Ensure display
            } else {
                container.classList.add('hidden');
                container.style.display = 'none';
            }
        }
    });

    // Trigger View Logic
    if (viewId === 'unified') {
        // Delegate to Dashboard Script
        const container = document.getElementById('unified-canvas-container');
        if (window.initSciFiDashboard && container) {
            // Only init if not already running or valid
            // The dashboard script handles its own idempotency usually
            // Ensure container has dimensions before init
            requestAnimationFrame(() => {
                try {
                    console.log('Starting SciFi Dashboard Init...');
                    window.initSciFiDashboard(container);
                    viewers.unified = true;
                } catch (e) {
                    console.error('SciFi Dashboard Init Failed:', e);
                    container.innerHTML = `<div class="error" style="color:red; padding:20px;">
                        <h3>Dashboard Error</h3>
                        <pre>${e.message}</pre>
                        <pre>${e.stack}</pre>
                    </div>`;
                }
            });
        } else {
            if (container) container.innerHTML = "<div class='error'>Dashboard Script Not Loaded</div>";
        }
    } else if (viewId === 'services') {
        initServicesView();
    } else if (viewId === 'workflows') {
        initWorkflowsView();
    } else if (viewId === 'living') {
        initLivingSystemView();
    }
}

// --- 2. Panel Drag & Drop Logic ---
function initDragAndDrop() {
    const panels = document.querySelectorAll('.panel[draggable="true"]');
    const container = document.querySelector('.main-content');

    if (!container) return;

    panels.forEach(panel => {
        panel.addEventListener('dragstart', e => {
            panel.classList.add('dragging');
            e.dataTransfer.effectAllowed = 'move';
            e.dataTransfer.setData('text/plain', panel.id);
        });

        panel.addEventListener('dragend', () => {
            panel.classList.remove('dragging');
        });

        panel.addEventListener('dragover', e => {
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
        });

        panel.addEventListener('drop', e => {
            e.preventDefault();
            const sourceId = e.dataTransfer.getData('text/plain');
            const sourcePanel = document.getElementById(sourceId);
            const targetPanel = e.currentTarget;

            if (sourcePanel && targetPanel && sourcePanel !== targetPanel) {
                // Swap logic
                const currentPanels = Array.from(container.querySelectorAll('.panel'));
                const fromIndex = currentPanels.indexOf(sourcePanel);
                const toIndex = currentPanels.indexOf(targetPanel);

                // Reorder array
                currentPanels[fromIndex] = targetPanel;
                currentPanels[toIndex] = sourcePanel;

                // Reconstruct DOM with Resizers
                const resizer1 = document.getElementById('resizerLeft') || createResizer('resizerLeft');
                const resizer2 = document.getElementById('resizerRight') || createResizer('resizerRight');

                // Detach all
                currentPanels.forEach(p => p.remove());
                if (resizer1) resizer1.remove();
                if (resizer2) resizer2.remove();

                // Append in Order: P1, R1, P2, R2, P3
                container.appendChild(currentPanels[0]);
                container.appendChild(resizer1);
                container.appendChild(currentPanels[1]);
                container.appendChild(resizer2);
                container.appendChild(currentPanels[2]);
            }
        });
    });
}
function createResizer(id) {
    const r = document.createElement('div');
    r.className = 'resizer';
    r.id = id;
    return r;
}

// --- 2b. Panel Resizing Logic ---
function initResizers() {
    const resizerLeft = document.getElementById('resizerLeft');
    const resizerRight = document.getElementById('resizerRight');
    const leftPanel = document.getElementById('leftPanel');
    const rightPanel = document.getElementById('rightPanel');
    const container = document.querySelector('.main-content');

    if (!resizerLeft || !resizerRight || !leftPanel || !rightPanel) return;

    // Helper for resize events
    const createResizeHandler = (resizer, panel, isLeft) => {
        let startX, startWidth;

        const onMouseDown = (e) => {
            startX = e.clientX;
            startWidth = parseInt(document.defaultView.getComputedStyle(panel).width, 10);
            document.documentElement.addEventListener('mousemove', onMouseMove, false);
            document.documentElement.addEventListener('mouseup', onMouseUp, false);
            resizer.classList.add('active');
            document.body.style.cursor = 'col-resize';
        };

        const onMouseMove = (e) => {
            const dx = e.clientX - startX;
            const newWidth = isLeft ? startWidth + dx : startWidth - dx;

            // Min/Max constraints
            if (newWidth > 150 && newWidth < (container.clientWidth - 400)) {
                panel.style.width = `${newWidth}px`;
                panel.style.flex = 'none'; // Disable flex growth to respect pixel width
            }
        };

        const onMouseUp = () => {
            document.documentElement.removeEventListener('mousemove', onMouseMove, false);
            document.documentElement.removeEventListener('mouseup', onMouseUp, false);
            resizer.classList.remove('active');
            document.body.style.cursor = '';

            // Trigger 3D resize if needed
            window.dispatchEvent(new Event('resize'));
        };

        resizer.addEventListener('mousedown', onMouseDown, false);
    };

    createResizeHandler(resizerLeft, leftPanel, true);
    createResizeHandler(resizerRight, rightPanel, false);
}

// --- 3. Mermaid Diagram Renderers ---

async function renderMermaid(container, definition) {
    if (!container) return;
    container.innerHTML = `<div class="mermaid">${definition.trim()}</div>`;

    if (!window.mermaid) {
        // Load Mermaid on demand if missing
        await loadMermaid();
    }

    try {
        window.mermaid.initialize({ startOnLoad: false, theme: 'dark' });
        await window.mermaid.run({ nodes: container.querySelectorAll('.mermaid') });
    } catch (e) {
        console.error("Mermaid Render Error:", e);
        container.innerHTML += `<div style="color:red; font-size:10px;">Render Error: ${e.message}</div>`;
    }
}

function loadMermaid() {
    return new Promise(resolve => {
        const script = document.createElement('script');
        script.src = "https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js";
        script.onload = resolve;
        document.head.appendChild(script);
    });
}


// --- 4. Topological Views ---

function initServicesView() {
    const container = document.getElementById('view-services');
    if (!container) return;

    // Prevent re-render if populated
    if (viewers.services && container.childElementCount > 0) return;

    const graphDef = `graph TD
    subgraph Agents["AI Agent Layer"]
        GEN[Genesis]
        SER[Serena]
        UI_A[Interaction]
    end
    subgraph Core["Core Intelligence"]
        LLM[LLM Gateway]
        COG[Cognitive Tick]
        GEO[Geometry Kernel]
    end
    subgraph Memory["Memory Layer"]
        REDIS[Redis]
        NEO4J[Neo4j]
        CHROMA[Chroma]
        PGSQL[Postgres]
    end
    
    GEN --> LLM & REDIS & NEO4J
    SER --> LLM & REDIS & LOKI
    UI_A --> GEN & SER
    LLM --> CHROMA
    COG --> GEO & REDIS
    GEO --> REDIS
    
    style GEO fill:#ffd700,stroke:#333
    style GEN fill:#007aff
    style SER fill:#af52de`;

    renderMermaid(container, graphDef);
    viewers.services = true;
}

function initWorkflowsView() {
    const container = document.getElementById('view-workflows');
    if (!container) return;
    if (viewers.workflows && container.childElementCount > 0) return;

    const graphDef = `sequenceDiagram
    participant U as User
    participant UI as Interface
    participant GEN as Genesis
    participant SER as Serena
    participant LLM as Models
    
    U->>UI: Request
    UI->>GEN: Objective
    GEN->>LLM: Plan
    GEN->>SER: Coding Task
    SER->>LLM: Generate
    SER->>GEN: Result
    GEN->>UI: Success`;

    renderMermaid(container, graphDef);
    viewers.workflows = true;
}

function initLivingSystemView() {
    const container = document.getElementById('view-living');
    if (!container) return;
    if (viewers.living && container.childElementCount > 0) return;

    const graphDef = `graph TD
    subgraph Mind["The Living Mind"]
        Input -->|Vector| Manifold
        Manifold -->|Resonate| Geometry
        Geometry -->|Dream| Consolidate
    end
    style Manifold fill:#220033
    style Geometry fill:#ff9500`;

    renderMermaid(container, graphDef);
    viewers.living = true;
}

// --- 5. Bootstrapper ---
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initSystemViews);
} else {
    // If loaded late/dynamically
    initSystemViews();
}
