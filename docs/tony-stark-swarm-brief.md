---
tags: ["#bios/architecture", "#bios/swarm", "#bios/infrastructure"]
status: active
---

# Tony Stark Swarm - Meta-Cognitive Project Development System

## Executive Summary

The Tony Stark Swarm is a meta-cognitive model orchestration system that deploys the right AI model for the right task, maximizing effectiveness while minimizing cost. Named after Tony Stark's JARVIS/FRIDAY system, it coordinates multiple AI models to work together as an intelligent development swarm. ` #bios/architecture #bios/architecture/component #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/component #bios/meta #bios/meta/operational

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     AGENT PM (Cloudflare Worker)                  │
│              Routes GitHub Issues → Task Briefs                   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                 TASK BRIEF GENERATOR (Stark Swarm)               │
│           Analyzes task → Creates brief → Routes to model         │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    MODEL ORCHESTRATION LAYER                     │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Conversational│  │    Code      │  │   Premium    │          │
│  │  (Free Rot.) │  │   (Free)     │  │  (Paid)     │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│        │                 │                 │                    │
│        ▼                 ▼                 ▼                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Gemini Flash │  │ Kimi K2.5    │  │ Kimi K2.5 Go │          │
│  │ MiniMax 2.5  │  │ Qwen 122B    │  │ GLM-5        │          │
│  │ Nemotron 3   │  │ Nemotron     │  │ Claude 3.7/4 │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      SERENA MCP SERVER                           │
│              Multi-model project analysis                        │
│         Each model contributes unique perspective                 │
└─────────────────────────────────────────────────────────────────┘
```

## Model Tiers

### TIER 0: Free Conversational (Daily Rotation)
| Model | Provider | Strengths | Daily Quota |
|-------|----------|-----------|-------------|
| Gemini 2.5 Flash | Google | Fast, multimodal | 1500 |
| MiniMax 2.5 Free | OpenCode Zen | Concise, good code | 500 |
| Super Nemotron 3 | OpenCode Zen | Thorough, precise | 100 | #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

**Strategy**: Rotate between models every 4 hours for varied perspectives while maintaining context. `).    `

### TIER 1: Free Code/Reasoning
| Model | Provider | Strengths | Daily Quota |
|-------|----------|-----------|-------------|
| Kimi K2.5 | OpenRouter | Error detection, long context | 100 |
| Qwen 3 122B | OpenRouter | Wide knowledge, speed | 50 |
| Nemotron 3 | OpenCode Zen | Rigorous implementation | 100 | #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

**Strategy**: Use for project-wide analysis and complex reasoning.

### TIER 2: Paid Subscriptions
| Model | Provider | Strengths | Monthly Quota |
|-------|----------|-----------|---------------|
| Kimi K2.5 | OpenCode Go | Code analysis, architecture | 6000 |
| GLM-5 | OpenCode Go | Planning, complex reasoning | 6000 |
| MiniMax M2.7 | OpenCode Go | Advanced reasoning | 3000 | #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

**Strategy**: Use sparingly for complex architecture, task brief creation.

### TIER 3: GitHub Pro
| Model | Provider | Strengths | Monthly Quota |
|-------|----------|-----------|---------------|
| Claude 3.7 Sonnet | GitHub Copilot | Code generation, review | 15000 |
| Claude 4.6 Opus | GitHub Copilot | Complex orchestration | 6000 | #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

**Strategy**: Use for GitHub-integrated tasks, top-tier reasoning.

## Task Routing Matrix

| Task Type | Primary Model | Review Model | Quota Priority |
|-----------|--------------|--------------|----------------|
| CONVERSATION | Gemini Flash | - | Free tier |
| ANALYSIS | Kimi K2.5 | Nemotron | Tier 1-2 |
| IMPLEMENTATION | Nemotron 3 | Claude 3.7 | Tier 1-3 |
| REASONING | MiniMax M2.7 | Kimi K2.5 | Tier 2-3 |
| CREATION (Briefs) | GLM-5 | - | Tier 2 |
| REVIEW | Kimi K2.5 | Nemotron | Tier 1 |
| ROUTING (Orchestration) | Claude 4.6 | - | Tier 3 | #bios/architecture #bios/architecture/config #bios/personal_assistant #bios/personal_assistant/routing #bios/architecture #bios/architecture/config #bios/personal_assistant #bios/personal_assistant/routing

## Key Insight: Multi-Model Analysis

Kilo Code demonstrated that each model finds things others miss. The swarm approach:

1. **Primary Analysis**: One model performs main analysis
2. **Secondary Scan**: Different model finds missed issues
3. **Quality Gate**: Third model reviews for errors
4. **Consensus**: Final model synthesizes findings    #bios/architecture #bios/architecture/component #bios/personal_assistant #bios/personal_assistant/memory #bios/architecture #bios/architecture/component #bios/personal_assistant #bios/personal_assistant/memory

This is why Serena MCP with multiple models outperforms single-model analysis.    `. `

## Usage Examples

### Generate Task Brief
```bash
python scripts/swarm/task_brief_generator.py "Add authentication to API endpoints" \
  --context "Using JWT tokens, existing user model"

# Output includes:
# - Optimal model selection
# - Implementation steps
# - Success criteria
```

### Run Multi-Model Analysis
```bash
python scripts/swarm/project_analyzer.py --mode full

# Runs analysis with:
# 1. Kimi K2.5 (primary)
# 2. Qwen 122B (knowledge)
# 3. Nemotron (precision)
```

### Check Swarm Status
```bash
python scripts/swarm/model_selector.py

# Shows:
# - All models and quotas
# - Optimal routing by task type
# - Current team composition
```

## Integration Points

### CoPaw (Conversational Interface)
- Uses TIER_0 models for conversation
- Routes heavy tasks to TIER_1-2 when needed
- Preserves session context in MemU #bios/copaw #bios/copaw/workflow #bios/personal_assistant #bios/personal_assistant/memory #bios/copaw #bios/copaw/workflow #bios/personal_assistant #bios/personal_assistant/memory

### Serena MCP (Project Analysis)
- Uses multi-model team for comprehensive analysis
- Each model contributes unique perspective
- Results synthesized into actionable insights #bios/mcp_server #bios/mcp_server/tool #bios/architecture #bios/architecture/component #bios/mcp_server #bios/mcp_server/tool #bios/architecture #bios/architecture/component

### Agent PM (GitHub → Notion)
- Creates task briefs from GitHub issues
- Routes briefs to optimal model
- Tracks outcomes for learning #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/task #bios/notion #bios/notion/sync #bios/personal_assistant #bios/personal_assistant/task

### MemU (Memory)
- Stores analysis results
- Provides context for future tasks
- Enables cross-session learning

## Quota Management

The system tracks:
- **Daily limits**: Reset at midnight
- **Monthly limits**: Reset on 1st of month
- **Usage patterns**: Learn from task outcomes
- **Fallback routing**: Automatically use next-best when quota exceeded    #bios/personal_assistant #bios/personal_assistant/task #bios/personal_assistant/routing #bios/personal_assistant/memory #bios/personal_assistant #bios/personal_assistant/task #bios/personal_assistant/routing #bios/personal_assistant/memory

## Cost Optimization

| Scenario | Model Used | Cost |
|----------|-----------|------|
| Simple conversation | Gemini Flash | Free |
| Quick code fix | MiniMax Free | Free |
| Project analysis | Kimi K2.5 Free | Free |
| Complex architecture | Kimi K2.5 Go | Subscription |
| Critical task brief | GLM-5 | Subscription |
| Top-tier reasoning | Claude 4.6 Opus | GitHub Pro | #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/config #bios/meta #bios/meta/operational

## Success Metrics

Track:
1. **Task completion rate** by model
2. **Error detection rate** per model
3. **Quota utilization** efficiency
4. **Cost per successful task**
5. **Model switching frequency**    #bios/meta #bios/meta/operational #bios/personal_assistant #bios/personal_assistant/task #bios/meta #bios/meta/operational #bios/personal_assistant #bios/personal_assistant/task

## Next Steps

1. **Run diagnostic**: `python scripts/swarm/model_selector.py`
2. **Test brief generation**: `python scripts/swarm/task_brief_generator.py "Analyze authentication flow"`
3. **Full project analysis**: `python scripts/swarm/project_analyzer.py --mode full`
4. **Integrate with Agent PM**: Add task brief generation to GitHub issue workflow    #bios/architecture #bios/architecture/component #bios/meta #bios/meta/operational #bios/architecture #bios/architecture/component #bios/meta #bios/meta/operational

---

*"Sometimes you gotta run before you can walk." - Tony Stark*

The Tony Stark Swarm transforms your multi-model setup from chaos into a coordinated intelligence that works 24/7, deploying the right brain for every task. #bios/architecture #bios/architecture/component #bios/meta #bios/meta/uncategorized #bios/architecture #bios/architecture/component #bios/meta #bios/meta/uncategorized

<!-- LLM_TAGGED -->