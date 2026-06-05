import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { TodayLearningDetailOverlay } from './TodayLearningDetailOverlay';
import type { TodayLearning } from '../../types/profile';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const todayLearning: TodayLearning = {
  title: '基于画像规划下一步',
  description: '默认描述',
  source: '学习路径智能体',
  currentLearningCourse: {
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
  currentCourseDetail: {
    course_node_id: 'year_3_course_1',
    grade_id: 'year_3',
    course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
    time_arrangement: {
      semester_scope: '上学期',
      duration: '6 周',
      pace_reason: '配合课程推进',
    },
    course_goal: '完成最小功能闭环',
    prerequisite_node_ids: [],
    chapter_nodes: [],
    core_knowledge_points: [],
    key_points: ['功能边界', '接口契约'],
    difficult_points: ['错误处理', '流式联调'],
    learning_sequence: ['需求拆解', '接口接入'],
    knowledge_relations: [],
    downstream_resource_direction_ids: [],
    acceptance_criteria: ['完成最小功能闭环演示'],
  },
  currentCourseOutline: {
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
        key_knowledge_points: ['完成标准', '演示路径'],
      },
      {
        section_id: '1.2',
        parent_section_id: '1',
        depth: 2,
        title: '任务拆解',
        order_index: 3,
        description: '把本章拆成具体的实现与练习任务。',
        key_knowledge_points: ['任务拆分', '演示路径'],
      },
      {
        section_id: '1.3',
        parent_section_id: '1',
        depth: 2,
        title: '检查点',
        order_index: 4,
        description: '确认这一章是否具备进入下一章的条件。',
        key_knowledge_points: ['完成标准', '推进条件'],
      },
    ],
    learning_sequence: ['第一章：需求拆解'],
    total_estimated_hours: '8-12 小时',
  },
  followingCourses: [
    {
      course_node_id: 'year_3_course_2',
      grade_id: 'year_3',
      course_or_chapter_theme: 'SSE 流式交互与部署',
      time_arrangement: {
        semester_scope: '下学期',
        duration: '8 周',
        pace_reason: '完成最小闭环后再进入交互与部署',
      },
      course_goal: '支持真实用户流程与部署演示',
      prerequisite_node_ids: ['year_3_course_1'],
      chapter_nodes: [],
      core_knowledge_points: [],
      key_points: [],
      difficult_points: [],
      learning_sequence: [],
      knowledge_relations: [],
      downstream_resource_direction_ids: [],
      acceptance_criteria: [],
    },
  ],
};

describe('TodayLearningDetailOverlay', () => {
  it('renders structured course outline details when outline data exists', () => {
    const onClose = vi.fn();

    render(
      <TodayLearningDetailOverlay
        isOpen
        onClose={onClose}
        data={todayLearning}
      />,
    );

    expect(screen.getByRole('dialog', { name: '今日学习详情' })).toBeTruthy();
    expect(screen.getByText('课程大纲说明')).toBeTruthy();
    expect(screen.getByText('先完成需求拆解，再进入接口接入与最小闭环演示。')).toBeTruthy();
    expect(screen.getByText('预计总投入：8-12 小时')).toBeTruthy();
    expect(screen.getByText('章节主线')).toBeTruthy();
    expect(screen.getAllByText('第一章：需求拆解').length).toBeGreaterThan(0);
    expect(screen.getByText('确认功能边界与验收标准。')).toBeTruthy();
    expect(screen.getByText('1.1 学习目标')).toBeTruthy();
    expect(screen.getByText('1.2 任务拆解')).toBeTruthy();
    expect(screen.getByText('1.3 检查点')).toBeTruthy();
    expect(screen.getAllByText('完成标准').length).toBeGreaterThan(0);
    expect(screen.getByText('SSE 流式交互与部署')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: '关闭今日学习详情' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
