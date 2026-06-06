import { describe, expect, it, vi } from 'vitest';
import type { AgentRunStep, ChatMessage } from '../types/chat';
import { chatReducer, type ChatStore } from './chatReducer';

function assistantMessage(id: string, content: string): ChatMessage {
  return {
    id,
    role: 'assistant',
    content,
    status: 'completed',
    timestamp: 1000,
    runTrace: [],
  };
}

const step: AgentRunStep = {
  stepId: 'learning_path_agent',
  kind: 'agent',
  status: 'success',
  title: '学习路径智能体',
  summary: '学习路径智能体结果返回成功。',
  agent: 'learning_path_agent',
};

describe('chatReducer', () => {
  it('does not attach a later run trace to an earlier assistant message', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [assistantMessage('assistant-1', '第一轮问题')],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'STEP',
      messageId: 'assistant-2',
      step,
    });

    expect(next.messages[0].runTrace).toEqual([]);
    expect(next.messages[0].content).toBe('第一轮问题');
  });

  it('does not overwrite an earlier assistant message when another message finishes', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [assistantMessage('assistant-1', '第一轮问题')],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_DONE',
      messageId: 'assistant-2',
      content: '第二轮完成',
      sessionMessage: null,
      sessionId: 'session-2',
      agentAnswer: null,
      learningPath: null,
    });

    expect(next.messages[0].content).toBe('第一轮问题');
    expect(next.currentSessionId).toBe('session-2');
  });

  it('marks any still-running steps as success when the run finishes', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [
        {
          ...assistantMessage('assistant-1', ''),
          status: 'streaming',
          runTrace: [
            {
              stepId: 'course_knowledge_agent',
              kind: 'agent',
              status: 'running',
              title: '课程大纲智能体',
              summary: '课程大纲智能体结果已生成',
              agent: 'course_knowledge_agent',
            },
          ],
          activeStepId: 'course_knowledge_agent',
        },
      ],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_DONE',
      messageId: 'assistant-1',
      content: '课程大纲已生成',
      sessionMessage: null,
      sessionId: 'session-1',
      agentAnswer: null,
      learningPath: null,
    });

    expect(next.messages[0].status).toBe('completed');
    expect(next.messages[0].activeStepId).toBeNull();
    expect(next.messages[0].runTrace?.[0].status).toBe('success');
  });

  it('stores the active session id as soon as the stream announces session_started', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'connecting',
      messages: [assistantMessage('assistant-1', '')],
      currentSessionId: null,
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'SET_SESSION_ID',
      sessionId: 'session-streaming',
    });

    expect(next.currentSessionId).toBe('session-streaming');
    expect(next.messages[0].content).toBe('');
  });

  it('stores structured course outline data on the completed assistant message', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [
        {
          ...assistantMessage('assistant-1', ''),
          status: 'streaming',
        },
      ],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_DONE',
      messageId: 'assistant-1',
      content: '课程大纲已生成',
      sessionMessage: null,
      sessionId: 'session-1',
      agentAnswer: null,
      learningPath: null,
      courseKnowledge: {
        course_id: 'year_3_course_1',
        course_name: 'AI Agent 开发基础能力搭建',
        grade_year: 'year_3',
        personalization_summary: '先完成需求拆解，再进入接口接入。',
        sections: [],
        learning_sequence: [],
        total_estimated_hours: '8 小时',
      },
    });

    expect(next.messages[0].courseKnowledge?.course_id).toBe('year_3_course_1');
    expect(next.messages[0].status).toBe('completed');
  });

  it('keeps both learning path and course outline when the same run returns both', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [
        {
          ...assistantMessage('assistant-1', ''),
          status: 'streaming',
        },
      ],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_DONE',
      messageId: 'assistant-1',
      content: '学习路径和课程大纲已生成',
      sessionMessage: null,
      sessionId: 'session-1',
      agentAnswer: null,
      learningPath: {
        schema_version: 'learning_path.v2.course_node',
        learning_goal: {
          target_course_or_skill: 'AI Agent 开发',
          goal_type: '项目实践',
          desired_outcome: '完成一个可演示的 Agent 模块',
          four_year_outcome: '形成项目交付能力',
        },
        learner_baseline: {
          current_grade: '大三',
          major: '软件工程',
          mastered_content: [],
          weaknesses: [],
          constraints: [],
          weekly_available_time: '每周 8 小时',
        },
        planning_rules: {
          node_unit: 'course_node',
          grade_boundary_rule: '按年级拆分',
          sequence_rule: '先基础后项目',
          resource_rule: '每个节点对应资源方向',
        },
        grade_plans: {
          year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
          year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '进阶', course_nodes: [] },
          year_3: { grade_id: 'year_3', grade_name: '大三', grade_goal: '项目', course_nodes: [] },
          year_4: { grade_id: 'year_4', grade_name: '大四', grade_goal: '交付', course_nodes: [] },
        },
        knowledge_graph: {
          global_relations: [],
          critical_paths: [],
        },
        resource_generation_contract: {
          downstream_agents: [],
          resource_directions: [],
        },
        dynamic_update_contract: {
          trackable_metrics: [],
          update_triggers: [],
          adjustment_strategy: '按周调整',
        },
        current_learning_course: {
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
      },
      courseKnowledge: {
        course_id: 'year_3_course_1',
        course_name: 'AI Agent 开发基础能力搭建',
        grade_year: 'year_3',
        personalization_summary: '先完成需求拆解，再进入接口接入。',
        sections: [],
        learning_sequence: [],
        total_estimated_hours: '8 小时',
      },
    });

    expect(next.messages[0].learningPath?.current_learning_course.course_node_id).toBe('year_3_course_1');
    expect(next.messages[0].courseKnowledge?.course_id).toBe('year_3_course_1');
    expect(next.messages[0].status).toBe('completed');
  });

  it('preserves thought log entries when a later step update arrives for the same step', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [
        {
          ...assistantMessage('assistant-1', ''),
          status: 'streaming',
          runTrace: [
            {
              stepId: 'supervisor',
              kind: 'thought',
              status: 'running',
              title: '主智能体思考',
              summary: '正在推理',
              thoughtLog: [
                {
                  stepId: 'supervisor',
                  text: '先分析用户意图',
                  timestamp: 1500,
                },
              ],
            },
          ],
        },
      ],
      currentSessionId: 'session-1',
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'STEP',
      messageId: 'assistant-1',
      step: {
        stepId: 'supervisor',
        kind: 'thought',
        status: 'running',
        title: '主智能体思考',
        summary: '继续推理中',
      },
    });

    expect(next.messages[0].runTrace?.[0].thoughtLog).toEqual([
      {
        stepId: 'supervisor',
        text: '先分析用户意图',
        timestamp: 1500,
      },
    ]);
  });

  it('keeps the active session id when a run fails after the session has already started', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'streaming',
      messages: [
        {
          ...assistantMessage('assistant-1', ''),
          status: 'streaming',
        },
      ],
      currentSessionId: null,
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'RUN_ERROR',
      messageId: 'assistant-1',
      message: '学习路径生成失败',
      sessionId: 'session-retry',
      retryAction: 'retry_learning_path',
    });

    expect(next.currentSessionId).toBe('session-retry');
    expect(next.messages[0].retryAction).toBe('retry_learning_path');
    expect(next.messages[0].status).toBe('error');
  });

  it('normalizes recovered streaming assistant messages to completed when loading a cached session', () => {
    vi.spyOn(Date, 'now').mockReturnValue(2000);
    const state: ChatStore = {
      state: 'idle',
      messages: [],
      currentSessionId: null,
      errorMessage: null,
    };

    const next = chatReducer(state, {
      type: 'LOAD_SESSION',
      sessionId: 'session-recovered-streaming',
      messages: [
        {
          id: 'assistant-streaming',
          role: 'assistant',
          content: '学习路径已生成',
          status: 'streaming',
          timestamp: 1000,
          activeStepId: 'learning_path_agent',
          runTrace: [
            {
              stepId: 'learning_path_agent',
              kind: 'agent',
              status: 'running',
              title: '学习路径智能体',
              summary: '学习路径智能体结果已生成',
              agent: 'learning_path_agent',
            },
          ],
        },
      ],
    });

    expect(next.state).toBe('idle');
    expect(next.currentSessionId).toBe('session-recovered-streaming');
    expect(next.messages[0].status).toBe('completed');
    expect(next.messages[0].activeStepId).toBeNull();
    expect(next.messages[0].runTrace?.[0].status).toBe('success');
  });
});
