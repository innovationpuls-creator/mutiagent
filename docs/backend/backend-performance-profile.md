# OneTree 后端性能剖析报告（cProfile / pstats）

- **采样日期：** 2026-10-03
- **用途：** 为后续 AI 优化会话提供当前后端耗时基线和可核查的代码入口。

## 结论

这次对后端完整测试套件进行了 `cProfile` 采样。采样覆盖了 892 项测试实际执行到的后端代码，不等于线上全部请求、所有分支或生产 LLM 延迟。

在这组测试负载中，累计耗时最大的后端代码集中在：

1. 应用和数据库初始化：`init_db`、`create_app`、`run_schema_upgrades`。
2. 用户创建时的密码哈希：`hash_password`，实际时间主要花在 bcrypt 的 C 扩展中。
3. 测试反复触发的 PostgreSQL schema 反射与 SQL 执行。
4. 知识库混合检索：`hybrid_search_textbooks`，其测量值包含 embedding 客户端调用，不能当作纯 Python CPU 时间。

**首要解释限制：** 测试会反复创建应用和测试 schema，累计启动、迁移和数据库反射耗时被放大。当前生产配置在 `create_app` 中走 `assert_schema_at_head`，开发/测试配置才走 `init_db`；因此不能把测试中的 `init_db` 累计值直接解释成生产启动时间或请求延迟。

## 采样方法与负载

- Python：CPython 3.12.14。
- 采样器：标准库 `cProfile.Profile`。
- 汇总器：标准库 `pstats.Stats`，分别按 `cumulative` 与 `tottime` 排序。
- 负载：`pytest.main(["-q", "--tb=short"])`，完整收集到 892 项后端测试。
- 结果：**892 passed，1 条 StarletteDeprecationWarning，258.40 秒**；`cProfile` 记录 129,352,990 次调用（125,092,997 次 primitive calls），总计 258.288 秒。
- 数据库：本机 PostgreSQL `mutiagent`。为保留既有数据库状态，运行器将全局 orphan schema 清理函数替换为 no-op；每个测试自身注册的 schema 清理仍启用。采样后 `test_*` schema 数量为 0。
- 测量值是整套测试进程里的累计值。表格中的每次调用平均值仅用于帮助阅读，不是基准稳定性或线上单请求的保证。

运行时使用了完整测试集。检查发现知识库混合检索测试没有替换 embedding 客户端，且本地 `.env` 配有模型密钥；因此 `hybrid_search_textbooks` 的 24 次调用很可能触达外部 embedding API。`cProfile` 不能证明请求是否被服务端接受或是否计费。这部分结果可能包含网络等待，不应被当作纯 CPU 热点；后续复测前应先设置离线 embedding 替身。

本次没有持久化二进制 `.prof` 文件。下表记录的是运行时 `pstats` 输出中可见的函数统计；若要对原始调用树重新排序，需要在隔离外部服务的条件下重新采样。

## 后端函数排名

按 `pstats` 的 cumulative time 排序。父函数包含子函数时间，**行与行之间有重叠，不能求和**。

| 函数 | 调用次数 | 自身耗时 | 累计耗时 | 约每次调用 | 代码位置 |
|---|---:|---:|---:|---:|---|
| `init_db` | 297 | 0.006 秒 | **131.219 秒** | 0.442 秒 | [`database.py:62`](../../backend/app/database.py#L62) |
| `create_app` | 185 | 0.009 秒 | **104.712 秒** | 0.566 秒 | [`main.py:34`](../../backend/app/main.py#L34) |
| `hash_password` | 480 | 0.003 秒 | **86.826 秒** | 0.181 秒 | [`security.py:27`](../../backend/app/core/security.py#L27) |
| `bcrypt._bcrypt.hashpw` | 480 | **86.819 秒** | **86.819 秒** | 0.181 秒 | bcrypt C 扩展，被 `hash_password` 调用 |
| `run_schema_upgrades` | 373 | 0.019 秒 | **73.176 秒** | 0.196 秒 | [`schema_upgrades.py:37`](../../backend/app/schema_upgrades.py#L37) |
| `ensure_demo_user` | 299 | 0.008 秒 | **56.242 秒** | 0.188 秒 | [`database.py:75`](../../backend/app/database.py#L75) |
| `register_user` | 129 | 0.008 秒 | **22.317 秒** | 0.173 秒 | [`auth_service.py:51`](../../backend/app/services/auth_service.py#L51) |
| `_normalize_knowledge_gap_notice_action_payloads` | 373 | 0.004 秒 | **19.968 秒** | 0.053 秒 | [`schema_upgrades.py:114`](../../backend/app/schema_upgrades.py#L114) |
| `hybrid_search_textbooks` | 24 | 0.002 秒 | **16.805 秒** | 0.700 秒 | [`knowledge_base_service.py:1562`](../../backend/app/services/knowledge_base_service.py#L1562) |
| `_upgrade_textbook_section_content_original_column` | 373 | 0.003 秒 | **12.636 秒** | 0.034 秒 | [`schema_upgrades.py:186`](../../backend/app/schema_upgrades.py#L186) |
| `_recalculate_knowledge_gap_follow_counts` | 373 | 0.005 秒 | **11.102 秒** | 0.030 秒 | [`schema_upgrades.py:513`](../../backend/app/schema_upgrades.py#L513) |
| `_create_knowledge_base_tables` | 373 | 0.006 秒 | **10.578 秒** | 0.028 秒 | [`schema_upgrades.py:80`](../../backend/app/schema_upgrades.py#L80) |
| `_upgrade_textbook_embedding_column` | 373 | 0.002 秒 | **10.314 秒** | 0.028 秒 | [`schema_upgrades.py:806`](../../backend/app/schema_upgrades.py#L806) |

### 数据库与驱动层

这些行说明数据库操作和 schema 反射对测试总耗时有显著贡献。它们与上表中的 `init_db`、`run_schema_upgrades` 等父函数统计重叠。

| 函数 | 调用次数 | 累计耗时 | 说明 |
|---|---:|---:|---|
| SQLAlchemy `Engine.execute` | 60,482 | 90.112 秒 | ORM/SQL 调用入口 |
| psycopg `cursor.execute` | 92,418 | 85.850 秒 | PostgreSQL 驱动执行；含数据库往返耗时 |
| PostgreSQL dialect `get_columns` | 2,071 | 55.110 秒 | schema 反射，主要由迁移检查路径触发 |

`get_columns` 约 26.6 毫秒/次。它的高累计值与 373 次 schema 升级调用同时出现，是优先检查迁移反射重复工作的依据；是否能缓存或减少反射，仍需检查每个迁移函数的事务、幂等和旧 schema 兼容要求。

## 独立补充：教材 HTML 解析微基准

此前还对 `parse_and_slice_html` 做过独立采样。这是一个合成教材输入，只说明知识库导入路径，不并入上面的测试套件排名。

- 输入：279,360 字节 HTML，8 章、400 节、每节 4 段。
- 执行：连续完整解析 3 次，生成 102,806 字符 Markdown；总计约 0.417 秒。
- 累计耗时：MarkItDown `convert_local` 0.287 秒；HTML converter `convert` 0.256 秒；BeautifulSoup `_feed` 0.122 秒；Markdownify `process_tag` 0.114 秒。
- 项目代码：`locate_and_slice_sections` 0.067 秒；`_next_section_heading_position` 累计 0.062 秒、自身 0.019 秒。

代码位置见 [`document_parser_service.py:58`](../../backend/app/services/document_parser_service.py#L58) 和 [`document_parser_service.py:197`](../../backend/app/services/document_parser_service.py#L197)。标题查找对每个 section 扫描行列表；随着教材行数和节数增多，这段工作会增加。需要用真实教材样本再测，不能仅凭该合成输入就判定生产瓶颈。

## 给后续优化会话的工作顺序

1. **先分开负载。** 分别建立生产模式冷启动、开发模式初始化、用户注册/登录、知识库检索、教材解析的 profile；不要把整套测试累计时间当成单请求时间。
2. **迁移路径先量清楚。** 对全新 schema 和已升级 schema 分别采样 `run_schema_upgrades`，检查 PostgreSQL `get_columns` 和重复 `UPDATE` 的调用来源，再评估反射或写入能否安全减少。
3. **分离认证路径。** 对 `register_user` 拆解数据库操作与 bcrypt 成本。不得为追求速度而直接降低密码哈希安全参数；先确认认证安全要求和调用路径是否有重复哈希。
4. **检索路径隔离外部等待。** 给 embedding API、向量/全文 SQL 和 fallback 分别计时。用本地确定性替身做 CPU/数据库基准，真实 API 延迟单独记录。
5. **保留导入基线。** 对真实教材大小、HTML/PDF 类型和 section 数量做多个样本，区分 MarkItDown 转换时间与项目目录提取、切片时间。
6. **优化后重跑对应样本。** 记录相同 Python/依赖、数据规模、调用次数、cumulative 与 tottime，并运行受影响的后端测试；先报告实测变化，再讨论是否需要扩大范围。

生产应用入口与启动分支见 [`main.py:34`](../../backend/app/main.py#L34)；数据库初始化见 [`database.py:62`](../../backend/app/database.py#L62)；生产迁移版本检查见 [`migration_state.py:55`](../../backend/app/migration_state.py#L55)。

## 可交给优化会话的任务说明

> 阅读本报告及标注的后端源码。先建立不调用真实外部模型服务的可复现 profile，把生产冷启动、数据库迁移、认证、知识库检索和教材解析分开测量。优先确认 `run_schema_upgrades` 中 PostgreSQL schema 反射与重复 SQL 的成本，以及 `register_user` 中 bcrypt 与数据库操作的占比。不要用测试累计时间推断生产单请求延迟，也不要在没有安全依据时降低密码哈希成本。提出优化后，按相同数据和运行环境对比 cProfile/pstats，并运行相关后端测试。


---

## 2026-10-03 实施后复测

上文保留原始采样，不修改其历史数值。以下数据来自独立 PostgreSQL 实例，不能与上文的整套测试累计时间直接比较。

### 环境与测量边界

- macOS arm64，CPython 3.12.14，PostgreSQL 18.4；SQLAlchemy 2.0.50、SQLModel 0.0.38、FastAPI 0.136.3、bcrypt 5.0.0、MarkItDown 0.1.6。沿用项目锁定依赖。
- 基线来自本次修改前的 Git HEAD；完整 revision、每次采样、SQL 类型和峰值内存在 [机器可读结果](backend-performance-results-20261003.json)。使用 `git archive` 临时副本执行基线，未切换或回滚工作区。
- 临时集群监听本机独立端口；每个基准再建立独立 schema，结束后删除该 schema。业务数据库未用于写入或测试清理。测试亦仅连接该临时集群。
- 除 SSE 一次批次、启动三个新进程外，每项五次。普通表格为同时开启 cProfile、tracemalloc 的 wall time 中位数；SQL 次数按单次操作计算。空库清表、旧库 JSON 列准备、播种 1,000 条数据均不计入测量。
- 大数据负载：1,000 本已发布教材、1,000 个测验与作答、1,000 条已通过 progress；教材 outline、问题和答案各含约 2 KB 合成内容。模型是确定性替身，无外部模型网络请求。
- `.prof`、pstats 文本、JSON 和测试日志保存在本地 `backend/.codex-artifacts/backend-performance/`。cProfile 仅覆盖运行线程；异步改造后的线程池 CPU 不全部进入主线程调用树，不能据此声称 CPU 成本等比例下降。tracemalloc 是 Python 分配峰值，不是进程 RSS。

### 数据库与统计

| 相同负载 | 修改前 ms | 修改后 ms | 修改前 SQL | 修改后 SQL |
| --- | ---: | ---: | ---: | ---: |
| 空 schema 初始化，不播种用户 | 91.468 | 47.246 | 190 | 87 |
| 当前 schema 重复初始化 | 51.241 | 45.834 | 115 | 93 |
| profile_data 为 JSON 的兼容升级 | 49.808 | 45.698 | 115 | 96 |
| Canopy，1,000 条 progress | 50.025 | 4.881 | 8 | 7 |
| 成长报告上下文，1,000 份历史作答 | 86.793 | 12.559 | 7 | 8 |
| 顺序检查 1,000 个已通过章节 | 783.451 | 10.331 | 1,000 | 1 |
| 注册，真实 bcrypt | 176.648 | 176.366 | 3 | 3 |
| 登录，真实 bcrypt | 176.156 | 176.355 | 3 | 3 |
| 单次 worker 领取 | 4.485 | 4.648 | 5 | 5 |

空库现在直接建当前模型：每次只有 1 次反射 SELECT，86 条 CREATE；旧路径每次 98 次 SELECT，且含 UPDATE、ALTER、DROP。当前库每次 SELECT 从 107 次降到 87 次，JSON 旧库降到 89 次。Inspector API 调用计数在 JSON 文件中；缓存减少底层重复反射 SQL，并不保证 Python `get_columns` 调用次数减少。当前库该方法五次采样合计从 45 次变为 50 次，因此不把方法调用数量当作 SQL 节省指标。

迁移继续修复历史数据及通知约束。已为 JSONB 的列不再 ALTER；关注人数仅更新差异行，回归测试中第一次纠正 1 行、第二次 0 行。严格通知约束仍按原规则重建，没有使用表达式字符串的宽松等价判断。缓存只活在一次连接内，DDL 后失效。空库、旧库、重复升级、松通知约束修复、原文和历史数据保留均由现有迁移测试覆盖。

Canopy 的 Python 分配峰值从 6,217,198 降到 375,238 bytes；成长报告上下文从 10,046,404 降到 709,002 bytes。报告累计统计仍覆盖全部历史，但最多加载最近 30 份测验及必要证据。SQL 增加一条用于分别计算累计统计，不再把所有 JSON 答案载入 Python。新增测试使用 40 份测验、80 次作答，核对累计统计、最近 30 份选择及首次/最近成绩；原测试继续验证用户隔离和题目快照。

注册未减少安全成本：bcrypt cost=12、SQL 次数均保持。仅不使用演示账号的 conversation/course knowledge/learning path/intake 服务测试采用 `seed_users=False`，认证及基准仍执行真实哈希。单次 worker 耗时没有改善；其收益是 SQL `LIMIT 1` 缩小锁范围，双事务回归证明首个 worker 提交前第二个 worker 能领取另一任务。

### 检索

当前 FLOAT[] 列、缺少 vector 运算符或 chinese 全文配置时，直接进入字符串匹配，embedding 调用次数为零。匹配仍限已发布教材，标题 +10，每个命中 tag +5，保留 Python 稳定排序与切片规则。

在相同 1,000 本教材下，给 embedding 客户端设置立即失败的替身，使旧代码可以成功进入原匹配路径：中位耗时从 53.310 降到 15.894 ms，Python 峰值从 5,096,732 降到 550,740 bytes。匹配结果一致，SQL 从 1 次变为 3 次：能力探测、轻量投影、选中实体加载。减少的是无关大字段加载，不是 SQL 条数。

让 embedding 替身成功返回向量时，旧实现会执行不支持的 SQL，随后 fallback 因事务已中止而失败；优化后正常返回 15 个结果。这条旧路径的 1.556 ms 是失败耗时，不能作为成功检索的性能基线。混合 SQL 使用 savepoint；强制失败的回归测试确认 fallback 成功且调用者待提交数据仍能提交。

### 教材解析

切片在不启用 cProfile/tracemalloc 时另外执行五次，保持相同 Markdown、outline 和输出 SHA-256：

| 合成小节数 | 修改前切片 ms | 修改后切片 ms | 输出 |
| --- | ---: | ---: | --- |
| 400 | 7.571 | 4.448 | 完全一致 |
| 1,600 | 66.810 | 17.449 | 完全一致 |
| 6,400 | 874.000 | 74.766 | 完全一致 |

正式实现为一次标准化标题索引及二分定位。重复标题、目录排除、缺失标题、Unicode、CRLF 和无末尾换行由回归覆盖。

转换和目录提取单独测量：此次转换输入是含 Markdown 内容的合成 `.txt`，不是上文 HTML 样本，也不是真实 PDF。开启测量工具时，400/1,600/6,400 节转换分别为 24.283/49.701/147.125 → 23.422/49.621/148.321 ms；目录提取为 24.622/98.184/379.988 → 24.914/96.670/380.767 ms，基本持平。第一次转换包含对应运行方式下的首次导入成本，完整 samples 保留在 JSON 中。MarkItDown 延迟到转换时导入，requests Session 在成功与异常退出时关闭，网络抓取预算不变。

没有真实教材样本，真实 PDF、远程 HTML、下载、完整导入 wall time 和真实网络收益仍未验证，不能将切片提速外推为整体导入提速。

### 短事务、并发与启动

认证、聊天上下文/结果、测验生成和批改、成长报告均使用绑定应用 engine 的短 Session。数据库操作在线程中完成、关闭连接后返回完整数据，再等待模型。Agent 内整段同步数据库 helper 移入线程；请求 engine 通过上下文传递，避免读取另一应用的全局 engine。聊天原有事件顺序和完成前持久化由测试保留，事务失败后的用户消息回退使用新 Session。

10 个报告同时生成、每次模型等待 50 ms 的同负载批次，初始复测总耗时 1,092.154 → 231.383 ms；SQL 70 → 80。旧代码在第二轮模型等待时持有 10 个连接，新代码第二轮为 0。第一轮观测整个 pool，仍可能看见其他请求的短查询占用，不能把该采样直接解释为本请求持有连接。追加独立批次（含服务首次导入）总 wall time 为 2,417.072 → 1,530.626 ms；请求 p95 为 1,033.580 → 226.156 ms，连接累计占用 6,026.490 → 875.587 ms。该批次和前一暖服务批次的导入状态不同，不能交叉比较。见 JSON 的 `before-sse-final` / `after-sse-final`。

35 个带认证的 HTTP 报告请求用模型屏障同时停在等待处：pool.checkedout()=0；健康接口在测试限定的 2 秒内成功返回，事件循环继续运行，释放屏障后全部得到 report_completed。聊天同样测试模型等待时连接为 0、使用正确 engine、完成事件前消息已提交，以及结束后上下文恢复。engine token 在每次推进生成器后、输出事件前恢复；额外回归验证另一异步任务提前关闭 SSE 时亦能清理。失败、权限及测验评分语义由完整回归覆盖。

生产启动不执行 init_db。三个新进程（文件系统缓存不清空）的无插桩中位冷导入为 699.570 → 599.343 ms，应用工厂为 55.307 → 79.041 ms；装配在这一组中反而增加，不能声称生产装配提速。开启 cProfile/tracemalloc 时，中位导入 7,020.832 → 6,293.833 ms，工厂 507.416 → 508.195 ms。启动 Python 分配峰值约 154 MB → 136 MB；主要将 MarkItDown 成本移到实际转换。本机一次测量不等于生产 SLA，和原报告不同环境/插桩结果不可直接拼接。

### 复跑

脚本仅向明确传入的数据库创建、删除自己生成的 profile schema。完整测试会清理 test_ schema，必须使用独立临时实例：

```bash
# 在仓库根目录；临时目录只属于本次复跑
PERF_ROOT=$(mktemp -d -t onetree-perf)
PERF_PORT=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
PG_BIN=/opt/homebrew/opt/postgresql@18/bin
"$PG_BIN/initdb" -D "$PERF_ROOT/data" -A trust -U "$USER"
"$PG_BIN/pg_ctl" -D "$PERF_ROOT/data" -l "$PERF_ROOT/server.log" -o "-h 127.0.0.1 -p $PERF_PORT" start
"$PG_BIN/createdb" -h 127.0.0.1 -p "$PERF_PORT" onetree_perf
export DATABASE_URL="postgresql://$USER@127.0.0.1:$PERF_PORT/onetree_perf"
export LLM_API_KEY=offline LLM_MODEL=offline LLM_BASE_URL=http://127.0.0.1:1/v1
export LANGSMITH_TRACING=false LANGCHAIN_TRACING_V2=false
cd backend
uv run --no-sync python scripts/profile_backend.py --database-url "$DATABASE_URL" --output-dir .codex-artifacts/backend-performance/replay --repeats 5 --size 1000
uv run --no-sync python scripts/profile_startup.py --database-url "$DATABASE_URL" --output-dir .codex-artifacts/backend-performance/replay-startup
uv run --no-sync python scripts/profile_startup.py --database-url "$DATABASE_URL" --output-dir .codex-artifacts/backend-performance/replay-startup-plain --plain
uv run --no-sync pytest -q
uv run --no-sync ruff check app scripts tests
uv run --no-sync ruff format --check app scripts tests
"$PG_BIN/pg_ctl" -D "$PERF_ROOT/data" -m fast stop
# 完成后删除自己创建的 PERF_ROOT 临时目录
```

基线复跑：将 JSON 中 baseline_revision 的 `backend/` 用 `git archive` 解压到新临时目录，复制当前 `backend/scripts/` 到临时副本；用原仓库 `.venv/bin/python` 及副本 backend 工作目录运行相同命令。两个版本使用相同依赖、数据库实例、数据规模和脚本。

### 验证结果与保留项

- 受影响测试：157 passed；新增性能回归共 9 项通过；取消生命周期补充测试：79 passed；最终完整后端：901 passed（122.00 秒）。测试 wall time包含环境、fixture 和真实 bcrypt，不能作为生产请求速度。
- Ruff check、format check 与 git diff --check 通过。保留已有 Starlette TestClient 的弃用 warning。
- HTTP/OpenAPI、SSE 事件、评分阈值和权限边界保持；未新增 pgvector、向量入库、排序规则或多进程部署。
- 真实 LLM/embedding、可用 pgvector 混合排序、真实教材及生产负载未验证；这些环境未在本次测试中模拟成成功结果。
- 本次未提交、推送或部署。上文原始报告内容保留，临时 PostgreSQL 和基线副本在交付前清理；本地原始 profile 作为复测证据保留。

## 2026-10-04 当前工作树全套后端测试剖析

本节补充当前工作树的完整测试集 profile，供后续优化会话定位**测试负载里**的耗时。它不是生产流量画像，也不与前面的 892 项历史样本直接做速度对比。

### 运行范围与复核文件

- 采样时 Git `HEAD` 为 `55b67705fecd21489b2d7bde518760ad19b8175c`，工作区已有未提交的后端实现和测试修改；profile 反映的是当时的工作树文件，不是该 commit 的干净检出。
- CPython 3.12.14、macOS arm64、PostgreSQL 18.6；完整运行 `backend` 下的 901 项测试。测试结果：**901 passed，1 条 Starlette `TestClient` 弃用警告，139.68 秒**。
- 测试数据库是本轮新建的 loopback 临时 PostgreSQL 实例，结束后已停止并移除；没有使用项目的 `mutiagent` 数据库。LLM 配置为不可达的本地离线地址，LangSmith tracing 关闭。
- `cProfile` 记录 **119,026,973 次调用（115,198,284 次 primitive calls），139.860 秒**。`pstats` 从原始文件导出累计时间、自身时间和调用次数排名。
- 当时 `backend/app` 的 83 个 Python 文件中，有 81 个出现在 profile；`backend/migrations` 的 5 个文件全部出现。未执行到的 app 文件是 `app/export_openapi.py` 与 `app/workers/__main__.py`。共得到 1,507 条 app/migration 函数记录；这表示测试实际触达范围，不代表所有语句或分支都执行过。
- 主线程原始 profile、全部 pstats 文本、仅后端函数 JSON 排名和 pytest 日志保存在本机忽略目录 `backend/.codex-artifacts/backend-performance/current-suite-20261004/`：[原始 `.prof`](../../backend/.codex-artifacts/backend-performance/current-suite-20261004/backend-test-suite.prof)、[完整 pstats 文本](../../backend/.codex-artifacts/backend-performance/current-suite-20261004/pstats-report.txt)、[后端函数 JSON 排名](../../backend/.codex-artifacts/backend-performance/current-suite-20261004/pstats-backend.json)、`profile-summary.json`、`pytest-profile.log`。JSON 含全部观测到的函数行及累计/自身排名，可用 `pstats.Stats` 重新排序 `.prof`。

### 当前测试负载中的后端累计耗时

按 `pstats` cumulative time 排序。父函数的累计值包含子函数，行间会重叠，不得相加。

| 后端函数 | 调用次数 | 自身耗时 | 累计耗时 | 代码入口 | 解读 |
| --- | ---: | ---: | ---: | --- | --- |
| `bcrypt._bcrypt.hashpw` | 435 | 72.159 秒 | 72.159 秒 | bcrypt C 扩展 | 密码哈希成本 |
| `hash_password` | 435 | 0.002 秒 | 72.164 秒 | [`security.py:27`](../../backend/app/core/security.py#L27) | 累计时间主要来自上面的 bcrypt |
| `create_app` | 186 | 0.007 秒 | 65.429 秒 | [`main.py:34`](../../backend/app/main.py#L34) | 测试反复创建应用的累计成本 |
| `init_db` | 298 | 0.004 秒 | 62.680 秒 | [`database.py:102`](../../backend/app/database.py#L102) | 测试/开发初始化路径，不等于生产请求延迟 |
| `ensure_demo_user` | 254 | 0.006 秒 | 42.612 秒 | [`database.py:120`](../../backend/app/database.py#L120) | 初始化演示用户，含密码哈希等子调用 |
| `register_user` | 129 | 0.002 秒 | 21.703 秒 | [`auth_service.py:51`](../../backend/app/services/auth_service.py#L51) | 注册服务累计值包含密码哈希 |
| `bcrypt._bcrypt.checkpw` | 48 | 7.945 秒 | 7.945 秒 | bcrypt C 扩展 | 密码校验成本 |
| `verify_password` | 48 | 0.000 秒 | 7.946 秒 | [`security.py:31`](../../backend/app/core/security.py#L31) | 累计时间主要来自上面的 bcrypt |
| `_ensure_admin_user` | 252 | 0.001 秒 | 7.801 秒 | [`database.py:141`](../../backend/app/database.py#L141) | 管理员初始化的测试累计成本 |
| `create_knowledge_base_router` | 186 | 0.002 秒 | 4.713 秒 | [`knowledge_base.py:110`](../../backend/app/api/knowledge_base.py#L110) | 测试重复构造知识库路由 |
| `run_schema_upgrades` | 78 | 0.001 秒 | 1.809 秒 | [`schema_upgrades.py:39`](../../backend/app/schema_upgrades.py#L39) | 本轮临时数据库上的迁移检查累计时间 |

这组结果首先说明测试负载会重复应用工厂、数据库初始化和演示账号播种；它们不应按累计秒数映射成单次生产启动。密码哈希仍是最明显的运行成本，但 bcrypt 参数承担安全强度，不能仅凭 profile 降低 cost。应用/路由纯 Python 自身时间远低于其累计时间；若要优化生产 API，应从相同请求场景的 wall time、数据库等待和并发数据判断，而不是从测试总时间推断。

### 线程与生产覆盖边界

本节全套 profile 使用一个 `cProfile.Profile` 包围 pytest 主线程。`TestClient` 可能通过 AnyIO portal 在线程中执行 ASGI 请求；这些工作线程中的 Python 调用不保证进入本节函数排名。因此不要把本节当作完整的并发 API CPU画像。此前“短事务、并发与启动”中的 SSE 同负载 wall time、请求 p95、连接占用和 35 路 HTTP 屏障测试是独立证据，应与本节分开阅读。

覆盖边界还包括：未执行 `app/export_openapi.py` 和 `app/workers/__main__.py` 的命令行入口；未覆盖真实 LLM/embedding 网络延迟、生产数据库规模、真实教材 PDF/HTML 下载与解析；未测生产部署的多进程启动与流量分布。profile 只对当前测试执行到的路径计时，没有做 line/branch coverage。

### 当前 profile 复跑

测试套件会清理目标数据库中的遗留 `test_*` schema；请继续使用独立的一次性 PostgreSQL 实例。下面命令中的数据库名需以 `onetree_perf` 开头，profile 脚本会拒绝非 loopback 或其他数据库名：

```bash
cd backend
uv run --no-sync python scripts/profile_test_suite.py \
  --database-url "$DATABASE_URL" \
  --output-dir ".codex-artifacts/backend-performance/current-suite-$(date +%Y%m%d-%H%M%S)" \
  --top 150
```

脚本写出二进制 `.prof`、前 150 条全进程累计/自身排名，以及 app/migrations 的完整 `pstats` 列表和全部观测函数 JSON。`DATABASE_URL` 应指向全新本地临时库；不要传项目日常开发库。


## 2026-10-04 第二轮定点优化与复测

本轮仅补齐知识库管理员 Agent 的短事务、上传接口的同步阻塞，以及三组非认证测试的无用播种。上文历史采样及第一轮数据原样保留。

### 基线与环境

- 基线为本轮修改前的工作树，包含第一轮未提交优化；不是干净 Git HEAD。HEAD 仍为 `55b67705fecd21489b2d7bde518760ad19b8175c`。实施前复制 backend 源码并记录文件 SHA-256；测量脚本另行复制进副本，用同一计时和计数逻辑运行。源码摘要与可重建的 `baseline-backend.patch` 保留在本地证据目录。
- macOS arm64、CPython 3.12.14、PostgreSQL 18.6、SQLAlchemy 2.0.50、SQLModel 0.0.38、FastAPI 0.136.3、Starlette 1.2.0、bcrypt 5.0.0、httpx 0.28.1。使用本轮独立 loopback PostgreSQL 临时实例；测试与基准均未写业务数据库。
- HTTP 基准装配项目原有知识库路由、权限依赖、RequestIdMiddleware 和健康路由，使用真实 JWT 与数据库查询；数据为一位无密码管理员、一项已准入来源，教材与缺口初始为空。装配及首轮预热不计入比较。
- Agent 每批 10 路 HTTP SSE，搜索替身等待 50 ms、返回空结果；前后各五批。上传为 1/10/100 MiB 固定合成 bytes、PDF 文件名，前后各五次，文件写入本轮临时目录；没有实际 PDF 解析或外部网络调用。
- HTTP 表格开启 cProfile 与 tracemalloc，报告 wall time；cProfile 只覆盖主线程，移入线程池的 CPU 调用不保证被记录，不能据此推断 CPU 提速。Python 峰值不是 RSS，也不包括采样前创建的原始上传 payload。
- 机器可读结果：[第二轮 JSON](backend-performance-results-20261004-round2.json)。原始 `.prof`、pstats、采样 JSON、测试日志与源码摘要位于本机忽略目录 `backend/.codex-artifacts/backend-performance/round2-20261004/`；代码与数据快照不上传。

### 知识库 Agent

两个 HTTP 入口现在传入绑定应用 engine 的 Session factory。计数、查重和缺口查询分别通过 `run_db_sync` 在当前工作线程完成并关闭 Session，随后才联网搜索或输出事件。计数返回普通字典，缺口返回完整 DTO，搜索结果查重只修改已加载的搜索 DTO。

内部服务仍接受直接 Session：保留调用者未提交数据的可见性，不替调用者提交或回滚。同步生成器、事件顺序、搜索规则和 error payload 保持，路由退出时关闭内层生成器；已经开始的同步搜索仍遵循原有超时。

| 指标 | 修改前 | 修改后 |
| --- | ---: | ---: |
| 10 路批次 wall time 中位数 | 156.108 ms | 160.977 ms |
| 50 个请求合并 p95 | 154.309 ms | 156.994 ms |
| 五批连接累计占用 | 5,199.186 ms | 759.317 ms |
| 每批 SQL | 50 | 50 |

这组收益是连接累计占用减少约 **85.4%**，不是单请求提速；延迟略增，不能声称延迟优化。50 ms 假搜索与空结果亦不代表真实联网搜索成本。单个请求开始搜索时观察的是整个连接池，可能看到其他请求的短查询，不能用该时刻 pool 数量认定它自己持有连接。

新增屏障验收分别覆盖普通与 SSE 两个入口：35 路请求同时等待搜索时，连接占用均为 **0**；健康接口在 2 秒限定内返回；释放屏障后全部完成，无连接遗留。独立 HTTP 基准的 SSE 屏障健康响应约 0.888 ms，只是本机这一批测量，不是生产 SLA。

### 上传响应性

上传仍异步分块读取并校验精确 100 MiB 上限。`bytes.join` 移入线程池；落盘、数据库操作及完整响应 DTO 构造通过 `run_db` 在线程自己的 Session 中执行，请求 Session 和 UploadFile 不跨线程。请求取消不会提前关闭线程正在使用的文件或 Session。

| 上传大小 | 修改前 wall time 中位数 | 修改后 wall time 中位数 | 每次 SQL 前/后 |
| --- | ---: | ---: | ---: |
| 1 MiB | 21.161 ms | 21.643 ms | 7 / 7 |
| 10 MiB | 28.897 ms | 28.395 ms | 7 / 7 |
| 100 MiB | 86.309 ms | 78.050 ms | 7 / 7 |

上述插桩数据没有证明真实上传吞吐改善；目标是消除事件循环阻塞。100 MiB 的 Python 分配峰值前后都约 210 MB，仍保留分块列表再拼接为 bytes 的接口，没有声称降低上传内存。

另外将真实文件 write 暂停在屏障，独立定时线程在 1 秒后兜底释放：旧路由在事件循环中写入，健康探针只能在释放后完成，约 **1,040.169 ms**；新路由在工作线程写入，屏障仍关闭时健康探针已经完成，约 **35.097 ms**，心跳持续推进。这里的探针时间从上传任务启动计时，并包含 30 ms 心跳观察，不是单独的健康请求耗时；它是一项受控阻塞实验，不是磁盘性能数据。

教材和任务仍分次提交。新增回归保留既有边界：任务提交失败时，已提交的教材仍存在；磁盘或首次提交失败时数据库没有新增教材/任务。没有将性能改造扩为持久化原子性重构。

### 非认证测试播种

profile Agent、course resource Agent 和知识库 lifecycle 的 71 处非认证初始化使用 `seed_users=False`；两项依赖演示 UID 的 profile 测试显式建立无密码用户，保留原 UID 和持久化断言。HTTP 登录、注册、演示用户初始化及认证基准继续真实 bcrypt，cost=12 不变。

三个文件固定节点集合，前后各在新进程采样三次，每次 **205 passed**。哈希计数包装原 bcrypt 函数并继续执行真实计算，使用锁覆盖所有工作线程；主线程 `.prof` 的哈希排名不作为完整计数。

| 指标，每批 | 修改前 | 修改后 |
| --- | ---: | ---: |
| `pytest.main` 外围 wall time 中位数 | 21.171 s | 8.573 s |
| 三次 wall time samples | 21.373 / 20.390 / 21.171 s | 8.977 / 8.504 / 8.573 s |
| 实际 bcrypt.hashpw 次数 | 77 | 6 |
| 实际 bcrypt.checkpw 次数 | 2 | 2 |
| 主线程 init_db 次数 | 74 | 74 |
| 主线程 ensure_demo_user 次数 | 74 | 3 |

同一测试集合减少 71 次真实哈希，耗时中位数减少 **12.598 s，约 59.5%**。这是开发/测试效率收益，不能推导生产请求性能。不是把历史全套播种的 42.61 秒全部当作可省时间，也没有改变认证安全成本。

### 复跑与验证

先按上文“复跑”建立全新 loopback 临时 PostgreSQL 实例；数据库名必须以 `onetree_perf` 开头。使用同一依赖，并关闭真实模型与 tracing。输出目录使用新名字，避免覆盖历史证据：

```bash
cd backend
ROUND2_OUT=".codex-artifacts/backend-performance/round2-replay-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$ROUND2_OUT"
uv run --no-sync python scripts/profile_knowledge_base.py \
  --database-url "$DATABASE_URL" --output-dir "$ROUND2_OUT/http" --acceptance
for sample in 1 2 3; do
  uv run --no-sync python scripts/profile_test_suite.py \
    --database-url "$DATABASE_URL" --output-dir "$ROUND2_OUT/fixtures-$sample" -- \
    -q --tb=short tests/test_profile_agent_contract.py \
    tests/test_course_resource_agent_contract.py tests/test_knowledge_base_lifecycle.py
done
uv run --no-sync pytest -q
uv run --no-sync ruff check app scripts tests
uv run --no-sync ruff format --check app scripts tests
```

前版本复跑：将本节 HEAD 的 backend 用 `git archive` 解压到新临时目录，应用本地证据目录的 `baseline-backend.patch`，再将当前 `profile_knowledge_base.py` 和 `profile_test_suite.py` 复制到副本的 scripts。用原工作区 `.venv/bin/python`、副本 backend 工作目录运行相同命令；基线 HTTP 不传 `--acceptance`，35 路屏障是新版本的验收，不是前后延迟比较。所有版本均使用独立一次性数据库，完成后停止实例并清理自己的临时目录。

- 知识库 API、服务和性能回归：**134 passed**；本轮新增回归 **16 项**，覆盖完整事件顺序与 payload、直接 Session 未提交数据、空消息、查询异常、提前关闭、两种入口 35 路并发、上传取消、线程/文件/连接生命周期、大小边界和异常提交。
- 三个 fixture 文件前后三批全部通过，每批 **205 passed**；最终完整后端 **917 passed，112.51 秒**，保留原有一条 Starlette TestClient 弃用 warning。
- Ruff check、format check 与 git diff --check 通过；HTTP/OpenAPI、权限及业务模型没有变化。
- 真实搜索模型、实际网络传输、真实教材解析、生产流量和部署环境仍未验证，合成输入与线程池响应性结果不外推为这些环境的性能收益。
- 未提交、推送或部署。临时数据库、源码副本和上传样本在交付前清理；可复跑脚本、原始 profile、源码摘要及重建 patch 作为本地证据保留。

## 2026-10-07 提交前整理与验证

- 补齐本轮新增数据库 helper 的参数与返回类型标注，清理多余空行。
- 修正 `profile_test_suite.py` 的文本报告筛选：`pstats.print_stats` 使用正则字符串，已编译的正则对象不会生效。合成 profile 验证两个后端排名段均包含后端函数、排除外部函数；历史 JSON 测量数据不变。
- 独立临时 loopback PostgreSQL 实例上完整后端测试：**917 passed，1 warning，114.20 秒**；warning 为现有 Starlette TestClient 弃用提示。
- Ruff check、format 与 `git diff --check` 通过；四个 profiling 脚本 CLI 入口和两份性能结果 JSON 检查通过。本次未重跑前后性能基准，上文性能数据仍属于对应日期的历史测量。
