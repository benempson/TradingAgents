---
description: Shared framework for complexity-based routing between Inline Mode and Orchestrator Mode. Referenced by draft-spec, implement-spec, update-spec, and fix-bug workflows.
type: include
---

# COMPLEXITY ASSESSMENT & ORCHESTRATOR PROTOCOL

This file is an **include** — it is referenced by other workflows, not invoked directly.

---

## A. SCORING MATRIX

Evaluate four dimensions. Each scores 0 or 1.

| Dimension | 0 (Simple) | 1 (Complex) | How to Measure |
|---|---|---|---|
| **File Radius** | 1-3 source files touched | 4+ source files touched | Grep for symbols/modules affected; count distinct files |
| **Layer Span** | Single architectural layer | 2+ layers (dataflows, agents, llm_clients, graph) | Check which `tradingagents/` subdirectories are affected |
| **Independence** | All tasks are sequential (each depends on the previous) | 2+ tasks can execute in parallel (no shared files between them) | Analyze the plan checklist for dependency chains |
| **Research Load** | Existing patterns cover it; no exploration needed | Must read 5+ unfamiliar files or trace unknown call paths before planning | Count files needing investigation during gap analysis |

### Routing Rule

- **Score 0-1** -> **Inline Mode**. Proceed with the current workflow exactly as written. No sub-agents.
- **Score 2+** -> **Orchestrator Mode**. The current session becomes the orchestrator and delegates to sub-agents.

### Override Rules

- If the user explicitly says "keep it simple", "no agents", or "inline only" -> force **Inline Mode** regardless of score.
- If the user explicitly says "use sub-agents", "parallelize this", or "orchestrator mode" -> force **Orchestrator Mode** regardless of score.

---

## B. VISIBLE OUTPUT FORMAT

Before proceeding, emit this block so the user can see and override the routing decision:

```
COMPLEXITY ASSESSMENT
  File Radius:    [0|1] — N files affected
  Layer Span:     [0|1] — layers: [list]
  Independence:   [0|1] — N parallel groups identified
  Research Load:  [0|1] — N unfamiliar files to explore
  TOTAL:          N/4
  ROUTING:        [Inline Mode | Orchestrator Mode]
```

Wait for implicit or explicit user acknowledgment before proceeding. If the user objects to the routing, switch modes.

---

## C. ORCHESTRATOR PROTOCOL

When Orchestrator Mode is active, the current Claude Code session becomes the **Orchestrator**. The orchestrator coordinates work but **never writes implementation code directly**. All implementation is delegated to sub-agents.

### C.1 Sub-Agent Roles

| Role | `subagent_type` | Purpose | Can edit files? |
|---|---|---|---|
| **Scout** | `Explore` | Read-only codebase exploration: trace call paths, find existing patterns, identify affected files, locate test fixtures | No |
| **Architect** | `Plan` | Analyze Scout findings; propose plan structure, dependency graph, and parallel groups | No |
| **Implementor** | `general-purpose` | Write tests + implementation code for a specific, scoped task group from the plan | Yes |

### C.2 Wave Execution Model

Work proceeds in sequential waves. Agents within a wave run in parallel.

```
[RESEARCH WAVE]  ->  [PLANNING WAVE]  ->  [EXECUTION WAVE(S)]  ->  [VERIFICATION]
```

**Research Wave:**
- Spawn 1-3 Scout agents in parallel, each with a distinct exploration focus (e.g., one per affected layer, or one for existing patterns + one for test fixtures).
- Wait for ALL Scouts to complete before proceeding.
- If a Scout returns insufficient information, spawn ONE follow-up Scout (max 1 retry per question).

**Planning Wave (optional):**
- If the orchestrator can write the plan directly from Scout results, skip this wave.
- If the task is large (10+ plan items) or the dependency structure is unclear, spawn 1 Architect agent to propose the plan structure and parallel groups.
- The orchestrator transcribes the Architect's output into the `IMPLEMENTATION_PLAN-*.md` file. The Architect does not write to the plan file.

**Execution Wave(s):**
- The orchestrator reads the plan and groups checklist items into **parallel groups** based on file ownership (see Section D).
- Each wave spawns 1-3 Implementor agents. Each Implementor receives:
  1. Its specific checklist items from the plan
  2. A file whitelist (files it may create or modify)
  3. The relevant architectural rules (see Section C.3)
  4. The test file(s) it should write to
- Waves run sequentially. Agents within a wave run in parallel.
- After each wave completes, the orchestrator marks completed items `[x]` in the plan file before spawning the next wave.

**Verification:**
- After ALL execution waves complete, the orchestrator asks the user to run `python -m pytest tests/` once.
- The orchestrator then performs the Adversarial Security Review (Rule 13) examining all files modified across all agents.

### C.3 Rule Injection (MANDATORY)

Sub-agents do not automatically load `.ai/rules/`. The orchestrator MUST inject the following into every **Implementor** agent's prompt:

1. **TDD mandate** — "Write the failing test BEFORE the implementation code. No exceptions. Follow the test-first protocol from Rule 08."
2. **Layer separation** — "The dependency direction is: dataflows <- agents <- graph. llm_clients is standalone. Do not create imports that violate this direction."
3. **Production-ready** — "No TODO comments, no placeholder logic, no debug print() statements. Use logger.info/error/warning for instrumentation."
4. **Observability** — "Add breadcrumb logs (logger.info) at entry points, branching decisions, and async results per Rule 11."
5. **Tool returns** — "LangGraph tools must return strings, not dicts or Pydantic models."
6. **Pydantic gotcha** — "Use `model_name` not `model` as a field name on BaseChatModel subclasses."

For **Scout** agents, inject only the layer separation rule (so they understand what they're looking at).

### C.4 Orchestrator Status Reporting

The orchestrator emits a status block before and after each wave so the user maintains visibility:

```
WAVE 1/3: RESEARCH
  Spawning 2 Scout agents:
    Scout-1: Exploring tradingagents/llm_clients/ for factory pattern
    Scout-2: Exploring tradingagents/graph/ for state management
  [waiting for results...]

  Scout-1: Complete. Found 3 relevant patterns in factory.py, base_client.py.
  Scout-2: Complete. Identified 2 state fields to modify in agent_states.py.
```

```
WAVE 2/3: EXECUTION
  Spawning 2 Implementor agents:
    Impl-1: Items 1-4 (llm_clients layer) — files: factory.py, new_client.py, test_factory.py
    Impl-2: Items 5-7 (graph layer) — files: setup.py, test_graph.py
  [waiting for results...]

  Impl-1: Complete. Created new_client.py, updated factory.py, wrote 4 tests.
  Impl-2: Complete. Updated setup.py, wrote 3 tests.
```

---

## D. FILE OWNERSHIP MAP

Before each Execution Wave, the orchestrator MUST build a file ownership map and enforce these rules:

1. **List every file** each Implementor will create or modify.
2. **Check for overlaps.** If two Implementors need the same file, they CANNOT run in parallel. Move one to the next sequential wave.
3. **Record the map** in the `IMPLEMENTATION_PLAN-*.md` under a `## Parallel Groups` section:

```markdown
## Parallel Groups

### Wave 1 (parallel)
- **Group A** (llm_clients): Items 1-4
  Files: factory.py, new_client.py, tests/test_factory.py
- **Group B** (graph): Items 5-7
  Files: setup.py, tests/test_graph.py

### Wave 2 (sequential — depends on Wave 1)
- **Group C** (agents): Items 8-10
  Files: analyst.py, tests/test_analyst.py
  Depends on: Group A (imports new client)
```

**Hard cap:** Maximum 3 parallel Implementor agents per wave. If more than 3 independent groups exist, queue them into sequential waves of 3.

---

## E. TDD BATCHING PROTOCOL

In Orchestrator Mode, the interactive TDD gates ("ask user to run test, confirm red") are batched for efficiency:

1. **Each Implementor writes the failing test FIRST, then the implementation code.** This is enforced in the Implementor's prompt (Section C.3). The Implementor does not ask the user to run tests — it writes both test and code.
2. **After ALL Implementors in a wave complete,** the orchestrator asks the user to run the test suite ONCE: `python -m pytest tests/ -v`.
3. **If tests fail,** the orchestrator identifies which Implementor's work caused the failure (by matching failing test files to the file ownership map) and spawns a targeted fix agent for that group only.
4. **The TDD discipline is preserved** because test files are always written before implementation files within each Implementor's execution. The batching only defers the interactive verification gate — it does not skip it.

---

## F. RESUMABILITY PROTOCOL

If the session is interrupted mid-wave (context limit, crash, user disconnect):

1. **On resume**, the orchestrator checks the current state:
   - Read `IMPLEMENTATION_PLAN-*.md` for unchecked `[ ]` items.
   - Run `git diff --name-only` to see which files were actually modified since the plan was created.
   - Compare modified files against the `## Parallel Groups` file ownership map.
2. **Mark completed items**: If a group's files are all present and modified, mark its items `[x]`.
3. **Resume from next unchecked item** — spawn the next wave of Implementors for remaining groups.
4. **If partially modified** (some files in a group changed, others not), treat the group as incomplete. Spawn a single Implementor to finish the remaining items in that group.

---

## G. SECURITY REVIEW SCOPE

The Adversarial Security Review (Rule 13) remains an **orchestrator-level responsibility**. It is NEVER delegated to sub-agents because:
- Sub-agents see only their slice of the codebase.
- Security vulnerabilities often span multiple slices (e.g., an unvalidated input in one module consumed without checking in another).
- The review needs the full picture of ALL changes made across ALL agents in the session.

After all execution waves complete and tests pass, the orchestrator:
1. Collects the list of every file modified by any Implementor agent.
2. Reads each modified file.
3. Performs the Rule 13 adversarial review against the complete change set.
