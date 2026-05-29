# Session 开发规范

> 所有 session 类界面必须遵守 Headspace meditation 风格：温暖、柔和、触感明确、有呼吸感。目标不是标准 SaaS chat，而是高品质的平静工具。

---

## 1. 画布与全局光线

- 页面基础使用 `--color-background` 或 `--gradient-paper`。
- 首屏可加入晨光层，但必须来自 `--effect-sun-glow`，并通过独立伪元素实现。
- 深色面板使用 `--dark-surface`、`--dark-surface-raised`，只作为对比区域。
- 光晕和纸感纹理不能遮挡文字，不能造成横向滚动。

---

## 2. 容器物理

- 主容器使用 `--radius-lg` 或 `--radius-xl`。
- 按钮、状态 pill、头像使用 `--radius-full`。
- 主卡片 padding 最低使用 `--space-40`；移动端最低使用 `--space-24`。
- 阴影必须使用 `--shadow-sm/md/lg` 多层 token，不写临时 box-shadow。

---

## 3. 字体与符号

- 全部文字使用 LXGW WenKai。
- 禁止引入额外圆体、手写体、Google Fonts。
- 情绪词不使用外部手写字体；可通过 `--color-primary`、`--text-h*` 和留白强调。
- 不用 emoji 作为图标。
- 图标优先使用低密度、单色、几何化符号，如 `*`、`//`、`+`；需要真实图标时使用 lucide 单色线性图标。

---

## 4. 微控件与数据可视化

深色背景上的控件必须清晰、实心、可触摸：

- Running 使用 `--status-running`。
- Waiting 使用 `--status-waiting`。
- Neutral 使用 `--status-neutral`。
- Error 使用 `--status-error`。

禁止用低透明度填充模拟状态色。进度条和滑块按 `08-dark-panel-tokens.md` 的 Pill-in-Pill 与 Groove & Pebble 规范实现。

---

## 5. Session 页面结构

推荐结构：

1. 顶部轻导航：返回、标题、状态。
2. 主工作区：当前 session 内容或对话流。
3. 侧向或底部状态面板：任务、进度、运行状态。
4. 输入区或行动区：主要操作始终清晰可见。
5. 反馈层：toast、modal、error panel。

移动端优先保持单列，状态面板可折叠到底部抽屉。

---

## 6. 状态覆盖

每个 session 必须定义：

- idle
- running
- waiting
- completed
- empty
- error
- disabled

状态切换只动 `transform` 和 `opacity`，并提供 reduced-motion 降级。

---

## 7. 禁止事项

- 禁止 HEX/RGB 硬编码。
- 禁止低透明度白色糊在深色面板上。
- 禁止尖角、薄进度线、冷灰阴影。
- 禁止廉价彩色图标和 emoji 装饰。
- 禁止为了“看起来丰富”伪造数据、统计、用户反馈。
