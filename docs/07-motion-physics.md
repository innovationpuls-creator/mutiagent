# 动效 & 物理

> **核心哲学**：全面拥抱绝对放松的慢节奏。没有任何生硬的回弹与弹簧感。一切都如同深水中的浮木、缓慢的呼吸，或是翻开一本散发着墨香的高级杂志。

---

## 一、缓动曲线与时间系统 (Tokens)

我们彻底抛弃了代表“现代高效”的弹簧 (Spring) 和快速响应 (150ms)，所有的曲线均基于极其柔和的贝塞尔曲线，强调**顺滑的减速**和**从容不迫的过渡**。

### 1. 缓动曲线 (Easing)

| Token | 值 | 质感描述 | 适用场景 |
|-------|-----|---------|---------|
| `--ease-editorial` | `cubic-bezier(0.25, 1, 0.5, 1)` | 极致平滑的减速，如同水流缓慢止息，完全无过冲。 | 内容入场、列表浮现、状态流转 |
| `--ease-flip` | `cubic-bezier(0.64, 0, 0.35, 1)` | 前期带有阻滞感，随后顺滑翻转。 | 3D 翻页、共享元素跨页面过渡 |
| `--ease-lazy` | `cubic-bezier(0.33, 1, 0.68, 1)` | 比 editorial 略带一点重量感，但依然柔顺。 | 按钮卡片 Hover，柔和的微交互 |
| `--ease-breathe` | `ease-in-out` | 平稳的起伏，无缝衔接。 | 周期性呼吸动画、背景渐变流转 |

### 2. 时长 (Duration)

| Token | 值 | 质感描述 | 适用场景 |
|-------|-----|---------|---------|
| `--duration-lazy-hover` | `400ms` | 慵懒的悬浮，不急躁。 | 卡片/按钮 Hover、Focus 状态切换 |
| `--duration-reveal` | `800ms` | 如墨迹在宣纸上缓慢晕开定型。 | 页面内容入场、列表逐个浮出 |
| `--duration-flip` | `1200ms` | 厚重纸张翻动的物理感与时间感。 | 页面级别的转场、3D 翻页过渡 |
| `--duration-breathe` | `4000ms` | 极其缓慢的深呼吸周期。 | 背景光晕流动、元素的周期性膨胀 |

---

## 二、四大核心场景与 Keyframes

### 场景一：慵懒微交互 (Lazy Hover)

抛弃了以往通过缩小 (`scale(0.97)`) 模拟的 Haptics 按压震动，因为那太“硬”了。
在这里，Hover 就像**水中的木块被微微托起**，带有极好的浮力感。

```css
/* 卡片和按钮的微交互 */
.interactive-lazy {
  transition: transform var(--duration-lazy-hover) var(--ease-lazy),
              box-shadow var(--duration-lazy-hover) var(--ease-lazy),
              background-color var(--duration-lazy-hover) var(--ease-lazy);
}

.interactive-lazy:hover {
  /* 仅进行极微小的放大，同时阴影变得极其柔和扩散 */
  transform: scale(1.01) translateY(-2px);
  box-shadow: 0 12px 32px var(--shadow-color-soft);
}

.interactive-lazy:active {
  /* 按下时不是硬压缩，而是缓慢回到原位，象征浮力的消退 */
  transform: scale(1) translateY(0);
  box-shadow: 0 4px 12px var(--shadow-color-base);
}
```

### 场景二：杂志感入场 (Editorial Reveal)

元素像从纸面安静浮现，极度克制。纯粹依靠柔和的位移和透明度过渡。

```css
.editorial-reveal {
  opacity: 0;
  /* 极小的位移距离，避免过强的动感 */
  transform: translateY(12px);
}

.editorial-reveal.is-visible {
  opacity: 1;
  transform: translateY(0);
  transition: opacity var(--duration-reveal) var(--ease-editorial),
              transform var(--duration-reveal) var(--ease-editorial);
}

/* 针对列表项的从容交错入场 */
.stagger-list > * {
  opacity: 0;
  transform: translateY(12px);
  transition: opacity var(--duration-reveal) var(--ease-editorial),
              transform var(--duration-reveal) var(--ease-editorial);
}
/* 在 JS 或 CSS 中设置延迟，例如：
   nth-child(1) -> transition-delay: 0ms
   nth-child(2) -> transition-delay: 150ms 
   这里的交错延迟也刻意拉长，增加从容感 */
```

### 场景三：Headspace 标志性呼吸 (Breathing)

背景光晕或核心元素的循环动画。缓慢扩张与收缩，周期性、无缝隙的流转。

```css
.breathing-element {
  animation: breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  /* 推荐搭配温润的渐变色背景或柔软的阴影使用 */
}

@keyframes breathe {
  0% {
    transform: scale(1);
    opacity: 0.85;
  }
  100% {
    transform: scale(1.04);
    opacity: 1;
    /* 配合滤镜效果产生更好的发光质感 */
    filter: brightness(1.05);
  }
}
```

### 场景四：3D 翻页与杂志过渡 (Page Flip)

适用于页面级别的路由切换。像翻开一本精装杂志，利用 3D 透视制造高级感，但不炫技。

```css
/* 翻页动画容器需要设置景深 */
.page-flip-container {
  perspective: 1200px;
  overflow: hidden;
}

.page-flip-enter {
  animation: pageFlipIn var(--duration-flip) var(--ease-flip) both;
  transform-origin: left center;
}

.page-flip-exit {
  animation: pageFlipOut var(--duration-flip) var(--ease-flip) both;
  transform-origin: right center;
}

@keyframes pageFlipIn {
  0% {
    opacity: 0;
    transform: rotateY(15deg) translateX(40px) scale(0.98);
    /* 纸张背光的阴影感 */
    filter: brightness(0.9);
  }
  100% {
    opacity: 1;
    transform: rotateY(0deg) translateX(0) scale(1);
    filter: brightness(1);
  }
}

@keyframes pageFlipOut {
  0% {
    opacity: 1;
    transform: rotateY(0deg) translateX(0) scale(1);
  }
  100% {
    opacity: 0;
    transform: rotateY(-15deg) translateX(-40px) scale(0.98);
  }
}
```

---

## 三、强制降级方案 (Reduced Motion)

考虑到大量慢速动效和透明度变化可能引起的眩晕或对于辅助功能的要求，所有动画必须尊重系统设置。降级后仅保留极致舒缓的透明度渐变，**去除一切位移、缩放与 3D 翻转**。

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    /* 交互动效保留最基本的透明度切换，时长极短 */
    transition: opacity 150ms ease !important;
    transform: none !important;
  }

  /* 入场动画退化为直接显示 */
  .editorial-reveal, .editorial-reveal.is-visible, .stagger-list > * {
    opacity: 1 !important;
    transform: none !important;
    transition: none !important;
  }

  /* 关闭背景的持续呼吸动画 */
  .breathing-element {
    animation: none !important;
    transform: none !important;
    opacity: 1 !important;
  }

  /* 关闭复杂的 3D 翻转 */
  .page-flip-enter, .page-flip-exit {
    animation: none !important;
    transform: none !important;
    opacity: 1 !important;
  }
}
```

---
> **总结提示**：开发组件时，请严格遵守这些 `--duration` 和 `--ease` Token，不要试图“优化”使之变快。设计系统的意图正是要剥离互联网的“效率感”，还给用户一杯下午茶般的时间流逝感。
