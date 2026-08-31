# -*- coding: utf-8 -*-
"""Project Management tools for CoPaw agent.
Proxies requests to the local dispatcher to ensure secret handling parity.
"""
import logging
import httpx
from agentscope.tool import ToolResponse
from agentscope.message import TextBlock

logger = logging.getLogger(__name__)

DISPATCHER_URL = "http://127.0.0.1:8090/api/mcp/tool/execute"

def create_pm_tools():
    """Factory for PM-related agent tools."""

    async def _execute_proxy(name: str, arguments: dict) -> str:
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    DISPATCHER_URL,
                    json={"name": name, "arguments": arguments}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    return str(data.get("result", "Operation successful."))
                else:
                    return f"Error: Dispatcher returned {resp.status_code} - {resp.text}"
        except Exception as e:
            logger.error(f"PM Dispatcher proxy error: {e}")
            return f"Internal dispatch error: {str(e)}"

    async def dispatch_pm_brief(
        title: str,
        description: str,
        repo: str = "danxalot/biomimetics"
    ) -> ToolResponse:
        """
        Record a new engineering requirement, project goal, or task brief. 
        STRATEGY: GitHub-First (Ingestion via Issue → Cloudflare → Notion).
        
        REQUIRED: You must have final verbal or written authorization from the user before committing this.

        Args:
            title (str): Clear, descriptive title for the issue/task.
            description (str): Detailed engineering brief or requirement.
            repo (str, optional): GitHub repository. Defaults to "danxalot/biomimetics".

        Returns:
            ToolResponse: Confirmation of GitHub issue creation (Capture 201).
        """
        owner, repo_name = repo.split("/", 1)
        args = {
            "owner": owner,
            "repo": repo_name,
            "title": title,
            "body": description
        }
        
        # PRIMARY: GitHub-First Ingestion
        result = await _execute_proxy("create_issue", args)
        
        if "201" in result or "successful" in result.lower():
            return ToolResponse(content=[TextBlock(type="text", text=f"PM Brief committed via GitHub-First Strategy. Result: {result}")])
        else:
            # FALLBACK: Degraded Mode Direct Notion Sync
            logger.warning(f"PM: GitHub-First failed ({result}), falling back to direct Notion sync.")
            notion_args = {"title": title, "status": "Ready for Dev", "content": description}
            notion_result = await _execute_proxy("notion_create_task", notion_args)
            return ToolResponse(content=[TextBlock(type="text", text=f"PM Brief fallback executed (DEGRADED MODE). GitHub Error: {result} | Notion Result: {notion_result}")])

    async def update_notion_task_status(task_id: str, status: str) -> ToolResponse:
        """
        Update the status of a Notion task (e.g. to 'Ready for Dev' or 'In Progress').

        Args:
            task_id (str): The unique Notion page/task ID.
            status (str): The target status name (e.g. 'Ready for Dev', 'In Progress').

        Returns:
            ToolResponse: Confirmation of update.
        """
        args = {"task_id": task_id, "status": status}
        result = await _execute_proxy("update_notion_task_status", args)
        return ToolResponse(content=[TextBlock(type="text", text=f"Notion status updated. Result: {result}")])

    return dispatch_pm_brief, update_notion_task_status
