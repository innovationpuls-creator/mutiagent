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

  it('reads my saved learning path', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        learning_path: {
          learning_goal: {
            target_course_or_skill: '数据结构',
            target_completion_time: '大二结束前',
            goal_type: '课程学习',
            desired_outcome: '能完成课程项目',
          },
          gap_analysis: {
            current_mastered_content: ['Python 基础'],
            current_weaknesses: ['算法复杂度'],
            required_capabilities: ['线性表'],
            main_gaps: ['缺少系统刷题'],
          },
          foundation_path: { stages: [] },
          generated_path: {
            overall_goal: '形成数据结构学习路径',
            stage_routes: [],
            schedule: [],
            task_checklist: [],
            recommended_resource_types: [],
            stage_acceptance_criteria: [],
            next_actions: [],
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
    expect(result.learningPath.learning_goal.target_course_or_skill).toBe('数据结构');
    expect(result.updatedAt).toBe('2026-06-01T12:00:00Z');
  });
});
