import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LearningPathCard } from './LearningPathCard';
import type { LearningPathResult } from '../../types/chat';

const path: LearningPathResult = {
  learning_goal: {
    target_course_or_skill: '数据结构',
    target_completion_time: '大二结束前',
    goal_type: '课程学习',
    desired_outcome: '完成课程项目',
  },
  gap_analysis: {
    current_mastered_content: ['Python 基础'],
    current_weaknesses: ['算法复杂度'],
    required_capabilities: ['树', '图'],
    main_gaps: ['练习不足'],
  },
  foundation_path: {
    stages: [{
      stage_id: 'year_1',
      stage_name: '大一基础',
      learning_goal: '打牢基础',
      learning_content: ['编程语言'],
      learning_tasks: ['完成练习'],
      recommended_methods: ['课程学习'],
      completion_standard: ['完成小项目'],
    }],
  },
  generated_path: {
    overall_goal: '形成完整数据结构能力',
    stage_routes: [{ stage_id: 'year_1', route_summary: '先补编程基础' }],
    schedule: [{ period: '大一上', focus: '编程基础', milestone: '完成项目' }],
    task_checklist: ['每周练习'],
    recommended_resource_types: ['教材', '题库'],
    stage_acceptance_criteria: [{ stage_id: 'year_1', criteria: ['完成项目'] }],
    next_actions: ['学习数组和链表'],
  },
};

describe('LearningPathCard', () => {
  it('renders all learning path sections', () => {
    render(<LearningPathCard path={path} />);

    expect(screen.getByText('明确学习目标')).toBeTruthy();
    expect(screen.getByText('分析当前差距')).toBeTruthy();
    expect(screen.getByText('规划基础学习路径')).toBeTruthy();
    expect(screen.getByText('生成学习路径')).toBeTruthy();
    expect(screen.getByText('数据结构')).toBeTruthy();
  });
});
