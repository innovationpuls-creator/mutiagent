import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../../types/chat';
import { useChatSession } from './useChatSession';

function message(id: string, content: string): ChatMessage {
  return {
    id,
    role: 'assistant',
    content,
    status: 'completed',
    timestamp: 1000,
  };
}

function Harness({
  storeSessionId,
  token,
  onRecovered,
  tick,
}: {
  storeSessionId: string | null;
  token: string | null;
  onRecovered: (messages: ChatMessage[], sessionId: string) => void;
  tick: number;
}) {
  useChatSession(storeSessionId, token, (messages, sessionId) => onRecovered(messages, sessionId));
  return <span>{tick}</span>;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  window.history.replaceState({}, '', '/');
});

function stubLocalStorage(initial: Record<string, string> = {}) {
  const store = { ...initial };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store[key] = value;
    }),
    removeItem: vi.fn((key: string) => {
      delete store[key];
    }),
  });
}

describe('useChatSession', () => {
  it('recovers a different session_id after the URL changes to another cached session', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ messages: [message('assistant-1', '第一段对话')], savedAt: 1000 }),
      'session-session-2': JSON.stringify({ messages: [message('assistant-2', '第二段对话')], savedAt: 2000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=session-1');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-1', content: '第一段对话' })],
        'session-1',
      ),
    );

    window.history.replaceState({}, '', '/sprout?session_id=session-2');
    rerender(<Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-2', content: '第二段对话' })],
        'session-2',
      ),
    );
  });

  it('does not recover the same cached session twice across rerenders before storeSessionId is set', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ messages: [message('assistant-1', '第一段对话')], savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=session-1');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-1', content: '第一段对话' })],
        'session-1',
      ),
    );

    rerender(<Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() => expect(onRecovered).toHaveBeenCalledTimes(1));
  });

  it('does not recover stale localStorage after the active session writes its id to the URL', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ messages: [message('assistant-1', '旧问题')], savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );
    rerender(<Harness storeSessionId="session-1" token="token-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() => expect(window.location.search).toBe('?session_id=session-1'));
    rerender(<Harness storeSessionId="session-1" token="token-1" onRecovered={onRecovered} tick={2} />);

    expect(onRecovered).not.toHaveBeenCalled();
  });

  it('clears stale session_id from the URL when no cached session exists', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=missing-session');

    render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() => expect(window.location.search).toBe(''));
    expect(onRecovered).not.toHaveBeenCalled();
  });

  it('clears stale session_id from the URL when cached session shape is invalid', async () => {
    stubLocalStorage({
      'session-bad-session': JSON.stringify({ savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=bad-session');

    render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() => expect(window.location.search).toBe(''));
    expect(onRecovered).not.toHaveBeenCalled();
  });

  it('recovers from the server when localStorage is missing but the session still exists remotely', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续上次对话' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
        ],
        profile: null,
        year_learning_paths: {
          year_3: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: 'AI 应用开发',
              goal_type: '项目实践',
              desired_outcome: '完成一个 AI 功能模块',
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
                pace_reason: '项目驱动',
              },
              current_focus: '需求拆解',
              progress_state: 'in_progress',
              next_action: '开始接口接入',
            },
          },
        },
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-session');

    render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续上次对话' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
            learningPath: expect.objectContaining({
              current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
            }),
          }),
        ],
        'remote-session',
      ),
    );
  });

  it('prefers latest_grade_year when recovering a multi-year session from the server', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-latest-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的最新路径' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《毕业项目实战》。' } },
        ],
        profile: null,
        year_learning_paths: {
          year_2: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: '数据结构',
              goal_type: '课程学习',
              desired_outcome: '完成数据结构课程',
              four_year_outcome: '完成计算机基础课程体系',
            },
            learner_baseline: {
              current_grade: '大二',
              major: '计算机科学与技术',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 6 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先基础后进阶',
              resource_rule: '每个节点都提供资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '核心课程', course_nodes: [] },
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
              grade_id: 'year_2',
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '数据结构基础',
              course_goal: '掌握线性表、树和图',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '8 周',
                pace_reason: '配合课程安排',
              },
              current_focus: '线性表',
              progress_state: 'in_progress',
              next_action: '继续学习树结构',
            },
          },
          year_4: {
            schema_version: 'learning_path.v2.course_node',
            learning_goal: {
              target_course_or_skill: '毕业项目',
              goal_type: '项目实践',
              desired_outcome: '完成毕业项目交付',
              four_year_outcome: '形成作品集',
            },
            learner_baseline: {
              current_grade: '大四',
              major: '软件工程',
              mastered_content: [],
              weaknesses: [],
              constraints: [],
              weekly_available_time: '每周 8 小时',
            },
            planning_rules: {
              node_unit: 'course_node',
              grade_boundary_rule: '按年级拆分',
              sequence_rule: '先交付后沉淀',
              resource_rule: '每个节点都提供资源方向',
            },
            grade_plans: {
              year_1: { grade_id: 'year_1', grade_name: '大一', grade_goal: '基础', course_nodes: [] },
              year_2: { grade_id: 'year_2', grade_name: '大二', grade_goal: '核心课程', course_nodes: [] },
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
              grade_id: 'year_4',
              course_node_id: 'year_4_course_1',
              course_or_chapter_theme: '毕业项目实战',
              course_goal: '完成毕业项目实战',
              time_arrangement: {
                semester_scope: '上学期',
                duration: '6 周',
                pace_reason: '配合课程安排',
              },
              current_focus: '毕业项目交付',
              progress_state: 'in_progress',
              next_action: '继续推进交付里程碑',
            },
          },
        },
        latest_grade_year: 'year_4',
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-latest-session');

    render(
      <Harness storeSessionId={null} token="token-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续恢复我的最新路径' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径已生成，当前建议先学习《毕业项目实战》。',
            learningPath: expect.objectContaining({
              current_learning_course: expect.objectContaining({ course_node_id: 'year_4_course_1' }),
            }),
          }),
        ],
        'remote-latest-session',
      ),
    );
  });
});
