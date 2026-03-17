export default {
  async fetch(request, env) {
    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const payload = await request.json();
    
    // We only care about issue events
    if (!payload.issue) {
      return new Response("Ignored: Not an issue event", { status: 200 });
    }

    const action = payload.action; // 'opened', 'edited', 'closed'
    const issue = payload.issue;
    
    // Map GitHub status to Notion Status
    let notionStatus = "Not Started";
    if (issue.state === "closed") notionStatus = "Done";
    if (action === "edited" && issue.state === "open") notionStatus = "In Progress";

    const notionData = {
      parent: { database_id: env.NOTION_DB_ID },
      properties: {
        "Name": {
          title: [{ text: { content: issue.title } }]
        },
        "Status": {
          status: { name: notionStatus }
        },
        "Github Link": {
          url: issue.html_url
        },
        "Description": {
          rich_text: [{ text: { content: issue.body ? issue.body.substring(0, 500) : "No description" } }]
        }
      }
    };

    // Push to Notion
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

    return new Response("Successfully synced to Notion", { status: 200 });
  }
};
