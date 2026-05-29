# 材质与效果

> 核心方向：柔软纸面、晨光弥散、轻微水汽。材质服务于放松感，不制造冷硬科技感。

---

## 基础材质

| Token | 值 | 用途 |
| --- | --- | --- |
| `--material-paper-base` | `var(--color-background)` | 全局纸面 |
| `--material-paper-raised` | `var(--color-surface-raised)` | 抬升卡片 |
| `--material-paper-inset` | `var(--color-surface-inset)` | 凹槽、轨道、输入底 |
| `--material-dark-panel` | `oklch(18% 0.035 235)` | 深色对比面板 |
| `--material-dark-panel-raised` | `oklch(22% 0.04 235)` | 深色面板高层 |

---

## 晨光与弥散

所有大面积光感必须使用伪元素或独立层实现，动画只允许改变 `transform` 和 `opacity`。

| Token | 值 | 用途 |
| --- | --- | --- |
| `--effect-sun-glow` | `radial-gradient(circle, oklch(84% 0.12 63 / 0.72), oklch(84% 0.12 63 / 0) 68%)` | Hero 晨光 |
| `--effect-peach-glow` | `radial-gradient(circle, oklch(76% 0.12 55 / 0.34), oklch(76% 0.12 55 / 0) 70%)` | 品牌光晕 |
| `--effect-sage-glow` | `radial-gradient(circle, oklch(75% 0.09 135 / 0.28), oklch(75% 0.09 135 / 0) 70%)` | 成功/运行光晕 |
| `--effect-blur-soft` | `blur(32px)` | 小面积弥散 |
| `--effect-blur-sun` | `blur(120px)` | 首屏晨光 |

```css
.ambient-sun {
  position: absolute;
  inset-block-start: calc(var(--space-64) * -1);
  inset-inline-end: calc(var(--space-64) * -1);
  inline-size: calc(var(--space-120) * 5);
  max-inline-size: calc(100% - var(--space-64));
  aspect-ratio: 1;
  border-radius: var(--radius-full);
  background: var(--effect-sun-glow);
  filter: var(--effect-blur-sun);
  opacity: 0.8;
  pointer-events: none;
  animation: ambient-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
}

@keyframes ambient-breathe {
  from { transform: scale(0.96); opacity: 0.66; }
  to { transform: scale(1.04); opacity: 0.86; }
}
```

---

## 纸感纹理

纸感纹理必须非常轻，不能盖过内容。优先使用 CSS 渐变层；如果使用 SVG/PNG 纹理，必须放在本地 assets 中。

```css
.paper-canvas {
  background:
    radial-gradient(circle at 20% 10%, oklch(99% 0.02 80 / 0.42), transparent 32%),
    radial-gradient(circle at 82% 8%, oklch(84% 0.12 63 / 0.24), transparent 34%),
    var(--color-background);
}
```

---

## 轻毛玻璃

毛玻璃只用于浮动导航、弹窗和紧贴内容的轻浮层。禁止大面积强模糊。

| Token | 值 | 用途 |
| --- | --- | --- |
| `--glass-bg` | `oklch(97% 0.02 75 / 0.76)` | 浅色浮层背景 |
| `--glass-dark-bg` | `oklch(20% 0.04 235 / 0.72)` | 深色浮层背景 |
| `--glass-blur` | `blur(12px)` | 轻雾化 |
| `--glass-border` | `oklch(100% 0 0 / 0.42)` | 暖亮边缘 |

```css
.soft-glass {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-md);
  backdrop-filter: var(--glass-blur);
}
```

---

## 品牌渐变

| Token | 值 | 用途 |
| --- | --- | --- |
| `--gradient-paper` | `linear-gradient(135deg, oklch(94% 0.04 73), oklch(97% 0.02 75))` | 纸面背景 |
| `--gradient-coral` | `linear-gradient(135deg, oklch(78% 0.12 55), oklch(72% 0.13 28))` | 主按钮、大 CTA |
| `--gradient-night` | `linear-gradient(135deg, oklch(16% 0.035 235), oklch(22% 0.04 235))` | 暗色面板 |

渐变本身不做动态位移。需要呼吸感时，在渐变层外套一个伪元素，动画只改 `transform` 和 `opacity`。

---

## Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  .ambient-sun,
  .breathing-glow {
    animation: none;
    transform: none;
    opacity: 0.72;
  }
}
```
