/**
 * BaseComponent - Foundation for all ARCA UI components
 * Provides lifecycle hooks and WebSocket integration
 */
class BaseComponent {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = null;
        this.state = {};
        this.listeners = new Map();
    }

    /**
     * Mount the component to the DOM
     */
    mount() {
        this.container = document.querySelector(this.containerId);
        if (!this.container) {
            console.error(`Container ${this.containerId} not found`);
            return;
        }

        this.render();
        this.attachEventListeners();
        this.onMounted();
    }

    /**
     * Unmount and cleanup
     */
    unmount() {
        this.removeEventListeners();
        this.onUnmounted();
        if (this.container) {
            this.container.innerHTML = '';
        }
    }

    /**
     * Render the component (override in subclass)
     */
    render() {
        if (this.container) {
            this.container.innerHTML = this.template();
        }
    }

    /**
     * Template method - return HTML string (override in subclass)
     */
    template() {
        return '<div>Base Component</div>';
    }

    /**
     * Attach event listeners (override in subclass)
     */
    attachEventListeners() { }

    /**
     *  Remove event listeners
     */
    removeEventListeners() {
        this.listeners.forEach((handler, key) => {
            const [element, event] = key.split(':');
            const el = this.container.querySelector(element);
            if (el) {
                el.removeEventListener(event, handler);
            }
        });
        this.listeners.clear();
    }

    /**
     * Helper to add tracked event listener
     */
    on(selector, event, handler) {
        const el = this.container.querySelector(selector);
        if (el) {
            this.listeners.set(`${selector}:${event}`, handler);
            el.addEventListener(event, handler);
        }
    }

    /**
     * Update component state and re-render
     */
    setState(newState) {
        this.state = { ...this.state, ...newState };
        this.render();
        this.attachEventListeners();
    }

    /**
     * Handle WebSocket message (override in subclass)
     */
    handleMessage(data) { }

    /**
     * Lifecycle hooks (override in subclass)
     */
    onMounted() { }
    onUnmounted() { }

    /**
     * Emit custom event for component communication
     */
    emit(eventName, data) {
        const event = new CustomEvent(eventName, { detail: data });
        document.dispatchEvent(event);
    }

    /**
     * Listen for custom events
     */
    subscribe(eventName, handler) {
        document.addEventListener(eventName, handler);
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = BaseComponent;
}
