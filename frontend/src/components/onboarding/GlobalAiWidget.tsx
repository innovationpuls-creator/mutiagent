import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AiGreetingInput } from './AiGreetingInput';
import { useAiWidget } from '../../context/AiWidgetContext';

export function GlobalAiWidget() {
  const { widgetState } = useAiWidget();

  return (
    <>
      <AnimatePresence>
        {widgetState === 'EXPANDED' && (
          <motion.div
            initial={{ opacity: 0, backdropFilter: 'blur(0px)' }}
            animate={{ opacity: 1, backdropFilter: 'blur(80px)' }}
            exit={{ opacity: 0, backdropFilter: 'blur(0px)' }}
            transition={{ duration: 1.5, ease: 'easeInOut' }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9998,
              backgroundColor: 'oklch(var(--color-bg-glass, 98% 0.01 70) / 0.4)',
              pointerEvents: 'auto'
            }}
          />
        )}
      </AnimatePresence>
      
      <AnimatePresence>
        {widgetState !== 'HIDDEN' && (
          <motion.div
            initial={{ opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 40 }}
            transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            style={{
              position: 'fixed',
              inset: 0,
              pointerEvents: 'none',
              zIndex: 99999,
              display: 'flex',
              // Base centering for both EXPANDED and CENTER_INPUT, flex-end for WIDGET
              justifyContent: widgetState === 'WIDGET' ? 'flex-end' : 'center',
              alignItems: widgetState === 'WIDGET' ? 'flex-end' : 'center',
              padding: widgetState === 'WIDGET' ? '40px' : '0'
            }}
          >
            <div style={{ 
              pointerEvents: 'auto',
              // Push it down by 25vh only in CENTER_INPUT state so it doesn't occlude text
              marginTop: widgetState === 'CENTER_INPUT' ? '25vh' : '0',
              transition: 'margin-top 1.2s cubic-bezier(0.16, 1, 0.3, 1)'
            }}>
              <AiGreetingInput />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
