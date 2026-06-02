import React from 'react';
import { motion } from 'framer-motion';
import styled from 'styled-components';
import type { AgentRunStep } from '../../types/chat';
import { formatStepTitle, formatStepKind } from './stepLabels';

interface ExpandedLogProps {
  steps: AgentRunStep[];
}

function formatDuration(ms?: number): string {
  if (typeof ms !== 'number' || Number.isNaN(ms) || ms < 0) return '';
  if (ms < 10) return `${ms.toFixed(1)}ms`;
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

function StatusSymbol({ status }: { status: string }) {
  switch (status) {
    case 'running': return <span>运行中</span>;
    case 'success': return <span>已完成</span>;
    case 'error': return <span>异常</span>;
    default: return <span>{status}</span>;
  }
}

export function ExpandedLog({ steps }: ExpandedLogProps) {
  return (
    <Shell>
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        const branch = isLast ? '└─' : '├─';

        return (
          <StepRow
            key={step.stepId}
            data-status={step.status}
            as={motion.div}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              duration: 0.35,
              ease: [0.22, 0.61, 0.36, 1],
              delay: idx * 0.04,
            }}
          >
            <div className="step-line">
              <span className="branch">{branch}</span>
              <span className="kind">【{formatStepKind(step)}】</span>
              <span className="name">{formatStepTitle(step)}</span>
              <span className={`status status-${step.status}`}>
                <StatusSymbol status={step.status} />
              </span>
              {step.durationMs !== undefined && (
                <span className="duration">{formatDuration(step.durationMs)}</span>
              )}
            </div>
            {step.summary && (
              <div className="summary">{step.summary}</div>
            )}
          </StepRow>
        );
      })}
    </Shell>
  );
}

const Shell = styled.div`
  margin: 0 var(--space-12);
  padding: var(--space-8) var(--space-12);
  background: transparent;
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  line-height: 1.7;
  color: var(--color-text-secondary);
`;

const StepRow = styled.div`
  position: relative;
  margin-left: -4px;
  padding-left: 4px;
  border-left: 2px solid transparent;
  transition:
    border-color 0.5s var(--ease-editorial),
    background 0.5s var(--ease-editorial);

  &[data-status='running'] {
    border-left-color: var(--color-primary);
    background: linear-gradient(90deg, oklch(74% 0.08 60 / 0.06) 0%, transparent 60%);
  }

  &[data-status='error'] {
    border-left-color: var(--color-error);
    background: linear-gradient(90deg, oklch(60% 0.10 28 / 0.06) 0%, transparent 60%);
  }

  &[data-status='success'] {
    border-left-color: var(--color-success);
  }

  .step-line {
    display: flex;
    align-items: baseline;
    gap: 6px;
    min-width: 0;
  }

  .branch {
    color: var(--color-text-muted);
    flex-shrink: 0;
  }

  .kind {
    color: var(--color-text-muted);
    flex-shrink: 0;
  }

  .name {
    color: var(--color-text-primary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .status {
    flex-shrink: 0;
    font-size: var(--text-caption);
  }

  .status-running {
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
  }

  .status-success {
    color: var(--color-success);
  }

  .status-error {
    color: var(--color-error);
  }

  .duration {
    color: var(--color-text-muted);
    margin-left: auto;
    flex-shrink: 0;
  }

  .summary {
    margin: 2px 0 var(--space-8) 18px;
    color: var(--color-text-muted);
    font-size: 11px;
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;
