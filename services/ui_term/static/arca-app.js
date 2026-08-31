/**
 * ARCA Terminal - Puter.js Application
 * Main entry point for the componentized ARCA UI
 */

// Component imports (in Puter.js, these will be handled by the module system)
// For now, assume they're loaded via script tags

const ARCATerminal = {
    // Component instances
    components: {},
    wsManager: null,

    /**
     * Initialize and launch the ARCA Terminal app
     */
    async launch() {
        console.log('🚀 Launching ARCA Terminal...');

        // Create main layout
        this.createLayout();

        // Initialize WebSocket manager
        this.wsManager = wsManager || new WebSocketManager();
        this.wsManager.connect();

        // Initialize components
        this.initializeComponents();

        // Connect components to WebSocket
        this.connectWebSocket();

        // Setup inter-component communication
        this.setupCommunication();

        console.log('✅ ARCA Terminal launched successfully');
    },

    /**
     * Create the main layout structure
     */
    createLayout() {
        const appContainer = document.body;

        appContainer.innerHTML = `
            <div class="arca-terminal">
                <div class="terminal-header">
                    <div class="terminal-title">ARCA Interactive Terminal</div>
                    <div class="user-info">dan@arca</div>
                    <div class="connection-status">
                        <span class="status-dot" id="connectionDot"></span>
                        <span id="connectionStatus">Connecting...</span>
                    </div>
                </div>

                <div class="main-layout">
                    <!-- Left Panel: Library -->
                    <div class="panel panel-left">
                        <div id="library-panel"></div>
                    </div>

                    <!-- Center Panel: Chat -->
                    <div class="panel panel-center">
                        <div id="chat-panel"></div>
                    </div>

                    <!-- Right Panel: Serena -->
                    <div class="panel panel-right">
                        <div id="serena-panel"></div>
                    </div>
                </div>

                <!-- Bottom Panel: Resource Monitor -->
                <div class="panel panel-bottom">
                    <div id="resource-panel"></div>
                </div>

                <!-- Floating Geometry Window (hidden by default) -->
                <div id="geometry-panel" class="hidden"></div>
            </div>
        `;
    },

    /**
     * Initialize all components
     */
    initializeComponents() {
        // Library Browser
        this.components.library = new LibraryBrowser('#library-panel');
        this.components.library.mount();

        // Chat Panel
        this.components.chat = new ChatPanel('#chat-panel');
        this.components.chat.mount();

        // Serena Panel
        this.components.serena = new SerenaPanel('#serena-panel');
        this.components.serena.mount();

        // Resource Monitor
        this.components.resource = new ResourceMonitor('#resource-panel');
        this.components.resource.mount();

        // Geometry Viewer (mounted on demand)
        this.components.geometry = new GeometryViewer('#geometry-panel');
    },

    /**
     * Connect all components to WebSocket manager
     */
    connectWebSocket() {
        Object.values(this.components).forEach(component => {
            if (this.wsManager) {
                this.wsManager.subscribe(component);
            }
        });

        // Update connection status UI
        this.wsManager.subscribe({
            handleMessage: (data) => {
                if (data.type === 'connection') {
                    this.updateConnectionStatus(data.status === 'connected');
                }
            }
        });
    },

    /**
     * Setup inter-component communication
     */
    setupCommunication() {
        // Library -> Document Viewer
        document.addEventListener('file-opened', (e) => {
            console.log('File opened:', e.detail.path);
            // Could open in a new window or panel
        });

        // Geometry viewer launch
        document.addEventListener('launch-geometry', () => {
            this.components.geometry.mount();
            document.querySelector('#geometry-panel').classList.remove('hidden');
        });

        // Geometry viewer close
        document.addEventListener('geometry-closed', () => {
            document.querySelector('#geometry-panel').classList.add('hidden');
        });
    },

    /**
     * Update connection status indicator
     */
    updateConnectionStatus(connected) {
        const dot = document.getElementById('connectionDot');
        const status = document.getElementById('connectionStatus');

        if (dot && status) {
            if (connected) {
                dot.classList.add('connected');
                status.textContent = 'Connected';
            } else {
                dot.classList.remove('connected');
                status.textContent = 'Disconnected';
            }
        }
    },

    /**
     * Cleanup on app close
     */
    cleanup() {
        // Unmount all components
        Object.values(this.components).forEach(component => {
            if (component.unmount) {
                component.unmount();
            }
        });

        // Disconnect WebSocket
        if (this.wsManager) {
            this.wsManager.disconnect();
        }
    }
};

// Puter.js initialization
if (typeof puter !== 'undefined') {
    // Running in Puter.js environment
    puter.on('app.launched', () => {
        ARCATerminal.launch();
    });

    puter.on('app.closing', () => {
        ARCATerminal.cleanup();
    });
} else {
    // Running standalone (development)
    document.addEventListener('DOMContentLoaded', () => {
        ARCATerminal.launch();
    });
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = ARCATerminal;
}
