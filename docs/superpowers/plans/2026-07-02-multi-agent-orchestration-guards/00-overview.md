# Multi-Agent Orchestration Guards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full multi-agent safety layer so profile, intake, path, outline, Markdown, video, animation, and compose phases run in order, preserve source bindings, and produce verifiable teaching resources.

**Architecture:** Add a thin contract layer under `backend/app/orchestration/` and wire existing agent modules through it at phase boundaries. Keep generation responsibilities in the current worker files while moving shared order, quality, event, recovery, trace, and prompt-budget rules into small focused modules.

**Tech Stack:** FastAPI backend, Python 3.12, Pydantic v2, asyncio, LangChain, SQLModel, pytest, Ruff.

---

## Source Design

Approved design document:

- `/Users/torch/torch/opt/mutiagent/docs/superpowers/specs/2026-07-02-multi-agent-orchestration-guards-design.md`

## Plan Files

Execute in this order:

1. `/Users/torch/torch/opt/mutiagent/docs/superpowers/plans/2026-07-02-multi-agent-orchestration-guards/01-contract-foundation.md`
2. `/Users/torch/torch/opt/mutiagent/docs/superpowers/plans/2026-07-02-multi-agent-orchestration-guards/02-markdown-resource-planning.md`
3. `/Users/torch/torch/opt/mutiagent/docs/superpowers/plans/2026-07-02-multi-agent-orchestration-guards/03-video-animation-compose.md`
4. `/Users/torch/torch/opt/mutiagent/docs/superpowers/plans/2026-07-02-multi-agent-orchestration-guards/04-events-recovery-observability.md`
5. `/Users/torch/torch/opt/mutiagent/docs/superpowers/plans/2026-07-02-multi-agent-orchestration-guards/05-prompt-budget-regression.md`

Each file is a complete phase with tests, implementation steps, validation commands, and commit command.

## File Map

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/contracts.py`
  Shared agent order, phases, typed quality results, resource statuses, source references, brief checks, and trace-safe refs.

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/guards.py`
  Enter and exit checks for each agent boundary. Raises a typed contract error for blocking states and returns structured quality results for quality gates.

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/events.py`
  One event builder for stream events. Existing stream code should call it rather than assembling incompatible event dictionaries.

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/recovery.py`
  Reads and writes `section_resource_checkpoints` inside the outline JSON.

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/observability.py`
  Builds compact trace dictionaries with IDs, counts, durations, quality results, and failure reasons.

- Create `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/prompt_budget.py`
  Applies character budgets for each phase and records whether trimming happened.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/models.py`
  Extend structured resource models with source references, paragraph-bound video briefs, simulation-first animation briefs, and honest unavailable resource outputs.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/common.py`
  Share source-reference construction, brief validation helpers, compose preservation, and generated seed data.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/markdown.py`
  Store `source_references`, generate source footer from structure, require paragraph-bound briefs, and produce full simulation specs before animation runs.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/video.py`
  Return `status="unavailable"` with `failure_reason` when no related direct video is found. Remove search-page style fallback as a successful video.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/animation.py`
  Treat animation agent as implementation-only. Validate HTML against `animation_briefs.visual_model` and `animation_briefs.timeline`.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_resources/main.py`
  Emit unified ordered events and store recovery checkpoints after each phase.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path_intake.py`
  Apply intake guard and prompt budget.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/learning_path.py`
  Apply confirmed-intake guard, source binding guard, and prompt budget.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/course_knowledge.py`
  Apply course source guard and prompt budget.

- Modify `/Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/prompts.py`
  Add concise prompt rules for source references, paragraph-bound video briefs, and simulation-first animation plans.

- Create `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_contract_guards.py`
  Unit tests for state transitions and contract errors.

- Create `/Users/torch/torch/opt/mutiagent/backend/tests/test_orchestration_event_recovery_observability.py`
  Unit tests for event schema, recovery checkpoint updates, and trace compactness.

- Create `/Users/torch/torch/opt/mutiagent/backend/tests/test_prompt_budget.py`
  Unit tests for per-phase budget trimming.

- Modify `/Users/torch/torch/opt/mutiagent/backend/tests/test_agent_contract_models.py`
  Tests for new Pydantic resource fields and no-match video output.

- Modify `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_resource_agent_contract.py`
  Cross-agent resource contract, Markdown brief gates, video unavailable flow, and animation simulation gate.

- Modify `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_intake_agent_contract.py`
  Intake enter guard and source-bound handoff tests.

- Modify `/Users/torch/torch/opt/mutiagent/backend/tests/test_learning_path_agent_contract.py`
  Confirmed-intake and downstream order guard tests.

- Modify `/Users/torch/torch/opt/mutiagent/backend/tests/test_course_knowledge_agent_contract.py`
  Course source guard and outline-to-Markdown handoff tests.

## Global Verification Commands

Run after every Python phase:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run ruff check --fix app/orchestration tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py
uv run ruff format app/orchestration tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py
```

Run after the final phase:

```bash
cd /Users/torch/torch/opt/mutiagent/backend
uv run pytest tests/test_orchestration_contract_guards.py tests/test_orchestration_event_recovery_observability.py tests/test_prompt_budget.py tests/test_agent_contract_models.py tests/test_course_resource_agent_contract.py tests/test_learning_path_intake_agent_contract.py tests/test_learning_path_agent_contract.py tests/test_course_knowledge_agent_contract.py -q
```

## Commit Order

Use these commits:

```bash
git commit -m "feat: add orchestration contract guards"
git commit -m "feat: strengthen markdown resource planning"
git commit -m "feat: make resources honest and simulation first"
git commit -m "feat: add resource event recovery traces"
git commit -m "perf: add agent prompt budgets"
```

## Self-Review

Spec coverage:

- State machine: `01-contract-foundation.md`
- Cross-agent contract tests: `01-contract-foundation.md`, `05-prompt-budget-regression.md`
- Resource planning quality gate: `02-markdown-resource-planning.md`
- Structured source references: `02-markdown-resource-planning.md`
- Video no-match degradation: `03-video-animation-compose.md`
- Animation simulation checks: `03-video-animation-compose.md`
- Unified event schema: `04-events-recovery-observability.md`
- Recovery points: `04-events-recovery-observability.md`
- Observability logs: `04-events-recovery-observability.md`
- Prompt budget: `05-prompt-budget-regression.md`

Type consistency:

- `source_references`, `video_briefs`, `animation_briefs`, `quality_result`, `section_resource_checkpoints`, and trace fields are introduced in earlier phases before use in later phases.
- Resource phase names are consistently `markdown`, `video`, `animation`, and `compose`.
- Agent names are consistently `profile_agent`, `learning_path_intake_agent`, `learning_path_agent`, `course_knowledge_agent`, `section_markdown_agent`, `section_video_search_agent`, `section_html_animation_agent`, and `compose_resource`.
