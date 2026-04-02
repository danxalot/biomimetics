/**
 * WhatsApp Notification Worker for CoPaw
 * Routes approval requests via Green API WhatsApp bridge
 *
 * Environment Variables:
 * - GREEN_API_ID: Green API instance ID (e.g., "7107560335")
 * - GREEN_API_TOKEN: Green API token instance
 * - GREEN_API_URL: Green API base URL (e.g., "https://7107.api.greenapi.com")
 * - USER_WHATSAPP_NUMBER: Recipient WhatsApp number (e.g., "1234567890@c.us")
 * - COPAW_WEBHOOK_URL: CoPaw webhook receiver URL (for inbound responses)
 *
 * Green API Documentation:
 * - Send Message: https://greenapi.com/docs/api/sending/SendMessage/
 * - Webhooks: https://greenapi.com/docs/api/receiving/
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // CORS preflight
    if (request.method === "OPTIONS") {
      return handleCORS();
    }

    // Route: /notify - Send approval notification via Green API
    if (url.pathname === "/notify" && request.method === "POST") {
      return await handleNotify(request, env);
    }

    // Route: /webhook - Handle incoming WhatsApp messages from Green API
    if (url.pathname === "/webhook" && request.method === "POST") {
      return await handleGreenAPIWebhook(request, env);
    }

    // Route: /response - Handle parsed approval responses
    if (url.pathname === "/response" && request.method === "POST") {
      return await handleResponse(request, env);
    }

    // Route: /health - Health check
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({
        status: "healthy",
        service: "whatsapp-notifier",
        provider: "green-api",
        timestamp: new Date().toISOString()
      }), {
        headers: { "Content-Type": "application/json" }
      });
    }

    // Route: /test - Test message endpoint
    if (url.pathname === "/test" && request.method === "POST") {
      return await handleTest(request, env);
    }

    return new Response("Not Found", {
      status: 404,
      headers: { "Content-Type": "application/json" }
    });
  }
};

/**
 * Handle approval notification requests - Send via Green API
 */
async function handleNotify(request, env) {
  try {
    const payload = await request.json();

    // Validate required fields
    if (!payload.approval_id || !payload.tool_name) {
      return new Response(JSON.stringify({
        success: false,
        error: "Missing required fields: approval_id, tool_name"
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    // Validate Green API configuration
    if (!env.GREEN_API_ID || !env.GREEN_API_TOKEN || !env.GREEN_API_URL) {
      return new Response(JSON.stringify({
        success: false,
        error: "Green API not configured (GREEN_API_ID, GREEN_API_TOKEN, GREEN_API_URL required)"
      }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }

    const message = formatApprovalMessage(payload);

    // Green API sendMessage endpoint
    // https://greenapi.com/docs/api/sending/SendMessage/
    const greenApiUrl = `${env.GREEN_API_URL}/waInstance${env.GREEN_API_ID}/sendMessage/${env.USER_WHATSAPP_NUMBER}`;

    const response = await fetch(greenApiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: message
      })
    });

    const result = await response.json();

    // Green API returns: { idMessage: "..." } on success
    // or { code: 500, error: "..." } on error
    if (result.code === 500 || result.error) {
      return new Response(JSON.stringify({
        success: false,
        error: result.error || "Green API error",
        green_api_code: result.code
      }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }

    return new Response(JSON.stringify({
      success: true,
      message_id: result.idMessage,
      approval_id: payload.approval_id,
      provider: "green-api"
    }), {
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}

/**
 * Handle incoming webhook from Green API
 * Green API sends incoming messages to this endpoint
 *
 * Webhook payload format:
 * {
 *   "typeWebhook": "incomingMessageReceived",
 *   "instanceData": { "idInstance": 7107560335, ... },
 *   "timestamp": 1234567890,
 *   "idMessage": "...",
 *   "senderData": { "chatId": "1234567890@c.us", ... },
 *   "messageData": { "typeMessage": "textMessage", "textMessageData": { "text": "APPROVE abc123" } }
 * }
 */
async function handleGreenAPIWebhook(request, env) {
  try {
    const webhookData = await request.json();

    console.log("📥 Green API Webhook received:", JSON.stringify(webhookData, null, 2));

    // Only process incoming messages
    if (webhookData.typeWebhook !== "incomingMessageReceived") {
      return new Response(JSON.stringify({ success: true, message: "Webhook type ignored" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    // Extract message data
    const messageData = webhookData.messageData;
    const senderData = webhookData.senderData;

    if (!messageData || messageData.typeMessage !== "textMessage") {
      return new Response(JSON.stringify({ success: true, message: "Non-text message ignored" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    const messageText = messageData.textMessageData?.text || "";
    const chatId = senderData?.chatId || "";

    console.log(`📱 Message from ${chatId}: ${messageText}`);

    // Parse approval command
    const command = parseCommand(messageText);

    if (!command) {
      // Not an approval command, ignore
      return new Response(JSON.stringify({ success: true, message: "Not an approval command" }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }

    console.log(`✅ Parsed command: ${command.action} ${command.approval_id}`);

    // Forward to CoPaw webhook receiver via Cloudflare Tunnel
    if (env.COPAW_WEBHOOK_URL) {
      await fetch(env.COPAW_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "whatsapp_approval_response",
          from: chatId,
          approval_id: command.approval_id,
          action: command.action,
          timestamp: new Date().toISOString(),
          raw_message: messageText,
          confidence: command.confidence,
          source: "green-api"
        })
      });

      console.log(`✅ Forwarded to CoPaw: ${env.COPAW_WEBHOOK_URL}`);
    } else {
      console.warn("⚠️  COPAW_WEBHOOK_URL not configured");
    }

    return new Response(JSON.stringify({
      success: true,
      action: command.action,
      approval_id: command.approval_id,
      forwarded: !!env.COPAW_WEBHOOK_URL
    }), {
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    console.error("❌ Webhook error:", error);
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}

/**
 * Handle parsed approval responses (direct API calls)
 */
async function handleResponse(request, env) {
  try {
    const payload = await request.json();

    const { message, from, approval_id } = payload;
    const command = parseCommand(message);

    if (!command) {
      return new Response(JSON.stringify({
        success: false,
        error: "Could not parse command"
      }), {
        status: 400,
        headers: { "Content-Type": "application/json" }
      });
    }

    // Forward to CoPaw webhook receiver
    if (env.COPAW_WEBHOOK_URL) {
      await fetch(env.COPAW_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          type: "whatsapp_approval_response",
          from: from,
          approval_id: command.approval_id || approval_id,
          action: command.action,
          timestamp: new Date().toISOString()
        })
      });
    }

    return new Response(JSON.stringify({
      success: true,
      action: command.action,
      approval_id: command.approval_id
    }), {
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}

/**
 * Handle test message requests
 */
async function handleTest(request, env) {
  try {
    const payload = await request.json();
    const message = payload.message || "🔔 CoPaw WhatsApp Integration Test (Green API)\n\nHello World! This is a test message from the CoPaw notification system via Green API.\n\nIf you received this, the integration is working correctly! ✅";

    // Validate Green API configuration
    if (!env.GREEN_API_ID || !env.GREEN_API_TOKEN || !env.GREEN_API_URL) {
      return new Response(JSON.stringify({
        success: false,
        error: "Green API not configured"
      }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }

    const greenApiUrl = `${env.GREEN_API_URL}/waInstance${env.GREEN_API_ID}/sendMessage/${env.USER_WHATSAPP_NUMBER}`;

    const response = await fetch(greenApiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        message: message
      })
    });

    const result = await response.json();

    if (result.code === 500 || result.error) {
      return new Response(JSON.stringify({
        success: false,
        error: result.error || "Green API error"
      }), {
        status: 500,
        headers: { "Content-Type": "application/json" }
      });
    }

    return new Response(JSON.stringify({
      success: true,
      message_id: result.idMessage,
      test: true,
      provider: "green-api"
    }), {
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(JSON.stringify({
      success: false,
      error: error.message
    }), {
      status: 500,
      headers: { "Content-Type": "application/json" }
    });
  }
}

/**
 * Format approval message for WhatsApp
 */
function formatApprovalMessage(payload) {
  const args = JSON.stringify(payload.arguments || {});

  return `🔒 *Tool Approval Required*\n\n` +
    `*Tool:* \`${payload.tool_name}\`\n` +
    `*Arguments:* \`${args}\`\n` +
    `*Context:* ${payload.context || "N/A"}\n\n` +
    `*Risk Level:* ${payload.risk_level || "unknown"}\n\n` +
    `*Approval ID:* \`${payload.approval_id}\`\n\n` +
    `*Reply with:*\n` +
    `✅ APPROVE ${payload.approval_id}\n` +
    `❌ DENY ${payload.approval_id}\n\n` +
    `⏱️  Timeout: 5 minutes`;
}

/**
 * Parse approval command from message
 */
function parseCommand(message) {
  if (!message) return null;

  // Pattern 1: Direct command (APPROVE/DENY + ID)
  const approveMatch = message.match(/(?:✅\s*)?(APPROVE|APPROVED|YES)\s+([a-zA-Z0-9_-]+)/i);
  if (approveMatch) {
    return {
      action: "approve",
      approval_id: approveMatch[2],
      confidence: 0.95
    };
  }

  const denyMatch = message.match(/(?:❌\s*)?(DENY|DENIED|NO|REJECT)\s+([a-zA-Z0-9_-]+)/i);
  if (denyMatch) {
    return {
      action: "deny",
      approval_id: denyMatch[2],
      confidence: 0.95
    };
  }

  // Pattern 2: Approval ID only (implicit approve)
  const idMatch = message.match(/\b([a-zA-Z0-9_-]{6,})\b/);
  if (idMatch && message.split(/\s+/).length <= 2) {
    return {
      action: "approve",
      approval_id: idMatch[1],
      confidence: 0.7
    };
  }

  return null;
}

/**
 * Handle CORS preflight requests
 */
function handleCORS() {
  return new Response(null, {
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type, Authorization"
    }
  });
}
