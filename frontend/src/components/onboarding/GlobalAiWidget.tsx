import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AiGreetingInput } from './AiGreetingInput';
import { useAiWidget } from '../../context/AiWidgetContext';

export function GlobalAiWidget() {
  const { widgetState } = useAiWidget();

  return (
    <AnimatePresence>
      {widgetState !== 'HIDDEN' && (
        <motion.div
          layout
          initial={{ opacity: 0, y: 40 }}
          animate={{
            opacity: 1,
            y: widgetState === 'EXPANDED' ? '-50%' : 0,
            x: widgetState === 'WIDGET' ? 0 : '-50%',
            bottom: widgetState === 'WIDGET' ? 40 : (widgetState === 'EXPANDED' ? 'auto' : '20%'),
            right: widgetState === 'WIDGET' ? 40 : 'auto',
            top: widgetState === 'EXPANDED' ? '50%' : 'auto',
            left: widgetState === 'WIDGET' ? 'auto' : '50%',
            scale: widgetState === 'WIDGET' ? 0.3 : 1
          }}
          exit={{ opacity: 0, y: 40 }}
          transition={{ duration: 1.5, ease: 'easeOut' }}
          style={{ position: 'fixed', zIndex: 99999 }}
        >
          <AiGreetingInput />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
