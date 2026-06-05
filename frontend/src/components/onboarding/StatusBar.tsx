import React from 'react';
import styled from 'styled-components';
import { motion } from 'framer-motion';

interface StatusBarProps {
  text: string;
  time?: string;
  status?: 'running' | 'done' | 'none';
  onClick?: () => void;
}

export function StatusBar({ text, time, status = 'running', onClick }: StatusBarProps) {
  return (
    <>
      <Divider />
      <Bar
        as={onClick ? motion.button : 'div'}
        type={onClick ? "button" : undefined}
        onClick={onClick}
        whileHover={onClick ? { background: 'var(--dark-highlight)' } : undefined}
        whileTap={onClick ? { scale: 0.99 } : undefined}
        $clickable={!!onClick}
        $hasTime={!!time}
      >
        {status !== 'none' && (
          <Dot className={status === 'running' ? 'dot-running' : status === 'done' ? 'dot-done' : ''} data-testid="status-dot" />
        )}
        <span className="text">{text}</span>
        {time && <span className="time">{time}</span>}
        {onClick && <span className="chevron">收起详情</span>}
      </Bar>
    </>
  );
}

const Divider = styled.div`
  margin: 0 var(--space-12) var(--space-4);
  border-top: 1px solid var(--dark-border);
`;

const Bar = styled.div<{ $clickable?: boolean; $hasTime?: boolean }>`
  margin: 0 var(--space-4) var(--space-4);
  padding: var(--space-8) var(--space-8);
  display: flex;
  align-items: center;
  gap: var(--space-8);
  font-family: var(--font-body);
  font-size: var(--text-caption);
  background: transparent;
  border: none;
  width: calc(100% - var(--space-8));
  text-align: left;
  border-radius: var(--radius-sm);
  transition:
    background var(--duration-lazy-hover) var(--ease-lazy),
    opacity var(--duration-lazy-hover) var(--ease-lazy);
  ${props => props.$clickable && `
    cursor: pointer;
  `}

  .text {
    color: var(--dark-text-secondary);
  }

  .time {
    color: var(--dark-text-muted);
    margin-left: auto;
    flex-shrink: 0;
    font-family: var(--font-mono);
  }

  .chevron {
    color: var(--dark-text-muted);
    font-size: var(--text-caption);
    margin-left: ${props => props.$hasTime ? 'var(--space-8)' : 'auto'};
    flex-shrink: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
  }
`;

const Dot = styled.span`
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  position: relative;
  background: var(--dark-text-muted);

  &.dot-running {
    background: var(--status-running);
    animation: dotPulseRing 1.2s var(--ease-editorial) infinite;

    &::after {
      content: '';
      position: absolute;
      inset: -3px;
      border-radius: var(--radius-full);
      border: 1px solid var(--status-running);
      opacity: 0;
      animation: dotPulseRingExpand 1.2s var(--ease-editorial) infinite;
    }
  }

  &.dot-done {
    background: var(--status-running);
  }

  @keyframes dotPulseRing {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.55; transform: scale(1.3); }
  }

  @keyframes dotPulseRingExpand {
    0% { opacity: 0.5; transform: scale(0.8); }
    100% { opacity: 0; transform: scale(2.8); }
  }

  @media (prefers-reduced-motion: reduce) {
    &.dot-running {
      animation: none;
      opacity: 0.7;
      &::after { animation: none; display: none; }
    }
  }
`;
