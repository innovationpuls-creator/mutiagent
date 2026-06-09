import { afterEach, describe, expect, test, vi } from 'vitest';
import { fetchForestQuizSession } from './forest';

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
});
