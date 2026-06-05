# Branch 学习界面设计

日期：2026-06-05

## 目标

在现有 branch 页面中实现“学习路径总览 → 课程 markmap → 章节占位内容”的学习界面。页面只展示已有结构化学习内容，不展示真实文档、视频、动画，也不预留这些能力入口。

## 已确认事实

- branch 当前前端入口是 `frontend/src/pages/branch/BranchPage.tsx`，现在只渲染静态年级 tab 与四个静态 view。
- 学习路径读取接口是 `GET /api/learning-path/me`，后端响应模型是 `YearLearningPathsReadResponse`，字段为 `year_learning_paths` 与 `updated_at`。
- 学习路径真实结构来自 `backend/app/orchestration/agents/models.py` 的 `LearningPathResultOutput`，核心字段为 `grade_plans`、`course_nodes`、`current_learning_course`。
- 当前后端只支持单个 `current_learning_course`。`find_current_course`、`advance_current_learning_course`、profile dashboard 与 chat session 装载逻辑都围绕单个当前课程。
- 用户基础信息中的当前年级来源是 `profile.confirmed_info.current_grade`，前端 dashboard 映射为 `profile.currentGrade`。
- 课程大纲真实结构来自 `CourseKnowledgeOutput` 与前端 `CourseKnowledgeResult`：`course_id`、`course_name`、`grade_year`、`personalization_summary`、`sections`、`learning_sequence`、`total_estimated_hours`。
- markmap 主数据源固定为课程大纲 `sections` / `key_knowledge_points`。
- `UserCourseKnowledgeOutline` 已按 `course_id` 存储课程大纲，但当前没有公开的按 `course_id` 读取大纲 HTTP API。

## 后端契约

### 学习路径 JSON schema

继续沿用 `schema_version: "learning_path.v2.course_node"`，做向后兼容的加法变更。

`CourseNodeOutput` 新增字段：

```python
progress_state: Literal["not_started", "in_progress", "paused", "completed"]
```

`LearningPathResultOutput` 新增字段：

```python
current_learning_courses: list[CurrentLearningCourse]
```

`current_learning_course` 暂时保留为兼容字段。新逻辑以 `current_learning_courses` 和每个课程节点的 `progress_state` 为准。兼容规则：

- 新生成的学习路径必须同时包含 `current_learning_courses` 与 `current_learning_course`。
- `current_learning_courses` 可以包含多个 `CurrentLearningCourse`。
- `current_learning_course` 写入 `current_learning_courses[0]`。
- 读取旧数据时，如果只有 `current_learning_course`，后端将其归一化为长度为 1 的 `current_learning_courses`。
- 每个 `current_learning_courses[].course_node_id` 必须能在对应 `grade_plans[grade_id].course_nodes` 中找到。
- 每个 `current_learning_courses[]` 对应的课程节点 `progress_state` 必须是 `in_progress`。

课程节点三态来自后端真值：

- `completed`：已完成课程，可点击。
- `in_progress`：当前正在学习课程，可点击。
- `not_started`：未开始课程，不可点击。
- `paused`：保留既有进度字面量，界面按不可进入的低强调状态处理，除非后续业务另行定义。

### LLM 提示词

修改 `LEARNING_PATH_AGENT_SYSTEM_PROMPT`：

- 要求每个 `grade_plan.course_nodes[]` 完整输出 `progress_state`。
- 要求输出 `current_learning_courses`。
- 允许业务上存在多个正在学习课程。
- 要求 `current_learning_courses` 中每一项必须来自 `course_nodes`。
- 要求所有当前课程对应节点的 `progress_state` 为 `in_progress`。
- 要求已完成课程输出 `completed`，未开始课程输出 `not_started`。
- 保留 `current_learning_course`，其值必须与 `current_learning_courses[0]` 一致。

### Service 逻辑

在 `backend/app/services/learning_path_service.py` 中补齐：

- 读取学习路径时归一化旧数据，提供 `current_learning_courses`。
- 新增多当前课程读取函数，返回 `list[dict]`。
- 保留 `find_current_course(path_data)`，继续返回第一个当前课程对应的课程节点，供现有 dashboard/chat 兼容使用。
- 新增按 `current_learning_courses` 查找多个课程节点的逻辑。
- `advance_current_learning_course` 更新课程节点自己的 `progress_state`，并同步 `current_learning_courses` 与兼容字段 `current_learning_course`。

### Course Knowledge API

新增公开读取接口：

```http
GET /api/course-knowledge/{course_id}
```

行为：

- 只读取当前登录用户的 `UserCourseKnowledgeOutline`。
- 找不到对应 `course_id` 时返回 404。
- 成功时返回 `outline_data` 原结构，也就是前端现有 `CourseKnowledgeResult`。
- 不触发课程大纲生成。

## 前端数据流

branch 页面加载时并行读取：

- `fetchProfileDashboard(token)` 获取 `profile.currentGrade`。
- `getMyLearningPath(token)` 获取 `yearLearningPaths`。

默认年级：

- 使用 `profile.currentGrade` 映射到 `year_1`、`year_2`、`year_3`、`year_4`。
- 页面只展示当前 active 年级的 `grade_plans[activeGradeId].course_nodes`。
- 用户切换年级 tab 后，仅切换该年级路径图。

点击课程：

- `progress_state === "completed"` 可点击。
- `progress_state === "in_progress"` 可点击。
- `progress_state === "not_started"` 不可点击。
- `progress_state === "paused"` 不可点击。
- 点击可进入课程后，调用 `GET /api/course-knowledge/{course_id}` 读取课程大纲。
- 课程大纲不存在时，停留在课程内容状态并显示“当前课程大纲尚未生成”的占位，不伪造章节。

## Branch UI 状态

### 路径总览状态

- 显示年级 tab。
- 显示当前年级学习路径图。
- 当前课程用 `in_progress` 节点高亮，并显示现有风格一致的状态标签“正在学习”。
- 已完成课程弱化显示但保持可点击，状态标签为“已完成”。
- 未开始课程低强调显示，并通过禁用样式与 `disabled` 交互表达不可点击，状态标签为“未开始”。
- 默认状态不显示“返回路径总览”按钮。

### 课程内容状态

- 年级 tab 淡出。
- 路径图淡出。
- 左侧课程 markmap 淡入。
- 右侧章节占位内容区出现。
- 进入课程内容状态后才显示“返回路径总览”按钮。
- 右侧默认不选中章节，只显示选择提示。

### Markmap

层级固定为：

```text
课程 → 章节 → 知识点
```

映射：

- 课程：`course_name`
- 章节：`sections[]`
- 知识点：每个 section 的 `key_knowledge_points[]`

章节点击：

- 点击 section 节点后，右侧显示该章节占位内容。
- 占位内容只显示章节标题、简短说明与“内容尚未展开”的空状态，不展示真实文档、视频、动画或 AI 生成内容。

折叠：

- markmap 左上角显示折叠按钮。
- 折叠后左侧只保留展开按钮和当前课程名称。
- 折叠后右侧内容区域扩大。
- 展开后左侧 markmap 恢复，markmap 内容淡入。

## 视觉与动效

遵守项目设计系统：

- 颜色只使用 OKLCH token 或现有 `--color-*` 变量。
- 字体使用 LXGW WenKai。
- 间距使用 `--space-*`。
- 阴影使用 `--shadow-sm/md/lg`。
- 动效只改变 `transform` 和 `opacity`。
- 所有动效提供 `prefers-reduced-motion` 降级。

动效：

- 当前年级路径图进入时淡入。
- 切换年级 tab 时旧路径图淡出，新路径图淡入。
- 点击课程进入时，tab 与路径图淡出，markmap 从左侧淡入。
- 折叠 markmap 时使用 Framer Motion `layout` 做 FLIP 过渡；CSS 不写 `width`、`height`、`grid-template-columns` 的 transition。
- 展开 markmap 时左侧内容通过 `transform` 与 `opacity` 淡入。

## 测试

后端：

- `LearningPathResultOutput` 接受 `progress_state` 与 `current_learning_courses`。
- 缺少 `current_learning_courses` 的旧数据可以归一化读取。
- `current_learning_courses` 中不存在于 `course_nodes` 的课程会被拒绝。
- 多个 `in_progress` 课程可以通过 schema 与 service。
- `GET /api/course-knowledge/{course_id}` 返回当前用户对应大纲。
- `GET /api/course-knowledge/{course_id}` 对不存在的大纲返回 404。

前端：

- branch 默认按 `profile.currentGrade` 定位年级。
- 年级 tab 切换后只展示对应年级路径图。
- `completed` 与 `in_progress` 节点可点击。
- `not_started` 与 `paused` 节点不可点击。
- 点击可进入课程后读取对应 `course_id` 的课程大纲。
- 课程内容状态默认不选中章节。
- 点击章节后右侧切换为该章节占位。
- 折叠 markmap 后左侧保留展开按钮和课程名称。
- 默认路径总览状态不显示“返回路径总览”。

## 实施边界

本轮不实现：

- 文档生成入口。
- 视频生成入口。
- 动画生成入口。
- 伪造真实学习材料。
- 后续资源 Agent 的界面预留。
