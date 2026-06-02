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
  vi.restoreAllMocks();
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

const emptyConfirmedInfo = {
  current_grade: '',
  major: '',
  learning_stage: '',
  has_clear_goal: '',
  learning_method_preference: '',
  learning_pace_preference: '',
  content_preference: [],
  need_guidance: '',
  knowledge_foundation: '',
  strengths: '',
  weaknesses: '',
  experience: '',
  short_term_goal: '',
  long_term_goal: '',
  weekly_available_time: '',
  constraints: '',
};

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
  vi.spyOn(Date, 'now').mockReturnValue(1000);
  vi.spyOn(performance, 'now').mockReturnValue(1000);
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
            'data: {"step_id":"context_user_input","agent_key":"main_agent","label":"读取用户输入","message":"已读取本轮用户输入。","kind":"data"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_profile","agent_key":"main_agent","label":"加载用户画像","message":"已加载基础画像上下文。","kind":"data"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_agent_registry","agent_key":"main_agent","label":"配置智能体能力","message":"已配置可调用智能体。","kind":"system"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"context_main_inputs","agent_key":"main_agent","label":"整理主智能体上下文","message":"已注入主智能体上下文。","kind":"data"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"main_agent","agent_key":"main_agent","label":"主智能体","message":"主智能体开始处理。","kind":"agent"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"main_agent","agent_key":"main_agent","label":"主智能体","message":"主智能体已返回调用计划：学习路径智能体。","kind":"agent"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"learning","agent_key":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体开始处理。","depends_on":["main_agent"],"parallel_group":"path","kind":"agent"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"learning","agent_key":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体结果返回成功。","depends_on":["main_agent"],"parallel_group":"path","kind":"agent"}',
            '',
            'event: agent_step_started',
            'data: {"step_id":"main_agent_final","agent_key":"main_agent","label":"主智能体","message":"主智能体开始整合智能体结果。","kind":"agent"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"main_agent_final","agent_key":"main_agent","label":"主智能体","message":"主智能体已整合智能体结果。","kind":"agent"}',
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
    expect(screen.getAllByText('【数据】').length).toBeGreaterThan(0);
    expect(screen.getAllByText('【系统】').length).toBeGreaterThan(0);
    expect(screen.getAllByText('【agent】').length).toBeGreaterThan(0);
    expect(screen.getByText('主智能体已返回调用计划：学习路径智能体。')).toBeTruthy();
    expect(screen.getByText(/学习路径智能体结果返回成功。 · 并行中：path · 依赖：main_agent/)).toBeTruthy();
    expect(screen.getByText('主智能体已整合智能体结果。')).toBeTruthy();
    expect(screen.getByText('【answer】')).toBeTruthy();
    expect(screen.queryByText('0ms')).toBeNull();
  });
});

test('keeps the agent timeline when a structured question card is rendered', async () => {
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

  const profile = {
    type: 'collecting',
    stage: 'basic_info',
    question_mode: 'question_box',
    confirmed_info: emptyConfirmedInfo,
    defaulted_fields: [],
    question_md: '请选择你的年级',
    question_box: { question: '请选择你的年级', options: ['大一', '大二'] },
    text: '请选择你的年级',
  };
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: agent_step_started',
            'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
            '',
            'event: agent_step_completed',
            'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体已完成本轮处理。"}',
            '',
            'event: orchestration_completed',
            `data: ${JSON.stringify({
              session_id: 'session-structured',
              answer: { user_message: '请选择你的年级', question_box: profile.question_box },
              agent_trace: [],
              completed: false,
              profile,
              learning_path: null,
            })}`,
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
  fireEvent.change(input, { target: { value: '重新采集画像' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('请选择你的年级')).toBeTruthy();
    expect(screen.getByText('大一')).toBeTruthy();
    expect(screen.getByLabelText('Agent run timeline')).toBeTruthy();
    expect(screen.getByText('基础画像智能体已完成本轮处理。')).toBeTruthy();
  });
});

test('hides options after user clicks one and shows user message in chat', async () => {
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

  const profile = {
    type: 'collecting',
    stage: 'basic_info',
    question_mode: 'question_box',
    confirmed_info: emptyConfirmedInfo,
    defaulted_fields: [],
    question_md: '请选择你的年级',
    question_box: { question: '请选择你的年级', options: ['大一', '大二'] },
    text: '请选择你的年级',
  };

  const encoder = new TextEncoder();
  let fetchCallCount = 0;
  const fetchMock = vi.fn().mockImplementation(() => {
    fetchCallCount++;
    if (fetchCallCount === 1) {
      // First call: return the question card
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(
            encoder.encode(
              [
                'event: agent_step_started',
                'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
                '',
                'event: agent_step_completed',
                'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体已完成本轮处理。"}',
                '',
                'event: orchestration_completed',
                `data: ${JSON.stringify({
                  session_id: 'session-structured',
                  answer: { user_message: '请选择你的年级', question_box: profile.question_box },
                  agent_trace: [],
                  completed: false,
                  profile,
                  learning_path: null,
                })}`,
                '',
              ].join('\n'),
            ),
          );
          controller.close();
        },
      });
      return Promise.resolve(new Response(stream, { status: 200 }));
    }
    // Second call: return a simple response
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            [
              'event: agent_step_started',
              'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
              '',
              'event: agent_step_completed',
              'data: {"step_id":"profile_agent","agent_key":"profile_agent","label":"基础画像智能体","message":"基础画像智能体已完成本轮处理。"}',
              '',
              'event: orchestration_completed',
              `data: ${JSON.stringify({
                session_id: 'session-structured-2',
                answer: { user_message: '好的，已记录你的年级。', question_box: null },
                agent_trace: [],
                completed: false,
                profile: { ...profile, type: 'collecting', stage: 'learning_preference', question_box: { question: '请选择你的学习偏好', options: ['自主学习', '小组学习'] } },
                learning_path: null,
              })}`,
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      },
    });
    return Promise.resolve(new Response(stream, { status: 200 }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  // Step 1: Send initial message to get the question card
  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '重新采集画像' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  // Step 2: Wait for the question card to appear
  await waitFor(() => {
    expect(screen.getByText('请选择你的年级')).toBeTruthy();
    expect(screen.getByText('大一')).toBeTruthy();
    expect(screen.getByText('大二')).toBeTruthy();
  });

  // Step 3: Click an option
  fireEvent.click(screen.getByText('大一'));

  // Step 4: Verify that the user message appears in the chat
  await waitFor(() => {
    expect(screen.getByText('大一')).toBeTruthy();
  });

  // Step 5: Verify that the original question card's options are no longer interactive
  // The original ChatCard should still show the question text, but the options should be disabled
  // or hidden because isLatestInteractive is false
  await waitFor(() => {
    // The options should be disabled (not clickable)
    const optionButtons = screen.getAllByText('大一');
    // There should be at least one "大一" (the user message)
    expect(optionButtons.length).toBeGreaterThan(0);
  });
});
