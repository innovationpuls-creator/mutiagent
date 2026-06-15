# 繁枝课程来源标签设计

日期：2026-06-15

## 背景

教师端已有本地人培方案流程：`frontend/src/pages/teacher/TeacherPage.tsx` 使用 `teacher_cultivation_program` 保存整理后的课程。学生端繁枝页 `frontend/src/pages/branch/BranchPage.tsx` 会读取同名本地数据，并把课程并入对应年级。

现有字段与视觉规则：

- `BranchCourseNode.is_custom` 表示课程来自人培方案。
- `BranchCourseNode.parent_preset_id` 和 `BranchCourseNode.prerequisite_ids` 用于聚焦课程时渲染关系高亮线。
- `is_custom` 为 `true` 时，繁枝课程卡已有 `branch-blob-card-custom`、`branch-custom-glow-dot` 和珊瑚色关系高亮线。

当前问题是来源只靠视觉样式暗示，没有直接文字说明。用户希望保留当前设计，只增加“人培课程 / 自选课程”的文字区分。

## 目标

在繁枝课程卡内增加来源标签，让每张课程都明确展示来源：

- `is_custom === true`：显示「人培课程」
- 其他课程：显示「自选课程」

## 非目标

- 不改变教师端 `teacher_cultivation_program` 的保存逻辑。
- 不新增服务端教师口令、学生绑定、发布 API 或数据库表。
- 不改变课程合并策略。
- 不新增顶部图例、筛选器或分组视图。
- 不改变课程状态语义，`completed`、`current`、`locked` 保持不变。

## 交互与视觉设计

标签放在课程卡文本区内，优先靠近课程名：

- 普通卡：在课程名上方或状态文案附近显示「自选课程」。
- 人培卡：同一位置显示「人培课程」。

视觉规则：

- 标签使用 `--text-caption` 或 `--text-overline` 级别，避免抢过课程名。
- 标签圆角使用 `--radius-full`。
- 标签内边距使用 `--space-*` token。
- 颜色使用 OKLCH 或现有 `--color-*` token。
- 人培标签可使用当前人培卡已有的暖珊瑚语义，例如 `--color-primary-soft`、`--color-primary`。
- 自选标签使用更安静的辅助语义，例如 `--color-secondary-soft`、`--color-secondary` 或现有低对比文字 token。
- 不新增动画；现有 hover、focus、卡片状态动效保持。

## 组件边界

主要变更点：

- `frontend/src/pages/branch/BranchPage.tsx`
  - 新增一个小的来源文案解析函数，例如根据 `course.is_custom` 返回「人培课程」或「自选课程」。
  - 在左、中、右三处课程卡渲染中加入同一来源标签结构。

- `frontend/src/pages/branch/branch.css`
  - 增加来源标签样式。
  - 使用项目设计 token；不写 HEX/RGB；不写任意间距值。

可选整理：

- 如果三处课程卡重复标签结构，可以添加局部小组件，名称需清楚表达用途，并保持文件内小范围变更。

## 数据流

不新增字段。继续使用现有 `BranchCourseNode.is_custom`：

```ts
course.is_custom ? '人培课程' : '自选课程'
```

后端返回的课程未设置 `is_custom` 时，前端按「自选课程」显示。教师本地方案并入的课程如果设置 `is_custom: true`，前端按「人培课程」显示。

## 可访问性

- 标签作为可见文本参与课程卡可读信息。
- 不依赖颜色单独表达来源。
- 课程按钮现有 `aria-label` 可以保持不变；若测试或读屏体验需要增强，可把来源加入 `railAriaLabel`，但本次实现以视觉文本为主。

## 测试

更新前端测试，覆盖：

- 后端普通课程卡显示「自选课程」。
- `is_custom: true` 的人培课程卡显示「人培课程」。
- 现有 `is_custom` 课程的卡片样式和关系高亮测试不被破坏。

建议测试文件：

- `frontend/src/pages/branch/BranchPage.test.tsx`

## 验收标准

- 繁枝页同时存在普通课程和人培课程时，用户能直接看到「自选课程」与「人培课程」。
- 人培课程现有虚线边框、小亮点、关系高亮线仍然存在。
- 没有新增后端接口、数据库迁移或教师端发布逻辑。
- 前端测试通过。
