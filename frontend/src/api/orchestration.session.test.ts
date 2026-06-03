import { beforeEach, describe, expect, it, vi } from 'vitest';
import { continueSession, startSession, streamSession, type SessionAgentEvent } from './orchestration';
import { getMyLearningPath } from './learningPath';

describe('session orchestration API', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('posts to the new session start endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        answer: { user_message: '你好', question_box: null },
        agent_trace: [],
        completed: false,
        profile: null,
        learning_path: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await startSession('token-1', '你好');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/sessions/start',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Authorization: 'Bearer token-1' }),
        body: JSON.stringify({ query: '你好' }),
      }),
    );
    expect(result.sessionId).toBe('session-1');
    expect(result.answer.userMessage).toBe('你好');
  });

  it('drops legacy learning path payloads from session responses', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-legacy-path',
        answer: { user_message: '你好', question_box: null },
        agent_trace: [],
        completed: false,
        profile: null,
        learning_path: {
          learning_goal: { target_course_or_skill: '旧版路径' },
          gap_analysis: {},
          foundation_path: {},
          generated_path: {},
        },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await startSession('token-1', '你好');

    expect(result.learningPath).toBeNull();
  });

  it('posts to the new session continue endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-1',
        answer: { user_message: '继续', question_box: null },
        agent_trace: [],
        completed: false,
        profile: null,
        learning_path: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await continueSession('token-1', 'session-1', '继续');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/sessions/continue',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ session_id: 'session-1', query: '继续' }),
      }),
    );
    expect(result.sessionId).toBe('session-1');
    expect(result.answer.userMessage).toBe('继续');
  });

  it('parses new session stream events and returns the completed turn', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            [
              'event: agent_step_started',
              'data: {"step_id":"main_agent","agent_key":"main_agent","label":"主智能体","message":"主智能体开始处理。"}',
              '',
              'event: orchestration_completed',
              'data: {"session_id":"session-1","answer":{"user_message":"流式完成","question_box":null},"agent_trace":[],"completed":false,"profile":null,"learning_path":null}',
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const events: SessionAgentEvent[] = [];

    const turn = await streamSession('token-1', '开始流式', null, (event) => events.push(event));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/sessions/start/stream',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Accept: 'text/event-stream' }),
        body: JSON.stringify({ query: '开始流式' }),
      }),
    );
    expect(events.map((event) => event.event)).toEqual(['agent_step_started', 'orchestration_completed']);
    expect(turn.sessionId).toBe('session-1');
    expect(turn.answer.userMessage).toBe('流式完成');
  });

  it('drops legacy learning path payloads from session stream events', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            [
              'event: orchestration_completed',
              'data: {"session_id":"session-legacy-stream","answer":{"user_message":"流式完成","question_box":null},"agent_trace":[],"completed":false,"profile":null,"learning_path":{"learning_goal":{"target_course_or_skill":"旧版路径"},"gap_analysis":{},"foundation_path":{},"generated_path":{}}}',
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 200 })));

    const turn = await streamSession('token-1', '开始流式', null, () => undefined);

    expect(turn.learningPath).toBeNull();
  });

  it('reads my saved learning path', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        learning_path: {
          schema_version: 'learning_path.v2.course_node',
          learning_goal: {
            target_course_or_skill: '数据结构',
            goal_type: '课程学习',
            desired_outcome: '能完成课程项目',
            four_year_outcome: '形成数据结构、项目实践与就业表达的完整能力链路',
          },
          learner_baseline: {
            current_grade: '大一',
            major: '计算机科学与技术',
            mastered_content: ['Python 基础'],
            weaknesses: ['算法复杂度'],
            constraints: ['时间分散'],
            weekly_available_time: '每周 8 小时',
          },
          planning_rules: {
            node_unit: 'course_node',
            grade_boundary_rule: '每个 course_node 必须只属于一个 grade_id，不能跨年级安排；跨年级内容必须拆成多个 course_node。',
            sequence_rule: '先程序设计，再数据结构。',
            resource_rule: '每个课程节点提供资源方向。',
          },
          grade_plans: {
            year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '打牢基础', course_nodes: [] },
            year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '学习数据结构', course_nodes: [] },
            year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目实践', course_nodes: [] },
            year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '就业准备', course_nodes: [] },
          },
          knowledge_graph: {
            global_relations: [],
            critical_paths: [],
          },
          resource_generation_contract: {
            downstream_agents: [
              'learning_resource_agent',
              'question_bank_agent',
              'document_agent',
              'code_example_agent',
              'video_script_agent',
              'dynamic_update_agent',
            ],
            resource_directions: [],
          },
          dynamic_update_contract: {
            trackable_metrics: ['课程节点完成率'],
            update_triggers: ['学习进度偏离'],
            adjustment_strategy: '只调整同一年级内未完成的 course_node。',
          },
        },
        updated_at: '2026-06-01T12:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await getMyLearningPath('token-1');

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/learning-path/me',
      expect.objectContaining({
        headers: { Authorization: 'Bearer token-1' },
      }),
    );
    expect(result.learningPath.schema_version).toBe('learning_path.v2.course_node');
    expect(result.learningPath.learning_goal.target_course_or_skill).toBe('数据结构');
    expect(result.updatedAt).toBe('2026-06-01T12:00:00Z');
  });
});
