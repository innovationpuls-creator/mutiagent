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
