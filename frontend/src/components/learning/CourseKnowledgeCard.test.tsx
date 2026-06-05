import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CourseKnowledgeCard } from './CourseKnowledgeCard';
import type { CourseKnowledgeResult } from '../../types/chat';

const outline: CourseKnowledgeResult = {
  course_id: 'year_3_course_1',
  course_name: 'AI Agent 开发基础能力搭建',
  grade_year: 'year_3',
  personalization_summary: '先稳住接口接入与最小闭环，再逐步提升到联调与部署演示。',
  sections: [
    {
      section_id: '1',
      parent_section_id: null,
      depth: 1,
      title: '需求拆解',
      order_index: 1,
      description: '先确认功能边界与验收标准。',
      key_knowledge_points: ['功能边界', '验收标准'],
    },
    {
      section_id: '1.1',
      parent_section_id: '1',
      depth: 2,
      title: '学习目标',
      order_index: 2,
      description: '明确本章完成后的理解深度与产出目标。',
      key_knowledge_points: ['功能边界', '验收标准'],
    },
    {
      section_id: '1.2',
      parent_section_id: '1',
      depth: 2,
      title: '任务拆解',
      order_index: 3,
      description: '拆成可执行任务与实现步骤。',
      key_knowledge_points: ['任务拆分', '实现步骤'],
    },
    {
      section_id: '1.3',
      parent_section_id: '1',
      depth: 2,
      title: '检查点',
      order_index: 4,
      description: '确认本章是否已经学会并可进入下一章。',
      key_knowledge_points: ['完成确认', '推进条件'],
    },
    {
      section_id: '2',
      parent_section_id: null,
      depth: 1,
      title: '接口接入',
      order_index: 3,
      description: '完成模型调用、错误处理与稳定性控制。',
      key_knowledge_points: ['OpenAI-compatible API', '错误处理'],
    },
  ],
  learning_sequence: ['第一章：需求拆解', '第二章：接口接入'],
  total_estimated_hours: '8-12 小时',
};

describe('CourseKnowledgeCard', () => {
  it('renders outline summary, sequence and nested sections', () => {
    render(<CourseKnowledgeCard outline={outline} />);

    expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
    expect(screen.getByText('先稳住接口接入与最小闭环，再逐步提升到联调与部署演示。')).toBeTruthy();
    expect(screen.getByText('8-12 小时')).toBeTruthy();
    expect(screen.getAllByText('第一章：需求拆解').length).toBeGreaterThan(0);
    expect(screen.getByText('1.1 学习目标')).toBeTruthy();
    expect(screen.getByText('1.2 任务拆解')).toBeTruthy();
    expect(screen.getByText('1.3 检查点')).toBeTruthy();
    expect(screen.getByText('OpenAI-compatible API')).toBeTruthy();
  });
});
