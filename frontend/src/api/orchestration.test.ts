import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamChatflow, type ChatflowAgentEvent } from './orchestration';

describe('streamChatflow', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('emits agent events and returns the completed chatflow turn', async () => {
    const encoder = new TextEncoder();
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(
          encoder.encode(
            [
              'event: agent_started',
              'data: {"agent":"intent_recognition_agent","label":"意图识别智能体","message":"正在判断"}',
              '',
              'event: route_decided',
              'data: {"agent":"profile_agent","label":"基础画像智能体","message":"准备进入具体智能体"}',
              '',
              'event: completed',
              'data: {"execution_id":"exec-1","conversation_id":"conv-1","completed":false,"answer":{"type":"collecting","stage":"basic_info","question_mode":"question_md","confirmed_info":{},"defaulted_fields":[],"question_md":"请介绍","question_box":{"question":"","options":[]},"text":"请介绍"},"final_result":null}',
              '',
            ].join('\n'),
          ),
        );
        controller.close();
      },
    });
    const fetchMock = vi.fn().mockResolvedValue(new Response(body, { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const events: ChatflowAgentEvent[] = [];

    const turn = await streamChatflow('token-1', '我想完善画像', null, (event) => events.push(event));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/orchestration/chatflow/start/stream',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({ Accept: 'text/event-stream' }),
      }),
    );
    expect(events.map((event) => event.event)).toEqual(['agent_started', 'route_decided', 'completed']);
    expect(events[0].label).toBe('意图识别智能体');
    expect(events[1].label).toBe('基础画像智能体');
    expect(turn.executionId).toBe('exec-1');
    expect(turn.answer.text).toBe('请介绍');
  });
});
