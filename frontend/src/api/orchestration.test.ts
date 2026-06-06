import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchSessionRecoveryData, fetchSessionState, startSession, streamSession, type SessionAgentEvent } from './orchestration';

function makeCompleteProfile() {
  return {
    type: 'basic_profile',
    stage: 'generated',
    question_mode: 'question_box',
    confirmed_info: {
      current_grade: '大三',
      major: '软件工程',
      learning_stage: '项目实践',
      has_clear_goal: '是',
      learning_method_preference: '项目驱动学习',
      learning_pace_preference: '按项目里程碑推进',
      content_preference: ['代码实践'],
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
    text: '画像已生成',
  };
}

function makeLearningPath() {
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

function makeCourseKnowledge() {
  return {
    course_id: 'year_3_course_1',
    course_name: 'AI Agent 开发基础能力搭建',
    grade_year: 'year_3',
    personalization_summary: '先完成需求拆解，再进入接口接入。',
    sections: [],
    learning_sequence: ['第一章：需求拆解'],
    total_estimated_hours: '8 小时',
  };
}

describe('startSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('POSTs to /api/chat/start and returns a SessionTurn', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-1',
        reply_text: '你好！请告诉我你的基本情况。',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const turn = await startSession('token-1', '你好');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/chat/start',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          Authorization: 'Bearer token-1',
        }),
        body: JSON.stringify({ query: '你好' }),
      }),
    );
    expect(turn.sessionId).toBe('sess-1');
    expect(turn.text).toBe('你好！请告诉我你的基本情况。');
    expect(turn.hasProfile).toBe(false);
    expect(turn.hasPaths).toBe(false);
    expect(turn.hasOutline).toBe(false);
  });

  it('reflects profile/path/outline presence from start response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-2',
        reply_text: null,
        profile: makeCompleteProfile(),
        year_learning_paths: { year_3: makeLearningPath() },
        course_knowledge: makeCourseKnowledge(),
      }),
    }));

    const turn = await startSession('token-1', '你好');
    expect(turn.hasProfile).toBe(true);
    expect(turn.hasPaths).toBe(true);
    expect(turn.hasOutline).toBe(true);
  });

  it('does not mark collecting profile as completed on start response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-collecting',
        reply_text: null,
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
          question_box: { question: '', options: [] },
          text: '为了生成基础画像，请先告诉我你的专业。',
        },
        year_learning_paths: null,
        course_knowledge: null,
      }),
    }));

    const turn = await startSession('token-1', '你好');

    expect(turn.hasProfile).toBe(false);
  });

  it('does not mark summary-only legacy basic_profile as completed on start response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-summary-only',
        reply_text: null,
        profile: {
          type: 'basic_profile',
          summary_text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
        },
        year_learning_paths: null,
        course_knowledge: null,
      }),
    }));

    const turn = await startSession('token-1', '你好');

    expect(turn.hasProfile).toBe(false);
    expect(turn.hasPaths).toBe(false);
    expect(turn.hasOutline).toBe(false);
  });

  it('does not mark unsupported postgraduate basic_profile as completed on start response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-postgraduate-profile',
        reply_text: null,
        profile: {
          ...makeCompleteProfile(),
          confirmed_info: {
            ...makeCompleteProfile().confirmed_info,
            current_grade: '研一',
          },
        },
        year_learning_paths: null,
        course_knowledge: null,
      }),
    }));

    const turn = await startSession('token-1', '你好');

    expect(turn.hasProfile).toBe(false);
    expect(turn.hasPaths).toBe(false);
    expect(turn.hasOutline).toBe(false);
  });

  it('rejects malformed start response shell', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        reply_text: '你好！请告诉我你的基本情况。',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    }));

    await expect(startSession('token-1', '你好')).rejects.toThrow('会话数据格式不正确');
  });

  it('throws on non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      json: async () => ({ detail: 'Unauthorized' }),
    }));

    await expect(startSession('bad-token', '你好')).rejects.toThrow('Unauthorized');
  });
});

describe('streamSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function makeSseStream(lines: string[]): ReadableStream {
    const encoder = new TextEncoder();
    return new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode(lines.join('\n')));
        controller.close();
      },
    });
  }

  it('creates a session via /api/chat/start then streams via /api/chat/message', async () => {
    const fetchMock = vi.fn()
      // First call: /api/chat/start
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          session_id: 'sess-stream-1',
          reply_text: 'greeting',
          profile: null,
          year_learning_paths: null,
          course_knowledge: null,
        }),
      })
      // Second call: /api/chat/message (SSE)
      .mockResolvedValueOnce(new Response(
        makeSseStream([
          'event: session_started\ndata: {"session_id":"sess-stream-1","query":"hi"}\n\n',
          'event: supervisor_thinking\ndata: {"message":"正在分析..."}\n\n',
          'event: text_chunk\ndata: {"chunk":"你好"}\n\n',
          'event: text_chunk\ndata: {"chunk":"同学"}\n\n',
          'event: message_completed\ndata: {"full_text":"你好同学"}\n\n',
          'event: session_completed\ndata: {"session_id":"sess-stream-1","has_profile":false,"has_paths":false,"has_outline":false}\n\n',
        ]),
        { status: 200 },
      ));

    vi.stubGlobal('fetch', fetchMock);
    const events: SessionAgentEvent[] = [];

    const turn = await streamSession('token-1', 'hi', null, (e) => events.push(e));

    // Should have called start first
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8000/api/chat/start');

    // Second call should be the message SSE endpoint
    expect(fetchMock.mock.calls[1][0]).toBe('http://127.0.0.1:8000/api/chat/message');
    expect(fetchMock.mock.calls[1][1].method).toBe('POST');

    expect(turn.sessionId).toBe('sess-stream-1');
    expect(turn.text).toBe('你好同学');
    expect(events.map((e) => e.event)).toEqual([
      'session_started',
      'supervisor_thinking',
      'text_chunk',
      'text_chunk',
      'message_completed',
      'session_completed',
    ]);
  });

  it('reuses existing sessionId without calling /api/chat/start', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(
      makeSseStream([
        'event: text_chunk\ndata: {"chunk":"ok"}\n\n',
        'event: message_completed\ndata: {"full_text":"ok"}\n\n',
        'event: session_completed\ndata: {"session_id":"existing-sess","has_profile":true,"has_paths":true,"has_outline":false}\n\n',
      ]),
      { status: 200 },
    ));
    vi.stubGlobal('fetch', fetchMock);

    const turn = await streamSession('token-1', 'next', 'existing-sess', () => {});

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe('http://127.0.0.1:8000/api/chat/message');
    expect(turn.sessionId).toBe('existing-sess');
    expect(turn.hasProfile).toBe(true);
    expect(turn.hasPaths).toBe(true);
    expect(turn.hasOutline).toBe(false);
  });

  it('throws on error event', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ session_id: 's', reply_text: '', profile: null, year_learning_paths: null, course_knowledge: null }),
    }).mockResolvedValueOnce(new Response(
      makeSseStream([
        'event: error\ndata: {"message":"服务出错","recoverable":true}\n\n',
      ]),
      { status: 200 },
    )));

    await expect(streamSession('t', 'q', null, () => {})).rejects.toThrow('服务出错');
  });

  it('keeps the started session_id when an error arrives before session_started', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        session_id: 'sess-error-before-started',
        reply_text: '',
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
      }),
    }).mockResolvedValueOnce(new Response(
      makeSseStream([
        'event: supervisor_thinking\ndata: {"message":"正在分析..."}\n\n',
        'event: error\ndata: {"message":"服务出错","recoverable":true}\n\n',
      ]),
      { status: 200 },
    )));

    await expect(streamSession('t', 'q', null, () => {})).rejects.toMatchObject({
      name: 'SessionStreamError',
      message: '服务出错',
      sessionId: 'sess-error-before-started',
    });
  });

  it('preserves retry metadata from SSE error events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ session_id: 's', reply_text: '', profile: null, year_learning_paths: null, course_knowledge: null }),
    }).mockResolvedValueOnce(new Response(
      makeSseStream([
        'event: error\ndata: {"message":"学习路径生成失败","stepId":"learning-path-run","retryable":true,"retryAction":"retry_learning_path"}\n\n',
      ]),
      { status: 200 },
    )));

    const events: SessionAgentEvent[] = [];

    await expect(streamSession('t', 'q', null, (event) => {
      events.push(event);
    })).rejects.toThrow('学习路径生成失败');

    expect(events[0]).toMatchObject({
      event: 'error',
      stepId: 'learning-path-run',
      retryable: true,
      retryAction: 'retry_learning_path',
    });
  });

  it('preserves kind and status metadata from SSE events', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce({
      ok: true,
      json: async () => ({ session_id: 's', reply_text: '', profile: null, year_learning_paths: null, course_knowledge: null }),
    }).mockResolvedValueOnce(new Response(
      makeSseStream([
        'event: agent_calling\ndata: {"message":"正在读取历史对话记录","stepId":"memory-history-load","kind":"system","status":"running"}\n\n',
        'event: message_completed\ndata: {"full_text":"完成"}\n\n',
        'event: session_completed\ndata: {"session_id":"s","has_profile":false,"has_paths":false,"has_outline":false}\n\n',
      ]),
      { status: 200 },
    )));

    const events: SessionAgentEvent[] = [];

    await streamSession('t', 'q', null, (event) => {
      events.push(event);
    });

    expect(events[0]).toMatchObject({
      event: 'agent_calling',
      stepId: 'memory-history-load',
      kind: 'system',
      status: 'running',
    });
  });
});

describe('fetchSessionState', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('returns structured learning path and course outline from session state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-structured',
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
            content_preference: ['代码实践'],
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
          text: '【基础学习画像总结】大三软件工程学生。',
        },
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可部署的 Agent 项目',
              four_year_outcome: '具备 AI 应用开发能力',
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
              resource_rule: '每个节点都提供资源方向',
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
                pace_reason: '配合课程安排',
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
          personalization_summary: '先完成需求拆解，再完成接口接入。',
          sections: [
            {
              section_id: '1',
              parent_section_id: null,
              depth: 1,
              title: '需求拆解',
              order_index: 1,
              description: '确认边界。',
              key_knowledge_points: ['功能边界'],
            },
          ],
          learning_sequence: ['1'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

    const result = await fetchSessionState('token-1', 'sess-structured');

    expect(result.profile?.type).toBe('basic_profile');
    expect(result.learningPath?.current_learning_course.course_node_id).toBe('year_3_course_1');
    expect(result.courseKnowledge?.course_id).toBe('year_3_course_1');
  });

  it('drops learning path from session state when current progress_state is unsupported', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-invalid-progress',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            ...makeLearningPath(),
            current_learning_course: {
              ...makeLearningPath().current_learning_course,
              progress_state: 'paused',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

    const result = await fetchSessionState('token-1', 'sess-invalid-progress');

    expect(result.learningPath).toBeNull();
    expect(result.courseKnowledge).toBeNull();
  });

  it('returns a structured learning path when session state contains multiple year paths', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-multi-year',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_2: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: '数据结构',
              goal_type: '课程学习',
              desired_outcome: '完成数据结构课程',
              four_year_outcome: '完成计算机基础课程体系',
            },
            learner_baseline: {
              current_grade: '大二',
              major: '计算机科学与技术',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 6 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后进阶',
              resource_rule: '每个节点都提供资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '核心课程', course_nodes: [] },
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
              grade_id: 'year_2',
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '数据结构基础',
              course_goal: '掌握线性表、树和图',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '8 周',
                pace_reason: '配合课程安排',
              },
              current_focus: '线性表',
              progress_state: 'in_progress',
              next_action: '继续学习树结构',
            },
          },
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可部署的 Agent 项目',
              four_year_outcome: '具备 AI 应用开发能力',
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
              resource_rule: '每个节点都提供资源方向',
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
                pace_reason: '配合课程安排',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: {
          course_id: 'year_2_course_1',
          course_name: '数据结构基础',
          grade_year: 'year_2',
          personalization_summary: '先完成线性表，再进入树结构。',
          sections: [],
          learning_sequence: ['线性表', '树结构'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

    const result = await fetchSessionState('token-1', 'sess-multi-year');

    expect(result.learningPath?.current_learning_course.course_node_id).toBe('year_2_course_1');
    expect(result.courseKnowledge?.course_id).toBe('year_2_course_1');
  });

  it('prefers latest_grade_year when session state contains multiple year paths without course knowledge', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-multi-year-latest',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_2: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: '数据结构',
              goal_type: '课程学习',
              desired_outcome: '完成数据结构课程',
              four_year_outcome: '完成计算机基础课程体系',
            },
            learner_baseline: {
              current_grade: '大二',
              major: '计算机科学与技术',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 6 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后进阶',
              resource_rule: '每个节点都提供资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '核心课程', course_nodes: [] },
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
              grade_id: 'year_2',
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '数据结构基础',
              course_goal: '掌握线性表、树和图',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '8 周',
                pace_reason: '配合课程安排',
              },
              current_focus: '线性表',
              progress_state: 'in_progress',
              next_action: '继续学习树结构',
            },
          },
          year_4: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: '毕业项目',
              goal_type: '项目实践',
              desired_outcome: '完成毕业项目交付',
              four_year_outcome: '形成作品集',
            },
            learner_baseline: {
              current_grade: '大四',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先交付后沉淀',
              resource_rule: '每个节点都提供资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '核心课程', course_nodes: [] },
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
              grade_id: 'year_4',
              course_node_id: 'year_4_course_1',
              course_or_chapter_theme: '毕业项目实战',
              course_goal: '完成毕业项目实战',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程安排',
              },
              current_focus: '毕业项目交付',
              progress_state: 'in_progress',
              next_action: '继续推进交付里程碑',
            },
          },
        },
        latest_grade_year: 'year_4',
        course_knowledge: null,
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

    const result = await fetchSessionState('token-1', 'sess-multi-year-latest');

    expect(result.learningPath?.current_learning_course.course_node_id).toBe('year_4_course_1');
    expect(result.courseKnowledge).toBeNull();
  });

  it('does not attach outline data from another course when session state course_knowledge does not match the selected path', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-outline-mismatch',
        user_uid: 'user-1',
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI Agent 开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个可部署的 Agent 项目',
              four_year_outcome: '具备 AI 应用开发能力',
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
              resource_rule: '每个节点都提供资源方向',
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
                pace_reason: '配合课程安排',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: {
          course_id: 'year_3_course_2',
          course_name: 'AI Agent 项目实战',
          grade_year: 'year_3',
          personalization_summary: '这是另一门课的大纲。',
          sections: [],
          learning_sequence: ['项目实战'],
          total_estimated_hours: '10 小时',
        },
        updated_at: '2026-06-04T10:00:00Z',
      }),
    }));

    const result = await fetchSessionState('token-1', 'sess-outline-mismatch');

    expect(result.learningPath?.current_learning_course.course_node_id).toBe('year_3_course_1');
    expect(result.courseKnowledge).toBeNull();
  });

  it('recovers persisted session messages from session state and attaches the matching learning path', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续上次会话' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: makeLearningPath(),
        },
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover');

    expect(result.sessionId).toBe('sess-recover');
    expect(result.messages).toHaveLength(2);
    expect(result.messages[0]).toMatchObject({
      role: 'user',
      content: '继续上次会话',
      status: 'completed',
    });
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
      learningPath: expect.objectContaining({
        current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
      }),
    });
  });

  it('recovers a generated basic_profile when the last assistant message is 基础画像已完成', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-profile',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的画像' } },
          { type: 'ai', data: { content: '基础画像已完成' } },
        ],
        profile: {
          ...makeCompleteProfile(),
          text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
          summary_text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-profile');

    expect(result.sessionId).toBe('sess-recover-profile');
    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '基础画像已完成',
      sessionMessage: expect.objectContaining({
        type: 'basic_profile',
        stage: 'generated',
        text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
      }),
    });
  });

  it('does not mark summary-only legacy basic_profile as completed during recovery', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-summary-only',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的画像' } },
          { type: 'ai', data: { content: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。' } },
        ],
        profile: {
          type: 'basic_profile',
          summary_text: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-summary-only');

    expect(result.hasCompleteProfile).toBe(false);
    expect(result.profile).toBeNull();
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。',
    });
    expect(result.messages[1]?.sessionMessage).toBeUndefined();
  });

  it('does not mark unsupported postgraduate basic_profile as completed during recovery', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-postgraduate-profile',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的画像' } },
          { type: 'ai', data: { content: '基础画像已完成' } },
        ],
        profile: {
          ...makeCompleteProfile(),
          confirmed_info: {
            ...makeCompleteProfile().confirmed_info,
            current_grade: '研一',
          },
          text: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
          summary_text: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
        },
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-postgraduate-profile');

    expect(result.hasCompleteProfile).toBe(false);
    expect(result.profile).toBeNull();
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '基础画像已完成',
    });
    expect(result.messages[1]?.sessionMessage).toBeUndefined();
  });

  it('attaches recovered learning path to the matching assistant message instead of only the last assistant message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-nonterminal-structured',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '先帮我生成学习路径' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
          { type: 'human', data: { content: '我先看看，再继续' } },
          { type: 'ai', data: { content: '好的，我们可以继续调整。' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: makeLearningPath(),
        },
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-nonterminal-structured');

    expect(result.messages).toHaveLength(4);
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
      learningPath: expect.objectContaining({
        current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
      }),
    });
    expect(result.messages[3]).toMatchObject({
      role: 'assistant',
      content: '好的，我们可以继续调整。',
    });
    expect(result.messages[3].learningPath ?? null).toBeNull();
  });

  it('recovers both learning path and course outline when the persisted assistant text is 学习路径和课程大纲已生成', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-combined-structured',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的学习结果' } },
          { type: 'ai', data: { content: '学习路径和课程大纲已生成' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: makeLearningPath(),
        },
        course_knowledge: makeCourseKnowledge(),
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-combined-structured');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '学习路径和课程大纲已生成',
      learningPath: expect.objectContaining({
        current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
      }),
      courseKnowledge: expect.objectContaining({
        course_id: 'year_3_course_1',
        course_name: 'AI Agent 开发基础能力搭建',
      }),
    });
  });

  it('recovers course outline when the persisted assistant text is 课程大纲已生成', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-generic-outline',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '开始第一门课' } },
          { type: 'ai', data: { content: '课程大纲已生成' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: makeLearningPath(),
        },
        course_knowledge: makeCourseKnowledge(),
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-generic-outline');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '课程大纲已生成',
      courseKnowledge: expect.objectContaining({
        course_id: 'year_3_course_1',
        course_name: 'AI Agent 开发基础能力搭建',
      }),
    });
    expect(result.messages[1].learningPath ?? null).toBeNull();
  });

  it('does not attach learning path when the persisted assistant text is 课程大纲已生成：《...》', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-titled-outline',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '开始第一门课' } },
          { type: 'ai', data: { content: '课程大纲已生成：《AI Agent 开发基础能力搭建》。' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: makeLearningPath(),
        },
        course_knowledge: makeCourseKnowledge(),
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    const result = await fetchSessionRecoveryData('token-1', 'sess-recover-titled-outline');

    expect(result.messages).toHaveLength(2);
    expect(result.messages[1]).toMatchObject({
      role: 'assistant',
      content: '课程大纲已生成：《AI Agent 开发基础能力搭建》。',
      courseKnowledge: expect.objectContaining({
        course_id: 'year_3_course_1',
        course_name: 'AI Agent 开发基础能力搭建',
      }),
    });
    expect(result.messages[1].learningPath ?? null).toBeNull();
  });

  it('rejects malformed session state shell during recovery', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'sess-recover-malformed',
        user_uid: 'user-1',
        messages: {},
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    }));

    await expect(fetchSessionRecoveryData('token-1', 'sess-recover-malformed')).rejects.toThrow('会话数据格式不正确');
  });
});
