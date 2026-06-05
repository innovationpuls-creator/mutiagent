import type { AgentRunStep } from '../../types/chat';

const STEP_LABELS: Record<AgentRunStep['kind'], string> = {
  agent: 'agent',
  route: '调度',
  answer: 'answer',
  data: '数据',
  system: '系统',
  thought: '思考',
  tool_call: '工具调用',
};

const STEP_STAGE_LABELS: Record<AgentRunStep['kind'], string> = {
  agent: '智能体执行',
  route: '路由判定',
  answer: '回复生成',
  data: '数据回填',
  system: '上下文装载',
  thought: '主控思考',
  tool_call: '工具调度',
};

export function formatStepKind(step: AgentRunStep): string {
  return STEP_LABELS[step.kind] || step.kind;
}

export function formatStepStageLabel(step: AgentRunStep): string {
  return STEP_STAGE_LABELS[step.kind] || step.kind;
}

export function formatStepTitle(step: AgentRunStep): string {
  return step.title || step.kind;
}

export function formatRunSummary(params: {
  label: string;
  runStatus: 'running' | 'completed' | 'failed';
  stepCount: number;
  duration: string;
}): string {
  const { label, runStatus, stepCount, duration } = params;
  const symbol = runStatus === 'running' ? '●' : runStatus === 'failed' ? '×' : '✓';
  const statusLabel = runStatus === 'running' ? '运行中' : runStatus === 'failed' ? '异常' : '已完成';
  const stepsLabel = `${stepCount} 个步骤`;
  const durationPart = duration ? ` · ${duration}` : '';
  return `${symbol} ${label} ${statusLabel} · ${stepsLabel}${durationPart}`;
}
