import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import type { AgentRunStep, MessageStatus } from '../../types/chat';
import { CollapsedBar } from './CollapsedBar';
import { ExpandedLog } from './ExpandedLog';
import { StatusBar } from './StatusBar';
import { formatStepTitle } from './stepLabels';

const COLLAPSE_DELAY_MS = 2000;

interface AgentRunTimelineProps {
  steps?: AgentRunStep[];
  status: MessageStatus;
}

function getCollapsedLabel(steps: AgentRunStep[]): string {
  const representativeStep =
    [...steps].reverse().find((step) => step.kind === 'answer')
    ?? [...steps].reverse().find((step) => step.kind === 'agent')
    ?? [...steps].reverse().find((step) => step.status === 'running')
    ?? steps[steps.length - 1];

  return representativeStep ? formatStepTitle(representativeStep) : '多智能体流程';
}

export function AgentRunTimeline({ steps = [], status }: AgentRunTimelineProps) {
  const [expanded, setExpanded] = useState(false);
  const [timelineNow, setTimelineNow] = useState(() =>
    typeof performance !== 'undefined' ? performance.now() : Date.now(),
  );
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualExpandedRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return;

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
    const updatePreference = (event?: MediaQueryListEvent) => {
      setPrefersReducedMotion(event?.matches ?? mediaQuery.matches);
    };

    updatePreference();

    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', updatePreference);
      return () => mediaQuery.removeEventListener('change', updatePreference);
    }

    mediaQuery.addListener(updatePreference);
    return () => mediaQuery.removeListener(updatePreference);
  }, []);

  useEffect(() => {
    if (status !== 'streaming' && status !== 'pending') return;

    const updateNow = () => {
      setTimelineNow(typeof performance !== 'undefined' ? performance.now() : Date.now());
    };

    updateNow();
    const timer = setInterval(updateNow, 120);
    return () => clearInterval(timer);
  }, [status]);

  useEffect(() => {
    if (status === 'streaming' || status === 'pending') {
      manualExpandedRef.current = false;
      if (collapseTimerRef.current) {
        clearTimeout(collapseTimerRef.current);
        collapseTimerRef.current = null;
      }
      setExpanded(true);
    }
  }, [status]);

  useEffect(() => {
    if (status === 'completed' && expanded && !manualExpandedRef.current) {
      collapseTimerRef.current = setTimeout(() => {
        setExpanded(false);
        collapseTimerRef.current = null;
      }, COLLAPSE_DELAY_MS);
    }
    return () => {
      if (collapseTimerRef.current) {
        clearTimeout(collapseTimerRef.current);
        collapseTimerRef.current = null;
      }
    };
  }, [status, expanded]);

  const handleManualExpand = () => {
    manualExpandedRef.current = true;
    if (collapseTimerRef.current) {
      clearTimeout(collapseTimerRef.current);
      collapseTimerRef.current = null;
    }
    setExpanded(true);
  };

  const timelineSteps = useMemo(
    () => steps.map((step) => {
      if (step.status !== 'running' || typeof step.startedAtMs !== 'number') return step;
      return {
        ...step,
        durationMs: Math.max(timelineNow - step.startedAtMs, 0),
      };
    }),
    [steps, timelineNow],
  );

  const collapsedLabel = useMemo(
    () => getCollapsedLabel(timelineSteps),
    [timelineSteps],
  );

  const runStatus = useMemo(() => {
    if (status === 'error') return 'failed';
    const failed = timelineSteps.find((s) => s.status === 'error');
    if (failed) return 'failed';
    if (status === 'streaming' || status === 'pending') return 'running';
    const running = timelineSteps.find((s) => s.status === 'running');
    if (running) return 'running';
    return 'completed';
  }, [status, timelineSteps]);

  const stepCount = timelineSteps.length;
  const timingBounds = timelineSteps.reduce(
    (bounds, step) => {
      if (typeof step.startedAtMs !== 'number' || !Number.isFinite(step.startedAtMs)) {
        return bounds;
      }
      const durationMs = typeof step.durationMs === 'number' && Number.isFinite(step.durationMs)
        ? step.durationMs
        : 0;
      const stepEndMs = step.startedAtMs + durationMs;
      return {
        earliest: bounds.earliest === null ? step.startedAtMs : Math.min(bounds.earliest, step.startedAtMs),
        latest: bounds.latest === null ? stepEndMs : Math.max(bounds.latest, stepEndMs),
      };
    },
    { earliest: null as number | null, latest: null as number | null },
  );
  const totalMs = timingBounds.earliest !== null && timingBounds.latest !== null
    ? Math.max(timingBounds.latest - timingBounds.earliest, 0)
    : 0;
  const durationText =
    totalMs > 0
      ? totalMs < 1000
        ? `${Math.round(totalMs)}ms`
        : `${(totalMs / 1000).toFixed(totalMs < 10000 ? 1 : 0)}s`
      : '';

  const currentStep = [...timelineSteps].reverse().find((s) => s.status === 'running');
  const statusText = currentStep
    ? currentStep.summary ?? currentStep.title
    : runStatus === 'running'
      ? '智能体处理中'
      : '';

  if (steps.length === 0) return null;

  return (
    <Shell aria-label="Agent run timeline" data-surface="warm-paper">
      <AnimatePresence mode="wait">
        {expanded ? (
          <motion.div
            key="expanded"
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 'calc(var(--space-4) * -1)' }}
            animate={{ opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 'var(--space-4)' }}
            transition={prefersReducedMotion ? { duration: 0.12 } : { duration: 0.3, ease: [0.25, 1, 0.5, 1] }}
          >
            <ExpandedLog steps={timelineSteps} />
            <StatusBar
              text={statusText}
              time={runStatus === 'running' ? durationText : undefined}
              status={runStatus === 'running' ? 'running' : 'done'}
              onClick={() => {
                manualExpandedRef.current = false;
                setExpanded(false);
              }}
            />
          </motion.div>
        ) : (
          <motion.div
            key="collapsed"
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 'var(--space-4)' }}
            animate={{ opacity: 1, y: 0 }}
            exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 'calc(var(--space-4) * -1)' }}
            transition={prefersReducedMotion ? { duration: 0.12 } : { duration: 0.15, ease: [0.33, 1, 0.68, 1] }}
          >
            <CollapsedBar
              label={collapsedLabel}
              runStatus={runStatus}
              stepCount={stepCount}
              duration={durationText}
              onClick={handleManualExpand}
            />
          </motion.div>
        )}
      </AnimatePresence>
    </Shell>
  );
}

const Shell = styled.section`
  border: 1px solid var(--dark-border);
  border-radius: var(--radius-md);
  background: var(--dark-surface);
  box-shadow: var(--shadow-sm);
  margin-bottom: var(--space-8);
  overflow: hidden;
  color: var(--dark-text-secondary);
`;
