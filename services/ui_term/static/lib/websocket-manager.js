/**
 * WebSocketManager - Centralized WebSocket connection management
 * Handles connection, reconnection, and message distribution to components
 */
class WebSocketManager {
    constructor() {
        this.ws = null;
        this.subscribers = new Set();
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        this.reconnectDelay = 3000;
        this.isConnected = false;
    }

    /**
     * Connect to WebSocket server
     */
    connect(url) {
        if (!url) {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsHost = window.location.hostname;
            const wsPort = window.location.port || (window.location.protocol === 'https:' ? '443' : '80');
            url = `${wsProtocol}//${wsHost}:${wsPort}/ws`;
        }

        console.log(`WebSocket connecting to ${url}`);

        this.ws = new WebSocket(url);

        this.ws.onopen = (event) => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.broadcast({ type: 'connection', status: 'connected' });
        };

        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.distributeMessage(data);
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        this.ws.onclose = (event) => {
            console.log('WebSocket disconnected');
            this.isConnected = false;
            this.broadcast({ type: 'connection', status: 'disconnected' });
            this.attemptReconnect(url);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    /**
     * Attempt to reconnect with exponential backoff
     */
    attemptReconnect(url) {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnect attempts reached');
            return;
        }

        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);

        console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        setTimeout(() => {
            this.connect(url);
        }, delay);
    }

    /**
     * Send message to server
     */
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            console.error('WebSocket not connected');
        }
    }

    /**
     * Subscribe a component to receive messages
     */
    subscribe(component) {
        if (component && typeof component.handleMessage === 'function') {
            this.subscribers.add(component);
        } else {
            console.error('Component must have handleMessage method');
        }
    }

    /**
     * Unsubscribe a component
     */
    unsubscribe(component) {
        this.subscribers.delete(component);
    }

    /**
     * Distribute message to all subscribed components
     */
    distributeMessage(data) {
        this.subscribers.forEach(component => {
            try {
                component.handleMessage(data);
            } catch (e) {
                console.error('Component message handler error:', e);
            }
        });
    }

    /**
     * Broadcast message to all subscribers
     */
    broadcast(data) {
        this.distributeMessage(data);
    }

    /**
     * Close connection
     */
    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    /**
     * Get connection status
     */
    getStatus() {
        return {
            connected: this.isConnected,
            readyState: this.ws ? this.ws.readyState : WebSocket.CLOSED
        };
    }
}

// Singleton instance
const wsManager = new WebSocketManager();

// Export
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketManager, wsManager };
}
