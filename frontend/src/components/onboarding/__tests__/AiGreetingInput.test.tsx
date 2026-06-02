import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { useEffect } from 'react';
import { afterEach, expect, test, vi } from 'vitest';
import { AiGreetingInput } from '../AiGreetingInput';
import { AiWidgetProvider, useAiWidget } from '../../../context/AiWidgetContext';
import { AuthProvider } from '../../../contexts/AuthContext';

function ExpandedWidget() {
  const { setWidgetState } = useAiWidget();

  useEffect(() => {
    setWidgetState('EXPANDED');
  }, [setWidgetState]);

  return <AiGreetingInput />;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function stubLocalStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
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

test('renders AiGreetingInput cleanly without CSS areas', () => {
  const { container } = render(
    <AuthProvider>
      <AiWidgetProvider>
        <AiGreetingInput />
      </AiWidgetProvider>
    </AuthProvider>
  );
  // Ensure the 15 css-hover grid areas are removed
  expect(container.querySelectorAll('.area').length).toBe(0);
});

test('shows the Codex-style progress panel beside the chat flow when expanded', async () => {
  vi.stubGlobal('scrollTo', vi.fn());

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  expect(await screen.findByLabelText('多智能体调用状态')).toBeTruthy();
  expect(screen.getByText('进度')).toBeTruthy();
  expect(screen.getByText('Agent 步骤')).toBeTruthy();
  expect(screen.getByText('等待本轮调用开始...')).toBeTruthy();
  expect(screen.getByLabelText('对话内容')).toBeTruthy();
  expect(screen.getByLabelText('AI 基础画像对话')).toBeTruthy();
});

test('renders detailed main agent flow in the left message timeline', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  stubLocalStorage({
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
  });

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: agent_step_completed',
            'data: {"step_id":"context_user_input","agent_key":"main_agent","label":"读取用户输入","message":"已读取本轮用户输入。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_profile","agent_key":"main_agent","label":"加载用户画像","message":"已加载基础画像上下文。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_agent_registry","agent_key":"main_agent","label":"配置智能体能力","message":"已配置可调用智能体。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_main_inputs","agent_key":"main_agent","label":"整理主智能体上下文","message":"已注入主智能体上下文。"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"main_agent","agent_key":"main_agent","label":"主智能体","message":"主智能体开始处理。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"main_agent","agent_key":"main_agent","label":"主智能体","message":"主智能体已返回调用计划：学习路径智能体。"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"learning","agent_key":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体开始处理。","depends_on":["main_agent"],"parallel_group":"path"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"learning","agent_key":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体结果返回成功。","depends_on":["main_agent"],"parallel_group":"path"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"main_agent_final","agent_key":"main_agent","label":"主智能体","message":"主智能体开始整合智能体结果。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"main_agent_final","agent_key":"main_agent","label":"主智能体","message":"主智能体已整合智能体结果。"}',
            '',
            'event: orchestration_completed',
            'data: {"session_id":"session-1","answer":{"user_message":"学习路径已生成","question_box":null},"agent_trace":[],"completed":true,"profile":null,"learning_path":null}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(stream, { status: 200 })));

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '帮我生成学习路径' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('已读取本轮用户输入。')).toBeTruthy();
    expect(screen.getAllByText('【agent】').length).toBeGreaterThan(0);
    expect(screen.getByText('主智能体已返回调用计划：学习路径智能体。')).toBeTruthy();
    expect(screen.getByText(/学习路径智能体结果返回成功。 · 并行中：path · 依赖：main_agent/)).toBeTruthy();
    expect(screen.getByText('主智能体已整合智能体结果。')).toBeTruthy();
    expect(screen.getByText('【answer】')).toBeTruthy();
  });
});
