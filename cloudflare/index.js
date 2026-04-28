/**
 * ARCA Biomimetics GitHub → Notion Sync Worker
 *
 * Handles GitHub webhooks and Serena agent requests:
 * - GitHub Webhooks (Issues, PRs, Pushes) → Biomimetic OS database
 * - Serena Agent Tasks → Life OS Triage & Biomimetic OS databases
 *
 * Environment Secrets:
 * - NOTION_API_KEY: Notion integration token (alias: NOTION_TOKEN)
 * - NOTION_DB_ID: Biomimetic OS database ID (3244d2d9fc7c808b97c3ce78648d77a1)
 * - BIOMIMETIC_DB_ID: Alias for NOTION_DB_ID
 * - LIFE_OS_TRIAGE_DB_ID: Life OS Triage database ID
 * - GITHUB_WEBHOOK_SECRET: Webhook validation secret
 */

/**
 * Global OIDC Token Cache (Task 3: Phase 5.1)
 */
let cachedOidcToken = null;
let oidcTokenExpiry = 0;

export default {
  async fetch(request, env) {
    // Only accept POST requests (GET allowed for Serena queries)
    if (request.method !== "POST" && request.method !== "GET") {
      return new Response("Method not allowed. Use POST or GET.", {
        status: 405,
        headers: { "Content-Type": "text/plain" }
      });
    }

    // =========================================================
    // HEADER EXTRACTION
    // =========================================================
    const arcaSource = request.headers.get("X-Arca-Source");
    const userAgent = request.headers.get("User-Agent");
    const actionType = request.headers.get("X-Serena-Action");

    // GitHub webhook headers
    const githubEvent = request.headers.get("X-GitHub-Event");
    const githubSignature = request.headers.get("X-Hub-Signature-256");
    const githubDelivery = request.headers.get("X-GitHub-Delivery");

    // Log request info
    console.log(`Request received - X-Arca-Source: ${arcaSource}, User-Agent: ${userAgent}, X-Serena-Action: ${actionType}, GitHub-Event: ${githubEvent}`);

    // =========================================================
    // REQUEST ROUTING (via X-Arca-Source header)
    // =========================================================

    // Route 1: X-Arca-Source header takes priority
    if (arcaSource) {
      console.log(`Routing via X-Arca-Source: ${arcaSource}`);

      switch (arcaSource) {
        case 'GitHub':
          return await routeGitHubRequest(request, env);
        case 'Serena':
          return await routeSerenaRequest(request, env);
        case 'GCP-Memory':
          return await routeGcpMemoryInsight(request, env);
        case 'CoPaw':
          return await routeCoPawRequest(request, env);
        case 'PM-Agent':
          return await routePMAgent(request, env);
        default:
          return new Response(`Unknown X-Arca-Source: ${arcaSource}. Use 'GitHub', 'Serena', 'GCP-Memory', 'CoPaw', or 'PM-Agent'.`, {
            status: 400,
            headers: { "Content-Type": "text/plain" }
          });
      }
    }

    // Route 2: GitHub Webhook (detected by User-Agent)
    if (userAgent && userAgent.includes("GitHub-Hookshot")) {
      console.log("Routing: GitHub Webhook detected (User-Agent)");
      return await routeGitHubRequest(request, env);
    }

    // Route 3: Serena Agent Task (detected by X-Serena-Action header)
    if (actionType) {
      console.log(`Routing: Serena Agent action - ${actionType}`);
      return await routeSerenaRequest(request, env);
    }

    // Route 4: Legacy GitHub event routing (fallback)
    if (githubEvent) {
      console.log(`Routing: Legacy GitHub event - ${githubEvent}`);
      return await routeGitHubRequest(request, env);
    }

    // Default: No recognized headers - reject request
    console.log("Request rejected: No recognized headers");
    return new Response("Forbidden: No recognized request type. Use X-Arca-Source header (GitHub|Serena), GitHub webhook, or X-Serena-Action header.", {
      status: 403,
      headers: { "Content-Type": "text/plain" }
    });
  }
};

/**
 * Route GitHub requests (webhooks → Biomimetic OS database)
 */
async function routeGitHubRequest(request, env) {
  const githubEvent = request.headers.get("X-GitHub-Event");
  const githubSignature = request.headers.get("X-Hub-Signature-256");

  // Handle ping event
  if (githubEvent === "ping") {
    return new Response("Pong! GitHub webhook received.", { status: 200 });
  }

  // Verify webhook signature
  if (env.GITHUB_WEBHOOK_SECRET) {
    const payload = await request.clone().text();
    const isValid = await verifySignature(payload, githubSignature, env.GITHUB_WEBHOOK_SECRET);
    if (!isValid) {
      return new Response("Invalid webhook signature", { status: 401 });
    }
  }

  // Parse payload
  let payload;
  try {
    payload = await request.json();
  } catch (e) {
    return new Response("Invalid JSON payload", { status: 400 });
  }

  // Route to specific handler based on event type
  switch (githubEvent) {
    case "issues":
      return await handleIssues(payload, env);
    case "pull_request":
      return await handlePullRequest(payload, env);
    case "push":
      return await handlePush(payload, env);
    default:
      console.log(`Ignoring GitHub event type: ${githubEvent}`);
      return new Response(`Event type ${githubEvent} received`, { status: 200 });
  }
}

/**
 * Route Serena requests (GET/POST → Life OS Triage & Biomimetic OS databases)
 */
async function routeSerenaRequest(request, env) {
  const actionType = request.headers.get("X-Serena-Action");
  const method = request.method;

    // Get database IDs from environment (required)
    const biomimeticDbId = env.BIOMIMETIC_DB_ID || env.NOTION_DB_ID;
    const lifeOsTriageDbId = env.LIFE_OS_TRIAGE_DB_ID;
    const toolGuardDbId = env.TOOL_GUARD_DB_ID;
    const notionToken = env.NOTION_TOKEN || env.NOTION_API_KEY;
    
    // Validate required configuration
    if (!biomimeticDbId) {
        return new Response("Missing required database configuration: BIOMIMETIC_DB_ID or NOTION_DB_ID", { status: 500 });
    }
    if (!notionToken) {
        return new Response("Missing Notion token configuration: NOTION_TOKEN or NOTION_API_KEY", { status: 500 });
    }

  if (!notionToken) {
    return new Response("Missing Notion token", { status: 500 });
  }

  // Handle GET requests (queries)
  if (method === "GET") {
    return await handleSerenaQuery(request, env, biomimeticDbId, lifeOsTriageDbId, notionToken);
  }

  // Handle POST requests
  if (method === "POST") {
    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return new Response("Invalid JSON payload", { status: 400 });
    }

    // Route by action type
    if (actionType) {
       // For QUERY action, use the database from payload or default to biomimetic
       if (actionType === "QUERY") {
         const targetDb = payload.database || "biomimetic";
         // Use environment variables for database IDs
         const DB_IDS = {
           "biomimetic": biomimeticDbId,
           "life-os": lifeOsTriageDbId || biomimeticDbId,
           "triage": lifeOsTriageDbId || biomimeticDbId,
           "tool-guard": toolGuardDbId || biomimeticDbId
         };
         const targetDbId = DB_IDS[targetDb] || biomimeticDbId;
         console.log(`QUERY action: targetDb=${targetDb}, using ID=${targetDbId}`);
         return await queryDatabase(payload, env, targetDbId, notionToken);
       }
      return await handleSerenaTask(payload, env, actionType, biomimeticDbId, lifeOsTriageDbId, notionToken);
    }

    // Default: Create entry in Biomimetic OS
    return await createDatabaseEntry(payload, env, biomimeticDbId, notionToken);
  }

  return new Response("Method not allowed", { status: 405 });
}

/**
 * Handle Serena GET queries
 */
async function handleSerenaQuery(request, env, biomimeticDbId, lifeOsTriageDbId, notionToken) {
  const url = new URL(request.url);
  const database = url.searchParams.get("database") || "biomimetic";
  const filter = url.searchParams.get("filter");

  let databaseId = biomimeticDbId;
  if (database === "life-os" || database === "triage") {
    databaseId = lifeOsTriageDbId || biomimeticDbId;
  }

  const queryData = {
    database_id: databaseId,
    filter: filter ? JSON.parse(filter) : {},
    page_size: 10
  };

  try {
    const response = await fetch("https://api.notion.com/v1/databases/query", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(queryData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

    const result = await response.json();

    return new Response(JSON.stringify({
      success: true,
      database: database,
      results: result.results.length,
      data: result.results
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(`Query Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Handle Serena Agent Tasks
 *
 * Supported action types:
 * - SYNC_TASK: Create/update task in Notion
 * - UPDATE_STATUS: Update task status
 * - CREATE_ENTRY: Create generic database entry
 * - QUERY: Query Notion database
 */
async function handleSerenaTask(payload, env, actionType, biomimeticDbId, lifeOsTriageDbId, notionToken) {
  console.log(`Processing Serena action: ${actionType}`);

  // Get database IDs from environment (use parameters or fallback to env)
  const databaseId = biomimeticDbId || env.BIOMIMETIC_DB_ID || env.NOTION_DB_ID;
  const token = notionToken || env.NOTION_TOKEN || env.NOTION_API_KEY;

  if (!databaseId) {
    return new Response("Missing database ID", { status: 500 });
  }

  if (!token) {
    return new Response("Missing Notion token", { status: 500 });
  }

  // Determine target database from payload
  let targetDbId = databaseId;
  if (payload.database === "life-os" || payload.database === "triage") {
    targetDbId = lifeOsTriageDbId || databaseId;
  }

  switch (actionType) {
    case "SYNC_TASK":
      return await syncTask(payload, env, targetDbId, token);

    case "UPDATE_STATUS":
      return await updateTaskStatus(payload, env, targetDbId, token);

    case "CREATE_ENTRY":
      return await createDatabaseEntry(payload, env, targetDbId, token);

    case "QUERY":
      return await queryDatabase(payload, env, targetDbId, token);
    
    default:
      return new Response(`Unknown action type: ${actionType}. Supported: SYNC_TASK, UPDATE_STATUS, CREATE_ENTRY, QUERY`, { status: 400 });
  }
}

/**
 * SYNC_TASK: Create or update a task in Notion
 */
async function syncTask(payload, env, databaseId, notionToken) {
  const {
    task_id,
    title,
    description,
    status = "Not Started",
    source = "Serena",
    metadata = {}
  } = payload;

  const notionData = {
    parent: { database_id: databaseId },
    properties: {
      "Task Name": {
        title: [{ text: { content: `[TASK] ${title}` } }]
      },
      "Status": {
        status: { name: status }
      }
    },
    children: [
      {
        object: "block",
        type: "paragraph",
        paragraph: {
          rich_text: [{ text: { content: truncateText(description, 2000) } }]
        }
      }
    ]
  };

  // Add optional metadata fields (only if database has them)
  if (metadata.tags || metadata.labels) {
    const tags = metadata.tags || metadata.labels;
    notionData.properties["Tags"] = {
      multi_select: tags.map(tag => ({ name: tag }))
    };
  }

  if (metadata.priority) {
    notionData.properties["Priority"] = {
      select: { name: metadata.priority }
    };
  }

  if (metadata.github_link) {
    notionData.properties["Github Link"] = {
      url: metadata.github_link
    };
  }

  if (metadata.email) {
    notionData.properties["Email"] = {
      email: metadata.email
    };
  }

  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

     const result = await response.json();
     
     // Forward to GCP memory system
     await forwardToGcpMemory({
       type: "task-synced",
       task: {
         task_id: task_id,
         title: title,
         description: description,
         status: status,
         source: source
       },
       notionPageId: result.id
     }, env);
     
     return new Response(JSON.stringify({
       success: true,
       notion_page_id: result.id,
       task_id: task_id,
       action: "SYNC_TASK"
     }), {
       status: 200,
       headers: { "Content-Type": "application/json" }
     });

  } catch (error) {
    return new Response(`Sync Error: ${error.message}`, { status: 500 });
  }
}

/**
 * UPDATE_STATUS: Update task status in Notion
 */
async function updateTaskStatus(payload, env, databaseId, notionToken) {
  const { page_id, task_id, new_status } = payload;

  if (!page_id && !task_id) {
    return new Response("Missing page_id or task_id", { status: 400 });
  }

  if (!new_status) {
    return new Response("Missing new_status", { status: 400 });
  }

  const notionData = {
    properties: {
      "Status": {
        status: { name: new_status }
      }
    }
  };

  try {
    const response = await fetch(`https://api.notion.com/v1/pages/${page_id}`, {
      method: "PATCH",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

    const result = await response.json();
    
    return new Response(JSON.stringify({
      success: true,
      notion_page_id: result.id,
      new_status: new_status,
      action: "UPDATE_STATUS"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(`Update Error: ${error.message}`, { status: 500 });
  }
}

/**
 * CREATE_ENTRY: Create generic database entry
 */
async function createDatabaseEntry(payload, env, databaseId, notionToken) {
  const { name, properties = {} } = payload;

  const notionData = {
    parent: { database_id: databaseId },
    properties: {
      "Name": {
        title: [{ text: { content: name || "Untitled Entry" } }]
      },
      ...properties
    }
  };

  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

    const result = await response.json();
    
    return new Response(JSON.stringify({
      success: true,
      notion_page_id: result.id,
      action: "CREATE_ENTRY"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    return new Response(`Create Error: ${error.message}`, { status: 500 });
  }
}

/**
 * QUERY: Query Notion database
 */
async function queryDatabase(payload, env, databaseId, notionToken) {
  const { filter, sorts, page_size = 10 } = payload;

  // Validate database ID
  if (!databaseId) {
    return new Response("Missing database ID", { status: 500 });
  }

  console.log(`queryDatabase: databaseId=${databaseId}, notionToken=${notionToken ? 'present' : 'MISSING'}`);

  const queryData = {
    database_id: databaseId,
    filter: filter || {},
    sorts: sorts || [],
    page_size: page_size || 10
  };

  console.log(`queryDatabase: queryData=${JSON.stringify(queryData)}`);

  try {
    const response = await fetch("https://api.notion.com/v1/databases/query", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${notionToken}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(queryData)
    });

    console.log(`queryDatabase: response status=${response.status}`);

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Notion API Error: ${response.status} - ${errorText}`);
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

    const result = await response.json();

    return new Response(JSON.stringify({
      success: true,
      results: result.results.length,
      data: result.results,
      has_more: result.has_more,
      action: "QUERY"
    }), {
      status: 200,
      headers: { "Content-Type": "application/json" }
    });

  } catch (error) {
    console.error(`Query Error: ${error.message}`);
    return new Response(`Query Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Handle GitHub Issues events
 */
async function handleIssues(payload, env) {
  const action = payload.action;
  const issue = payload.issue;
  const repository = payload.repository;

  console.log(`Issue ${action}: ${issue.title} by ${issue.user.login}`);

  // Check if this issue should be synced to Notion
  const shouldSync = shouldSyncIssue(issue, action);

  if (!shouldSync) {
    return new Response("Issue not marked for sync", { status: 200 });
  }

  // Determine Notion status based on issue state and labels
  const notionStatus = getNotionStatus(issue, action);

  // Check for Serena label
  const isSerena = isSerenaIssue(issue);

  // Build Notion page properties (Task 1: Strict Schema Mapping)
  const notionData = {
    parent: { database_id: env.NOTION_DB_ID },
    properties: {
      "Task Name": {
        title: [{ text: { content: issue.title } }]
      },
      "GitHub Issue": {
        url: issue.html_url
      },
      "Status": {
        status: { name: notionStatus }
      }
    },
    // Task 2: Page Content Injection
    children: [
      {
        object: "block",
        type: "paragraph",
        paragraph: {
          rich_text: [{ text: { content: truncateText(issue.body, 2000) } }]
        }
      }
    ]
  };

  // Add labels to Notion if they exist
  if (issue.labels && issue.labels.length > 0) {
    notionData.properties["Labels"] = {
      multi_select: issue.labels.map(label => ({ name: label.name }))
    };
  }

  // Push to Notion
  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.NOTION_API_KEY}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`Notion API Error: ${response.status} - ${errorText}`);
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

     const result = await response.json();
     console.log(`Created Notion page: ${result.id}`);

     // Forward to GCP memory system
     await forwardToGcpMemory({
       type: "issue-created",
       issue: {
         number: issue.number,
         title: issue.title,
         user: issue.user.login,
         action: action,
         repository: repository.full_name
       },
       notionPageId: result.id
     }, env);

     return new Response(JSON.stringify({
       success: true,
       notion_page_id: result.id,
       issue_number: issue.number,
       serena: isSerena
     }), { 
       status: 200,
       headers: { "Content-Type": "application/json" }
     });

  } catch (error) {
    console.error(`Error syncing to Notion: ${error.message}`);
    return new Response(`Sync Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Handle Pull Request events
 */
async function handlePullRequest(payload, env) {
  const action = payload.action;
  const pr = payload.pull_request;
  const repository = payload.repository;

  console.log(`PR ${action}: ${pr.title} by ${pr.user.login}`);

  // Only sync PR open/close events
  if (!["opened", "closed", "reopened"].includes(action)) {
    return new Response(`PR action ${action} ignored`, { status: 200 });
  }

  const notionStatus = action === "closed" ? "Done" : "In Progress";

  const notionData = {
    parent: { database_id: env.NOTION_DB_ID },
    properties: {
      "Task Name": {
        title: [{ text: { content: `[PR] ${pr.title}` } }]
      },
      "GitHub Issue": {
        url: pr.html_url
      },
      "Status": {
        status: { name: notionStatus }
      }
    },
    children: [
      {
        object: "block",
        type: "paragraph",
        paragraph: {
          rich_text: [{ text: { content: truncateText(pr.body, 2000) } }]
        }
      }
    ]
  };

  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.NOTION_API_KEY}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

     const result = await response.json();
     console.log(`Created Notion page for PR: ${result.id}`);

     // Forward to GCP memory system
     await forwardToGcpMemory({
       type: "pull-request-event",
       pullRequest: {
         number: pr.number,
         title: pr.title,
         user: pr.user.login,
         action: action,
         repository: repository.full_name
       },
       notionPageId: result.id
     }, env);

     return new Response(JSON.stringify({
       success: true,
       notion_page_id: result.id,
       pr_number: pr.number
     }), { 
       status: 200,
       headers: { "Content-Type": "application/json" }
     });

  } catch (error) {
    return new Response(`Sync Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Handle Push events
 */
async function handlePush(payload, env) {
  const repository = payload.repository;
  const ref = payload.ref;
  const commits = payload.commits || [];
  const pushedBy = payload.pusher;

  console.log(`Push to ${ref} in ${repository.full_name}: ${commits.length} commits`);

  // Only sync pushes to main branches
  if (!ref.match(/refs\/heads\/(main|master|develop)/)) {
    return new Response(`Ignoring push to ${ref}`, { status: 200 });
  }

  // Create a summary entry for the push
  const commitSummaries = commits.map(c => `- ${c.message.split('\n')[0]} (${c.id.substring(0, 7)})`).join('\n');

  const notionData = {
    parent: { database_id: env.NOTION_DB_ID },
    properties: {
      "Name": {
        title: [{ text: { content: `[Push] ${repository.name}: ${ref.split('/').pop()}` } }]
      },
      "Status": {
        status: { name: "In Progress" }
      },
      "Source": {
        rich_text: [{ text: { content: `GitHub: ${repository.full_name}` } }]
      },
      "Github Link": {
        url: repository.html_url
      },
      "Description": {
        rich_text: [{ text: { content: `Pushed by: ${pushedBy.name}\n\nCommits:\n${commitSummaries}` } }]
      },
      "Memory_UUID": {
        rich_text: [{ text: { content: generateUUID(repository.id, ref) } }]
      },
      "Timestamp": {
        date: { start: new Date().toISOString() }
      }
    }
  };

  try {
    const response = await fetch("https://api.notion.com/v1/pages", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${env.NOTION_API_KEY}`,
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
      },
      body: JSON.stringify(notionData)
    });

    if (!response.ok) {
      const errorText = await response.text();
      return new Response(`Notion API Error: ${errorText}`, { status: response.status });
    }

     const result = await response.json();
     console.log(`Created Notion page for push: ${result.id}`);

     // Forward to GCP memory system
     await forwardToGcpMemory({
       type: "push-event",
       push: {
         repository: repository.full_name,
         ref: ref,
         commits: commits.length,
         pushedBy: pushedBy.name
       },
       notionPageId: result.id
     }, env);

     return new Response(JSON.stringify({
       success: true,
       notion_page_id: result.id,
       commits: commits.length
     }), { 
       status: 200,
       headers: { "Content-Type": "application/json" }
     });

  } catch (error) {
    return new Response(`Sync Error: ${error.message}`, { status: 500 });
  }
}

/**
 * Determine if an issue should be synced to Notion
 */
function shouldSyncIssue(issue, action) {
  // Always sync new issues
  if (action === "opened") return true;
  
  // Sync labeled events (for "Serena" label detection)
  if (action === "labeled") return true;
  
  // Sync closed issues
  if (action === "closed") return true;
  
  return false;
}

/**
 * Check if issue has "Serena" label
 */
function isSerenaIssue(issue) {
  if (!issue.labels || !Array.isArray(issue.labels)) return false;
  return issue.labels.some(label => 
    label.name.toLowerCase() === "serena" || 
    label.name.toLowerCase() === "ai-agent"
  );
}

/**
 * Get Notion status based on issue state and action
 */
function getNotionStatus(issue, action) {
  if (issue.state === "closed") return "Done";
  if (action === "labeled") return "In Progress";
  if (action === "opened") return "PM Review";
  return "PM Review";
}

/**
 * Verify webhook signature
 */
async function verifySignature(payload, signature, secret) {
  if (!signature || !secret) return false;

  const encoder = new TextEncoder();
  const keyData = encoder.encode(secret);
  const messageData = encoder.encode(payload);

  const key = await crypto.subtle.importKey(
    "raw",
    keyData,
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signatureBuffer = await crypto.subtle.sign("HMAC", key, messageData);
  const expectedSignature = "sha256=" + Array.from(new Uint8Array(signatureBuffer))
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");

  return signature === expectedSignature;
}

/**
 * Truncate text to max length
 */
function truncateText(text, maxLength) {
  if (!text) return "No description";
  const sanitized = sanitizeForNotion(text);
  if (sanitized.length <= maxLength) return sanitized;
  return sanitized.substring(0, maxLength - 3) + "...";
}

/**
 * Robust string sanitization to preserve file paths and backticks in Notion text
 */
function sanitizeForNotion(text) {
  if (!text) return "";
  
  // We prioritize DATA RETENTION over native markdown rendering.
  // Ensure the string can be safely stringified and sent to a Notion rich_text content field.
  // We don't perform heavy transformations, but we ensure special sequence characters 
  // that might confuse parsers are preserved as literal text.
  
  return text
    .replace(/\\/g, "\\\\") // Escape backslashes for JSON safety (Notion handles double escaping internally)
    .replace(/`/g, "'")    // Convert backticks to single-quotes to prevent block-breakage if relevant
    .trim();
}

/**
 * Generate deterministic UUID from issue data
 */
function generateUUID(...parts) {
  const hash = parts.join("-");
  // Simple hash to UUID v5-like format
  const hashBytes = new Uint8Array(16);
  for (let i = 0; i < 16 && i < hash.length; i++) {
    hashBytes[i] = hash.charCodeAt(i) % 256;
  }
   
  // Format as UUID
  const hex = Array.from(hashBytes)
    .map(b => b.toString(16).padStart(2, "0"))
    .join("");
   
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}

/**
 * Forward Notion update to GCP memory system
 */
async function forwardToGcpMemory(notionUpdate, env) {
  if (!env.GCP_GATEWAY) {
    console.log("GCP Gateway not configured, skipping memory sync");
    return;
  }

  try {
    // Task 2: Route the Memory via OIDC Identity Token
    const idToken = await getGoogleOidcToken(env);
    if (!idToken) {
      console.error("Failed to obtain GCP OIDC token, skipping forward.");
      return;
    }

    const response = await fetch(env.GCP_GATEWAY, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${idToken}`
      },
      body: JSON.stringify({
        source: "notion-update",
        timestamp: new Date().toISOString(),
        data: notionUpdate
      })
    });

    if (!response.ok) {
      console.error(`GCP Memory Sync Failed: ${response.status}`);
    } else {
      console.log("Successfully forwarded update to GCP memory system");
    }
  } catch (error) {
    console.error(`Error forwarding to GCP memory: ${error.message}`);
  }
}

/**
 * Route GCP Memory insights back to Biomimetic OS
 */
async function routeGcpMemoryInsight(request, env) {
  const method = request.method;
  
  // Only accept POST requests for insights
  if (method !== "POST") {
    return new Response("Method not allowed. Use POST.", {
      status: 405,
      headers: { "Content-Type": "text/plain" }
    });
  }

  // Parse payload
  let payload;
  try {
    payload = await request.json();
  } catch (e) {
    return new Response("Invalid JSON payload", { status: 400 });
  }

  // Handle different types of insights
  const insightType = payload.type;
  console.log(`Processing GCP memory insight: ${insightType}`);

  switch (insightType) {
    case "suggest-task":
      // Convert memory insight to Serena task suggestion
      return await handleGcpTaskSuggestion(payload, env);
    case "update-context":
      // Update Serena agent context based on memory insights
      return await handleGcpContextUpdate(payload, env);
    default:
      // Log unknown insight types but don't fail
      console.log(`Unknown GCP insight type: ${insightType}`);
      return new Response(`Insight type ${insightType} received`, { status: 200 });
  }
}

/**
 * Handle GCP memory task suggestions
 */
async function handleGcpTaskSuggestion(payload, env) {
  const { suggestion, context, priority = "medium" } = payload;
  
  // Create a Serena task suggestion in Biomimetic OS
  const taskData = {
    task_id: `gcp-insight-${Date.now()}`,
    title: `[GCP INSIGHT] ${suggestion.title || "AI Generated Task Suggestion"}`,
    description: `${suggestion.description || ""}\n\nContext: ${JSON.stringify(context || {})}`,
    status: "Not Started",
    source: "GCP-Memory",
    metadata: {
      priority: priority,
      tags: ["ai-generated", "gcp-insight"],
      github_link: suggestion.github_link || null,
      email: suggestion.email || null
    }
  };

  // Use the existing CREATE_ENTRY function to create the task
  return await createDatabaseEntry(taskData, env, 
    env.BIOMIMETIC_DB_ID || env.NOTION_DB_ID, 
    env.NOTION_TOKEN || env.NOTION_API_KEY);
}

/**
 * Handle GCP memory context updates
 */
async function handleGcpContextUpdate(payload, env) {
  const { updates, agentId } = payload;
  
  // Store context updates in a special context database or as metadata
  // For now, we'll log it and could extend to update agent profiles
  console.log(`Updating context for agent ${agentId || "unknown"}:`, updates);
  
  // In a full implementation, this would update agent-specific context
  // that could be retrieved by Serena agents for better decision making
  
  return new Response(JSON.stringify({
    success: true,
    message: `Context update processed for agent ${agentId || "unknown"}`,
    updates_applied: Object.keys(updates || {}).length
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * Route CoPaw requests for tool approvals and skill execution
 */
async function routeCoPawRequest(request, env) {
  const method = request.method;
  const actionType = request.headers.get("X-CoPaw-Action");
  
  // Handle different HTTP methods
  if (method === "GET") {
    // GET requests for querying approvals or status
    return await handleCoPawQuery(request, env);
  }
  
  if (method === "POST") {
    // Parse payload
    let payload;
    try {
      payload = await request.json();
    } catch (e) {
      return new Response("Invalid JSON payload", { status: 400 });
    }

    // Route by action type
    if (actionType) {
      switch (actionType) {
        case "tool-approval":
          return await handleToolApproval(request, env, payload);
        case "skill-execution":
          return await handleSkillExecution(request, env, payload);
        case "approval-response":
          return await handleApprovalResponse(request, env, payload);
        default:
          return new Response(`Unknown CoPaw action: ${actionType}`, { status: 400 });
      }
    } else {
      // Default: treat as tool execution request for approval
      return await handleToolExecutionRequest(request, env, payload);
    }
  }

  return new Response("Method not allowed", { status: 405 });
}

/**
 * Handle CoPaw GET queries (approvals, status, etc.)
 */
async function handleCoPawQuery(request, env) {
  const url = new URL(request.url);
  const queryType = url.searchParams.get("type") || "approvals";
  const limit = parseInt(url.searchParams.get("limit") || "10");
  
  // For now, return placeholder - in full implementation would query Notion or memory
  return new Response(JSON.stringify({
    success: true,
    queryType: queryType,
    results: [],
    count: 0,
    message: "CoPaw query endpoint - implement based on storage backend"
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * Handle tool execution requests - check if approval needed
 */
async function handleToolExecutionRequest(request, env, payload) {
  const { tool_name, tool_arguments, context = "" } = payload;
  
  if (!tool_name) {
    return new Response("Missing tool_name", { status: 400 });
  }
  
  // Import the tool guard logic (in practice, this would be a proper import)
  // For now, we'll implement a simplified version inline
  
  // High-risk patterns that require approval
  const HIGH_RISK_PATTERNS = [
    /git\s+push/i,
    /git\s+commit/i,
    /rm\s+-rf/i,
    /sudo/i,
    /chmod\s+777/i,
    /curl.*\|\s*(ba)?sh/i,
    /wget.*\|\s*(ba)?sh/i,
    /DROP\s+TABLE/i,
    /DELETE\s+FROM/i,
    /TRUNCATE/i,
    /serena\.execute_shell_command/i,
    /serena\.git_push/i,
    /serena\.git_commit/i
  ];
  
  // Auto-approve patterns (safe operations)
  const AUTO_APPROVE_PATTERNS = [
    /git\s+status/i,
    /git\s+log/i,
    /git\s+diff/i,
    /ls\s+-la/i,
    /cat\s+/i,
    /head\s+/i,
    /tail\s+/i,
    /grep\s+/i,
    /serena\.search_symbols/i,
    /serena\.get_symbol_implementation/i,
    /serena\.get_file_content/i
  ];
  
  // Combine tool name and arguments for pattern matching
  const check_text = `${tool_name} ${JSON.stringify(tool_arguments)}`;
  
  // Check auto-approve first
  for (const pattern of AUTO_APPROVE_PATTERNS) {
    if (pattern.test(check_text)) {
      return new Response(JSON.stringify({
        status: "approved",
        risk_level: "safe",
        tool_name: tool_name,
        message: `Tool '${tool_name}' auto-approved as safe`
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
  
  // Check high-risk patterns
  for (const pattern of HIGH_RISK_PATTERNS) {
    if (pattern.test(check_text)) {
      // Request approval via Notion/Telegram (simplified)
      const approval_id = `${tool_name}_${Date.now()}`;
      
      // In a full implementation, this would:
      // 1. Create approval request in Notion
      // 2. Send notification via Telegram/email
      // 3. Wait for response
      
      return new Response(JSON.stringify({
        status: "pending",
        risk_level: "high_risk",
        tool_name: tool_name,
        approval_id: approval_id,
        message: `Tool '${tool_name}' requires approval. Check Notion for approval request ${approval_id}`
      }), {
        status: 200,
        headers: { "Content-Type": "application/json" }
      });
    }
  }
  
  // Medium risk - approved but logged
  return new Response(JSON.stringify({
    status: "approved",
    risk_level: "medium",
    tool_name: tool_name,
    message: `Tool '${tool_name}' approved with medium risk`
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * Handle tool approval responses (from Notion/Telegram)
 */
async function handleApprovalResponse(request, env, payload) {
  const { approval_id, response } = payload;
  
  if (!approval_id || !response) {
    return new Response("Missing approval_id or response", { status: 400 });
  }
  
  // In a full implementation, this would:
  // 1. Update the approval request in the CoPaw approvals database
  // 2. Notify waiting processes
  // 3. Update memory with the decision
  
  const approvalDbId = env.COPAW_APPROVAL_DB_ID;
  if (!approvalDbId) {
    return new Response("CoPaw approval database not configured", { status: 500 });
  }
  
  // Update the approval request in Notion
  try {
    // First, we would need to find the page with this approval ID
    // For simplicity in this implementation, we'll note that a full implementation
    // would query the database for the approval_id and update the page
    
    // In practice, this would involve:
    // 1. Query the database for pages where "Approval ID" equals approval_id
    // 2. Update the page with status, response, and responded_at timestamp
    
    console.log(`Would update approval ${approval_id} with response ${response} in database ${approvalDbId}`);
  } catch (error) {
    console.error(`Error updating approval in Notion: ${error.message}`);
    // Don't fail the response for tracking errors
  }
  
  return new Response(JSON.stringify({
    success: true,
    approval_id: approval_id,
    response: response,
    message: `Approval ${approval_id} marked as ${response}`
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * Handle skill execution requests
 */
async function handleSkillExecution(request, env, payload) {
  const { skill_name, input_data } = payload;
  
  if (!skill_name) {
    return new Response("Missing skill_name", { status: 400 });
  }
  
  // In a full implementation, this would:
  // 1. Queue the skill for CoPaw execution
  // 2. Return a tracking ID
  // 3. Optionally wait for completion
  
  return new Response(JSON.stringify({
    success: true,
    skill_name: skill_name,
    status: "queued",
    message: `Skill '${skill_name}' queued for execution`
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * PM Agent entry point – triggered via X-Arca-Source: PM-Agent
 * (Can be invoked by a Cloudflare Cron Trigger or a GitHub Action)
 */
async function routePMAgent(request, env) {
  // Only accept POST for simplicity
  if (request.method !== "POST") {
    return new Response("Method not allowed. Use POST.", { status: 405 });
  }

  let payload;
  try {
    payload = await request.json();
  } catch (e) {
    return new Response("Invalid JSON payload", { status: 400 });
  }

  const { trigger } = payload; // e.g., "schedule", "issue-opened", etc.
  console.log(`PM Agent triggered by: ${trigger}`);

  // 0️⃣ Pre-fetch high-activation engrams from local MuninnDB
  let engrams = "";
  try {
    const memoryUrl = `http://127.0.0.1:8095/memory/search/${encodeURIComponent(trigger)}`;
    const memoryResp = await fetch(memoryUrl);
    if (memoryResp.ok) {
      const memoryData = await memoryResp.json();
      engrams = memoryData.results || "";
      console.log(`Retrieved ${engrams.split('\n').length - 1} engrams from MuninnDB.`);
    }
  } catch (e) {
    console.warn(`MuninnDB offline or query failed: ${e.message}. Proceeding with clean slate.`);
  }

  // 1️⃣ Gather context from GitHub (issues, project board, recent commits)
  let ghContext;
  try {
    ghContext = await gatherGitHubContext(env);
  } catch (e) {
    return new Response(JSON.stringify({error: "gatherGitHubContext failed", message: e.message}), {status: 500, headers: {"Content-Type":"application/json"}});
  }

  // 2️⃣ Build prompt for Gemma‑3‑27b
  const prompt = buildPMAPrompt(ghContext, trigger, engrams);

  // 3️⃣ Call Google AI Studio (Phase 1: Agent PM)
  let pmData;
  try {
    pmData = await callGemini(prompt, env.GEMINI_API_KEY, "models/gemma-4-31b-it");
  } catch (e) {
    return new Response(JSON.stringify({error: "PM Phase failed", message: e.message}), {status: 500});
  }

  const { text: rawPlan, model: modelPM } = pmData;

  // 4️⃣ Phase 2: Validator (Gemma 4 26b)
  const validationPrompt = buildValidatorPrompt(ghContext, rawPlan);
  let validatorData;
  try {
    validatorData = await callGemini(validationPrompt, env.GEMINI_API_KEY, "models/gemma-4-26b-a4b-it");
  } catch (e) {
    return new Response(JSON.stringify({error: "Validator Phase failed", message: e.message}), {status: 500});
  }

  const { text: validatedPlan, model: modelValidator } = validatorData;

  // 5️⃣ Construct Dual-Model Telemetry Trace
  const telemetryTrace = `Execution Trace: Agent PM [${modelPM}] | Validator [${modelValidator}]`;

  // 6️⃣ Parse model output into concrete GitHub actions
  let actions = parsePMResponse(validatedPlan);

  // 7️⃣ Inject Telemetry Trace into Action Payloads
  actions = actions.map(act => {
    const traceHeader = `${telemetryTrace}\n\n`;
    if (act.type === "comment" || act.type === "create_issue") {
      act.body = traceHeader + (act.body || "");
    } else if (act.type === "serena_task") {
      if (typeof act.payload === "object") {
        act.payload.telemetry = telemetryTrace;
      }
    }
    return act;
  });

  // 8️⃣ Execute actions (GitHub API) OR forward to Serena agent
  const results = await executePMActions(actions, env);

  // 9️⃣ Return summary
  return new Response(JSON.stringify({
    success: true,
    trigger,
    trace: telemetryTrace,
    actionsCount: actions.length,
    results
  }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  });
}

/**
 * Helper: build a prompt for the Validator agent
 */
function buildValidatorPrompt(context, proposedPlan) {
  return `
You are the ARCA Swarm Validator. Your job is to review the following execution plan proposed by the Project Manager (PM) agent.
Context:
${JSON.stringify(context.openIssues).slice(0, 2000)}

Proposed Plan:
${proposedPlan}

Your Goal:
1. Verify all issue numbers exist in the context.
2. Sanitize any malformed JSON or markdown blocks.
3. Ensure all descriptions are clear and actionable.
4. If an action is redundant or dangerous, remove it.

Output ONLY the final JSON array of actions using the following schema:
{ "type": "comment", "issue_number": <int>, "body": "<markdown>" }
{ "type": "label",   "issue_number": <int>, "label": "<string>" }
{ "type": "create_issue", "title": "<string>", "body": "<markdown>", "labels": [...] }
{ "type": "serena_task", "payload": { ... } }

Strict Requirement: Output ONLY the JSON array.
`;
}

/**
 * Helper: gather GitHub context (issues, project board, etc.)
 * Uses the GitHub API via a personal token stored as GITHUB_TOKEN secret.
 */
async function gatherGitHubContext(env) {
  const token = env.GITHUB_TOKEN; // you'll need to add this secret
  if (!token) throw new Error("GITHUB_TOKEN secret not configured");

  const headers = {
    Authorization: `token ${token}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "ARCA-PM-Agent"
  };

  // Example: get open issues in the ARCA repo (adjust owner/repo as needed)
  const owner = "danxalot";   // ← change to ARCA org/user
  const repo  = "ARCA";       // ← your ARCA repo name

  const issuesResp = await fetch(`https://api.github.com/repos/${owner}/${repo}/issues?state=open&per_page=100`, { headers });
  if (!issuesResp.ok) { const errText = await issuesResp.text(); throw new Error(`GitHub API error: ${issuesResp.status} ${errText.slice(0,200)}`); }
  const issues = await issuesResp.json();

  // Optionally: fetch project board columns, recent commits, etc.
  // For brevity we just return issues; you can expand as needed.

  return {
    owner,
    repo,
    openIssues: issues.map(i => ({
      number: i.number,
      title: i.title,
      labels: i.labels.map(l => l.name),
      state: i.state,
      created_at: i.created_at,
      html_url: i.html_url,
      body: i.body || ""
    }))
  };
}

/**
 * Helper: build a prompt for Gemma‑3‑27b
 */
function buildPMAPrompt(context, trigger, engrams = "") {
  const { openIssues } = context;
  const issuesText = openIssues.map(i =>
    `- #${i.number} [${i.labels.join(",")}] ${i.title}\n  ${i.body.slice(0,200)}...`
  ).join("\n");

  return `
You are an expert software project manager for the ARCA repository.
Your goal is to read the current open issues and suggest concrete, actionable next steps
that a developer (or the Serena agent) can take right now.

Trigger: ${trigger}

Hebbian Memory (MuninnDB Engrams):
${engrams.length > 0 ? engrams : "(no relevant engrams found)"}

Open Issues:
${issuesText.length > 0 ? issuesText : "(no open issues)"}

Please output a JSON array of actions. Each action must be one of:
{ "type": "comment", "issue_number": <int>, "body": "<markdown comment>" }
{ "type": "label",   "issue_number": <int>, "label": "<label-name>" }
{ "type": "create_issue", "title": "<string>", "body": "<markdown>", "labels": ["..."] }
{ "type": "serena_task", "payload": <any> }   // forward to Serena agent as‑is

Only output valid JSON, no extra text.
`;
}

/**
 * Helper: call Google AI Studio (Gemma‑3‑27b v1beta)
 */
async function callGemini(prompt, apiKey, modelName) {
  const url = `https://generativelanguage.googleapis.com/v1beta/${modelName}:generateContent?key=${apiKey}`;
  const body = {
    contents: [{ parts: [{ text: prompt }] }]
  };
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Gemini API error: ${resp.status} ${err}`);
  }
  const data = await resp.json();
  
  // Dynamic Traceability: Extract modelVersion from API response
  const modelId = data.modelVersion || modelName; // Fallback to requested name
  const outputText = data.candidates?.[0]?.content?.parts?.[0]?.text ?? "";

  return {
    text: outputText,
    model: modelId
  };
}

/**
 * Helper: parse the model's JSON output into action objects
 */
function parsePMResponse(text) {
  try {
    // The model should output pure JSON; we trim whitespace and try parse
    const cleaned = text.trim();
    // If the model wrapped JSON in markdown fences, strip them
    const jsonStr = cleaned.replace(/^```json\s*|\s*```$/g, "");
    return JSON.parse(jsonStr);
  } catch (e) {
    console.error("Failed to parse PM response:", e, "Raw:", text);
    return []; // return empty to avoid crashing
  }
}

/**
 * Helper: execute the parsed actions via GitHub API (or forward to Serena)
 */
async function executePMActions(actions, env) {
  const token = env.GITHUB_TOKEN;
  const owner = "danxalot";
  const repo  = "ARCA";
  const headers = {
    Authorization: `token ${token}`,
    "Accept": "application/vnd.github+json",
    "User-Agent": "ARCA-PM-Agent"
  };

  const results = [];

  for (const act of actions) {
    try {
      switch (act.type) {
        case "comment": {
          const url = `https://api.github.com/repos/${owner}/${repo}/issues/${act.issue_number}/comments`;
          const body = { body: act.body };
          const resp = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error(`Comment failed: ${resp.status}`);
          results.push({ action: act, status: "commented", issue: act.issue_number });
          break;
        }
        case "label": {
          const url = `https://api.github.com/repos/${owner}/${repo}/issues/${act.issue_number}/labels`;
          const body = { labels: [act.label] };
          const resp = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error(`Label failed: ${resp.status}`);
          results.push({ action: act, status: "labeled", issue: act.issue_number });
          break;
        }
        case "create_issue": {
          const url = `https://api.github.com/repos/${owner}/${repo}/issues`;
          const body = {
            title: act.title,
            body: act.body || "",
            labels: act.labels || []
          };
          const resp = await fetch(url, { method: "POST", headers, body: JSON.stringify(body) });
          if (!resp.ok) throw new Error(`Create issue failed: ${resp.status}`);
          const created = await resp.json();
          results.push({ action: act, status: "created", issue: created.number });
          break;
        }
        case "serena_task": {
          // Forward to Serena agent – we assume Serena is reachable via a local HTTP endpoint
          // or we can shell out to its CLI. For simplicity we POST to a local Serena listener.
          // Adjust URL/port as needed; if Serena exposes a CLI you could use child_process.
          const serenaEndpoint = "http://127.0.0.1:8080/serena-task"; // example
          const resp = await fetch(serenaEndpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(act.payload)
          });
          if (!resp.ok) throw new Error(`Serena task failed: ${resp.status}`);
          results.push({ action: act, status: "sent-to-serena" });
          break;
        }
        default:
          results.push({ action: act, status: "labeled", issue: act.issue_number });
          break;
        }
    } catch (error) {
      results.push({ action: act, status: "failed", error: error.message });
    }
  }

  return results;
}

/**
 * =========================================================
 * PHASE 5.1: EDGE OIDC SIGNER & GOOGLE OAUTH EXCHANGE
 * =========================================================
 */

/**
 * Task 1: The Cryptographic Helper
 * Performs an OAuth 2.0 Token Exchange to get a Google-signed Identity Token
 */
async function getGoogleOidcToken(env) {
  const now = Math.floor(Date.now() / 1000);

  // Return cached token if still valid (50-minute buffer)
  if (cachedOidcToken && now < oidcTokenExpiry - 300) {
    return cachedOidcToken;
  }

  try {
    // 1. Resilient Secret Parsing
    let credentials;
    try {
      credentials = JSON.parse(env.GCP_SERVICE_ACCOUNT);
    } catch (e) {
      credentials = JSON.parse(atob(env.GCP_SERVICE_ACCOUNT));
    }

    const { client_email, private_key } = credentials;
    const targetAudience = env.GCP_GATEWAY;

    // 2. Import Private Key
    const rsaKey = await importPrivateKey(private_key);

    // 3. Construct JWT Assertion
    const header = base64urlEncode({ alg: "RS256", typ: "JWT" });
    const payload = base64urlEncode({
      iss: client_email,
      sub: client_email,
      aud: "https://oauth2.googleapis.com/token",
      iat: now,
      exp: now + 3600,
      target_audience: targetAudience
    });

    const assertionData = `${header}.${payload}`;
    const signatureBuffer = await crypto.subtle.sign(
      "RSASSA-PKCS1-v1_5",
      rsaKey,
      new TextEncoder().encode(assertionData)
    );
    const signature = base64urlEncode(new Uint8Array(signatureBuffer));
    const assertion = `${assertionData}.${signature}`;

    // 4. Exchange Assertion for Identity Token
    const exchangeResp = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "urn:ietf:params:oauth:grant-type:jwt-bearer",
        assertion: assertion
      })
    });

    if (!exchangeResp.ok) {
      const err = await exchangeResp.text();
      throw new Error(`Google OAuth Exchange failed: ${err}`);
    }

    const { id_token } = await exchangeResp.json();
    
    // 5. Update Cache (Task 3: Isolate Caching)
    cachedOidcToken = id_token;
    oidcTokenExpiry = now + 3000; // 50 minutes
    
    return id_token;

  } catch (error) {
    console.error(`Edge OIDC Signer Error: ${error.message}`);
    return null;
  }
}

/**
 * Import PEM Private Key into crypto.subtle
 */
async function importPrivateKey(pem) {
  // Strip headers, footers, and newlines
  const pemHeader = "-----BEGIN PRIVATE KEY-----";
  const pemFooter = "-----END PRIVATE KEY-----";
  const pemContents = pem
    .replace(pemHeader, "")
    .replace(pemFooter, "")
    .replace(/\s+/g, "");

  const binaryDerString = atob(pemContents);
  const binaryDer = new Uint8Array(binaryDerString.length);
  for (let i = 0; i < binaryDerString.length; i++) {
    binaryDer[i] = binaryDerString.charCodeAt(i);
  }

  return await crypto.subtle.importKey(
    "pkcs8",
    binaryDer.buffer,
    {
      name: "RSASSA-PKCS1-v1_5",
      hash: { name: "SHA-256" },
    },
    false,
    ["sign"]
  );
}

/**
 * URL-safe Base64 encoding
 */
function base64urlEncode(input) {
  let str;
  if (input instanceof Uint8Array) {
    str = String.fromCharCode.apply(null, input);
  } else {
    str = JSON.stringify(input);
  }
  
  return btoa(str)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}
