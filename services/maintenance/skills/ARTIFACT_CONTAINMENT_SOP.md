# Artifact Containment & Hygiene SOP

**Version**: 2.0 (Enforced)
**Criticality**: HIGH - Failure to follow leads to "Virus" (Container Bloat)

## 🛑 THE GOLDEN RULE

**NEVER** build a Docker image without first scanning the directory for artifacts.
**NEVER** commit large binaries, archives, or nested repositories to Git.

---

## 🔍 Pre-Build Protocol (MANDATORY)

Before running `docker build`:

1. **Run the Scanner**:

   ```bash
   ./scripts/pre_build_scan.sh services/<target_service>
   ```

   * If it fails (❌), **STOP**. Delete the forbidden files.
   * If it passes (✅), proceed.
2. **Check .dockerignore**:

   * Verify the service directory does NOT contain `tar.gz`, `venv`, or `arca_source`.
   * If uncertain, add them to `.dockerignore` explicitly.

---

## 🧹 Housekeeping Protocol

When finishing a task:

1. **Clean Up**:

   ```bash
   rm -rf services/<target_service>/build/
   rm -rf services/<target_service>/dist/
   rm -rf services/<target_service>/*.tar.gz
   ```
2. **Verify Git Status**:

   ```bash
   git status
   ```

   * Ensure no huge files are staged.

---

## 🚫 Forbidden Items (The "Virus" List)

Do not allow these into the build context:

* `arca_source/` (Nested repo copies)
* `.secrets/` (API Keys)
* `*API* / *TOKEN*`
* `*.tar.gz` / `*.zip` (Archives)
* `venv/` / `.venv/` (Local environments)
* `__pycache__/`
* `models/*.gguf` (Unless strictly required for baking, prefer external mounts)

## Troubleshooting

- **"Build context is huge (GBs)"**: You failed this SOP. Cancel build. Check for `tar.gz` or nested `arca_source`.
- **"Copy failed / file not found"**: Check `.dockerignore`.

---

**Linked Policies**: `PROJECT_ARTIFACT_POLICIES.md`
