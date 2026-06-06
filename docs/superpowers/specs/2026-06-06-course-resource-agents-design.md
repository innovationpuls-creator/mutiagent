# Course Resource Agents Design

## Goal

用户在现有对话框内输入“开始学习这门课”“生成当前课程教学内容”“生成第一章内容”等请求后，后端基于当前课程节点生成可学习的教学资源，并把资源持久化到数据库。

课程大纲的真实结构是一级大章加二级小节，例如 `1`、`1.1`、`1.2`、`1.3`。本设计的强制资源粒度是二级及更深的小节节点：`1.1`、`1.2`、`1.3` 每个点都必须有 Markdown 文档；视频和 HTML 动画是小节级可选资源。

## Current System Facts

- 现有编排入口是 `backend/app/orchestration/graph.py`。
- 现有 worker agent 是 `profile_agent`、`learning_path_agent`、`course_knowledge_agent`。
- 当前课程大纲持久化在 `UserCourseKnowledgeOutline.outline_data`。
- 当前课程大纲读取和写入通过 `backend/app/services/course_knowledge_service.py`。
- 当前聊天 API 在 `backend/app/api/orchestration.py` 中每轮从数据库加载 `profile`、`year_learning_paths` 和 `course_knowledge`。
- 当前 LLM 工厂在 `backend/app/orchestration/llm.py`，已经通过 `model_kwargs={"extra_body": {...}}` 透传百炼 OpenAI 兼容参数。

## New Worker Agents

新增三个 worker agent：

1. `section_markdown_agent`
   - 根据当前课程大纲中的单个小节节点生成完整 Markdown 教学内容。
   - 输入参数：`course_id`、`section_id`。
   - 输出资源写入 `outline_data["section_markdowns"][section_id]`。

2. `section_video_search_agent`
   - 使用当前 LLM API 的联网搜索模式搜索与章节点匹配的视频链接。
   - 输入参数：`course_id`、`section_id`。
   - 联网参数：`extra_body.enable_search = true`，并设置 `search_options.forced_search = true`。
   - 输出资源写入 `outline_data["section_video_links"][section_id]`。

3. `section_html_animation_agent`
   - 读取 Markdown 教学内容里的动画展示点，生成 HTML 动画资源。
   - 输入参数：`course_id`、`section_id`。
   - 输出资源写入 `outline_data["section_html_animations"][section_id]`。

## Agent I/O and Interconnection Contract

### Upstream: `course_knowledge_agent`

`course_knowledge_agent` 保持现有职责：生成课程大纲，并把 `CourseKnowledgeOutput` 写入 `UserCourseKnowledgeOutline.outline_data`。

输入：

```json
{
  "course_id": ""
}
```

状态依赖：

- `state["user_id"]`
- `state["profile"]`
- `state["year_learning_paths"]`
- `state["latest_grade_year"]`

输出：

```json
{
  "course_knowledge": {
    "course_id": "year_3_course_1",
    "course_name": "AI 应用开发",
    "grade_year": "year_3",
    "sections": [
      {
        "section_id": "1",
        "parent_section_id": null,
        "depth": 1,
        "title": "需求拆解",
        "order_index": 1,
        "description": "确认功能边界与验收标准。",
        "key_knowledge_points": ["功能边界", "验收标准"]
      },
      {
        "section_id": "1.1",
        "parent_section_id": "1",
        "depth": 2,
        "title": "学习目标",
        "order_index": 2,
        "description": "明确本节学习目标。",
        "key_knowledge_points": ["功能边界"]
      }
    ]
  }
}
```

互联规则：

- 如果用户请求生成教学内容，但数据库中没有当前课程大纲，先调用 `course_knowledge_agent`。
- `course_knowledge_agent` 完成后，图路由回到 `supervisor`，由 `supervisor` 调用 `section_markdown_agent`。

### Agent 1: `section_markdown_agent`

职责：定位目标小节，给每个目标小节生成完整 Markdown 教学文档。一级大章只用于展开子小节，不写入一级大章文档。

本协议中的状态输出示例只展示新增或变更字段；实际返回和持久化时必须保留 `course_knowledge` 中已有的大纲字段。

工具输入：

```json
{
  "course_id": "",
  "section_id": "",
  "scope": "default_first_chapter"
}
```

`scope` 只使用以下值：

- `default_first_chapter`：未指定章节时，展开当前课程大纲中排序最靠前的一级章节。
- `single_section`：只生成一个二级及更深小节。
- `chapter_sections`：展开指定一级大章下的全部二级及更深小节。
- `course_sections`：生成当前课程全部二级及更深小节。

状态依赖：

- `state["user_id"]`
- `state["course_knowledge"]`
- `state["query"]`

目标小节解析规则：

- `scope == "single_section"` 时，`section_id` 必须命中 `sections[*].section_id`，且该 section 的 `depth > 1`。
- `scope == "chapter_sections"` 时，`section_id` 必须命中一级大章，目标小节为 `parent_section_id == section_id` 且 `depth > 1` 的全部 section。
- `scope == "default_first_chapter"` 时，先找 `depth == 1` 且 `order_index` 最小的一级大章，再展开它的子小节。
- `scope == "course_sections"` 时，目标小节为 `depth > 1` 的全部 section。

LLM 输入：

```json
{
  "course": {
    "course_id": "year_3_course_1",
    "course_name": "AI 应用开发",
    "grade_year": "year_3",
    "personalization_summary": "..."
  },
  "parent_section": {
    "section_id": "1",
    "title": "需求拆解",
    "description": "确认功能边界与验收标准。"
  },
  "section": {
    "section_id": "1.1",
    "title": "学习目标",
    "description": "明确本节学习目标。",
    "key_knowledge_points": ["功能边界"]
  }
}
```

LLM 结构化输出：

```json
{
  "section_id": "1.1",
  "parent_section_id": "1",
  "title": "学习目标",
  "markdown": "# 学习目标\n\n...",
  "animation_briefs": [
    {
      "animation_id": "section-1-1-animation-1",
      "title": "目标到验收标准",
      "concept": "展示学习目标如何收敛为验收标准",
      "placement_hint": "放在“核心概念”之后"
    }
  ]
}
```

状态输出：

```json
{
  "course_knowledge": {
    "section_markdowns": {
      "1.1": {
        "section_id": "1.1",
        "parent_section_id": "1",
        "title": "学习目标",
        "markdown": "# 学习目标\n\n...",
        "animation_briefs": [],
        "generated_at": "2026-06-06T00:00:00Z"
      }
    }
  },
  "course_resource_plan": {
    "course_id": "year_3_course_1",
    "scope": "chapter_sections",
    "target_section_ids": ["1.1", "1.2", "1.3"],
    "markdown_section_ids": ["1.1", "1.2", "1.3"],
    "video_section_ids": [],
    "animation_section_ids": []
  }
}
```

互联规则：

- `section_markdown_agent` 完成后，图路由直接进入 `section_video_search_agent`。
- `section_video_search_agent` 读取 `course_resource_plan.target_section_ids`，不重新解析用户自然语言。

### Agent 2: `section_video_search_agent`

职责：给每个目标小节搜索教学视频链接，并保证每条视频结果都有 `url` 和 `cover_url`。

工具输入：

```json
{
  "course_id": "",
  "section_id": "",
  "scope": "default_first_chapter"
}
```

直接从 `section_markdown_agent` 路由进入时，使用 `state["course_resource_plan"]`，不读取工具输入。

状态依赖：

- `state["user_id"]`
- `state["course_knowledge"]`
- `state["course_resource_plan"]`

LLM 调用参数：

```json
{
  "extra_body": {
    "enable_thinking": true,
    "enable_search": true,
    "search_options": {
      "forced_search": true,
      "search_strategy": "turbo"
    }
  }
}
```

LLM 输入：

```json
{
  "course_name": "AI 应用开发",
  "section_id": "1.1",
  "section_title": "学习目标",
  "section_markdown_excerpt": "# 学习目标\n\n...",
  "search_goal": "搜索适合该小节学习目标的视频教程，优先返回可直接打开的视频页面 URL。"
}
```

LLM 结构化输出：

```json
{
  "section_id": "1.1",
  "query": "AI 应用开发 需求拆解 学习目标 视频教程",
  "videos": [
    {
      "title": "AI Agent 需求拆解教程",
      "url": "https://example.com/video",
      "cover_url": "https://example.com/cover.jpg",
      "source": "example.com"
    }
  ]
}
```

本地规范化输出：

```json
{
  "section_id": "1.1",
  "parent_section_id": "1",
  "query": "AI 应用开发 需求拆解 学习目标 视频教程",
  "videos": [
    {
      "title": "AI Agent 需求拆解教程",
      "url": "https://example.com/video",
      "cover_url": "https://example.com/cover.jpg",
      "cover_status": "provided",
      "source": "example.com"
    },
    {
      "title": "无封面视频",
      "url": "https://example.com/video-without-cover",
      "cover_url": "data:image/svg+xml;utf8,<svg ...></svg>",
      "cover_status": "fallback",
      "source": "example.com"
    }
  ],
  "generated_at": "2026-06-06T00:00:00Z"
}
```

状态输出：

```json
{
  "course_knowledge": {
    "section_video_links": {
      "1.1": {
        "section_id": "1.1",
        "parent_section_id": "1",
        "query": "AI 应用开发 需求拆解 学习目标 视频教程",
        "videos": []
      }
    }
  },
  "course_resource_plan": {
    "video_section_ids": ["1.1", "1.2", "1.3"]
  }
}
```

互联规则：

- `section_video_search_agent` 完成后，图路由直接进入 `section_html_animation_agent`。
- `section_html_animation_agent` 读取 `section_markdowns[*].animation_briefs`，不读取视频搜索结果作为动画输入。

### Agent 3: `section_html_animation_agent`

职责：为每个目标小节中需要动画展示的内容生成 HTML 动画。没有动画展示点的小节写入空 `animations`。

工具输入：

```json
{
  "course_id": "",
  "section_id": "",
  "scope": "default_first_chapter"
}
```

直接从 `section_video_search_agent` 路由进入时，使用 `state["course_resource_plan"]`，不读取工具输入。

状态依赖：

- `state["user_id"]`
- `state["course_knowledge"]`
- `state["course_resource_plan"]`

LLM 输入：

```json
{
  "course_name": "AI 应用开发",
  "section_id": "1.1",
  "section_title": "学习目标",
  "markdown": "# 学习目标\n\n...",
  "animation_briefs": [
    {
      "animation_id": "section-1-1-animation-1",
      "title": "目标到验收标准",
      "concept": "展示学习目标如何收敛为验收标准",
      "placement_hint": "放在“核心概念”之后"
    }
  ]
}
```

LLM 结构化输出：

```json
{
  "section_id": "1.1",
  "animations": [
    {
      "animation_id": "section-1-1-animation-1",
      "title": "目标到验收标准",
      "html": "<section class=\"section-animation\" data-animation-id=\"section-1-1-animation-1\">...</section>"
    }
  ]
}
```

本地规范化规则：

- `animation_id` 必须来自 `animation_briefs[*].animation_id`。
- `html` 必须是单段可嵌入 HTML 字符串。
- 如果 `animation_briefs` 为空，写入 `animations: []`。

状态输出：

```json
{
  "course_knowledge": {
    "section_html_animations": {
      "1.1": {
        "section_id": "1.1",
        "parent_section_id": "1",
        "animations": [
          {
            "animation_id": "section-1-1-animation-1",
            "title": "目标到验收标准",
            "html": "<section class=\"section-animation\" data-animation-id=\"section-1-1-animation-1\">...</section>",
            "generated_at": "2026-06-06T00:00:00Z"
          }
        ],
        "generated_at": "2026-06-06T00:00:00Z"
      }
    }
  },
  "course_resource_result": {
    "course_id": "year_3_course_1",
    "generated_section_ids": ["1.1", "1.2", "1.3"],
    "markdown_count": 3,
    "video_count": 2,
    "animation_count": 1
  },
  "response": "《AI 应用开发》的 1.1、1.2、1.3 教学内容已生成：每个小节都有 Markdown 文档，视频与动画资源已同步保存。"
}
```

互联规则：

- `section_html_animation_agent` 是教学资源流水线的最后一个 agent。
- `section_html_animation_agent` 完成后图路由结束。

## Graph and Rule Wiring

`supervisor.py` 的 `create_tools_for_llm()` 暴露以下新增工具：

- `section_markdown_agent(course_id: str = "", section_id: str = "", scope: str = "default_first_chapter")`
- `section_video_search_agent(course_id: str = "", section_id: str = "", scope: str = "default_first_chapter")`
- `section_html_animation_agent(course_id: str = "", section_id: str = "", scope: str = "default_first_chapter")`

`graph.py` 的 `WORKER_AGENTS` 增加三个新 agent，`AGENT_LABELS` 增加三个中文标签。

`route_after_worker()` 增加固定流水线：

```text
section_markdown_agent -> section_video_search_agent
section_video_search_agent -> section_html_animation_agent
section_html_animation_agent -> END
```

`course_knowledge_agent` 完成后，如果当前 `query` 是教学内容生成请求，路由回 `supervisor`，再由 `supervisor` 调用 `section_markdown_agent`。

`rule_engine.py` 增加教学内容生成意图：

- 用户画像未完成时，阻止三个 section resource agent。
- 学习路径不存在时，阻止三个 section resource agent。
- 课程大纲不存在且用户请求教学内容时，强制调用 `course_knowledge_agent`。
- 课程大纲存在且用户请求教学内容时，强制调用 `section_markdown_agent`。

## Stored Resource Shape

资源统一挂在现有 `outline_data` 下，不新增数据库表。

```json
{
  "section_markdowns": {
    "1.1": {
      "section_id": "1.1",
      "parent_section_id": "1",
      "title": "学习目标",
      "markdown": "# 学习目标\n\n...",
      "animation_briefs": [
        {
          "animation_id": "section-1-1-animation-1",
          "title": "从用户目标到验收标准",
          "concept": "展示需求拆解如何从目标收敛到可验收任务",
          "placement_hint": "放在“核心概念”之后"
        }
      ],
      "generated_at": "2026-06-06T00:00:00Z"
    }
  },
  "section_video_links": {
    "1.1": {
      "section_id": "1.1",
      "parent_section_id": "1",
      "query": "AI Agent 需求拆解 学习目标 教程 视频",
      "videos": [
        {
          "title": "AI Agent 需求拆解教程",
          "url": "https://example.com/video",
          "cover_url": "https://example.com/cover.jpg",
          "cover_status": "provided",
          "source": "example.com"
        }
      ],
      "generated_at": "2026-06-06T00:00:00Z"
    }
  },
  "section_html_animations": {
    "1.1": {
      "section_id": "1.1",
      "parent_section_id": "1",
      "animations": [
        {
          "animation_id": "section-1-1-animation-1",
          "title": "从用户目标到验收标准",
          "html": "<section class=\"section-animation\" data-animation-id=\"section-1-1-animation-1\">...</section>",
          "generated_at": "2026-06-06T00:00:00Z"
        }
      ],
      "generated_at": "2026-06-06T00:00:00Z"
    }
  }
}
```

`cover_status` 只使用两个值：

- `provided`：联网结果或模型输出提供了可用封面 URL。
- `fallback`：未拿到封面 URL，后端生成稳定的 SVG data URL 写入 `cover_url`。

## Chat Flow

用户在对话框内触发课程教学内容生成时，编排流程如下：

1. 从数据库加载当前用户画像、学习路径和当前课程大纲。
2. 如果当前课程大纲不存在，先调用 `course_knowledge_agent` 生成大纲。
3. 定位本轮需要生成资源的目标小节列表。
   - 用户明确说“第一章”时，先定位 `sections[*].section_id == "1"`，再展开它的子小节，例如 `1.1`、`1.2`、`1.3`。
   - 用户明确说“1.2”时，只生成 `sections[*].section_id == "1.2"` 对应的小节资源。
   - 用户未指定章节时，默认使用当前课程大纲中排序最靠前的一级章节，并展开该章下的全部子小节。
   - 用户要求“生成当前课程教学内容”时，生成当前课程大纲里全部二级及更深小节资源。
4. 对每个目标小节调用 `section_markdown_agent`，每个小节都必须写入一份完整 Markdown。
5. 对每个目标小节调用 `section_video_search_agent`，搜索适合该小节点的视频资源；没有可用视频时写入空 `videos`。
6. 如果小节 Markdown 中有 `animation_briefs`，调用 `section_html_animation_agent` 生成该小节点的 HTML 动画资源。
7. 将三个资源写回 `UserCourseKnowledgeOutline.outline_data`。
8. 对话框返回简短完成说明，说明课程名、已生成的小节编号、Markdown、视频和动画资源状态。

## Error Handling

- 如果用户画像不存在或不完整，沿用现有规则，先走 `profile_agent`。
- 如果学习路径不存在，沿用现有规则，先走 `learning_path_agent`。
- 如果课程大纲无法定位当前课程，返回现有 `course_knowledge_agent` 的错误语义。
- 如果视频搜索没有返回封面，后端必须生成 `cover_status="fallback"` 和 SVG data URL。
- 如果视频搜索没有返回任何 URL，`videos` 写入空列表，并在对话回复中说明对应小节暂未检索到可用视频链接。
- 如果 HTML 动画生成失败，保留 Markdown 和视频结果，`section_html_animations[section_id].animations` 写入空列表，并在对话回复中说明动画资源稍后可重新生成。

## Testing

后端测试覆盖：

- `section_markdown_agent` 能读取课程大纲小节并写入 `section_markdowns[section_id]`。
- 当用户请求“第一章”时，后端必须为 `1.1`、`1.2`、`1.3` 这些子小节分别写入 Markdown，不能只写入 `1`。
- `section_video_search_agent` 调用联网 LLM 时传入 `extra_body.enable_search = true` 和 `search_options.forced_search = true`。
- `section_video_search_agent` 在封面缺失时写入 `cover_status="fallback"` 和非空 `cover_url`。
- `section_html_animation_agent` 根据 `animation_briefs` 写入 `section_html_animations[section_id].animations`。
- 编排图能识别新 agent 并路由执行。
- 聊天 API 在用户请求生成教学内容时能返回完成消息，并把资源持久化到 `UserCourseKnowledgeOutline.outline_data`。

## Scope

本次实现只做后端 agent、编排、持久化和后端测试。前端展示可以继续读取 `course_knowledge` 扩展字段；不在本次实现中改造新的教学页面。
