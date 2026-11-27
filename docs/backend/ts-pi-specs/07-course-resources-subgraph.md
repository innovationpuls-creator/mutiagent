# M7 开发文档：小节多模态教学资源生成子图（Markdown + 视频 + HTML 动画 + 拼装）

> 文档日期：2026-11-27  
> 对应里程碑：M7（前置依赖：M6）  
> 上位文档：`docs/backend/ts-pi-agent-redesign.md`、`docs/backend/ts-pi-specs/00-roadmap-and-milestones.md`

---

## 1. 目标范围与前置依赖

### 1.1 目标范围
将原先分散在 Python 侧的“叶茂按钮流式函数”与“LangGraph 三节点”彻底合并为一个统一的 **`LangGraph.js` 资源生成子图**；把“全章串行阶段阻塞”升级为 **单小节并行流水线（图文 → 视频检索与 HTML 动画并发 → 单小节拼装即时落库）**；同时落实高质量视频检索下的平稳降级与会话显式重生成侧重点状态。

### 1.2 已锁定的业务决策
- **视频容错策略**：前提是优先保障视频检索器的高质量命中与精准校验；在此前提下，若某小节确无合格视频则**平稳降级**（正文跳过视频占位、提示暂缺视频），不阻断图文与交互动画的交付。
- **重生成侧重点追问**：从旧版 AI 回复文本中埋 `[LEAF_REGEN_PENDING]` 隐藏标签，升级为 **`ConversationSession.session_state.pending_leaf_regeneration` 显式结构化字段**。

---

## 2. 现有源码盘点与必须兼容的边界约束

1. **前端叶茂页事件消费强契约**（`frontend/src/pages/leaf/leafGenerationEvents.ts`、`leafPrompt.ts`）
   - 前端点击“生成/重新生成本章内容”时发送包含 `[LEAF_RESOURCE_GENERATION]` 块的消息（含 `course_node_id`、`chapter_section_id`、`scope`、`mode`）。
   - 前端 `dispatchLeafGenerationEvent()` 严格校验：事件必须携带 `course_id`、`chapter_section_id`，且 `kind` 必须为 `"course_resource_section"` 或 `"course_resource_chapter"`，附带 `section_id`、`phase`（`markdown` / `video` / `animation` / `compose`）、`status`（`queued` / `running` / `completed` / `error`）。
   - 当收到 `event === "agent_result"` 且 `success === true` 且 `status === "completed"` 时，前端会立刻触发页面刷新加载已落库内容——**这意味着只要我们每完成一个小节就即时落库并推 `compose` 的 `agent_result`，叶茂页无需改代码就能实现“首小节完成即刻可读”！**
2. **章节解锁与并发锁门禁**（`backend/app/api/chat_handlers.py`、`course_generation_status_service.py`）
   - 仅允许为当前学习课程生成资源；仅允许为第一章或上一章测验已通过（`passed`）的章节生成；生成期间必须持有章节级并发锁防止重复点击，无论成功或异常退出必须在 `finally` 释放锁。
3. **小节正文质量与占位符契约**（`backend/app/orchestration/agents/course_resources/markdown.py`）
   - 严格以绑定教材中文正文证据包为唯一事实来源（含 M6 自动拆分后的 `source_char_range` 切片）。
   - 必须包含 5 个固定二级标题：`## 学习目标`、`## 核心概念`、`## 步骤讲解`（含表格或代码块）、`## 练习任务`、`## 检查标准`（至少 4 条 `- [ ]` 验收清单），以及视频占位符 `<!-- video:id=video_1 -->`、动画占位符 `<!-- animation:id=anim_1 -->`。
4. **小节阶段检查点**（`backend/app/orchestration/recovery.py`）
   - 大纲内 `section_resource_checkpoints[section_id][phase]` 记录每个小节在 `markdown`、`video`、`animation`、`compose` 的完成状态、输出引用与质量校验结果。
5. **外部视频检索现状**（`bilibili.py`、`aliyun_bilibili_search.py`、`video.py`）
   - 视频检索本质是确定性外部检索 + 链接可用性与相关性校验（不消耗用户大模型），需在 TS 侧重写或通过内部工具模块保留高质量检索与严格核验。

---

## 3. 业务模块设计与核心流转

### 3.1 统一入口门禁节点（`resource_gatekeeper`）
无论是叶茂页按钮（带 `[LEAF_RESOURCE_GENERATION]`）还是对话自然语言触发（如“生成第一章内容”），统一进入子图入口节点：
1. **重生成侧重点状态机（显式字段）**：
   - 若请求为 `mode = "generate"` 且目标章节已有已拼装正文：不启动生成，向 `session_state.pending_leaf_regeneration` 写入 `{ course_node_id, chapter_section_id, requested_at }`，向学生追问“重新生成本章前，请告诉我下一版需要侧重哪里？”，结束本轮。
   - 下一轮学生回复侧重点时，入口分流器直接读取 `session_state.pending_leaf_regeneration`，将其作为 `regeneration_focus` 启动重生成，并在启动时清空该待确认字段。
2. **业务门禁与加锁**：调 Python 内部接口一次完成：① 当前课程校验；② 章节测验解锁校验；③ 教材学生可见性校验；④ 申请章节级生成锁；⑤ 拉取目标章下全部叶子小节的教材正文切片（尊重 M6 `source_char_range`）与已有小节检查点。

### 3.2 单小节并行流水线（LangGraph Fan-out / Fan-in）
整章叶子小节按 **2–3 个小节受控并发** 分发，每个小节独立走完以下 4 步闭环（每一步先查检查点，若非重生成且该阶段检查点已通过质量校验，则直接跳过复用）：

1. **小节图文节点（Pi 循环 + 自修）**
   - 基于教材正文证据包、学生画像与可选 `regeneration_focus`，产出 5 板块 Markdown 正文 + 结构化 `video_briefs` + `animation_briefs`。
   - 确定性质量校验器核验 5 大标题、表格/代码块、4 条验收清单与占位符匹配；不合规则通过 Pi 循环原地自修（最多 2 次）。
   - 通过后立即落盘 `markdown` 阶段检查点并推送进度事件。
2. **并行分叉：视频检索节点 ∥ HTML 动画节点**
   - **高质量视频检索节点**：
     - 根据 `video_briefs`（精准知识点关键词 + 课程语境）执行多策略检索（如 B 站等高质量教学视频源），过滤标题无关、时长过短/过长、低质营销号，并做真实链接可访问性与封面校验。
     - 若多轮精准与放宽检索均未找到合格视频：标记该小节 `video_status = "unavailable"`，**平稳降级不抛硬错**，落盘检查点并推送提示事件（“该小节暂未找到合适教学视频，已平稳跳过”）。
   - **HTML 交互动画节点（Pi 循环 + 安全校验 + 兜底模板）**：
     - 根据 `animation_briefs` 生成可独立嵌入沙箱渲染的交互式 HTML 动画；执行结构与安全性校验（无外链脚本、有效交互控件、与知识点绑定）；不合规则带具体报错原地自修 1 次；仍不通过时自动降级为确定性教学交互模板动画，确保交付稳定。
3. **单小节拼装与即时落库节点（确定性模块）**
   - 等待当前小节的视频与动画分支汇合。
   - 按占位符确定性拼装最终 `section_composed_markdowns[section_id]`（视频平稳降级时自动移除失效占位并附简洁提示）。
   - **即时落库 + 推可读事件**：调用 Python 内部单小节合并持久化接口保存该小节的 `markdown` / `video` / `animation` / `composed` 与阶段检查点，随即推送 `phase = "compose"`、`status = "completed"` 的 `agent_result`，前端叶茂页立刻刷新可读。

### 3.3 章节汇总与收尾节点（`resource_finalize`）
- 无论所有小节全部成功还是个别小节在图文阶段最终失败，`finally` 必定调用 Python 内部接口**释放章节级生成锁**。
- 对成功生成的小节汇总结果，通知 Python 内部接口执行 `score_course_resources` 质量评分，并向前端发出 `message_completed` 与 `session_completed`（若有小节失败，明确列出失败小节编号，提示可直接点击重试补跑，已成功小节会自动复用检查点）。

---

## 4. Python 内部接口契约新增

- `POST /internal/students/{user_uid}/courses/{course_id}/chapters/{chapter_id}/generation-prepare`：完成当前课程校验、章节解锁校验、教材可见性校验、申请章节生成锁，并返回目标章下全部叶子小节的教材正文切片（按 `source_char_range`）与已有资源检查点。
- `PUT /internal/students/{user_uid}/courses/{course_id}/sections/{section_id}/resources`：加学生锁原子合并写入单个小节的图文、视频、动画、拼装结果与阶段检查点（避免并发小节互相覆盖整个大纲 JSON）。
- `POST /internal/students/{user_uid}/courses/{course_id}/chapters/{chapter_id}/generation-finish`：释放章节生成锁并触发课程质量打分。

---

## 5. 风险点与缓解策略

1. **多小节并发写同一门课大纲产生 JSON 覆盖竞态**：所有单小节落库必须通过 Python 内部接口在 `lock_student` 行锁内做 JSON 字段级合并（只覆写目标 `section_id` 对应键），绝不允许 TS 侧全量覆盖整份 `outline_data`。
2. **视频检索质量退化**：在 TS 侧为视频检索器建立独立单测与相关性打分规则（关键词命中 + 教学类标题加权 + 链接真实可达核验），确保“先高质量命中，确无结果才平稳降级”。

---

## 6. M7 可执行验收清单

| 编号 | 验收维度 | 具体验证步骤 | 预期达成结果 |
|---|---|---|---|
| **AC-1** | 单一子图消除双轨 | 分别从叶茂页点击“生成本章内容”和在对话框输入“生成第一章教学内容” | 两条入口均进入同一资源子图，前端 `leafGenerationEvents` 正常接收进度与完成刷新。 |
| **AC-2** | 视频与动画并行 + 首节即刻可读 | 生成含 3 个小节的章节，观测日志时间戳与前端叶茂页 | 同一小节内视频检索与动画生成时间窗口重叠；第 1 小节 `compose` 完成后数据库立即可查、叶茂页无需等整章结束即可阅读第 1 小节。 |
| **AC-3** | 检查点断点续跑 | 模拟第 2 小节在动画阶段失败 → 再次触发本章生成 | 第 1 小节全部阶段与第 2 小节的图文/视频阶段自动跳过复用，仅补跑第 2 小节的动画与拼装。 |
| **AC-4** | 高质量视频检索与平稳降级 | ① 正常知识点检索教学视频<br>② 模拟外部视频源全部无合格结果 | ① 返回真实可访问且主题匹配的教学视频<br>② 图文与交互动画正常拼装落库交付，正文优雅跳过视频占位，整章不报错。 |
| **AC-5** | 显式重生成侧重点状态 | 对已有内容的章节点击重新生成 → 检查数据库 `session_state` 与 AI 回复原文 → 输入侧重点继续生成 | AI 回复不再包含 `[LEAF_REGEN_PENDING]` 隐藏文本；`session_state.pending_leaf_regeneration` 正确记录并在新一轮启动后清空，生成内容体现侧重点。 |
| **AC-6** | 并发锁释放与防重 | 生成期间再次点击同一章节生成；以及模拟中途异常 | 并发重复点击被门禁拒绝提示正在生成；异常中断后章节锁被 `finally` 正确释放，可立即重新触发。 |
