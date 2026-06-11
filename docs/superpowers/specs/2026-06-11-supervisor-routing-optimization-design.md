# Design Spec: Supervisor Routing Optimization

## 1. Goal Description
Currently, when a user asks a general question or chitchat query (e.g., "帮我解释一下什么是fastapi"), the supervisor agent (main agent) suffers from tool-calling hallucination and mistakenly invokes `section_markdown_agent`. This sub-agent then fails with an error like "指定小节无法定位" because the query does not correspond to any structural chapter/section in the database.

The goal is to resolve this routing issue by:
1. Rewriting the `SUPERVISOR_BASE_PROMPT` to explicitly introduce all 6 sub-agents, their exact responsibilities, and a clear 4-step decision tree (Analyze Intent, Select Sub-agent, Direct Reply, Ask/Clarify).
2. Refining tool descriptions in the LLM tool definitions to reinforce when they should and should not be invoked.
3. Adding tests to verify that conversational queries do not trigger tool calls.

---

## 2. Proposed Changes

### Component: Backend Orchestration Prompts
#### [MODIFY] [prompts.py](file:///Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/prompts.py)
Update `SUPERVISOR_BASE_PROMPT` to explicitly list all 6 sub-agents and define the decision flowchart.

```python
SUPERVISOR_BASE_PROMPT = """\
你是学习助手的主调度 AI。你的任务是分析用户需求，决定是调度特定的子智能体（子 Agent）提供帮助，还是直接回复用户。

## 核心决策逻辑
1. **分析意图**：仔细分析用户的最新输入及上下文，对照【子智能体职责与分工】进行评估。
2. **选择进入**：若用户意图明确，且属于某个子智能体的职责范围，调用对应的工具进入子智能体。
3. **直接回复**：若用户的请求是通用的技术概念解释（例如：“什么是 FastAPI”、“如何写 Python”）、日常闲聊或问题解答，且【不属于】任何子智能体的职责，你必须【直接以文本形式回复用户】，绝对禁止调用任何工具！
4. **反问确认**：若用户的意图模糊、信息不足，或者你无法判断该调用哪个工具，【绝对不要盲目调用工具】，应直接向用户提问进行确认（例如：“你是想让我解答关于 FastAPI 的基础概念，还是想为当前课程生成关于 FastAPI 的小节教学文档？”）。

## 子智能体职责与分工
- `profile_agent`：画像智能体。负责收集并生成用户的个人画像（年级、专业、偏好、目标等）。仅在需要收集基础信息、更新画像方向时调用。
- `learning_path_agent`：学习路径智能体。负责规划四年的课程推荐与先后顺序。仅在画像已完成，且需要生成或更新整体学习路径时调用。
- `course_knowledge_agent`：课程大纲智能体。负责为具体课程生成详细的章节与小节目录。仅在需要生成、刷新某门课程的章节大纲时调用。
- `section_markdown_agent`：小节文档智能体。负责为大纲中的某个具体二级小节生成 Markdown 教学文档。仅在需要生成具体小节的图文内容时调用。
- `section_video_search_agent`：视频搜索智能体。为小节检索 bilibili 教学视频。仅在需要为章节小节匹配视频资源时调用。
- `section_html_animation_agent`：HTML动画智能体。为小节生成交互式动效辅助教学。仅在需要为章节小节生成动画资源时调用。

## 注意事项
- 如果工具返回错误，不要重复调用同一个工具。向用户解释原因并给出下一步建议。
- 每轮对话尽量只调用一个工具，让用户有时间理解和确认结果。
- 回复风格自然、友好、中文。
"""
```

---

### Component: Backend Orchestration Supervisor Node
#### [MODIFY] [supervisor.py](file:///Users/torch/torch/opt/mutiagent/backend/app/orchestration/agents/supervisor.py)
Refine descriptions inside `create_tools_for_llm` to add restrictive constraints on when to call the tools (especially for `section_markdown_agent`, `course_knowledge_agent`, and others).

For example:
```python
    @tool
    async def section_markdown_agent(
        course_id: str = "",
        section_id: str = "",
        scope: str = "default_first_chapter",
    ) -> str:
        """为当前大纲中已存在的具体章节小节生成结构化的 Markdown 教学文档。
        注意：仅在生成课程小节内容时调用。如果用户是询问通用概念（如“什么是 FastAPI”、“如何学习后端”），绝对禁止调用此工具，应直接以文本形式回复用户。
        """
        return ""
```

---

### Component: Automated Tests
#### [MODIFY] [test_supervisor_force_call.py](file:///Users/torch/torch/opt/mutiagent/backend/tests/test_supervisor_force_call.py)
Add a test verifying that general Q&A and chitchat do not call any tools.

```python
def test_supervisor_node_direct_text_reply_for_chitchat_and_qa():
    # Setup state with completed profile and path
    # Run supervisor node with query "什么是 FastAPI" or "你好"
    # Verify the response has no tool_calls and returns text content directly.
```

---

## 3. Verification Plan

### Automated Tests
Run the pytest suite to verify both existing force-call logic and the new conversational routing case:
```bash
.venv/bin/pytest tests/test_supervisor_force_call.py
```

### Manual Verification
Validate that a chitchat input like "帮我解释一下什么是fastapi" successfully outputs a textual explanation without attempting to transition to `section_markdown_agent`.
