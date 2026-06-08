import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { GlobalAiWidget } from './GlobalAiWidget';
import { AiWidgetProvider, useAiWidget } from '../../context/AiWidgetContext';
import { AuthProvider } from '../../contexts/AuthContext';
import { useAuth } from '../../contexts/AuthContext';

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
  const { setWidgetState, pendingMessage, openWithMessage } = useAiWidget();
  const auth = useAuth();

  return (
    <div>
      <span data-testid="widget-pending">{pendingMessage?.text ?? ''}</span>
      <button type="button" onClick={() => setWidgetState('EXPANDED')}>expanded</button>
      <button type="button" onClick={() => setWidgetState('CENTER_INPUT')}>center</button>
      <button type="button" onClick={() => setWidgetState('WIDGET')}>widget</button>
      <button type="button" onClick={() => openWithMessage('开始第一门课')}>pending</button>
      <button
        type="button"
        onClick={() => auth.logout()}
      >
        logout
      </button>
      <button
        type="button"
        onClick={() => auth.login({
          access_token: 'token-2',
          token_type: 'bearer',
          authType: 'password',
          user: {
            uid: 'user-2',
            username: '重新登录用户',
            identifier: 'user2@example.com',
            provider: 'password',
            is_active: true,
            created_at: '2026-06-03T00:00:00Z',
            last_login_at: null,
          },
        })}
      >
        login
      </button>
    </div>
  );
}

afterEach(() => {
  cleanup();
  window.history.replaceState({}, '', '/');
  window.sessionStorage.clear();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function stubLoggedInAuth(extraStore: Record<string, string> = {}) {
  const store: Record<string, string> = {
    'mutiagent-auth': JSON.stringify({
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
    }),
    ...extraStore,
  };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
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

  const overlay = await screen.findByTestId('global-ai-widget-overlay');
  expect(overlay).toBeTruthy();
  expect((overlay as HTMLDivElement).style.pointerEvents).toBe('none');
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

test('shows the bottom-right widget after a logged-in page reload', async () => {
  window.history.replaceState({}, '', '/branch');
  stubLoggedInAuth();

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByTestId('global-ai-widget-shell')).toBeTruthy();
  });

  const shell = screen.getByTestId('global-ai-widget-shell') as HTMLDivElement;
  expect(screen.queryByTestId('global-ai-widget-overlay')).toBeNull();
  expect(shell.style.justifyContent).toBe('flex-end');
  expect(shell.style.alignItems).toBe('flex-end');
});

test('resets expanded widget state after logout before a later login returns to the docked widget', async () => {
  stubLoggedInAuth();

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <WidgetControls />
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  fireEvent.click(screen.getByRole('button', { name: 'expanded' }));
  expect(await screen.findByTestId('global-ai-widget-overlay')).toBeTruthy();

  fireEvent.click(screen.getByRole('button', { name: 'logout' }));

  expect(screen.queryByTestId('global-ai-widget-shell')).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'login' }));

  await waitFor(() => {
    expect(screen.getByTestId('global-ai-widget-shell')).toBeTruthy();
  });
  expect(screen.queryByTestId('global-ai-widget-overlay')).toBeNull();
});

test('reopens the chat panel when a logged-in sprout page contains a recoverable session_id', async () => {
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-profile');
  stubLoggedInAuth({
    'session-session-recover-profile': JSON.stringify({
      userUid: 'user-1',
      savedAt: 1000,
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '继续恢复我的画像',
          status: 'completed',
          timestamp: 1000,
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
          status: 'completed',
          timestamp: 1001,
          sessionMessage: {
            type: 'basic_profile',
            stage: 'generated',
            question_mode: 'question_box',
            confirmed_info: {
              current_grade: '大三',
              major: '软件工程',
              learning_stage: '有基础',
              has_clear_goal: '大致有方向',
              learning_method_preference: '项目驱动学习',
              learning_pace_preference: '按项目里程碑推进',
              content_preference: ['代码实践', '项目案例'],
              need_guidance: '需要轻量提醒',
              knowledge_foundation: '软件工程基础',
              strengths: '工程实现',
              weaknesses: '大型项目实战经验',
              experience: '做过课程项目',
              short_term_goal: '完成 AI 功能模块',
              long_term_goal: '形成 AI 应用开发能力',
              weekly_available_time: '每周 8 小时',
              constraints: '时间有限',
            },
            defaulted_fields: [],
            question_md: '画像已生成，是否继续生成学习路径？',
            question_box: {
              question: '画像已生成，下一步要继续生成学习路径吗？',
              options: [],
            },
            text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
          },
          runTrace: [],
          activeStepId: null,
        },
      ],
    }),
  });
  vi.stubGlobal('fetch', vi.fn());

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByLabelText('AI 基础画像对话')).toBeTruthy();
    expect(screen.getByText('画像已整理成可继续更新的学习底稿')).toBeTruthy();
  });
});

test('docks the expanded sprout recovery panel to the right edge', async () => {
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-docked');
  stubLoggedInAuth({
    'session-session-recover-docked': JSON.stringify({
      userUid: 'user-1',
      savedAt: 1000,
      messages: [
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
          status: 'completed',
          timestamp: 1001,
          sessionMessage: {
            type: 'basic_profile',
            stage: 'generated',
            question_mode: 'question_box',
            confirmed_info: {
              current_grade: '大三',
              major: '软件工程',
              learning_stage: '有基础',
              has_clear_goal: '大致有方向',
              learning_method_preference: '项目驱动学习',
              learning_pace_preference: '按项目里程碑推进',
              content_preference: ['代码实践', '项目案例'],
              need_guidance: '需要轻量提醒',
              knowledge_foundation: '软件工程基础',
              strengths: '工程实现',
              weaknesses: '大型项目实战经验',
              experience: '做过课程项目',
              short_term_goal: '完成 AI 功能模块',
              long_term_goal: '形成 AI 应用开发能力',
              weekly_available_time: '每周 8 小时',
              constraints: '时间有限',
            },
            defaulted_fields: [],
            question_md: '画像已生成，是否继续生成学习路径？',
            question_box: {
              question: '画像已生成，下一步要继续生成学习路径吗？',
              options: [],
            },
            text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
          },
          runTrace: [],
          activeStepId: null,
        },
      ],
    }),
  });
  vi.stubGlobal('fetch', vi.fn());

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <GlobalAiWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByLabelText('AI 基础画像对话')).toBeTruthy();
  });

  expect(screen.getByTestId('global-ai-widget-frame').getAttribute('data-expanded-layout')).toBe('docked');
  expect((screen.getByTestId('global-ai-widget-shell') as HTMLDivElement).style.justifyContent).toBe('flex-end');
});
