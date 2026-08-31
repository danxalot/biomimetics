/**
 * Notion Event Router - Cloudflare Worker
 * 
 * Routes Notion webhooks to:
 * 1. GitHub Issues (if ARCA tag present)
 * 2. GCP Pub/Sub (for system-wide event broadcasting)
 * 
 * Environment Variables:
 * - GCP_PROJECT_ID: GCP project ID
 * - PUBSUB_TOPIC_ID: Pub/Sub topic name (default: os-events)
 * - GITHUB_OWNER: GitHub username/org
 * - GITHUB_REPO: Target repository for issues
 * - NOTION_WEBHOOK_SECRET: Webhook signature secret
 * 
 * Secrets (via wrangler secret put):
 * - GITHUB_PAT: GitHub Personal Access Token
 * - GCP_SERVICE_ACCOUNT_JSON: GCP Service Account JSON
 * - NOTION_WEBHOOK_SECRET: Notion webhook signing secret
 */

interface Env {
  GCP_PROJECT_ID: string;
  PUBSUB_TOPIC_ID: string;
  GITHUB_OWNER: string;
  GITHUB_REPO: string;
  NOTION_WEBHOOK_SECRET: string;
  GITHUB_PAT: string;
  GCP_SERVICE_ACCOUNT_JSON: string;
}

// Notion webhook payload types
interface NotionPageProperties {
  title?: Array<{
    plain_text: string;
  }>;
  Name?: {
    title: Array<{
      plain_text: string;
    }>;
  };
  Tags?: {
    multi_select: Array<{
      name: string;
    }>;
  };
  Description?: {
    rich_text: Array<{
      plain_text: string;
    }>;
  };
}

interface NotionWebhookPayload {
  event: {
    id: string;
    created_time: string;
    last_edited_time: string;
    properties: NotionPageProperties;
    parent: {
      type: string;
      database_id: string;
    };
  };
}

// GitHub Issue types
interface GitHubIssue {
  title: string;
  body: string;
  labels: string[];
}

// GCP Pub/Sub message
interface PubSubMessage {
  data: string; // base64 encoded
  attributes: Record<string, string>;
}

/**
 * Verify Notion webhook signature
 */
async function verifyNotionSignature(
  signature: string,
  body: string,
  secret: string
): Promise<boolean> {
  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const messageData = encoder.encode(body);

  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );

  const signatureBytes = hexToBytes(signature.replace("sha256=", ""));

  return await crypto.subtle.verify(
    "HMAC",
    key,
    signatureBytes,
    messageData
  );
}

/**
 * Convert hex string to Uint8Array
 */
function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substr(i, 2), 16);
  }
  return bytes;
}

/**
 * Extract task information from Notion payload
 */
function extractTaskData(payload: NotionWebhookPayload): {
  title: string;
  tags: string[];
  description: string;
  notionId: string;
  createdTime: string;
} {
  const props = payload.event.properties;

  // Extract title (handles both "title" and "Name" property types)
  const title = props.title?.[0]?.plain_text 
    || props.Name?.title?.[0]?.plain_text 
    || "Untitled Task";

  // Extract tags
  const tags = props.Tags?.multi_select?.map(tag => tag.name) || [];

  // Extract description
  const description = props.Description?.rich_text?.[0]?.plain_text 
    || "";

  return {
    title,
    tags,
    description,
    notionId: payload.event.id,
    createdTime: payload.event.created_time,
  };
}

/**
 * Check if task should create GitHub issue (has ARCA tag)
 */
function shouldCreateGitHubIssue(tags: string[]): boolean {
  return tags.some(tag => 
    tag.toUpperCase().includes("ARCA") || 
    tag.toUpperCase().includes("DEV") ||
    tag.toUpperCase().includes("CODE")
  );
}

/**
 * Generate GitHub issue body from Notion task
 */
function generateIssueBody(taskData: ReturnType<typeof extractTaskData>): string {
  return `## 📋 Task from Notion

**Source**: Notion Database
**Notion ID**: \`${taskData.notionId}\`
**Created**: ${taskData.createdTime}

---

## Description

${taskData.description || "No description provided."}

---

## Tags

${taskData.tags.map(tag => `- \`${tag}\``).join("\n") || "No tags"}

---

*Automatically created by Notion Event Router*
`;
}

/**
 * Create GitHub Issue via REST API
 */
async function createGitHubIssue(
  taskData: ReturnType<typeof extractTaskData>,
  githubPat: string,
  owner: string,
  repo: string
): Promise<Response> {
  const issue: GitHubIssue = {
    title: taskData.title,
    body: generateIssueBody(taskData),
    labels: taskData.tags.filter(tag => !tag.toUpperCase().includes("ARCA")),
  };

  const url = `https://api.github.com/repos/${owner}/${repo}/issues`;

  return await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${githubPat}`,
      "Accept": "application/vnd.github.v3+json",
      "Content-Type": "application/json",
      "User-Agent": "notion-event-router/1.0",
    },
    body: JSON.stringify(issue),
  });
}

/**
 * Get GCP OAuth 2.0 access token using Service Account
 */
async function getGCPAccessToken(serviceAccountJson: string): Promise<string> {
  const serviceAccount = JSON.parse(serviceAccountJson);
  
  const now = Math.floor(Date.now() / 1000);
  const claimSet = {
    iss: serviceAccount.client_email,
    sub: serviceAccount.client_email,
    scope: "https://www.googleapis.com/auth/pubsub",
    aud: "https://oauth2.googleapis.com/token",
    exp: now + 3600,
    iat: now,
  };

  // Create JWT header
  const header = {
    alg: "RS256",
    typ: "JWT",
  };

  // Base64url encode
  const encodeBase64 = (data: string) => 
    btoa(data)
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");

  const encodedHeader = encodeBase64(JSON.stringify(header));
  const encodedClaimSet = encodeBase64(JSON.stringify(claimSet));

  // For Cloudflare Workers, we need to use the private key directly
  // This is a simplified version - in production, use proper JWT signing
  const assertion = `${encodedHeader}.${encodedClaimSet}`;

  // Exchange for access token
  const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({
      grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
      assertion: assertion,
    }),
  });

  if (!tokenResponse.ok) {
    throw new Error(`Failed to get GCP access token: ${await tokenResponse.text()}`);
  }

  const tokenData = await tokenResponse.json();
  return tokenData.access_token;
}

/**
 * Publish event to GCP Pub/Sub
 */
async function publishToPubSub(
  taskData: ReturnType<typeof extractTaskData>,
  accessToken: string,
  projectId: string,
  topicId: string
): Promise<Response> {
  const topicName = `projects/${projectId}/topics/${topicId}`;
  
  // Create message payload
  const messagePayload = {
    event_type: "notion.task.created",
    source: "notion",
    timestamp: new Date().toISOString(),
    data: taskData,
  };

  const message: PubSubMessage = {
    data: btoa(JSON.stringify(messagePayload)),
    attributes: {
      "event-type": "notion.task.created",
      "source": "notion",
      "notion-id": taskData.notionId,
      "tags": taskData.tags.join(","),
    },
  };

  const url = `https://pubsub.googleapis.com/v1/${topicName}:publish`;

  return await fetch(url, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${accessToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      messages: [message],
    }),
  });
}

/**
 * Main request handler
 */
export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    // Only accept POST requests
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    // Get signature from headers
    const signature = request.headers.get("X-Notion-Signature");
    
    // Read body
    const body = await request.text();

    // Parse payload FIRST (we need to check for verification_token before signature validation)
    let payload: NotionWebhookPayload;
    try {
      payload = JSON.parse(body);
    } catch (e) {
      return new Response("Invalid JSON payload", { status: 400 });
    }

    // --- NOTION VERIFICATION TRAP ---
    // Notion sends a verification_token on first webhook registration
    // We catch it, log it, and return OK to complete verification
    // This MUST come BEFORE signature validation
    if ("verification_token" in payload) {
      const verificationToken = (payload as any).verification_token;
      console.log("🔑 NOTION VERIFICATION TOKEN:", verificationToken);
      console.log("Copy this token and paste it into Notion's verification field!");
      return new Response("OK", { 
        status: 200,
        headers: { "Content-Type": "text/plain" }
      });
    }
    // --------------------------------

    // Verify signature (skip if no signature provided - test mode)
    if (signature && env.NOTION_WEBHOOK_SECRET && env.NOTION_WEBHOOK_SECRET !== "production-secret-set-via-cli") {
      const isValid = await verifyNotionSignature(
        signature,
        body,
        env.NOTION_WEBHOOK_SECRET
      );

      if (!isValid) {
        console.log("Invalid signature received");
        return new Response("Invalid signature", { status: 401 });
      }
    } else if (!signature) {
      console.log("No signature provided - processing in test mode");
    }

    // Extract task data
    const taskData = extractTaskData(payload);

    // Route BiOS Authorisation database events directly to local CoPaw sweeper
    const parentDbId = payload.event.parent?.database_id || "";
    const isAuthDb = parentDbId.replace(/-/g, "") === "3284d2d9fc7c81bd9a91e865511e642f";
    const props = payload.event.properties;
    const isAuthTrigger = (props as any)["Auth Trigger"]?.checkbox === true;

    if (isAuthDb) {
      if (isAuthTrigger) {
        console.log("🔒 BiOS Authorisation Triggered! Notifying local CoPaw sweeper...");
        ctx.waitUntil(
          (async () => {
            try {
              const copawResponse = await fetch("https://copaw.arca-internal.com/webhook/notion/sync", {
                method: "POST",
                headers: { "Content-Type": "application/json" }
              });
              console.log(`Local CoPaw sweeper notify response: ${copawResponse.status} ${await copawResponse.text()}`);
            } catch (err) {
              console.error("Failed to notify local CoPaw sweeper:", err);
            }
          })()
        );
      }
      return new Response(
        JSON.stringify({
          success: true,
          message: "Authorisation event received",
          auth_triggered: isAuthTrigger,
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }
      );
    }

    console.log("Received Notion task:", {
      title: taskData.title,
      tags: taskData.tags,
      notionId: taskData.notionId,
    });

    // Process asynchronously (don't block response)
    ctx.waitUntil(
      (async () => {
        const results: Record<string, any> = {
          notion_id: taskData.notionId,
          timestamp: new Date().toISOString(),
        };

        try {
          // Create GitHub issue if ARCA tag present
          if (shouldCreateGitHubIssue(taskData.tags)) {
            console.log("Creating GitHub issue for ARCA task...");
            
            const githubResponse = await createGitHubIssue(
              taskData,
              env.GITHUB_PAT,
              env.GITHUB_OWNER,
              env.GITHUB_REPO
            );

            if (githubResponse.ok) {
              const issueData = await githubResponse.json();
              results.github_issue = {
                created: true,
                url: issueData.html_url,
                number: issueData.number,
              };
              console.log("GitHub issue created:", issueData.html_url);
            } else {
              results.github_issue = {
                created: false,
                error: await githubResponse.text(),
              };
              console.error("Failed to create GitHub issue:", await githubResponse.text());
            }
          }

          // Publish to GCP Pub/Sub
          console.log("Publishing to GCP Pub/Sub...");
          
          const accessToken = await getGCPAccessToken(env.GCP_SERVICE_ACCOUNT_JSON);
          
          const pubsubResponse = await publishToPubSub(
            taskData,
            accessToken,
            env.GCP_PROJECT_ID,
            env.PUBSUB_TOPIC_ID
          );

          if (pubsubResponse.ok) {
            const pubsubData = await pubsubResponse.json();
            results.pubsub = {
              published: true,
              message_id: pubsubData.messageIds?.[0],
            };
            console.log("Published to Pub/Sub:", pubsubData.messageIds?.[0]);
          } else {
            results.pubsub = {
              published: false,
              error: await pubsubResponse.text(),
            };
            console.error("Failed to publish to Pub/Sub:", await pubsubResponse.text());
          }
        } catch (error) {
          console.error("Error processing event:", error);
          results.error = error instanceof Error ? error.message : String(error);
        }

        // Log results (in production, send to Cloudflare Logs or external service)
        console.log("Event processing results:", results);
      })()
    );

    // Return immediate response to Notion
    return new Response(
      JSON.stringify({
        success: true,
        message: "Event received and processing",
        notion_id: taskData.notionId,
      }),
      {
        status: 200,
        headers: {
          "Content-Type": "application/json",
        },
      }
    );
  },
};
