# Create-Agent Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a skill that scaffolds new voice agents with standardized structure, permissions, and CLAUDE.md template through interactive questions. Automatically registers agents in voice-agent-config.yaml and triggers hot reload.

**Architecture:** Markdown skill definition that prompts for agent details (name, purpose, data sources, skills), then generates directory structure with .claude/settings.local.json, CLAUDE.md, and conversations/ folder. Updates voice-agent-config.yaml with new agent entry and keywords, then calls /reload-config endpoint for hot reload.

**Tech Stack:** Markdown (skill definition), YAML (config), JSON (permissions), Claude Code tools (execution), HTTP requests

**Note:** Hardcoded to Kevin's directory structure (~/coding/voice-agent/, ~/journal/agents/)

---

## Task 1: Create Skill Definition File

**Files:**
- Create: `~/.claude/skills/create-agent.md`

**Step 1: Write the skill definition**

```markdown
---
name: create-agent
description: Scaffold a new voice agent with template structure, permissions, and CLAUDE.md. Use when user wants to create a new agent for tracking/managing something.
trigger_patterns:
  - create.*agent
  - new agent
  - scaffold.*agent
  - set up.*agent
---

# Create Agent Skill

## When to Use
- User says "create a new agent"
- User wants to track/manage something new via voice
- User mentions setting up an agent

## Workflow

1. **Ask required questions:**
   - Agent name (kebab-case, becomes directory name)
   - Purpose (one sentence description)

2. **Ask optional questions:**
   - Data sources/files it works with (for permissions)
   - Special skills needed (for pre-allowing in settings.json)

3. **Create agent structure in ~/journal/agents/{name}/:**
   - `.claude/settings.local.json` with baseline permissions
   - `CLAUDE.md` with template sections
   - `conversations/` directory

4. **Baseline permissions (all agents):**
   - `Read(//home/kevin/journal/agents/{name}/**)`
   - `Write(//home/kevin/journal/agents/{name}/**)`
   - `Edit(//home/kevin/journal/agents/{name}/**)`
   - `Bash(git:*)` (use Read/Grep tools for file operations, not bash)
   - `WebSearch`
   - `mcp__mem0__add_memory`
   - `mcp__mem0__search_memories`
   - `mcp__plugin_episodic-memory_episodic-memory__search`
   - `mcp__plugin_episodic-memory_episodic-memory__read`
   - `mcp__sequential-thinking__sequentialthinking`
   - `mcp__context7__resolve-library-id`
   - `mcp__context7__query-docs`
   - `Read(//home/kevin/.claude/CLAUDE.md)`
   - `Write(//home/kevin/journal/agents/task/completed.jsonl:*)`
   - `Write(//home/kevin/journal/agents/task/inbox.jsonl:*)`

5. **CLAUDE.md template sections:**
   - Purpose
   - Key Workflows
   - Data Sources
   - Related Agents

6. **Confirm creation and show next steps**

## Implementation Notes
- Validate agent name (no spaces, lowercase, hyphens ok)
- Check if agent directory already exists AND if name exists in config
- Expand data source paths to absolute form, add Read permissions
- List available skills from ~/.claude/skills/ for user selection
- Convert agent name hyphens to spaces for keywords list
- Sort keywords alphabetically after adding new one
- Check /health before attempting reload to provide accurate error messages
```

**Step 2: Save and verify**

Run: `cat ~/.claude/skills/create-agent.md | head -20`
Expected: Shows skill metadata and description

**Step 3: Commit**

```bash
git add ~/.claude/skills/create-agent.md
git commit -m "feat: add create-agent skill definition"
```

---

## Task 2: Create Permission Template Generator

**Files:**
- Create: `~/.claude/skills/templates/agent-permissions.json`

**Step 1: Write baseline permissions template**

```json
{
  "permissions": {
    "allow": [
      "Read(//home/kevin/journal/agents/{{AGENT_NAME}}/**)",
      "Write(//home/kevin/journal/agents/{{AGENT_NAME}}/**)",
      "Edit(//home/kevin/journal/agents/{{AGENT_NAME}}/**)",
      "Bash(git:*)",
      "WebSearch",
      "mcp__mem0__add_memory",
      "mcp__mem0__search_memories",
      "mcp__plugin_episodic-memory_episodic-memory__search",
      "mcp__plugin_episodic-memory_episodic-memory__read",
      "mcp__sequential-thinking__sequentialthinking",
      "mcp__context7__resolve-library-id",
      "mcp__context7__query-docs",
      "Read(//home/kevin/.claude/CLAUDE.md)",
      "Write(//home/kevin/journal/agents/task/completed.jsonl:*)",
      "Write(//home/kevin/journal/agents/task/inbox.jsonl:*)"
    ],
    "deny": [],
    "ask": []
  }
}
```

**Step 2: Verify template exists**

Run: `cat ~/.claude/skills/templates/agent-permissions.json`
Expected: Shows JSON template with {{AGENT_NAME}} placeholder

**Step 3: Commit**

```bash
git add ~/.claude/skills/templates/agent-permissions.json
git commit -m "feat: add agent permissions template"
```

---

## Task 3: Create CLAUDE.md Template

**Files:**
- Create: `~/.claude/skills/templates/agent-claude.md`

**Step 1: Write CLAUDE.md template**

```markdown
# {{AGENT_NAME}} Agent

## Purpose

{{PURPOSE}}

## Key Workflows

[Describe the main tasks this agent handles]

## Data Sources

{{DATA_SOURCES}}

## Related Agents

{{RELATED_AGENTS}}
```

**Step 2: Verify template**

Run: `cat ~/.claude/skills/templates/agent-claude.md`
Expected: Shows markdown with placeholders

**Step 3: Commit**

```bash
git add ~/.claude/skills/templates/agent-claude.md
git commit -m "feat: add agent CLAUDE.md template"
```

---

## Task 4: Update Skill with Implementation Logic

**Files:**
- Modify: `~/.claude/skills/create-agent.md`

**Step 1: Add implementation instructions to skill**

After the "Implementation Notes" section, add:

```markdown
## Step-by-Step Execution

### Step 1: Gather Information

Use AskUserQuestion to collect:
1. Agent name (required, validate kebab-case)
2. Purpose (required, one sentence)
3. Data sources (optional, comma-separated paths)
4. Special skills (optional, multiSelect from available skills in ~/.claude/skills/)

### Step 2: Validate Agent Name

- Convert to lowercase
- Replace spaces with hyphens
- Verify matches pattern: `^[a-z][a-z0-9-]*$`
- Check `~/journal/agents/{name}` doesn't exist
- Check agent not already in `~/coding/voice-agent/voice-agent-config.yaml` agents section
- If either exists, abort with error: "Agent '{name}' already exists. Use a different name or remove existing agent first."

### Step 3: Create Directory Structure

```bash
mkdir -p ~/journal/agents/{name}/.claude
mkdir -p ~/journal/agents/{name}/conversations
```

### Step 4: Generate settings.local.json

1. Read template from `~/.claude/skills/templates/agent-permissions.json`
2. Replace `{{AGENT_NAME}}` with agent name
3. If data sources provided:
   - Expand paths to absolute form (replace ~ with /home/kevin)
   - Add `Read(//absolute/path/**)` entries to permissions
   - Add note in generated file: "Review permissions and add Write/Edit if needed"
4. If skills provided:
   - List available skills: `ls ~/.claude/skills/`
   - Present as multiSelect via AskUserQuestion
   - Add `Skill(selected-skill)` entries for each selected skill
5. Write to `~/journal/agents/{name}/.claude/settings.local.json`

### Step 5: Generate CLAUDE.md

1. Read template from `~/.claude/skills/templates/agent-claude.md`
2. Replace `{{AGENT_NAME}}` with agent name
3. Replace `{{PURPOSE}}` with provided purpose
4. Replace `{{DATA_SOURCES}}` with data sources or "[None specified]"
5. Replace `{{RELATED_AGENTS}}` with "[To be determined]"
6. Write to `~/journal/agents/{name}/CLAUDE.md`

### Step 6: Register Agent in voice-agent-config.yaml

1. Read current `~/coding/voice-agent/voice-agent-config.yaml`
2. Add agent name to `keywords` list:
   - Convert hyphens to spaces (e.g., "meal-planning" → "meal planning")
   - Append to keywords list
   - Sort keywords list alphabetically
3. Add agent entry to `agents` section:
   ```yaml
   {name}:
     path: "~/journal/agents/{name}"
   ```
4. Write updated YAML back to file

### Step 7: Trigger Config Reload

1. First check if server is running: GET `http://localhost:8000/health`
2. If connection refused: "Server not running. Start voice-agent to activate the new agent."
3. If server responds, POST to `http://localhost:8000/reload-config`
4. If reload succeeds: "Config reloaded successfully. Agent is ready to use."
5. If reload fails: "Reload failed: [error message]. Check voice-agent-config.yaml syntax."

### Step 8: Confirm and Show Next Steps

Output:
```
✓ Created agent: {name}
✓ Location: ~/journal/agents/{name}
✓ Files created:
  - .claude/settings.local.json
  - CLAUDE.md
  - conversations/
✓ Registered in voice-agent-config.yaml
✓ Config reloaded (server still running)

Next steps:
1. Customize CLAUDE.md with specific workflows
2. Test by saying "{name} agent [command]"
```
```

**Step 2: Verify skill content**

Run: `grep -A 5 "Step-by-Step Execution" ~/.claude/skills/create-agent.md`
Expected: Shows execution steps

**Step 3: Commit**

```bash
git add ~/.claude/skills/create-agent.md
git commit -m "feat: add implementation steps to create-agent skill"
```

---

## Task 5: Add Config Reload Endpoint

**Files:**
- Modify: `src/voice_agent/main.py`

**Step 1: Verify infrastructure and add reload endpoint**

First, read `src/voice_agent/agents.py` to verify:
- `load_agents_config()` function exists and its return type
- `set_hotwords()` function exists and its signature
- Confirm `CONFIG` is used as a global variable in main.py

Then add reload endpoint after existing endpoints:

```python
@app.post("/reload-config")
async def reload_config() -> dict[str, str]:
    """Reload voice agent configuration without restarting server."""
    global CONFIG
    try:
        CONFIG = load_agents_config()
        # Update hotwords for Whisper
        set_hotwords(CONFIG)
        logger.info(f"Config reloaded: {len(CONFIG.agents)} agents, {len(CONFIG.commands)} commands")
        return {
            "status": "ok",
            "agents": len(CONFIG.agents),
            "commands": len(CONFIG.commands)
        }
    except Exception as e:
        logger.error(f"Failed to reload config: {e}")
        return {"status": "error", "message": str(e)}
```

**Step 2: Verify endpoint exists**

Run: `grep -A 10 "reload-config" src/voice_agent/main.py`
Expected: Shows the new endpoint definition

**Step 3: Test endpoint manually**

Start voice-agent server, then run:
```bash
curl -X POST http://localhost:8000/reload-config
```

Expected: Response with `"status":"ok"`, `"agents"` > 0, and `"commands"` > 0

**Step 4: Commit**

```bash
git add src/voice_agent/main.py
git commit -m "feat: add /reload-config endpoint for hot reload"
```

---

## Task 6: Test Skill Invocation

**Files:**
- N/A (testing)

**Step 1: Test skill loads**

In Claude Code, say: "Help me create a test agent"
Expected: Skill is invoked automatically

**Step 2: Verify questions appear**

Expected: AskUserQuestion prompts for name, purpose, data sources, skills

**Step 3: Complete flow with test data**

Provide:
- Name: "test-agent"
- Purpose: "Test agent for validation"
- Data sources: (leave empty)
- Skills: (leave empty)

**Step 4: Verify created structure**

Run: `ls -la ~/journal/agents/test-agent/`
Expected:
```
.claude/
conversations/
CLAUDE.md
```

Run: `cat ~/journal/agents/test-agent/.claude/settings.local.json | jq .`
Expected: Valid JSON with baseline permissions

Run: `cat ~/journal/agents/test-agent/CLAUDE.md`
Expected: Template with "test-agent" and "Test agent for validation"

**Step 5: Clean up test agent**

```bash
rm -rf ~/journal/agents/test-agent
```

**Step 5b: Clean up test agent from config**

1. Remove "test agent" from keywords list in voice-agent-config.yaml
2. Remove test-agent entry from agents section
3. Call `curl -X POST http://localhost:8000/reload-config` to apply changes

---

## Testing Checklist

- [ ] Skill loads when user says "create a new agent"
- [ ] Questions collect all required info
- [ ] Agent name validation works (rejects spaces, uppercase)
- [ ] Prevents overwriting existing agents (checks both directory AND config)
- [ ] Creates all required directories
- [ ] settings.local.json has valid JSON with baseline permissions (no Bash(grep:*) or Bash(cat:*))
- [ ] settings.local.json uses Read(//home/kevin/.claude/CLAUDE.md) not Read(**)
- [ ] CLAUDE.md has correct replacements
- [ ] Data sources expand to absolute paths and add Read permissions
- [ ] Skills listed from ~/.claude/skills/ for selection
- [ ] Selected skills add Skill() permissions
- [ ] Agent registered in voice-agent-config.yaml (keywords with hyphens→spaces + agents sections)
- [ ] Keywords list sorted alphabetically
- [ ] /health check works before attempting reload
- [ ] /reload-config endpoint returns success with status/agents/commands
- [ ] Error messages distinguish between server not running vs reload failure
- [ ] Can immediately use new agent via voice without manual restart
- [ ] Test cleanup removes both directory AND config entry
- [ ] Next steps message displays

