# 本地磁盘清理设计

日期：2026-07-12

## 目标

清理本机可确认不再需要的缓存、历史生成物、重复文件和旧视频版本，同时满足以下条件：

- `/Users/torch/torch/opt/mutiagent` 清理后无需重新安装依赖即可直接启动。
- `/Users/torch/torch/opt/career-planning-agent` 清理后无需重新安装依赖即可直接启动。
- 保留两个项目的源码、未提交改动、环境配置、数据库、依赖目录和锁文件。
- 保留当前视频成片、当前剪辑所需素材及其最短可复现生成链。
- 清理前后记录磁盘占用、删除路径、释放空间和验证结果。

## 当前磁盘基线

- APFS 容器总容量：494.3 GB。
- APFS 容器可用空间：310.6 GB。
- `/System/Volumes/Data` 已用空间：约 145 GiB。
- `/Users/torch` 已读取内容：约 63 GB。macOS 隐私保护阻止读取的目录不计入该数字。
- `/Users/torch/torch/opt/mutiagent`：约 4.8 GB。
- `/Users/torch/torch/opt/career-planning-agent`：约 2.1 GB。

## 不得删除的内容

### 两个项目共同保留

- Git 已跟踪文件。
- 所有未提交修改和未跟踪源码。
- `.git`。
- `.env` 和 `backend/.env`。
- `package.json`、`package-lock.json`、`pyproject.toml` 和 `uv.lock`。
- 前端 `node_modules`，但其中明确的工具缓存除外。
- 后端 `.venv`。
- 后端数据库、向量数据和当前运行数据。

### mutiagent 运行链保留

- `frontend/src`、`frontend/public` 和前端配置文件。
- `backend/app`、`backend/tests` 和后端配置文件。
- `start.sh`。
- `frpc` 和 `frpc.toml`。
- 现有 Git 工作区状态。

### 当前视频保留

- `backend/.codex-artifacts/video-production/final/最终版.mp4`。
- `backend/.codex-artifacts/video-production/raw` 中全部原始素材，但不保留经过 SHA-256 验证的重复副本。
- `backend/.codex-artifacts/video-production/scripts`。
- `backend/.codex-artifacts/video-production/README-HANDOFF.md`。
- 当前生成链使用的以下音频及同名分块目录：
  - `voiceover-00-login-v12.mp3` 与 `segment-00-v12-chunks`。
  - `voiceover-01-architecture-v12.mp3` 与 `segment-01-v12-chunks`。
  - `voiceover-02-03-entry-profile-v4.mp3` 与 `segment-02-03-v4-chunks`。
  - `voiceover-04-draft-agent-v5.mp3` 与 `segment-04-v5-chunks`。
  - `voiceover-05-learning-path-v8.mp3` 与 `segment-05-v8-chunks`。
  - `voiceover-06-outline-admin-evidence-v2.mp3` 与 `segment-06-v2-chunks`。
  - `voiceover-07-resource-generation-v2.mp3` 与 `segment-07-v2-chunks`。
  - `voiceover-08-quiz-generation-v5.mp3` 与 `segment-08-v5-chunks`。
  - `voiceover-09-answer-tutoring-v5.mp3` 与 `segment-09-v5-chunks`。
  - `voiceover-10-pass-feedback-v9.mp3` 与 `segment-10-v9-chunks`。
  - `voiceover-11-growth-tree-v3.mp3` 与 `segment-11-v3-chunks`。
  - `voiceover-11b-admin-overview-v3.mp3` 与 `segment-11b-v3-chunks`。
  - `voiceover-12-ending-v3.mp3` 与 `segment-12-v3-chunks`。
- `backend/.codex-artifacts/video-production/subtitles/onetree-software-cup.zh.v14-segment10-v9.ass`。
- `backend/.codex-artifacts/video-production/work/onetree-v13-no-subtitles.mp4`。
- `backend/.codex-artifacts/video-production/work/onetree-v14-no-subtitles.mp4`。
- `backend/.codex-artifacts/video-production/work/segment-language-join-cuts-v13.json`。
- `backend/.codex-artifacts/video-production/work/final-v13-parts`。
- `backend/.codex-artifacts/video-production/scripts/segment-10-v9.json`。
- `backend/.codex-artifacts/video-production/audio/voiceover-10-pass-feedback-v9.mp3`。
- `backend/.codex-artifacts/video-production/audio/segment-10-v9-chunks`。

当前成片 SHA-256 基线：

`501fa3ff47a80310feccbfafc553c213852f3f71c2747e4746d2fd64c9218d2a`

## 第一阶段：项目内部清理

### mutiagent 前端

删除：

- `frontend/node_modules/.vite`。
- `frontend/dist`。
- `frontend/test-results`。
- `frontend/tsconfig.tsbuildinfo`。

保留 `frontend/e2e`，因为其中包含 Git 已跟踪的测试与截图。

### mutiagent 后端

删除：

- `backend/.pytest_cache`。
- `backend/.ruff_cache`。
- `backend/**/__pycache__`。
- `backend/mutiagent_backend.egg-info`。
- `backend/.codex-artifacts/tts-test`。
- `backend/.codex-artifacts/tts-draft`。
- `backend/.codex-artifacts/tts-draft-v2`。
- `backend/.codex-artifacts/tts-draft-v3`。
- `backend/.codex-artifacts/tts-draft-v4`。
- 空的 `backend/.codex-artifacts/course-resource-real`。
- 空的 `backend/.codex-artifacts/knowledge-base-uploads`。

### mutiagent 视频工程

删除：

- `final` 中除 `最终版.mp4` 外的文件。
- `work` 中除当前视频保留清单外的文件和目录。
- 不属于 `work/final-v13-parts` 的历史预览。当前生成链直接保留 `work/final-v13-parts`，不依赖 `previews/v2`、`previews/v3` 或 `previews/v4`。
- 当前生成链未引用的历史字幕。
- 不在“当前视频保留”精确音频清单中的历史音频和音频分块。
- 视频目录内的日志、`.DS_Store` 和 `__pycache__`。
- 与 `raw/segment-00-login-user-recording.mov` SHA-256 完全相同的 `raw/录屏2026-07-03 15.41.08.mov`。

删除前先生成视频保留清单。每个视频删除路径必须满足以下至少一项：

- 不在保留清单内且不被当前生成链引用。
- 与保留文件的 SHA-256 完全相同。
- 属于明确命名的历史成片、历史预览、历史字幕、历史音频或中间 QA 产物。

### career-planning-agent

保留 `myapp/node_modules`、`backend/.venv`、`backend/data`、`backend/qdrant-bin`、环境配置和全部源码。

删除：

- `.DS_Store`。
- `.pytest_cache`。
- `backend/.mypy_cache`。
- `backend/.pytest_cache`。
- `backend/.ruff_cache`。
- `backend/**/__pycache__`。
- `myapp/dist`。
- `myapp/coverage`。
- `myapp/artifacts`。
- `myapp/playwright-report`。
- `myapp/test-results`。
- 根目录 `test-results`。
- `myapp/.umi`。
- `myapp/.umi-production`。
- `myapp/.umi-test`。
- `myapp/docs`。
- `.playwright-mcp`。
- `.superpowers`。
- 空的 `models`。

不删除 `行业数据`、`scripts`、`CODE_SPEC_ALIGNMENT.md`、Git 已跟踪的 `docs` 或任何未提交内容。

## 第二阶段：用户级缓存与大型应用数据审查

项目内部清理完成并验证后，再逐项审查以下路径。没有精确内容清单和影响判断时不得删除：

- `/Users/torch/.cache`：约 5.9 GB。
- `/Users/torch/Library/Caches`：约 7.1 GB。
- `/Users/torch/.lmstudio`：约 8.3 GB，其中模型约 6.4 GB。
- `/Users/torch/Library/Containers/com.docker.docker`：约 8.5 GB。
- `/Users/torch/.codex`：约 3.6 GB。
- `/Users/torch/Downloads`：约 1.4 GB。

Docker daemon 当前未运行。启动 Docker 并取得镜像、容器、卷和构建缓存的精确清单前，不删除 Docker 数据。

## 执行记录

每一阶段都记录：

1. 执行时间。
2. 删除前路径及字节数。
3. 删除的精确路径。
4. 删除后路径及字节数。
5. APFS 可用空间变化。
6. Git 状态前后对比。
7. 项目启动与健康检查结果。
8. 视频哈希和解码检查结果。

执行记录保存为：

`docs/superpowers/specs/2026-07-12-local-disk-cleanup-record.md`

## 验证

### 文件安全

- 清理前后分别保存两个仓库的 `git status --short`。
- 清理后不得新增 Git 已跟踪文件删除记录。
- 清理后不得丢失现有未提交文件。

### mutiagent

- `start.sh` 能启动后端、前端和 frpc。
- `http://127.0.0.1:5173` 可访问。
- `http://127.0.0.1:8000/api/health` 返回成功。
- 前端现有依赖无需重新安装。
- 后端现有依赖无需重新安装。

### career-planning-agent

- 后端使用现有 `.venv` 完成导入检查。
- 前端使用现有 `node_modules` 完成启动或构建检查。
- 本地数据库和 Qdrant 数据保持存在。

### 视频

- `最终版.mp4` SHA-256 与基线一致。
- `ffmpeg` 完整解码无错误。
- 当前生成链保留文件全部存在。
- 原始素材除完全重复副本外全部存在。

## 停止条件

出现以下任一情况立即停止当前阶段，不继续删除：

- 删除路径不在本设计或执行计划中。
- 路径是否被当前代码、配置或视频生成链使用无法从文件中确认。
- Git 状态出现新的已跟踪文件删除或现有修改丢失。
- 项目无法使用现有依赖恢复启动。
- 当前视频哈希发生变化或完整解码失败。
