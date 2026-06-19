import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import styled from 'styled-components';
import {
  fetchSessionState,
  isCourseKnowledgeStructuredCompletionContent,
  isLearningPathStructuredCompletionContent,
  SessionStreamError,
  streamSession,
  type SessionAgentEvent,
} from '../../api/orchestration';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';
import type { AgentRunStep, AgentRunStepKind, ChatMessage, SessionMessage, ChatStage } from '../../types/chat';
import { chatReducer, initialChatStore, nextMessageId } from '../../onboarding/chatReducer';
import { type SessionRecoveryMeta, useChatSession } from '../../onboarding/hooks/useChatSession';
import { CourseKnowledgeCard } from '../learning/CourseKnowledgeCard';
import { LearningPathCard } from '../learning/LearningPathCard';
import { AiEyes } from './AiEyes';
import { AgentRunTimeline } from './AgentRunTimeline';
import { ChatCard } from './ChatCard';
import { MessageBubble } from './MessageBubble';
import { AssistantMessage } from './AssistantMessage';
import { SystemMessage } from './AssistantMessage';
import { hasCompleteBasicProfileSessionMessage } from '../../lib/profileContract';
import { dispatchLeafGenerationCompleted, dispatchLeafGenerationEvent } from '../../pages/leaf/leafGenerationEvents';
import { HandwritingCanvas } from '../ui/HandwritingCanvas';
import { PenTool } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  buildLearningPathGenerationDraft,
  dispatchLearningPathUpdated,
  findLatestLearningPath,
  hasLearningOutputInMessages,
} from '../../onboarding/learningPathFlow';

const AGENT_LABELS: Record<string, string> = {
  main_agent: '主智能体',
  intent_recognition_agent: '意图识别智能体',
  profile_agent: '基础画像智能体',
  learning_path_intake_agent: '课程草案智能体',
  learning_path_agent: '学习路径智能体',
  course_knowledge_agent: '课程知识智能体',
  learning_resource_agent: '资源推荐智能体',
  dynamic_update_agent: '动态更新智能体',
  chat: '日常对话智能体',
};

function isStructuredMessage(answer: unknown): answer is SessionMessage {
  if (!answer || typeof answer !== 'object') return false;
  const a = answer as Record<string, unknown>;
  return a.type === 'collecting' || a.type === 'basic_profile';
}

interface AgentStepStatus {
  id: string;
  title: string;
  detail: string;
  status: 'pending' | 'running' | 'completed' | 'routed' | 'error';
  agentType?: 'scan' | 'pulse' | 'spin' | 'write';
}

const DEFAULT_AGENT_STEPS: AgentStepStatus[] = [
  { id: 'context', title: '读取上下文', status: 'pending', detail: '等待接收你的学习线索', agentType: 'scan' },
  { id: 'intent', title: '意图识别智能体', status: 'pending', detail: '判断该由哪个智能体处理', agentType: 'scan' },
  { id: 'route', title: '路由决策', status: 'pending', detail: '等待意图识别结果', agentType: 'pulse' },
  { id: 'profile', title: '基础画像智能体', status: 'pending', detail: '等待路由转交', agentType: 'spin' },
  { id: 'update', title: '更新画像 / 生成问题', status: 'pending', detail: '等待智能体返回内容', agentType: 'write' },
];

const MIN_VISIBLE_DURATION_MS = 0.1;

function isLoadedDataUpdate(updateType: string | undefined): boolean {
  return updateType === 'learning_path_loaded' || updateType === 'course_knowledge_loaded';
}

function getDataUpdateLabel(updateType: string | undefined, label: string | undefined): string {
  if (label) return label;
  if (updateType === 'learning_path_loaded') return '学习路径';
  if (updateType === 'course_knowledge_loaded') return '课程大纲';
  if (updateType === 'profile_loaded') return '学习画像';
  if (updateType === 'paths_loaded') return '学习路径';
  return updateType ?? '数据更新';
}

function getTimelineNow(): number {
  return typeof performance !== 'undefined' ? performance.now() : Date.now();
}

function getVisibleDuration(startTime: number, endTime: number): number {
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return MIN_VISIBLE_DURATION_MS;
  return Math.max(endTime - startTime, MIN_VISIBLE_DURATION_MS);
}

function statusLabel(status: 'pending' | 'running' | 'completed' | 'routed' | 'error'): string {
  const map: Record<string, string> = { running: '运行中', completed: '已完成', routed: '已转交', error: '异常', pending: '等待中' };
  return map[status] || '待命';
}

function updateStep(steps: AgentStepStatus[], id: string, status: AgentStepStatus['status'], detail: string): AgentStepStatus[] {
  return steps.map((step) => (step.id === id ? { ...step, status, detail } : step));
}

function getSessionEventAgent(event: SessionAgentEvent): string | undefined {
  return event.agent;
}

function getSessionEventStepId(event: SessionAgentEvent): string {
  return event.stepId ?? getSessionEventAgent(event) ?? event.session_id ?? event.event;
}

export function getSessionEventTimingKey(event: SessionAgentEvent): string {
  const agent = getSessionEventAgent(event);
  if (agent && event.course_id && event.chapter_section_id && event.section_id) {
    return [
      'structured',
      event.kind ?? 'agent',
      agent,
      event.course_id,
      event.chapter_section_id,
      event.section_id,
    ].join('|');
  }
  return `step|${getSessionEventStepId(event)}`;
}

export function rememberSessionEventStartTime(
  starts: Record<string, number>,
  event: SessionAgentEvent,
  now: number,
): void {
  const stepId = getSessionEventStepId(event);
  const timingKey = getSessionEventTimingKey(event);
  const startTime = starts[stepId] ?? starts[timingKey] ?? now;
  starts[stepId] = startTime;
  starts[timingKey] = startTime;
}

export function getSessionEventStartTime(
  starts: Record<string, number>,
  event: SessionAgentEvent,
  fallback: number,
): number {
  return starts[getSessionEventTimingKey(event)] ?? starts[getSessionEventStepId(event)] ?? fallback;
}

function getSessionEventTitle(event: SessionAgentEvent): string {
  const agent = getSessionEventAgent(event);
  return event.label ?? (agent ? AGENT_LABELS[agent] ?? agent : event.event);
}

function getSessionEventDetail(event: SessionAgentEvent): string {
  return event.error ?? event.message ?? event.summary ?? event.reason ?? '等待下一步结果';
}

function getTimelineSummary(event: SessionAgentEvent, fallback: string): string {
  const details = [fallback];
  if (event.parallelGroup) details.push(`并行中：${event.parallelGroup}`);
  if (event.dependsOn && event.dependsOn.length > 0) details.push(`依赖：${event.dependsOn.join('、')}`);
  return details.join(' · ');
}

function upsertPanelStep(
  current: AgentStepStatus[],
  nextStep: AgentStepStatus,
): AgentStepStatus[] {
  const existingIndex = current.findIndex((step) => step.id === nextStep.id);
  if (existingIndex < 0) {
    return [...current, nextStep];
  }

  return current.map((step, index) => (index === existingIndex ? { ...step, ...nextStep } : step));
}

function mergeSessionAgentStep(current: AgentStepStatus[], event: SessionAgentEvent): AgentStepStatus[] {
  if (event.event === 'agent_calling' || event.event === 'agent_progress') {
    return upsertPanelStep(
      updateStep(current, 'context', 'completed', '已读取本轮输入与历史对话'),
      {
        id: getSessionEventStepId(event),
        title: getSessionEventTitle(event),
        status: 'running',
        detail: getSessionEventDetail(event),
        agentType: 'scan',
      },
    );
  }

  if (event.event === 'agent_result') {
    const status = event.success === false ? 'error' : 'completed';
    return upsertPanelStep(current, {
      id: getSessionEventStepId(event),
      title: getSessionEventTitle(event),
      status,
      detail: getSessionEventDetail(event),
      agentType: 'write',
    });
  }

  if (event.event === 'error') {
    return upsertPanelStep(current, {
      id: getSessionEventStepId(event),
      title: getSessionEventTitle(event),
      status: 'error',
      detail: getSessionEventDetail(event),
      agentType: 'write',
    });
  }

  if (event.event === 'data_update') {
    const label = getDataUpdateLabel(event.update_type, event.label);
    const isLoaded = isLoadedDataUpdate(event.update_type);
    return upsertPanelStep(current, {
      id: getSessionEventStepId(event),
      title: isLoaded ? `读取 ${label}` : event.schemaName ? `生成 ${event.schemaName}` : '结构化数据处理中',
      status: 'running',
      detail: isLoaded ? `正在读取已保存的${label}...` : `正在处理 ${label}...`,
      agentType: 'write',
    });
  }



  if (event.event === 'session_completed') {
    return current.map((step) =>
      step.status === 'running' || step.status === 'routed'
        ? { ...step, status: 'completed' as const, detail: '本轮内容已生成' }
        : step,
    );
  }

  return current;
}

function currentProgressLabel(steps: AgentStepStatus[]): string {
  const active = steps.find((step) => step.status === 'running' || step.status === 'routed');
  if (active) return `${active.title}：${active.detail}`;
  const failed = steps.find((step) => step.status === 'error');
  if (failed) return `${failed.title}：${failed.detail}`;
  const completedCount = steps.filter((step) => step.status === 'completed').length;
  if (completedCount > 0) return '本轮智能体调用已完成';
  return '等待你输入学习线索';
}

interface AssistantMessageFrameProps {
  message: ChatMessage;
  children: React.ReactNode;
}

function AssistantMessageFrame({ message, children }: AssistantMessageFrameProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-8)' }}>
      {(message.runTrace && message.runTrace.length > 0) && (
        <AgentRunTimeline
          steps={message.runTrace}
          status={message.status}
        />
      )}
      {children}
    </div>
  );
}

const ONBOARDING_STAGES = [
  { id: 'basic_info', label: '画像线索' },
  { id: 'learning_preference', label: '目标锚定' },
  { id: 'ability_basis', label: '路径生成' },
  { id: 'goal_constraint', label: '持续更新' },
] as const;

interface StepProgressBarProps {
  messages: ChatMessage[];
}

function StepProgressBar({ messages }: StepProgressBarProps) {
  const latestSessionMessage = [...messages]
    .reverse()
    .find((m) => m.sessionMessage)?.sessionMessage;

  const currentStage = latestSessionMessage?.stage || 'basic_info';
  const confirmedInfo = latestSessionMessage?.confirmed_info;

  const STAGE_ORDER: ChatStage[] = ['basic_info', 'learning_preference', 'ability_basis', 'goal_constraint', 'generated'];

  const hasFields = (stage: ChatStage): boolean => {
    if (!confirmedInfo) return false;
    switch (stage) {
      case 'basic_info':
        return !!(confirmedInfo.current_grade || confirmedInfo.major);
      case 'learning_preference':
        return !!(
          confirmedInfo.learning_stage ||
          confirmedInfo.has_clear_goal ||
          confirmedInfo.learning_method_preference ||
          confirmedInfo.learning_pace_preference ||
          (confirmedInfo.content_preference && confirmedInfo.content_preference.length > 0) ||
          confirmedInfo.need_guidance
        );
      case 'ability_basis':
        return !!(
          confirmedInfo.knowledge_foundation ||
          confirmedInfo.strengths ||
          confirmedInfo.weaknesses ||
          confirmedInfo.experience
        );
      case 'goal_constraint':
        return !!(
          confirmedInfo.short_term_goal ||
          confirmedInfo.long_term_goal ||
          confirmedInfo.weekly_available_time ||
          confirmedInfo.constraints
        );
      default:
        return false;
    }
  };

  return (
    <div className="onboarding-step-bar">
      {ONBOARDING_STAGES.map((stage, index) => {
        const currentIndex = STAGE_ORDER.indexOf(currentStage);
        const stageIndex = STAGE_ORDER.indexOf(stage.id);

        let status: 'completed' | 'active' | 'pending' = 'pending';
        if (currentStage === 'generated' || stageIndex < currentIndex) {
          status = 'completed';
        } else if (stage.id === currentStage) {
          status = 'active';
        } else if (hasFields(stage.id)) {
          status = 'completed';
        }

        return (
          <React.Fragment key={stage.id}>
            <div className={`step-node ${status}`} data-status={status}>
              <div className="step-number">
                {status === 'completed' ? '✓' : index + 1}
              </div>
              <div className="step-label">{stage.label}</div>
            </div>
            {index < ONBOARDING_STAGES.length - 1 && (
              <div
                className={`step-connector ${status === 'completed' ? 'completed' : ''}`}
              />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

type ExpandedLayout = 'centered' | 'docked';

interface AiGreetingInputProps {
  expandedLayout?: ExpandedLayout;
}

export function AiGreetingInput({ expandedLayout = 'centered' }: AiGreetingInputProps) {
  const navigate = useNavigate();
  const {
    widgetState,
    setWidgetState,
    pendingMessage,
    clearPendingMessage,
    openWithDraft,
  } = useAiWidget();
  const { token, user } = useAuth();

  const handleGeneratePathDraft = () => {
    openWithDraft(buildLearningPathGenerationDraft());
  };
  const cardRef = useRef<HTMLDivElement>(null);
  const [store, dispatch] = useReducer(chatReducer, initialChatStore);
  const [inputValue, setInputValue] = useState('');
  const [agentSteps, setAgentSteps] = useState<AgentStepStatus[]>(DEFAULT_AGENT_STEPS);
  const [agentEvents, setAgentEvents] = useState<SessionAgentEvent[]>([]);
  const [showEventLog, setShowEventLog] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [showCanvas, setShowCanvas] = useState(false);
  const [imageAttachment, setImageAttachment] = useState<string | null>(null);
  const [hiddenPathActionsMessageId, setHiddenPathActionsMessageId] = useState<string | null>(null);

  const runIdRef = useRef(0);
  const startTimeRef = useRef<Record<string, number>>({});
  const runStartTimeRef = useRef(0);
  const lastEventTimeRef = useRef(0);
  const executionIdRef = useRef<string | null>(null);
  const hasCompleteProfileRef = useRef(false);
  const recoveryMetaRef = useRef<SessionRecoveryMeta | null>(null);
  const finalTextRef = useRef('');
  const accumulatedTextRef = useRef('');
  const retryActionRef = useRef<'retry_learning_path' | null>(null);
  const consumedPendingMessageIdRef = useRef<number | null>(null);
  const resetConversationOnNextSendRef = useRef(false);
  const leafCourseIdRef = useRef<string | null>(null);

  const isPending = store.state === 'connecting' || store.state === 'streaming';
  const aiMood = store.state === 'error' ? 'error' : isPending ? 'thinking' : store.messages.some((m) => m.role === 'assistant' && m.status === 'completed') ? 'happy' : 'idle';
  const latestLearningPathMessage = (() => {
    for (let index = store.messages.length - 1; index >= 0; index -= 1) {
      if (store.messages[index].learningPath) {
        return store.messages[index];
      }
    }
    return null;
  })();
  const latestLearningPath = findLatestLearningPath(store.messages);
  const latestLearningPathMessageId = latestLearningPathMessage?.id ?? null;
  const shouldShowPathActions = Boolean(
    latestLearningPath && latestLearningPathMessageId !== hiddenPathActionsMessageId,
  );
  const hasLearningOutput = hasLearningOutputInMessages(store.messages);
  const isLearningPathStage = hasLearningOutput || store.messages.some(
    (m) =>
      Boolean(m.learningPath) ||
      Boolean(m.runTrace && m.runTrace.some((t) => t.agent === 'learning_path_intake_agent' || t.agent === 'learning_path_agent')) ||
      (m.role === 'user' && m.content === buildLearningPathGenerationDraft())
  );

  const handleOpenPath = () => {
    setHiddenPathActionsMessageId(latestLearningPathMessageId);
    setWidgetState('WIDGET');
    navigate('/branch', { state: { justGeneratedProfile: true } });
  };

  const { persistSession, clearSessionFromUrl, clearPersistedSession } = useChatSession(
    store.currentSessionId,
    token,
    user?.uid ?? null,
    (messages, sessionId) => {
      dispatch({ type: 'LOAD_SESSION', messages, sessionId });
      executionIdRef.current = sessionId;
      hasCompleteProfileRef.current = recoveryMetaRef.current?.hasCompleteProfile ?? messages.some(
        (m) => m.role === 'assistant' && hasCompleteBasicProfileSessionMessage(m.sessionMessage),
      );
      window.dispatchEvent(new CustomEvent('mutiagent-profile-updated'));
    },
    recoveryMetaRef,
  );

  const clearInvalidSessionAnchor = useCallback((sessionId: string | null) => {
    if (sessionId) {
      clearPersistedSession(sessionId);
    }
    executionIdRef.current = null;
    hasCompleteProfileRef.current = false;
    resetConversationOnNextSendRef.current = true;
    dispatch({ type: 'SET_SESSION_ID', sessionId: null });
    clearSessionFromUrl();
  }, [clearPersistedSession, clearSessionFromUrl]);

  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const mouseXSpring = useSpring(x, { stiffness: 150, damping: 20 });
  const mouseYSpring = useSpring(y, { stiffness: 150, damping: 20 });
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ['15deg', '-15deg']);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ['-15deg', '15deg']);
  const expandedCardVariant = expandedLayout === 'docked'
    ? {
      width: 'min(86.6vw, calc(100vw - (var(--space-24) * 2)))',
      height: 'min(86.6vh, calc(100vh - (var(--space-24) * 2)))',
    }
    : { width: '85vw', height: '85vh' };

  useEffect(() => {
    const handleGlobalMouseMove = (event: MouseEvent) => {
      if (widgetState !== 'CENTER_INPUT' && widgetState !== 'WIDGET') return;
      if (!cardRef.current) return;
      const rect = cardRef.current.getBoundingClientRect();
      const cardCenterX = rect.left + rect.width / 2;
      const cardCenterY = rect.top + rect.height / 2;
      const xPct = Math.max(-0.5, Math.min(0.5, (event.clientX - cardCenterX) / window.innerWidth));
      const yPct = Math.max(-0.5, Math.min(0.5, (event.clientY - cardCenterY) / window.innerHeight));
      x.set(xPct);
      y.set(yPct);
    };
    const handleGlobalMouseLeave = () => { x.set(0); y.set(0); };
    window.addEventListener('mousemove', handleGlobalMouseMove);
    document.addEventListener('mouseleave', handleGlobalMouseLeave);
    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      document.removeEventListener('mouseleave', handleGlobalMouseLeave);
    };
  }, [widgetState, x, y]);

  const eventToStep = useCallback((event: SessionAgentEvent, now: number): { step: AgentRunStep | null } => {
    const agent = getSessionEventAgent(event);
    const label = getSessionEventTitle(event);
    const kind: AgentRunStepKind = (event.kind as AgentRunStepKind) || 'agent';

    if (event.event === 'agent_calling' || event.event === 'agent_progress') {
      const stepId = getSessionEventStepId(event);
      rememberSessionEventStartTime(startTimeRef.current, event, now);
      return {
        step: {
          stepId,
          kind,
          status: 'running',
          title: label,
          summary: getTimelineSummary(event, event.message ?? '正在执行...'),
          agent: agent ?? null,
          startedAtMs: getSessionEventStartTime(startTimeRef.current, event, now),
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'agent_result') {
      const stepId = getSessionEventStepId(event);
      const startTime = getSessionEventStartTime(
        startTimeRef.current,
        event,
        lastEventTimeRef.current || runStartTimeRef.current || now,
      );
      const status = event.success === false ? 'error' : 'success';
      const fallbackSummary = event.success === false ? '这一步没有正常完成' : '完成';
      return {
        step: {
          stepId,
          kind,
          status,
          title: label,
          summary: getTimelineSummary(event, event.summary ?? event.error ?? event.message ?? fallbackSummary),
          agent: agent ?? null,
          startedAtMs: startTime,
          durationMs: getVisibleDuration(startTime, now),
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'error') {
      const stepId = getSessionEventStepId(event);
      const startTime = getSessionEventStartTime(
        startTimeRef.current,
        event,
        lastEventTimeRef.current || runStartTimeRef.current || now,
      );
      return {
        step: {
          stepId,
          kind,
          status: 'error',
          title: label,
          summary: getTimelineSummary(event, event.error ?? event.message ?? '这一步没有正常完成'),
          agent: agent ?? null,
          startedAtMs: startTime,
          durationMs: getVisibleDuration(startTime, now),
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'supervisor_plan') {
      const stepId = getSessionEventStepId(event);
      const toolStepId = `tool-${event.toolName ?? stepId}`;
      return {
        step: {
          stepId: toolStepId,
          kind: 'tool_call' as AgentRunStepKind,
          status: 'running',
          title: event.label ?? `调用 ${event.toolName ?? '工具'}`,
          summary: getTimelineSummary(event, event.message ?? '正在调用...'),
          agent: agent ?? null,
          startedAtMs: now,
        },
      };
    }

    if (event.event === 'session_completed') {
      const startTime = lastEventTimeRef.current || runStartTimeRef.current || now;
      return {
        step: {
          stepId: `step-answer-${event.session_id ?? now}`,
          kind: 'answer',
          status: 'success',
          title: '生成回复',
          summary: event.message ?? '本轮内容已生成',
          agent: agent ?? null,
          startedAtMs: startTime,
          durationMs: getVisibleDuration(startTime, now),
        },
      };
    }

    return { step: null };
  }, []);

  const sendMessage = useCallback(
    async (text: string, imageAttachmentArg?: string | null) => {
      const query = text.trim();
      if ((!query && !imageAttachmentArg) || isPending) return;
      if (!token) {
        setGlobalError('请先登录后再开始基础画像对话。');
        return;
      }
      if (resetConversationOnNextSendRef.current) {
        dispatch({ type: 'NEW_SESSION' });
        resetConversationOnNextSendRef.current = false;
      }

      setInputValue('');
      const userMsgId = nextMessageId();
      dispatch({
        type: 'ADD_USER_MESSAGE',
        id: userMsgId,
        content: query,
        imageAttachment: imageAttachmentArg ?? null,
      });

      const assistantMsgId = nextMessageId();
      dispatch({ type: 'ADD_ASSISTANT_MESSAGE', id: assistantMsgId });
      dispatch({ type: 'CONNECTING' });

      setAgentSteps(DEFAULT_AGENT_STEPS);
      setAgentEvents([]);
      setShowEventLog(false);
      setGlobalError(null);

      const runId = runIdRef.current + 1;
      runIdRef.current = runId;
      startTimeRef.current = {};
      const runStartedAt = getTimelineNow();
      runStartTimeRef.current = runStartedAt;
      lastEventTimeRef.current = runStartedAt;
      retryActionRef.current = null;
      let finalSessionId: string | undefined;

      try {
        let finalTurnText = '';
        let finalTurnHasPaths = false;
        let finalTurnHasOutline = false;
        let generatedProfileThisTurn = false;
        let generatedLearningPathThisTurn = false;
        let generatedCourseOutlineThisTurn = false;
        let loadedLearningPathThisTurn = false;
        let loadedCourseOutlineThisTurn = false;

        const turn = await streamSession(
          token,
          query,
          executionIdRef.current,
          (event) => {
            if (runIdRef.current !== runId) return;
            setAgentSteps((current) => mergeSessionAgentStep(current, event));
            setAgentEvents((current) => [...current, event]);
            dispatchLeafGenerationEvent(event);
            if (event.course_id) {
              leafCourseIdRef.current = event.course_id;
            }

            if (event.event === 'supervisor_thinking') {
              dispatch({ type: 'MESSAGE_STARTED', messageId: assistantMsgId });
              return;
            }

            if (event.event === 'session_started') {
              finalSessionId = event.session_id ?? finalSessionId;
              executionIdRef.current = event.session_id ?? executionIdRef.current;
              if (event.session_id) {
                dispatch({ type: 'SET_SESSION_ID', sessionId: event.session_id });
              }
              return;
            }

            if (event.event === 'text_chunk' && event.chunk) {
              accumulatedTextRef.current += event.chunk;
              dispatch({ type: 'TEXT_CHUNK', messageId: assistantMsgId, chunk: event.chunk });
              return;
            }

            if (event.event === 'supervisor_plan') {
              if (event.event === 'supervisor_plan') {
                dispatch({ type: 'STREAMING_STARTED' });
              }
              const { step } = eventToStep(event, getTimelineNow());
              if (step) {
                dispatch({ type: 'STEP', messageId: assistantMsgId, step });
              }
              lastEventTimeRef.current = getTimelineNow();
              return;
            }

            if (event.event === 'data_update') {
              if (event.update_type === 'learning_path_loaded') {
                loadedLearningPathThisTurn = true;
              }
              if (event.update_type === 'course_knowledge_loaded') {
                loadedCourseOutlineThisTurn = true;
              }
              dispatch({
                type: 'DATA_SCHEMA_STARTED',
                messageId: assistantMsgId,
                schemaName: getDataUpdateLabel(event.update_type, event.label),
              });
              return;
            }

            if (event.event === 'message_completed' && event.full_text) {
              finalTextRef.current = event.full_text;
              if (isLearningPathStructuredCompletionContent(event.full_text)) {
                loadedLearningPathThisTurn = true;
              }
              if (isCourseKnowledgeStructuredCompletionContent(event.full_text)) {
                loadedCourseOutlineThisTurn = true;
              }
              return;
            }

            const now = getTimelineNow();

            if (
              event.event === 'agent_calling'
              || event.event === 'agent_progress'
              || event.event === 'agent_result'
              || event.event === 'error'
              || event.event === 'session_completed'
            ) {
              if (event.event === 'agent_calling') {
                dispatch({ type: 'STREAMING_STARTED' });
              }
              const { step } = eventToStep(event, now);
              if (step) {
                dispatch({ type: 'STEP', messageId: assistantMsgId, step });
              }
              lastEventTimeRef.current = now;
            }

            if (event.event === 'agent_result' && event.success) {
              if (event.agent === 'profile_agent') {
                generatedProfileThisTurn = true;
              }
              if (event.agent === 'learning_path_agent') {
                generatedLearningPathThisTurn = true;
              }
              if (event.agent === 'course_knowledge_agent') {
                generatedCourseOutlineThisTurn = true;
              }
            }

            if (event.event === 'session_completed') {
              if (leafCourseIdRef.current) {
                dispatchLeafGenerationCompleted(leafCourseIdRef.current);
                leafCourseIdRef.current = null;
              }
              const text = finalTextRef.current || accumulatedTextRef.current || '';
              finalTurnText = text;
              finalTurnHasPaths = event.has_paths ?? false;
              finalTurnHasOutline = event.has_outline ?? false;
              executionIdRef.current = event.session_id ?? null;
              hasCompleteProfileRef.current = event.has_profile ?? false;
              finalSessionId = event.session_id ?? undefined;

              dispatch({
                type: 'RUN_DONE',
                messageId: assistantMsgId,
                content: text,
                sessionMessage: null,
                agentAnswer: null,
                learningPath: null,
                sessionId: event.session_id ?? undefined,
              });
              finalTextRef.current = '';
              accumulatedTextRef.current = '';
              retryActionRef.current = null;
            }

            if (event.event === 'error') {
              retryActionRef.current = event.retryAction ?? null;
              const message = event.error ?? event.message ?? '对话请求失败，请稍后重试';
              dispatch({
                type: 'RUN_ERROR',
                messageId: assistantMsgId,
                message,
                retryAction: retryActionRef.current,
              });
              setGlobalError(message);
            }
          },
          imageAttachmentArg,
        );

        if (runIdRef.current !== runId) return;

        finalSessionId = finalSessionId ?? turn.sessionId;
        finalTurnText = finalTurnText || turn.text;
        finalTurnHasPaths = finalTurnHasPaths || turn.hasPaths;
        finalTurnHasOutline = finalTurnHasOutline || turn.hasOutline;

        if (finalSessionId) {
          executionIdRef.current = finalSessionId;
        }

        const shouldFetchLearningPath = generatedLearningPathThisTurn || loadedLearningPathThisTurn;
        const shouldFetchCourseOutline = generatedCourseOutlineThisTurn || loadedCourseOutlineThisTurn;
        const shouldFetchProfile = generatedProfileThisTurn;

        if (finalSessionId && (shouldFetchProfile || shouldFetchLearningPath || shouldFetchCourseOutline)) {
          try {
            const structuredData = await fetchSessionState(token, finalSessionId);
            if (runIdRef.current !== runId) return;
            dispatch({
              type: 'RUN_DONE',
              messageId: assistantMsgId,
              content: finalTurnText,
              sessionMessage: shouldFetchProfile ? structuredData.profile : null,
              agentAnswer: null,
              learningPath: shouldFetchLearningPath ? structuredData.learningPath : null,
              courseKnowledge: shouldFetchCourseOutline ? structuredData.courseKnowledge : null,
              sessionId: finalSessionId,
            });
            if (shouldFetchCourseOutline && structuredData.courseKnowledge?.course_id) {
              dispatchLeafGenerationCompleted(structuredData.courseKnowledge.course_id, 'course_outline');
            }
            if (shouldFetchLearningPath && structuredData.learningPath) {
              dispatchLearningPathUpdated(finalSessionId);
            }
          } catch {
            // Ignore structured follow-up errors and keep text result visible.
          }
        }

        if (hasCompleteProfileRef.current) {
          window.dispatchEvent(new CustomEvent('mutiagent-profile-updated'));
        }
      } catch (err) {
        if (runIdRef.current !== runId) return;
        const errorSessionId = err instanceof SessionStreamError
          ? err.sessionId ?? finalSessionId ?? executionIdRef.current
          : finalSessionId ?? executionIdRef.current;
        if (errorSessionId) {
          finalSessionId = errorSessionId;
          executionIdRef.current = errorSessionId;
          dispatch({ type: 'SET_SESSION_ID', sessionId: errorSessionId });
        }
        const message = err instanceof Error ? err.message : '对话请求失败，请稍后重试';
        if (message === '会话不存在') {
          clearInvalidSessionAnchor(finalSessionId ?? executionIdRef.current);
        }
        dispatch({
          type: 'RUN_ERROR',
          messageId: assistantMsgId,
          message,
          sessionId: finalSessionId,
          retryAction: retryActionRef.current,
        });
        setGlobalError(message);
        setAgentSteps((current) =>
          current.map((step) =>
            step.status === 'running' || step.status === 'routed'
              ? { ...step, status: 'error' as const, detail: '这一步没有正常完成' }
              : step,
          ),
        );
      }
    },
    [clearInvalidSessionAnchor, isPending, token, eventToStep],
  );

  const retryLearningPath = useCallback(() => {
    void sendMessage('重试生成学习路径');
  }, [sendMessage]);

  useEffect(() => {
    if (widgetState !== 'EXPANDED') return;
    if (!pendingMessage) return;
    if (isPending) return;
    if (consumedPendingMessageIdRef.current === pendingMessage.id) return;

    consumedPendingMessageIdRef.current = pendingMessage.id;
            clearPendingMessage();
    if (pendingMessage.mode === 'draft') {
      setInputValue(pendingMessage.text);
      return;
    }
    void sendMessage(pendingMessage.text);
  }, [clearPendingMessage, isPending, pendingMessage, sendMessage, widgetState]);

  useEffect(() => {
    if (
      (store.state === 'idle' || store.state === 'error' || store.state === 'streaming')
      && store.currentSessionId
      && store.messages.length > 0
    ) {
      persistSession(store.currentSessionId, store.messages, hasCompleteProfileRef.current);
    }
  }, [store.state, store.currentSessionId, store.messages, persistSession]);

  const handleCardClick = () => {
    if (widgetState === 'CENTER_INPUT' || widgetState === 'WIDGET') {
      x.set(0);
      y.set(0);
      setWidgetState('EXPANDED');
    }
  };

  const handleSubmit = () => {
    void sendMessage(inputValue, imageAttachment);
    setInputValue('');
    setImageAttachment(null);
  };

  function renderMessage(message: ChatMessage, isLatestInteractive: boolean) {
    if (message.role === 'user') {
      return (
        <MessageBubble
          key={message.id}
          content={message.content}
          imageAttachment={message.imageAttachment}
        />
      );
    }

    if (message.role === 'system') {
      return <SystemMessage key={message.id} message={message} />;
    }

    if (message.role === 'assistant') {
      let assistantContent: React.ReactNode;

      if (message.learningPath && message.courseKnowledge) {
        assistantContent = (
          <div className="assistant-structured-stack">
            <LearningPathCard path={message.learningPath} />
            <CourseKnowledgeCard outline={message.courseKnowledge} />
          </div>
        );
      } else if (message.learningPath) {
        assistantContent = <LearningPathCard path={message.learningPath} />;
      } else if (message.courseKnowledge) {
        assistantContent = <CourseKnowledgeCard outline={message.courseKnowledge} />;
      } else if (message.sessionMessage && isStructuredMessage(message.sessionMessage)) {
        assistantContent = (
          <ChatCard
            message={message.sessionMessage}
            onSendReply={isLatestInteractive ? sendMessage : undefined}
            disabled={!isLatestInteractive || isPending}
            partialData={message.partialData ?? null}
            showPathGenerationCta={isLatestInteractive && !hasLearningOutput}
          />
        );
      } else {
        assistantContent = (
          <AssistantMessage
            message={message}
            onSendReply={isLatestInteractive ? sendMessage : undefined}
            onRetryLearningPath={
              message.retryAction === 'retry_learning_path' ? retryLearningPath : undefined
            }
            disabled={!isLatestInteractive || isPending}
            showTimeline={false}
          />
        );
      }

      return (
        <AssistantMessageFrame key={message.id} message={message}>
          {assistantContent}
        </AssistantMessageFrame>
      );
    }

    return null;
  }

  return (
    <StyledWrapper>
      <motion.div
        ref={cardRef}
        layout
        onClick={handleCardClick}
        className={`card ${widgetState === 'CENTER_INPUT' ? 'initial' : widgetState}`}
        variants={{
          initial: { width: 260, height: 160 },
          expanded: expandedCardVariant,
          widget: { width: 100, height: 100 },
        }}
        initial="initial"
        animate={
          widgetState === 'EXPANDED'
            ? 'expanded'
            : widgetState === 'WIDGET'
              ? 'widget'
              : 'initial'
        }
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        style={{
          rotateX: widgetState === 'EXPANDED' ? 0 : rotateX,
          rotateY: widgetState === 'EXPANDED' ? 0 : rotateY,
          cursor: widgetState === 'EXPANDED' ? 'default' : 'pointer',
        }}
      >
        {widgetState === 'EXPANDED' ? (
          <section className="session-panel" aria-label={isLearningPathStage ? "AI 学习路径对话" : "AI 基础画像对话"}>
            <header className="session-header">
              <div className="session-title-cluster">
                <div className="agent-face" data-ai-state={aiMood}>
                  <span className="agent-face-glow" aria-hidden="true" />
                  <AiEyes layoutId="eyes" isHappy={aiMood === 'happy'} />
                </div>
                <div className="session-title-copy">
                  <span>{isLearningPathStage ? "学习路径对话" : "基础画像对话"}</span>
                  <strong>{currentProgressLabel(agentSteps)}</strong>
                </div>
              </div>
              <button
                type="button"
                className="collapse-button"
                aria-label="收起 AI 对话"
                onClick={(event) => {
                  event.stopPropagation();
                  setWidgetState('WIDGET');
                }}
              >
                <span aria-hidden="true">✕</span>
              </button>
            </header>

            {globalError && (
              <div className="global-error">
                <span>{globalError}</span>
                <button type="button" onClick={() => setGlobalError(null)} aria-label="关闭">×</button>
              </div>
            )}

            <div className="session-workbench">
              <main className="chat-column" aria-label="对话内容">
                <StepProgressBar messages={store.messages} />
                <div className="chat-flow">
                  {store.messages.length === 0 && (
                    <div className="chat-empty-state">
                      欢迎！告诉我你的年级、专业、学习目标或当前卡点，我会先整理基础画像，再生成可迭代的学习路径。
                    </div>
                  )}

                  {store.messages.map((message, index) => {
                    const hasSubsequentUserMessage = store.messages
                      .slice(index + 1)
                      .some((m) => m.role === 'user');
                    return renderMessage(message, !hasSubsequentUserMessage);
                  })}
                </div>

                <div className="composer-container">
                  {imageAttachment && (
                    <div className="image-preview-box">
                      <img
                        src={imageAttachment}
                        alt="Preview"
                        className="preview-thumbnail"
                      />
                      <button
                        type="button"
                        className="delete-preview-button"
                        onClick={() => setImageAttachment(null)}
                        aria-label="删除图片"
                      >
                        ✕
                      </button>
                    </div>
                  )}
                  {hasCompleteProfileRef.current && !isLearningPathStage && !hasLearningOutput && !isPending && !inputValue.trim() && !imageAttachment && !(pendingMessage && pendingMessage.mode === 'draft') ? (
                    <div className="composer-completed-cta-panel">
                      <button className="cta-completed-btn" onClick={handleGeneratePathDraft} type="button">
                        <span>确认并生成学习路径</span>
                        <span className="arrow">➔</span>
                      </button>
                    </div>
                  ) : (
                    <>
                      {shouldShowPathActions && (
                        <div className="composer-path-actions">
                          <button type="button" onClick={handleOpenPath}>
                            开始学习
                          </button>
                        </div>
                      )}
                      <form
                        className="chat-composer"
                        onSubmit={(event) => {
                          event.preventDefault();
                          handleSubmit();
                        }}
                      >
                        <textarea
                          rows={1}
                          placeholder="输入你的学习情况..."
                          value={inputValue}
                          disabled={isPending}
                          onChange={(event) => setInputValue(event.target.value)}
                          onKeyDown={(event) => {
                            if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
                              handleSubmit();
                            }
                          }}
                        />
                        <button
                          type="button"
                          className="pen-button"
                          disabled={isPending}
                          onClick={() => setShowCanvas(true)}
                          aria-label="手写/绘图输入"
                        >
                          <PenTool className="w-4 h-4" />
                        </button>
                        <button
                          type="submit"
                          className="submit-button"
                          disabled={isPending || (!inputValue.trim() && !imageAttachment)}
                          aria-label="发送消息"
                        >
                          <span aria-hidden="true">+</span>
                        </button>
                      </form>
                    </>
                  )}
                </div>
              </main>

              <aside className="codex-agent-panel" aria-label="多智能体调用状态">
                <section className="agent-panel-section agent-panel-progress">
                  {agentEvents.length > 0 ? (
                    <button
                      type="button"
                      className="agent-panel-heading"
                      onClick={() => setShowEventLog((value) => !value)}
                      aria-expanded={showEventLog}
                    >
                      <span>进度</span>
                      <span aria-hidden="true">{showEventLog ? '⌃' : '⌄'}</span>
                    </button>
                  ) : (
                    <div className="agent-panel-heading static">
                      <span>进度</span>
                    </div>
                  )}
                  <p>{currentProgressLabel(agentSteps)}</p>
                </section>

                <section className="agent-panel-section">
                  <div className="agent-panel-heading static">
                    <span>Agent 步骤</span>
                    {agentSteps.some(s => s.status !== 'pending') && (
                      <strong>{isPending ? '运行中' : '待命'}</strong>
                    )}
                  </div>
                  <div className="agent-step-list">
                    {(() => {
                      const activeSteps = agentSteps.filter(
                        s => s.status === 'running' || s.status === 'routed' || s.status === 'error'
                      );
                      if (activeSteps.length === 0) {
                        const label = isPending
                          ? '等待调用...'
                          : agentSteps.some(s => s.status === 'completed')
                            ? '本轮调用已完成'
                            : '等待本轮调用开始...';
                        return <p className="agent-step-placeholder">{label}</p>;
                      }
                      return (
                        <AnimatePresence mode="popLayout">
                          {activeSteps.map((step) => (
                            <motion.div
                              className="agent-step-row"
                              data-status={step.status}
                              data-agent-type={step.agentType || 'default'}
                              key={step.id}
                              initial={{ opacity: 0, x: -16, scale: 0.96 }}
                              animate={{ opacity: 1, x: 0, scale: 1 }}
                              exit={{ opacity: 0, scale: 0.94, y: -4 }}
                              transition={{ duration: 0.42, ease: [0.25, 1, 0.5, 1] }}
                            >
                              <span className="agent-step-dot" aria-hidden="true" />
                              <div>
                                <strong>{step.title}</strong>
                                <p>{step.detail}</p>
                              </div>
                              <span>{statusLabel(step.status)}</span>
                            </motion.div>
                          ))}
                        </AnimatePresence>
                      );
                    })()}
                  </div>
                </section>

                {agentEvents.length > 0 && showEventLog && (
                  <section className="agent-panel-section">
                    <div className="agent-event-log">
                      {agentEvents.map((event, index) => (
                        <p key={`${event.event}-${index}`}>
                          <strong>{event.label || getSessionEventAgent(event) || event.event}</strong>
                          <span>{event.message || event.summary || event.reason || event.intent || event.event}</span>
                        </p>
                      ))}
                    </div>
                  </section>
                )}
              </aside>
            </div>
          </section>
        ) : (
          <div className="widget-shell">
            <AiEyes layoutId="eyes" />
            <AiEyes isHappy />
          </div>
        )}
      </motion.div>
      {showCanvas && (
        <HandwritingCanvas
          onSave={(base64Data) => {
            setImageAttachment(base64Data);
            setShowCanvas(false);
          }}
          onClose={() => setShowCanvas(false)}
        />
      )}
    </StyledWrapper>
  );
}

const StyledWrapper = styled.div`
  perspective: 1000px;
  display: flex;
  align-items: center;
  justify-content: center;

  .card {
    transform-style: preserve-3d;
    will-change: transform, width, height;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-lg);
    background: var(--color-surface-raised);
    box-shadow: var(--shadow-md);
    overflow: hidden;
  }

  .card.initial,
  .card.WIDGET {
    background:
      radial-gradient(circle at 24% 24%, oklch(84% 0.12 63 / 0.36), transparent 36%),
      radial-gradient(circle at 78% 70%, oklch(75% 0.09 135 / 0.24), transparent 34%),
      var(--glass-bg);
    backdrop-filter: var(--glass-blur);
  }

  .card.initial:hover,
  .card.WIDGET:hover {
    transform: translateY(calc(var(--space-4) * -1)) scale(1.01);
    box-shadow: var(--shadow-lg);
  }

  .widget-shell {
    inline-size: 100%;
    block-size: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    transform: translateZ(var(--space-40));
  }

  .widget-shell .eyes.happy { display: none; }

  .card:hover .widget-shell .eyes:not(.happy) { display: none; }
  .card:hover .widget-shell .eyes.happy { display: flex; }

  .session-panel {
    inline-size: 100%;
    block-size: 100%;
    display: flex;
    flex-direction: column;
    padding: var(--space-16);
    gap: var(--space-12);
    background:
      radial-gradient(circle at 12% 0%, oklch(84% 0.12 63 / 0.16), transparent 32%),
      var(--color-surface-raised);
  }

  .session-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gap-sm);
    min-block-size: var(--space-48);
    border-block-end: 1px solid var(--color-border);
    padding-block-end: var(--space-12);
    flex-shrink: 0;
  }

  .session-title-cluster {
    min-inline-size: 0;
    display: flex;
    align-items: center;
    gap: var(--gap-sm);
  }

  .agent-face {
    position: relative;
    display: grid;
    place-items: center;
    inline-size: var(--space-48);
    min-inline-size: var(--space-48);
    block-size: var(--space-48);
    border-radius: var(--radius-md);
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
  }

  .agent-face-glow {
    position: absolute;
    inset: calc(var(--space-12) * -1);
    border-radius: var(--radius-full);
    background: var(--effect-peach-glow);
    filter: var(--effect-blur-soft);
    opacity: 0.5;
    animation: agent-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  }

  .agent-face[data-ai-state='thinking'] .agent-face-glow,
  .agent-face[data-ai-state='running'] .agent-face-glow {
    background: var(--effect-sage-glow);
    opacity: 0.66;
  }

  .session-title-copy {
    min-inline-size: 0;
    display: grid;
    gap: var(--space-4);
  }

  .session-title-copy span {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .session-title-copy strong {
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.45;
    text-wrap: pretty;
  }

  .global-error {
    display: flex;
    align-items: center;
    gap: var(--space-12);
    padding: var(--space-8) var(--space-16);
    border-radius: var(--radius-md);
    background: var(--color-error-bg);
    color: var(--color-error);
    font-size: var(--text-caption);
    flex-shrink: 0;
    animation: globalErrorShake 0.4s ease both;

    button {
      margin-left: auto;
      background: none;
      border: none;
      color: var(--color-error);
      font-size: var(--text-h4);
      cursor: pointer;
      padding: 0 var(--space-4);
      line-height: 1;
    }
  }

  @keyframes globalErrorShake {
    0% { transform: translateX(0); }
    20% { transform: translateX(-4px); }
    40% { transform: translateX(4px); }
    60% { transform: translateX(-4px); }
    80% { transform: translateX(4px); }
    100% { transform: translateX(0); }
  }

  .session-workbench {
    position: relative;
    flex: 1;
    min-block-size: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
    gap: var(--gap-md);
    align-items: stretch;
    overflow: hidden;
  }

  .chat-column {
    min-inline-size: 0;
    min-block-size: 0;
    display: flex;
    flex-direction: column;
    position: relative;
  }

  .codex-agent-panel {
    align-self: start;
    max-block-size: 100%;
    overflow: auto;
    border: 1px solid oklch(92% 0.025 75 / 0.12);
    border-radius: var(--radius-lg);
    padding: var(--space-16);
    background: var(--gradient-night);
    color: var(--color-text-inverse);
    box-shadow: var(--shadow-lg);
  }

  .agent-panel-section {
    display: grid;
    gap: var(--space-12);
    padding-block: var(--space-16);
    border-block-end: 1px solid oklch(92% 0.025 75 / 0.10);
  }

  .agent-panel-section:first-child { padding-block-start: 0; }
  .agent-panel-section:last-child { border-block-end: none; padding-block-end: 0; }

  .agent-panel-heading {
    inline-size: 100%;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gap-sm);
    border: none;
    background: transparent;
    color: oklch(92% 0.025 75 / 0.72);
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
    padding: 0;
    cursor: pointer;
  }

  .agent-panel-heading.static { cursor: default; }

  .agent-panel-heading strong {
    border-radius: var(--radius-full);
    padding: var(--space-4) var(--space-8);
    background: oklch(92% 0.025 75 / 0.12);
    color: var(--color-text-inverse);
    font-size: var(--text-caption);
    font-weight: var(--font-weight-medium);
  }

  .agent-panel-progress p {
    margin: 0;
    color: var(--color-text-inverse);
    font-size: var(--text-h6);
    line-height: 1.6;
    text-wrap: pretty;
  }

  .agent-step-list,
  .agent-event-log {
    display: grid;
    gap: var(--space-8);
  }

  .agent-step-row {
    position: relative;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-12);
    border-radius: var(--radius-md);
    padding: var(--space-12);
    background: oklch(92% 0.025 75 / 0.08);
    overflow: hidden;
  }

  .agent-step-row::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: var(--radius-md);
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.5s var(--ease-editorial);
  }

  .agent-step-row[data-status='running']::before,
  .agent-step-row[data-status='routed']::before {
    opacity: 1;
    background: linear-gradient(90deg, oklch(78% 0.06 75 / 0.12) 0%, transparent 80%);
  }

  .agent-step-row[data-status='error']::before {
    opacity: 1;
    background: linear-gradient(90deg, oklch(72% 0.08 28 / 0.12) 0%, transparent 80%);
  }

  .agent-step-dot {
    inline-size: var(--space-12);
    block-size: var(--space-12);
    border-radius: var(--radius-full);
    background: oklch(92% 0.025 75 / 0.28);
    transition: background 0.4s var(--ease-editorial);
  }

  .agent-step-row[data-status='running'] .agent-step-dot,
  .agent-step-row[data-status='routed'] .agent-step-dot {
    background: var(--color-primary);
  }

  .agent-step-row[data-status='error'] .agent-step-dot {
    background: var(--color-error);
  }

  .agent-step-row[data-agent-type='scan'][data-status='running'] .agent-step-dot {
    animation: dot-scan 1.8s var(--ease-editorial) infinite;
  }

  .agent-step-row[data-agent-type='pulse'][data-status='running'] .agent-step-dot,
  .agent-step-row[data-agent-type='pulse'][data-status='routed'] .agent-step-dot {
    animation: dot-pulse 1.2s var(--ease-editorial) infinite;
  }

  .agent-step-row[data-agent-type='spin'][data-status='running'] .agent-step-dot {
    animation: dot-spin 2.4s linear infinite;
  }

  .agent-step-row[data-agent-type='write'][data-status='running'] .agent-step-dot {
    animation: dot-write 0.8s ease-in-out infinite;
  }

  .agent-step-row[data-status='error'] .agent-step-dot {
    animation: dot-shake 0.5s var(--ease-editorial);
  }

  .agent-step-placeholder {
    margin: 0;
    color: oklch(92% 0.025 75 / 0.48);
    font-size: var(--text-caption);
    line-height: 1.6;
    padding: var(--space-12);
  }

  .agent-step-row strong,
  .agent-step-row p,
  .agent-step-row span {
    margin: 0;
    line-height: 1.45;
  }

  .agent-step-row strong {
    display: block;
    color: var(--color-text-inverse);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
  }

  .agent-step-row p,
  .agent-event-log span {
    color: oklch(92% 0.025 75 / 0.68);
    font-size: var(--text-caption);
  }

  .agent-step-row > span:last-child {
    border-radius: var(--radius-full);
    padding: var(--space-4) var(--space-8);
    background: oklch(92% 0.025 75 / 0.10);
    color: var(--color-text-inverse);
    font-size: var(--text-caption);
    white-space: nowrap;
  }

  .agent-event-log {
    overflow: hidden;
    animation: event-log-reveal var(--duration-reveal) var(--ease-editorial) both;
  }

  .agent-event-log p {
    display: grid;
    gap: var(--space-4);
    margin: 0;
    border-radius: var(--radius-sm);
    padding: var(--space-8) var(--space-12);
    background: oklch(92% 0.025 75 / 0.08);
  }

  .agent-event-log strong {
    color: var(--color-text-inverse);
    font-size: var(--text-caption);
    font-weight: var(--font-weight-medium);
  }

  .collapse-button,
  .submit-button {
    min-inline-size: 44px;
    min-block-size: 44px;
    border: none;
    border-radius: var(--radius-full);
    font-family: var(--font-body);
    font-size: var(--text-button);
    font-weight: var(--font-weight-medium);
    cursor: pointer;
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  .collapse-button {
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
  }

  .submit-button {
    background: var(--gradient-coral);
    color: var(--color-text-inverse);
    box-shadow: var(--shadow-sm);
  }

  .collapse-button:hover,
  .submit-button:hover {
    transform: translateY(calc(var(--space-4) * -1));
  }

  .chat-flow {
    flex: 1;
    min-block-size: 0;
    inline-size: 100%;
    padding: var(--space-8) var(--space-8) var(--space-96);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
  }

  .onboarding-step-bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: var(--space-12) var(--space-16);
    background: var(--color-surface);
    border-bottom: 1px solid var(--color-border);
    flex-shrink: 0;
    gap: var(--space-4);
  }

  .step-node {
    display: flex;
    align-items: center;
    gap: var(--space-8);
  }

  .step-number {
    width: 20px;
    height: 20px;
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--text-caption);
    font-family: var(--font-body);
    font-weight: var(--font-weight-medium);
    border: 1.5px solid var(--color-border);
    background: var(--color-surface-raised);
    color: var(--color-text-muted);
    transition: all 0.3s ease;
  }

  .step-node.active .step-number {
    background: var(--color-primary-soft);
    border-color: var(--color-primary);
    color: var(--color-primary);
    box-shadow: 0 0 6px var(--color-focus-ring);
  }

  .step-node.completed .step-number {
    background: var(--color-success);
    border-color: var(--color-success);
    color: var(--color-text-inverse);
  }

  .step-label {
    font-size: var(--text-caption);
    font-family: var(--font-body);
    color: var(--color-text-muted);
    white-space: nowrap;
    transition: all 0.3s ease;
  }

  .step-node.active .step-label {
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
  }

  .step-node.completed .step-label {
    color: var(--color-text-primary);
  }

  .step-connector {
    flex: 1;
    height: 1.5px;
    background: var(--color-border);
    transition: background 0.3s ease;
  }

  .step-connector.completed {
    background: var(--color-success);
  }

  @media (prefers-reduced-motion: reduce) {
    .step-number,
    .step-label,
    .step-connector {
      transition: none !important;
    }
  }

  .chat-empty-state {
    width: fit-content;
    max-inline-size: min(100%, var(--container-narrow));
    border-radius: var(--radius-md);
    padding: var(--space-16) var(--space-24);
    font-family: var(--font-body);
    line-height: 1.8;
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
  }

  .composer-container {
    position: absolute;
    bottom: var(--space-8);
    left: var(--space-8);
    right: var(--space-8);
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  .composer-completed-hint {
    font-size: var(--text-caption);
    color: var(--color-primary);
    background: var(--color-primary-soft);
    padding: var(--space-8) var(--space-12);
    border-radius: var(--radius-md);
    margin-inline-start: var(--space-12);
    margin-inline-end: var(--space-12);
    text-align: center;
    border: 1px solid oklch(90% 0.04 140 / 0.3);
    animation: fade-in-hint 0.5s var(--ease-editorial);
  }

  @keyframes fade-in-hint {
    from {
      opacity: 0;
      transform: translateY(4px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .image-preview-box {
    position: relative;
    inline-size: fit-content;
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    background: var(--color-surface);
    padding: var(--space-4);
    box-shadow: var(--shadow-sm);
    display: flex;
    align-items: center;
    margin-inline-start: var(--space-12);
  }

  .preview-thumbnail {
    max-block-size: 80px;
    max-inline-size: 120px;
    border-radius: var(--radius-sm);
    object-fit: contain;
  }

  .delete-preview-button {
    position: absolute;
    top: calc(var(--space-4) * -1);
    right: calc(var(--space-4) * -1);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    width: 20px;
    height: 20px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition: transform var(--duration-lazy-hover) var(--ease-lazy);
  }

  .delete-preview-button:hover {
    transform: scale(1.1);
    background: var(--color-error-bg);
    color: var(--color-error);
  }

  .chat-composer {
    display: flex;
    align-items: flex-end;
    gap: var(--space-8);
    border-radius: var(--radius-full);
    padding: var(--space-4);
    background: var(--glass-bg);
    backdrop-filter: var(--glass-blur);
    box-shadow: var(--shadow-sm), inset 0 1px 1px oklch(100% 0 0 / 0.4);
    flex-shrink: 0;
  }

  .chat-composer textarea {
    flex: 1;
    min-block-size: 0;
    max-block-size: var(--space-64);
    border: none;
    outline: none;
    resize: vertical;
    background: transparent;
    color: var(--color-text-primary);
    font-family: var(--font-body);
    font-size: var(--text-body);
    line-height: 1.6;
  }

  .pen-button {
    min-inline-size: 32px;
    min-block-size: 32px;
    display: flex;
    align-items: center;
    justify-content: center;
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    cursor: pointer;
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      background-color var(--duration-lazy-hover) var(--ease-lazy);
    align-self: flex-end;
    margin-bottom: var(--space-4);
  }

  .pen-button:hover {
    transform: translateY(calc(var(--space-2) * -1));
    background: var(--color-secondary-soft);
    color: var(--color-secondary);
  }

  .pen-button:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .chat-composer .submit-button {
    min-inline-size: var(--space-32);
    min-block-size: var(--space-32);
  }

  .chat-composer textarea:disabled,
  .submit-button:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  .composer-completed-cta-panel {
    display: flex;
    justify-content: center;
    align-items: center;
    border-radius: var(--radius-full);
    padding: var(--space-4);
    background: var(--glass-bg);
    backdrop-filter: var(--glass-blur);
    box-shadow: var(--shadow-sm), inset 0 1px 1px oklch(100% 0 0 / 0.4);
    flex-shrink: 0;
  }

  .composer-path-actions {
    display: flex;
    justify-content: center;
    gap: var(--space-8);
    padding-inline: var(--space-12);
  }

  .composer-path-actions button {
    flex: 1 1 0;
    min-block-size: var(--space-40);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    background: var(--color-surface-raised);
    color: var(--color-text-primary);
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      background-color var(--duration-lazy-hover) var(--ease-lazy);
  }

  .composer-path-actions button:hover {
    transform: translateY(calc(var(--space-2) * -1));
    background: var(--color-primary-soft);
  }

  .cta-completed-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-8);
    inline-size: 100%;
    min-block-size: var(--space-48);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    font-family: var(--font-body);
    font-size: var(--text-body);
    font-weight: var(--font-weight-medium);
    cursor: pointer;
    box-shadow: var(--shadow-sm);
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      background-color var(--duration-lazy-hover) var(--ease-lazy),
      box-shadow var(--duration-lazy-hover) var(--ease-lazy);
  }

  .cta-completed-btn:hover {
    background: var(--color-primary-hover);
    transform: translateY(calc(var(--space-2) * -1)) scale(1.01);
    box-shadow: var(--shadow-md);
  }

  .cta-completed-btn:active {
    transform: translateY(0) scale(0.995);
  }

  .cta-completed-btn .arrow {
    display: inline-block;
    transition: transform var(--duration-lazy-hover) var(--ease-lazy);
  }

  .cta-completed-btn:hover .arrow {
    transform: translateX(var(--space-4));
  }

  @media (prefers-reduced-motion: reduce) {
    .card,
    .collapse-button,
    .submit-button,
    .cta-completed-btn,
    .cta-completed-btn .arrow {
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }

    .agent-face-glow,
    .agent-step-dot,
    .agent-event-log,
    .agent-step-row,
    .global-error,
    .composer-completed-hint {
      animation: none;
    }

    .agent-step-row::before {
      transition: none;
    }
  }

  @media (max-width: 767px) {
    .session-header { align-items: flex-start; }

    .session-workbench {
      grid-template-columns: 1fr;
    }

    .codex-agent-panel {
      order: -1;
      max-block-size: 38vh;
    }

    .agent-step-row {
      grid-template-columns: auto minmax(0, 1fr);
    }

    .agent-step-row > span:last-child {
      grid-column: 2;
      inline-size: fit-content;
    }
  }

  @keyframes dot-scan {
    0% { box-shadow: -8px 0 0 0 oklch(92% 0.025 75 / 0); }
    40% { box-shadow: 0 0 8px 3px var(--color-primary); }
    100% { box-shadow: 8px 0 0 0 oklch(92% 0.025 75 / 0); }
  }

  @keyframes dot-pulse {
    0% { box-shadow: 0 0 0 0 oklch(98% 0.03 75 / 0.4); }
    70% { box-shadow: 0 0 0 10px oklch(98% 0.03 75 / 0); }
    100% { box-shadow: 0 0 0 0 oklch(98% 0.03 75 / 0); }
  }

  @keyframes dot-spin {
    0% { filter: hue-rotate(0deg); }
    100% { filter: hue-rotate(360deg); }
  }

  @keyframes dot-write {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.3; transform: scale(1.16); }
  }

  @keyframes dot-shake {
    0%, 100% { transform: translateX(0); }
    15% { transform: translateX(-5px); }
    30% { transform: translateX(5px); }
    45% { transform: translateX(-4px); }
    60% { transform: translateX(4px); }
    75% { transform: translateX(-2px); }
  }

  @keyframes event-log-reveal {
    from { transform: translateY(calc(var(--space-8) * -1)); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
`;
