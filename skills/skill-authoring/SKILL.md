---
name: skill-authoring
description: Create or improve a skill in skills/ when you discover a workflow, pitfall or convention that future agents should follow.
---

# Writing skills

Skills are how agents pass on *procedural* knowledge (how to do things here). Facts about the research
belong in the wiki instead.

- Improve an existing skill rather than adding a near-duplicate.
- File: `skills/<kebab-name>/SKILL.md` with front matter `name` and `description`. The description says
  **what** and **when to use it**, because that's what agents scan to decide whether to load the skill.
- Keep it short: steps, commands and rules. Add helper scripts next to it if useful.
- Record pitfalls you hit ("training diverges with lr > 1e-3 on dataset X"). Those save the most time.
- Mention the change in the thread you were working on so the human sees it.
- Skills are also available to Claude Code automatically through the `.claude/skills` symlink.
