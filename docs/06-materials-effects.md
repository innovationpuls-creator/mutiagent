# 材质 & 效果

> **核心哲学**：移除一切赛博朋克式的高强度 Neon Glow。Headspace 的材质是流动的、呼吸的。我们使用极度柔和的渐变底色，它们会像慢镜头的晚霞一样缓慢流转。

---

## 呼吸渐变背景 (Breathing Gradients)

不再使用生硬的单色或短促的渐变。页面的 Hero 区域或者卡片背景，应当使用 `radial-gradient` 或平缓的 `linear-gradient`，并在多种暖色之间进行缓慢的漂移。

### Token 定义

| Token | 值 | 质感描述 |
|-------|-----|---------|
| `--gradient-peach-sunrise` | `linear-gradient(135deg, oklch(93% 0.05 70), oklch(96% 0.03 70))` | 桃色日出，极度柔和的同色系渐变。 |
| `--gradient-coral-sunset` | `linear-gradient(135deg, oklch(76% 0.12 55), oklch(70% 0.14 25))` | 珊瑚夕阳，品牌色与鲑鱼粉的温暖碰撞，用于重色块背景。 |
| `--gradient-night-sky` | `linear-gradient(135deg, oklch(25% 0.04 240), oklch(30% 0.05 240))` | 用于暗色模式的深鸭蓝渐变。 |

### 色彩漂移动画 (Color Drift)

配合 `07-motion-physics.md` 中的 `--duration-breathe`，我们可以让背景产生呼吸感。

```css
.breathing-bg {
  /* 扩大背景尺寸以便移动 */
  background: linear-gradient(135deg, var(--color-background), var(--color-surface), var(--color-background));
  background-size: 200% 200%;
  /* 4s - 8s 的极长周期 */
  animation: bgDrift 8s ease-in-out infinite alternate;
}

@keyframes bgDrift {
  0% { background-position: 0% 50%; }
  100% { background-position: 100% 50%; }
}
```

---

## 材质：告别高强度毛玻璃

虽然 Apple 喜欢重度毛玻璃 (Glassmorphism)，但那往往显得冰冷且科技感过强。在 Warm Humanist 风格中，如果必须使用叠加层，我们更倾向于**半透明的实色**或**非常轻微的模糊**。

| Token | 值 | 质感描述 |
|-------|-----|---------|
| `--overlay-blur` | `blur(8px)` | 轻微的模糊，仿佛隔着一层水汽，而不是厚重的磨砂玻璃。 |
| `--overlay-bg` | `oklch(93% 0.05 70 / 0.8)` | 带有暖桃色倾向的半透明遮罩。 |

```css
/* 浮动导航栏或弹窗背景 */
.soft-overlay {
  background: var(--overlay-bg);
  backdrop-filter: var(--overlay-blur);
  -webkit-backdrop-filter: var(--overlay-blur);
  /* 拒绝生硬的 border，使用极其柔和的光晕代替 */
  box-shadow: 0 4px 24px oklch(76% 0.12 55 / 0.05);
}
```

---

## 发光效果 (Glows)

绝不使用刺眼的蓝色或紫色发光。所有的光晕都应该是温暖的、面积巨大的、极度稀释的。

```css
/* Hero 区域背后的温暖光晕 */
.hero-ambient-glow {
  position: absolute;
  width: 600px; /* 极大的面积 */
  height: 600px;
  background: radial-gradient(circle, oklch(76% 0.12 55 / 0.1), transparent 60%);
  filter: blur(80px); /* 极度的弥散 */
  pointer-events: none;
  /* 配合呼吸动画 */
  animation: breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
}
```

> **性能提示**：大面积的 `blur` 如果配合动画，必须加上 `will-change: transform, opacity;` 或者尽量避免在主线程繁杂时运行。在 `prefers-reduced-motion: reduce` 时，应直接关闭该层以确保性能和避免眩晕。
