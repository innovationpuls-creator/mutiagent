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
    // Compressed timeline pacing for a snappier intro (Total ~7.5s)
    const schedule = [
      { delay: 400, phase: 1 },   // Blur in
      { delay: 1000, phase: 2 },  // "你好" in
      { delay: 2200, phase: 3 },  // "你好" out (Stay 1.2s)
      { delay: 2600, phase: 4 },  // "Hello" in (Interval 0.4s)
      { delay: 3800, phase: 5 },  // "Hello" out (Stay 1.2s)
      { delay: 4200, phase: 6 },  // "欢迎来到 one-tree" in (Interval 0.4s)
      { delay: 5700, phase: 7 },  // "欢迎来到 one-tree" out (Stay 1.5s)
      { delay: 6300, phase: 8 },  // 正文 in (Interval 0.6s)
      { delay: 6900, phase: 9 },  // 附注 in
      { delay: 7500, phase: 10 }  // Input in
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

  useEffect(() => {
    if (widgetState === 'WIDGET' || widgetState === 'EXPANDED') {
      onComplete?.();
    }
  }, [widgetState, onComplete]);

  return (
    <motion.div
      initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
      animate={{ opacity: 1, backdropFilter: 'blur(80px)' }}
      exit={{ opacity: 0, backdropFilter: 'blur(0px)' }}
      transition={{ delay: 0.4, duration: 1.2, ease: 'easeInOut' }}
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
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 0.5 } }}
              transition={{ duration: 0.6, ease: 'easeInOut' }}
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
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 0.5 } }}
              transition={{ duration: 0.6, ease: 'easeInOut' }}
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
              exit={{ opacity: 0, filter: 'blur(4px)', transition: { duration: 0.5 } }}
              transition={{ duration: 0.6, ease: 'easeInOut' }}
              style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', fontWeight: 400, color: 'oklch(28% 0.01 60)', letterSpacing: '0.02em', margin: 0 }}
            >
              欢迎来到 <span style={{ fontFamily: 'Caveat, cursive', fontWeight: 600, color: 'oklch(70% 0.12 45)', marginLeft: '8px', fontSize: '42px', transform: 'translateY(2px)', display: 'inline-block' }}>one-tree</span>
            </motion.h1>
          )}
        </AnimatePresence>

        {phase >= 8 && (
          <motion.div
            layout // smoothly transition height changes
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-20)' }}
          >
            <motion.h2 
              layout 
              style={{ fontFamily: 'var(--font-heading)', fontSize: '38px', color: 'oklch(28% 0.01 60)', margin: 0, fontWeight: 400, letterSpacing: '0.02em', lineHeight: 1.38 }}
            >
              在开启旅程之前，想先听听你的声音。
            </motion.h2>
            <AnimatePresence>
              {phase >= 9 && (
                <motion.p
                  layout
                  initial={{ opacity: 0, y: 5 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.8, ease: 'easeOut' }}
                  style={{ fontFamily: 'var(--font-body)', fontSize: '18px', color: 'oklch(55% 0.02 60)', margin: 0, letterSpacing: '0.04em' }}
                >
                  关于你的专业、现在的状态，或是当下的困惑……随便聊聊。
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
