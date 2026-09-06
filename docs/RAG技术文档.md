# RAG 技术文档

## 1. 概述

RAG（Retrieval-Augmented Generation，检索增强生成），核心思想：检索外部私有知识库，把检索到的片段拼入 Prompt，交给大模型生成答案，弥补大模型静态训练知识的缺陷，解决幻觉、私有数据问答、知识过期问题。

### RAG ≠ 微调

- **微调**：修改模型权重，学习知识 / 风格，成本高；
- **RAG**：不改动模型，外部拿资料做上下文注入，轻量、可随时更新知识库。

## 2. 整体工作流程

完整分为两大阶段：**索引构建阶段（离线）**、**推理问答阶段（在线）**。

### 2.1 索引构建（离线预处理）

1. **文档加载**：PDF、Markdown、txt、网页、数据库等原始文档读取。
2. **文档解析 & 清洗**：去除无用格式、乱码、页眉页脚。
3. **文本分块（Chunk）**
   - 为什么分块：Embedding 输入长度有限；控制检索粒度，避免上下文过长。
   - 参数：块大小 `chunk_size`，重叠 `chunk_overlap`（防止语义被切断）。
4. **向量化 Embedding**：把文本块转为向量（稠密向量）。
5. **存入向量数据库**：如 Chroma、FAISS、Milvus、MinIO 搭配向量库。
   - 补充：混合检索系统会同时保存原始文本，做 BM25 关键词检索。

### 2.2 推理问答（在线，用户提问）

1. 用户输入 Query。
2. Query 向量化，到向量库做相似度检索，返回 Top-N 相关文本块。
3. （可选）重排序 Reranker：对检索结果二次打分过滤，提升相关性。
4. 构造 Prompt 模板：把用户问题 + 检索出来的上下文拼接。

```plaintext
参考上下文：
{检索到的片段}
请基于上面参考上下文回答用户问题，不要编造信息。
用户问题：{query}
```

5. 送入大模型，生成回答返回给用户。

## 3. 核心组件说明

### 文档切片 Chunk

- 块太大：噪声多，无关内容混入；
- 块太小：语义断裂，信息不全。
- 经验：中文一般 **300–800 token**，overlap **50–150**。

### Embedding 模型

将语义转为高维向量，语义相近向量距离近。开源：bge-v3、m3e；闭源：OpenAI text-embedding。

### 向量数据库

存储向量，提供 ANN 近似最近邻搜索，解决海量向量暴力比对速度慢。

### Reranker 重排器

检索阶段召回一批候选，reranker 模型输入 `(query, passage)` 打分，筛掉语义不匹配，显著提升 RAG 精度。

### 大模型 LLM

负责最终生成，不存储私有知识。

### 混合检索 Hybrid Search

向量语义检索 + BM25 关键词检索，融合两者得分。向量抓语义；BM25 抓关键词、专有名词，解决纯向量检索漏召回。

## 4. RAG 常见问题与缺陷

- **幻觉依然存在**：检索到无关片段，模型依旧会顺着错误材料输出；需要 Prompt 约束、reranker 过滤。
- **检索失败（召回不到有效资料）**
  - chunk 切分不合理；
  - embedding 不匹配业务场景；
  - query 和文档表述措辞差异大。
- **上下文溢出**：检索返回太多片段，超过 LLM 上下文窗口。解决：限制 topN、reranker 精简、窗口压缩。
- **噪声混入**：检索返回无关文档片段，误导输出。

## 5. RAG 优化方向

- **数据侧**：文档清洗、优化分块策略（语义分块代替固定长度分块）
- **检索侧**：混合检索、Reranker、查询改写（Query Expansion），把用户问题扩写多版本做多路检索
- **生成侧**：严格 Prompt 约束，引用溯源输出，标记信息来源片段
- **进阶**：Agent-RAG，增加工具调用、自我校验；分层 RAG（摘要索引 + 细粒度块索引）

## 6. 极简伪代码（Python 逻辑）

```python
# 1. 离线构建知识库
docs = load_documents("./docs/")
chunks = split_text(docs, chunk_size=500, overlap=80)
embeddings = embedding_model.encode(chunks)
vector_db.add(embeddings, chunks)

# 2. 用户问答
query = "用户的问题"
query_vec = embedding_model.encode(query)
candidates = vector_db.search(query_vec, top_k=4)
candidates = reranker.rerank(query, candidates)
prompt = build_prompt(query, candidates)
answer = llm.chat(prompt)
print(answer)
```

## 7. RAG 与 Agent 简单区分

- **RAG**：核心是检索资料做问答，偏向知识库问答；
- **Agent**：核心是思考 + 工具调用，可以调用 RAG、计算器、API 完成复杂任务。Agent 可以内置 RAG 作为其中一个工具。

## 8. 工程部署注意点

- **知识库更新**：新增文档需要重新分块、向量化入库；删除文档需要向量库同步删除；
- **可观测性**：记录检索命中片段，方便排查为什么回答出错；
- **成本**：Embedding 调用成本、向量库内存开销、LLM 输入 token 随检索片段增加上涨。
