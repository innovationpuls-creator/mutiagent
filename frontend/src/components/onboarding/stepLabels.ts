import type { AgentRunStep } from '../../types/chat';

const STEP_LABELS: Record<AgentRunStep['kind'], string> = {
  agent: 'agent',
  route: 'route',
  answer: 'answer',
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
  const symbol = runStatus === 'running' ? '●' : runStatus === 'failed' ? '✗' : '✓';
  const stepsLabel = `${stepCount} step${stepCount !== 1 ? 's' : ''}`;
  const durationPart = duration ? ` · ${duration}` : '';
  return `${symbol} ${agent} ${runStatus === 'running' ? 'running' : runStatus === 'failed' ? 'failed' : 'completed'} · ${stepsLabel}${durationPart}`;
}
