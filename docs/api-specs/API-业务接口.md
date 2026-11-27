# 业务接口 (Business API)

本文档定义了一棵树 (OneTree) 系统的核心业务 API 接口，涵盖 Chat 编排、繁枝路径与成长报告、展叶细节、自测森林、培养方案、学情管理以及教材知识库端点。

* **Base URL**: `/api`
* **身份认证**：所有业务接口均需要通过 Header 传递 JWT Access Token：`Authorization: Bearer <access_token>`

---

## 目录
1. [Chat 智能体对话编排](#1-chat-智能体对话编排)
2. [Branch 繁枝学习路径与成长](#2-branch-繁枝学习路径与成长)
3. [Leaf 展叶精读大纲](#3-leaf-展叶精读大纲)
4. [Forest 森林自测评估](#4-forest-森林自测评估)
5. [Profile 画像仪表盘](#5-profile-画像仪表盘)
6. [培养方案（Student & Admin）](#6-培养方案student--admin)
7. [Admin & Data 学情与用户管理](#7-admin--data-学情与用户管理)
8. [Knowledge Base 教材知识库与缺口闭环](#8-knowledge-base-教材知识库与缺口闭环)

---

## 1. Chat 智能体对话编排

### 1.1 POST `/chat/start` — 启动对话
开启一个新的多智能体陪伴式对话（如 onboarding 破冰阶段），返回 session_id 及开场问候。

* **请求体** (空)
* **响应参数** `200 OK` (对应 `ChatResponse` 模式)
  ```json
  {
    "session_id": "4a7b51c8-2b36-4d0f-baee-1594e9f7a7db",
    "reply_text": "你好！我是你的 AI 学习助手。为了帮助你定制专属的学习大纲和 4 年学习路径，能先告诉我你的年级和专业吗？",
    "profile": null,
    "year_learning_paths": null,
    "course_knowledge": null
  }
  ```

### 1.2 POST `/chat/message` — 发送用户消息 (SSE 流式)
发送用户的对话消息，并通过 Server-Sent Events (SSE) 流式返回中枢 Supervisor 的思考、子智能体调度及大模型流式文本输出。

* **请求体** `application/json`
  | 字段 | 类型 | 必填 | 说明 |
  | :--- | :--- | :--- | :--- |
  | `session_id` | str | 是 | 会话 ID |
  | `message` | str | 是 | 用户输入的提问或指令 |

* **响应** `200 OK` (内容类型 `text/event-stream`)
  每一行返回符合下述格式的事件帧：
  ```text
  event: <event_name>
  data: <JSON_payload>
  ```
  **典型事件流程例**：
  1. `session_started`
  2. `message` (type = `supervisor_thinking`, text = "正在规划...")
  3. `agent_calling` (agent = `profile_agent`)
  4. `agent_progress` (message = "正在提取画像...")
  5. `agent_result` (success = true)
  6. `text_chunk` (chunk = "收到了你的专业是...")
  7. `message_completed`
  8. `session_completed`

### 1.3 GET `/chat/sessions/{session_id}` — 读取历史会话
读取数据库中持久化的会话历史消息明细。

* **响应参数** `200 OK` (对应 `SessionStateResponse` 模式)
  ```json
  {
    "session_id": "4a7b51c8-2b36-4d0f-baee-1594e9f7a7db",
    "user_uid": "user-uuid",
    "messages": [
      {
        "type": "human",
        "content": "你好，我是大一计算机专业学生。"
      },
      {
        "type": "ai",
        "content": "收到！已为你记录。你有什么特定的学习目标吗？"
      }
    ],
    "profile": {},
    "year_learning_paths": {},
    "latest_grade_year": "year_1",
    "course_knowledge": {},
    "updated_at": "2026-06-19T10:05:00Z"
  }
  ```

---

## 2. Branch 繁枝学习路径与成长

### 2.1 GET `/branch/canopy` — 获取树冠总览
拉取学生全局学习进度的树状总览，用于渲染首页的“树冠模型”。

* **响应参数** `200 OK` (对应 `CanopyOverviewResponse` 模式)
  ```json
  {
    "courses": [
      {
        "id": "data-structure",
        "title": "数据结构",
        "grade": "大一",
        "status": "current",
        "score": 85,
        "description": "深入学习链表、树、图等结构及基本算法应用",
        "prerequisite_ids": ["c-programming"]
      }
    ],
    "growth_stage": 1,
    "completed_count": 4,
    "active_rate": 80,
    "avg_score": 88,
    "focused_hours": 12.5,
    "milestones": [
      {
        "date": "2026-06-18",
        "title": "初学乍练",
        "desc": "完成首门课程学习",
        "reached": true
      }
    ],
    "quality_scores": {
      "data-structure": {
        "accuracy": 92,
        "difficulty_fit": 90,
        "completeness": 94,
        "overall": 92,
        "suggestions": [],
        "scored_at": "2026-06-19T10:00:00Z"
      }
    }
  }
  ```

### 2.2 GET `/branch/overview` — 获取全学年路径总览
拉取大一到大四的完整课程拓扑路线图及当前活跃节点状态。

* **响应参数** `200 OK` (对应 `BranchOverviewReadResponse` 模式)
  ```json
  {
    "years": {
      "year_1": {
        "grade_id": "year_1",
        "grade_name": "大一",
        "has_courses": true,
        "has_outline_content": true,
        "is_clickable": true,
        "current_course_id": "data-structure",
        "courses": [
          {
            "course_node_id": "c-programming",
            "course_or_chapter_theme": "C语言程序设计",
            "course_goal": "掌握过程化程序设计思想与 C 语言语法基础。",
            "status": "completed",
            "has_outline": true
          },
          {
            "course_node_id": "data-structure",
            "course_or_chapter_theme": "数据结构",
            "course_goal": "深入学习链表、树、图等结构及基本算法应用。",
            "status": "current",
            "has_outline": true
          }
        ]
      },
      "year_2": { "grade_id": "year_2", "grade_name": "大二", "has_courses": false, "has_outline_content": false, "is_clickable": false, "current_course_id": null, "courses": [] }
    },
    "updated_at": "2026-06-19T10:30:00Z"
  }
  ```
  * `status` 的枚举值：`locked` (未解锁) / `current` (当前进行中) / `completed` (已通关/完成)。

### 2.3 GET `/learning-path/me` — 获取用户自己的全部学年路径列表
获取由路径规划智能体生成的、归属于当前用户的所有学年的路径大纲数据。

* **响应参数** `200 OK` (对应 `YearLearningPathsReadResponse` 模式)
  ```json
  {
    "year_learning_paths": {
      "year_1": {
        "user_uid": "user-uuid",
        "grade_id": "year_1",
        "grade_name": "大一",
        "learning_topic": "计算机基础与算法导论",
        "grade_plans": {
          "year_1": {
            "grade_id": "year_1",
            "grade_name": "大一",
            "course_nodes": [
              {
                "course_node_id": "data-structure",
                "course_or_chapter_theme": "数据结构",
                "course_goal": "深入学习链表、树、图等结构"
              }
            ]
          }
        },
        "current_learning_course": {
          "course_node_id": "data-structure",
          "course_or_chapter_theme": "数据结构",
          "grade_id": "year_1",
          "course_goal": "深入学习链表、树、图等结构",
          "current_focus": "链表基本操作",
          "next_action": "完成单链表测验",
          "progress_state": "learning"
        }
      }
    },
    "updated_at": "2026-06-19T10:30:00Z"
  }
  ```

### 2.4 POST `/branch/canopy/report/stream` — 生成累计 AI 成长报告 (SSE)
按需汇总当前学生的真实学习记录并流式生成结构化成长报告（`report_stage` / `report_completed` / `report_error`），详细字段与统计口径见 [API-成长报告](./API-成长报告.md)。

---

## 3. Leaf 展叶精读大纲

### 3.1 GET `/leaf/courses/{course_node_id}` — 获取特定课程精读信息
加载特定课程节点对应的详细精读大纲及互动章节卡片配置。

* **响应参数** `200 OK` (对应 `LeafCourseReadResponse` 模式)
  ```json
  {
    "chapter_progress": [
      {
        "chapter_id": "sec-1",
        "state": "available",
        "best_score": 85,
        "latest_attempt_id": "attempt-uuid-123"
      }
    ],
    "access_state": "available",
    "course": {
      "course_node_id": "data-structure",
      "grade_id": "year_1",
      "course_or_chapter_theme": "数据结构",
      "course_goal": "深入学习链表、树、图等结构及基本算法应用。",
      "status": "current",
      "has_outline": true
    },
    "outline": {
      "course_id": "data-structure",
      "course_name": "数据结构",
      "personalization_summary": "基于你的画像，我们为你重点倾斜了内存管理与图算法的实例分析。",
      "sections": [
        {
          "section_id": "sec-1",
          "title": "单链表及其基本操作"
        }
      ],
      "total_estimated_hours": "32小时"
    },
    "sections": [],
    "section_composed_markdowns": {
      "sec-1": {
        "markdown_content": "### 1. 链表定义\n链表是一种链式存储的线性表..."
      }
    },
    "section_resource_errors": {},
    "generation_status": {
      "course_node_id": "data-structure",
      "chapter_section_id": "sec-1",
      "status": "running",
      "message": "正在生成小节资源"
    },
    "can_generate": true,
    "first_generatable_chapter_id": "sec-1",
    "locked_reason": null
  }
  ```

---

## 4. Forest 森林自测评估

### 4.1 GET `/forest/courses/{course_node_id}/chapters/{chapter_id}/quiz` — 获取章节测验状态
检查或加载当前用户对特定章节的测验信息及最新一次的作答成绩。

* **响应参数** `200 OK` (对应 `ForestQuizSessionReadResponse` 模式)
  ```json
  {
    "course": {
      "course_node_id": "data-structure",
      "grade_id": "year_1",
      "course_or_chapter_theme": "数据结构",
      "course_goal": "掌握常见数据组织方式",
      "status": "current",
      "has_outline": true
    },
    "chapter": {
      "section_id": "chapter-1",
      "title": "单链表及其基本操作"
    },
    "progress": {
      "course_node_id": "data-structure",
      "chapter_id": "chapter-1",
      "state": "available",
      "best_score": 85,
      "latest_attempt_id": "attempt-uuid-123",
      "passed_at": null,
      "updated_at": "2026-06-19T10:40:00Z"
    },
    "quiz": {
      "quiz_version": "a1b2c3...64位十六进制SHA256",
      "quiz_id": "quiz-uuid-999",
      "course_node_id": "data-structure",
      "chapter_id": "chapter-1",
      "status": "ready",
      "questions": [
        {
          "question_id": "q1",
          "type": "single_choice",
          "prompt": "单链表插入一个节点的时间复杂度是多少？",
          "options": [
            { "option_id": "A", "text": "O(1)" },
            { "option_id": "B", "text": "O(n)" },
            { "option_id": "C", "text": "O(log n)" },
            { "option_id": "D", "text": "O(n^2)" }
          ],
          "starter_code": "",
          "image_prompt": "",
          "points": 100
        }
      ],
      "generation_error": "",
      "created_at": "2026-06-19T10:35:00Z",
      "updated_at": "2026-06-19T10:35:00Z"
    },
    "latest_attempt": null,
    "next_unlocked_chapter_id": null,
    "next_course_id": null
  }
  ```

### 4.2 POST `/forest/courses/{course_node_id}/chapters/{chapter_id}/quiz/generate` — 动态生成章节试卷
请求智能体为特定章节动态组装出一套测验。

* **请求体** `application/json` (对应 `ForestQuizGenerateRequest` 模式)
  ```json
  {
    "regenerate": false
  }
  ```
* **响应参数** `200 OK` (对应 `ForestQuizRead` 模式)
  ```json
  {
    "quiz_version": "a1b2c3...64位十六进制SHA256",
    "quiz_id": "quiz-uuid-999",
    "course_node_id": "data-structure",
    "chapter_id": "chapter-1",
    "status": "ready",
    "questions": [
      {
        "question_id": "q1",
        "type": "single_choice",
        "prompt": "单链表插入一个节点的时间复杂度是多少？",
        "options": [
          { "option_id": "A", "text": "O(1)" },
          { "option_id": "B", "text": "O(n)" }
        ],
        "starter_code": "",
        "image_prompt": "",
        "points": 100
      }
    ],
    "generation_error": "",
    "created_at": "2026-06-19T10:35:00Z",
    "updated_at": "2026-06-19T10:35:00Z"
  }
  ```

### 4.3 POST `/forest/quizzes/{quiz_id}/attempts` — 提交作答并打分
提交对测验试卷的答题并获取即时评分结果（`client_submission_id` 与 `quiz_version` 可选，提供时必须成对传入）。

* **请求体** `application/json` (对应 `ForestQuizAttemptCreateRequest` 模式)
  ```json
  {
    "answers": {
      "q1": "A"
    },
    "client_submission_id": "550e8400-e29b-41d4-a716-446655440000",
    "quiz_version": "a1b2c3...64位十六进制SHA256"
  }
  ```
* **响应参数** `200 OK` (对应 `ForestAttemptRead` 模式)
  ```json
  {
    "quiz_version": "a1b2c3...64位十六进制SHA256",
    "attempt_id": "att-uuid-888",
    "quiz_id": "quiz-uuid-999",
    "answers": {
      "q1": "A"
    },
    "score": 100,
    "passed": true,
    "grading_result": {
      "q1": {
        "is_correct": true,
        "feedback": "回答正确，插入操作仅需修改指针，复杂度为 O(1)。"
      }
    },
    "created_at": "2026-06-19T10:45:00Z"
  }
  ```

### 4.4 POST `/forest/quizzes/{quiz_id}/attempts/stream` — 提交作答 (SSE 流式批改)
采用异步 SSE 流式广播批改进度、薄弱知识点分析和后续关卡解锁结果。

* **请求体** 同上 `POST /forest/quizzes/{quiz_id}/attempts`。
* **响应** `text/event-stream`
  返回事件包括：
  * `event: status` -> `phase = "grading"`（正在批改答案）
  * `event: status` -> `phase = "analyzing"`（正在分析学习进度与薄弱点）
  * `event: done` -> 包含 `attempt`、`weaknesses`、`canopy_overview`、`next_unlocked_chapter_id`、`next_course_id`
  * `event: error` -> 包含 `message` 与 `status_code`

### 4.5 POST `/forest/ai/stream` — 森林测验 AI 答疑助手 (SSE)
针对自测错题或概念，调用 AI 助手进行流式对话答疑。

* **请求体** `application/json` (对应 `ForestAiStreamRequest` 模式)
  | 字段 | 类型 | 必填 | 说明 |
  | :--- | :--- | :--- | :--- |
  | `course_node_id` | str | 是 | 关联的课程 ID |
  | `chapter_id` | str | 是 | 关联的章节 ID |
  | `quiz_id` | str | 否 | 关联的测验 ID |
  | `question_id` | str | 否 | 提问的问题 ID |
  | `message` | str | 是 | 学生对 AI 提问的话 (最长4000字) |
  | `active_question_context` | object | 是 | 详见下方 `ForestAiContext` 结构说明 |
  | `image_attachment` | str | 否 | Base64 格式的可选图片附件 |

* **`active_question_context` 结构说明 (对应 `ForestAiContext` 模式)**
  | 字段 | 类型 | 说明 |
  | :--- | :--- | :--- |
  | `course_node_id` | str | 课程节点 ID |
  | `chapter_id` | str | 章节 ID |
  | `quiz_id` | str (可空) | 测验 ID |
  | `question_id` | str (可空) | 问题 ID |
  | `question` | dict (可空) | 问题的完整结构体 (包括题干及选项) |
  | `answer` | object (可空) | 用户的作答值 |
  | `grading_result` | dict (可空) | 该题目的批改解析结果 |

* **响应** `text/event-stream`
  * 发送流式文本帧 `forest_ai_text_chunk` ➡️ 完成标识 `forest_ai_completed`（异常时返回 `forest_error`）。

---

## 5. Profile 画像仪表盘

### 5.1 GET `/profile/dashboard` — 读取画像仪表盘数据
读取当前登录学生的个人画像完整数据、推荐清单以及今日推荐学习卡片。

* **响应参数** `200 OK` (`ProfileDashboardReadResponse`)
  ```json
  {
    "hasCompleteProfile": true,
    "profile": {
      "currentGrade": "大一",
      "major": "计算机科学与技术",
      "learningStage": "基础学习",
      "hasClearGoal": "有明确目标",
      "learningMethodPreference": "图文结合加动手实践",
      "learningPacePreference": "中等速度",
      "contentPreference": ["视频教程", "动画模拟"],
      "weeklyAvailableTime": "每周约15小时"
    },
    "profileCompleteness": 85,
    "profileSummaryText": "你是一个有清晰目标且学习态度积极的计算机大一新生...",
    "todayLearning": {
      "title": "继续学习：数据结构",
      "description": "深入学习链表、树、图等结构及基本算法应用。 当前重点：单链表指针修改",
      "source": "学习路径智能体",
      "currentLearningCourse": {
        "course_node_id": "data-structure",
        "course_or_chapter_theme": "数据结构"
      }
    },
    "recommendations": [
      {
        "id": "rec-profile-goal",
        "title": "学习目标拆解",
        "duration": "每周15小时",
        "description": "围绕近期目标拆解学习任务",
        "accent": "sage"
      }
    ]
  }
  ```

---

## 6. 培养方案（Student & Admin）

> 说明：历史 `teacher` 角色已合并入 `admin`；以下 `/teacher/program*` 路径保留兼容，实际由 `admin` 权限校验控制访问。

### 6.1 GET `/student/matched-program` — 学生端匹配培养方案
获取匹配学生三元组属性 (`school + major + class_name`) 的已发布人培方案。

* **响应参数** `200 OK` (对应 `CultivationProgramRead` 模式，若无匹配则返回 `null`)

### 6.2 GET `/teacher/program` — 管理端读取编辑中培养方案
获取当前管理员名下正在维护的培养方案。

* **响应参数** `200 OK` (对应 `CultivationProgramRead` 模式，若无配置则返回 `null`)

### 6.3 PUT `/teacher/program` — 保存培养方案 (草案)
保存配置的课程节点矩阵，不发布给学生。

* **请求体** `application/json` (对应 `CultivationProgramSaveRequest` 模式)
  | 字段 | 类型 | 说明 |
  | :--- | :--- | :--- |
  | `school` | str | 学校名称 |
  | `major` | str | 专业名称 |
  | `class_name`| str | 班级名称 |
  | `courses` | list | 课程节点配置数组 |

### 6.4 POST `/teacher/program/publish` — 发布培养方案
发布培养方案，使绑定该学段班级的学生可以正式进行画像和路径规划。

* **请求体** 同上 `PUT /teacher/program` (对应 `CultivationProgramSaveRequest` 模式)。

---

## 7. Admin & Data 学情与用户管理

### 7.1 GET `/admin/accounts` — 获取账户列表
* **响应**：`list[UserRead]` (列出所有管理员与学生账号)

### 7.2 POST `/admin/accounts` — 单账号创建
* **请求体**：`AdminAccountCreateRequest` (含 `username`, `identifier`, `password`, `role`, `school`, `major`, `class_name` 字段)

### 7.3 POST `/admin/accounts/batch` — 批量修改/删除账号
批量调整现有账号的启用状态、角色或者物理删除。

* **请求体** `application/json` (对应 `AdminAccountBatchRequest` 模式)
  | 字段 | 类型 | 必填 | 说明 |
  | :--- | :--- | :--- | :--- |
  | `action` | str | 是 | 执行的批量动作：`activate` (激活) / `deactivate` (停用) / `delete` (删除) / `set_role` (设定角色) |
  | `uids` | list[str]| 是 | 目标账号的用户 UUID 数组 |
  | `role` | str | 否 | 当 `action` 为 `set_role` 时，必填指定的角色类型 |

### 7.4 POST `/admin/accounts/import` — CSV 批量导入账号
* **请求体**：`AdminAccountImportRequest` (传入 `csv_text` 字符串内容)

### 7.5 GET `/admin/accounts/export` — 导出账号 CSV 文件
* **响应**：返回内容类型为 `text/csv` 的导出文件响应。

### 7.6 PUT `/admin/accounts/{uid}` — 更新单账号信息
* **请求体**：`AdminAccountUpdateRequest`

### 7.7 DELETE `/admin/accounts/{uid}` — 删除单账号
* **响应**：`204 No Content`

### 7.8 GET `/admin/data/overview` — 获取全校学情大盘数据
* **响应**：`DataOverviewResponse`（涵盖活跃人数、人培覆盖数、路径规划完结比例等指标）。

### 7.9 GET `/admin/data/cohorts` — 获取全量班级名单
* **响应**：`list[DataCohortRead]`

### 7.10 GET `/admin/data/users/{uid}/learning-data` — 获取学生完整学习行为档案
* **响应**：`UserLearningDataRead` (包含该学生的画像、年级路径、已生成大纲和全部错题测验明细)。

### 7.11 DELETE `/admin/data/users/{uid}/learning-data` — 清空特定学生的学习规划数据
* **响应**：`204 No Content` (清空其画像、路径以及对应课程大纲)

### 7.12 DELETE `/admin/data/cohorts/{school}/{major}/{class_name}/program` — 清除特定班级的培养方案关联
* **响应**：`204 No Content`

---

## 8. Knowledge Base 教材知识库与缺口闭环

以下端点定义在 `backend/app/api/knowledge_base.py`（完整 Schema 见 `frontend/openapi.json`）：

### 8.1 管理端端点（需 `admin` 权限）
* `GET /admin/knowledge-base/sources` / `POST /admin/knowledge-base/sources` — 查询或创建知识来源
* `GET /admin/knowledge-base/textbooks` / `POST /admin/knowledge-base/textbooks` — 列出或写入结构化教材
* `GET /admin/knowledge-base/textbooks/{textbook_id}/sections` — 获取教材切分小节列表
* `PUT /admin/knowledge-base/textbooks/{textbook_id}/outline` — 确认并保存教材大纲
* `POST /admin/knowledge-base/textbooks/{textbook_id}/publish` / `unpublish` — 发布或下架教材
* `DELETE /admin/knowledge-base/textbooks/{textbook_id}` — 删除草稿教材或归档已发布教材
* `POST /admin/knowledge-base/textbooks/{textbook_id}/agent-organize` / `agent-organize/run` — 创建或触发教材后台整理任务
* `POST /admin/knowledge-base/ingestion-jobs/{job_id}/run` / `GET /admin/knowledge-base/ingestion-jobs/{job_id}` — 推进或查询摄取任务状态
* `POST /admin/knowledge-base/agent` / `POST /admin/knowledge-base/agent/stream` — 同步或 SSE 流式运行知识库管理 Agent
* `POST /admin/knowledge-base/source-results/confirm` — 确认检索来源结果并创建摄取任务
* `POST /admin/knowledge-base/uploads` — 上传教材文件（`multipart/form-data`，支持 PDF/DOCX 等格式，限额 100 MiB）
* `GET /admin/knowledge-base/gaps`、`POST /admin/knowledge-base/gaps/{gap_id}/find-materials`、`POST /admin/knowledge-base/gaps/{gap_id}/upload` — 查看并补全学生触发的知识缺口
* `GET /admin/knowledge-base/textbooks/{textbook_id}/extension-resources` / `POST .../extension-resources` — 查询或新增教材小节扩展资源

### 8.2 学生端端点（需 `student` 权限）
* `POST /knowledge-base/gaps/{gap_id}/follow` — 关注知识缺口
* `GET /knowledge-base/notices` — 获取当前学生的知识缺口补全通知列表
* `POST /knowledge-base/notices/{notice_id}/read` — 将指定知识缺口通知标记为已读


## 学生关键流程与提交恢复

- `GET /api/profile/dashboard` 增加 `hasCompleteProfile: boolean`，使用服务端画像完整性判定。学生登录进入首页；画像采集仅由学生主动开始，已有会话可继续。
- `GET /api/leaf/courses/{course_node_id}` 增加 `chapter_progress`，每项包含 `chapter_id`、`state`、`best_score`、可空 `latest_attempt_id`。状态为 `locked / available / passed`。读取课程列表和章节摘要不创建进度；Leaf 与 Forest 使用相同课程访问规则，包括匹配人培课程。
- 测验响应的 `quiz_version` 是完整规范化题目内容（含批改字段）的 SHA256。attempt 的 `quiz_version` 可空；历史记录不推断版本。只有相同版本的历史答案可以回填。
- 普通提交和 SSE 提交请求继续兼容 `{answers}`。新客户端必须成对发送 `client_submission_id`（UUID）和 `quiz_version`（64 位十六进制），与固定答案快照一起持久化。同一用户的同一 UUID 绑定相同测验、版本、答案；不同内容返回 409。已完成的重复提交返回原结果，不重复写入成绩或推进路径。
- `GET /api/forest/quizzes/{quiz_id}/submissions/{client_submission_id}` 仅查询本人提交。200 返回与 SSE `done` 相同的结果对象：`attempt`、`weaknesses`、`canopy_overview`、`next_unlocked_chapter_id`、`next_course_id`；404 表示尚未确认，不等于提交失败。成功结果保存时的成长概览和后续学习信息随原结果返回。
- SSE 保留 `status / done / error` 事件。断网、错误事件或没有 `done` 就结束时，客户端退出提交状态并查询该 UUID。尚未确认时保留快照，允许重新查询或以同一 UUID 原样重试。刷新后只查询，不自动重新提交。课程、章节或版本失效时要求重新进入有效测验。
- 批改在数据库锁之外执行。最终短事务按 User → ChapterQuiz 加锁、重读权限及版本，将 attempt、薄弱点、章节进度、实际年度路径、恢复快照一次提交。仅首次通过且课程仍为当前课程时推进路径；已通过状态和首次通过时间不降级或覆盖。题目生成、路径替换和大纲写入使用同一用户协调锁。

### 学生测验与生成的一致性

题目生成使用生成前的章节内容快照，在 User 协调锁内重新读取章节内容和解锁状态；内容变化时返回 409，未解锁返回 403，不覆盖已有题目。课程大纲生成在同一协调锁内对照生成前后年度课程列表的 ID、主题、目标及顺序，路径替换后不回写旧大纲。批改不持数据库锁，结果落库时再次校验权限和题目版本。
