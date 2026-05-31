import React, { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAiWidget } from '../../context/AiWidgetContext';

interface Props {
  onComplete?: () => void;
}

export function SproutInitOverlay({ onComplete }: Props) {
  const [phase, setPhase] = useState<number>(0);
  const { widgetState, setWidgetState } = useAiWidget();

  useEffect(() => {
    // Exact timeline pacing mapped from design spec
    const schedule = [
      { delay: 800, phase: 1 },  // Blur in
      { delay: 2300, phase: 2 }, // "你好" in
      { delay: 4300, phase: 3 }, // "你好" out
      { delay: 5300, phase: 4 }, // "Hello" in
      { delay: 7300, phase: 5 }, // "Hello" out
      { delay: 8300, phase: 6 }, // "欢迎来到 one-tree" in
      { delay: 10800, phase: 7 }, // "欢迎来到 one-tree" out
      { delay: 12300, phase: 8 }, // 正文 in
      { delay: 13300, phase: 9 }, // 附注 in
      { delay: 14300, phase: 10 } // Input in
    ];

    const timeouts = schedule.map(({ delay, phase: p }) => 
      setTimeout(() => {
        setPhase(p);
        if (p === 10) {
          setWidgetState('CENTER_INPUT');
        }
      }, delay)
    );

    return () => timeouts.forEach(clearTimeout);
  }, [setWidgetState]);

  // Hide the overlay completely when widget minimizes or expands if desired,
  // or keep the blur while in CENTER_INPUT.
  if (widgetState === 'WIDGET' || widgetState === 'EXPANDED') return null;

  return (
    <motion.div
      initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
      animate={{ opacity: 1, backdropFilter: 'blur(80px)' }}
      transition={{ delay: 0.8, duration: 1.5, ease: 'easeInOut' }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 9999,
        backgroundColor: 'oklch(var(--color-bg-glass, 98% 0.01 70) / 0.4)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center'
      }}
    >
      <div style={{ position: 'absolute', top: '40%', transform: 'translateY(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
        <AnimatePresence mode="wait">
          {phase >= 2 && phase < 3 && (
            <motion.h1
              key="t1"
              initial={{ opacity: 0, filter: 'blur(4px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 1.5 } }}
              transition={{ duration: 1, ease: 'easeInOut' }}
              style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', fontWeight: 400, color: 'oklch(28% 0.01 60)', letterSpacing: '0.02em', margin: 0 }}
            >
              你好
            </motion.h1>
          )}
          {phase >= 4 && phase < 5 && (
            <motion.h1
              key="t2"
              initial={{ opacity: 0, filter: 'blur(4px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 1.5 } }}
              transition={{ duration: 1, ease: 'easeInOut' }}
              style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', fontWeight: 400, color: 'oklch(28% 0.01 60)', letterSpacing: '0.02em', margin: 0 }}
            >
              Hello
            </motion.h1>
          )}
          {phase >= 6 && phase < 7 && (
            <motion.h1
              key="t3"
              initial={{ opacity: 0, filter: 'blur(4px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 1.5 } }}
              transition={{ duration: 1, ease: 'easeInOut' }}
              style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', fontWeight: 400, color: 'oklch(28% 0.01 60)', letterSpacing: '0.02em', margin: 0 }}
            >
              欢迎来到 <span style={{ fontFamily: 'Caveat, cursive', fontWeight: 600, color: 'oklch(70% 0.12 45)', marginLeft: '8px', fontSize: '42px', transform: 'translateY(2px)', display: 'inline-block' }}>one-tree</span>
            </motion.h1>
          )}
        </AnimatePresence>

        {phase >= 8 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 1, ease: 'easeInOut' }}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-20)' }}
          >
            <h2 style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', color: 'oklch(28% 0.01 60)', margin: 0, fontWeight: 400, letterSpacing: '0.02em', lineHeight: 1.38 }}>
              在开启旅程之前，想先听听你的声音。
            </h2>
            {phase >= 9 && (
              <motion.p
                initial={{ opacity: 0, y: 5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 1.5, ease: 'easeInOut' }}
                style={{ fontFamily: 'var(--font-body)', fontSize: '18px', color: 'oklch(55% 0.02 60)', margin: 0, letterSpacing: '0.04em' }}
              >
                关于你的专业、现在的状态，或是当下的困惑……随便聊聊。
              </motion.p>
            )}
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
