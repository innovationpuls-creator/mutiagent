# 深色面板 & Chat 专用 Token

> 扩展 `01-颜色系统.md`，为 Chat UI 的深色面板、状态色和组件专用色提供补充 Token。所有值使用 OKLCH。

---

## 深色面板底色

用于 Progress Card、Result Card、Sidebar（generating 阶段）的深色渐变面板。

| Token | 值 | 用途 |
|-------|-----|------|
| `--dark-surface` | `oklch(22% 0.02 210)` | 深色面板底色（渐变起始） |
| `--dark-surface-2` | `oklch(25% 0.02 210)` | 深色面板渐变中间色 |
| `--dark-surface-3` | `oklch(28% 0.02 210)` | 深色面板渐变终止色 |
| `--dark-divider` | `oklch(100% 0 0 / 0.06)` | 深色面板内行分隔线 |

---

## 深色面板文字

替代 Tailwind `text-white/70` 等原始 opacity 工具类。

| Token | 值 | 用途 |
|-------|-----|------|
| `--dark-text-secondary` | `oklch(100% 0 0 / 0.7)` | 深色面板次要文字（文件名、标签） |
| `--dark-text-tertiary` | `oklch(100% 0 0 / 0.35)` | 深色面板辅助文字（进度百分比） |
| `--dark-text-badge` | `oklch(100% 0 0 / 0.5)` | 深色面板 Badge 数字 |

---

## 深色面板交互

| Token | 值 | 用途 |
|-------|-----|------|
| `--dark-highlight` | `oklch(100% 0 0 / 0.04)` | 行 hover / active agent 高亮 |
| `--dark-highlight-hover` | `oklch(100% 0 0 / 0.1)` | Count badge 背景 |
| `--dark-track-bg` | `oklch(100% 0 0 / 0.05)` | 进度条 Track 背景 |

---

## 状态色（实心不透明，深色背景专用）

**关键规则**：深色背景上的状态色必须是 100% 不透明实心色，禁止 `rgba(x,x,x,0.2)` 半透明填充。

| Token | 值 | 状态 | 形状 |
|-------|-----|------|------|
| `--sage` | `oklch(78% 0.08 145)` | Running | ● 实心圆 |
| `--soft-peach` | `oklch(85% 0.08 60)` | Waiting | ○ 空心圆 |
| `--lavender` | `oklch(75% 0.06 290)` | Neutral | ◆ 实心菱形 |

来源：`docs/session-desgin.md` "Physical Toys" 指令——Active Sage Green、Idle Soft Peach、Neutral Muted Lavender。

---

## Chat 组件专用色

| Token | 值 | 用途 |
|-------|-----|------|
| `--color-user-bubble` | `oklch(92% 0.03 290 / 0.3)` | 用户消息气泡底色（淡紫 mist） |
| `--color-cursive-accent` | `oklch(72% 0.14 45)` | Caveat 手写情感词颜色（暖桃） |
| `--color-card-overlay` | `oklch(96% 0.01 80 / 0.5)` | 结构化选择卡外层叠加底色 |

---

## 暗色模式

深色面板 Token（`--dark-surface`、`--sage`、`--soft-peach`、`--lavender`）在暗色模式下保持不变——它们已经是深色系。

Chat 组件专用色的暗色映射见 `superpowers/specs/2026-05-28-multi-agent-chat-ui-design.md` Section 15。
