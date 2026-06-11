import { useEffect, useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { motionTokens, DURATION_INSTANT } from '../../styles/motion-tokens';

interface Props {
  onComplete?: () => void;
}

export function PathInitOverlay({ onComplete }: Props) {
  const [phase, setPhase] = useState<number>(0);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion) {
      setPhase(2);
      return;
    }
    const t1 = setTimeout(() => setPhase(1), 1200); // 概要文本淡入
    const t2 = setTimeout(() => setPhase(2), 2800); // 按钮滑入
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [reduceMotion]);

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={reduceMotion ? { duration: DURATION_INSTANT } : motionTokens.route}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        backgroundColor: 'oklch(97% 0.02 75 / 0.45)',
        backdropFilter: 'blur(56px)',
        WebkitBackdropFilter: 'blur(56px)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        textAlign: 'center',
      }}
    >
      <div style={{ maxWidth: '600px', padding: '0 var(--space-24)' }}>
        <motion.h1
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={motionTokens.editorial}
          style={{
            fontFamily: 'var(--font-heading)',
            fontSize: '32px',
            color: 'oklch(28% 0.01 60)',
            fontWeight: 400,
            margin: '0 0 var(--space-24) 0',
          }}
        >
          你的自适应学习路径已顺利编织完成。
        </motion.h1>

        <AnimatePresence>
          {phase >= 1 && (
            <motion.p
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={motionTokens.editorial}
              style={{
                fontFamily: 'var(--font-body)',
                fontSize: '18px',
                color: 'oklch(55% 0.02 60)',
                lineHeight: 1.8,
                margin: '0 0 var(--space-32) 0',
              }}
            >
              系统已根据你的画像基础，为你自动<strong>剪枝精简了 2 门</strong>已知的基础课程，并针对你的薄弱点<strong>融入了 1 门</strong>专项强化课。
            </motion.p>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {phase >= 2 && (
            <motion.button
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={motionTokens.lazy}
              onClick={onComplete}
              style={{
                padding: 'var(--space-12) var(--space-32)',
                borderRadius: 'var(--radius-full)',
                background: 'var(--color-primary)',
                color: 'var(--color-text-inverse)',
                fontFamily: 'var(--font-body)',
                fontSize: '16px',
                fontWeight: 'var(--font-weight-medium)',
                border: 'none',
                cursor: 'pointer',
                boxShadow: 'var(--shadow-md)',
              }}
            >
              开始第一门课
            </motion.button>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
