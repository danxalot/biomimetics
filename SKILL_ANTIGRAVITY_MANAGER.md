# Skill: Antigravity Manager Agent

## Overview
This skill transforms the Antigravity IDE Agent into a specialized **Worker Agent** within the BiOS Swarm. It allows the IDE to autonomously pull and execute high-context engineering tasks from the **ARCA Tasks** Notion database.

## Activation
At the start of a session, if no specific task is assigned, run the following command to claim a mission:
```bash
python3 /Users/danexall/biomimetics/scripts/copaw/antigravity_manager.py
```

## Workflow
1.  **Poll**: The `antigravity_manager.py` script queries Notion for tasks where `Status == Ready for Dev` and `Execution_Tier == Antigravity`.
2.  **Claim**: The script sets the task status to `In Progress` in Notion, signaling to the rest of the swarm that the IDE has claimed the work.
3.  **Execute**: I (Antigravity) parse the mission brief, perform the necessary research, and execute the architectural or code changes locally.
4.  **Sync**: Upon completion, I update the Notion Task card with execution logs and transition the status to `Ready for Sync` for the **Archivist** to ingest into the Obsidian vault.

## Schemas
- **Database ID**: `3284d2d9fc7c811188deeeaba9c5f845`
- **Execution Tier**: `Antigravity` (High-context, local modification tasks).
- **Status Flow**: `Ready for Dev` -> `In Progress` -> `Ready for Sync` (Archivist Sweep) -> `Done`.
