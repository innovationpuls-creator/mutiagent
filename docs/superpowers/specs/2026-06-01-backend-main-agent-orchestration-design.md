# Backend Main Agent Orchestration Design

Date: 2026-06-01

## Scope

This design upgrades the backend orchestration from the current intent-router-first flow to a main-agent-led flow.

The main Dify Chatflow is `DIFY_CHAT_API_KEY`. The backend calls this main agent first, validates its JSON control output, executes the requested downstream agent graph, then calls the main agent again for the final user-facing summary.

The implementation is allowed to replace the old `/api/orchestration/chatflow/*` paths. The new API must use clearer session paths.

## Existing Context

Current confirmed backend surfaces:

- `backend/app/orchestration/dify_client.py` reads `DIFY_PROFILE_AGENT_API_KEY` and `DIFY_INTENT_RECOGNITION_API_KEY`.
- `backend/.env` already contains `DIFY_API_URL`, `DIFY_PROFILE_AGENT_API_KEY`, `DIFY_INTENT_RECOGNITION_API_KEY`, `DIFY_LEARNING_PATH_AGENT_API_KEY`, and `DIFY_CHAT_API_KEY`.
- `UserProfile` stores `profile_data` and `profile_text`.
- `UserDifyConversation` currently stores `intent_conversation_id` and `profile_conversation_id`.
- Existing profile agent output uses `collecting` and `basic_profile`.
- Existing frontend trace data uses `AgentRunStep` with `stepId`, `kind`, `status`, `title`, `summary`, `agent`, and `durationMs`.

## Agent Roles

### `main_agent`

Environment key: `DIFY_CHAT_API_KEY`

Type: Dify Chatflow

Enabled Dify features: memory and web search

Responsibilities:

- Talk directly with the user.
- Ask follow-up questions before learning path generation.
- Return a backend-control JSON object.
- Request one or more downstream agent calls.
- Explicitly describe dependency and parallel execution relationships.
- Generate final user-facing summaries after downstream agent results return.

### `intent_recognition_agent`

Environment key: `DIFY_INTENT_RECOGNITION_API_KEY`

Responsibilities:

- Assist the main agent with intent recognition when requested.
- Return its result to the backend.
- The backend must return that result to the main agent. The backend must not use intent recognition to replace main-agent decision making.

### `profile_agent`

Environment key: `DIFY_PROFILE_AGENT_API_KEY`

Type: Dify Chatflow

Responsibilities:

- Keep the existing profile collection and profile generation behavior unchanged.
- Continue returning the existing `collecting` / `basic_profile` output structure.
- Once entered, future profile turns bypass the main agent until profile completion.
- On completion, save the profile result to `UserProfile`, then call the main agent with only the complete profile JSON for final summary.

### `learning_path_agent`

Environment key: `DIFY_LEARNING_PATH_AGENT_API_KEY`

Type: Dify Chatflow

Enabled Dify features: memory

Responsibilities:

- Generate a complete structured learning path in a single backend call.
- Receive only `user_profile` and `learning_path_request`.
- Return a JSON object matching the learning path result schema.
- Use its persisted Dify `conversation_id` for future learning path updates.

## Orchestration Flow

1. User sends a message to a new session API.
2. Backend calls `main_agent`.
3. Backend parses and validates the main agent JSON.
4. If the JSON is invalid, missing required fields, or references an invalid agent key, backend returns an error to the frontend.
5. If `control.action` is `reply_only`, backend returns the main agent user-visible response.
6. If `control.action` is `call_agents`, backend validates and executes the declared call graph.
7. Calls run sequentially or in parallel according to `depends_on` and `parallel_group`.
8. After the declared call batch completes, backend sends the downstream results back to `main_agent`.
9. `main_agent` returns the final user-visible response.
10. Backend returns final response, trace, and any saved structured result to the frontend.

## Special Flows

### Profile Flow

When `main_agent` requests `profile_agent`, backend enters profile mode.

While profile mode is active:

- User turns bypass `main_agent`.
- Backend continues the `profile_agent` Dify conversation directly.
- The flow continues until the profile agent returns `type: "basic_profile"` and `stage: "generated"`.
- Backend saves the result to `userprofile.profile_data` and `userprofile.profile_text`.
- Backend calls `main_agent` for final summary with only the complete profile JSON.

### Learning Path Flow

Learning path follow-up questions are handled by `main_agent`.

Backend calls `learning_path_agent` only after `main_agent` sends a call plan for `learning_path_agent`.

Before calling `learning_path_agent`, backend must verify:

- Current user has `UserProfile`.
- `UserProfile.profile_data.type` is `basic_profile`.
- `UserProfile.profile_data.stage` is `generated`.

If this verification fails:

- Backend does not call `learning_path_agent`.
- Backend returns a user-visible prompt that guides the user to complete the profile first.

When verification passes:

- Backend calls `learning_path_agent` once.
- Backend sends `user_profile` and `learning_path_request`.
- Backend validates the learning path JSON.
- Backend saves it to `userlearningpath.path_data`.
- Backend calls `main_agent` for final summary with only the complete learning path JSON.
- Backend returns both the final main-agent response and the full learning path JSON to the frontend.

### Failure Flow

If a downstream agent call fails:

- Backend calls `main_agent` again with the failure information.
- `main_agent` generates a user-facing failure explanation and next-step suggestion.
- If this failure explanation call also fails, backend returns a clear orchestration error.

## Database Design

### `useragentconversation`

Purpose: persist each user-agent Dify conversation ID.

Fields:

| Field | Type | Constraint | Description |
|---|---|---|---|
| `user_uid` | str | PK, FK -> `user.uid` | User ID |
| `agent_key` | str | PK | Agent key |
| `conversation_id` | str | NOT NULL, default `""` | Dify conversation ID |
| `created_at` | datetime | UTC | Created time |
| `updated_at` | datetime | UTC | Updated time |

Allowed `agent_key` values:

- `main_agent`
- `intent_recognition_agent`
- `profile_agent`
- `learning_path_agent`

The old `UserDifyConversation` data does not need migration. Existing users can start new agent conversations.

### `userlearningpath`

Purpose: persist the current user's latest learning path.

Fields:

| Field | Type | Constraint | Description |
|---|---|---|---|
| `user_uid` | str | PK, FK -> `user.uid` | User ID |
| `path_data` | JSON | default `{}` | Complete learning path JSON |
| `created_at` | datetime | UTC | Created time |
| `updated_at` | datetime | UTC | Updated time |

There is no text field. The learning path JSON also does not include `text`. Frontend rendering uses structured fields only.

## API Design

Primary endpoints:

```text
POST /api/orchestration/sessions/start
POST /api/orchestration/sessions/continue
GET  /api/learning-path/me
```

Streaming endpoints are part of the design and are used as the main frontend experience:

```text
POST /api/orchestration/sessions/start/stream
POST /api/orchestration/sessions/continue/stream
```

Non-streaming endpoints remain useful for tests and fallback behavior.

### `POST /api/orchestration/sessions/start`

Request:

```json
{
  "query": "用户输入"
}
```

Response:

```json
{
  "session_id": "后端执行会话 ID",
  "answer": {
    "user_message": "主 agent 最终给用户看的文本",
    "question_box": null
  },
  "agent_trace": [],
  "completed": false,
  "profile": null,
  "learning_path": null
}
```

### `POST /api/orchestration/sessions/continue`

Request:

```json
{
  "session_id": "后端执行会话 ID",
  "query": "用户输入"
}
```

Response shape matches session start.

### `GET /api/learning-path/me`

Response when data exists:

```json
{
  "learning_path": {},
  "updated_at": "ISO datetime"
}
```

When no learning path exists, return 404 with a clear message that the user has not generated a learning path.

## SSE Event Design

Events:

- `agent_step_started`
- `agent_step_completed`
- `agent_step_failed`
- `orchestration_completed`
- `orchestration_failed`

Step event payload:

```json
{
  "step_id": "main_plan_1",
  "agent_key": "main_agent",
  "label": "主 agent 判断",
  "phase": "planning",
  "status": "running",
  "message": "主 agent 正在判断下一步",
  "depends_on": [],
  "parallel_group": "group_1"
}
```

The frontend must render visible trace steps for:

- 主 agent 判断
- 意图识别 agent 执行
- 基础画像 agent 执行
- 学习路径 agent 执行
- 主 agent 总结

Sequential and parallel executions both appear as multi-agent trace steps. Actual backend execution follows the validated dependency graph.

## Main Agent Dify JSON Schema

Use this schema in the Dify main Chatflow configuration for `DIFY_CHAT_API_KEY`.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": ["response", "control"],
  "properties": {
    "response": {
      "type": "object",
      "additionalProperties": false,
      "required": ["user_message", "question_box"],
      "properties": {
        "user_message": {
          "type": "string",
          "minLength": 1
        },
        "question_box": {
          "type": ["object", "null"],
          "additionalProperties": false,
          "required": ["question", "options"],
          "properties": {
            "question": {
              "type": "string"
            },
            "options": {
              "type": "array",
              "items": {
                "type": "string"
              }
            }
          }
        }
      }
    },
    "control": {
      "type": "object",
      "additionalProperties": false,
      "required": ["action", "calls"],
      "properties": {
        "action": {
          "type": "string",
          "enum": ["reply_only", "call_agents", "final_answer"]
        },
        "calls": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "call_id",
              "agent_key",
              "label",
              "depends_on",
              "parallel_group",
              "agent_input"
            ],
            "properties": {
              "call_id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_]*$"
              },
              "agent_key": {
                "type": "string",
                "enum": [
                  "intent_recognition_agent",
                  "profile_agent",
                  "learning_path_agent"
                ]
              },
              "label": {
                "type": "string",
                "minLength": 1
              },
              "depends_on": {
                "type": "array",
                "items": {
                  "type": "string",
                  "pattern": "^[a-z][a-z0-9_]*$"
                }
              },
              "parallel_group": {
                "type": ["string", "null"]
              },
              "agent_input": {
                "type": "object"
              }
            }
          }
        }
      }
    }
  }
}
```

## Main Agent Dify Prompt

Use this prompt in the Dify main Chatflow LLM for `DIFY_CHAT_API_KEY`.

```text
你是应用里的主 agent，负责直接与中文用户对话，并调度后端可调用的专业 agent。

你必须始终只输出一个合法 JSON 对象，不能输出 Markdown，不能输出代码块，不能在 JSON 外输出任何文字。

你的输出分为两部分：
1. response：给用户看的内容。必须像正常对话一样自然、清楚、友好。
2. control：给后端看的控制信息。不能包含长篇推理过程，只能包含可执行控制字段。

你可以使用的 agent_key 只有：
- intent_recognition_agent：用于辅助判断用户意图。调用后，后端会把结果返回给你，由你决定下一步。
- profile_agent：用于收集和生成用户基础画像。进入这个流程后，后端会直接继续基础画像 agent 的多轮对话，直到画像完成。
- learning_path_agent：用于基于已完成的用户画像和你整理的学习路径需求，一次性生成完整学习路径。

决策规则：
- 如果用户只是普通闲聊或简单问答，control.action 使用 reply_only，calls 为空数组。
- 如果信息不足，需要继续向用户追问，control.action 使用 reply_only，calls 为空数组，并在 response 中提出问题。
- 如果需要调用一个或多个 agent，control.action 使用 call_agents，calls 中写清楚调用计划。
- 如果你收到后端传回的最终 agent 结果并需要总结，control.action 使用 final_answer，calls 为空数组。

调用计划规则：
- call_id 必须是小写英文、数字、下划线，且以小写英文开头。
- depends_on 写这个调用依赖的 call_id；没有依赖时写空数组。
- parallel_group 用于标记可并行执行的一组调用；不需要并行时写 null。
- agent_input 必须是你整理后的结构化输入，不要把用户原话粗暴复制进去。
- learning_path_agent 的追问由你完成。只有当学习路径目标、时间、类型、最终效果等信息足够明确时，才调用 learning_path_agent。
- profile_agent 保持原有画像收集逻辑。用户没有完成基础画像时，不要直接调用 learning_path_agent。

失败处理规则：
- 如果后端告诉你某个下游 agent 调用失败，你要生成给用户看的失败解释和下一步建议。
- 失败解释也必须输出同一个 JSON 结构。

输出示例：
{
  "response": {
    "user_message": "我先帮你确认学习目标，然后再生成完整学习路径。你希望这条路径更偏考试、项目实践，还是就业准备？",
    "question_box": {
      "question": "你希望学习目标更偏向哪一类？",
      "options": [
        {
          "label": "考试",
          "value": "考试",
          "description": "以考试、期末、考证或考研为目标",
          "target_fields": ["learning_goal_type"],
          "fills": {
            "learning_goal_type": "考试"
          }
        },
        {
          "label": "项目实践",
          "value": "项目实践",
          "description": "以做出可展示项目为目标",
          "target_fields": ["learning_goal_type"],
          "fills": {
            "learning_goal_type": "项目实践"
          }
        },
        {
          "label": "就业准备",
          "value": "就业准备",
          "description": "以实习、简历、面试和作品集为目标",
          "target_fields": ["learning_goal_type"],
          "fills": {
            "learning_goal_type": "就业准备"
          }
        },
        {
          "label": "能力提升",
          "value": "能力提升",
          "description": "以提升某项技术能力为目标",
          "target_fields": ["learning_goal_type"],
          "fills": {
            "learning_goal_type": "能力提升"
          }
        }
      ]
    }
  },
  "control": {
    "action": "reply_only",
    "calls": []
  }
}
```

## Learning Path Agent Dify Inputs

Backend calls `DIFY_LEARNING_PATH_AGENT_API_KEY` with these exact input keys:

```json
{
  "user_profile": {},
  "learning_path_request": {}
}
```

`user_profile` is the current user's `userprofile.profile_data`.

`learning_path_request` is the main agent's structured `agent_input` for the learning path call.

## Learning Path Agent Dify JSON Schema

Use this schema in the Dify learning path Chatflow configuration.

```json
{
  "type": "object",
  "additionalProperties": false,
  "required": [
    "learning_goal",
    "gap_analysis",
    "foundation_path",
    "generated_path"
  ],
  "properties": {
    "learning_goal": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "target_course_or_skill",
        "target_completion_time",
        "goal_type",
        "desired_outcome"
      ],
      "properties": {
        "target_course_or_skill": {
          "type": "string",
          "minLength": 1
        },
        "target_completion_time": {
          "type": "string",
          "minLength": 1
        },
        "goal_type": {
          "type": "string",
          "enum": [
            "考试",
            "课程学习",
            "项目实践",
            "能力提升",
            "就业准备",
            "其他"
          ]
        },
        "desired_outcome": {
          "type": "string",
          "minLength": 1
        }
      }
    },
    "gap_analysis": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "current_mastered_content",
        "current_weaknesses",
        "required_capabilities",
        "main_gaps"
      ],
      "properties": {
        "current_mastered_content": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "current_weaknesses": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "required_capabilities": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "main_gaps": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        }
      }
    },
    "foundation_path": {
      "type": "object",
      "additionalProperties": false,
      "required": ["stages"],
      "properties": {
        "stages": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "stage_id",
              "stage_name",
              "learning_goal",
              "learning_content",
              "learning_tasks",
              "recommended_methods",
              "completion_standard"
            ],
            "properties": {
              "stage_id": { "type": "string", "minLength": 1 },
              "stage_name": { "type": "string", "minLength": 1 },
              "learning_goal": { "type": "string", "minLength": 1 },
              "learning_content": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1
              },
              "learning_tasks": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1
              },
              "recommended_methods": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1
              },
              "completion_standard": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1
              }
            }
          }
        }
      }
    },
    "generated_path": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "overall_goal",
        "stage_routes",
        "schedule",
        "task_checklist",
        "recommended_resource_types",
        "stage_acceptance_criteria",
        "next_actions"
      ],
      "properties": {
        "overall_goal": { "type": "string", "minLength": 1 },
        "stage_routes": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["stage_id", "route_summary"],
            "properties": {
              "stage_id": { "type": "string", "minLength": 1 },
              "route_summary": { "type": "string", "minLength": 1 }
            }
          }
        },
        "schedule": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["period", "focus", "milestone"],
            "properties": {
              "period": { "type": "string", "minLength": 1 },
              "focus": { "type": "string", "minLength": 1 },
              "milestone": { "type": "string", "minLength": 1 }
            }
          }
        },
        "task_checklist": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "recommended_resource_types": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        },
        "stage_acceptance_criteria": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["stage_id", "criteria"],
            "properties": {
              "stage_id": { "type": "string", "minLength": 1 },
              "criteria": {
                "type": "array",
                "items": { "type": "string" },
                "minItems": 1
              }
            }
          }
        },
        "next_actions": {
          "type": "array",
          "items": { "type": "string" },
          "minItems": 1
        }
      }
    }
  }
}
```

## Learning Path Agent Dify Prompt

Use this prompt in the Dify learning path Chatflow LLM.

```text
你是学习路径生成 agent。你的任务是根据后端传入的用户画像 user_profile 和主 agent 整理后的学习路径需求 learning_path_request，一次性生成完整、结构化、可被前端直接渲染的学习路径 JSON。

你必须始终只输出一个合法 JSON 对象，不能输出 Markdown，不能输出代码块，不能在 JSON 外输出任何文字。

输入说明：
- user_profile：用户基础画像 JSON，来自 userprofile.profile_data。
- learning_path_request：主 agent 整理后的学习路径需求，包含目标、时间、类型、最终效果等信息。

输出要求：
- 顶层必须只包含 learning_goal、gap_analysis、foundation_path、generated_path。
- 不要输出 type、stage、text。
- 所有字段必须使用 JSON Schema 中规定的英文键名。
- 所有面向用户展示的内容值使用中文。
- 不要留空字符串。
- 不要输出“待补充”“未知”“暂无”等占位内容。如果输入信息不足，根据 user_profile 和 learning_path_request 做保守、明确的规划。
- 学习路径要覆盖大学一到四年的学习内容、时间节点，以及对应相关数据。
- 阶段划分要能被前端渲染为清晰路线。
- 推荐资源只描述资源类型，不要输出具体外链，除非输入中明确要求具体链接。

你必须完整覆盖以下内容：

第二步：明确学习目标
- 目标课程或目标技能
- 目标完成时间
- 学习目标类型：考试、课程学习、项目实践、能力提升、就业准备、其他
- 用户希望达到的最终效果

第三步：分析当前差距
- 当前已掌握内容
- 当前薄弱环节
- 目标所需能力
- 从当前状态到目标状态的主要差距

第四步：规划基础学习路径
- 阶段划分
- 每个阶段的学习目标
- 每个阶段的学习内容
- 每个阶段的学习任务
- 每个阶段的推荐学习方式
- 每个阶段的完成标准

第五步：生成学习路径
- 学习路径总目标
- 阶段学习路线
- 周期安排
- 学习任务清单
- 推荐学习资源类型
- 阶段验收标准
- 下一步行动建议
```

## Backend Module Design

Backend modules:

```text
backend/app/orchestration/
  dify_client.py
  state.py
  graph.py
  agent_plan.py
  agent_executor.py
  response_parser.py

backend/app/services/
  agent_conversation_service.py
  learning_path_service.py
  profile_service.py

backend/app/api/
  orchestration.py
  learning_path.py
```

Responsibilities:

- `agent_plan.py`: Pydantic models for the main agent control JSON. Validate `action`, `calls`, `depends_on`, `parallel_group`, and allowed `agent_key`.
- `agent_executor.py`: Execute `intent_recognition_agent`, `profile_agent`, and `learning_path_agent` according to the validated call graph.
- `response_parser.py`: Parse Dify `answer` JSON. Invalid JSON produces a clear backend error.
- `agent_conversation_service.py`: Read and write `useragentconversation` rows by `user_uid` and `agent_key`.
- `learning_path_service.py`: Save and read `userlearningpath.path_data`.
- `graph.py`: Keep LangGraph state transitions clear and avoid embedding heavy business logic.
- `orchestration.py`: Expose session APIs and streaming APIs.
- `learning_path.py`: Expose `GET /api/learning-path/me`.

## Frontend Design

Frontend changes:

- Switch API client calls to `/api/orchestration/sessions/*`.
- Use streaming endpoints when available.
- Extend message types to represent:
  - main agent response
  - profile message
  - learning path result
- Reuse `AgentRunTimeline` for multi-agent traces.
- Add a learning path renderer, such as `LearningPathCard`.

`LearningPathCard` renders four sections:

- 明确学习目标
- 分析当前差距
- 规划基础学习路径
- 生成学习路径

## Testing Design

Backend tests:

- Main agent valid JSON parses into an executable plan.
- Missing fields or invalid `agent_key` returns a clear error.
- `profile_agent` completion saves `UserProfile` and then calls `main_agent` for summary.
- `learning_path_agent` cannot run without completed `UserProfile`.
- Valid learning path JSON saves to `userlearningpath.path_data`.
- `GET /api/learning-path/me` returns 200 with data and 404 without data.
- `useragentconversation` saves `conversation_id` by `user_uid + agent_key`.
- SSE events show `主 agent 判断 -> 下游 agent 执行 -> 主 agent 总结`.

Frontend tests:

- Streaming events update the agent timeline.
- Learning path JSON renders all four sections.
- Profile collection still renders the existing `ChatCard`.
- API errors show failed message state.
- Refresh can continue main-agent context through persisted Dify conversation IDs.

## Out Of Scope

- Migrating old `UserDifyConversation` rows.
- Rewriting the profile agent prompt.
- Adding concrete external resource links to learning path output.
- Implementing code in this design step.

## Self Review

- Placeholder scan: no placeholders remain.
- Internal consistency: agent keys, API paths, database table names, and Dify input keys are defined consistently.
- Scope check: this is one backend-led orchestration upgrade with required frontend integration.
- Ambiguity check: all user-confirmed choices are written as fixed design rules.
