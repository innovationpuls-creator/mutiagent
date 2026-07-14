# 阿里云 Bilibili 视频搜索设计

## 目标

只替换视频 Agent 的联网搜索链路。使用项目现有 `LLM_API_KEY` 与 `LLM_MODEL` 调用 DashScope 原生联网搜索，取得可审计的 Bilibili 搜索来源；其他 Agent、全局阿里云模型工厂和编排顺序不变。

## 根因

编排图已经把启用阿里云联网搜索的 `search_worker_llm` 传给视频 Agent，但 `run_section_video_search_agent` 使用 `_ = llm` 丢弃该对象，实际走本地搜索页抓取器。生产服务器访问 YouTube 全部 `ConnectTimeout`，Bilibili 抓取器虽每次返回 12 条结果，但查询噪声与字符串门禁会接受无关标题或拒绝全部结果。

## 数据流

1. 从当前叶子小节及对应 `video_briefs` 读取课程名、章节名、小节标题、目标段落、目的和搜索词。
2. 通过 `asyncio.to_thread` 调用同步 `dashscope.Generation.call`，避免阻塞事件循环。
3. 请求使用当前 `LLM_API_KEY`、`LLM_MODEL`，并精确设置：
   - `enable_search=True`
   - `result_format="message"`
   - `search_options.forced_search=True`
   - `search_options.search_strategy="turbo"`
   - `search_options.enable_source=True`
   - `search_options.assigned_site_list=["bilibili.com"]`
   - `search_options.intention_options.prompt_intervene` 写入当前课程、小节和 brief 的语义边界
4. 只读取 `response.output.search_info["search_results"]` 中的 `title`、`url`、`site_name`、`index`，不采信模型正文里的 URL。
5. 只保留现有精确 Bilibili `/video/BV...` URL 校验通过的来源，并通过现有 Bilibili 稿件接口验证真实可见。
6. 按阿里云搜索来源顺序保存第一条验证通过的视频。没有来源、API 跳过搜索、URL 不精确或稿件不可见时返回无视频，由现有整章硬失败契约处理。

## 边界

- 不修改 `backend/app/orchestration/llm.py`。
- 不修改 `backend/app/orchestration/graph.py`。
- 不修改 Markdown、动画、课程大纲或其他 Agent。
- 不恢复搜索页 URL 兜底，不把模型正文当作搜索来源。
- 不新增环境变量和第三方依赖；项目已固定 `dashscope==1.26.2`。

## 验收

- 单元测试证明请求参数、来源解析、精确 URL 过滤和失败语义。
- 原有视频质量、整章硬失败及编排回归全部通过。
- 使用当前阿里云账号和模型完成一次真实搜索烟测，结果来源必须来自 `output.search_info.search_results`。
- 生产重跑后逐小节核对状态、真实标题、URL 和章节语义；任何小节缺少合格视频则整章失败。
