---
name: wrap-up
description: Use when user says "wrap up", "close session", "end session",
  "wrap things up", "close out this task", or invokes /wrap-up — runs
  end-of-session checklist for shipping, memory, and self-improvement
---

# Session Wrap-Up
Run four phases in order. Each phase is conversational and inline — no
separate documents. All phases auto-apply without asking; present a
consolidated report at the end.

## Phase 1: Ship It
**Commit:**
1. Run `git status` in each repo directory that was touched during the session
2. Stage only the files that were touched in this session — do not stage files not changed by this session.
3. Run `git log --oneline -5` to review the project's commit message style, then write a message that matches it. Keep it short and imperative (e.g. "Fix ImageModal navigation desync"). No bullet-point body, no co-author footers.
4. Commit the staged files.
5. Ask the user before pushing to remote — do not push automatically.

## Phase 2: Remember It
Review what was learned during the session. Decide where each piece of
knowledge belongs in the memory hierarchy:

**Memory placement guide:**
- **AGENTS.md** (instructions for Agents) — Permanent project rules,
  conventions, commands, architecture decisions that should guide all future
  sessions
- **`.ai/rules/`** (modular project rules) — Topic-specific instructions
  that apply to certain file types or areas. Use `paths:` frontmatter to scope
  rules to relevant files (e.g., testing rules scoped to `tests/**`)
- **`AGENT.local.md`** (private per-project notes) — Personal WIP context,
  local URLs, local paths for running tests, sandbox credentials, current focus
  areas that shouldn't be committed
- **`@import` references** — When a AGENTS.md would benefit from referencing
  another file rather than duplicating its content
- **Auto memory** (last resort only) — Reserve exclusively for cross-project
  user preferences (e.g. "always use bun", "never auto-commit"). Do NOT write
  project-specific patterns, conventions, or debugging insights here — those
  belong in the repo so they are version-controlled and shared with all
  developers.

**Decision framework:**
- Is it a permanent project convention? → AGENTS.md or `.ai/rules`
- Is it scoped to specific file types? → `.ai/rules` with `paths:`
  frontmatter
- Is it personal/ephemeral context? → `AGENT.local.md`
- Is it duplicating content from another file? → Use `@import` instead
- Is it a cross-project user preference (not project-specific)? → Auto memory
- Is it a project-specific pattern Claude discovered? → `.ai/rules` (not auto memory)

Note anything important in the appropriate location.

## Phase 3: Review & Apply
Analyze the conversation for self-improvement findings. If the session was
short or routine with nothing notable, say "Nothing to improve" and proceed
to Phase 4.

**Auto-apply all actionable findings immediately** — do not ask for approval
on each one. Apply the changes, commit them, then present a summary of what
was done.

**Finding categories:**
- **Skill gap** — Things Claude struggled with, got wrong, or needed multiple
  attempts
- **Friction** — Repeated manual steps, things user had to ask for explicitly
  that should have been automatic
- **Knowledge** — Facts about projects, preferences, or setup that Claude
  didn't know but should have
- **Automation** — Repetitive patterns that could become skills, hooks, or
  scripts

**Action types:**
- **AGENTS.md** — Edit the relevant project or global AGENTS.md
- **Rules** — Create or update a `.ai/rules` file
- **Skill / Hook** — Document a new skill or hook spec for implementation
- **AGENT.local.md** — Create or update per-project local memory
- **Auto memory** — Only for cross-project user preferences, never for project-specific insights

Present a summary after applying, in two sections — applied items first,
then no-action items:

Findings (applied):

1. ✅ Skill gap: Cost estimates were wrong multiple times
   → [AGENTS.md] Added token counting reference table

2. ✅ Knowledge: Worker crashes on 429/400 instead of retrying
   → [Rules] Added error-handling rules for worker

3. ✅ Automation: Checking service health after deploy is manual
   → [Skill] Created post-deploy health check skill spec

---
No action needed:

4. Knowledge: Discovered X works this way
   Already documented in AGENTS.md

## Phase 4: Publish It
After all other phases are complete, review the full conversation for material
that could be published. Look for:

- Interesting technical solutions or debugging stories
- Community-relevant announcements or updates
- Educational content (how-tos, tips, lessons learned)
- Project milestones or feature launches

**If publishable material exists:**
Draft the article(s) for the appropriate platform and save to a drafts folder.
Present suggestions with the draft:

All wrap-up steps complete. I also found potential content to publish:

1. "Title of Post" — 1-2 sentence description of the content angle.
   Platform: Reddit
   Draft saved to: Drafts/Title-Of-Post/Reddit.md


**If no publishable material exists:**
Say "Nothing worth publishing from this session" and you're done.
