# PM Agent (Project Manager Agent) Specification

## Overview
The PM Agent is an AI-powered project management agent that uses Google's Gemma‑3‑27b model (via AI Studio v1beta) to analyze the current state of the ARCA GitHub repository and suggest concrete, actionable next steps. The agent runs as a Cloudflare Worker (triggered on a schedule or manually) and can either execute GitHub actions directly (comment, label, create_issue) or forward recommended tasks to the Serena agent for execution.

## Goals
- Reduce manual project management overhead by automating triage and suggestion generation.
- Leverage large‑language‑model reasoning to identify high‑impact work (e.g., blocking issues, technical debt, refactoring opportunities).
- Integrate tightly with the existing Serena agent so that approved actions are carried out in the codebase (file edits, test runs, etc.).
- Keep all secrets (API keys, tokens) in Azure Key Vault, with zero plaintext exposure in source control.

## Triggers
The PM Agent is invoked via an HTTP POST to the Cloudflare Worker endpoint with the header:
```
X-Arca-Source: PM-Agent
```
and a JSON body:
```json
{
  "trigger": "schedule"   // or "manual-test", "issue-opened", etc.
}
```
A cron trigger is configured to run every 6 hours (`0 */6 * * *`).

## Inputs
### 1. Environment Variables (injected via Azure Key Vault → wrangler secrets)
| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google AI Studio API key for model `gemma-3-27b` |
| `GITHUB_TOKEN`   | GitHub personal access token with `repo` scope (or at least `issues`, `pull_requests`, `contents` write) for the ARCA repository |
| `NOTION_API_KEY` / `NOTION_TOKEN` | (Already present) Used for logging to Notion if needed |
| `GCP_GATEWAY`    | (Already present) URL of GCP memory system (used for forwarding updates) |
| `COPAW_APPROVAL_DB_ID` | (Already present) Notion DB ID for CoPaw approvals |

### 2. Runtime Payload (POST body)
| Field | Type | Description |
|-------|------|-------------|
| `trigger` | string | Arbitrary label indicating why the agent was run (e.g., `"schedule"`, `"issue-opened:#42"`). Not used in logic but logged for traceability.

### 3. Data Fetched at Runtime
The agent makes authenticated calls to the GitHub API to gather context:
- **Open issues** (state=open, per_page=100) in the ARCA repository (owner/repo configurable in code; currently `danxalot/ARCA`).
Each issue provides:
  - `number`, `title`, `body`, `state`, `labels` (array of label names), `html_url`, `created_at`, `user.login`.

## Outputs / Effects
The PM Agent returns a JSON response:
```json
{
  "success": true,
  "trigger": "<string>",
  "actionsCount": <int>,
  "results": [ ... ]   // array of action result objects
}
```
Each element in `results` corresponds to one action attempted and contains:
```json
{
  "action": { ...original action object... },
  "status": "<string>",   // e.g., "commented", "labeled", "created", "sent-to-serena", "error"
  "issue": <int|optional>, // issue number if applicable
  "error": "<string|optional>" // present only on error
}
```

### Action Types the PM Agent May Generate
The Gemma‑3‑27b model is prompted to output a JSON array where each element is one of:

| Type | Fields | Effect |
|------|--------|--------|
| `comment` | `issue_number` (int), `body` (string) | Posts a comment on the given GitHub issue. |
| `label` | `issue_number` (int), `label` (string) | Adds the given label to the issue. |
| `create_issue` | `title` (string), `body` (string|optional), `labels` (array of string|optional) | Creates a new issue in the ARCA repository. |
| `serena_task` | `payload` (any) | Forwards the payload to the Serena agent for execution. The exact schema of `payload` is defined by the Serena agent; the PM agent treats it as an opaque blob. |

If the model outputs anything else, the agent treats it as a parse error and returns an empty action list.

## Side Effects
- **GitHub**: May create comments, add labels, or create new issues.
- **Notion**: If a `serena_task` is forwarded and Serena logs to Notion (via its own integration), Notion may be updated indirectly.
- **GCP Memory System**: The worker already forwards all GitHub events (issues, PRs, pushes) to the GCP memory system; the PM agent does **not** currently add extra forwarding, but the existing `forwardToGcpMemory` calls remain in place for other event types.
- **Serena**: Receives a task payload and performs whatever action the Serena agent is programmed to do (e.g., edit a file, run a test, update an issue, etc.).
- **Logs**: All actions and errors are logged to Cloudflare Worker logs (accessible via `wrangler tail`).

## Error Handling
- If required secrets (`GEMINI_API_KEY`, `GITHUB_TOKEN`) are missing, the worker returns a 500 error.
- If the GitHub API call to fetch open issues fails, the agent logs the error and proceeds with an empty issue list (thus likely suggesting no actions).
- If the Gemma‑3‑27b API returns a non‑200 status, the agent logs the error and returns an empty action list.
- If the model output cannot be parsed as valid JSON, the agent logs the raw output and returns an empty action list.
- Each individual action is wrapped in a try/catch; failures are recorded in the `results` array with `status: "error"` and an `error` message, but processing continues for remaining actions.

## Security & Secrets
- All API keys and tokens are stored exclusively in Azure Key Vault.
- The `azure_secrets_init.py` script pulls them at runtime (or on refresh) and injects them into:
  - The Cloudflare Worker environment (via `wrangler secret put`).
  - Local configuration files (`omni_sync_config.json`).
  - Notion MCP config files (for Claude Desktop, Qwen Code, etc.).
  - Encrypted local backup (`secrets/azure_secrets.json`).
- No secrets are hard‑coded in the source tree.

## Dependencies
- Cloudflare Workers runtime (Node.js compatible).
- `axios` or native `fetch` for HTTP calls (built‑in).
- No external npm packages are required; the worker uses only built-in APIs.

## Performance & Limits
- The agent is designed to complete within the Cloudflare Worker CPU time limit (typically 50ms CPU time; wall‑clock limit ~30s). The most expensive operation is the call to Gemma‑3‑27b, which is expected to complete within a few seconds.
- The GitHub API call for open issues is lightweight (≤100 issues).
- The agent respects GitHub rate limits via the provided `GITHUB_TOKEN` (5000 requests/hour for authenticated requests).
- Google AI Studio quota applies (check your plan for Gemma‑3‑27b v1beta).

## Testing
### Manual Test
```bash
curl -X POST https://arca-github-notion-sync.dan-exall.workers.dev \
  -H "Content-Type: application/json" \
  -H "X-Arca-Source: PM-Agent" \
  -d '{"trigger": "manual-test"}'
```
Expected response shape:
```json
{
  "success": true,
  "trigger": "manual-test",
  "actionsCount": <number >= 0>,
  "results": [ ... ]
}
```
Inspect `wrangler tail arca-github-notion-sync` for logs showing:
- Context gathering from GitHub,
- Prompt sent to Gemini,
- Model output,
- Parsed actions,
- Execution results.

### End‑to‑End Test (with Serena)
1. Ensure Serena is listening for tasks (e.g., running a local HTTP endpoint at `http://127.0.0.1:8080/serena-task` or exposing a CLI).
2. Trigger the PM agent as above.
3. Verify that any `serena_task` actions result in a `status: "sent-to-serena"` (or similar) in the response.
4. Check Serena logs or the ARCA repository for the expected side effect (file change, comment, etc.).

### Automated Test (Cron)
The agent runs every 6 hours automatically. Verify that after a few cycles, new comments/labels/issues appear in the ARCA repository that correspond to the agent’s suggestions.

## Future Enhancements
- Allow the PM agent to accept a list of repositories or a query to restrict issue gathering.
- Add support for labeling based on AI‑suggested priority or area.
- Enable the PM agent to close stale issues or suggest stale‑issue cleanup.
- Integrate with the CoPaw approval workflow for high‑risk actions (e.g., issue creation, label changes) if desired.
- Expose a Prometheus metric for actions taken vs. suggested.

## References
- Cloudflare Worker code: `/Users/danexall/biomimetics/cloudflare/index.js` (look for `routePMAgent` and helpers).
- Azure secrets update script: `/Users/danexall/biomimetics/azure/azure_secrets_init.py`.
- Serena agent location: `/Users/danexall/Documents/VS Code Projects/ARCA/services/ui_term/` (see `serena_graph.py`, `main.py`, etc.).
