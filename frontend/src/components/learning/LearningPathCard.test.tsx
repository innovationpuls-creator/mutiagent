import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LearningPathCard } from './LearningPathCard';
import type { LearningPathResult } from '../../types/chat';

const path: LearningPathResult = {
  schema_version: 'learning_path.v2.course_node',
  learning_goal: {
    target_course_or_skill: '计算机专业能力',
    goal_type: '就业准备',
    desired_outcome: '具备独立完成后端项目与面试表达的能力',
    four_year_outcome: '形成从基础编程到工程实践的完整能力链路',
  },
  learner_baseline: {
    current_grade: '准大一',
    major: '计算机科学与技术',
    mastered_content: ['Python 基础语法'],
    weaknesses: ['算法复杂度理解不稳定'],
    constraints: ['每周学习时间有限'],
    weekly_available_time: '每周 8 小时',
  },
  planning_rules: {
    node_unit: 'course_node',
    grade_boundary_rule: '每个 course_node 必须只属于一个 grade_id，不能跨年级安排；跨年级内容必须拆成多个 course_node。',
    sequence_rule: '先完成编程基础，再进入数据结构、工程实践和项目综合。',
    resource_rule: '每个课程节点必须提供后续资源生成方向。',
  },
  grade_plans: {
    year_1: {
      grade_id: 'year_1',
      grade_name: '大一',
      grade_goal: '打牢编程与数学基础',
      course_nodes: [
        {
          course_node_id: 'year_1_course_1',
          grade_id: 'year_1',
          course_or_chapter_theme: '程序设计基础',
          time_arrangement: {
            semester_scope: '上学期',
            duration: '3 个月',
            pace_reason: '先建立基础语法与调试习惯',
          },
          course_goal: '能独立完成小型命令行程序',
          prerequisite_node_ids: [],
          chapter_nodes: [
            {
              chapter_node_id: 'year_1_course_1_chapter_1',
              chapter_theme: '变量、流程控制与函数',
              knowledge_hierarchy: [
                {
                  hierarchy_id: 'hier_year_1_course_1',
                  parent_hierarchy_id: null,
                  hierarchy_level: '课程',
                  title: '程序设计基础',
                  summary: '建立编程表达能力',
                  knowledge_point_ids: ['kp_programming_basic'],
                },
              ],
              core_knowledge_point_ids: ['kp_programming_basic'],
              key_points: ['函数拆分', '调试习惯'],
              difficult_points: ['循环边界', '状态变化追踪'],
              prerequisite_node_ids: [],
              learning_sequence: ['变量', '条件', '循环', '函数'],
              knowledge_relations: [
                {
                  from_node_id: 'kp_programming_basic',
                  to_node_id: 'year_1_course_1_chapter_1',
                  relation_type: 'contains',
                  description: '章节包含基础编程知识点',
                },
              ],
              downstream_resource_direction_ids: ['resource_programming_basic_doc'],
            },
          ],
          core_knowledge_points: [
            {
              knowledge_point_id: 'kp_programming_basic',
              name: '基础编程表达',
              parent_knowledge_point_id: null,
              level: '基础',
              description: '使用变量、分支、循环和函数表达解题过程',
              mastery_standard: '能独立写出带函数拆分的小程序',
            },
          ],
          key_points: ['基础语法', '函数拆分', '调试'],
          difficult_points: ['边界条件', '变量状态'],
          learning_sequence: ['year_1_course_1_chapter_1'],
          knowledge_relations: [
            {
              from_node_id: 'year_1_course_1_chapter_1',
              to_node_id: 'year_1_course_1',
              relation_type: 'contains',
              description: '课程节点包含章节节点',
            },
          ],
          downstream_resource_direction_ids: ['resource_programming_basic_doc'],
          acceptance_criteria: ['完成 3 个基础编程项目'],
        },
      ],
    },
    year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进入数据结构与数据库', course_nodes: [] },
    year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '完成后端工程实践', course_nodes: [] },
    year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '作品集与就业准备', course_nodes: [] },
  },
  knowledge_graph: {
    global_relations: [
      {
        from_node_id: 'year_1_course_1',
        to_node_id: 'year_2_course_1',
        relation_type: 'prerequisite',
        description: '程序设计基础是数据结构学习的先修课程节点',
      },
    ],
    critical_paths: [
      {
        path_id: 'backend_employment_path',
        purpose: '形成后端就业能力',
        ordered_node_ids: ['year_1_course_1', 'year_2_course_1', 'year_3_course_1', 'year_4_course_1'],
      },
    ],
  },
  resource_generation_contract: {
    downstream_agents: [
      'learning_resource_agent',
      'question_bank_agent',
      'document_agent',
      'code_example_agent',
      'video_script_agent',
      'dynamic_update_agent',
    ],
    resource_directions: [
      {
        resource_direction_id: 'resource_programming_basic_doc',
        target_node_ids: ['year_1_course_1'],
        resource_type: '文档',
        generation_goal: '生成程序设计基础讲义',
        content_requirements: ['包含概念解释', '包含练习入口'],
        difficulty_level: '入门',
      },
    ],
  },
  dynamic_update_contract: {
    trackable_metrics: ['课程节点完成率', '章节验收通过率'],
    update_triggers: ['连续两周未完成计划', '章节测验低于 70 分'],
    adjustment_strategy: '只调整同一年级内未完成的 course_node，不把节点移动到其他年级。',
  },
};

describe('LearningPathCard', () => {
  it('renders course-node learning path sections', () => {
    render(<LearningPathCard path={path} />);

    expect(screen.getByText('多学年课程路径')).toBeTruthy();
    expect(screen.getByText('计算机专业能力')).toBeTruthy();
    expect(screen.getByText('大一')).toBeTruthy();
    expect(screen.getByText('程序设计基础')).toBeTruthy();
    expect(screen.getByText('基础编程表达')).toBeTruthy();
    expect(screen.getAllByText('后续资源生成方向')).toHaveLength(2);
    expect(screen.getByText('动态更新依据')).toBeTruthy();
  });
});
