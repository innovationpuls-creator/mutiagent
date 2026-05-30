import type { Variants } from 'framer-motion';

export const whisperTransition = {
  duration: 0.4,
  ease: [0.4, 0, 0.2, 1], // Elegant cubic-bezier as requested
};

export const whisperVariants: Variants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: whisperTransition },
  exit: { opacity: 0, transition: { duration: 0.2, ease: 'easeOut' } },
};

export const breathingGlowVariants: Variants = {
  animate: {
    boxShadow: [
      '0 0 0px 0px rgba(244, 199, 163, 0)',     /* No glow */
      '0 0 16px 4px rgba(244, 199, 163, 0.4)',   /* Soft pulse of --color-intent-active */
      '0 0 0px 0px rgba(244, 199, 163, 0)'
    ],
    transition: {
      duration: 4.2, // Matches var(--duration-breathe)
      repeat: Infinity,
      ease: 'easeInOut'
    }
  }
};

export const actionHintVariants: Variants = {
  rest: { 
    opacity: 0, 
    x: -8,
    transition: whisperTransition
  },
  hover: { 
    opacity: 1, 
    x: 0,
    transition: whisperTransition
  }
};
