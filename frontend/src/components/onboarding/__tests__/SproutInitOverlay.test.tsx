import { act, cleanup, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { AiWidgetProvider, useAiWidget } from '../../../context/AiWidgetContext';
import { SproutInitOverlay } from '../SproutInitOverlay';

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
      h2: createMotionTag<React.HTMLAttributes<HTMLHeadingElement>>('h2'),
      p: createMotionTag<React.HTMLAttributes<HTMLParagraphElement>>('p'),
    },
    useReducedMotion: () => reduceMotionValue,
  };
});

function WidgetStateProbe() {
  const { widgetState } = useAiWidget();
  return <div data-testid="widget-state">{widgetState}</div>;
}

afterEach(() => {
  cleanup();
  reduceMotionValue = false;
  vi.useRealTimers();
});

test('expands immediately when reduced motion is enabled', async () => {
  reduceMotionValue = true;

  render(
    <AiWidgetProvider>
      <WidgetStateProbe />
      <SproutInitOverlay />
    </AiWidgetProvider>,
  );

  await waitFor(() => {
    expect(screen.getByTestId('widget-state').textContent).toBe('EXPANDED');
  });

  expect(screen.getByText('在开启旅程之前，想先听听你的声音。')).toBeTruthy();
});

test('uses opacity and transform motion props instead of filter-based animation', () => {
  vi.useFakeTimers();
  reduceMotionValue = false;

  const { container } = render(
    <AiWidgetProvider>
      <SproutInitOverlay />
    </AiWidgetProvider>,
  );
  const rootOverlay = container.firstElementChild as HTMLElement | null;

  act(() => {
    vi.advanceTimersByTime(1000);
  });

  const introHeading = screen.getByText('你好');

  expect(rootOverlay?.getAttribute('data-initial')).toBe(JSON.stringify({ opacity: 0 }));
  expect(rootOverlay?.getAttribute('data-animate')).toBe(JSON.stringify({ opacity: 1 }));
  expect(rootOverlay?.getAttribute('data-exit')).toBe(JSON.stringify({ opacity: 0 }));

  expect(introHeading.getAttribute('data-initial')).toBe(JSON.stringify({ opacity: 0, y: 8 }));
  expect(introHeading.getAttribute('data-animate')).toBe(JSON.stringify({ opacity: 1, y: 0 }));
  expect(introHeading.getAttribute('data-exit')).toContain('"y":-8');
  expect(introHeading.getAttribute('data-initial')).not.toContain('filter');
  expect(rootOverlay?.getAttribute('data-initial')).not.toContain('backdropFilter');
  expect(rootOverlay).toBeTruthy();
});
