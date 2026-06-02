import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { AgentRunTimeline } from '../AgentRunTimeline';
import type { AgentRunStep } from '../../../types/chat';

vi.mock('framer-motion', () => {
  const MotionDiv = ({
    children,
    initial: _initial,
    animate: _animate,
    exit: _exit,
    transition: _transition,
    ...props
  }: React.HTMLAttributes<HTMLDivElement> & {
    initial?: unknown;
    animate?: unknown;
    exit?: unknown;
    transition?: unknown;
  }) => <div {...props}>{children}</div>;

  const MotionButton = ({
    children,
    whileHover: _whileHover,
    whileTap: _whileTap,
    transition: _transition,
    ...props
  }: React.ButtonHTMLAttributes<HTMLButtonElement> & {
    whileHover?: unknown;
    whileTap?: unknown;
    transition?: unknown;
  }) => <button {...props}>{children}</button>;

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: {
      div: MotionDiv,
      button: MotionButton,
    },
  };
});

const completedSteps: AgentRunStep[] = [
  {
    stepId: 'profile_agent',
    kind: 'agent',
    status: 'success',
    title: '基础画像智能体',
    summary: '基础画像智能体已完成本轮处理。',
    agent: 'profile_agent',
    durationMs: 1200,
  },
];

const runningSteps: AgentRunStep[] = [
  {
    stepId: 'profile_agent',
    kind: 'agent',
    status: 'running',
    title: '基础画像智能体',
    summary: '基础画像智能体开始处理。',
    agent: 'profile_agent',
  },
];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

test('keeps details open after the user manually expands a completed timeline', () => {
  vi.useFakeTimers();

  render(<AgentRunTimeline steps={completedSteps} status="completed" />);

  act(() => {
    fireEvent.click(screen.getByRole('button', { name: /展开详情/ }));
    vi.advanceTimersByTime(200);
  });
  expect(screen.getByText('基础画像智能体已完成本轮处理。')).toBeTruthy();

  act(() => {
    vi.advanceTimersByTime(2500);
  });

  expect(screen.getByText('基础画像智能体已完成本轮处理。')).toBeTruthy();
});

test('auto-collapses after the AI-finished timeline stays visible for two seconds', () => {
  vi.useFakeTimers();

  const { rerender } = render(<AgentRunTimeline steps={runningSteps} status="streaming" />);
  expect(screen.getByText('基础画像智能体开始处理。')).toBeTruthy();

  rerender(<AgentRunTimeline steps={completedSteps} status="completed" />);

  act(() => {
    vi.advanceTimersByTime(2500);
  });

  expect(screen.queryByText('基础画像智能体已完成本轮处理。')).toBeNull();
  expect(screen.getByRole('button', { name: /展开详情/ })).toBeTruthy();
});
