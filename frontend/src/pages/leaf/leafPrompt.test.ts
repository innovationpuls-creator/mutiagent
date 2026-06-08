import { describe, expect, it } from 'vitest';
import type { LeafCourse } from '../../types/leaf';
import { buildCourseOutlineGenerationPrompt } from './leafPrompt';

describe('buildCourseOutlineGenerationPrompt', () => {
  it('keeps the exact course name in the outline draft prompt', () => {
    const course: LeafCourse = {
      course_node_id: 'year_3_course_1',
      grade_id: 'year_3',
      course_or_chapter_theme: '构建本地知识库问答系统 (RAG基础)',
      course_goal: '完成本地知识库问答系统',
      status: 'current',
      has_outline: false,
    };

    expect(buildCourseOutlineGenerationPrompt(course)).toBe(
      '帮我生成《构建本地知识库问答系统 (RAG基础)》的大纲',
    );
  });
});
