import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamSession, type SessionAgentEvent } from './orchestration';

describe('streamSession', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('emits session events and returns the completed session turn', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            [
              'event: agent_step_started',
              'data: {"step_id":"intent","agent_key":"intent_recognition_agent","label":"意图识别智能体","phase":"intent","status":"running","message":"正在判断"}',
              '',
              'event: agent_step_completed',
              'data: {"step_id":"profile","agent_key":"profile_agent","label":"基础画像智能体","phase":"profile","status":"completed","message":"画像智能体已完成"}',
              '',
              'event: agent_step_started',
              'data: {"step_id":"learning","agent_key":"learning_path_agent","label":"学习路径智能体","phase":"agent","status":"running","message":"学习路径智能体开始处理。","depends_on":["profile"],"parallel_group":"path"}',
              '',
              'event: orchestration_completed',
              'data: {"session_id":"session-1","answer":{"user_message":"请介绍","question_box":{"question":"请介绍","options":["基础情况","学习目标"]}},"agent_trace":[{"step_id":"profile","agent_key":"profile_agent","label":"基础画像智能体","phase":"profile","status":"completed","message":"画像智能体已完成","depends_on":["intent"],"parallel_group":null}],"completed":false,"profile":null,"learning_path":null}',
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

    const turn = await streamSession('token-1', '我想完善画像', null, (event) => events.push(event));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/sessions/start/stream',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Accept: 'text/event-stream' }),
        body: JSON.stringify({ query: '我想完善画像' }),
      }),
    );
    expect(events.map((event) => event.event)).toEqual([
      'agent_step_started',
      'agent_step_completed',
      'agent_step_started',
      'orchestration_completed',
    ]);
    expect(events[0].label).toBe('意图识别智能体');
    expect(events[1].label).toBe('基础画像智能体');
    expect(events[2].dependsOn).toEqual(['profile']);
    expect(events[2].parallelGroup).toBe('path');
    expect(turn.sessionId).toBe('session-1');
    expect(turn.answer.userMessage).toBe('请介绍');
    expect(turn.answer.questionBox?.options).toEqual(['基础情况', '学习目标']);
    expect(turn.agentTrace[0]).toMatchObject({
      stepId: 'profile',
      agentKey: 'profile_agent',
      dependsOn: ['intent'],
      parallelGroup: null,
    });
  });
});
