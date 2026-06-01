import React from 'react';
import styled from 'styled-components';

interface StatusBarProps {
  text: string;
  time?: string;
  status?: 'running' | 'done' | 'none';
}

export function StatusBar({ text, time, status = 'running' }: StatusBarProps) {
  return (
    <>
      <Divider />
      <Bar>
        {status !== 'none' && (
          <Dot className={status === 'running' ? 'dot-running' : status === 'done' ? 'dot-done' : ''} data-testid="status-dot" />
        )}
        <span className="text">{text}</span>
        {time && <span className="time">{time}</span>}
      </Bar>
    </>
  );
}

const Divider = styled.div`
  margin: 0 var(--space-12) var(--space-4);
  border-top: 1px solid oklch(78% 0.012 80 / 0.18);
`;

const Bar = styled.div`
  margin: 0 var(--space-12) var(--space-12);
  padding: 6px var(--space-12);
  display: flex;
  align-items: center;
  gap: var(--space-8);
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  background: transparent;

  .text {
    color: var(--color-text-secondary);
  }

  .time {
    color: var(--color-text-muted);
    margin-left: auto;
    flex-shrink: 0;
  }
`;

const Dot = styled.span`
  width: 6px;
  height: 6px;
  border-radius: var(--radius-full);
  flex-shrink: 0;
  position: relative;
  background: var(--color-text-muted);

  &.dot-running {
    background: var(--color-primary);
    animation: dotPulseRing 1.2s var(--ease-editorial) infinite;

    &::after {
      content: '';
      position: absolute;
      inset: -3px;
      border-radius: var(--radius-full);
      border: 1px solid var(--color-primary);
      opacity: 0;
      animation: dotPulseRingExpand 1.2s var(--ease-editorial) infinite;
    }
  }

  &.dot-done {
    background: var(--color-success);
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
