/**
 * CoPaw HUD - Native Console Upgrade
 * Intercepts pushed messages from /console/push-messages
 * and renders canvas_update payloads to a fixed overlay.
 */

(function() {
    console.log("CoPaw HUD Bridge initialized.");

    const HUD_CONTAINER_ID = 'copaw-hud-container';
    const POLL_INTERVAL = 1000; // 1 second polling
    let lastProcessedId = null;

    // Check if marked is available (injected via index.html)
    const renderMarkdown = (text) => {
        if (window.marked && typeof window.marked.parse === 'function') {
            return window.marked.parse(text);
        }
        return text; // Fallback to raw text
    };

    const getHUDContainer = () => {
        let container = document.getElementById(HUD_CONTAINER_ID);
        if (!container) {
            container = document.createElement('div');
            container.id = HUD_CONTAINER_ID;
            document.body.appendChild(container);
        }
        return container;
    };

    const updateHUD = (message) => {
        const container = getHUDContainer();
        container.innerHTML = renderMarkdown(message.text);
        container.classList.add('active');
        console.log("HUD updated with canvas_update.");
    };

    const pollMessages = async () => {
        try {
            // Polling the recent endpoint (last 60s)
            // We use no session_id to get global console messages
            const response = await fetch('/console/push-messages');
            if (!response.ok) return;

            const data = await response.json();
            const messages = data.messages || [];

            // Identify the latest canvas_update
            const canvasUpdates = messages.filter(m => m.type === 'canvas_update');
            if (canvasUpdates.length > 0) {
                const latest = canvasUpdates[canvasUpdates.length - 1];
                
                // Only update if it's new (simple heuristic: text change or first load)
                if (latest.text !== lastProcessedId) {
                    updateHUD(latest);
                    lastProcessedId = latest.text;
                }
            }
        } catch (error) {
            console.error("CoPaw HUD Polling error:", error);
        }
    };

    // Initialize polling
    setInterval(pollMessages, POLL_INTERVAL);
    pollMessages(); // Initial poll

})();
