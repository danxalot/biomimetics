/**
 * tcp_bridge.js
 * Generic Stdio <-> TCP Bridge for MCP
 * 
 * Pipes process.stdin -> TCP Socket
 * Pipes TCP Socket -> process.stdout
 * 
 * Usage: node tcp_bridge.js
 * Configuration: via Environment Variables
 * - DATA_HUB_MCP_URL: URL of the target (parsed for host/port if rpc://)
 * - RPC_TARGET_HOST: Host to connect to (override)
 * - RPC_TARGET_PORT: Port to connect to (override)
 */

const net = require('net');
const url = require('url');

const rpcUrlStr = process.env.OPENCLAW_RPC_URL || process.env.RPC_URL;
let host = process.env.RPC_TARGET_HOST;
let port = process.env.RPC_TARGET_PORT;

if (rpcUrlStr) {
    try {
        // Handle rpc:// scheme or plain host:port
        const cleanUrl = rpcUrlStr.replace('rpc://', 'http://');
        const parsed = url.parse(cleanUrl);
        host = parsed.hostname || host;
        port = parsed.port || port;
    } catch (e) {
        console.error(`Failed to parse RPC URL: ${e.message}`);
        process.exit(1);
    }
}

if (!host || !port) {
    console.error("Error: Target host/port not configured.");
    console.error("Set OPENCLAW_RPC_URL, RPC_URL, or RPC_TARGET_HOST/PORT.");
    process.exit(1);
}

const socket = new net.Socket();

socket.connect(Number(port), host, () => {
    // console.error(`Connected to ${host}:${port}`);
});

socket.on('error', (err) => {
    console.error(`Socket Error: ${err.message}`);
    process.exit(1);
});

socket.on('close', () => {
    console.error('Socket closed');
    process.exit(0);
});

// Pipe Stdin -> Socket
process.stdin.pipe(socket);

// Pipe Socket -> Stdout
socket.pipe(process.stdout);

// Handle process termination
process.on('SIGINT', () => {
    socket.end();
    process.exit();
});
