import React from 'react';
import { motion } from 'framer-motion';
import styled from 'styled-components';
import { formatRunSummary } from './stepLabels';

interface CollapsedBarProps {
  agent: string;
  runStatus: 'running' | 'completed' | 'failed';
  stepCount: number;
  duration: string;
  onClick: () => void;
}

export function CollapsedBar({
  agent,
  runStatus,
  stepCount,
  duration,
  onClick,
}: CollapsedBarProps) {
  const summary = formatRunSummary({ agent, runStatus, stepCount, duration });

  return (
    <CollapsedButton
      as={motion.button}
      type="button"
      onClick={onClick}
      whileHover={{ background: 'rgba(245,240,232,0.25)' }}
      whileTap={{ scale: 0.99 }}
      transition={{ duration: 0.3, ease: [0.33, 1, 0.68, 1] }}
    >
      <span>{summary}</span>
      <span className="chevron">展开详情</span>
    </CollapsedButton>
  );
}

const CollapsedButton = styled.button`
  border: none;
  background: transparent;
  display: flex;
  align-items: center;
  gap: var(--space-8);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  cursor: pointer;
  width: 100%;
  text-align: left;
  padding: var(--space-8) var(--space-12);
  border-radius: var(--radius-md);

  &:hover {
    background: oklch(90% 0.03 73 / 0.25);
  }

  .chevron {
    color: var(--color-text-muted);
    font-size: 11px;
    margin-left: auto;
    flex-shrink: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    &:hover { background: oklch(90% 0.03 73 / 0.25); }
  }
`;
