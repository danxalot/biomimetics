/**
 * ARCA Sci-Fi 3D Dashboard - Tron/Blade Runner Style
 * 
 * Central Geometry Core (gold torus) with silver gyroscope rings,
 * service nodes connected via tubes (red/green/gold) with animated light pulses.
 */

// ===== CONFIGURATION =====
const DASHBOARD_CONFIG = {
    torusRadius: 2.0, // Larger core
    torusTube: 0.5,
    torusYScale: 2.5,
    ringCount: 3,
    ringRadius: 3.5,
    ringTube: 0.05,
    tubeRadius: 0.03,
    tubeSegments: 64,
    pulseSpeed: 0.02,
    colors: {
        gold: 0xffd700,
        goldDark: 0xb8860b,
        silver: 0xc0c0c0,
        red: 0xff3b30,
        green: 0x34c759,
        greenBright: 0x00ff00,
        blue: 0x007aff,
        purple: 0xaf52de,
        cyan: 0x32ade6,
        orange: 0xff9500,
        background: 0x111111
    }
};

const HEALTH_LED_POSITION = { x: 0, y: 3.5, z: 0 };

// ===== SERVICE CLUSTERS =====
// Center is (0,0,0)
const SERVICES = {
    // --- AGENTS (East) ---
    user_interaction: { name: 'User Interaction', pos: { x: 6, y: 1, z: 2 }, color: 0x007aff },
    agent_service: { name: 'Agent Orchestrator', pos: { x: 8, y: 0, z: 0 }, color: 0x007aff },
    genesis: { name: 'Genesis Agent', pos: { x: 10, y: 1, z: 2 }, color: 0x32ade6 },
    serena: { name: 'Serena Agent', pos: { x: 10, y: 1, z: -2 }, color: 0xaf52de },
    mcp_server: { name: 'MCP Server', pos: { x: 8, y: 2, z: 0 }, color: 0xff9500 },

    // --- INTELLIGENCE (North) ---
    llm_gateway: { name: 'LLM Gateway', pos: { x: 0, y: 1, z: -6 }, color: 0xaf52de },
    llama_cpp: { name: 'Native LLM', pos: { x: -2, y: 0, z: -8 }, color: 0x5856d6 },
    llama_vision: { name: 'Vision Server', pos: { x: 2, y: 0, z: -8 }, color: 0x5856d6 },
    embedding: { name: 'Embedding Svc', pos: { x: 0, y: 2, z: -8 }, color: 0x34c759 },
    hse_encoder: { name: 'HSE Encoder', pos: { x: 0, y: 4, z: -6 }, color: 0xff3b30 },
    guardian: { name: 'Guardian', pos: { x: -3, y: 2, z: -5 }, color: 0xff2d55 },

    // --- MEMORY (South) ---
    memory_system: { name: 'Memory System', pos: { x: 0, y: 1, z: 6 }, color: 0x34c759 },
    postgres: { name: 'PostgreSQL', pos: { x: -2, y: 0, z: 8 }, color: 0x34c759 },
    neo4j: { name: 'Neo4j Graph', pos: { x: 2, y: 0, z: 8 }, color: 0xff9500 },
    redis: { name: 'Redis Cache', pos: { x: 0, y: 0, z: 9 }, color: 0xff3b30 },
    conversational_hdc: { name: 'Conv. HDC', pos: { x: 0, y: 3, z: 7 }, color: 0x32ade6 },
    chroma: { name: 'ChromaDB', pos: { x: 4, y: 0, z: 8 }, color: 0x34c759 },

    // --- OPS & INFRA (West) ---
    resource_monitor: { name: 'Res. Monitor', pos: { x: -6, y: 1, z: 2 }, color: 0x8e8e93 },
    docker_helper: { name: 'Docker Helper', pos: { x: -8, y: 0, z: 0 }, color: 0x007aff },
    host_bridge: { name: 'Host Bridge', pos: { x: -10, y: 0, z: 0 }, color: 0xff9500 },
    loki: { name: 'Loki Logging', pos: { x: -6, y: 2, z: -2 }, color: 0xff3b30, isLogDestination: true },
    otel_collector: { name: 'OTel Collector', pos: { x: -8, y: 2, z: -2 }, color: 0x32ade6 },
    grafana: { name: 'Grafana', pos: { x: -10, y: 2, z: -2 }, color: 0xff9500 },

    // --- SPECIAL ---
    // --- SPECIAL ---
    cognitive: { name: 'Cognitive Tick', pos: { x: 3, y: 4, z: 3 }, color: 0xffd700 },
    pythagorus: { name: 'The Mount', pos: { x: -3, y: 5, z: 0 }, color: 0x9370db }
};

// Global State
let dashboardScene = null;
let dashboardCamera = null;
let dashboardRenderer = null;
let dashboardControls = null;
let dashboardActive = false;
let resizeObserver = null;

// Instance Refs
let geometryCore = null;
let silverRings = [];
let serviceNodes = {};
let tubes = [];
let healthLED = null;
let logCenterHub = null;
let promptVisuals = null;
let oracleModel = null;
let pythagorusModel = null;
let documentVisuals = null;

let animationFrameId = null;

// ===== INITIALIZATION =====
function initSciFiDashboard(targetContainer = null) {
    // If no target provided, try the default dynamic overlay
    const container = targetContainer || document.getElementById('dynamicViewContent');
    if (!container) {
        console.error('Dashboard container not found');
        return;
    }

    // Cleanup previous instance if any
    destroySciFiDashboard();

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 500;

    // Scene
    dashboardScene = new THREE.Scene();
    dashboardScene.background = new THREE.Color(DASHBOARD_CONFIG.colors.background);
    dashboardScene.fog = new THREE.Fog(DASHBOARD_CONFIG.colors.background, 20, 60);

    // Camera
    dashboardCamera = new THREE.PerspectiveCamera(60, width / height, 0.1, 100);
    dashboardCamera.position.set(20, 15, 20); // Zoom out for larger cluster
    dashboardCamera.lookAt(0, 0, 0);

    // Renderer
    dashboardRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    dashboardRenderer.setSize(width, height);
    dashboardRenderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    dashboardRenderer.shadowMap.enabled = true;
    container.innerHTML = ''; // Clear container
    container.appendChild(dashboardRenderer.domElement);

    // Resize Observer
    resizeObserver = new ResizeObserver(entries => {
        for (let entry of entries) {
            const w = entry.contentRect.width;
            const h = entry.contentRect.height;
            if (dashboardCamera && dashboardRenderer) {
                dashboardCamera.aspect = w / h;
                dashboardCamera.updateProjectionMatrix();
                dashboardRenderer.setSize(w, h);
            }
        }
    });
    resizeObserver.observe(container);

    // Lighting
    setupLighting();

    // Grid floor
    createGridFloor();

    // Build all components
    createGeometryCore();
    createSilverRings();
    createHealthLED();
    createLogCenterHub();
    createServiceNodes();
    createAllTubes();
    createPromptVisualization();
    createPromptVisualization();
    createDelphiModel();    // New
    createTheorismModel(); // New
    createDocumentModel();  // New
    update3DLayers(); // Apply initial layer state

    // Orbit controls
    if (typeof THREE.OrbitControls !== 'undefined') {
        dashboardControls = new THREE.OrbitControls(dashboardCamera, dashboardRenderer.domElement);
        dashboardControls.enableDamping = true;
        dashboardControls.dampingFactor = 0.05;
        dashboardControls.minDistance = 5;
        dashboardControls.maxDistance = 25;
        dashboardControls.target.set(0, 0, 0);
    }

    // Start animation
    dashboardActive = true;
    animateDashboard();

    // Start health pulse timer
    startHealthPulseTimer();

    console.log('🌟 Sci-Fi Dashboard initialized');
}

function setupLighting() {
    // Ambient
    const ambient = new THREE.AmbientLight(0x1a1a2e, 0.4);
    dashboardScene.add(ambient);

    // Main light
    const mainLight = new THREE.DirectionalLight(0xffeedd, 0.7);
    mainLight.position.set(10, 20, 10);
    mainLight.castShadow = true;
    mainLight.shadow.mapSize.width = 2048;
    mainLight.shadow.mapSize.height = 2048;
    dashboardScene.add(mainLight);

    // Cluster Accents
    // East (Agents) - Blue
    const blueLight = new THREE.PointLight(0x007aff, 0.4, 25);
    blueLight.position.set(10, 5, 0);
    dashboardScene.add(blueLight);

    // West (Ops) - Orange
    const orangeLight = new THREE.PointLight(0xff9500, 0.4, 25);
    orangeLight.position.set(-10, 5, 0);
    dashboardScene.add(orangeLight);

    // North (Intel) - Purple
    const purpleLight = new THREE.PointLight(0xaf52de, 0.4, 25);
    purpleLight.position.set(0, 5, -10);
    dashboardScene.add(purpleLight);

    // South (Mem) - Green
    const greenLight = new THREE.PointLight(0x34c759, 0.4, 25);
    greenLight.position.set(0, 5, 10);
    dashboardScene.add(greenLight);
}

// Main grid
function createGridFloor() {
    const gridHelper = new THREE.GridHelper(60, 60, 0x1a1a3a, 0x0a0a1a);
    gridHelper.position.y = -0.5;
    dashboardScene.add(gridHelper);

    // Secondary finer grid
    const fineGrid = new THREE.GridHelper(60, 120, 0x151530, 0x0a0a15);
    fineGrid.position.y = -0.49;
    dashboardScene.add(fineGrid);
}

// ===== GEOMETRY CORE (Gold Torus) =====
function createGeometryCore() {
    const { torusRadius, torusTube, torusYScale, colors } = DASHBOARD_CONFIG;

    // Create canvas for texture with tick labels
    const canvas = document.createElement('canvas');
    canvas.width = 1024;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    // Gold gradient
    const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    gradient.addColorStop(0, '#d4a520');
    gradient.addColorStop(0.3, '#ffd700');
    gradient.addColorStop(0.5, '#c9a227');
    gradient.addColorStop(0.7, '#ffd700');
    gradient.addColorStop(1, '#d4a520');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;

    // Torus geometry
    const geometry = new THREE.TorusGeometry(torusRadius, torusTube, 32, 100);

    // Gold material
    const material = new THREE.MeshStandardMaterial({
        map: texture,
        metalness: 0.9,
        roughness: 0.2,
        emissive: colors.goldDark,
        emissiveIntensity: 0.2
    });

    geometryCore = new THREE.Mesh(geometry, material);
    geometryCore.scale.y = torusYScale;  // Elongate on Y axis
    geometryCore.rotation.x = Math.PI / 2;  // Stand upright

    // Store texture context for tick updates
    geometryCore.userData.textureCtx = ctx;
    geometryCore.userData.texture = texture;
    geometryCore.userData.canvas = canvas;

    // Inner glow for tick pulse
    const glowGeom = new THREE.TorusGeometry(torusRadius * 0.8, torusTube * 0.5, 16, 50);
    const glowMat = new THREE.MeshBasicMaterial({
        color: 0xffff00,
        transparent: true,
        opacity: 0
    });
    const innerGlow = new THREE.Mesh(glowGeom, glowMat);
    innerGlow.scale.y = torusYScale;
    innerGlow.rotation.x = Math.PI / 2;
    geometryCore.add(innerGlow);
    geometryCore.userData.innerGlow = innerGlow;

    dashboardScene.add(geometryCore);
}

// ===== SILVER GYROSCOPE RINGS =====
function createSilverRings() {
    const { ringRadius, ringTube, colors } = DASHBOARD_CONFIG;

    const ringAngles = [
        { x: 0, y: 0, z: 0 },
        { x: Math.PI / 3, y: 0, z: Math.PI / 4 },
        { x: -Math.PI / 4, y: Math.PI / 3, z: 0 }
    ];

    const material = new THREE.MeshStandardMaterial({
        color: colors.silver,
        metalness: 0.95,
        roughness: 0.1,
        emissive: 0x333344,
        emissiveIntensity: 0.1
    });

    ringAngles.forEach((angles, i) => {
        const radius = ringRadius + (i * 0.3);
        const geometry = new THREE.TorusGeometry(radius, ringTube, 16, 100);
        const ring = new THREE.Mesh(geometry, material.clone());

        ring.rotation.set(angles.x, angles.y, angles.z);
        ring.userData.rotationSpeed = {
            x: 0.002 * (i % 2 === 0 ? 1 : -1),
            y: 0.003 * (i % 2 === 0 ? -1 : 1),
            z: 0.001 * (i % 2 === 0 ? 1 : -1)
        };

        dashboardScene.add(ring);
        silverRings.push(ring);
    });
}

// ===== HEALTH LED =====
function createHealthLED() {
    const geometry = new THREE.SphereGeometry(0.4, 32, 32);
    const material = new THREE.MeshBasicMaterial({
        color: DASHBOARD_CONFIG.colors.greenBright,
        transparent: true,
        opacity: 0.9
    });

    healthLED = new THREE.Mesh(geometry, material);
    healthLED.position.set(HEALTH_LED_POSITION.x, HEALTH_LED_POSITION.y, HEALTH_LED_POSITION.z);

    // Glow effect
    const glowGeom = new THREE.SphereGeometry(0.6, 16, 16);
    const glowMat = new THREE.MeshBasicMaterial({
        color: DASHBOARD_CONFIG.colors.green,
        transparent: true,
        opacity: 0.3
    });
    const glow = new THREE.Mesh(glowGeom, glowMat);
    healthLED.add(glow);

    // Label
    addLabel(healthLED, 'HEALTH', 0.8);

    dashboardScene.add(healthLED);
}

// ===== LOG CENTER HUB =====
function createLogCenterHub() {
    // Central routing point for log tubes
    const geometry = new THREE.OctahedronGeometry(0.3, 0);
    const material = new THREE.MeshBasicMaterial({
        color: DASHBOARD_CONFIG.colors.red,
        transparent: true,
        opacity: 0.7
    });

    logCenterHub = new THREE.Mesh(geometry, material);
    logCenterHub.position.set(0, 2, 0);  // Above the core

    dashboardScene.add(logCenterHub);
}

// ===== SERVICE NODES =====
function createServiceNodes() {
    Object.entries(SERVICES).forEach(([key, config]) => {
        const node = createServiceNode(key, config);
        serviceNodes[key] = node;
        dashboardScene.add(node);
    });
}

function createServiceNode(key, config) {
    const group = new THREE.Group();
    
    // Handle both 'pos' and 'position' property names
    const pos = config.pos || config.position || { x: 0, y: 0, z: 0 };
    group.position.set(pos.x, pos.y, pos.z);

    // Main node (cube with beveled edges effect)
    const geometry = new THREE.BoxGeometry(0.6, 0.6, 0.6);
    const material = new THREE.MeshStandardMaterial({
        color: config.color || 0x888888,
        metalness: 0.7,
        roughness: 0.3,
        emissive: config.color,
        emissiveIntensity: 0.2
    });

    const cube = new THREE.Mesh(geometry, material);
    cube.castShadow = true;
    group.add(cube);

    // Glow ring around node
    const ringGeom = new THREE.TorusGeometry(0.5, 0.02, 8, 32);
    const ringMat = new THREE.MeshBasicMaterial({
        color: config.color,
        transparent: true,
        opacity: 0.5
    });
    const ring = new THREE.Mesh(ringGeom, ringMat);
    ring.rotation.x = Math.PI / 2;
    ring.position.y = -0.35;
    group.add(ring);

    // Error LED (red, small)
    const errorLED = new THREE.Mesh(
        new THREE.SphereGeometry(0.08, 16, 16),
        new THREE.MeshBasicMaterial({ color: 0x330000, transparent: true, opacity: 0.8 })
    );
    errorLED.position.set(0.4, 0.4, 0);
    group.add(errorLED);
    group.userData.errorLED = errorLED;

    // Label
    addLabel(group, config.name, 0.9);

    group.userData.serviceKey = key;
    group.userData.config = config;

    return group;
}

function addLabel(parent, text, yOffset) {
    // Create canvas for text
    const canvas = document.createElement('canvas');
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = 'rgba(0,0,0,0)';
    ctx.fillRect(0, 0, 256, 64);

    ctx.font = 'bold 24px "Courier New", monospace';
    ctx.textAlign = 'center';
    ctx.fillStyle = '#ffffff';
    ctx.fillText(text, 128, 40);

    const texture = new THREE.CanvasTexture(canvas);
    const material = new THREE.SpriteMaterial({ map: texture, transparent: true });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(2, 0.5, 1);
    sprite.position.y = yOffset;

    parent.add(sprite);
}

// ===== TUBE CONNECTIONS =====
function createAllTubes() {
    Object.entries(SERVICES).forEach(([key, config]) => {
        if (config.isLogDestination) return;  // Loki doesn't send, only receives

        // Handle both 'pos' and 'position' property names
        const pos = config.pos || config.position || { x: 0, y: 0, z: 0 };
        const servicePos = new THREE.Vector3(pos.x, pos.y, pos.z);

        // 1. Gold tube to Geometry Core
        createTube(
            servicePos,
            new THREE.Vector3(0, 0, 0),
            DASHBOARD_CONFIG.colors.gold,
            'gold',
            key
        );

        // 2. Green tube to Health LED
        createTube(
            servicePos,
            new THREE.Vector3(HEALTH_LED_POSITION.x, HEALTH_LED_POSITION.y, HEALTH_LED_POSITION.z),
            DASHBOARD_CONFIG.colors.green,
            'health',
            key
        );

        // 3. Red tube to Log Center Hub (then to Loki)
        createTube(
            servicePos,
            new THREE.Vector3(0, 2, 0),  // Log center hub
            DASHBOARD_CONFIG.colors.red,
            'log',
            key
        );
    });

    // Log hub to Loki tube
    const lokiConfig = SERVICES.loki;
    const lokiPos = lokiConfig.pos || lokiConfig.position || { x: 0, y: 0, z: 0 };
    createTube(
        new THREE.Vector3(0, 2, 0),
        new THREE.Vector3(lokiPos.x, lokiPos.y, lokiPos.z),
        DASHBOARD_CONFIG.colors.red,
        'log-main',
        'hub'
    );
}

function createTube(start, end, color, type, sourceKey) {
    // Create curved path
    const midY = Math.max(start.y, end.y) + 1;
    const mid = new THREE.Vector3(
        (start.x + end.x) / 2,
        midY,
        (start.z + end.z) / 2
    );

    const curve = new THREE.QuadraticBezierCurve3(start, mid, end);

    // Tube geometry
    const geometry = new THREE.TubeGeometry(curve, DASHBOARD_CONFIG.tubeSegments, DASHBOARD_CONFIG.tubeRadius, 8, false);
    const material = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.4
    });

    const tube = new THREE.Mesh(geometry, material);
    tube.userData.curve = curve;
    tube.userData.type = type;
    tube.userData.sourceKey = sourceKey;
    tube.userData.color = color;

    dashboardScene.add(tube);
    tubes.push(tube);

    return tube;
}

// ===== LIGHT PULSES =====
function createPulse(tube, color, intensity = 1) {
    const geometry = new THREE.SphereGeometry(DASHBOARD_CONFIG.pulseSize * intensity, 16, 16);
    const material = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.9
    });

    const pulse = new THREE.Mesh(geometry, material);

    // Add glow
    const glowGeom = new THREE.SphereGeometry(DASHBOARD_CONFIG.pulseSize * intensity * 2, 8, 8);
    const glowMat = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.3
    });
    const glow = new THREE.Mesh(glowGeom, glowMat);
    pulse.add(glow);

    // Point light for extra glow
    const light = new THREE.PointLight(color, 0.5, 2);
    pulse.add(light);

    pulse.userData.progress = 0;
    pulse.userData.tube = tube;
    pulse.userData.curve = tube.userData.curve;
    pulse.userData.speed = DASHBOARD_CONFIG.pulseSpeed * (0.8 + Math.random() * 0.4);

    dashboardScene.add(pulse);
    pulses.push(pulse);

    return pulse;
}

// ===== ANIMATION =====
function animateDashboard() {
    if (!dashboardActive) return;
    animationFrameId = requestAnimationFrame(animateDashboard);

    // Update controls
    if (dashboardControls) {
        dashboardControls.update();
    }

    // Rotate silver rings (gyroscope effect)
    silverRings.forEach(ring => {
        ring.rotation.x += ring.userData.rotationSpeed.x;
        ring.rotation.y += ring.userData.rotationSpeed.y;
        ring.rotation.z += ring.userData.rotationSpeed.z;
    });

    // Rotate torus (outward roll)
    if (geometryCore) {
        geometryCore.rotation.z += 0.005;

        // Scroll texture
        if (geometryCore.userData.texture) {
            geometryCore.userData.texture.offset.x += 0.001;
        }
    }

    // Animate Oracle
    if (oracleModel && oracleModel.visible) {
        oracleModel.rotation.x += oracleModel.userData.rotationSpeed.x;
        oracleModel.rotation.y += oracleModel.userData.rotationSpeed.y;
        // Pulse scale
        const scale = 1 + Math.sin(Date.now() * 0.002) * 0.05;
        oracleModel.scale.set(scale, scale, scale);
    }

    // Animate The Mount
    if (pythagorusModel && pythagorusModel.visible) {
        pythagorusModel.rotation.x -= 0.01;
        pythagorusModel.rotation.z += 0.01;
        const scale = 1 + Math.cos(Date.now() * 0.003) * 0.05;
        pythagorusModel.scale.set(scale, scale, scale);
    }

    // Animate Documents (Float)
    if (documentVisuals && documentVisuals.visible) {
        documentVisuals.rotation.y -= 0.005;
        documentVisuals.children.forEach((shard, i) => {
            if (shard.type === 'Mesh') {
                shard.rotation.x += 0.01;
                shard.position.y += Math.sin(Date.now() * 0.001 + i) * 0.002;
            }
        });
    }

    // Animate pulses
    animatePulses();

    // Render
    dashboardRenderer.render(dashboardScene, dashboardCamera);
}

function animatePulses() {
    for (let i = pulses.length - 1; i >= 0; i--) {
        const pulse = pulses[i];
        pulse.userData.progress += pulse.userData.speed;

        if (pulse.userData.progress >= 1) {
            // Pulse reached destination - remove it
            dashboardScene.remove(pulse);
            pulses.splice(i, 1);
        } else {
            // Update position along curve
            const pos = pulse.userData.curve.getPointAt(pulse.userData.progress);
            pulse.position.copy(pos);

            // Fade out near end
            if (pulse.userData.progress > 0.8) {
                pulse.material.opacity = (1 - pulse.userData.progress) * 4.5;
            }
        }
    }
}

// ===== EVENT TRIGGERS =====

// Health pulse every second (async per service)
function startHealthPulseTimer() {
    setInterval(() => {
        if (!dashboardActive) return;

        // Random service sends health pulse
        const serviceKeys = Object.keys(SERVICES).filter(k => !SERVICES[k].isLogDestination);
        const randomService = serviceKeys[Math.floor(Math.random() * serviceKeys.length)];

        triggerHealthPulse(randomService);
    }, 1000);
}

function triggerHealthPulse(serviceKey) {
    const tube = tubes.find(t => t.userData.sourceKey === serviceKey && t.userData.type === 'health');
    if (tube) {
        createPulse(tube, DASHBOARD_CONFIG.colors.greenBright);
    }
}

function triggerLogPulse(serviceKey) {
    // Service to hub
    const tube = tubes.find(t => t.userData.sourceKey === serviceKey && t.userData.type === 'log');
    if (tube) {
        createPulse(tube, DASHBOARD_CONFIG.colors.redBright);
    }

    // Hub to Loki (slight delay for visual effect)
    setTimeout(() => {
        const hubTube = tubes.find(t => t.userData.sourceKey === 'hub' && t.userData.type === 'log-main');
        if (hubTube) {
            createPulse(hubTube, DASHBOARD_CONFIG.colors.redBright);
        }
    }, 300);
}

function triggerCorePulse(serviceKey) {
    const tube = tubes.find(t => t.userData.sourceKey === serviceKey && t.userData.type === 'gold');
    if (tube) {
        createPulse(tube, DASHBOARD_CONFIG.colors.gold, 1.2);
    }
}

function triggerTickPulse(tickLabel) {
    if (!geometryCore || !geometryCore.userData.innerGlow) return;

    const glow = geometryCore.userData.innerGlow;

    // Flash yellow
    glow.material.opacity = 0.8;
    glow.material.color.setHex(0xffff00);

    // Fade out
    const fadeOut = () => {
        if (glow.material.opacity > 0) {
            glow.material.opacity -= 0.02;
            requestAnimationFrame(fadeOut);
        }
    };
    fadeOut();

    // Update texture with tick label
    if (geometryCore.userData.textureCtx) {
        updateTorusLabel(tickLabel);
    }

    console.log(`⚡ Tick pulse: ${tickLabel}`);
}

function updateTorusLabel(label) {
    const ctx = geometryCore.userData.textureCtx;
    const canvas = geometryCore.userData.canvas;

    // Redraw gold gradient
    const gradient = ctx.createLinearGradient(0, 0, canvas.width, canvas.height);
    gradient.addColorStop(0, '#d4a520');
    gradient.addColorStop(0.3, '#ffd700');
    gradient.addColorStop(0.5, '#c9a227');
    gradient.addColorStop(0.7, '#ffd700');
    gradient.addColorStop(1, '#d4a520');

    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw label
    if (label) {
        ctx.font = 'bold 28px "Courier New", monospace';
        ctx.textAlign = 'center';
        ctx.fillStyle = 'rgba(80, 50, 10, 0.6)';

        const textWidth = ctx.measureText(label).width + 30;
        const repeats = Math.ceil(canvas.width / textWidth) + 1;

        for (let i = 0; i < repeats; i++) {
            const x = (i * textWidth) + textWidth / 2;
            ctx.fillText(label, x, canvas.height * 0.4);
            ctx.fillText(label, x + textWidth / 2, canvas.height * 0.7);
        }
    }

    geometryCore.userData.texture.needsUpdate = true;
}

function setServiceError(serviceKey, hasError) {
    const node = serviceNodes[serviceKey];
    if (node && node.userData.errorLED) {
        node.userData.errorLED.material.color.setHex(hasError ? 0xff0000 : 0x330000);
        node.userData.errorLED.material.opacity = hasError ? 1 : 0.3;
    }
}

// ===== CLEANUP =====
function destroySciFiDashboard() {
    dashboardActive = false;

    if (animationFrameId) {
        cancelAnimationFrame(animationFrameId);
    }

    // Clear resize observer
    if (resizeObserver) {
        resizeObserver.disconnect();
        resizeObserver = null;
    }

    if (dashboardRenderer) {
        dashboardRenderer.dispose();
    }

    // Clear references
    dashboardScene = null;
    dashboardCamera = null;
    dashboardRenderer = null;
    dashboardControls = null;
    geometryCore = null;
    silverRings = [];
    serviceNodes = {};
    tubes = [];
    pulses = [];
    healthLED = null;
    logCenterHub = null;
    healthLED = null;
    logCenterHub = null;
    oracleModel = null;
    pythagorusModel = null;
    documentVisuals = null;

    // Clear DOM if we created it
    // (Optional, user might prefer to keep container structure)

    console.log('🌟 Sci-Fi Dashboard destroyed');
}

// ===== TOGGLE FUNCTION =====
function toggleSciFiDashboard() {
    const pane = document.getElementById('dynamicViewPane');
    const title = document.getElementById('dynamicViewTitle');

    if (pane.classList.contains('hidden')) {
        pane.classList.remove('hidden');
        title.textContent = "ARCA System Core - Geometry Kernel";
        geometryActive = true;
        setTimeout(initSciFiDashboard, 100);
    } else if (dashboardActive) {
        destroySciFiDashboard();
        pane.classList.add('hidden');
        document.getElementById('dynamicViewContent').innerHTML = '';
        geometryActive = false;
    }
}

// ===== PROMPT VISUALIZATION (New Layer) =====
function createPromptVisualization() {
    promptVisuals = new THREE.Group();

    // Represents the "User Vector" entering the system
    const dir = new THREE.Vector3(0, -1, 0.5).normalize();
    const length = 5;
    const hex = 0xff00ff; // Magenta for User Intent

    const arrowHelper = new THREE.ArrowHelper(dir, new THREE.Vector3(0, 4, -2), length, hex, 1, 0.5);
    promptVisuals.add(arrowHelper);

    // Text Label
    const label = addLabel(promptVisuals, "USER INTENT", 4.5);

    // Orbiting "Context" Particles around the arrow
    const particleCount = 20;
    const particleGeo = new THREE.BufferGeometry();
    const positions = new Float32Array(particleCount * 3);
    for (let i = 0; i < particleCount; i++) {
        positions[i * 3] = (Math.random() - 0.5) * 2;
        positions[i * 3 + 1] = 4 + (Math.random() - 0.5) * 2;
        positions[i * 3 + 2] = -2 + (Math.random() - 0.5) * 2;
    }
    particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    const particleMat = new THREE.PointsMaterial({ color: 0xffffff, size: 0.1 });
    const particles = new THREE.Points(particleGeo, particleMat);
    promptVisuals.add(particles);

    dashboardScene.add(promptVisuals);
}

// ===== ORACLE MODEL (Cyan Icosahedron) =====
function createDelphiModel() {
    // Represents the "Oracle" / Learning Engine
    // Position: Floating high above the core
    const geometry = new THREE.IcosahedronGeometry(0.8, 0); // Low poly look
    const material = new THREE.MeshStandardMaterial({
        color: 0x00ffff, // Cyan
        emissive: 0x0088aa,
        emissiveIntensity: 0.6,
        metalness: 0.9,
        roughness: 0.1,
        transparent: true,
        opacity: 0.9,
        wireframe: false
    });

    oracleModel = new THREE.Mesh(geometry, material);
    oracleModel.position.set(0, 5, 0);

    // Add wireframe overlay for tech look
    const wireGeo = new THREE.WireframeGeometry(geometry);
    const wireMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
    const wireframe = new THREE.LineSegments(wireGeo, wireMat);
    oracleModel.add(wireframe);

    // Label
    addLabel(oracleModel, "PYTHIA", 1.2);

    // Gentle rotation animation is handled in animateDashboard (or we add it here as property)
    oracleModel.userData.rotationSpeed = { x: 0.01, y: 0.02 };

    dashboardScene.add(oracleModel);
}

// ===== THE MOUNT MODEL (Purple Dodecahedron) =====
function createTheorismModel() {
    // Represents "The Mount" / Geometry Logic
    // Position: Floating opposite Oracle
    const geometry = new THREE.DodecahedronGeometry(0.8, 0);
    const material = new THREE.MeshStandardMaterial({
        color: 0x9370db, // Medium Purple
        emissive: 0x4b0082,
        emissiveIntensity: 0.6,
        metalness: 0.9,
        roughness: 0.1,
        transparent: true,
        opacity: 0.9,
        wireframe: false
    });

    pythagorusModel = new THREE.Mesh(geometry, material);
    pythagorusModel.position.set(-3, 5, 0);

    // Add wireframe overlay
    const wireGeo = new THREE.WireframeGeometry(geometry);
    const wireMat = new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
    const wireframe = new THREE.LineSegments(wireGeo, wireMat);
    pythagorusModel.add(wireframe);

    // Label
    addLabel(pythagorusModel, "THE MOUNT", 1.2);

    dashboardScene.add(pythagorusModel);
}

// ===== DOCUMENT MODEL (Floating Data Shards) =====
function createDocumentModel() {
    documentVisuals = new THREE.Group();
    // Position near Embedding Service
    const embeddingConfig = SERVICES.embedding;
    const embeddingPos = embeddingConfig.pos || embeddingConfig.position || { x: 0, y: 0, z: 0 };
    documentVisuals.position.set(embeddingPos.x, embeddingPos.y + 2, embeddingPos.z);

    const shardCount = 15;
    const shardGeo = new THREE.PlaneGeometry(0.3, 0.4);
    const shardMat = new THREE.MeshBasicMaterial({
        color: 0x00ff00, // Matrix Green
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.6
    });

    for (let i = 0; i < shardCount; i++) {
        const shard = new THREE.Mesh(shardGeo, shardMat);
        // Random spread
        shard.position.set(
            (Math.random() - 0.5) * 2,
            (Math.random() - 0.5) * 2,
            (Math.random() - 0.5) * 2
        );
        shard.rotation.set(
            Math.random() * Math.PI,
            Math.random() * Math.PI,
            Math.random() * Math.PI
        );
        documentVisuals.add(shard);
    }

    addLabel(documentVisuals, "KNOWLEDGE BASE", 1.5);

    dashboardScene.add(documentVisuals);
}

// ===== DOCKING & LAYERS =====
function dock3DViewDown() {
    const mainContainer = document.getElementById('dynamicViewContent');
    const docContainer = document.getElementById('docContent');
    const docViewer = document.getElementById('docViewer');
    const title = document.getElementById('docTitle');

    if (!dashboardRenderer || !dashboardRenderer.domElement) return;

    if (!isDocked) {
        // Dock to Bottom
        console.log("Docking 3D View Down...");
        docViewer.classList.remove('collapsed', 'hidden');
        docViewer.classList.add('has-3d-view');
        title.textContent = "Geometric Kernel (Docked)";

        // Move Canvas
        docContainer.innerHTML = '';
        docContainer.appendChild(dashboardRenderer.domElement);
        
        // Force canvas to fill container with no gaps
        dashboardRenderer.domElement.style.width = '100%';
        dashboardRenderer.domElement.style.height = '100%';
        dashboardRenderer.domElement.style.display = 'block';

        // Resize with delay to ensure layout is complete
        setTimeout(() => {
            const width = docContainer.clientWidth || window.innerWidth - 100;
            const height = docContainer.clientHeight || 400;
            dashboardCamera.aspect = width / height;
            dashboardCamera.updateProjectionMatrix();
            dashboardRenderer.setSize(width, height, false);
        }, 100);

        // Close Overlay but keep state active
        document.getElementById('dynamicViewPane').classList.add('hidden');
        isDocked = true;

        // Watch for resizing and adjust canvas accordingly
        const resizeObserver = new ResizeObserver(() => {
            const width = docContainer.clientWidth;
            const height = docContainer.clientHeight;
            if (width > 0 && height > 0) {
                dashboardCamera.aspect = width / height;
                dashboardCamera.updateProjectionMatrix();
                dashboardRenderer.setSize(width, height, false);
            }
        });
        resizeObserver.observe(docContainer);

    } else {
        // Undock (Restore to Overlay)
        // ... (Optional: For now, clicking "Dock" again could revert, or we use a separate "Undock" button in the bottom panel)
        // Implementation for undocking can be added if requested.
    }
}

function update3DLayers() {
    const showPrompt = document.getElementById('layerPrompt')?.checked ?? true;
    const showSystem = document.getElementById('layerSystem')?.checked ?? true;
    const showConcept = document.getElementById('layerConcept')?.checked ?? true;
    const showOracle = document.getElementById('layerOracle')?.checked ?? true;
    const showKnowledge = document.getElementById('layerKnowledge')?.checked ?? true;

    if (promptVisuals) promptVisuals.visible = showPrompt;
    if (promptVisuals) promptVisuals.visible = showPrompt;
    if (oracleModel) oracleModel.visible = showOracle;
    if (pythagorusModel) pythagorusModel.visible = showOracle; // Linked to Oracle toggle for now or add new one
    if (documentVisuals) documentVisuals.visible = showKnowledge;

    if (serviceNodes) {
        Object.values(serviceNodes).forEach(node => node.visible = showSystem);
    }
    // Also tubes
    tubes.forEach(tube => tube.visible = showSystem);

    if (geometryCore) geometryCore.visible = showConcept;
    if (silverRings) silverRings.forEach(r => r.visible = showConcept);
}


// Export for use in index.html
window.initSciFiDashboard = initSciFiDashboard;
window.destroySciFiDashboard = destroySciFiDashboard;
window.toggleSciFiDashboard = toggleSciFiDashboard;
window.triggerTickPulse = triggerTickPulse;
window.triggerLogPulse = triggerLogPulse;
window.triggerCorePulse = triggerCorePulse;
window.triggerHealthPulse = triggerHealthPulse;
window.setServiceError = setServiceError;
window.dock3DViewDown = dock3DViewDown;
window.update3DLayers = update3DLayers;
