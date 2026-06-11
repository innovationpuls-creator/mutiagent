import { act, cleanup, render, screen } from '@testing-library/react';
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { PathInitOverlay } from '../PathInitOverlay';

let reduceMotionValue = false;

vi.mock('framer-motion', () => {
  function createMotionTag<TagProps extends React.HTMLAttributes<HTMLElement>>(
    tag: keyof JSX.IntrinsicElements,
  ) {
    return ({
      children,
      initial,
      animate,
      exit,
      transition,
      layout: _layout,
      ...props
    }: TagProps & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: unknown;
      layout?: unknown;
    }) => React.createElement(tag, {
      ...props,
      'data-initial': JSON.stringify(initial ?? null),
      'data-animate': JSON.stringify(animate ?? null),
      'data-exit': JSON.stringify(exit ?? null),
      'data-transition': JSON.stringify(transition ?? null),
    }, children);
  }

  return {
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: {
      div: createMotionTag<React.HTMLAttributes<HTMLDivElement>>('div'),
      h1: createMotionTag<React.HTMLAttributes<HTMLHeadingElement>>('h1'),
      p: createMotionTag<React.HTMLAttributes<HTMLParagraphElement>>('p'),
      button: createMotionTag<React.ButtonHTMLAttributes<HTMLButtonElement>>('button'),
    },
    useReducedMotion: () => reduceMotionValue,
  };
});

afterEach(() => {
  cleanup();
  reduceMotionValue = false;
  vi.useRealTimers();
});

test('renders text phases and triggers completion callback on button click', () => {
  vi.useFakeTimers();
  const mockComplete = vi.fn();
  
  render(<PathInitOverlay onComplete={mockComplete} />);
  
  // 验证大标题存在
  expect(screen.getByText('你的自适应学习路径已顺利编织完成。')).toBeTruthy();
  // 初始状态下描述文本和按钮因未到时间均不渲染 (phase = 0)
  expect(screen.queryByText(/系统已根据你的画像基础/)).toBeNull();
  expect(screen.queryByRole('button', { name: '开始第一门课' })).toBeNull();
  
  // 前进 1200ms -> 进入 phase 1 (渲染概要文本)
  act(() => {
    vi.advanceTimersByTime(1200);
  });
  expect(screen.getByText(/系统已根据你的画像基础/)).toBeTruthy();
  expect(screen.queryByRole('button', { name: '开始第一门课' })).toBeNull();

  // 再前进 1600ms (累计 2800ms) -> 进入 phase 2 (渲染按钮)
  act(() => {
    vi.advanceTimersByTime(1600);
  });
  expect(screen.getByText(/系统已根据你的画像基础/)).toBeTruthy();
  const btn = screen.getByRole('button', { name: '开始第一门课' });
  expect(btn).toBeTruthy();

  // 点击按钮，验证触发回调
  act(() => {
    btn.click();
  });
  expect(mockComplete).toHaveBeenCalledTimes(1);
});

test('renders everything immediately when reduced motion is enabled', () => {
  reduceMotionValue = true;
  const mockComplete = vi.fn();

  render(<PathInitOverlay onComplete={mockComplete} />);

  expect(screen.getByText('你的自适应学习路径已顺利编织完成。')).toBeTruthy();
  expect(screen.getByText(/系统已根据你的画像基础/)).toBeTruthy();
  const btn = screen.getByRole('button', { name: '开始第一门课' });
  expect(btn).toBeTruthy();
});
