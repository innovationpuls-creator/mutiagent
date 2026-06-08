import React, { useEffect } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { AiGreetingInput } from './AiGreetingInput';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';

const CENTER_INPUT_OFFSET = 'min(25vh, calc(var(--space-120) + var(--space-96)))';
const SPROUT_INIT_OVERLAY_KEY = 'mutiagent-sprout-init-overlay';
type ExpandedLayout = 'centered' | 'docked';

function getExpandedLayout(): ExpandedLayout {
  if (typeof window === 'undefined') {
    return 'centered';
  }
  return window.location.pathname === '/sprout' ? 'docked' : 'centered';
}

function getCurrentUrl(): URL | null {
  if (typeof window === 'undefined') {
    return null;
  }

  return new URL(window.location.href);
}

function hasPendingSproutInitOverlay(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    return window.sessionStorage.getItem(SPROUT_INIT_OVERLAY_KEY) === '1'
      || document.querySelector('[data-sprout-init-overlay="true"]') !== null;
  } catch {
    return document.querySelector('[data-sprout-init-overlay="true"]') !== null;
  }
}

export function GlobalAiWidget() {
  const { widgetState, setWidgetState, clearPendingMessage } = useAiWidget();
  const { token } = useAuth();
  const reduceMotion = useReducedMotion();
  const expandedLayout = getExpandedLayout();
  const isDockedExpanded = widgetState === 'EXPANDED' && expandedLayout === 'docked';
  const shouldDockToBottomRight = widgetState === 'WIDGET' || isDockedExpanded;

  useEffect(() => {
    if (!token) {
      clearPendingMessage();
      if (widgetState !== 'HIDDEN') {
        setWidgetState('HIDDEN');
      }
      return;
    }

    if (widgetState !== 'HIDDEN') {
      return;
    }

    const url = getCurrentUrl();
    if (!url) {
      return;
    }

    const sessionId = url.searchParams.get('session_id');
    if (url.pathname === '/sprout' && typeof sessionId === 'string' && sessionId.trim()) {
      setWidgetState('EXPANDED');
      return;
    }

    if (hasPendingSproutInitOverlay() || url.pathname === '/sprout') {
      return;
    }

    setWidgetState('WIDGET');
  }, [clearPendingMessage, setWidgetState, token, widgetState]);

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
              pointerEvents: 'none',
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
              justifyContent: shouldDockToBottomRight ? 'flex-end' : 'center',
              alignItems: shouldDockToBottomRight ? 'flex-end' : 'center',
              padding: widgetState === 'WIDGET'
                ? 'var(--space-40)'
                : isDockedExpanded
                  ? 'var(--space-24)'
                  : '0',
            }}
          >
            <div
              data-testid="global-ai-widget-frame"
              data-expanded-layout={isDockedExpanded ? 'docked' : 'centered'}
              style={{
                pointerEvents: 'auto',
                transform: widgetState === 'CENTER_INPUT' ? `translateY(${CENTER_INPUT_OFFSET})` : 'translateY(0)',
                transition: reduceMotion
                  ? 'none'
                  : 'transform var(--duration-route) var(--ease-editorial)',
              }}
            >
              <AiGreetingInput expandedLayout={expandedLayout} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
