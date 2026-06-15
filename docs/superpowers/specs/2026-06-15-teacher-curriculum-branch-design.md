# 教师端课程管理与学生端分支展示设计规范

日期：2026-06-15

## 1. 目标 (Goals)

本设计旨在定义并实现教师端人培方案上传与编辑工作流，以及学生端 Branch（分支路网）界面中必修“主干”与自主生成“分支”课程的融合展示。

本设计仅聚焦于**前端界面与路由架构**，不涉及后端逻辑与数据库持久化的具体实现。设计秉承 **Headspace meditation 风格（Warm Humanist）**：大圆角、温和淡雅的 OKLCH 色彩体系、有呼吸感的加载微动效以及极简低密度的几何指示符。

---

## 2. 路由设计 (Routing)

路由体系基于项目既有 `react-router-dom` 结构进行配置与拓展，不增加冗余路由层级：

- **教师端路由**：
  - `/teacher`：对应教师工作台。重构现有 `TeacherPage.tsx`，以单页内嵌状态机（Empty ➔ Loading ➔ Editor ➔ Error）的形式承载上传与大纲编辑，保持无跳页的沉浸式操作流。
- **学生端路由**：
  - `/branch`：对应学生课程路径大图。在现有 `BranchPage.tsx` 中嵌入藤蔓侧蔓（Tendrils）动态挂接逻辑，完成个性化课程与主干课程的拓扑融合。

---

## 3. 数据模型与契约 (Data Models & Types)

在 `frontend/src/types/branch.ts` 中新增以下字段，用于在前端支撑多模态生成、树表编辑以及学生端的分叉连线逻辑：

```typescript
// 状态契约严格保持对齐原系统，仅限：已完成、当前焦点、锁定未开放三种状态
export type BranchCourseStatus = 'completed' | 'current' | 'locked';

export interface BranchCourseNode {
  course_node_id: string;          // 课程/节点唯一标识
  course_or_chapter_theme: string; // 课程名称
  course_goal: string;             // 课程目标 (Markdown 长文本)
  status: BranchCourseStatus;      // 学习状态
  has_outline: boolean;            // 是否已生成大纲
  
  // 新增拓展属性，用于支撑双端联动与生成大纲所需字段：
  is_custom?: boolean;             // 是否为学生自主生成的个性化课程 (false 代表教师人培)
  parent_preset_id?: string;       // 如果是自主生成课程，指向所关联的人培必修课程ID
  prerequisite_ids?: string[];     // 前置课程节点 ID 列表，用于藤蔓树拓扑连线
  
  // 时间安排与学习节奏
  time_arrangement?: {
    semester_scope: string;        // 开课学期范围 (如 "1", "1-2")
    duration: string;              // 学时或学分 (如 "64学时/4学分")
    pace_reason?: string;          // 开课节奏/顺序说明
  };
  
  // 大纲及章节生成的种子上下文
  key_points?: string[];           // 核心知识要点列表
  difficult_points?: string[];     // 学习难点列表
  acceptance_criteria?: string[];  // 验收与考核标准列表
}
```

---

## 4. API 归一化层设计 (API Normalization Layer)

为确保前端接口层能够保留并传递新增的元数据属性，需要重构 `frontend/src/api/branch.ts` 中的 `normalizeCourse` 归一化函数：

```typescript
function normalizeCourse(value: unknown): BranchCourseNode {
  if (!isRecord(value)) {
    throw new Error('繁枝数据格式不正确');
  }
  const courseId = value.course_node_id;
  const theme = value.course_or_chapter_theme;
  const goal = value.course_goal;
  const status = value.status;
  const hasOutline = value.has_outline;
  if (
    typeof courseId !== 'string'
    || typeof theme !== 'string'
    || typeof goal !== 'string'
    || !isStatus(status)
    || typeof hasOutline !== 'boolean'
  ) {
    throw new Error('繁枝数据格式不正确');
  }
  
  // 1. 抽取基础拓展标识
  const isCustom = typeof value.is_custom === 'boolean' ? value.is_custom : undefined;
  const parentPresetId = typeof value.parent_preset_id === 'string' ? value.parent_preset_id : undefined;
  const prerequisiteIds = Array.isArray(value.prerequisite_ids) && value.prerequisite_ids.every((id) => typeof id === 'string')
    ? (value.prerequisite_ids as string[])
    : undefined;
    
  // 2. 抽取时间编排对象
  let timeArrangement: BranchCourseNode['time_arrangement'] = undefined;
  if (isRecord(value.time_arrangement)) {
    const sem = value.time_arrangement.semester_scope;
    const dur = value.time_arrangement.duration;
    const pace = value.time_arrangement.pace_reason;
    if (typeof sem === 'string' && typeof dur === 'string') {
      timeArrangement = {
        semester_scope: sem,
        duration: dur,
        pace_reason: typeof pace === 'string' ? pace : undefined,
      };
    }
  }
  
  // 3. 抽取重难点与考核标准列表
  const keyPoints = Array.isArray(value.key_points) && value.key_points.every((kp) => typeof kp === 'string')
    ? (value.key_points as string[])
    : undefined;
  const difficultPoints = Array.isArray(value.difficult_points) && value.difficult_points.every((dp) => typeof dp === 'string')
    ? (value.difficult_points as string[])
    : undefined;
  const acceptanceCriteria = Array.isArray(value.acceptance_criteria) && value.acceptance_criteria.every((ac) => typeof ac === 'string')
    ? (value.acceptance_criteria as string[])
    : undefined;

  return {
    course_node_id: courseId,
    course_or_chapter_theme: theme,
    course_goal: goal,
    status,
    has_outline: hasOutline,
    is_custom: isCustom,
    parent_preset_id: parentPresetId,
    prerequisite_ids: prerequisiteIds,
    time_arrangement: timeArrangement,
    key_points: keyPoints,
    difficult_points: difficultPoints,
    acceptance_criteria: acceptanceCriteria,
  };
}
```

---

## 5. 教师端页面与交互闭环 (Teacher Panel Lifecycle)

教师端 `/teacher`（`TeacherPage.tsx`）将实现为具有清晰输入校验、保存副作用和重传流的闭环状态机。

### 5.1 页面本地状态机
```typescript
type TeacherPageState = 'empty' | 'loading' | 'editor' | 'error';
```

- **状态 1: `empty`（空白上传态）**
  - 渲染 `UploadZone`，监听 dragover、dragleave 和 drop 事件。
  - **文件类型校验**：仅接收 `.pdf`, `.docx`, `.doc`, `.txt`, `.png`, `.jpg`, `.jpeg`。
  - **大小校验**：最大限制 `20MB`。
  - 校验失败 ➔ 记录错误信息，转至 `error`。
  - 校验成功 ➔ 触发 3 秒模拟 LLM 识别的定时器，转至 `loading`。
- **状态 2: `loading`（渐变呼吸加载态）**
  - 渲染 `BreathingLoader`。中心展示脉动扩展的渐变光晕，并显示温和引导文案。
  - 计时器到期后，装载模拟数据并切换至 `editor`。
- **状态 3: `editor`（左表右单编辑态）**
  - **模拟数据载入**：自动渲染一套包含 8 门必修课（大一到大四，每学期 1-2 门）的树状大纲。
  - **交互逻辑**：
    - 点击左侧课程 ➔ 打开右侧抽屉 `DetailDrawer`。抽屉自右向左平滑推出，过渡时长 `420ms`，采用弹性物理曲线。
    - 在抽屉中编辑课程元数据 ➔ 更新本地 React `courses` 数组状态。
    - 点击顶部“重新导入” ➔ 确认弹窗 ➔ 清空数据并退回 `empty`。
  - **保存行为**：
    - 点击“保存并发布”按钮 ➔ 将当前 `courses` 数据序列化写入 `localStorage.setItem('teacher_cultivation_program', ...)`。
    - 弹出顶部轻量成功 Toast，并在 1.5 秒后淡出。
- **状态 4: `error`（错误反馈态）**
  - 展示大圆角暖红色警告框，提供明确的错误原因（如“文件格式不支持”或“文件超出 20MB”）。
  - 提供“重新上传”按钮，点击退回 `empty` 状态。

---

## 6. 学生端 Branch 页面改造设计 (Student Branch Integration)

改造 `/branch` 中的藤蔓生成与卡片渲染逻辑，打通教师发布的数据与学生自主路径：

### 6.1 数据桥接与融合
学生端 `BranchPage.tsx` 加载时，将优先尝试读取 `localStorage.getItem('teacher_cultivation_program')` 中的教师人培数据：
- 如果存在，则将其与 API 返回的 `BranchOverview` 数据合并。
- 归一化映射关系：
  - 教师人培课程（`is_custom: false`）渲染在贝塞尔主藤蔓（Main Vine Stem）上的关键节点槽位。
  - 学生在此基础上自主生成的定制课程（`is_custom: true`），则渲染在自对应主节点向外延伸的侧蔓（Tendrils）上。

### 6.2 贝塞尔高光连线 (Bezier Highlighting)
- 点击任何卡片时，使用 SVG 曲线连接当前节点与其 `prerequisite_ids`（前置课程）及 `parent_preset_id`（父代课程），高亮前因后果。
- 侧枝节点的解锁状态（`status: 'locked' | 'current' | 'completed'`）随其关联的父代必修课程自动计算（父节点 `status === 'completed'` 时，子节点解锁为 `current` 或 `completed`）。

---

## 7. 视觉设计系统与规范对齐 (Design Tokens)

严格遵循 `docs/01-颜色系统.md` 和 `docs/04-圆角与阴影.md` 的规范：

- **字体**: 全系统强制使用 `LXGW WenKai`（霞鹜文楷），无 Bold 字重，使用 Medium / Regular。
- **颜色 (OKLCH)**:
  - 必修卡片：温深鸭蓝 `oklch(49% 0.05 235)`
  - 自主生成卡片：暖珊瑚浅背景 `oklch(91% 0.05 55)`，描边 `oklch(76% 0.12 55)`
  - 全局背景：暖奶油纸面 `oklch(94% 0.04 73)`
- **阴影 (Shadows)**:
  - 统一采用多层暖调叠加，严禁 hardcode 任何 rgba 阴影：
    - 静止卡片：`var(--shadow-sm)`
    - Hover 悬浮卡片/侧滑抽屉：`var(--shadow-md)`
    - 模态框/全局浮层：`var(--shadow-lg)`
- **动效 (Motion)**:
  - 抽屉推出采用：`transition: transform 420ms var(--ease-lazy)`（`var(--ease-lazy)` 对应贝塞尔 `[0.25, 1, 0.5, 1]` 弹性阻尼曲线）。
  - 必须包含 `@media (prefers-reduced-motion)` 适配降级，降级时转场时长统一降为 `120ms`，仅使用 opacity 渐变。

---

## 8. 测试策略 (Testing Strategy)

为了保障代码质量与修改的鲁棒性，我们需要补充并执行以下三个维度的测试：

### 8.1 API 归一化层单体测试 (`branch.test.ts`)
- 编写测试用例验证 `normalizeCourse`：
  - 输入仅包含基础属性的扁平对象，验证能输出正确的默认值。
  - 输入包含 `is_custom`、`prerequisite_ids`、`time_arrangement` 完整元数据的对象，验证所有可选字段完整保留。
  - 输入错误格式的对象（例如 `status` 字段非 `'completed' | 'current' | 'locked'`），验证能够准确抛出 `"繁枝数据格式不正确"` 异常。

### 8.2 教师端页面状态机与交互测试 (`TeacherPage.test.tsx`)
- 验证初始化渲染为 `empty` 状态，并且拖拽区域（Dropzone）可交互。
- 模拟拖入不合规的二进制大文件（或非支持后缀），验证状态流转为 `error` 状态且错误文案正确展示。
- 模拟拖入合规的文本文件，验证状态流转为 `loading` 状态且呼吸动效挂载。
- 验证在 `editor` 状态下：
  - 点击左侧课程行，右侧 `DetailDrawer` 组件被挂载且数据项对齐。
  - 在右侧修改“课程目标”后，左侧对应的本地状态正确保存。
  - 点击“保存并发布”后，`localStorage` 被更新，且弹出成功 Toast。

### 8.3 学生端 Branch 路径与自定义卡片渲染测试 (`BranchPage.test.tsx`)
- 验证当 `localStorage` 含有发布的人培数据时，合并算法运行无误。
- 验证卡片列表根据 `is_custom` 属性挂载为不同的 ClassName 与视觉效果（`is_custom` 卡片包含虚线外框修饰）。
- 验证点击含有前置依赖的节点时，贝塞尔连线组件被渲染在 SVG 画布中。
