import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { GlobalAiWidget } from './GlobalAiWidget';
import { AiWidgetProvider, useAiWidget } from '../../context/AiWidgetContext';
import { AuthProvider } from '../../contexts/AuthContext';

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');

  const MotionDiv = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & {
      initial?: unknown;
      animate?: unknown;
      exit?: unknown;
      transition?: unknown;
      layout?: unknown;
      layoutId?: unknown;
      variants?: unknown;
    }
  >(({ children, initial: _initial, animate: _animate, exit: _exit, transition: _transition, layout: _layout, layoutId: _layoutId, variants: _variants, ...props }, ref) => (
    <div ref={ref} {...props}>{children}</div>
  ));
  MotionDiv.displayName = 'MotionDiv';

  return {
    ...actual,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
    motion: {
      div: MotionDiv,
    },
    useReducedMotion: () => false,
  };
});

function WidgetControls() {
  const { setWidgetState } = useAiWidget();

  return (
    <div>
      <button type="button" onClick={() => setWidgetState('EXPANDED')}>expanded</button>
      <button type="button" onClick={() => setWidgetState('CENTER_INPUT')}>center</button>
      <button type="button" onClick={() => setWidgetState('WIDGET')}>widget</button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function stubLoggedInAuth() {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => {
      if (key !== 'mutiagent-auth') return null;
      return JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'user-1',
          username: '测试用户',
          identifier: 'user@example.com',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      });
    }),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });
}

test('shows overlay only in expanded mode', async () => {
  stubLoggedInAuth();

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <WidgetControls />
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  expect(screen.queryByTestId('global-ai-widget-overlay')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'expanded' }));

  expect(await screen.findByTestId('global-ai-widget-overlay')).toBeTruthy();
  expect(screen.getByTestId('global-ai-widget-shell')).toBeTruthy();
});

test('uses transform offset for center input mode instead of margin-top', () => {
  stubLoggedInAuth();

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <WidgetControls />
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  fireEvent.click(screen.getByRole('button', { name: 'center' }));

  const frame = screen.getByTestId('global-ai-widget-frame');
  expect(frame.style.transform).toContain('translateY(');
  expect(frame.style.marginTop).toBe('');
});
