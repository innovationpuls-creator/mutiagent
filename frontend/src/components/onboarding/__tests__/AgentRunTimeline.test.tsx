import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
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
    startedAtMs: 1000,
  },
];

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
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
  const timeline = screen.getByLabelText('Agent run timeline');
  expect(within(timeline).getAllByText('基础画像智能体开始处理。').length).toBeGreaterThan(0);

  rerender(<AgentRunTimeline steps={completedSteps} status="completed" />);

  act(() => {
    vi.advanceTimersByTime(2500);
  });

  expect(screen.queryByText('基础画像智能体已完成本轮处理。')).toBeNull();
  expect(screen.getByRole('button', { name: /展开详情/ })).toBeTruthy();
});

test('shows live elapsed time while a step is still running', () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date('2026-06-04T00:00:00.000Z'));
  let now = 2200;
  vi.spyOn(performance, 'now').mockImplementation(() => now);

  render(<AgentRunTimeline steps={runningSteps} status="streaming" />);
  const timeline = screen.getByLabelText('Agent run timeline');
  const duration = () => within(timeline).getByText((content, element) =>
    element?.classList.contains('duration') === true && content === `(${((now - 1000) / 1000).toFixed(1)}s)`,
  );

  expect(duration()).toBeTruthy();

  act(() => {
    now = 3400;
    vi.advanceTimersByTime(1000);
  });

  expect(within(timeline).getByText((content, element) =>
    element?.classList.contains('duration') === true && content === '(2.4s)',
  )).toBeTruthy();
  expect(within(timeline).queryByText((content, element) =>
    element?.classList.contains('duration') === true && content === '(1.2s)',
  )).toBeNull();
});

test('renders the agent key for each step in the expanded log', () => {
  render(<AgentRunTimeline steps={runningSteps} status="streaming" />);

  const timeline = screen.getByLabelText('Agent run timeline');
  expect(within(timeline).getByText('[profile_agent]')).toBeTruthy();
  expect(within(timeline).getByText('基础画像智能体')).toBeTruthy();
});

test('prefers the answer step label in collapsed summary when the turn ends with a direct reply', () => {
  vi.useFakeTimers();

  const answerSteps: AgentRunStep[] = [
    {
      stepId: 'intent-routing',
      kind: 'route',
      status: 'success',
      title: '意图识别智能体',
      summary: '正在判断本轮要调用的智能体',
      agent: 'intent_agent',
      durationMs: 40,
    },
    {
      stepId: 'step-answer-session-1',
      kind: 'answer',
      status: 'success',
      title: '生成回复',
      summary: '本轮内容已生成',
      durationMs: 1200,
    },
  ];

  render(<AgentRunTimeline steps={answerSteps} status="completed" />);

  act(() => {
    vi.advanceTimersByTime(2500);
  });

  expect(screen.getByRole('button', { name: /生成回复 已完成/ })).toBeTruthy();
  expect(screen.queryByRole('button', { name: /intent_agent 已完成/ })).toBeNull();
});

test('renders the expanded timeline as a compact log stream inside one panel', () => {
  render(<AgentRunTimeline steps={runningSteps} status="streaming" />);

  const timeline = screen.getByLabelText('Agent run timeline');
  expect(within(timeline).getByTestId('agent-log-stream')).toBeTruthy();
  expect(within(timeline).getByTestId('agent-log-row-profile_agent')).toBeTruthy();
});

test('renders parallel and dependency metadata for a running step', () => {
  const parallelSteps: AgentRunStep[] = [
    {
      stepId: 'learning_path_agent',
      kind: 'agent',
      status: 'running',
      title: '学习路径智能体',
      summary: '学习路径智能体开始处理。',
      agent: 'learning_path_agent',
      startedAtMs: 1000,
      parallelGroup: 'path',
      dependsOn: ['supervisor'],
    },
  ];

  render(<AgentRunTimeline steps={parallelSteps} status="streaming" />);

  const timeline = screen.getByLabelText('Agent run timeline');
  expect(within(timeline).getByText('并行组 path')).toBeTruthy();
  expect(within(timeline).getByText('依赖 supervisor')).toBeTruthy();
});

test('marks the timeline as warm paper and highlights the running log row', () => {
  render(<AgentRunTimeline steps={runningSteps} status="streaming" />);

  const timeline = screen.getByLabelText('Agent run timeline');
  const runningRow = within(timeline).getByTestId('agent-log-row-profile_agent');

  expect(timeline.getAttribute('data-surface')).toBe('warm-paper');
  expect(runningRow.getAttribute('data-highlighted')).toBe('true');
});
