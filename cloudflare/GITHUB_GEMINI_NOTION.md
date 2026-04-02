# GitHub → Gemini → Notion Integration (The Planner)

## Overview

This integration automatically parses GitHub issues using **Gemini 3.1 Flash Lite Preview** (free tier) and creates structured "Ready for Dev" tasks in the Biomimetic OS Notion database.

## Architecture

```
GitHub Issue Created
       ↓
Cloudflare Worker (webhook receiver)
       ↓
Gemini 3.1 Flash Lite Preview API (AI parsing)
       ↓
Notion API (create "Ready for Dev" task)
       ↓
GCP Memory Gateway (store context)
```

## Features

- ✅ **Free AI Processing**: Uses Gemini 3.1 Flash Lite Preview free tier
- ✅ **Structured Output**: JSON parsing for consistent formatting
- ✅ **Auto-Prioritization**: Detects priority from issue content
- ✅ **Ready for Dev**: Creates immediately actionable tasks
- ✅ **Fallback Mode**: Basic sync if Gemini unavailable

## Setup

### 1. Get Gemini API Key

1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)
2. Create API key
3. Copy the key

### 2. Deploy to Cloudflare Worker

```bash
cd /Users/danexall/biomimetics/cloudflare

# Login to Cloudflare
wrangler login

# Set Gemini API key secret
wrangler secret put GEMINI_API_KEY

# Deploy worker
wrangler deploy
```

### 3. Configure GitHub Webhook

1. Go to GitHub repository → Settings → Webhooks
2. Add webhook:
   - **Payload URL**: `https://arca-github-notion-sync.<your-subdomain>.workers.dev`
   - **Content type**: `application/json`
   - **Secret**: Your webhook secret (set via `wrangler secret put GITHUB_WEBHOOK_SECRET`)
   - **Events**: Select "Issues"

### 4. Test the Integration

Create a test issue in GitHub:

```markdown
## Test Issue for Gemini Parsing

We need to add user authentication to the app.

### Requirements
- Support Google OAuth
- Store tokens securely in keychain
- Add logout functionality

### Acceptance Criteria
- User can sign in with Google
- Session persists across restarts
- Logout clears session

This is high priority for the MVP launch next week!
```

Expected Notion task:
- **Title**: ✨ [Ready for Dev] Test Issue for Gemini Parsing
- **Status**: Ready for Dev
- **Priority**: High (detected from "high priority" and "next week")
- **Complexity**: Medium
- **Description**: Formatted with summary, requirements, and acceptance criteria

## Gemini Prompt

The worker sends this prompt to Gemini:

```
You are a technical requirements analyst for a software development team.
Analyze this GitHub issue and extract technical requirements.

GitHub Issue:
- Title: {issue.title}
- Repository: {repository.full_name}
- Author: {issue.user.login}
- Labels: {labels}

Description:
{issue.body}

Extract and format the following:
1. **Summary**: One-sentence summary
2. **Technical Requirements**: Bullet list
3. **Acceptance Criteria**: Bullet list
4. **Dependencies**: Any mentioned dependencies
5. **Priority**: Low/Medium/High

Respond in valid JSON format:
{
  "summary": "...",
  "technical_requirements": ["req1", "req2"],
  "acceptance_criteria": ["criteria1", "criteria2"],
  "dependencies": ["dep1", "dep2"],
  "priority": "Medium",
  "estimated_complexity": "Low/Medium/High"
}
```

## Notion Database Properties

The worker creates tasks with these properties:

| Property | Type | Value |
|----------|------|-------|
| Name | Title | `✨ [Ready for Dev] {issue title}` |
| Status | Status | `Ready for Dev` |
| Priority | Select | `Low` / `Medium` / `High` |
| Complexity | Select | `Low` / `Medium` / `High` |
| Description | Rich Text | Formatted markdown with requirements |
| Source | Rich Text | `GitHub: {repository}` |
| Github Link | URL | Issue URL |
| Memory_UUID | Rich Text | Unique identifier |
| Timestamp | Date | Issue creation date |

## Response Format

### Success Response

```json
{
  "success": true,
  "notion_page_id": "abc123...",
  "issue_number": 42,
  "parsed_by": "gemini-flash-lite",
  "summary": "Add user authentication with Google OAuth",
  "priority": "High"
}
```

### Fallback Response (Gemini unavailable)

```json
{
  "success": true,
  "notion_page_id": "xyz789...",
  "issue_number": 42,
  "parsed_by": "basic"
}
```

## Error Handling

| Error | Cause | Resolution |
|-------|-------|------------|
| `GEMINI_API_KEY not configured` | Secret not set | Run `wrangler secret put GEMINI_API_KEY` |
| `Gemini API error: 403` | Invalid API key | Check key in Google AI Studio |
| `Notion API Error: 403` | Invalid Notion token | Run `wrangler secret put NOTION_API_KEY` |
| `Invalid webhook signature` | Wrong secret | Ensure GitHub webhook secret matches `GITHUB_WEBHOOK_SECRET` |

## Monitoring

### View Logs

```bash
# Real-time logs
wrangler tail

# Filter by issue parsing
wrangler tail | grep "Gemini"
```

### Check Worker Health

```bash
curl https://arca-github-notion-sync.<your-subdomain>.workers.dev/health
```

## Cost

| Component | Free Tier | Your Usage |
|-----------|-----------|------------|
| Gemini 3.1 Flash Lite Preview | 1M tokens/day | ~500 tokens/issue |
| Cloudflare Worker | 100K requests/day | ~100-500/day |
| **Monthly Cost** | **$0** | **$0** |

## Troubleshooting

### Issue not creating Notion task

1. Check worker logs: `wrangler tail`
2. Verify database ID in `wrangler.toml`
3. Ensure Notion integration has access to database

### Gemini returning invalid JSON

1. Check issue has description
2. Verify Gemini API key is valid
3. Check worker logs for parsing errors

### Webhook not triggering

1. Verify webhook URL is correct
2. Check webhook secret matches
3. Test with GitHub's "Redeliver" feature

## Related Documentation

- [PROJECT_WIKI.md](../PROJECT_WIKI.md) - Full system documentation
- [Cloudflare Worker Docs](https://developers.cloudflare.com/workers/)
- [Gemini API Docs](https://ai.google.dev/api)
