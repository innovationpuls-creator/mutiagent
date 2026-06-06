# Leaf Interface Design

Date: 2026-06-06

## Goal

Build the `leaf` learning interface opened from the `branch` course path. The interface lets users read generated course chapter content, navigate a collapsible markmap, and use the existing AI conversation panel to generate the current course's chapter teaching content.

This spec only covers `leaf` and the generation flow it needs. The future `forest` chapter quiz agent and completion logic are out of scope, but `leaf` must leave a clear integration point for it.

## Confirmed Product Rules

- `branch` only navigates to `leaf` for `completed` and `current` courses.
- `locked` courses do not enter `leaf`; clicking them in `branch` shows an unlocked-course hint.
- `leaf` uses `/leaf/{course_node_id}`.
- The selected section is stored in the URL as `?section_id=...`.
- `completed` courses can be viewed in `leaf`, but cannot generate or regenerate content.
- Only the `current` course can generate or regenerate chapter teaching content.
- Generation is only for the current course. A later database progress update unlocks the next course.
- First version allows generation of the first chapter only. Later chapters show disabled generation affordances until the future `forest` chapter quiz completion logic unlocks them.
- The future `forest` route receives course and chapter context as `/forest/{course_node_id}?chapter_id=...`.

## Existing Data Facts

The current code already defines these fields:

- Branch course fields: `course_node_id`, `course_or_chapter_theme`, `course_goal`, `status`, `has_outline`.
- Branch status values: `completed`, `current`, `locked`.
- Course outline fields: `course_id`, `course_name`, `grade_year`, `personalization_summary`, `sections`, `learning_sequence`, `total_estimated_hours`.
- Section fields: `section_id`, `parent_section_id`, `depth`, `title`, `order_index`, `description`, `key_knowledge_points`.
- Existing resource storage fields: `section_markdowns`, `section_video_links`, `section_html_animations`.

New implementation work must not rename or infer these fields. Any new field introduced below is part of this design and must be implemented explicitly with tests.

## Architecture

Use the confirmed approach: a dedicated `leaf` read API plus the existing chat/SSE generation channel.

### Read Path

Add `GET /api/leaf/courses/{course_node_id}`.

The API returns course accessibility, course metadata, outline data, generated resources, composed section content, and coarse running-generation status.

Error behavior:

- If the course does not exist for the current user, return `404`.
- If the course exists but is locked, return normal JSON with `access_state` set to `locked`.
- If the course is viewable, return normal JSON with `access_state` set to `available`.

The front end calls this API on `leaf` load and after generation completes.

### Generation Path

Generation continues through `/api/chat/message` so the user experiences it as an AI conversation.

The chat prompt is user-readable and includes:

- Course name.
- `course_node_id`.
- Chapter `section_id`.
- Generation scope.
- Requirement to generate Markdown, video resources, HTML animations, and save composed output.

The backend still enforces current-course-only generation. The prompt text is not the security boundary.

### Page Refresh During Generation

During the current browser session, the chat SSE stream broadcasts generation progress to the open `leaf` page.

On refresh or re-entry, the leaf read API only needs to restore coarse task state such as "generation in progress". It does not need to restore every per-section substate.

Generation task state only needs to exist while the task is running. After completion, the saved course content is the source of truth.

## Leaf UI

### Layout

Desktop only for the first version.

The page uses the project Headspace meditation design system:

- OKLCH colors and existing CSS tokens only.
- LXGW WenKai only.
- Warm paper background, soft surfaces, multi-layer token shadows.
- No HEX/RGB hardcoding.
- No Google Fonts.
- No Material Symbols.
- Motion only on `transform` and `opacity`, with `prefers-reduced-motion`.

The visual direction follows the reference files under:

- `stitch_exports/16699184054374309218`
- `.stitch/16699184054374309218`

The references are layout and mood references only. Their raw HTML must not be copied directly because it uses disallowed HEX colors, Google Fonts, and Material Symbols.

### Markmap

The left markmap:

- Shows the full `sections` hierarchy using `depth`.
- Supports collapse and expand for nodes with children.
- Defaults to all levels expanded.
- Persists collapse state in browser local storage.
- Takes layout space when expanded.
- Collapses to a small left-edge handle.
- Lets the main content recenter when collapsed.

Selection behavior:

- Only leaf sections switch the right-side teaching content.
- Parent chapters expand and collapse only.
- On first entry, if generated content exists, select the first leaf section with content.
- If no generated content exists, select the first chapter parent.
- The URL keeps the selected section as `?section_id=...`.

### Top Fixed Area

The top fixed area shows:

- Course name.
- Current chapter or section title.
- Course status.
- Return to `branch`.
- Chapter quiz entry.

The chapter quiz entry is always shown and routes to `/forest/{course_node_id}?chapter_id=...`.

There is no separate right-side floating tab.

### Content Rendering

The right side renders composed Markdown content.

Video and HTML animation blocks are embedded in the content flow as dedicated blocks:

- Video renders as a warm course video card.
- HTML animation renders inside a sandboxed iframe.
- The iframe may run agent-generated HTML/CSS/small JavaScript but must be isolated from the app document.

Content states must distinguish:

- Outline loading.
- Resource loading.
- Resource generation in progress.
- Generation failed.
- Course locked.
- Empty content.
- Content available.

## Generation Entry Rules

Generation entry appears only for the `current` course.

For the first version:

- The first chapter generation entry is enabled.
- Later chapter generation entries are disabled with copy explaining that the future `forest` chapter quiz must be passed before the next chapter opens.

Generation entry placement:

- Show the entry beside the corresponding first-level chapter in the markmap.
- Do not auto-open the conversation panel when a course has an outline but lacks resources.
- Clicking the entry opens the AI conversation panel and pre-fills the prompt.
- The prompt is not auto-sent; the user must confirm.

For completed courses:

- Do not show generation or regeneration entry points.

## Resource Generation Contract

Generation target:

- Generate one chapter at a time.
- For the first version, generate the first chapter's leaf subsections, such as `1.1`, `1.2`, `1.3`.
- Do not generate later chapter subsections such as `2.1` until chapter progression logic exists.

### Markdown Agent

The Markdown agent generates each leaf subsection's teaching Markdown.

Markdown output must include short resource placeholders:

```md
<!-- video:id=video_1 -->
<!-- animation:id=anim_1 -->
```

The Markdown text itself remains readable. The detailed resource requirements are emitted as structured fields, not packed into the Markdown comments.

New structured fields:

- `video_briefs`
- `animation_briefs`

Video briefs include:

- ID.
- Title.
- Purpose.

Animation briefs include:

- ID.
- Title.
- Concept.
- Required visual elements.
- Motion behavior.
- Spatial size or placement requirement.
- Placement hint.

The animation brief should read like instructions from a UI animation designer.

### Video Agent

The video search agent consumes `video_briefs` and the target section Markdown. It returns videos keyed to the brief IDs.

### HTML Animation Agent

The HTML animation agent consumes `animation_briefs` and the target section Markdown. It returns HTML snippets keyed to the animation brief IDs.

Each generated HTML snippet must remain embeddable and isolated in a sandboxed iframe on the frontend.

### Composition

After Markdown, video, and animation outputs are available, the backend replaces resource placeholders with renderable composed blocks and saves final composed content.

Persist both:

- Final composed section content for direct `leaf` rendering.
- Raw source data: Markdown, video links, HTML animations, briefs, and generation metadata for debugging and regeneration.

## Agent Scheduling And SSE

Generation runs per chapter.

Scheduling:

- Start one subsection agent card per leaf subsection.
- Each subsection first generates Markdown.
- After that subsection's Markdown succeeds, its video search and HTML animation generation start.
- Video and HTML animation generation may run in parallel for that subsection.
- Other subsections continue independently.
- After section resources are ready or downgraded, compose and save.

SSE and UI requirements:

- The conversation timeline must show each subsection as a visible agent card.
- Each card displays three internal states: text, video, animation.
- The UI should make "calling agent", "passing context", "running in parallel", and "saving result" visible.
- The open leaf page also receives generation progress through local frontend events derived from SSE.
- When generation completes, leaf automatically re-fetches `GET /api/leaf/courses/{course_node_id}`.

## Retry And Failure Rules

Retry behavior:

- Markdown generation retries 3 times.
- Video search retries 3 times.
- HTML animation generation retries 3 times.

Failure behavior:

- If Markdown still fails for a subsection, do not generate video or animation for that subsection. Mark that subsection failed. Other subsections continue.
- If video search still fails but Markdown and animation succeed, compose content with a "video temporarily unavailable" fallback block.
- If HTML animation still fails but Markdown and video succeed, compose content with an "animation temporarily unavailable" fallback block.
- If a chapter is already running, block duplicate generation for that same chapter and show "this chapter is generating".

## Regeneration Rules

Regeneration is allowed only for the current course and only through the conversation panel.

If a chapter already has generated content:

- The AI conversation must first ask what the next version should focus on.
- After the user answers, regeneration may overwrite existing content.
- The UI shows generation in progress once regeneration starts.
- The backend preserves an old-version snapshot during regeneration.
- Failed subsections retry 3 times.
- If a subsection still fails, only that subsection rolls back to the old version.
- The rollback notice is shown in the conversation panel only, not inside the main reading content.
- Completion message is a simple one-line completion message.

## Forest Integration Boundary

Future `forest` chapter quiz logic determines when later chapters can be generated.

Current first version:

- Shows later chapter generation entries disabled.
- Disabled copy explains that passing the chapter quiz will open the next chapter.
- The top chapter quiz entry routes to `/forest/{course_node_id}?chapter_id=...`.

The exact completion field name and database structure are not defined in this spec. They will be defined with the future `forest` agent work.

## Testing Priorities

First implementation should prioritize end-to-end key paths:

- `current` course in `branch` navigates to `/leaf/{course_node_id}`.
- `locked` course does not navigate.
- `completed` course opens view-only leaf.
- `GET /api/leaf/courses/{course_node_id}` distinguishes not found, locked, available, empty, generated, and running states.
- First chapter generation through `/api/chat/message` emits subsection agent progress.
- Markdown briefs drive video and animation generation.
- Composition saves final content and raw source resources.
- Leaf refreshes after generation and displays composed Markdown with video and sandboxed animation blocks.
- Generation failures retry and degrade according to this spec.
