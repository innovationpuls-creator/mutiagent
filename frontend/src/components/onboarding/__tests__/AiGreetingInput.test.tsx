import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React, { useEffect } from 'react';
import { afterEach, expect, test, vi, it } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { AiGreetingInput } from '../AiGreetingInput';
import { AiWidgetProvider, useAiWidget } from '../../../context/AiWidgetContext';
import { AuthProvider } from '../../../contexts/AuthContext';

function TestExpandedWrapper({ children }: { children: React.ReactNode }) {
  const { setWidgetState } = useAiWidget();
  useEffect(() => {
    setWidgetState('EXPANDED');
  }, [setWidgetState]);
  return <>{children}</>;
}

function renderWithRouter(ui: React.ReactElement) {
  return render(
    <AuthProvider>
      <AiWidgetProvider>
        <MemoryRouter>
          <TestExpandedWrapper>{ui}</TestExpandedWrapper>
        </MemoryRouter>
      </AiWidgetProvider>
    </AuthProvider>
  );
}

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function ExpandedWidget() {
  const { setWidgetState } = useAiWidget();

  useEffect(() => {
    setWidgetState('EXPANDED');
  }, [setWidgetState]);

  return <AiGreetingInput />;
}

function PendingMessageWidget() {
  const { openWithMessage } = useAiWidget();

  useEffect(() => {
    openWithMessage('开始第一门课');
  }, [openWithMessage]);

  return <AiGreetingInput />;
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

function stubLocalStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  const api = {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
  };
  vi.stubGlobal('localStorage', api);
  return { store, api };
}

function expandTimelineDetailsIfCollapsed() {
  const expandButton = screen.queryByRole('button', { name: /展开详情/ });
  if (expandButton) fireEvent.click(expandButton);
}

function makeRecoveredLearningPath() {
  return {
    schema_version: 'learning_path.v2.course_node',
    learning_goal: {
      target_course_or_skill: 'AI 应用开发',
      goal_type: '项目实践',
      desired_outcome: '完成一个 AI 功能模块',
      four_year_outcome: '形成 AI 应用开发能力',
    },
    learner_baseline: {
      current_grade: '大三',
      major: '软件工程',
      mastered_content: ['Python 基础'],
      weaknesses: ['部署经验不足'],
      constraints: ['时间有限'],
      weekly_available_time: '每周 8 小时',
    },
    planning_rules: {
      node_unit: 'course_node',
      grade_boundary_rule: '按年级拆分',
      sequence_rule: '先基础后项目',
      resource_rule: '每个节点补充学习资源',
    },
    grade_plans: {
      year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '夯实基础', course_nodes: [] },
      year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '建立工程能力', course_nodes: [] },
      year_3: {
        grade_id: 'year_3',
        grade_name: '大三',
        grade_goal: '完成 AI 项目闭环',
        course_nodes: [
          {
            course_node_id: 'year_3_course_1',
            grade_id: 'year_3',
            course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
            time_arrangement: {
              semester_scope: '上学期',
              duration: '6 周',
              pace_reason: '项目驱动',
            },
            course_goal: '完成最小功能闭环',
            prerequisite_node_ids: [],
            chapter_nodes: [],
            core_knowledge_points: [],
            key_points: ['接口接入'],
            difficult_points: ['错误处理'],
            learning_sequence: ['需求拆解', '接口接入'],
            knowledge_relations: [],
            downstream_resource_direction_ids: [],
            acceptance_criteria: ['完成一个可运行模块'],
          },
        ],
      },
      year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '作品集沉淀', course_nodes: [] },
    },
    knowledge_graph: {
      global_relations: [],
      critical_paths: [],
    },
    resource_generation_contract: {
      downstream_agents: [],
      resource_directions: [],
    },
    dynamic_update_contract: {
      trackable_metrics: [],
      update_triggers: [],
      adjustment_strategy: '按周调整',
    },
    current_learning_course: {
      grade_id: 'year_3',
      course_node_id: 'year_3_course_1',
      course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
      course_goal: '完成最小功能闭环',
      time_arrangement: {
        semester_scope: '上学期',
        duration: '6 周',
        pace_reason: '项目驱动',
      },
      current_focus: '需求拆解',
      progress_state: 'in_progress',
      next_action: '继续学习第一章',
    },
  };
}

function makeRecoveredCourseKnowledge() {
  return {
    course_id: 'year_3_course_1',
    course_name: 'AI Agent 开发基础能力搭建',
    grade_year: 'year_3',
    personalization_summary: '围绕项目驱动与工程化补强双线展开。',
    sections: [],
    learning_sequence: [],
    total_estimated_hours: '45 小时',
  };
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

test('clears the composer after a message is submitted', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-clear-input","query":"先看看学习路径"}',
            '',
            'event: message_completed',
            'data: {"full_text":"你的学习路径里已经有这些课程："}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-clear-input","has_profile":true,"has_paths":true,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-clear-input',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '先看看学习路径' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  expect((screen.getByPlaceholderText('输入你的学习情况...') as HTMLTextAreaElement).value).toBe('');

  await waitFor(() => {
    expect(screen.getByText('你的学习路径里已经有这些课程：')).toBeTruthy();
  }, { timeout: 4000 });
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
            'event: session_started',
            'data: {"session_id":"session-1","query":"帮我生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: data_update',
            'data: {"update_type":"profile_loaded","summary":"已加载历史学习画像"}',
            '',
            'event: supervisor_plan',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","reason":"调用 学习路径智能体"}',
            '',
            'event: agent_calling',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体开始处理。","kind":"agent","parallelGroup":"path","dependsOn":["supervisor"]}',
            '',
            'event: agent_result',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","success":true,"message":"学习路径智能体结果返回成功。","kind":"agent","parallelGroup":"path","dependsOn":["supervisor"]}',
            '',
            'event: text_chunk',
            'data: {"chunk":"学习路径"}',
            '',
            'event: text_chunk',
            'data: {"chunk":"已生成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"学习路径已生成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-1","has_profile":true,"has_paths":true,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI 应用开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个 AI 功能模块',
              four_year_outcome: '形成完整项目能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成一个 AI 功能模块并接入 Web 应用',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '围绕平时学习节奏安排',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

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
    const timeline = screen.getByLabelText('Agent run timeline');
    expect(timeline).toBeTruthy();
    expect(timeline.getAttribute('data-surface')).toBe('warm-paper');
    expect(screen.getByText('大学四年课程路径')).toBeTruthy();
  }, { timeout: 10000 });
});

test('keeps the agent timeline when a final profile answer is rendered', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-structured","query":"重新采集画像"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
            '',
            'event: agent_result',
            'data: {"agent":"profile_agent","label":"基础画像智能体","success":true,"message":"基础画像智能体已完成本轮处理。"}',
            '',
            'event: message_completed',
            'data: {"full_text":"基础画像已完成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-structured","has_profile":true,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-structured',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

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
    expect(screen.getByText('基础画像已完成')).toBeTruthy();
    expect(screen.getByLabelText('Agent run timeline')).toBeTruthy();
  }, { timeout: 10000 });

  expandTimelineDetailsIfCollapsed();

  await waitFor(() => {
    expect(screen.getAllByText('基础画像智能体已完成本轮处理。').length).toBeGreaterThan(0);
  }, { timeout: 10000 });
});

test('renders structured profile card after profile agent completes and session state returns profile data', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-profile-card","query":"重新采集画像"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
            '',
            'event: agent_result',
            'data: {"agent":"profile_agent","label":"基础画像智能体","success":true,"message":"基础画像智能体已完成本轮处理。"}',
            '',
            'event: message_completed',
            'data: {"full_text":"基础画像已完成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-profile-card","has_profile":true,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-profile-card',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-profile-card',
        user_uid: 'user-1',
        profile: {
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
            options: [
              {
                label: '继续生成学习路径',
                value: '继续生成学习路径',
                description: '根据当前画像生成今天可执行的课程路径',
                target_fields: [],
                fills: {},
              },
            ],
          },
          text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

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
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://127.0.0.1:8000/api/chat/sessions/session-profile-card',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    );
  }, { timeout: 2000 });

  await waitFor(() => {
    expect(screen.getByText('画像已整理成可继续更新的学习底稿')).toBeTruthy();
    expect(screen.getByText('可继续补充或追问')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
    expect(screen.getByText('软件工程')).toBeTruthy();
  }, { timeout: 4000 });

  expect(screen.getByLabelText('Agent run timeline')).toBeTruthy();
}, 10000);

test('renders collecting profile card and keeps composer in incomplete-profile mode', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-collecting-card","query":"我现在大三，你看看我的个人画像，你推荐什么？"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
            '',
            'event: agent_result',
            'data: {"agent":"profile_agent","label":"基础画像智能体","success":true,"message":"基础画像智能体已完成本轮处理。"}',
            '',
            'event: message_completed',
            'data: {"full_text":"为了生成基础画像，请先告诉我你的专业。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-collecting-card","has_profile":false,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-collecting-card',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-collecting-card',
        user_uid: 'user-1',
        profile: {
          type: 'collecting',
          stage: 'basic_info',
          question_mode: 'question_md',
          confirmed_info: {
            current_grade: '大三',
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
          },
          defaulted_fields: [],
          question_md: '为了生成基础画像，请先告诉我你的专业。',
          question_box: {
            question: '',
            options: [],
          },
          text: '为了生成基础画像，请先告诉我你的专业。',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '我现在大三，你看看我的个人画像，你推荐什么？' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://127.0.0.1:8000/api/chat/sessions/session-collecting-card',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    );
  }, { timeout: 2000 });

  await waitFor(() => {
    expect(screen.getByText('为了生成基础画像，请先告诉我你的专业。')).toBeTruthy();
    expect(screen.getByText('已确认')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
    expect(screen.queryByText('画像已整理成可继续更新的学习底稿')).toBeNull();
  }, { timeout: 4000 });

  expect(screen.getByPlaceholderText('输入你的学习情况...')).toBeTruthy();
  expect(screen.getByLabelText('Agent run timeline')).toBeTruthy();
}, 10000);

test('recovers a persisted basic_profile card from local session cache after refresh', async () => {
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
    'session-session-recover-profile': JSON.stringify({
      userUid: 'user-1',
      savedAt: 1000,
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '重新采集画像',
          status: 'completed',
          timestamp: 1000,
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '基础画像已完成',
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
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-profile');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('画像已整理成可继续更新的学习底稿')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
    expect(screen.getByText('软件工程')).toBeTruthy();
  });

  expect(screen.queryByPlaceholderText('输入你的学习情况...')).toBeNull();
  expect(document.querySelector('.composer-completed-cta-panel .cta-completed-btn')).toBeTruthy();
});

test('recovers a generated basic_profile card from the server when local cache is missing', async () => {
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
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      session_id: 'session-recover-profile-remote',
      user_uid: 'user-1',
      messages: [
        { type: 'human', data: { content: '继续恢复我的画像' } },
        { type: 'ai', data: { content: '基础画像已完成' } },
      ],
      profile: {
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
        summary_text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
      },
      year_learning_paths: null,
      course_knowledge: null,
      updated_at: '2026-06-05T10:00:00Z',
    }),
  }));
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-profile-remote');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('画像已整理成可继续更新的学习底稿')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
    expect(screen.getByText('软件工程')).toBeTruthy();
  });

  expect(screen.queryByPlaceholderText('输入你的学习情况...')).toBeNull();
  expect(document.querySelector('.composer-completed-cta-panel .cta-completed-btn')).toBeTruthy();
});

test('keeps completed-profile composer mode when a cached path-only session stores hasCompleteProfile', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
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
    'session-session-recover-path-complete': JSON.stringify({
      userUid: 'user-1',
      hasCompleteProfile: true,
      savedAt: 1000,
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '继续恢复我的学习路径',
          status: 'completed',
          timestamp: 1000,
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
          status: 'completed',
          timestamp: 1001,
          learningPath: makeRecoveredLearningPath(),
          runTrace: [],
          activeStepId: null,
        },
      ],
    }),
  });
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-path-complete');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('大学四年课程路径')).toBeTruthy();
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
  });

  expect(screen.queryByText('画像已整理成可继续更新的学习底稿')).toBeNull();
  expect(screen.queryByPlaceholderText('输入你的学习情况...')).toBeNull();
  expect(document.querySelector('.composer-completed-cta-panel .cta-completed-btn')).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
});

test('keeps completed-profile composer mode when the server recovers an outline-only session', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      session_id: 'session-recover-outline-complete',
      user_uid: 'user-1',
      messages: [
        { type: 'human', data: { content: '继续恢复我的课程大纲' } },
        { type: 'ai', data: { content: '课程大纲已生成：《AI Agent 开发基础能力搭建》。' } },
      ],
      profile: {
        type: 'basic_profile',
        confirmed_info: {
          current_grade: '大三',
          major: '软件工程',
          learning_stage: '项目实践',
          has_clear_goal: '是',
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
      },
      year_learning_paths: null,
      course_knowledge: makeRecoveredCourseKnowledge(),
      updated_at: '2026-06-05T10:00:00Z',
    }),
  });
  vi.stubGlobal('fetch', fetchMock);
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
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-outline-complete');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('课程大纲 · year_3')).toBeTruthy();
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
  });

  expect(screen.queryByText('画像已整理成可继续更新的学习底稿')).toBeNull();
  expect(screen.queryByPlaceholderText('输入你的学习情况...')).toBeNull();
  expect(document.querySelector('.composer-completed-cta-panel .cta-completed-btn')).toBeTruthy();
  expect(fetchMock).toHaveBeenCalledTimes(1);
});

test('recovers a persisted collecting profile card without marking the profile as completed', async () => {
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
    'session-session-recover-collecting': JSON.stringify({
      userUid: 'user-1',
      savedAt: 1000,
      messages: [
        {
          id: 'user-1',
          role: 'user',
          content: '我现在大三，你看看我的个人画像，你推荐什么？',
          status: 'completed',
          timestamp: 1000,
        },
        {
          id: 'assistant-1',
          role: 'assistant',
          content: '为了生成基础画像，请先告诉我你的专业。',
          status: 'completed',
          timestamp: 1001,
          sessionMessage: {
            type: 'collecting',
            stage: 'basic_info',
            question_mode: 'question_md',
            confirmed_info: {
              current_grade: '大三',
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
            },
            defaulted_fields: [],
            question_md: '为了生成基础画像，请先告诉我你的专业。',
            question_box: {
              question: '',
              options: [],
            },
            text: '为了生成基础画像，请先告诉我你的专业。',
          },
          runTrace: [],
          activeStepId: null,
        },
      ],
    }),
  });
  window.history.replaceState({}, '', '/sprout?session_id=session-recover-collecting');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('为了生成基础画像，请先告诉我你的专业。')).toBeTruthy();
    expect(screen.getByText('已确认')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
  });

  expect(screen.getByPlaceholderText('输入你的学习情况...')).toBeTruthy();
  expect(screen.queryByPlaceholderText('画像已生成，可以继续补充或追问...')).toBeNull();
});

test('renders worker timeline even when stream skips supervisor_plan events', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-no-plan","query":"第一门课程是什么？"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"course_knowledge_agent","label":"课程大纲智能体","message":"课程大纲智能体开始处理本轮请求"}',
            '',
            'event: agent_result',
            'data: {"agent":"course_knowledge_agent","label":"课程大纲智能体","success":true,"summary":"课程大纲智能体结果已生成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"课程大纲已生成：《AI 应用开发基础能力搭建》。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-no-plan","has_profile":true,"has_paths":false,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-no-plan',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-no-plan',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: null,
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI 应用开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '围绕项目驱动与工程化补强双线展开。',
          sections: [],
          learning_sequence: [],
          total_estimated_hours: '45 小时',
        },
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '第一门课程是什么？' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('课程大纲 · year_3')).toBeTruthy();
    expect(screen.getByLabelText('Agent run timeline')).toBeTruthy();
  }, { timeout: 10000 });

  expandTimelineDetailsIfCollapsed();

  await waitFor(() => {
    expect(screen.getAllByText('课程大纲智能体结果已生成').length).toBeGreaterThan(0);
  }, { timeout: 10000 });
});

test('renders retry button for retryable learning path errors and resends retry message', async () => {
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
  const failingStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-retry","query":"帮我生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: error',
            'data: {"message":"学习路径生成失败","retryAction":"retry_learning_path","retryable":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });
  const successStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-retry","query":"重试生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"重新生成中..."}',
            '',
            'event: agent_result',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","success":true,"message":"学习路径智能体结果返回成功。","kind":"agent","parallelGroup":"path","dependsOn":["supervisor"]}',
            '',
            'event: text_chunk',
            'data: {"chunk":"重试成功"}',
            '',
            'event: message_completed',
            'data: {"full_text":"重试成功"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-retry","has_profile":true,"has_paths":true,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-retry',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(failingStream, { status: 200 }))
    .mockResolvedValueOnce(new Response(successStream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-retry',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI 应用开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个 AI 功能模块',
              four_year_outcome: '形成完整项目能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成一个 AI 功能模块并接入 Web 应用',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '围绕平时学习节奏安排',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

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

  const retryButton = await screen.findByRole('button', { name: '重试生成学习路径' });
  expect(retryButton).toBeTruthy();

  fireEvent.click(retryButton);

  await waitFor(() => {
    expect(fetchMock).toHaveBeenNthCalledWith(
      3,
      'http://127.0.0.1:8000/api/chat/message',
      expect.objectContaining({
        body: JSON.stringify({ session_id: 'session-retry', message: '重试生成学习路径' }),
      }),
    );
    expect(fetchMock).toHaveBeenNthCalledWith(
      4,
      'http://127.0.0.1:8000/api/chat/sessions/session-retry',
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
      }),
    );
    expect(screen.getByText('大学四年课程路径')).toBeTruthy();
  });
});

test('treats failed agent_result events as error steps instead of successful completion', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-soft-fail","query":"继续生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"stepId":"learning-path-run","agent":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体开始处理。","kind":"agent"}',
            '',
            'event: agent_result',
            'data: {"stepId":"learning-path-run","agent":"learning_path_agent","label":"学习路径智能体","success":false,"error":"学习路径生成失败","kind":"agent"}',
            '',
            'event: error',
            'data: {"message":"学习路径生成失败","retryAction":"retry_learning_path","retryable":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-soft-fail',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '继续生成学习路径' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getAllByText('学习路径生成失败').length).toBeGreaterThan(0);
    expect(screen.getAllByText('异常').length).toBeGreaterThan(0);
    expect(screen.queryByText('本轮智能体调用已完成')).toBeNull();
  });
});

test('persists a failed session so refresh can recover the retry entrypoint', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const { store, api } = stubLocalStorage({
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
            'event: session_started',
            'data: {"session_id":"session-failed-refresh","query":"继续生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: error',
            'data: {"message":"学习路径生成失败","retryAction":"retry_learning_path","retryable":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-failed-refresh',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

  const view = render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '继续生成学习路径' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getAllByText('学习路径生成失败').length).toBeGreaterThan(0);
    expect(api.setItem).toHaveBeenCalledWith(
      'session-session-failed-refresh',
      expect.any(String),
    );
  });

  const persistedRaw = store['session-session-failed-refresh'];
  expect(persistedRaw).toBeTruthy();
  const persisted = JSON.parse(persistedRaw) as {
    messages: Array<{ status?: string; retryAction?: string | null; error?: string }>;
  };
  expect(persisted.messages.some((message) => message.status === 'error')).toBe(true);
  expect(
    persisted.messages.some((message) => message.retryAction === 'retry_learning_path'),
  ).toBe(true);

  view.unmount();
  window.history.replaceState({}, '', '/sprout?session_id=session-failed-refresh');

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getAllByText('学习路径生成失败').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '重试生成学习路径' })).toBeTruthy();
  });
});

test('persists and recovers a failed session even when the stream errors before session_started', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const { store, api } = stubLocalStorage({
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
  window.history.replaceState({}, '', '/sprout');

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: error',
            'data: {"message":"学习路径生成失败","retryAction":"retry_learning_path","retryable":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-error-before-started',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

  const view = render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '继续生成学习路径' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getAllByText('学习路径生成失败').length).toBeGreaterThan(0);
    expect(window.location.search).toBe('?session_id=session-error-before-started');
    expect(api.setItem).toHaveBeenCalledWith(
      'session-session-error-before-started',
      expect.any(String),
    );
  });

  const persistedRaw = store['session-session-error-before-started'];
  expect(persistedRaw).toBeTruthy();
  const persisted = JSON.parse(persistedRaw) as {
    messages: Array<{ status?: string; retryAction?: string | null; error?: string }>;
  };
  expect(persisted.messages.some((message) => message.status === 'error')).toBe(true);
  expect(
    persisted.messages.some((message) => message.retryAction === 'retry_learning_path'),
  ).toBe(true);

  view.unmount();

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getAllByText('学习路径生成失败').length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: '重试生成学习路径' })).toBeTruthy();
  });
});

test('updates the progress panel as soon as streaming agent events arrive', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-panel","query":"你好"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"memory-history-load","agent":"memory_agent","label":"记忆智能体","message":"正在读取历史对话记录","kind":"system"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"memory-profile-load","agent":"memory_agent","label":"记忆智能体","message":"正在提取用户画像数据","kind":"system"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"memory-path-load","agent":"memory_agent","label":"记忆智能体","message":"正在提取学习路径数据","kind":"system"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"memory-outline-load","agent":"memory_agent","label":"记忆智能体","message":"正在提取课程大纲数据","kind":"system"}',
            '',
            'event: agent_result',
            'data: {"stepId":"memory-context-load","agent":"memory_agent","label":"记忆智能体","success":true,"summary":"历史对话、用户画像、学习路径与课程大纲已完成状态组装","kind":"system"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"intent-routing","agent":"intent_agent","label":"意图识别智能体","message":"正在判断本轮要调用的智能体","kind":"route"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"profile-run","agent":"profile_agent","label":"基础画像智能体","message":"基础画像智能体开始处理。"}',
            '',
            '',
          ].join('\n'),
        ),
      );

      setTimeout(() => {
        controller.enqueue(
          encoder.encode(
            [
              'event: agent_result',
              'data: {"stepId":"profile-run","agent":"profile_agent","label":"基础画像智能体","success":true,"summary":"基础画像智能体已完成本轮处理。"}',
              '',
              'event: message_completed',
              'data: {"full_text":"基础画像已完成"}',
              '',
              'event: session_completed',
              'data: {"session_id":"session-panel","has_profile":true,"has_paths":false,"has_outline":false}',
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      }, 80);
    },
  });

  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-panel',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 })));

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '你好' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.queryByText(/Unexpected non-whitespace character after JSON/)).toBeNull();
    expect(screen.getAllByText('记忆智能体').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正在读取历史对话记录').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正在提取用户画像数据').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正在提取学习路径数据').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正在提取课程大纲数据').length).toBeGreaterThan(0);
    expect(screen.getAllByText('意图识别智能体').length).toBeGreaterThan(0);
    expect(screen.getAllByText('正在判断本轮要调用的智能体').length).toBeGreaterThan(0);
    expect(screen.getAllByText('基础画像智能体').length).toBeGreaterThan(0);
    expect(screen.getAllByText('基础画像智能体开始处理。').length).toBeGreaterThan(0);
    expect(screen.getAllByText('运行中').length).toBeGreaterThan(0);
  });

  await waitFor(() => {
    expect(screen.getByText('基础画像已完成')).toBeTruthy();
    expect(screen.getAllByText('本轮智能体调用已完成').length).toBeGreaterThan(0);
  });
});

test('auto-sends the pending start-course message when the widget opens from sprout', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-course","query":"开始第一门课"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","message":"课程知识智能体开始处理。"}',
            '',
            'event: agent_result',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","success":true,"message":"课程知识智能体已完成本轮处理。"}',
            '',
            'event: message_completed',
            'data: {"full_text":"课程大纲已生成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-course","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-course',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-course',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可演示的 Agent 模块',
              four_year_outcome: '形成项目交付能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
              course_goal: '完成最小功能闭环',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程推进',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入与最小闭环演示。',
          sections: [
            {
              section_id: '1',
              parent_section_id: null,
              depth: 1,
              title: '需求拆解',
              order_index: 1,
              description: '确认功能边界与验收标准。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
            {
              section_id: '1.1',
              parent_section_id: '1',
              depth: 2,
              title: '学习目标',
              order_index: 2,
              description: '明确本章完成后的理解深度与产出目标。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
            {
              section_id: '1.2',
              parent_section_id: '1',
              depth: 2,
              title: '任务拆解',
              order_index: 3,
              description: '把本章拆成可执行的实现与练习任务。',
              key_knowledge_points: ['任务拆分', '演示路径'],
            },
            {
              section_id: '1.3',
              parent_section_id: '1',
              depth: 2,
              title: '检查点',
              order_index: 4,
              description: '确认是否具备进入下一章的条件。',
              key_knowledge_points: ['完成标准', '推进条件'],
            },
          ],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8-12 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <PendingMessageWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          url === 'http://127.0.0.1:8000/api/chat/start'
          && init?.body === JSON.stringify({ query: '开始第一门课' }),
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([url, init]) =>
          url === 'http://127.0.0.1:8000/api/chat/message'
          && init?.body === JSON.stringify({ session_id: 'session-course', message: '开始第一门课' }),
      ),
    ).toBe(true);
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === 'http://127.0.0.1:8000/api/chat/sessions/session-course',
      ),
    ).toBe(true);
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
    expect(screen.getByText('先完成需求拆解，再进入接口接入与最小闭环演示。')).toBeTruthy();
    expect(screen.getByText('推荐学习步骤')).toBeTruthy();
    expect(screen.getAllByText('第一章：需求拆解').length).toBeGreaterThan(0);
    expect(screen.getByText('1.1 学习目标')).toBeTruthy();
    expect(screen.getAllByText('功能边界').length).toBeGreaterThan(0);
  });
});

test('renders both learning path and course outline when the same turn stores both structured results', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-both-structured","query":"开始第一门课"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"learning-path-run","agent":"learning_path_agent","label":"学习路径智能体","message":"开始生成学习路径"}',
            '',
            'event: agent_result',
            'data: {"stepId":"learning-path-run","agent":"learning_path_agent","label":"学习路径智能体","success":true,"summary":"学习路径已生成"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","message":"开始生成课程大纲"}',
            '',
            'event: agent_result',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","success":true,"summary":"课程大纲已生成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"学习路径和课程大纲已生成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-both-structured","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-both-structured',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-both-structured',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可演示的 Agent 模块',
              four_year_outcome: '形成项目交付能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
              course_goal: '完成最小功能闭环',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程推进',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入与最小闭环演示。',
          sections: [
            {
              section_id: '1',
              parent_section_id: null,
              depth: 1,
              title: '需求拆解',
              order_index: 1,
              description: '确认功能边界与验收标准。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
          ],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8-12 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <PendingMessageWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => {
    expect(screen.getByText('学习路径 · learning_path.v2.course_node')).toBeTruthy();
    expect(screen.getByText('课程大纲 · year_3')).toBeTruthy();
  });
});

test('notifies leaf page to refresh after course outline generation stores structured data', async () => {
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
  const listener = vi.fn<(event: CustomEvent<{ courseId: string }>) => void>();
  window.addEventListener(
    'mutiagent-leaf-generation-completed',
    listener as EventListener,
  );

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-outline-refresh","query":"帮我生成AI Agent 开发基础能力搭建的大纲"}',
            '',
            'event: agent_calling',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","message":"开始生成课程大纲"}',
            '',
            'event: agent_result',
            'data: {"stepId":"course-knowledge-run","agent":"course_knowledge_agent","label":"课程知识智能体","success":true,"summary":"课程大纲已生成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"课程大纲已生成：《AI Agent 开发基础能力搭建》。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-outline-refresh","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-refresh',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-refresh',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: makeRecoveredLearningPath(),
        },
        course_knowledge: makeRecoveredCourseKnowledge(),
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <PendingMessageWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  await waitFor(() => expect(listener).toHaveBeenCalled());
  expect(listener.mock.calls.at(-1)?.[0].detail).toEqual({
    courseId: 'year_3_course_1',
    reason: 'course_outline',
  });

  window.removeEventListener(
    'mutiagent-leaf-generation-completed',
    listener as EventListener,
  );
});

test('reuses the same session after profile completion instead of creating a new session', async () => {
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
  const firstStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-follow-up","query":"我现在大三，软件工程专业"}',
            '',
            'event: agent_calling',
            'data: {"agent":"profile_agent","label":"基础画像智能体","message":"开始更新画像"}',
            '',
            'event: agent_result',
            'data: {"agent":"profile_agent","label":"基础画像智能体","success":true,"summary":"画像已完成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"基础画像已完成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-follow-up","has_profile":true,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const secondStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-follow-up","query":"继续帮我生成学习路径"}',
            '',
            'event: agent_calling',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","message":"开始生成学习路径"}',
            '',
            'event: agent_result',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","success":true,"summary":"学习路径已生成"}',
            '',
            'event: message_completed',
            'data: {"full_text":"学习路径已生成"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-follow-up","has_profile":true,"has_paths":true,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-follow-up',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(firstStream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-follow-up',
        user_uid: 'user-1',
        profile: {
          type: 'basic_profile',
          stage: 'generated',
          question_mode: 'none',
          confirmed_info: {
            current_grade: '大三',
            major: '软件工程',
            learning_stage: '专业提升',
            has_clear_goal: '有',
            learning_method_preference: '项目驱动',
            learning_pace_preference: '稳步推进',
            content_preference: ['项目实践'],
            need_guidance: '需要',
            knowledge_foundation: '中等',
            strengths: '执行力强',
            weaknesses: '系统设计经验不足',
            experience: '有课程项目经验',
            short_term_goal: '补齐 Agent 开发基础',
            long_term_goal: '能独立交付 Agent 项目',
            weekly_available_time: '每周 8 小时',
            constraints: '平时课程较多',
          },
          defaulted_fields: [],
          question_md: '',
          question_box: { question: '', options: [] },
          text: '基础画像已完成',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    })
    .mockResolvedValueOnce(new Response(secondStream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-follow-up',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可演示的 Agent 模块',
              four_year_outcome: '形成项目交付能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
              course_goal: '完成最小功能闭环',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程推进',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-04T10:10:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '我现在大三，软件工程专业' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('基础画像已完成')).toBeTruthy();
  });

  expect(screen.queryByPlaceholderText('输入你的学习情况...')).toBeNull();
  const ctaBtn = document.querySelector('.composer-completed-cta-panel .cta-completed-btn');
  expect(ctaBtn).toBeTruthy();

  fireEvent.click(ctaBtn!);

  expect(mockNavigate).toHaveBeenCalledWith('/branch', { state: { justGeneratedProfile: true } });

  const startCalls = fetchMock.mock.calls.filter(
    ([url]) => url === 'http://127.0.0.1:8000/api/chat/start',
  );
  const messageCalls = fetchMock.mock.calls.filter(
    ([url]) => url === 'http://127.0.0.1:8000/api/chat/message',
  );

  expect(startCalls).toHaveLength(1);
  expect(messageCalls).toHaveLength(1);
  expect(messageCalls[0]?.[1]?.body).toBe(
    JSON.stringify({ session_id: 'session-follow-up', message: '我现在大三，软件工程专业' }),
  );
});

test('loads saved course outline when stream marks course knowledge loaded', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-outline-loaded","query":"给我看看这个课的大纲"}',
            '',
            'event: data_update',
            'data: {"update_type":"course_knowledge_loaded","label":"课程大纲","summary":"已从数据库读取课程大纲"}',
            '',
            'event: message_completed',
            'data: {"full_text":"课程大纲 · year_3\\nAI Agent 开发基础能力搭建"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-outline-loaded","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-loaded',
        reply_text: 'greeting',
        profile: { type: 'basic_profile' },
        year_learning_paths: { year_3: {} },
        course_knowledge: { course_id: 'year_3_course_1' },
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-loaded',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: null,
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '直接展示数据库中已有的大纲。',
          sections: [
            {
              section_id: '1',
              parent_section_id: null,
              depth: 1,
              title: '需求拆解',
              order_index: 1,
              description: '确认功能边界与验收标准。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
          ],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '给我看看这个课的大纲' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === 'http://127.0.0.1:8000/api/chat/sessions/session-outline-loaded',
      ),
    ).toBe(true);
    expect(screen.getByText('课程大纲 · year_3')).toBeTruthy();
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
    expect(screen.getByText('直接展示数据库中已有的大纲。')).toBeTruthy();
  });
});

test('loads saved learning path when only the final completion text says 学习路径已生成', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-path-fallback-text","query":"下一步"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: message_completed',
            'data: {"full_text":"学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-path-fallback-text","has_profile":true,"has_paths":true,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-path-fallback-text',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-path-fallback-text',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: makeRecoveredLearningPath(),
        },
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '下一步' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === 'http://127.0.0.1:8000/api/chat/sessions/session-path-fallback-text',
      ),
    ).toBe(true);
    expect(screen.getByText('大学四年课程路径')).toBeTruthy();
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
  });
});

test('loads saved course outline when only the final completion text says 课程大纲已生成', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-outline-fallback-text","query":"开始第一门课"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: message_completed',
            'data: {"full_text":"课程大纲已生成：《AI Agent 开发基础能力搭建》。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-outline-fallback-text","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-fallback-text',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-outline-fallback-text',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: null,
        course_knowledge: makeRecoveredCourseKnowledge(),
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '开始第一门课' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(
      fetchMock.mock.calls.some(
        ([url]) => url === 'http://127.0.0.1:8000/api/chat/sessions/session-outline-fallback-text',
      ),
    ).toBe(true);
    expect(screen.getByText('课程大纲 · year_3')).toBeTruthy();
    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
    expect(screen.getByText('围绕项目驱动与工程化补强双线展开。')).toBeTruthy();
  });
});

test('does not replace a plain chat reply with historical course outline from session state', async () => {
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
            'event: session_started',
            'data: {"session_id":"session-chat","query":"你好"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"intent_agent","label":"意图识别智能体","message":"正在判断本轮要调用的智能体","kind":"route"}',
            '',
            'event: message_completed',
            'data: {"full_text":"你好，我在这里帮你规划学习。"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-chat","has_profile":true,"has_paths":true,"has_outline":true}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-chat',
        reply_text: 'greeting',
        profile: { type: 'basic_profile' },
        year_learning_paths: { year_3: {} },
        course_knowledge: { course_id: 'year_3_course_1' },
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-chat',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可演示的 Agent 模块',
              four_year_outcome: '形成项目交付能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
              course_goal: '完成最小功能闭环',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程推进',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入与最小闭环演示。',
          sections: [
            {
              section_id: '1',
              parent_section_id: null,
              depth: 1,
              title: '需求拆解',
              order_index: 1,
              description: '确认功能边界与验收标准。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
            {
              section_id: '1.1',
              parent_section_id: '1',
              depth: 2,
              title: '学习目标',
              order_index: 2,
              description: '明确本章完成后的理解深度与产出目标。',
              key_knowledge_points: ['功能边界', '验收标准'],
            },
            {
              section_id: '1.2',
              parent_section_id: '1',
              depth: 2,
              title: '任务拆解',
              order_index: 3,
              description: '把本章拆成可执行的实现与练习任务。',
              key_knowledge_points: ['任务拆分', '演示路径'],
            },
            {
              section_id: '1.3',
              parent_section_id: '1',
              depth: 2,
              title: '检查点',
              order_index: 4,
              description: '确认是否具备进入下一章的条件。',
              key_knowledge_points: ['完成标准', '推进条件'],
            },
          ],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8-12 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '你好' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('你好，我在这里帮你规划学习。')).toBeTruthy();
  });

  expect(screen.queryByText('课程大纲 · year_3')).toBeNull();
  expect(
    fetchMock.mock.calls.some(
      ([url]) => url === 'http://127.0.0.1:8000/api/chat/sessions/session-chat',
    ),
  ).toBe(false);
});

test('writes session_id to URL and local cache as soon as session_started arrives', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const { api: localStorageApi } = stubLocalStorage({
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
  window.history.replaceState({}, '', '/sprout');

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-streaming-anchor","query":"帮我生成学习路径"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: agent_calling',
            'data: {"agent":"learning_path_agent","label":"学习路径智能体","message":"学习路径智能体开始处理。"}',
            '',
            '',
          ].join('\n'),
        ),
      );

      setTimeout(() => {
        controller.enqueue(
          encoder.encode(
            [
              'event: message_completed',
              'data: {"full_text":"学习路径已生成"}',
              '',
              'event: session_completed',
              'data: {"session_id":"session-streaming-anchor","has_profile":true,"has_paths":true,"has_outline":false}',
              '',
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      }, 50);
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-streaming-anchor',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }))
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-streaming-anchor',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI 应用开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个 AI 功能模块',
              four_year_outcome: '形成完整项目能力',
            },
            learner_baseline: {
              current_grade: '大三',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后项目',
              resource_rule: '每个节点对应资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
              year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
              year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
            },
            knowledge_graph: {
              global_relations: [],
              critical_paths: [],
            },
            resource_generation_contract: {
              downstream_agents: [],
              resource_directions: [],
            },
            dynamic_update_contract: {
              trackable_metrics: [],
              update_triggers: [],
              adjustment_strategy: '按周调整',
            },
            current_learning_course: {
              grade_id: 'year_3',
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成一个 AI 功能模块并接入 Web 应用',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '围绕平时学习节奏安排',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    });
  vi.stubGlobal('fetch', fetchMock);

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
    expect(window.location.search).toBe('?session_id=session-streaming-anchor');
    expect(localStorageApi.setItem).toHaveBeenCalledWith(
      'session-session-streaming-anchor',
      expect.stringContaining('"messages"'),
    );
  });

  await waitFor(() => {
    expect(screen.getByText('学习路径已生成')).toBeTruthy();
  });
}, 10000);

test('clears a stale session anchor after 会话不存在 and starts a new session on the next send', async () => {
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
  window.history.replaceState({}, '', '/sprout');

  const encoder = new TextEncoder();
  const firstStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-stale","query":"第一次消息"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: text_chunk',
            'data: {"chunk":"第一次成功"}',
            '',
            'event: message_completed',
            'data: {"full_text":"第一次成功"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-stale","has_profile":false,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const thirdStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-renewed","query":"第三次消息"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: text_chunk',
            'data: {"chunk":"第三次成功"}',
            '',
            'event: message_completed',
            'data: {"full_text":"第三次成功"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-renewed","has_profile":false,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-stale',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(firstStream, { status: 200 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: '会话不存在' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-renewed',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(thirdStream, { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');

  fireEvent.change(input, { target: { value: '第一次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('第一次成功')).toBeTruthy();
  });
  expect(window.location.search).toContain('session_id=session-stale');

  fireEvent.change(input, { target: { value: '第二次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getAllByText('会话不存在').length).toBeGreaterThan(0);
  });
  expect(window.location.search).not.toContain('session_id=');

  fireEvent.change(input, { target: { value: '第三次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('第三次成功')).toBeTruthy();
  });

  expect(fetchMock).toHaveBeenNthCalledWith(
    3,
    'http://127.0.0.1:8000/api/chat/message',
    expect.objectContaining({
      body: JSON.stringify({ session_id: 'session-stale', message: '第二次消息' }),
    }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    4,
    'http://127.0.0.1:8000/api/chat/start',
    expect.objectContaining({
      body: JSON.stringify({ query: '第三次消息' }),
    }),
  );
  expect(fetchMock).toHaveBeenNthCalledWith(
    5,
    'http://127.0.0.1:8000/api/chat/message',
    expect.objectContaining({
      body: JSON.stringify({ session_id: 'session-renewed', message: '第三次消息' }),
    }),
  );
  expect(window.location.search).toContain('session_id=session-renewed');
}, 10000);

test('starts a clean local conversation after 会话不存在 instead of persisting old messages into the renewed session cache', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  const { store } = stubLocalStorage({
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
  window.history.replaceState({}, '', '/sprout');

  const encoder = new TextEncoder();
  const firstStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-stale-clean","query":"第一次消息"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: text_chunk',
            'data: {"chunk":"第一次成功"}',
            '',
            'event: message_completed',
            'data: {"full_text":"第一次成功"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-stale-clean","has_profile":false,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const thirdStream = new ReadableStream({
    start(controller) {
      controller.enqueue(
        encoder.encode(
          [
            'event: session_started',
            'data: {"session_id":"session-renewed-clean","query":"第三次消息"}',
            '',
            'event: supervisor_thinking',
            'data: {"message":"正在分析你的需求..."}',
            '',
            'event: text_chunk',
            'data: {"chunk":"第三次成功"}',
            '',
            'event: message_completed',
            'data: {"full_text":"第三次成功"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-renewed-clean","has_profile":false,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-stale-clean',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(firstStream, { status: 200 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: '会话不存在' }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-renewed-clean',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(thirdStream, { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  const input = await screen.findByPlaceholderText('输入你的学习情况...');

  fireEvent.change(input, { target: { value: '第一次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('第一次成功')).toBeTruthy();
  });

  fireEvent.change(input, { target: { value: '第二次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getAllByText('会话不存在').length).toBeGreaterThan(0);
  });

  fireEvent.change(input, { target: { value: '第三次消息' } });
  fireEvent.click(screen.getByLabelText('发送消息'));

  await waitFor(() => {
    expect(screen.getByText('第三次成功')).toBeTruthy();
  });

  expect(screen.queryByText('第一次成功')).toBeNull();
  expect(screen.queryByText('第二次消息')).toBeNull();

  const renewedRaw = store['session-session-renewed-clean'];
  expect(renewedRaw).toBeTruthy();
  const renewed = JSON.parse(renewedRaw) as {
    messages: Array<{ role: string; content: string }>;
  };
  expect(renewed.messages).toEqual([
    expect.objectContaining({ role: 'user', content: '第三次消息' }),
    expect.objectContaining({ role: 'assistant', content: '第三次成功' }),
  ]);
}, 10000);

test('allows using handwriting canvas, previews sketch, and submits message with image attachment', async () => {
  vi.stubGlobal('scrollTo', vi.fn());
  HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
    scale: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    stroke: vi.fn(),
    clearRect: vi.fn(),
  });
  HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue('data:image/png;base64,fake-data');
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
            'event: session_started',
            'data: {"session_id":"session-with-attachment","query":"这里是手写内容"}',
            '',
            'event: message_completed',
            'data: {"full_text":"已收到您的图片"}',
            '',
            'event: session_completed',
            'data: {"session_id":"session-with-attachment","has_profile":true,"has_paths":false,"has_outline":false}',
            '',
          ].join('\n'),
        ),
      );
      controller.close();
    },
  });

  const fetchMock = vi.fn()
    .mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'session-with-attachment',
        reply_text: 'greeting',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    })
    .mockResolvedValueOnce(new Response(stream, { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);

  render(
    <AuthProvider>
      <AiWidgetProvider>
        <ExpandedWidget />
      </AiWidgetProvider>
    </AuthProvider>,
  );

  // Click on the handwriting pen tool button to open canvas
  const penButton = await screen.findByLabelText('手写/绘图输入');
  fireEvent.click(penButton);

  // The dialog should be in the document
  expect(screen.getByRole('dialog')).toBeTruthy();
  expect(screen.getByText('手写笔记/草图')).toBeTruthy();

  // Click '确认导出' to mock canvas export
  const confirmButton = screen.getByText('确认导出');
  fireEvent.click(confirmButton);

  // Dialog should be closed, and preview image should be shown
  await waitFor(() => {
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  const previewImg = screen.getByAltText('Preview');
  expect(previewImg).toBeTruthy();
  expect(previewImg.getAttribute('src')).toBe('data:image/png;base64,fake-data');

  // Input some optional text
  const input = screen.getByPlaceholderText('输入你的学习情况...');
  fireEvent.change(input, { target: { value: '这里是手写内容' } });

  // Click submit message
  fireEvent.click(screen.getByLabelText('发送消息'));

  // Ensure message is sent and preview is cleared
  await waitFor(() => {
    expect(screen.queryByAltText('Preview')).toBeNull();
    expect((screen.getByPlaceholderText('输入你的学习情况...') as HTMLTextAreaElement).value).toBe('');
  });

  // Verify fetch mock was called with correct payload containing image_attachment
  await waitFor(() => {
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const lastFetchBody = JSON.parse(fetchMock.mock.calls[1][1].body);
    expect(lastFetchBody.image_attachment).toBe('data:image/png;base64,fake-data');
    expect(lastFetchBody.message).toBe('这里是手写内容');
  });

  // Check that the image is rendered in the message flow
  await waitFor(() => {
    const bubbleImg = screen.getByAltText('Attachment');
    expect(bubbleImg).toBeTruthy();
    expect(bubbleImg.getAttribute('src')).toBe('data:image/png;base64,fake-data');
    expect(screen.getByText('已收到您的图片')).toBeTruthy();
  });
}, 10000);

it('renders progress bar indicating the active collection stage', () => {
  renderWithRouter(<AiGreetingInput />);
  expect(screen.getByText(/欢迎！告诉我你的年级、专业或学习方向。/)).toBeTruthy();
  expect(screen.getByText('基础信息')).toBeTruthy();
  expect(screen.getByText('学习偏好')).toBeTruthy();
  expect(screen.getByText('能力基础')).toBeTruthy();
  expect(screen.getByText('目标约束')).toBeTruthy();
});
