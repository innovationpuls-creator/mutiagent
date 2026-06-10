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
  const { widgetState, setWidgetState } = useAiWidget();
  return (
    <>
      <div data-testid="widget-state">{widgetState}</div>
      <button type="button" onClick={() => setWidgetState('WIDGET')}>
        set-widget
      </button>
    </>
  );
}

afterEach(() => {
  cleanup();
  reduceMotionValue = false;
  vi.useRealTimers();
});

test('shows the center input immediately when reduced motion is enabled', async () => {
  reduceMotionValue = true;

  const { container } = render(
    <AiWidgetProvider>
      <WidgetStateProbe />
      <SproutInitOverlay />
    </AiWidgetProvider>,
  );

  await waitFor(() => {
    expect(screen.getByTestId('widget-state').textContent).toBe('CENTER_INPUT');
  });

  const rootOverlay = container.querySelector('[data-animate]');
  expect(rootOverlay).toBeTruthy();
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
  expect(rootOverlay?.style.backdropFilter).toBe('blur(56px)');

  expect(introHeading.getAttribute('data-initial')).toBe(JSON.stringify({ opacity: 0, y: 8 }));
  expect(introHeading.getAttribute('data-animate')).toBe(JSON.stringify({ opacity: 1, y: 0 }));
  expect(introHeading.getAttribute('data-exit')).toContain('"y":-8');
  expect(introHeading.getAttribute('data-initial')).not.toContain('filter');
  expect(rootOverlay).toBeTruthy();
});

test('keeps the blur overlay mounted through center input and completes only when collapsed to widget', async () => {
  vi.useFakeTimers();
  const onComplete = vi.fn();

  render(
    <AiWidgetProvider>
      <WidgetStateProbe />
      <SproutInitOverlay onComplete={onComplete} />
    </AiWidgetProvider>,
  );

  // Advance timers by 7500ms to complete the introduction timeline and trigger CENTER_INPUT
  act(() => {
    vi.advanceTimersByTime(7500);
  });

  expect(screen.getByTestId('widget-state').textContent).toBe('CENTER_INPUT');
  expect(onComplete).not.toHaveBeenCalled();

  act(() => {
    screen.getByRole('button', { name: 'set-widget' }).click();
  });

  // Advance timers by 1200ms to execute the exit animation delay
  act(() => {
    vi.advanceTimersByTime(1200);
  });

  // Flush promise microtasks to allow the async sequence function to complete
  await act(async () => {
    await Promise.resolve();
  });

  expect(onComplete).toHaveBeenCalledTimes(1);
});
