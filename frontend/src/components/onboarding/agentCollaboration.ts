import type { AgentCollaborationNode, AgentRunStep } from '../../types/chat';

const AGENT_ORDER = [
  'supervisor',
  'profile_agent',
  'learning_path_intake_agent',
  'learning_path_agent',
  'course_knowledge_agent',
  'section_markdown_agent',
  'section_video_search_agent',
  'section_html_animation_agent',
] as const;

const WAITING_DEPENDENCY_LABELS: Record<string, string> = {
  profile_agent: '等待主智能体分配画像任务',
  learning_path_intake_agent: '等待画像完成',
  learning_path_agent: '等待课程草案确认',
  course_knowledge_agent: '等待学习路径完成',
  section_markdown_agent: '等待课程大纲完成',
  section_video_search_agent: '等待小节文档 brief 完成',
  section_html_animation_agent: '等待小节文档 brief 完成',
};

function normalizeAgent(step: AgentRunStep): string | null {
  const agent = step.agent?.trim();
  if (agent) return agent;
  if (step.kind === 'route') return 'supervisor';
  return null;
}

function statusPriority(status: AgentRunStep['status']) {
  if (status === 'error') return 4;
  if (status === 'running') return 3;
  if (status === 'success') return 2;
  return 1;
}

function pickNodeStatus(steps: AgentRunStep[]): AgentCollaborationNode['status'] {
  const ordered = [...steps].sort((a, b) => statusPriority(b.status) - statusPriority(a.status));
  return ordered[0]?.status ?? 'waiting';
}

function latestSummary(steps: AgentRunStep[], fallback: string): string {
  const latest = [...steps].reverse().find((step) => step.summary && step.summary.trim());
  return latest?.summary?.trim() ?? fallback;
}

export function buildAgentCollaborationNodes(steps: AgentRunStep[]): AgentCollaborationNode[] {
  const byAgent = new Map<string, AgentRunStep[]>();

  for (const step of steps) {
    const agent = normalizeAgent(step);
    if (!agent) continue;
    const existing = byAgent.get(agent) ?? [];
    byAgent.set(agent, [...existing, step]);
  }

  const activeAgents = [...byAgent.keys()];
  const orderedAgents = [
    ...AGENT_ORDER.filter((agent) => byAgent.has(agent)),
    ...activeAgents.filter((agent) => !AGENT_ORDER.includes(agent as (typeof AGENT_ORDER)[number])).sort(),
  ];

  return orderedAgents.map((agent) => {
    const agentSteps = byAgent.get(agent) ?? [];
    const latestStep = agentSteps[agentSteps.length - 1];
    const status = pickNodeStatus(agentSteps);
    const dependsOn = [...new Set(agentSteps.flatMap((step) => step.dependsOn ?? []))];
    const parallelGroup = [...agentSteps].reverse().find((step) => step.parallelGroup)?.parallelGroup ?? null;
    const durationMs = agentSteps.reduce((total, step) => total + (step.durationMs ?? 0), 0);
    const label = latestStep?.title ?? agent;
    const inputSummary = dependsOn.length > 0
      ? `输入来自：${dependsOn.join('、')}`
      : WAITING_DEPENDENCY_LABELS[agent] ?? '等待任务输入';
    const outputSummary = latestSummary(
      agentSteps,
      status === 'running' ? '正在生成输出摘要' : '本轮暂无输出摘要',
    );

    return {
      agent,
      label,
      status,
      latestStepId: latestStep?.stepId ?? agent,
      inputSummary,
      outputSummary,
      dependsOn,
      parallelGroup,
      durationMs: durationMs > 0 ? durationMs : undefined,
      stepCount: agentSteps.length,
    };
  });
}
