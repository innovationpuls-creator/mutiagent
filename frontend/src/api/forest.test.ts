import { afterEach, describe, expect, test, vi } from 'vitest';
import { fetchForestQuizSession, streamForestAi, submitForestQuizAttempt, submitForestQuizAttemptStream } from './forest';
import type { ForestSubmitStreamEvent } from '../types/forest';

const responsePayload = {
  course: {
    course_node_id: 'year_3_course_2',
    grade_id: 'year_3',
    course_or_chapter_theme: 'AI Agent 开发',
    course_goal: '完成 AI Agent 开发',
    status: 'current',
    has_outline: true,
  },
  chapter: {
    section_id: '1',
    parent_section_id: null,
    depth: 1,
    title: '第一章：需求拆解',
    order_index: 1,
    description: '确认边界',
    key_knowledge_points: ['边界'],
  },
  quiz: null,
  latest_attempt: null,
  progress: {
    course_node_id: 'year_3_course_2',
    chapter_id: '1',
    state: 'available',
    best_score: 0,
    latest_attempt_id: null,
    passed_at: null,
    updated_at: '2026-06-09T00:00:00Z',
  },
  next_unlocked_chapter_id: null,
  next_course_id: null,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('forest api', () => {
  test('normalizes quiz session response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => responsePayload,
    }));

    const result = await fetchForestQuizSession('token', 'year_3_course_2', '1');

    expect(result.course.course_node_id).toBe('year_3_course_2');
    expect(result.chapter.section_id).toBe('1');
    expect(result.progress.state).toBe('available');
  });

  test('submits quiz attempt payload', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        attempt_id: 'attempt_1',
        quiz_id: 'quiz_1',
        score: 71,
        passed: true,
        answers: { q1: 'A' },
        grading_result: { score: 71 },
        created_at: '2026-06-09T00:00:00Z',
      }),
    }));

    const result = await submitForestQuizAttempt('token', 'quiz_1', { answers: { q1: 'A' } });

    expect(result.attempt_id).toBe('attempt_1');
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/forest/quizzes/quiz_1/attempts',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ answers: { q1: 'A' } }),
      }),
    );
  });

  test('streams Forest AI SSE chunks', async () => {
    const chunks = [
      'event: forest_ai_text_chunk\ndata: {"chunk":"第一段"}\n\n',
      'event: forest_ai_completed\ndata: {"message":"completed"}\n\n',
    ];
    const encoder = new TextEncoder();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
          controller.close();
        },
      }),
    }));
    const events: unknown[] = [];

    await streamForestAi(
      'token',
      {
        course_node_id: 'year_3_course_2',
        chapter_id: '1',
        quiz_id: 'quiz_1',
        question_id: 'q1',
        question: null,
        answer: 'A',
        grading_result: null,
      },
      '解析',
      (event) => events.push(event),
    );

    expect(events).toEqual([
      { event: 'forest_ai_text_chunk', chunk: '第一段' },
      { event: 'forest_ai_completed', chunk: undefined },
    ]);
  });

  test('parses submitForestQuizAttemptStream SSE events', async () => {
    const sseChunks = [
      'event: status\ndata: {"phase":"grading","message":"正在判题…"}\n\n',
      'event: status\ndata: {"phase":"analyzing","message":"分析薄弱方向…"}\n\n',
      'event: done\ndata: {"attempt":{"attempt_id":"a1","quiz_id":"q1","score":85,"passed":true,"answers":{"q1":"A"},"grading_result":{"score":85},"created_at":"2026-06-09T00:00:00Z"},"weaknesses":[{"knowledge_point_id":"kp1","knowledge_point_name":"边界","severity":2}],"canopy_overview":{"total_courses":5,"completed_courses":1,"total_chapters":20,"completed_chapters":4,"avg_score":80,"total_focus_hours":12,"growth_tree_stage":3,"growth_advanced_steps":2,"milestones":[]},"next_unlocked_chapter_id":"ch2","next_course_id":null}\n\n',
    ];
    const encoder = new TextEncoder();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          sseChunks.forEach((c) => controller.enqueue(encoder.encode(c)));
          controller.close();
        },
      }),
    }));

    const events: ForestSubmitStreamEvent[] = [];
    await submitForestQuizAttemptStream(
      'token',
      'q1',
      { answers: { q1: 'A' } },
      (event) => events.push(event),
    );

    expect(events).toHaveLength(3);
    expect(events[0]).toEqual({ event: 'status', phase: 'grading', message: '正在判题…' });
    expect(events[1]).toEqual({ event: 'status', phase: 'analyzing', message: '分析薄弱方向…' });
    expect(events[2].event).toBe('done');
    expect(events[2].doneData?.attempt.score).toBe(85);
    expect(events[2].doneData?.weaknesses).toHaveLength(1);
    expect(events[2].doneData?.weaknesses[0].knowledge_point_name).toBe('边界');
    expect(events[2].doneData?.canopy_overview.growth_tree_stage).toBe(3);
    expect(events[2].doneData?.next_unlocked_chapter_id).toBe('ch2');
    expect(events[2].doneData?.next_course_id).toBeNull();
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/forest/quizzes/q1/attempts/stream',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ answers: { q1: 'A' } }),
      }),
    );
  });

  test('parses submitForestQuizAttemptStream error event', async () => {
    const sseChunks = [
      'event: status\ndata: {"phase":"grading","message":"正在判题…"}\n\n',
      'event: error\ndata: {"message":"内部错误"}\n\n',
    ];
    const encoder = new TextEncoder();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      body: new ReadableStream({
        start(controller) {
          sseChunks.forEach((c) => controller.enqueue(encoder.encode(c)));
          controller.close();
        },
      }),
    }));

    const events: ForestSubmitStreamEvent[] = [];
    await submitForestQuizAttemptStream(
      'token',
      'q1',
      { answers: { q1: 'A' } },
      (event) => events.push(event),
    );

    expect(events).toHaveLength(2);
    expect(events[0].event).toBe('status');
    expect(events[1]).toEqual({ event: 'error', message: '内部错误' });
  });
});
