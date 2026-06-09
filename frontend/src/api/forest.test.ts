import { afterEach, describe, expect, test, vi } from 'vitest';
import { fetchForestQuizSession, streamForestAi, submitForestQuizAttempt } from './forest';

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
});
