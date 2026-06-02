import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import styled from 'styled-components';
import { streamSession, type SessionAgentEvent } from '../../api/orchestration';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';
import type { AgentRunStep, ChatMessage, SessionMessage } from '../../types/chat';
import { chatReducer, initialChatStore, nextMessageId } from '../../onboarding/chatReducer';
import { useChatSession } from '../../onboarding/hooks/useChatSession';
import { LearningPathCard } from '../learning/LearningPathCard';
import { AiEyes } from './AiEyes';
import { AgentRunTimeline } from './AgentRunTimeline';
import { ChatCard } from './ChatCard';
import { MessageBubble } from './MessageBubble';
import { AssistantMessage } from './AssistantMessage';
import { SystemMessage } from './AssistantMessage';

const AGENT_LABELS: Record<string, string> = {
  main_agent: '主智能体',
  intent_recognition_agent: '意图识别智能体',
  profile_agent: '基础画像智能体',
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

function statusLabel(status: 'pending' | 'running' | 'completed' | 'routed' | 'error'): string {
  const map: Record<string, string> = { running: '运行中', completed: '已完成', routed: '已转交', error: '异常', pending: '等待中' };
  return map[status] || '待命';
}

function updateStep(steps: AgentStepStatus[], id: string, status: AgentStepStatus['status'], detail: string): AgentStepStatus[] {
  return steps.map((step) => (step.id === id ? { ...step, status, detail } : step));
}

function getSessionEventAgent(event: SessionAgentEvent): string | undefined {
  return event.agentKey ?? event.agent;
}

function getSessionEventStepId(event: SessionAgentEvent): string {
  return event.stepId ?? getSessionEventAgent(event) ?? event.sessionId ?? event.event;
}

function getSessionEventTitle(event: SessionAgentEvent): string {
  const agent = getSessionEventAgent(event);
  return event.label ?? (agent ? AGENT_LABELS[agent] ?? agent : event.event);
}

function getSessionEventDetail(event: SessionAgentEvent): string {
  return event.error ?? event.message ?? event.phase ?? '等待下一步结果';
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
  if (event.event === 'agent_step_started') {
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

  if (event.event === 'agent_step_completed') {
    return upsertPanelStep(current, {
      id: getSessionEventStepId(event),
      title: getSessionEventTitle(event),
      status: 'completed',
      detail: getSessionEventDetail(event),
      agentType: 'write',
    });
  }

  if (event.event === 'agent_step_failed' || event.event === 'orchestration_failed') {
    return upsertPanelStep(current, {
      id: getSessionEventStepId(event),
      title: getSessionEventTitle(event),
      status: 'error',
      detail: getSessionEventDetail(event),
      agentType: 'write',
    });
  }

  if (event.event === 'orchestration_completed') {
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
  const completedCount = steps.filter((step) => step.status === 'completed').length;
  if (completedCount > 0) return '本轮智能体调用已完成';
  return '等待你输入学习线索';
}

export function AiGreetingInput() {
  const { widgetState, setWidgetState } = useAiWidget();
  const { token } = useAuth();
  const cardRef = useRef<HTMLDivElement>(null);
  const [store, dispatch] = useReducer(chatReducer, initialChatStore);
  const [inputValue, setInputValue] = useState('');
  const [agentSteps, setAgentSteps] = useState<AgentStepStatus[]>(DEFAULT_AGENT_STEPS);
  const [agentEvents, setAgentEvents] = useState<SessionAgentEvent[]>([]);
  const [showEventLog, setShowEventLog] = useState(false);
  const [globalError, setGlobalError] = useState<string | null>(null);

  const runIdRef = useRef(0);
  const startTimeRef = useRef<Record<string, number>>({});
  const executionIdRef = useRef<string | null>(null);
  const isCompletedRef = useRef(false);

  const isPending = store.state === 'connecting' || store.state === 'streaming';
  const aiMood = store.state === 'error' ? 'error' : isPending ? 'thinking' : store.messages.some((m) => m.role === 'assistant' && m.status === 'completed') ? 'happy' : 'idle';

  const { persistSession } = useChatSession(store.currentSessionId, (messages, sessionId) => {
    dispatch({ type: 'LOAD_SESSION', messages, sessionId });
    executionIdRef.current = sessionId;
    isCompletedRef.current = messages.some(
      (m) => m.role === 'assistant' && m.sessionMessage?.stage === 'generated',
    );
    window.dispatchEvent(new CustomEvent('mutiagent-profile-updated'));
  });

  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const mouseXSpring = useSpring(x, { stiffness: 150, damping: 20 });
  const mouseYSpring = useSpring(y, { stiffness: 150, damping: 20 });
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ['15deg', '-15deg']);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ['-15deg', '15deg']);

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

    if (event.event === 'agent_step_started') {
      const stepId = getSessionEventStepId(event);
      startTimeRef.current[stepId] = now;
      return {
        step: {
          stepId,
          kind: 'agent',
          status: 'running',
          title: label,
          summary: getTimelineSummary(event, event.message ?? '正在执行...'),
          agent: agent ?? null,
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'agent_step_completed') {
      const stepId = getSessionEventStepId(event);
      const startTime = startTimeRef.current[stepId] ?? now;
      return {
        step: {
          stepId,
          kind: 'agent',
          status: 'success',
          title: label,
          summary: getTimelineSummary(event, event.message ?? '完成'),
          agent: agent ?? null,
          durationMs: now - startTime,
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'agent_step_failed' || event.event === 'orchestration_failed') {
      const stepId = getSessionEventStepId(event);
      return {
        step: {
          stepId,
          kind: 'agent',
          status: 'error',
          title: label,
          summary: getTimelineSummary(event, event.error ?? event.message ?? '这一步没有正常完成'),
          agent: agent ?? null,
          durationMs: 0,
          dependsOn: event.dependsOn,
          parallelGroup: event.parallelGroup,
        },
      };
    }

    if (event.event === 'orchestration_completed') {
      return {
        step: {
          stepId: `step-answer-${event.sessionId ?? now}`,
          kind: 'answer',
          status: 'success',
          title: '生成回复',
          summary: event.message ?? '本轮内容已生成',
          agent: agent ?? null,
          durationMs: 0,
        },
      };
    }

    return { step: null };
  }, []);

  const sendMessage = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || isPending) return;
      if (!token) {
        setGlobalError('请先登录后再开始基础画像对话。');
        return;
      }

      const userMsgId = nextMessageId();
      dispatch({ type: 'ADD_USER_MESSAGE', id: userMsgId, content: query });

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

      try {
        let finalSessionId: string | undefined;

        await streamSession(
          token,
          query,
          executionIdRef.current && !isCompletedRef.current ? executionIdRef.current : null,
          (event) => {
            if (runIdRef.current !== runId) return;
            setAgentSteps((current) => mergeSessionAgentStep(current, event));
            setAgentEvents((current) => [...current, event]);

            const now = Date.now();

            if (
              event.event === 'agent_step_started'
              || event.event === 'agent_step_completed'
              || event.event === 'agent_step_failed'
              || event.event === 'orchestration_completed'
              || event.event === 'orchestration_failed'
            ) {
              if (event.event === 'agent_step_started') {
                dispatch({ type: 'STREAMING_STARTED' });
              }
              const { step } = eventToStep(event, now);
              if (step) {
                dispatch({ type: 'STEP', step });
              }
            }

            if (event.event === 'orchestration_completed') {
              const text = event.answer?.userMessage ?? '';
              executionIdRef.current = event.sessionId ?? null;
              isCompletedRef.current = event.completed ?? false;
              finalSessionId = event.sessionId ?? undefined;

              if (event.error) {
                dispatch({ type: 'RUN_ERROR', message: event.error });
                setGlobalError(event.error);
                return;
              }

              dispatch({
                type: 'RUN_DONE',
                content: text,
                sessionMessage: event.profile,
                agentAnswer: event.answer ?? null,
                learningPath: event.learningPath ?? null,
                sessionId: event.sessionId ?? undefined,
              });
            }

            if (event.event === 'agent_step_failed' || event.event === 'orchestration_failed') {
              const message = event.error ?? event.message ?? '对话请求失败，请稍后重试';
              dispatch({ type: 'RUN_ERROR', message });
              setGlobalError(message);
            }
          },
        );

        if (runIdRef.current !== runId) return;

        if (finalSessionId) {
          executionIdRef.current = finalSessionId;
        }

        if (isCompletedRef.current) {
          window.dispatchEvent(new CustomEvent('mutiagent-profile-updated'));
        }
      } catch (err) {
        if (runIdRef.current !== runId) return;
        const message = err instanceof Error ? err.message : '对话请求失败，请稍后重试';
        dispatch({ type: 'RUN_ERROR', message });
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
    [isPending, token, eventToStep],
  );

  useEffect(() => {
    if (store.state === 'idle' && store.currentSessionId && store.messages.length > 0) {
      persistSession(store.currentSessionId, store.messages);
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
    void sendMessage(inputValue);
  };

  function renderMessage(message: ChatMessage) {
    if (message.role === 'user') {
      return <MessageBubble key={message.id} content={message.content} />;
    }

    if (message.role === 'system') {
      return <SystemMessage key={message.id} message={message} />;
    }

    if (message.role === 'assistant') {
      if (message.learningPath) {
        return <LearningPathCard key={message.id} path={message.learningPath} />;
      }

      if (message.sessionMessage && isStructuredMessage(message.sessionMessage)) {
        return (
          <ChatCard
            key={message.id}
            message={message.sessionMessage}
            onSendReply={sendMessage}
            disabled={isPending}
          />
        );
      }

      return (
        <AssistantMessage
          key={message.id}
          message={message}
          onSendReply={sendMessage}
          disabled={isPending}
        />
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
          expanded: { width: '85vw', height: '85vh' },
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
          <section className="session-panel" aria-label="AI 基础画像对话">
            <header className="session-header">
              <div className="session-title-cluster">
                <div className="agent-face" data-ai-state={aiMood}>
                  <span className="agent-face-glow" aria-hidden="true" />
                  <AiEyes layoutId="eyes" isHappy={aiMood === 'happy'} />
                </div>
                <div className="session-title-copy">
                  <span>基础画像对话</span>
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
                <span aria-hidden="true">//</span>
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
                <div className="chat-flow">
                  {store.messages.length === 0 && (
                    <div className="chat-empty-state">
                      告诉我你的年级、专业、学习偏好或近期目标，我会先判断意图，再进入基础画像对话。
                    </div>
                  )}

                  {store.messages.map(renderMessage)}
                </div>

                <form
                  className="chat-composer"
                  onSubmit={(event) => {
                    event.preventDefault();
                    handleSubmit();
                  }}
                >
                  <textarea
                    rows={1}
                    placeholder={isCompletedRef.current ? '画像已生成，可以继续补充或追问...' : '输入你的学习情况...'}
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
                    type="submit"
                    className="submit-button"
                    disabled={isPending || !inputValue.trim()}
                    aria-label="发送消息"
                  >
                    <span aria-hidden="true">+</span>
                  </button>
                </form>
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
                          <span>{event.message || event.intent || event.phase || event.event}</span>
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

  .chat-composer {
    position: absolute;
    bottom: var(--space-8);
    left: var(--space-8);
    right: var(--space-8);
    z-index: 10;
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

  .chat-composer .submit-button {
    min-inline-size: var(--space-32);
    min-block-size: var(--space-32);
  }

  .chat-composer textarea:disabled,
  .submit-button:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  @media (prefers-reduced-motion: reduce) {
    .card,
    .collapse-button,
    .submit-button {
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }

    .agent-face-glow,
    .agent-step-dot,
    .agent-event-log,
    .agent-step-row,
    .global-error {
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
