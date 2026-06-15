# 教师端课程管理与学生端分支展示设计规范

日期：2026-06-15

## 1. 目标 (Goals)

本设计旨在定义并实现教师端人培方案上传与编辑工作流，以及学生端 Branch（分支路网）界面中必修“主干”与自主生成“分支”课程的融合展示。

本设计仅聚焦于**前端界面与路由架构**，不涉及后端逻辑与数据库持久化的具体实现。设计秉承 **Headspace meditation 风格（Warm Humanist）**：大圆角、温和淡雅的 OKLCH 色彩体系、有呼吸感的加载微动效以及极简低密度的几何指示符。

---

## 2. 路由设计 (Routing)

路由体系基于项目既有 `react-router-dom` 结构进行配置与拓展，不增加冗余路由层级：

- **教师端路由**：
  - `/teacher`：对应教师工作台。重构现有 `TeacherPage.tsx`，以单页内嵌状态机（Empty ➔ Loading ➔ Editor）的形式承载上传与大纲编辑，保持无跳页的沉浸式操作流。
- **学生端路由**：
  - `/branch`：对应学生课程路径大图。在现有 `BranchPage.tsx` 中嵌入藤蔓侧蔓（Tendrils）动态挂接逻辑，完成个性化课程与主干课程的拓扑融合。

---

## 3. 数据模型与契约 (Data Models & Types)

在 `frontend/src/types/branch.ts` 中新增以下字段，用于在前端支撑多模态生成、树表编辑以及学生端的分叉连线逻辑：

```typescript
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

## 4. 教师端页面与组件设计 (Teacher Interface)

`/teacher` 页面采用单页多态交互结构（Single-Page State Machine），包含以下核心组件：

### 4.1 核心状态切换
- **空状态 (Empty State)**: 
  - 渲染 `UploadZone` 组件。一个柔和的暖色虚线区域（`border: 2px dashed var(--color-border)`），支持 PDF、Word、图片等课程文档拖拽上传。
- **生成中状态 (Loading State)**:
  - 渲染 `BreathingLoader` 组件。屏幕中央呈现一个大半径的渐变呼吸加载环，配合 LXGW WenKai 字体显示温和的加载文案，淡化教师等待的焦虑感。
- **编辑中状态 (Editor State)**:
  - 渲染 `TreeTable` 与 `DetailDrawer` 组件。顶部收缩为小巧的重传区，下方展宽为主工作区。

### 4.2 核心组件规格
- **`TreeTable` (左侧树表)**:
  - 按照大一至大四（第 1 至第 8 学期）折叠分组。
  - 行项目仅显示核心概要：`课程名称`、`学期/学分`、`课程性质`（必修/选修）。
  - 双击或单击行高亮，并在右侧激活抽屉。
- **`DetailDrawer` (右侧详情抽屉)**:
  - 采用滑动动效（`framer-motion` 自右向流平滑推出，缓动曲线：`[0.25, 1, 0.5, 1]`，时常 `420ms`）。
  - 内嵌富文本/Markdown 编辑区，可调整 `course_goal`、`key_points`、`difficult_points` 与 `acceptance_criteria`。
  - 底部提供“保存并发布”按钮，触发全局状态提交。

---

## 5. 学生端 Branch 页面改造设计 (Student Branch Integration)

改造 `/branch` 中的藤蔓生成与卡片渲染逻辑，支持“主干必修”与“侧枝自主”课程的融合展示。

### 5.1 视觉渲染规则
- **主干节点 (Trunk Node)**:
  - 数据中 `is_custom === false` 或缺省的课程。
  - 渲染于主藤蔓（Main Vine Stem）正上方。卡片背景采用实色填充（温深鸭蓝 `--color-secondary`），传达其稳定性与不可或缺的基础性。
- **侧枝节点 (Tendril Node)**:
  - 数据中 `is_custom === true` 的课程。
  - 渲染于派生出的侧蔓（Tendrils）末梢。卡片背景采用虚线外框（淡珊瑚色或鼠尾草绿），并包含一个微发光的呼吸光效粒子，表现其动态与自主性。

### 5.2 连线与解锁逻辑
- **贝塞尔高光连线 (Bezier Highlighting)**:
  - 点击任何卡片时，使用 SVG 曲线连接当前节点与其 `prerequisite_ids`（前置课程）及 `parent_preset_id`（父代课程），高亮前因后果。
- **状态联动**:
  - 自主生成课程的解锁状态（`status: 'locked' | 'available'`）随其关联的父代必修课程自动计算（父节点 `status === 'completed'` 时，子节点解锁为 `available`）。

---

## 6. 视觉设计系统与规范对齐 (Design Tokens)

- **字体**: 全系统强制使用 `LXGW WenKai`（霞鹜文楷）。
- **颜色 (OKLCH)**:
  - 必修卡片：温深鸭蓝 `oklch(49% 0.05 235)`
  - 自主生成卡片：暖珊瑚浅背景 `oklch(91% 0.05 55)`，描边 `oklch(76% 0.12 55)`
  - 全局背景：暖奶油纸面 `oklch(94% 0.04 73)`
- **阴影**:
  - 统一采用多层暖调叠加：`box-shadow: 0 8px 24px rgba(244, 165, 115, 0.2)`，禁止冷灰硬边界单层阴影。
- **动效**:
  - 所有过渡只针对 `transform` 和 `opacity` 进行渐变（使用 framer-motion），时长控制在 `300ms - 600ms` 之间。
  - 必须包含 `@media (prefers-reduced-motion)` 适配降级，保证可访问性。
