# Supervisor Routing Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize the supervisor's routing decisions so that general Q&A/chitchat queries do not incorrectly trigger tool calls (like `section_markdown_agent` or `course_knowledge_agent`) and are instead answered directly with text.

**Architecture:** Update system prompts in `prompts.py` and tool docstrings in `supervisor.py` to clarify the supervisor's core decision tree (Analyze Intent, Select Sub-agent, Direct Reply, Ask/Clarify) and tool scopes. Add a unit test to verify direct text responses.

**Tech Stack:** Python, LangChain, Pytest

---

### Task 1: Add Unit Tests for Conversational Routing

**Files:**
- Modify: `backend/tests/test_supervisor_force_call.py`

- [ ] **Step 1: Write a failing test for general Q&A query**
  Add a new test `test_supervisor_node_direct_text_reply_for_chitchat_and_qa` that sets up a completed profile state, mock LLM, and runs the supervisor node with the query "什么是 FastAPI". Verify that the mock LLM receives instructions restricting tool usage, and that the result does not contain tool calls.

  Add the following code to `backend/tests/test_supervisor_force_call.py`:
  ```python
  def test_supervisor_node_direct_text_reply_for_chitchat_and_qa() -> None:
      class MockLlm:
          def __init__(self):
              self.tools = []
              
          def bind_tools(self, tools):
              self.tools = tools
              return self

          async def ainvoke(self, messages):
              # Check if the prompt instructs LLM not to use tools for general Q&A
              system_msg = messages[0].content
              assert "## 核心决策逻辑" in system_msg
              assert "直接回复" in system_msg
              # Return a text reply instead of a tool call
              return AIMessage(content="FastAPI 是一个用于构建 API 的现代、快速（高性能）的 Web 框架。")

      supervisor_node = create_supervisor_node(MockLlm())
      
      result = asyncio.run(
          supervisor_node(
              {
                  "query": "什么是 FastAPI",
                  "profile": _complete_profile(),
                  "year_learning_paths": {
                      "year_3": {
                          "current_learning_course": {
                              "grade_id": "year_3",
                              "course_node_id": "year_3_course_1",
                          }
                      }
                  },
                  "messages": [],
              }
          )
      )

      assert not result["messages"][0].tool_calls
      assert "FastAPI 是一个" in result["response"]
  ```

- [ ] **Step 2: Run test to verify it fails**
  Run: `.venv/bin/pytest tests/test_supervisor_force_call.py -k test_supervisor_node_direct_text_reply_for_chitchat_and_qa`
  Expected: FAIL (AssertionError on system_msg check, since "## 核心决策逻辑" is not in the system prompt yet)

- [ ] **Step 3: Commit the test**
  ```bash
  git add tests/test_supervisor_force_call.py
  git commit -m "test: add test case for conversational query routing"
  ```

---

### Task 2: Update Supervisor System Prompt

**Files:**
- Modify: `backend/app/orchestration/agents/prompts.py`

- [ ] **Step 1: Update `SUPERVISOR_BASE_PROMPT`**
  Modify `backend/app/orchestration/agents/prompts.py:3-21` to include the refined decision logic, sub-agent responsibilities, and guidelines.

  Replace:
  ```python
  SUPERVISOR_BASE_PROMPT = """\
  你是学习助手的主调度 AI。你的任务是分析用户需求，并调用合适的工具来提供帮助。

  ## 可用工具
  - `profile_agent`：根据你与用户的对话，生成结构化的基础学习画像。当你已经收集到足够的用户信息（年级、专业、偏好、目标等）时调用。
  - `learning_path_agent`：为指定年级生成学习路径（推荐课程 + 顺序）。前提：用户画像已完成。
  - `course_knowledge_agent`：为学习路径中的课程生成详细的章节大纲。前提：该年级的学习路径已生成。如果不指定 course_id，自动选取下一门待学课程。

  ## 工作流程
  1. 首先通过对话了解用户的基本情况（年级、专业、学习目标等）
  2. 收集到足够信息后，调用 profile_agent 生成结构化画像
  3. 用户指定年级 and 学习主题后，调用 learning_path_agent 生成路径
  4. 路径生成后，调用 course_knowledge_agent 生成课程大纲

  ## 注意事项
  - 如果工具返回错误，不要重复调用同一个工具。向用户解释原因并给出下一步建议。
  - 每轮对话尽量只调用一个工具，让用户有时间理解和确认结果。
  - 回复风格自然、友好、中文。
  """
  ```

  With:
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

  ## 工作流程
  1. 首先通过对话了解用户的基本情况（年级、专业、学习目标等）
  2. 收集到足够信息后，调用 profile_agent 生成结构化画像
  3. 用户指定年级和学习主题后，调用 learning_path_agent 生成路径
  4. 路径生成后，调用 course_knowledge_agent 生成课程大纲
  5. 引导用户开始学习具体课程后，根据需要调用 section_markdown_agent 生成具体内容

  ## 注意事项
  - 如果工具返回错误，不要重复调用同一个工具。向用户解释原因并给出下一步建议。
  - 每轮对话尽量只调用一个工具，让用户有时间理解和确认结果。
  - 回复风格自然、友好、中文。
  """
  ```

- [ ] **Step 2: Verify the test passes**
  Run: `.venv/bin/pytest tests/test_supervisor_force_call.py -v`
  Expected: All 25 tests pass.

- [ ] **Step 3: Commit the prompt change**
  ```bash
  git add app/orchestration/agents/prompts.py
  git commit -m "feat: refine supervisor base prompt with clear routing decision logic"
  ```

---

### Task 3: Restrict Tool Descriptions in Supervisor Node

**Files:**
- Modify: `backend/app/orchestration/agents/supervisor.py`

- [ ] **Step 1: Refine tool docstrings in `create_tools_for_llm`**
  Modify tool definitions in `backend/app/orchestration/agents/supervisor.py:127-208` to include clear prohibitions on generic Q&A calls.

  Update the docstring for `course_knowledge_agent`:
  ```python
      @tool
      async def course_knowledge_agent(course_id: str = "") -> str:
          """为学习路径中的课程生成详细的章节大纲。
          前提：该年级的学习路径已生成。
          注意：仅在为特定课程生成大纲结构时使用。如果是通用的问答或概念解释，绝对禁止调用此工具。
          
          Args:
              course_id: 课程 ID（可选，留空则生成当前课程；"__all_current_grade__" 表示当前年级全部课程）
          """
          return ""
  ```

  Update the docstring for `section_markdown_agent`:
  ```python
      @tool
      async def section_markdown_agent(
          course_id: str = "",
          section_id: str = "",
          scope: str = "default_first_chapter",
      ) -> str:
          """为当前大纲中已存在的具体章节小节生成结构化的 Markdown 教学文档。
          注意：仅在生成课程小节内容时调用。如果用户是询问通用概念（如“什么是 FastAPI”、“如何学习后端”），绝对禁止调用此工具，应直接以文本形式回复用户。

          Args:
              course_id: 课程 ID，留空时使用当前课程
              section_id: 小节或一级章节 ID
              scope: default_first_chapter/single_section/chapter_sections
          """
          return ""
  ```

- [ ] **Step 2: Run pytest to verify all tests pass**
  Run: `.venv/bin/pytest tests/test_supervisor_force_call.py`
  Expected: PASS

- [ ] **Step 3: Commit tool docstring changes**
  ```bash
  git add app/orchestration/agents/supervisor.py
  git commit -m "feat: refine tool descriptions to add Q&A calling restrictions"
  ```
