/**
 * Cloudflare Worker: Notion Webhook Router
 * 
 * Receives Notion webhooks, verifies HMAC signatures,
 * and forwards to local Copaw API via Cloudflare Tunnel.
 * 
 * Environment Variables:
 * - NOTION_WEBHOOK_SECRET: HMAC secret from Notion developer portal
 * - COPAW_TUNNEL_URL: Local Copaw API URL (via Cloudflare Tunnel)
 * - COPAW_API_KEY: Optional API key for Copaw authentication
 */

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // Only accept POST requests
    if (request.method !== 'POST') {
      return new Response('Method not allowed', { status: 405 });
    }

    try {
      // Get request body
      const body = await request.text();
      
      // Verify HMAC signature
      const signature = request.headers.get('X-Notion-Signature');
      if (!signature) {
        return new Response('Missing signature', { 
          status: 401,
          headers: { 'Content-Type': 'text/plain' }
        });
      }

      const isValid = await verifySignature(body, signature, env.NOTION_WEBHOOK_SECRET);
      if (!isValid) {
        return new Response('Invalid signature', { 
          status: 401,
          headers: { 'Content-Type': 'text/plain' }
        });
      }

      // Parse Notion payload
      const notionPayload = JSON.parse(body);
      
      // Log webhook receipt
      console.log('Received Notion webhook:', {
        type: notionPayload.type,
        workspace_id: notionPayload.workspace_id,
        timestamp: notionPayload.timestamp
      });

      // Map Notion event to Copaw action
      const copawAction = mapNotionToCopaw(notionPayload);
      
      if (!copawAction) {
        // Event type not mapped, return success but don't forward
        return new Response('Event type not configured', { 
          status: 200,
          headers: { 'Content-Type': 'text/plain' }
        });
      }

      // Forward to Copaw API via Cloudflare Tunnel
      const copawUrl = env.COPAW_TUNNEL_URL || 'https://copaw.arca-internal.com/notion';
      
      const copawPayload = {
        source: 'notion',
        action: copawAction.action,
        data: copawAction.data,
        notion_payload: notionPayload,
        received_at: new Date().toISOString()
      };

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        'X-Source': 'cloudflare-worker',
        'X-Notion-Event-Type': notionPayload.type || 'unknown'
      };

      // Add API key if configured
      if (env.COPAW_API_KEY) {
        headers['Authorization'] = `Bearer ${env.COPAW_API_KEY}`;
      }

      const copawResponse = await fetch(copawUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(copawPayload)
      });

      // Log response status
      console.log('Copaw API response:', copawResponse.status);

      // Return success to Notion (they expect 2xx within 5 seconds)
      return new Response(JSON.stringify({
        success: true,
        action: copawAction.action,
        copaw_status: copawResponse.status
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' }
      });

    } catch (error) {
      console.error('Webhook processing error:', error);
      
      return new Response(JSON.stringify({
        success: false,
        error: error instanceof Error ? error.message : 'Unknown error'
      }), {
        status: 500,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
};

/**
 * Verify HMAC-SHA256 signature from Notion
 */
async function verifySignature(
  body: string,
  signature: string,
  secret: string
): Promise<boolean> {
  if (!secret) {
    console.warn('No webhook secret configured');
    return false;
  }

  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const messageData = encoder.encode(body);

  // Import key
  const key = await crypto.subtle.importKey(
    'raw',
    keyData,
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  // Sign message
  const signatureBuffer = await crypto.subtle.sign('HMAC', key, messageData);
  
  // Convert to hex string
  const signatureHex = Array.from(new Uint8Array(signatureBuffer))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Compare signatures (constant-time comparison)
  return signature === signatureHex;
}

/**
 * Map Notion webhook events to Copaw actions
 */
function mapNotionToCopaw(payload: any): { action: string; data: any } | null {
  const { type, database_id, page, comment, user } = payload;

  switch (type) {
    case 'database_page':
      // Page created/updated in database
      return {
        action: 'notion_page_updated',
        data: {
          database_id,
          page_id: page?.id,
          title: extractPageTitle(page),
          properties: page?.properties,
          url: page?.url
        }
      };

    case 'comment':
      // Comment added
      return {
        action: 'notion_comment_added',
        data: {
          comment_id: comment?.id,
          discussion_id: comment?.discussion_id,
          rich_text: comment?.rich_text,
          created_by: user?.name || user?.id,
          page_id: comment?.parent?.page_id,
          block_id: comment?.parent?.block_id
        }
      };

    case 'page':
      // Page created/updated (not in database)
      return {
        action: 'notion_page_updated',
        data: {
          page_id: page?.id,
          title: extractPageTitle(page),
          url: page?.url
        }
      };

    case 'button':
      // Database button pressed
      return {
        action: 'notion_button_pressed',
        data: {
          database_id,
          page_id: page?.id,
          button_action: extractButtonAction(page)
        }
      };

    default:
      // Unknown event type
      console.log('Unmapped Notion event type:', type);
      return null;
  }
}

/**
 * Extract page title from Notion page object
 */
function extractPageTitle(page: any): string {
  if (!page?.properties) return '';

  // Try common title property names
  const titleProps = ['Name', 'Title', 'title', 'name'];
  
  for (const propName of titleProps) {
    const prop = page.properties[propName];
    if (prop?.title?.[0]?.plain_text) {
      return prop.title[0].plain_text;
    }
    if (prop?.rich_text?.[0]?.plain_text) {
      return prop.rich_text[0].plain_text;
    }
  }

  return '';
}

/**
 * Extract button action from page properties
 */
function extractButtonAction(page: any): string {
  // Look for button-related properties
  const props = page?.properties || {};
  
  // Check for action/status properties
  if (props['Action']?.select?.name) {
    return props['Action'].select.name;
  }
  if (props['Status']?.select?.name) {
    return `status_${props.Status.select.name}`;
  }
  if (props['Priority']?.select?.name) {
    return `priority_${props.Priority.select.name}`;
  }

  return 'unknown';
}

/**
 * Environment variables interface
 */
interface Env {
  NOTION_WEBHOOK_SECRET: string;
  COPAW_TUNNEL_URL: string;
  COPAW_API_KEY?: string;
}
