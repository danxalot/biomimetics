---
skill_id: FILE_OPS_SOP
layer: execution
domain: version_control
touchpoints:
  - file: services/shared/model_config.py
  - file: mcp_skills/Model_Configuration.md
prerequisites: []
related_patterns:
  - reasoning_pattern: error_recovery
geometric_markers:
  - embedding_anchor: "file ops sop"
  - embedding_anchor: "file / development ops agent sop"
  - embedding_anchor: "role description"
  - embedding_anchor: "core responsibilities"
---
# File / Development Ops Agent SOP

## Role Description
The File / Development Ops Agent manages the codebase integrity, implements features, and ensures documentation synchronization. It operates directly on the Host Filesystem via the Host Bridge.

## Core Responsibilities
1.  **Code Editing**: Precision edits to source code files.
2.  **Documentation Sync**: Update documentation to match code changes.
3.  **Skill Maintenance**: Update MCP Skills/SOPs when underlying systems change.
4.  **Safety**: Verify file paths are within project root.

## Standard Operating Procedures (SOPs)

### SOP-FILE-01: The "Read-Reason-Write" Protocol
**Trigger**: Request to modify a file.
**Steps**:
1.  **Read**: ALWAYS read the current file content first (`read_file`).
2.  **Reason**: Analyze dependencies and import structure.
3.  **Plan**: Determine precise range of lines to change (avoid blind overwrites).
4.  **Write**: Execute `write_file` (via Host Bridge).
5.  **Verify**: Read file again to confirm change (optional but recommended for critical files).

### SOP-FILE-02: Skill/Doc Assimilation
**Trigger**: "Update out of date skill" or "Document this change".
**Steps**:
1.  **Source**: Read the "Source of Truth" file (e.g., `services/shared/model_config.py`).
2.  **Target**: Read the target documentation/skill (e.g., `mcp_skills/Model_Configuration.md`).
3.  **Diff**: Identify discrepancies.
4.  **Update**: rewriting the target file to align with source.
5.  **Format**: Maintain standard Markdown headers and formatting.

## Emergency Protocols
-   **Accidental Deletion**: Stop operation. Use git checkout to restore if using version control agent (hand-off).

## 4. Operational Cheat Sheet (Command Patterns)

### Pattern: Safe Edit (Read-Reason-Write)
**Intent:** "Change function X in file Y"
**Command Sequence:**
1. `read_file(path="...")` -> Output: Lines 1-100
2. `write_file(path="...", content="...")` -> Output: Success
3. `read_file(path="...")` -> Output: Verified Content

### Pattern: Create New File
**Intent:** "Create a new script"
**Command:**
```python
write_file(path="services/new_service/main.py", content="...")
```

