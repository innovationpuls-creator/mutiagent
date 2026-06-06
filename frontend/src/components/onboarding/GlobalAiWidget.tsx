import React, { useEffect } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { AiGreetingInput } from './AiGreetingInput';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';

const CENTER_INPUT_OFFSET = 'min(25vh, calc(var(--space-120) + var(--space-96)))';

export function GlobalAiWidget() {
  const { widgetState, setWidgetState, clearPendingMessage } = useAiWidget();
  const { token } = useAuth();
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (token) return;
    clearPendingMessage();
    setWidgetState('HIDDEN');
  }, [clearPendingMessage, setWidgetState, token]);

  useEffect(() => {
    if (!token || widgetState !== 'HIDDEN' || typeof window === 'undefined') {
      return;
    }

    const url = new URL(window.location.href);
    const sessionId = url.searchParams.get('session_id');
    if (url.pathname === '/sprout' && typeof sessionId === 'string' && sessionId.trim()) {
      setWidgetState('EXPANDED');
    }
  }, [setWidgetState, token, widgetState]);

  return (
    <>
      <AnimatePresence>
        {widgetState === 'EXPANDED' && (
          <motion.div
            data-testid="global-ai-widget-overlay"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={reduceMotion ? { duration: 0 } : { duration: 0.98, ease: [0.25, 1, 0.5, 1] }}
            style={{
              position: 'fixed',
              inset: 0,
              zIndex: 9998,
              backgroundColor: 'var(--color-overlay)',
              backdropFilter: 'var(--glass-blur)',
              pointerEvents: 'auto',
            }}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {widgetState !== 'HIDDEN' && token && (
          <motion.div
            data-testid="global-ai-widget-shell"
            initial={reduceMotion ? false : { opacity: 0, y: 40 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 40 }}
            transition={reduceMotion ? { duration: 0 } : { duration: 0.98, ease: [0.64, 0, 0.35, 1] }}
            style={{
              position: 'fixed',
              inset: 0,
              pointerEvents: 'none',
              zIndex: 99999,
              display: 'flex',
              justifyContent: widgetState === 'WIDGET' ? 'flex-end' : 'center',
              alignItems: widgetState === 'WIDGET' ? 'flex-end' : 'center',
              padding: widgetState === 'WIDGET' ? 'var(--space-40)' : '0',
            }}
          >
            <div
              data-testid="global-ai-widget-frame"
              style={{
              pointerEvents: 'auto',
                transform: widgetState === 'CENTER_INPUT' ? `translateY(${CENTER_INPUT_OFFSET})` : 'translateY(0)',
                transition: reduceMotion
                  ? 'none'
                  : 'transform var(--duration-route) var(--ease-editorial)',
              }}
            >
              <AiGreetingInput />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
