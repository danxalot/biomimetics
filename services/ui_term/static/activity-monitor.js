/**
 * ARCA Activity Monitor - LED Indicators & System Metrics
 * Real-time activity visualization with LED-style status indicators
 */

// LED Configuration
const LED_CONFIG = {
    thresholds: {
        green: { max: 50 },   // 0-50%: green (healthy)
        amber: { max: 80 },   // 50-80%: amber (warning)
        red: { min: 80 }      // 80-100%: red (critical)
    },
    refreshRate: 2000,  // 2 second refresh
    indicators: [
        { id: 'led-cpu', label: 'CPU', icon: '💻' },
        { id: 'led-mem', label: 'MEM', icon: '🧠' },
        { id: 'led-disk', label: 'DISK', icon: '💾' },
        { id: 'led-inference', label: 'INF', icon: '🤖' },
        { id: 'led-embedding', label: 'EMB', icon: '📊' },
        { id: 'led-vision', label: 'VIS', icon: '👁️' },
        { id: 'led-geometry', label: 'GEO', icon: '📐' },
        { id: 'led-hamiltonian', label: 'HAM', icon: '⚛️' },
        { id: 'led-coherence', label: 'COH', icon: '🌊' },
        { id: 'led-pulse', label: 'PLS', icon: '💓' },
        { id: 'led-entropy', label: 'ENT', icon: '🌀' }
    ]
};

// Current metrics state
let currentMetrics = {
    cpu: 0,
    memory: 0,
    disk: 0,
    inference: { active: false, tps: 0, buffer: 0 },
    embedding: { active: false, tps: 0, buffer: 0 },
    vision: { active: false, tps: 0, buffer: 0 },
    geometry: { active: false },
    neural_vitals: { mamba_pulse_l2: 0, kuramoto_coherence: 0, hamiltonian_energy: 0, gate_entropy: 0, expert_load: [] }
};

// Initialize activity monitor
function initActivityMonitor() {
    createLEDPanel();
    startMetricsPolling();
}

// Create LED indicator panel in header
function createLEDPanel() {
    const header = document.querySelector('.terminal-header');
    if (!header) return;

    const ledPanel = document.createElement('div');
    ledPanel.className = 'led-panel';
    ledPanel.innerHTML = `
        <div class="led-container">
            ${LED_CONFIG.indicators.map(ind => `
                <div class="led-indicator" id="${ind.id}" title="${ind.label}">
                    <div class="led-bulb"></div>
                    <span class="led-label">${ind.icon}</span>
                    <span class="led-value" id="${ind.id}-value">--</span>
                </div>
            `).join('')}
        </div>
    `;

    // Insert before header controls
    const headerControls = header.querySelector('.header-controls');
    if (headerControls) {
        header.insertBefore(ledPanel, headerControls);
    } else {
        header.appendChild(ledPanel);
    }

    injectLEDStyles();
}

// Inject LED CSS styles
function injectLEDStyles() {
    const style = document.createElement('style');
    style.textContent = `
        .led-panel {
            display: flex;
            align-items: center;
            padding: 0 12px;
        }
        
        .led-container {
            display: flex;
            gap: 8px;
        }
        
        .led-indicator {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            min-width: 32px;
        }
        
        .led-bulb {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #333;
            box-shadow: inset 0 -2px 4px rgba(0,0,0,0.5);
            transition: all 0.3s ease;
        }
        
        .led-bulb.green {
            background: radial-gradient(circle at 30% 30%, #7fff7f, #00cc00);
            box-shadow: 0 0 8px #00ff00;
        }
        
        .led-bulb.amber {
            background: radial-gradient(circle at 30% 30%, #ffcc7f, #ff9900);
            box-shadow: 0 0 8px #ff9900;
        }
        
        .led-bulb.red {
            background: radial-gradient(circle at 30% 30%, #ff7f7f, #cc0000);
            box-shadow: 0 0 8px #ff0000;
            animation: pulse-red 1s infinite;
        }
        
        @keyframes pulse-red {
            0%, 100% { box-shadow: 0 0 8px #ff0000; }
            50% { box-shadow: 0 0 16px #ff0000; }
        }
        
        .led-label {
            font-size: 10px;
            color: #888;
        }
        
        .led-value {
            font-size: 10px;
            color: #4ec9b0;
            font-family: monospace;
            min-width: 35px;
            text-align: center;
            margin-top: 2px;
        }

        /* Unified View Overlay */
        .query-bar {
            display: flex;
            background: rgba(30, 30, 30, 0.9);
            border: 1px solid #4ec9b0;
            padding: 10px;
            border-radius: 4px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .prompt-char { color: #4ec9b0; margin-right: 10px; font-weight: bold; }
        #agent-query-input {
            flex: 1;
            background: transparent;
            border: none;
            color: #fff;
            font-family: 'Monaco', monospace;
            outline: none;
        }
        #agent-query-btn {
            background: #4ec9b0;
            border: none;
            color: #000;
            font-weight: bold;
            padding: 2px 8px;
            cursor: pointer;
        }
        .agent-response {
            background: rgba(0,0,0,0.8);
            color: #aaa;
            padding: 8px;
            border-radius: 4px;
            font-size: 12px;
            font-family: 'Monaco', monospace;
            min-height: 20px;
        }
    `;
    document.head.appendChild(style);
}

// Get LED color based on value
function getLEDColor(value) {
    if (value >= LED_CONFIG.thresholds.red.min) return 'red';
    if (value >= LED_CONFIG.thresholds.green.max) return 'amber';
    return 'green';
}

// Update LED indicators
function updateLEDs(metrics) {
    function updateLED(id, value, displayValue) {
        const led = document.getElementById(id);
        if (!led) return;

        const bulb = led.querySelector('.led-bulb');
        const valueEl = led.querySelector(`#${id}-value`);

        bulb.className = 'led-bulb ' + getLEDColor(value);
        if (valueEl) valueEl.textContent = displayValue;
    }

    function updateModelLED(id, model) {
        const led = document.getElementById(id);
        if (!led) return;

        const bulb = led.querySelector('.led-bulb');
        const valueEl = led.querySelector(`#${id}-value`);

        if (model && model.active) {
            // Buffer-based color (1-3 capacity)
            const bufferPercent = Math.min((model.buffer || 0) * 33, 100);
            bulb.className = 'led-bulb ' + getLEDColor(bufferPercent);
            if (valueEl) valueEl.textContent = model.tps ? `${model.tps}t/s` : 'ACTV';
        } else {
            bulb.className = 'led-bulb';
            if (valueEl) valueEl.textContent = '--';
        }
    }

    // System metrics
    updateLED('led-cpu', metrics.cpu, `${metrics.cpu.toFixed(1)}%`);
    updateLED('led-mem', metrics.memory, `${metrics.memory.toFixed(1)}%`);
    updateLED('led-disk', metrics.disk, `${metrics.disk.toFixed(1)}%`);

    // Core inference components
    updateModelLED('led-inference', metrics.inference);
    updateModelLED('led-embedding', metrics.embedding);
    updateModelLED('led-vision', metrics.vision);
    updateModelLED('led-geometry', metrics.geometry);

    // Neural Vitals
    if (metrics.neural_vitals) {
        const v = metrics.neural_vitals;
        updateLED('led-hamiltonian', v.hamiltonian_energy * 10, v.hamiltonian_energy.toFixed(2));
        updateLED('led-coherence', (1.0 - v.kuramoto_coherence) * 100, v.kuramoto_coherence.toFixed(2));
        updateLED('led-entropy', v.gate_entropy * 50, v.gate_entropy.toFixed(2));
        
        // Pulse gets a special color if active
        const pulse = document.getElementById('led-pulse');
        if (pulse) {
            const bulb = pulse.querySelector('.led-bulb');
            const val = pulse.querySelector('#led-pulse-value');
            if (v.mamba_pulse_l2 > 0.001) {
                bulb.className = 'led-bulb green';
                if (val) val.textContent = v.mamba_pulse_l2.toFixed(3);
            } else {
                bulb.className = 'led-bulb';
                if (val) val.textContent = '--';
            }
        }
    }
}

    // Poll for metrics
    function startMetricsPolling() {
        fetchMetrics();
        setInterval(fetchMetrics, LED_CONFIG.refreshRate);
    }

    async function fetchMetrics() {
        try {
            const response = await fetch('/api/system/metrics');
            if (response.ok) {
                const metrics = await response.json();
                currentMetrics = metrics;
                updateLEDs(metrics);
            }
        } catch (error) {
            console.debug('Metrics fetch failed:', error);
        }
    }

    // Initialize on page load
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initActivityMonitor);
    } else {
        initActivityMonitor();
    }
}
