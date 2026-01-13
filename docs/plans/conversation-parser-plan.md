# Conversation Parser Project Plan

## Problem Statement
Kevin needs automated project status tracking from Claude Code conversations. Currently, picking up projects after time away (like Product Pix after 3 weeks) means not knowing where things left off.

## Goals
1. Parse JSONL conversation files into structured data
2. Generate atomic notes with rich tags in Obsidian
3. Auto-generate daily/weekly/monthly rollup summaries per project
4. Surface cross-project status at a glance
5. (Future) Feed "what I'm working on" section of portfolio website

## Architecture

### Data Flow
```
JSONL conversations → Markdown parser (existing script) → Conversation analyzer → Atomic notes with tags → Rollup generator → Summary files
```

### Project Detection
- Primary: Working directory of conversation
- Secondary: If another project is mentioned, update that project's notes too

### Note Structure (Obsidian)
```
journal/
  projects/
    {project-name}/
      status.md           # Current state, always overwritten
      next-steps.md       # What's planned
      daily/
        2026-01-10.md     # Auto-generated daily summary
      weekly/
        2026-W02.md       # Auto-generated weekly rollup
      monthly/
        2026-01.md        # Auto-generated monthly rollup
      notes/
        {atomic-note}.md  # Tagged atomic notes (decisions, blockers, completions, learnings)
```

### Tag System
- `#decision` - Choices made
- `#completed` - Work finished
- `#blocker` - Problems encountered
- `#learning` - Insights gained
- `#idea` - Future possibilities
- `#question` - Open questions
- Project tags: `#project/product-pix`, `#project/voice-agent`, etc.

### Update Frequency
- Atomic notes: Real-time (after each conversation via existing hook or scheduled)
- Daily rollup: Every hour (or end of day)
- Weekly rollup: Sunday night
- Monthly rollup: Last day of month

## Implementation Steps

### Phase 1: Conversation Analyzer
1. Extend existing JSONL→Markdown parser to extract structured data
2. For each conversation, identify:
   - Project (from working directory)
   - Key events: decisions, completions, blockers, learnings
   - Any mentions of other projects
3. Output atomic notes with appropriate tags and bidirectional links

### Phase 2: Rollup Generator
1. Read atomic notes for a project
2. Synthesize into daily summary (what happened today)
3. Weekly: aggregate daily summaries + highlight key decisions/completions
4. Monthly: aggregate weekly + overall progress narrative

### Phase 3: Status Dashboard
1. Master file listing all active projects
2. For each: last activity date, current status, immediate next steps
3. Updated whenever any project gets new notes

### Phase 4: Portfolio Integration (Future)
- Expose subset of project data via API or static generation
- Show on portfolio: project name, brief description, recent activity

## Files to Create/Modify
- `~/coding/voice-agent/scripts/conversation-analyzer.py` - Main parser
- `~/coding/voice-agent/scripts/rollup-generator.py` - Summary generator
- Cron job or systemd timer for scheduled runs

## Open Questions
- Where should the Obsidian project notes live? In journal or in each project's repo?
- Should rollups include links to specific conversation files?
- How to handle conversations that span multiple days?

## Verification
- Run parser on recent Product Pix conversations
- Verify atomic notes are created with correct tags
- Manually trigger rollup and check output quality
- Confirm bidirectional links work in Obsidian
