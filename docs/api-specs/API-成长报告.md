# 成森 AI 成长报告

## 产品范围

在 `/canopy` 点击生成成长报告，阅读累计学习回顾、优势、待巩固内容和最多三项下一步建议。支持来源展开、跳转已有课程、重新生成。报告只保留在当前页面内存中；刷新、离开页面或切换账号后清理，不新增报告表。

## 请求与事件

`POST /api/branch/canopy/report/stream`

使用 `Authorization: Bearer <token>`。无请求体，用户范围由认证信息确定。未认证返回 401；成功建立连接后响应为 `text/event-stream`，禁用缓存和代理缓冲。

| SSE event | data | 含义 |
| --- | --- | --- |
| `report_stage` | `{"stage":"collecting"}` | 整理学习记录 |
| `report_stage` | `{"stage":"analyzing"}` | 选择、读取分析证据 |
| `report_stage` | `{"stage":"writing"}` | 生成与校验报告 |
| `report_completed` | `GrowthReport` | 完整且通过结构与引用校验的报告 |
| `report_error` | `{"message":"成长报告暂时未能生成，请稍后重试。"}` | 生成失败，可重新请求 |

阶段依实际流程发出，不代表百分比。连接结束但没有 `report_completed` 时，客户端视为中断；重新生成失败保留当前旧报告。离开页面或换账号会取消客户端请求。

`GrowthReport` 定义在 `backend/app/report_schemas.py`，生成的前端类型位于 `frontend/src/types/api.ts`：

- `generated_at`：后端整理记录时的 UTC 时间。
- `stats`：`passed_chapters`、`tested_chapters`、`attempts`，均由后端计算。
- `overview`：成长概述。
- `strengths`、`improvements`：每项含 `title`、`body`、`evidence_ids`。
- `actions`：最多三项，除上述字段外含 `check`（完成标准）、`course_id`（已有课程标识或 null）。
- `evidence`：实际引用的来源，每项含 `id`、`kind`、`title`、`detail`、`course_id`。
- `coverage`：统计覆盖范围、证据目录上限、缺少测验时的说明。

## 数据与生成链路

1. 按认证用户读取画像、年度课程路径、实际章节通关、测验作答和历史薄弱点。画像只取已确认的年级、专业、学习偏好。
2. 全量记录计算统计；模型证据目录最多收录每年 30 个课程目标、最近 30 份有作答测验、30 个课程小节和 30 条薄弱点。章节目录按课程大纲更新时间排序。
3. 复用 `get_worker_llm()`，通过 `EvidenceSelection` 选择最多 6 项只读工具请求：`read_quiz`、`read_chapter`、`read_textbook`。标识必须来自本次目录，不做模糊匹配或自动修正。
4. 测验详情最多读取最近三次作答；章节详情只取选定小节和已生成文档。教材工具只读课程绑定的已发布教材、小节正文，不调用会写入知识缺口的服务。单次详情限制 5000 字符；作答中的图片 data URL 不进入模型。
5. 结构化生成 `ReportNarrative`。校验真实引用、教材可用性、优势测验证据和课程跳转范围，并检查事实分析中是否出现输入里没有的阿拉伯数字；未来练习建议中的示例数字与数量不作为既有事实校验。
6. 内容校验失败时，携带明确错误和原始标识目录让模型修正一次；仍失败则发出错误事件。整个生成流程超时 180 秒。数值字面量与引用存在性校验不能替代语义质量判断。

## 统计口径

- 已通关章节：`ChapterProgress.state == "passed"` 的记录数。
- 参与测验章节：有当前用户作答记录的课程、章节去重数。
- 累计作答：当前用户对自身测验的全部提交次数，包括重复尝试。
- 不使用图谱路径位置推导学生掌握情况；不把资源质量分当成能力分。
- 不使用估算的 `focused_hours`；不将 `avg_score`（已通关章节最高分平均值）称为全部测验平均分。
- `ChapterWeakness.consumed` 只代表资源生成是否消费该记录，不代表掌握或薄弱点解决。
- 测验题目可能重新生成，首次与最近成绩只用于描述记录变化，不能直接推导能力提升。
- 无测验时生成目标与路径回顾，优势列表为空，页面说明学习表现待验证。

## 验证入口

```bash
cd backend
uv run pytest -q tests/test_growth_report.py tests/test_canopy_api.py

cd ../frontend
npm run gen:api
npm test
npm run build
npm run e2e -- growth-report.spec.ts
```

浏览器测试使用合成报告，覆盖加载定位、来源展开、失败保留、重试、课程跳转及移动端布局；真实模型链路另用合成学习记录验证，不混淆为真实学生评估。
