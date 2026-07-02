# Multi-Agent Orchestration Guards Design

## Goal

Build the full safety layer for the multi-agent learning-content pipeline so each agent runs in the correct order, receives exact upstream context, preserves textbook bindings, emits machine-checkable outputs, and fails honestly when auxiliary resources cannot be produced.

The pipeline remains:

`profile_agent -> learning_path_intake_agent -> learning_path_agent -> course_knowledge_agent -> section_markdown_agent -> section_video_search_agent -> section_html_animation_agent -> compose_resource`

This design does not rewrite LangGraph or replace existing agents. It adds a thin contract layer around them.

## Architecture

Add a small orchestration contract layer:

- `backend/app/orchestration/contracts.py`
  Defines agent order, phases, dependency references, quality results, resource status, and common contract error structures.

- `backend/app/orchestration/guards.py`
  Holds enter and exit checks for every agent. Guards verify preconditions before a node runs and validate outputs before the next phase consumes them.

- `backend/app/orchestration/events.py`
  Builds stream events with one schema. Agents stop hand-writing incompatible event dictionaries.

- `backend/app/orchestration/recovery.py`
  Stores and reads section-phase recovery checkpoints in `course_knowledge` outline JSON.

- `backend/app/orchestration/observability.py`
  Records compact traces with IDs, counts, durations, quality results, and failure reasons. It must not record full textbook正文, full Markdown, or full HTML.

Existing agent modules keep their generation responsibilities. They call guards and event builders at phase boundaries.

## State Machine

Each agent has four contract parts: enter condition, required output, failure state, and downstream handoff.

### profile_agent

Enter condition:

- User needs profile creation or profile is incomplete.

Required output:

- `profile.type == "basic_profile"`
- `confirmed_info` contains the supported profile fields.

Failure state:

- Profile fields are incomplete.
- Current grade is unsupported.

### learning_path_intake_agent

Enter condition:

- Profile is complete.

Required output:

- `learning_path_intake.status` is one of `draft`, `confirmed`, `risk_pending`.
- Each course contains `title`, `purpose`, `source_textbook_id`, `source_textbook_title`, `source_outline_section_ids`.
- Course order is the exact order later inherited by `learning_path_agent`.
- `purpose` explains the textbook-bound learning boundary for later outline and Markdown generation.

Failure state:

- No published textbook context covers the topic.
- Course points to an unpublished textbook or unknown textbook section.

### learning_path_agent

Enter condition:

- `learning_path_intake.status == "confirmed"`.

Required output:

- Formal course order exactly matches the confirmed intake order.
- Course source bindings are preserved.
- `resource_generation_contract.downstream_agents` is:
  `course_knowledge_agent -> section_markdown_agent -> section_video_search_agent -> section_html_animation_agent`.

Failure state:

- Intake is not confirmed.
- Course count or order differs from the confirmed intake.
- Any course loses `source_textbook_id` or `source_outline_section_ids`.

### course_knowledge_agent

Enter condition:

- Current course is present in the formal learning path.
- Course has `source_textbook_id` and `source_outline_section_ids`.

Required output:

- Every section has `source_textbook_id`, `source_textbook_title`, `source_section_ids`, `source_section_titles`, `source_content_chars`.
- Every second-level section has specific `key_knowledge_points`.
- Section descriptions support later Markdown teaching, video search, and HTML animation planning.

Failure state:

- Outline introduces unbound textbook sections.
- Second-level sections are general resource themes instead of concrete teaching topics.

### section_markdown_agent

Enter condition:

- Target section has a textbook evidence pack.

Required output:

- Markdown is the main teaching product.
- `source_references` is populated from the evidence pack.
- `## 来源` can be generated from `source_references`.
- `video_briefs` and `animation_briefs` bind to concrete Markdown paragraphs.
- Animation briefs include complete simulation requirements.

Failure state:

- Source references are missing.
- Briefs are generic.
- Placeholders do not match brief IDs.
- Animation brief lacks simulation schema.

### section_video_search_agent

Enter condition:

- Markdown has concrete `video_briefs`.

Required output:

- Each brief either has a verified video with `status = "available"` or an honest `status = "unavailable"` with `failure_reason`.

Failure state:

- System error or malformed input is recoverable.
- No relevant video is not a hard failure; it becomes unavailable.

### section_html_animation_agent

Enter condition:

- Markdown has complete `animation_briefs`.
- The HTML agent receives animation specifications; it does not decide teaching meaning.

Required output:

- HTML implements the brief's visual model and timeline.
- HTML passes simulation-first checks.

Failure state:

- Incomplete brief is blocking and returns to Markdown planning.
- HTML that does not implement the brief is recoverable and can be retried.

### compose_resource

Enter condition:

- Markdown is completed.
- Video and animation may be available or unavailable.

Required output:

- Markdown block order is preserved.
- Available resources are inserted at specified positions.
- Unavailable resources produce light user-visible notices and do not remove teaching content.
- `source_references` survives composition.

## Data Structures

### source_references

Each `section_markdowns[section_id]` stores:

```json
{
  "source_references": [
    {
      "textbook_id": "textbook-data-structures",
      "textbook_title": "数据结构教程",
      "section_id": "2.1",
      "section_title": "线性表",
      "evidence_summary": "本小节依据教材中关于线性表顺序存储、链式存储和插入删除成本的说明生成。",
      "content_char_count": 842
    }
  ]
}
```

Rules:

- Values come from `textbook_evidence_pack.sections`.
- The model cannot invent textbook IDs or section IDs.
- `## 来源` is derived from this structure.
- Frontend can render source attribution without parsing Markdown.

### video_briefs

Markdown agent emits:

```json
{
  "video_id": "video_1",
  "title": "单链表节点与 next 指针讲解",
  "target_markdown_heading": "核心概念",
  "target_paragraph_summary": "解释节点由 data 和 next 组成，next 指向下一个节点。",
  "search_terms": ["单链表", "节点", "next 指针", "链式存储"],
  "purpose": "辅助理解单链表的节点和指针关系，而不是泛泛推荐数据结构课程。"
}
```

Quality rules:

- `target_markdown_heading` must match a real Markdown heading.
- `target_paragraph_summary` is required.
- `search_terms` has at least three terms and overlaps with source or Markdown content.
- `purpose` cannot be only "帮助理解本节内容".

### animation_briefs

Markdown agent emits full animation specifications:

```json
{
  "animation_id": "anim_1",
  "title": "单链表节点通过 next 指针串联",
  "target_markdown_heading": "步骤讲解",
  "target_paragraph_summary": "解释单链表由节点组成，每个节点包含 data 和 next，next 指向下一个节点，尾节点指向 None。",
  "concept": "单链表的节点与指针关系",
  "simulation_type": "data_structure_linked_list",
  "visual_elements": ["头指针", "节点(data,next)", "next 指针", "尾节点 None"],
  "visual_model": {
    "entities": [
      {"id": "head", "kind": "pointer", "label": "head"},
      {"id": "node_1", "kind": "node", "fields": ["data", "next"]},
      {"id": "node_2", "kind": "node", "fields": ["data", "next"]},
      {"id": "none", "kind": "terminal", "label": "None"}
    ],
    "relations": [
      {"from": "head", "to": "node_1", "kind": "points_to"},
      {"from": "node_1.next", "to": "node_2", "kind": "points_to"},
      {"from": "node_2.next", "to": "none", "kind": "points_to"}
    ]
  },
  "timeline": [
    {"step": 1, "action": "show_entity", "target": "head"},
    {"step": 2, "action": "show_entity", "target": "node_1"},
    {"step": 3, "action": "connect", "from": "head", "to": "node_1"},
    {"step": 4, "action": "show_entity", "target": "node_2"},
    {"step": 5, "action": "connect", "from": "node_1.next", "to": "node_2"},
    {"step": 6, "action": "connect", "from": "node_2.next", "to": "none"}
  ],
  "layout": "横向链式结构",
  "motion": "节点依次用 transform 从左到右进入，指针连线用 opacity 依次出现",
  "interaction": "点击步骤按钮切换到插入、删除、遍历状态",
  "success_check": ["DOM 中包含头指针", "DOM 中包含 next 指针", "DOM 中包含 None", "至少 3 个节点可见"],
  "placement_hint": "放在步骤讲解中解释节点结构之后"
}
```

Rules:

- Markdown agent owns teaching and animation planning.
- HTML agent only implements the specification.
- HTML agent must not invent, replace, or generalize the concept.

### resource status

Available:

```json
{
  "brief_id": "video_1",
  "status": "available",
  "quality_result": {
    "passed": true,
    "reason": "",
    "checked_at": "..."
  }
}
```

Unavailable:

```json
{
  "brief_id": "video_1",
  "status": "unavailable",
  "failure_reason": "未找到同时包含 单链表、节点、next 指针 的公开视频结果。",
  "videos": []
}
```

## Quality Gates

### Common result

All gates return:

```json
{
  "passed": false,
  "severity": "blocking",
  "reason": "animation_briefs 缺少 visual_model.entities。",
  "checks": [
    {
      "name": "visual_model_present",
      "passed": false,
      "reason": "visual_model.entities 为空。"
    }
  ]
}
```

Severity:

- `blocking`: output cannot proceed.
- `recoverable`: output can be retried later.
- `informational`: record only.

### Markdown gate

Blocking checks:

- `source_references` exists.
- `source_references` comes from the evidence pack.
- `video_briefs` are paragraph-bound.
- `animation_briefs` are paragraph-bound.
- Briefs do not use generic text such as "本节内容" or "流程动画".
- Animation briefs include `simulation_type`, `visual_model`, `timeline`, and `success_check`.

### Video gate

Checks:

- URL is a direct video page.
- Metadata matches `search_terms` or `target_paragraph_summary`.
- Search pages, course homepages, collection pages, and unrelated resources are rejected.

Failure:

- No relevant video becomes `unavailable`.
- System or malformed-data failures are `recoverable`.

### Animation gate

Simulation-first checks:

- HTML includes `section-animation`.
- HTML includes UTF-8 metadata.
- Colors use OKLCH or CSS variables.
- Reduced-motion fallback exists.
- DOM or SVG includes `visual_model.entities`.
- Connectors, SVG lines, or relation markers implement `visual_model.relations`.
- Timeline or step state exists.
- The output is not only animated text cards.

Linked-list checks:

- Contains `head` or `头指针`.
- Contains at least two nodes.
- Contains `data` and `next`.
- Contains `None` or an empty-pointer terminal.
- Contains pointer lines.
- Has step switching or an automatic timeline.

### Compose gate

Checks:

- Markdown block order is preserved.
- Resources are inserted only at specified positions.
- Unavailable resources do not delete正文.
- `source_references` remains present.

## Event Schema

All events are built by `events.py`.

Progress:

```json
{
  "event": "agent_progress",
  "agent": "section_markdown_agent",
  "agent_order": 5,
  "phase": "markdown",
  "status": "running",
  "stepId": "leaf-section-1.1-markdown",
  "depends_on": ["course_knowledge_agent"],
  "input_refs": {
    "course_id": "year_3_course_1",
    "section_id": "1.1",
    "source_textbook_id": "textbook-data-structures",
    "source_section_ids": ["2.1"]
  },
  "output_refs": {},
  "quality_result": null,
  "message": "正在基于教材证据生成小节 Markdown 与资源规划"
}
```

Completed:

```json
{
  "event": "agent_result",
  "agent": "section_markdown_agent",
  "agent_order": 5,
  "phase": "markdown",
  "status": "completed",
  "depends_on": ["course_knowledge_agent"],
  "input_refs": {},
  "output_refs": {
    "section_markdown_id": "1.1",
    "video_brief_ids": ["video_1"],
    "animation_brief_ids": ["anim_1"],
    "source_reference_ids": ["textbook-data-structures:2.1"]
  },
  "quality_result": {
    "passed": true,
    "severity": "informational",
    "reason": ""
  }
}
```

## Recovery Points

Store recovery data under outline JSON:

```json
{
  "section_resource_checkpoints": {
    "1.1": {
      "markdown": {
        "status": "completed",
        "updated_at": "...",
        "output_refs": {},
        "quality_result": {}
      },
      "video": {
        "status": "unavailable",
        "updated_at": "...",
        "failure_reason": "未找到合格视频"
      },
      "animation": {
        "status": "recoverable_failed",
        "updated_at": "...",
        "failure_reason": "HTML 未包含 next 指针关系线"
      }
    }
  }
}
```

Rules:

- Markdown completed means video failure only reruns video.
- Video unavailable does not block animation.
- Animation failure only reruns animation.
- Outline changes that affect section title or source binding clear downstream checkpoints.
- Markdown changes that alter brief IDs or target paragraph summaries clear video and animation checkpoints.

## Observability

Trace shape:

```json
{
  "trace_id": "session-1:course:section:phase",
  "agent": "section_html_animation_agent",
  "phase": "animation",
  "duration_ms": 18423,
  "input_summary": {
    "course_id": "year_3_course_1",
    "section_id": "1.1",
    "source_textbook_id": "textbook-data-structures",
    "brief_ids": ["anim_1"],
    "simulation_type": "data_structure_linked_list"
  },
  "output_summary": {
    "status": "available",
    "html_length": 12840,
    "quality_passed": true
  },
  "failure_reason": ""
}
```

Rules:

- Do not log full `evidence_text`.
- Do not log full Markdown.
- Do not log full HTML.
- Record IDs, lengths, counts, status, durations, quality results, and failure reasons.

## Prompt Budget

Use character budgets first; do not add a tokenizer dependency.

Rules:

- Intake receives textbook outline summaries only.
- Learning path receives confirmed intake, profile summary, and progress summaries.
- Course knowledge receives textbook section IDs, titles, content lengths, and short summaries.
- Markdown is the only phase that receives textbook evidence正文.
- Video and animation receive briefs, target paragraph summaries, and source references, not full textbook正文.

When a prompt exceeds budget:

- Trim history and existing generated resources first.
- Never trim current source binding.
- Never trim target section evidence pack in Markdown.
- Record `prompt_budget_applied = true` in trace.

## Testing Strategy

### Unit contract tests

Add tests for:

- Unconfirmed intake cannot enter learning path.
- Missing course source binding cannot enter course knowledge.
- Missing section source binding cannot enter Markdown.
- Missing `source_references` blocks Markdown output.
- Generic video and animation briefs fail.
- Missing `visual_model` or `timeline` blocks animation planning.
- Video no-match returns unavailable.
- Text-only animated HTML fails simulation-first gate.

### Cross-agent contract test

Add one full contract:

`intake -> learning_path -> course_knowledge -> section_markdown -> section_video_search -> section_html_animation -> compose`

Assertions:

- Same `source_textbook_id` is preserved.
- Same source section IDs are preserved.
- Course order equals intake order.
- Outline sections come from course source bindings.
- Markdown `source_references` comes from outline source fields.
- Video and animation briefs bind to concrete paragraphs.
- Linked-list brief yields simulation-first HTML.
- Video unavailable does not block compose.
- Event order and refs are complete.

### Regression tests

Each phase runs:

- Ruff.
- Relevant contract tests.
- Main course resource contract tests.
- At least one orchestration API stream test.

## Phased Development Plan

### Phase 1: Contract foundation

- Add `contracts.py`.
- Add `guards.py`.
- Define agent order, phases, refs, quality results.
- Add enter guards for intake, path, outline, and Markdown.
- Add unit tests and a light cross-agent contract.

System still runs mostly the old way, but contract boundaries exist.

### Phase 2: Markdown main product safeguards

- Add `source_references`.
- Generate `## 来源` from `source_references`.
- Extend video and animation brief schemas.
- Add Markdown quality gate for generic briefs.
- Add animation planning fields: `simulation_type`, `visual_model`, `timeline`, `success_check`.

Markdown fully plans auxiliary resources.

### Phase 3: Honest video and simulation-first animation

- Video no-match becomes unavailable.
- Remove or strictly limit unrelated search fallback.
- Add animation DOM/SVG simulation gate.
- Add linked-list special checks.
- Compose supports unavailable resources.

Auxiliary resources are either useful or honestly unavailable.

### Phase 4: Events, recovery, observability

- Add `events.py`.
- Add `recovery.py`.
- Add `observability.py`.
- Stream events include `agent_order`, `depends_on`, `input_refs`, `output_refs`, and `quality_result`.
- Store section-phase checkpoints.
- Record compact traces.

The system becomes debuggable and resumable.

### Phase 5: Prompt budget and full regression

- Add prompt budgets.
- Ensure only Markdown receives full evidence正文.
- Run full cross-agent and API-flow tests.
- Move existing scattered checks behind guards where practical.

The full safety layer is complete.

## Scope Boundaries

This design does not:

- Rewrite LangGraph.
- Add new database tables in the first implementation.
- Make video or animation failure block Markdown正文.
- Let the HTML animation agent decide teaching meaning.
- Parse Markdown as the source of truth for references.

## Self-Review

- No placeholders remain.
- The design covers all ten requested保障 layers.
- The animation responsibility is explicitly moved to `section_markdown_agent`.
- The HTML animation agent is explicitly simulation-first and implementation-only.
- Development can be split into phases while keeping the full target design intact.
