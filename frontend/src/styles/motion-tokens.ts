/**
 * Framer Motion token mapping — derived from docs/07-motion-physics.md
 *
 * Usage:
 *   import { motionTokens } from '@/styles/motion-tokens';
 *   <motion.div transition={motionTokens.editorial} />
 */

export const motionTokens = {
	/** 纸面浮现 — 内容入场、列表出现 */
	editorial: { duration: 0.76, ease: [0.25, 1, 0.5, 1] },
	/** 慵懒悬浮 — hover、focus、轻反馈 */
	lazy: { duration: 0.42, ease: [0.33, 1, 0.68, 1] },
	/** 厚纸翻页 — 路由切换、共享元素 */
	route: { duration: 0.98, ease: [0.64, 0, 0.35, 1] },
} as const;

/** 即时反馈持续时间 (秒) — 仅用于必要的可用性反馈 */
export const DURATION_INSTANT = 0.12;
