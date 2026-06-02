import React, { useEffect, useMemo, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import styled from 'styled-components';
import type { AgentRunStep, MessageStatus } from '../../types/chat';
import { CollapsedBar } from './CollapsedBar';
import { ExpandedLog } from './ExpandedLog';
import { StatusBar } from './StatusBar';

const COLLAPSE_DELAY_MS = 2000;

interface AgentRunTimelineProps {
  steps?: AgentRunStep[];
  status: MessageStatus;
}

export function AgentRunTimeline({ steps = [], status }: AgentRunTimelineProps) {
  const [expanded, setExpanded] = useState(false);
  const collapseTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualExpandedRef = useRef(false);

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

  const agent = useMemo(
    () => [...steps].reverse().find((s) => s.agent)?.agent || 'Agent',
    [steps],
  );

  const runStatus = useMemo(() => {
    const failed = steps.find((s) => s.status === 'error');
    const running = steps.find((s) => s.status === 'running');
    if (failed) return 'failed';
    if (running) return 'running';
    return 'completed';
  }, [steps]);

  const stepCount = steps.length;
  const totalMs = steps.reduce(
    (sum, s) => sum + (typeof s.durationMs === 'number' ? s.durationMs : 0),
    0,
  );
  const durationText =
    totalMs > 0
      ? totalMs < 1000
        ? `${Math.round(totalMs)}ms`
        : `${(totalMs / 1000).toFixed(totalMs < 10000 ? 1 : 0)}s`
      : '';

  const currentStep = [...steps].reverse().find((s) => s.status === 'running');
  const statusText = currentStep
    ? currentStep.kind === 'answer'
      ? '正在生成回复'
      : currentStep.kind === 'route'
        ? '正在调度智能体'
        : '智能体处理中'
    : runStatus === 'running'
      ? '智能体处理中'
      : '';

  if (steps.length === 0) return null;

  return (
    <Shell aria-label="Agent run timeline">
      <AnimatePresence mode="wait">
        {expanded ? (
          <motion.div
            key="expanded"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.25, 1, 0.5, 1] }}
          >
            <ExpandedLog steps={steps} />
            <StatusBar
              text={statusText}
              time={runStatus === 'running' ? durationText : undefined}
              status={runStatus === 'running' ? 'running' : 'done'}
            />
          </motion.div>
        ) : (
          <motion.div
            key="collapsed"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            <CollapsedBar
              agent={agent}
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
  border: 1px solid oklch(78% 0.012 80 / 0.2);
  border-radius: var(--radius-md);
  background: oklch(92% 0.02 75 / 0.3);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  margin-bottom: var(--space-8);
  overflow: hidden;
`;
