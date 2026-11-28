import type { Transition, Variants } from "framer-motion";

export const whisperTransition: Transition = {
	duration: 0.4,
	ease: [0.4, 0, 0.2, 1], // Elegant cubic-bezier as requested
};

export const whisperVariants: Variants = {
	initial: { opacity: 0 },
	animate: { opacity: 1, transition: whisperTransition },
	exit: { opacity: 0, transition: { duration: 0.2, ease: "easeOut" } },
};

/** 呼吸光晕：颜色来自 --shadow-glow-active，只做透明度动画，见 global.css 的 .breathing-glow */
export const breathingGlowClassName = "breathing-glow";

export const actionHintVariants: Variants = {
	rest: {
		opacity: 0,
		x: -8,
		transition: whisperTransition,
	},
	hover: {
		opacity: 1,
		x: 0,
		transition: whisperTransition,
	},
};
