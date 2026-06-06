import { cleanup, render, waitFor } from '@testing-library/react';
import { useRef } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { ChatMessage } from '../../types/chat';
import { useChatSession, type SessionRecoveryMeta } from './useChatSession';

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
  userUid,
  onRecovered,
  onRecoveredMeta,
  tick,
}: {
  storeSessionId: string | null;
  token: string | null;
  userUid: string | null;
  onRecovered: (messages: ChatMessage[], sessionId: string) => void;
  onRecoveredMeta?: (meta: SessionRecoveryMeta | null) => void;
  tick: number;
}) {
  const recoveryMetaRef = useRef<SessionRecoveryMeta | null>(null);
  useChatSession(
    storeSessionId,
    token,
    userUid,
    (messages, sessionId) => {
      onRecovered(messages, sessionId);
      onRecoveredMeta?.(recoveryMetaRef.current);
    },
    recoveryMetaRef,
  );
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
      'session-session-1': JSON.stringify({ userUid: 'user-1', messages: [message('assistant-1', '第一段对话')], savedAt: 1000 }),
      'session-session-2': JSON.stringify({ userUid: 'user-1', messages: [message('assistant-2', '第二段对话')], savedAt: 2000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=session-1');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-1', content: '第一段对话' })],
        'session-1',
      ),
    );

    window.history.replaceState({}, '', '/sprout?session_id=session-2');
    rerender(<Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-2', content: '第二段对话' })],
        'session-2',
      ),
    );
  });

  it('does not recover the same cached session twice across rerenders before storeSessionId is set', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ userUid: 'user-1', messages: [message('assistant-1', '第一段对话')], savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=session-1');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-1', content: '第一段对话' })],
        'session-1',
      ),
    );

    rerender(<Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() => expect(onRecovered).toHaveBeenCalledTimes(1));
  });

  it('does not recover stale localStorage after the active session writes its id to the URL', async () => {
    stubLocalStorage({
      'session-session-1': JSON.stringify({ userUid: 'user-1', messages: [message('assistant-1', '旧问题')], savedAt: 1000 }),
    });
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout');

    const { rerender } = render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );
    rerender(<Harness storeSessionId="session-1" token="token-1" userUid="user-1" onRecovered={onRecovered} tick={1} />);

    await waitFor(() => expect(window.location.search).toBe('?session_id=session-1'));
    rerender(<Harness storeSessionId="session-1" token="token-1" userUid="user-1" onRecovered={onRecovered} tick={2} />);

    expect(onRecovered).not.toHaveBeenCalled();
  });

  it('clears stale session_id from the URL when no cached session exists', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    window.history.replaceState({}, '', '/sprout?session_id=missing-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
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
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() => expect(window.location.search).toBe(''));
    expect(onRecovered).not.toHaveBeenCalled();
  });

  it('uses explicit hasCompleteProfile from local cache when recovered messages have no profile card', async () => {
    stubLocalStorage({
      'session-session-path-cache': JSON.stringify({
        userUid: 'user-1',
        hasCompleteProfile: true,
        messages: [message('assistant-1', '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。')],
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const onRecoveredMeta = vi.fn();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=session-path-cache');

    render(
      <Harness
        storeSessionId={null}
        token="token-1"
        userUid="user-1"
        onRecovered={onRecovered}
        onRecoveredMeta={onRecoveredMeta}
        tick={0}
      />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [expect.objectContaining({ id: 'assistant-1', content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' })],
        'session-path-cache',
      ),
    );
    expect(onRecoveredMeta).toHaveBeenLastCalledWith({ hasCompleteProfile: true });
    expect(fetchMock).not.toHaveBeenCalled();
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
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
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

  it('keeps a valid remote empty session instead of clearing session_id from the URL', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-empty-session',
        user_uid: 'user-1',
        messages: [],
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-06T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-empty-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith([], 'remote-empty-session'),
    );
    expect(window.location.search).toBe('?session_id=remote-empty-session');
  });

  it('falls back to server recovery when local cache cannot infer completed profile state', async () => {
    stubLocalStorage({
      'session-session-server-meta': JSON.stringify({
        userUid: 'user-1',
        messages: [message('assistant-1', '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。')],
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const onRecoveredMeta = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-server-meta',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的学习路径' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
        ],
        profile: {
          type: 'basic_profile',
          confirmed_info: {
            current_grade: '大三',
            major: '软件工程',
            learning_stage: '项目实践',
            has_clear_goal: '是',
            learning_method_preference: '项目驱动学习',
            learning_pace_preference: '按项目里程碑推进',
            content_preference: ['代码实践', '项目案例'],
            need_guidance: '需要轻量提醒',
            knowledge_foundation: '软件工程基础',
            strengths: '工程实现',
            weaknesses: '大型项目实战经验',
            experience: '做过课程项目',
            short_term_goal: '完成 AI 功能模块',
            long_term_goal: '形成 AI 应用开发能力',
            weekly_available_time: '每周 8 小时',
            constraints: '时间有限',
          },
        },
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
    window.history.replaceState({}, '', '/sprout?session_id=session-server-meta');

    render(
      <Harness
        storeSessionId={null}
        token="token-1"
        userUid="user-1"
        onRecovered={onRecovered}
        onRecoveredMeta={onRecoveredMeta}
        tick={0}
      />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续恢复我的学习路径' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
          }),
        ],
        'session-server-meta',
      ),
    );
    expect(onRecoveredMeta).toHaveBeenLastCalledWith({ hasCompleteProfile: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('prefers inferred incomplete profile over explicit local cache completion flag for unsupported postgraduate grade', async () => {
    stubLocalStorage({
      'session-session-unsupported-cache': JSON.stringify({
        userUid: 'user-1',
        hasCompleteProfile: true,
        messages: [
          {
            id: 'assistant-unsupported',
            role: 'assistant',
            content: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
            status: 'completed',
            timestamp: 1000,
            sessionMessage: {
              type: 'basic_profile',
              stage: 'generated',
              question_mode: 'question_box',
              confirmed_info: {
                current_grade: '研一',
                major: '软件工程',
                learning_stage: '项目实践',
                has_clear_goal: '是',
                learning_method_preference: '项目驱动学习',
                learning_pace_preference: '按项目里程碑推进',
                content_preference: ['代码实践'],
                need_guidance: '需要轻量提醒',
                knowledge_foundation: '软件工程基础',
                strengths: '工程实现',
                weaknesses: '大型项目实战经验',
                experience: '做过课程项目',
                short_term_goal: '完成 AI 功能模块',
                long_term_goal: '形成 AI 应用开发能力',
                weekly_available_time: '每周 8 小时',
                constraints: '时间有限',
              },
              defaulted_fields: [],
              question_md: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
              question_box: { question: '', options: [] },
              text: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
            },
          },
        ],
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const onRecoveredMeta = vi.fn();
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=session-unsupported-cache');

    render(
      <Harness
        storeSessionId={null}
        token="token-1"
        userUid="user-1"
        onRecovered={onRecovered}
        onRecoveredMeta={onRecoveredMeta}
        tick={0}
      />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({
            id: 'assistant-unsupported',
            content: '当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。',
          }),
        ],
        'session-unsupported-cache',
      ),
    );
    expect(onRecoveredMeta).toHaveBeenLastCalledWith({ hasCompleteProfile: false });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('recovers structured learning path from the matching assistant message even when later assistant replies already exist', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-structured-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '先帮我生成学习路径' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
          { type: 'human', data: { content: '我先看看，再继续' } },
          { type: 'ai', data: { content: '好的，我们可以继续调整。' } },
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
    window.history.replaceState({}, '', '/sprout?session_id=remote-structured-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '先帮我生成学习路径' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
            learningPath: expect.objectContaining({
              current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
            }),
          }),
          expect.objectContaining({ role: 'user', content: '我先看看，再继续' }),
          expect.objectContaining({
            role: 'assistant',
            content: '好的，我们可以继续调整。',
          }),
        ],
        'remote-structured-session',
      ),
    );
  });

  it('recovers both learning path and course outline from the server when the persisted assistant text is 学习路径和课程大纲已生成', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-combined-structured-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的学习结果' } },
          { type: 'ai', data: { content: '学习路径和课程大纲已生成' } },
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
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入。',
          sections: [],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-combined-structured-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续恢复我的学习结果' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径和课程大纲已生成',
            learningPath: expect.objectContaining({
              current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
            }),
            courseKnowledge: expect.objectContaining({
              course_id: 'year_3_course_1',
              course_name: 'AI Agent 开发基础能力搭建',
            }),
          }),
        ],
        'remote-combined-structured-session',
      ),
    );
  });

  it('recovers course outline from the server when the persisted assistant text is 课程大纲已生成', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-generic-outline-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '开始第一门课' } },
          { type: 'ai', data: { content: '课程大纲已生成' } },
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
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入。',
          sections: [],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-generic-outline-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '开始第一门课' }),
          expect.objectContaining({
            role: 'assistant',
            content: '课程大纲已生成',
            courseKnowledge: expect.objectContaining({
              course_id: 'year_3_course_1',
              course_name: 'AI Agent 开发基础能力搭建',
            }),
          }),
        ],
        'remote-generic-outline-session',
      ),
    );
  });

  it('does not recover learning path from the server when the persisted assistant text is 课程大纲已生成：《...》', async () => {
    stubLocalStorage();
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'remote-titled-outline-session',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '开始第一门课' } },
          { type: 'ai', data: { content: '课程大纲已生成：《AI Agent 开发基础能力搭建》。' } },
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
        course_knowledge: {
          course_id: 'year_3_course_1',
          course_name: 'AI Agent 开发基础能力搭建',
          grade_year: 'year_3',
          personalization_summary: '先完成需求拆解，再进入接口接入。',
          sections: [],
          learning_sequence: ['第一章：需求拆解'],
          total_estimated_hours: '8 小时',
        },
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=remote-titled-outline-session');

    render(
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '开始第一门课' }),
          expect.objectContaining({
            role: 'assistant',
            content: '课程大纲已生成：《AI Agent 开发基础能力搭建》。',
            courseKnowledge: expect.objectContaining({
              course_id: 'year_3_course_1',
              course_name: 'AI Agent 开发基础能力搭建',
            }),
          }),
        ],
        'remote-titled-outline-session',
      ),
    );

    const recoveredMessages = onRecovered.mock.calls.at(-1)?.[0] as ChatMessage[] | undefined;
    expect(recoveredMessages?.[1]?.learningPath ?? null).toBeNull();
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
      <Harness storeSessionId={null} token="token-1" userUid="user-1" onRecovered={onRecovered} tick={0} />,
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

  it('does not recover another user local session cache and falls back to the server', async () => {
    stubLocalStorage({
      'session-session-cross-user': JSON.stringify({
        userUid: 'user-1',
        messages: [message('assistant-1', '这是别人的本地会话')],
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-cross-user',
        user_uid: 'user-2',
        messages: [
          { type: 'human', data: { content: '继续我的对话' } },
          { type: 'ai', data: { content: '这是当前用户自己的服务端会话' } },
        ],
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-05T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=session-cross-user');

    render(
      <Harness storeSessionId={null} token="token-2" userUid="user-2" onRecovered={onRecovered} tick={0} />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续我的对话' }),
          expect.objectContaining({ role: 'assistant', content: '这是当前用户自己的服务端会话' }),
        ],
        'session-cross-user',
      ),
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls back to server recovery when local cache only has a streaming assistant snapshot', async () => {
    stubLocalStorage({
      'session-session-streaming-local': JSON.stringify({
        userUid: 'user-1',
        hasCompleteProfile: true,
        messages: [
          {
            id: 'assistant-streaming-local',
            role: 'assistant',
            content: '学习路径已生',
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
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const onRecoveredMeta = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-streaming-local',
        user_uid: 'user-1',
        messages: [
          { type: 'human', data: { content: '继续恢复我的学习路径' } },
          { type: 'ai', data: { content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。' } },
        ],
        profile: {
          type: 'basic_profile',
          confirmed_info: {
            current_grade: '大三',
            major: '软件工程',
            learning_stage: '项目实践',
            has_clear_goal: '是',
            learning_method_preference: '项目驱动学习',
            learning_pace_preference: '按项目里程碑推进',
            content_preference: ['代码实践', '项目案例'],
            need_guidance: '需要轻量提醒',
            knowledge_foundation: '软件工程基础',
            strengths: '工程实现',
            weaknesses: '大型项目实战经验',
            experience: '做过课程项目',
            short_term_goal: '完成 AI 功能模块',
            long_term_goal: '形成 AI 应用开发能力',
            weekly_available_time: '每周 8 小时',
            constraints: '时间有限',
          },
        },
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
    window.history.replaceState({}, '', '/sprout?session_id=session-streaming-local');

    render(
      <Harness
        storeSessionId={null}
        token="token-1"
        userUid="user-1"
        onRecovered={onRecovered}
        onRecoveredMeta={onRecoveredMeta}
        tick={0}
      />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({ role: 'user', content: '继续恢复我的学习路径' }),
          expect.objectContaining({
            role: 'assistant',
            content: '学习路径已生成，当前建议先学习《AI Agent 开发基础能力搭建》。',
            learningPath: expect.objectContaining({
              current_learning_course: expect.objectContaining({ course_node_id: 'year_3_course_1' }),
            }),
          }),
        ],
        'session-streaming-local',
      ),
    );
    expect(onRecoveredMeta).toHaveBeenLastCalledWith({ hasCompleteProfile: true });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('falls back to the local streaming snapshot when the server session is still empty', async () => {
    stubLocalStorage({
      'session-session-streaming-empty-remote': JSON.stringify({
        userUid: 'user-1',
        hasCompleteProfile: true,
        messages: [
          {
            id: 'assistant-streaming-empty-remote',
            role: 'assistant',
            content: '学习路径已生',
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
        savedAt: 1000,
      }),
    });
    const onRecovered = vi.fn();
    const onRecoveredMeta = vi.fn();
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        session_id: 'session-streaming-empty-remote',
        user_uid: 'user-1',
        messages: [],
        profile: null,
        year_learning_paths: null,
        course_knowledge: null,
        updated_at: '2026-06-06T10:00:00Z',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    window.history.replaceState({}, '', '/sprout?session_id=session-streaming-empty-remote');

    render(
      <Harness
        storeSessionId={null}
        token="token-1"
        userUid="user-1"
        onRecovered={onRecovered}
        onRecoveredMeta={onRecoveredMeta}
        tick={0}
      />,
    );

    await waitFor(() =>
      expect(onRecovered).toHaveBeenCalledWith(
        [
          expect.objectContaining({
            id: 'assistant-streaming-empty-remote',
            content: '学习路径已生',
            status: 'streaming',
          }),
        ],
        'session-streaming-empty-remote',
      ),
    );
    expect(onRecoveredMeta).toHaveBeenLastCalledWith({ hasCompleteProfile: true });
    expect(window.location.search).toBe('?session_id=session-streaming-empty-remote');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
