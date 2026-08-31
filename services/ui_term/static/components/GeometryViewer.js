/**
 * GeometryViewer - 3D Geometry Kernel Visualization Component
 * FIXED: System = live stream, Subject = static snapshot (was reversed)
 */
class GeometryViewer extends BaseComponent {
    constructor(containerId = '#geometry-panel') {
        super(containerId);
        this.state = {
            mode: 'system', // 'system' or 'subject'
            isActive: false
        };

        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.points = [];
        this.attractors = [];
        this.animationFrame = null;
    }

    template() {
        return `
            <div class="geometry-container">
                <div class="geometry-header">
                    <span>Geometry Kernel - ${this.state.mode === 'system' ? 'System View' : 'Subject Focus'}</span>
                    <div class="geometry-controls">
                        <button class="btn-tiny" id="toggleMode">
                            Switch to ${this.state.mode === 'system' ? 'Subject' : 'System'}
                        </button>
                        <button class="btn-tiny" id="closeGeometry">×</button>
                    </div>
                </div>
                
                <div class="geometry-canvas" id="geometryCanvas"></div>
                
                <div class="geometry-info">
                    <div class="info-item">
                        <span>Mode:</span>
                        <span>${this.state.mode === 'system' ? 'Live Stream' : 'Static Snapshot'}</span>
                    </div>
                    <div class="info-item">
                        <span>Points:</span>
                        <span id="pointCount">0</span>
                    </div>
                </div>
            </div>
        `;
    }

    attachEventListeners() {
        const toggleBtn = this.container.querySelector('#toggleMode');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggleMode());
        }

        const closeBtn = this.container.querySelector('#closeGeometry');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.close());
        }
    }

    onMounted() {
        this.initThreeJS();
        if (this.state.mode === 'system') {
            this.startLiveStream();
        } else {
            this.captureSnapshot();
        }
    }

    onUnmounted() {
        this.stopAnimation();
        if (this.renderer) {
            this.renderer.dispose();
        }
    }

    initThreeJS() {
        const canvas = this.container.querySelector('#geometryCanvas');
        if (!canvas) return;

        // Scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x1e1e1e);

        // Camera
        this.camera = new THREE.PerspectiveCamera(
            75,
            canvas.clientWidth / canvas.clientHeight,
            0.1,
            1000
        );
        this.camera.position.z = 5;

        // Renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);
        canvas.appendChild(this.renderer.domElement);

        // Lighting
        const light = new THREE.PointLight(0xffffff, 1, 100);
        light.position.set(0, 0, 10);
        this.scene.add(light);

        // Ambient light
        const ambientLight = new THREE.AmbientLight(0x404040);
        this.scene.add(ambientLight);
    }

    toggleMode() {
        this.state.mode = this.state.mode === 'system' ? 'subject' : 'system';

        if (this.state.mode === 'system') {
            this.startLiveStream();
        } else {
            this.stopAnimation();
            this.captureSnapshot();
        }

        this.render();
        this.attachEventListeners();
    }

    startLiveStream() {
        // FIXED: System mode shows LIVE animated stream
        this.stopAnimation();

        // Request live data from geometry kernel
        if (wsManager) {
            wsManager.send({
                type: 'geometry_subscribe',
                mode: 'system'
            });
        }

        // Start animation loop
        this.animate();
    }

    captureSnapshot() {
        // FIXED: Subject mode shows STATIC snapshot
        this.stopAnimation();

        // Request single snapshot
        if (wsManager) {
            wsManager.send({
                type: 'geometry_snapshot',
                mode: 'subject'
            });
        }

        // Render once
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }

    animate() {
        this.animationFrame = requestAnimationFrame(() => this.animate());

        // Update points (decay, movement)
        this.updatePoints();

        // Render
        if (this.renderer && this.scene && this.camera) {
            this.renderer.render(this.scene, this.camera);
        }
    }

    stopAnimation() {
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }
    }

    updatePoints() {
        this.points.forEach(point => {
            // Decay alpha
            if (point.material.opacity > 0) {
                point.material.opacity *= 0.98;
            }

            // Move toward attractors
            this.attractors.forEach(attractor => {
                const dir = new THREE.Vector3()
                    .subVectors(attractor.position, point.position)
                    .normalize()
                    .multiplyScalar(0.01);
                point.position.add(dir);
            });
        });

        // Update point count display
        const countEl = this.container.querySelector('#pointCount');
        if (countEl) {
            countEl.textContent = this.points.length;
        }
    }

    handleMessage(data) {
        if (data.type === 'geometry_update') {
            // Add new points from live stream
            if (this.state.mode === 'system') {
                this.addPoints(data.points);
            }
        } else if (data.type === 'geometry_snapshot') {
            // Replace all points with snapshot
            if (this.state.mode === 'subject') {
                this.clearPoints();
                this.addPoints(data.points);
                this.renderer.render(this.scene, this.camera);
            }
        }
    }

    addPoints(pointsData) {
        pointsData.forEach(p => {
            const geometry = new THREE.SphereGeometry(0.05, 8, 8);
            const material = new THREE.MeshBasicMaterial({
                color: p.color || 0x4ec9b0,
                transparent: true,
                opacity: p.alpha || 1.0
            });

            const point = new THREE.Mesh(geometry, material);
            point.position.set(p.x, p.y, p.z);

            this.scene.add(point);
            this.points.push(point);
        });
    }

    clearPoints() {
        this.points.forEach(point => {
            this.scene.remove(point);
            point.geometry.dispose();
            point.material.dispose();
        });
        this.points = [];
    }

    close() {
        this.emit('geometry-closed');
        this.unmount();
    }
}

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = GeometryViewer;
}
