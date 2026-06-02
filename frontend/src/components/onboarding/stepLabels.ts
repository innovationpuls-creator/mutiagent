import type { AgentRunStep } from '../../types/chat';

const STEP_LABELS: Record<AgentRunStep['kind'], string> = {
  agent: '智能体',
  route: '调度',
  answer: '回复',
};

export function formatStepKind(step: AgentRunStep): string {
  return STEP_LABELS[step.kind] || step.kind;
}

export function formatStepTitle(step: AgentRunStep): string {
  return step.title || step.kind;
}

export function formatRunSummary(params: {
  agent: string;
  runStatus: 'running' | 'completed' | 'failed';
  stepCount: number;
  duration: string;
}): string {
  const { agent, runStatus, stepCount, duration } = params;
  const symbol = runStatus === 'running' ? '●' : runStatus === 'failed' ? '×' : '✓';
  const statusLabel = runStatus === 'running' ? '运行中' : runStatus === 'failed' ? '异常' : '已完成';
  const stepsLabel = `${stepCount} 个步骤`;
  const durationPart = duration ? ` · ${duration}` : '';
  return `${symbol} ${agent} ${statusLabel} · ${stepsLabel}${durationPart}`;
}
