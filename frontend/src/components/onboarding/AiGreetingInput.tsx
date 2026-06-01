import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import styled from 'styled-components';
import { streamChatflow, type AgentEventName, type ChatflowAgentEvent } from '../../api/orchestration';
import { useAiWidget } from '../../context/AiWidgetContext';
import { useAuth } from '../../contexts/AuthContext';
import type { SessionMessage } from '../../types/chat';
import { AiEyes } from './AiEyes';
import { ChatCard } from './ChatCard';

type AgentStepStatus = 'pending' | 'running' | 'completed' | 'routed' | 'error';

interface AgentStep {
  id: string;
  title: string;
  status: AgentStepStatus;
  detail: string;
}

const DEFAULT_AGENT_STEPS: AgentStep[] = [
  {
    id: 'context',
    title: '读取上下文',
    status: 'pending',
    detail: '等待接收你的学习线索',
  },
  {
    id: 'intent',
    title: '意图识别智能体',
    status: 'pending',
    detail: '判断该由哪个智能体处理',
  },
  {
    id: 'route',
    title: '路由决策',
    status: 'pending',
    detail: '等待意图识别结果',
  },
  {
    id: 'profile',
    title: '基础画像智能体',
    status: 'pending',
    detail: '等待路由转交',
  },
  {
    id: 'update',
    title: '更新画像 / 生成问题',
    status: 'pending',
    detail: '等待智能体返回内容',
  },
];

function statusLabel(status: AgentStepStatus): string {
  if (status === 'running') return '运行中';
  if (status === 'completed') return '已完成';
  if (status === 'routed') return '已转交';
  if (status === 'error') return '异常';
  if (status === 'pending') return '等待中';
  return '待命';
}

function updateStep(
  steps: AgentStep[],
  id: string,
  status: AgentStepStatus,
  detail: string,
): AgentStep[] {
  return steps.map((step) => (step.id === id ? { ...step, status, detail } : step));
}

function mergeAgentStep(current: AgentStep[], event: ChatflowAgentEvent): AgentStep[] {
  if (event.event === 'agent_started' && event.agent === 'intent_recognition_agent') {
    return updateStep(
      updateStep(current, 'context', 'completed', '已读取本轮输入与历史对话'),
      'intent',
      'running',
      event.message || '正在判断这次对话应该交给哪个智能体',
    );
  }
  if (event.event === 'agent_completed' && event.agent === 'intent_recognition_agent') {
    return updateStep(current, 'intent', 'completed', '意图识别完成');
  }
  if (event.event === 'route_decided') {
    return updateStep(current, 'route', 'routed', event.message || `转交给${event.label || '具体智能体'}`);
  }
  if (event.event === 'agent_started' && event.agent === 'profile_agent') {
    return updateStep(current, 'profile', 'running', event.message || '正在整理基础画像信息');
  }
  if (event.event === 'agent_completed' && event.agent === 'profile_agent') {
    return updateStep(
      updateStep(current, 'profile', 'completed', '基础画像智能体已返回结果'),
      'update',
      'running',
      '正在生成问题或更新画像卡片',
    );
  }
  if (event.event === 'completed') {
    return updateStep(current, 'update', 'completed', '本轮内容已生成');
  }
  if (event.event === 'error') {
    return current.map((step) =>
      step.status === 'running' || step.status === 'routed'
        ? { ...step, status: 'error', detail: event.message || '这一步没有正常完成' }
        : step,
    );
  }
  return current;
}

function currentProgressLabel(steps: AgentStep[]): string {
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
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [executionId, setExecutionId] = useState<string | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [isPending, setIsPending] = useState(false);
  const [isCompleted, setIsCompleted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agentSteps, setAgentSteps] = useState<AgentStep[]>(DEFAULT_AGENT_STEPS);
  const [agentEvents, setAgentEvents] = useState<ChatflowAgentEvent[]>([]);
  const [showEventLog, setShowEventLog] = useState(false);
  const aiMood = error ? 'error' : isPending ? 'thinking' : isCompleted ? 'happy' : 'idle';

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

    const handleGlobalMouseLeave = () => {
      x.set(0);
      y.set(0);
    };

    window.addEventListener('mousemove', handleGlobalMouseMove);
    document.addEventListener('mouseleave', handleGlobalMouseLeave);

    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      document.removeEventListener('mouseleave', handleGlobalMouseLeave);
    };
  }, [widgetState, x, y]);

  const sendMessage = useCallback(
    async (text: string) => {
      const query = text.trim();
      if (!query || isPending) return;
      if (!token) {
        setError('请先登录后再开始基础画像对话。');
        return;
      }

      setIsPending(true);
      setError(null);
      setAgentSteps(DEFAULT_AGENT_STEPS);
      setAgentEvents([]);
      setShowEventLog(false);

      try {
        const turn = await streamChatflow(
          token,
          query,
          executionId && !isCompleted ? executionId : null,
          (event) => {
            setAgentSteps((current) => mergeAgentStep(current, event));
            setAgentEvents((current) => [...current, event]);
          },
        );

        setExecutionId(turn.completed ? null : turn.executionId);
        setMessages((current) => [...current, turn.answer]);
        setIsCompleted(turn.completed);
        setInputValue('');
        if (turn.completed) {
          window.dispatchEvent(new CustomEvent('mutiagent-profile-updated'));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : '对话请求失败，请稍后重试');
        setAgentSteps((current) =>
          current.map((step) =>
            step.status === 'running' || step.status === 'routed'
              ? { ...step, status: 'error', detail: '这一步没有正常完成' }
              : step,
          ),
        );
      } finally {
        setIsPending(false);
      }
    },
    [executionId, isCompleted, isPending, token],
  );

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

            <div className="session-workbench">
              <main className="chat-column" aria-label="对话内容">
                <div className="chat-flow">
                  {messages.length === 0 && (
                    <div className="chat-empty-state">
                      告诉我你的年级、专业、学习偏好或近期目标，我会先判断意图，再进入基础画像对话。
                    </div>
                  )}
                  {messages.map((message, index) => (
                    <ChatCard
                      key={`${message.stage}-${index}`}
                      message={message}
                      onSendReply={sendMessage}
                      disabled={isPending}
                    />
                  ))}
                  {isPending && <div className="chat-status">正在思考下一步问题...</div>}
                  {error && <div className="chat-error">{error}</div>}
                </div>
              </main>

              <aside className="codex-agent-panel" aria-label="多智能体调用状态">
                <section className="agent-panel-section agent-panel-progress">
                  <button
                    type="button"
                    className="agent-panel-heading"
                    onClick={() => setShowEventLog((value) => !value)}
                    aria-expanded={showEventLog}
                  >
                    <span>进度</span>
                    <span aria-hidden="true">›</span>
                  </button>
                  <p>{currentProgressLabel(agentSteps)}</p>
                </section>

                <section className="agent-panel-section">
                  <div className="agent-panel-heading static">
                    <span>步骤</span>
                    <strong>{isPending ? '运行中' : '待命'}</strong>
                  </div>
                  <div className="agent-step-list">
                    {agentSteps.map((step) => (
                      <div className="agent-step-row" data-status={step.status} key={step.id}>
                        <span className="agent-step-dot" aria-hidden="true" />
                        <div>
                          <strong>{step.title}</strong>
                          <p>{step.detail}</p>
                        </div>
                        <span>{statusLabel(step.status)}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="agent-panel-section">
                  <button
                    type="button"
                    className="agent-panel-heading"
                    onClick={() => setShowEventLog((value) => !value)}
                    aria-expanded={showEventLog}
                  >
                    <span>完整调用记录</span>
                    <span aria-hidden="true">{showEventLog ? '⌃' : '⌄'}</span>
                  </button>
                  {showEventLog && (
                    <div className="agent-event-log">
                      {agentEvents.length === 0 ? (
                        <p>本轮还没有实时事件。</p>
                      ) : (
                        agentEvents.map((event, index) => (
                          <p key={`${event.event}-${index}`}>
                            <strong>{event.label || event.agent || event.event}</strong>
                            <span>{event.message || event.intent || event.phase || event.event}</span>
                          </p>
                        ))
                      )}
                    </div>
                  )}
                </section>
              </aside>
            </div>

            <form
              className="chat-composer"
              onSubmit={(event) => {
                event.preventDefault();
                handleSubmit();
              }}
            >
              <textarea
                placeholder={isCompleted ? '画像已生成，可以继续补充或追问...' : '输入你的学习情况...'}
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

  .widget-shell .eyes.happy {
    display: none;
  }

  .card:hover .widget-shell .eyes:not(.happy) {
    display: none;
  }

  .card:hover .widget-shell .eyes.happy {
    display: flex;
  }

  .session-panel {
    inline-size: 100%;
    block-size: 100%;
    display: flex;
    flex-direction: column;
    padding: var(--space-24);
    gap: var(--gap-sm);
    background:
      radial-gradient(circle at 12% 0%, oklch(84% 0.12 63 / 0.16), transparent 32%),
      var(--color-surface-raised);
  }

  .session-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gap-sm);
    min-block-size: var(--space-64);
    border-block-end: 1px solid var(--color-border);
    padding-block-end: var(--space-12);
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
    inline-size: var(--space-64);
    min-inline-size: var(--space-64);
    block-size: var(--space-64);
    border-radius: var(--radius-md);
    background: var(--glass-bg);
    border: 1px solid var(--glass-border);
    box-shadow: var(--shadow-sm);
    overflow: hidden;
  }

  .agent-face-glow {
    position: absolute;
    inset: calc(var(--space-16) * -1);
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

  .session-workbench {
    position: relative;
    flex: 1;
    min-block-size: 0;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
    gap: var(--gap-md);
    align-items: stretch;
  }

  .chat-column {
    min-inline-size: 0;
    min-block-size: 0;
    display: flex;
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

  .agent-panel-section:first-child {
    padding-block-start: 0;
  }

  .agent-panel-section:last-child {
    border-block-end: none;
    padding-block-end: 0;
  }

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

  .agent-panel-heading.static {
    cursor: default;
  }

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
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: var(--space-12);
    border-radius: var(--radius-md);
    padding: var(--space-12);
    background: oklch(92% 0.025 75 / 0.08);
    animation: step-reveal var(--duration-reveal) var(--ease-editorial) both;
  }

  .agent-step-row[data-status='running'],
  .agent-step-row[data-status='routed'] {
    background: oklch(80% 0.13 55 / 0.22);
  }

  .agent-step-row[data-status='completed'] {
    background: oklch(82% 0.10 135 / 0.16);
  }

  .agent-step-row[data-status='error'] {
    background: oklch(80% 0.14 28 / 0.18);
  }

  .agent-step-dot {
    inline-size: var(--space-12);
    block-size: var(--space-12);
    border-radius: var(--radius-full);
    background: oklch(92% 0.025 75 / 0.28);
  }

  .agent-step-row[data-status='running'] .agent-step-dot,
  .agent-step-row[data-status='routed'] .agent-step-dot {
    background: var(--color-primary);
    box-shadow: var(--shadow-glow);
    animation: agent-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  }

  .agent-step-row[data-status='completed'] .agent-step-dot {
    background: var(--color-success);
  }

  .agent-step-row[data-status='error'] .agent-step-dot {
    background: var(--color-error);
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
    padding: var(--space-8) var(--space-8) var(--space-24);
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
  }

  .chat-empty-state,
  .chat-status,
  .chat-error {
    width: fit-content;
    max-inline-size: min(100%, var(--container-narrow));
    border-radius: var(--radius-md);
    padding: var(--space-16) var(--space-24);
    font-family: var(--font-body);
    line-height: 1.8;
  }

  .chat-empty-state,
  .chat-status {
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
  }

  .chat-error {
    background: var(--color-error-bg);
    color: var(--color-text-primary);
  }

  .chat-composer {
    display: flex;
    align-items: flex-end;
    gap: var(--gap-sm);
    min-block-size: var(--space-64);
    border-radius: var(--radius-full);
    padding: var(--space-12);
    background: var(--color-surface-inset);
    box-shadow: var(--shadow-inset);
  }

  .chat-composer textarea {
    flex: 1;
    min-block-size: var(--space-40);
    max-block-size: var(--space-120);
    border: none;
    outline: none;
    resize: vertical;
    background: transparent;
    color: var(--color-text-primary);
    font-family: var(--font-body);
    font-size: var(--text-body);
    line-height: 1.6;
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
    .agent-step-row {
      animation: none;
    }
  }

  @media (max-width: 767px) {
    .session-header {
      align-items: flex-start;
    }

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

  @keyframes agent-breathe {
    from { transform: scale(0.94); opacity: 0.42; }
    to { transform: scale(1.04); opacity: 0.72; }
  }

  @keyframes step-reveal {
    from { transform: translateY(var(--space-8)); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  @keyframes event-log-reveal {
    from { transform: translateY(calc(var(--space-8) * -1)); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }
`;
