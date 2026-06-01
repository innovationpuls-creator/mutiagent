import type { AgentTraceStep, AgentUserAnswer, LearningPathResult, QuestionBox, SessionMessage } from '../types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface ApiErrorResponse {
  detail?: string | { msg?: string }[];
}

interface ApiAgentUserAnswer {
  user_message: string;
  question_box: QuestionBox | null;
}

interface ApiAgentTraceStep {
  step_id: string;
  agent_key: string;
  label: string;
  phase: string;
  status: string;
  message: string;
  depends_on?: string[];
  parallel_group?: string | null;
}

interface SessionResponse {
  session_id: string;
  answer: ApiAgentUserAnswer;
  agent_trace: ApiAgentTraceStep[];
  completed: boolean;
  profile: SessionMessage | null;
  learning_path: LearningPathResult | null;
}

interface UnknownRecord {
  [key: string]: unknown;
}

export interface SessionTurn {
  sessionId: string;
  answer: AgentUserAnswer;
  agentTrace: AgentTraceStep[];
  completed: boolean;
  profile: SessionMessage | null;
  learningPath: LearningPathResult | null;
}

export type SessionEventName =
  | 'agent_step_started'
  | 'agent_step_completed'
  | 'agent_step_failed'
  | 'orchestration_completed'
  | 'orchestration_failed';

export interface SessionAgentEvent {
  event: SessionEventName;
  stepId?: string;
  agentKey?: string;
  agent?: string;
  label?: string;
  phase?: string;
  status?: string;
  message?: string;
  error?: string;
  intent?: string;
  routeStatus?: string;
  sessionId?: string;
  answer?: AgentUserAnswer;
  agentTrace?: AgentTraceStep[];
  completed?: boolean;
  profile?: SessionMessage | null;
  learningPath?: LearningPathResult | null;
}

export interface ChatflowTurn {
  executionId: string;
  conversationId: string;
  answer: SessionMessage;
  completed: boolean;
  finalResult: SessionMessage | null;
}

export type AgentEventName =
  | 'agent_started'
  | 'agent_completed'
  | 'route_decided'
  | 'completed'
  | 'error';

export interface ChatflowAgentEvent {
  event: AgentEventName;
  agent?: string;
  label?: string;
  message?: string;
  intent?: string;
  route_status?: string;
  execution_id?: string;
  conversation_id?: string;
  answer?: SessionMessage;
  completed?: boolean;
  final_result?: SessionMessage | null;
  phase?: string;
  error?: string;
}

function getErrorMessage(error: ApiErrorResponse | null): string {
  if (!error?.detail) return '对话请求失败，请稍后重试';
  if (typeof error.detail === 'string') return error.detail;
  return '输入内容不完整，请检查后重试';
}

async function requestOrchestration<TResponse>(
  path: string,
  token: string,
  body: object,
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as ApiErrorResponse | null;
    throw new Error(getErrorMessage(error));
  }

  return (await response.json()) as TResponse;
}

function normalizeAnswer(answer: ApiAgentUserAnswer): AgentUserAnswer {
  return {
    userMessage: answer.user_message,
    questionBox: answer.question_box,
  };
}

function normalizeTraceStep(step: ApiAgentTraceStep): AgentTraceStep {
  return {
    stepId: step.step_id,
    agentKey: step.agent_key,
    label: step.label,
    phase: step.phase,
    status: step.status,
    message: step.message,
    dependsOn: step.depends_on ?? [],
    parallelGroup: step.parallel_group ?? null,
  };
}

function normalizeSessionResponse(payload: SessionResponse): SessionTurn {
  return {
    sessionId: payload.session_id,
    answer: normalizeAnswer(payload.answer),
    agentTrace: payload.agent_trace.map(normalizeTraceStep),
    completed: payload.completed,
    profile: payload.profile,
    learningPath: payload.learning_path,
  };
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return value !== null && typeof value === 'object';
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function getBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function getProfile(value: unknown): SessionMessage | null | undefined {
  if (value === null) return null;
  return isUnknownRecord(value) ? (value as unknown as SessionMessage) : undefined;
}

function getLearningPath(value: unknown): LearningPathResult | null | undefined {
  if (value === null) return null;
  return isUnknownRecord(value) ? (value as unknown as LearningPathResult) : undefined;
}

function getAnswer(value: unknown): AgentUserAnswer | undefined {
  if (!isUnknownRecord(value)) return undefined;
  const userMessage = getString(value.user_message);
  if (userMessage === undefined) return undefined;
  return {
    userMessage,
    questionBox: value.question_box === null || isUnknownRecord(value.question_box)
      ? (value.question_box as QuestionBox | null)
      : null,
  };
}

function getTrace(value: unknown): AgentTraceStep[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.map((step) => normalizeTraceStep(step as ApiAgentTraceStep));
}

function normalizeSessionEvent(event: SessionEventName, payload: UnknownRecord): SessionAgentEvent {
  const answer = getAnswer(payload.answer);
  const agentTrace = getTrace(payload.agent_trace);
  return {
    event,
    stepId: getString(payload.step_id),
    agentKey: getString(payload.agent_key),
    agent: getString(payload.agent),
    label: getString(payload.label),
    phase: getString(payload.phase),
    status: getString(payload.status),
    message: getString(payload.message),
    error: getString(payload.error),
    intent: getString(payload.intent),
    routeStatus: getString(payload.route_status),
    sessionId: getString(payload.session_id),
    answer,
    agentTrace,
    completed: getBoolean(payload.completed),
    profile: getProfile(payload.profile),
    learningPath: getLearningPath(payload.learning_path),
  };
}

function parseSseChunk(buffer: string): { events: SessionAgentEvent[]; rest: string } {
  const parts = buffer.split('\n\n');
  const rest = parts.pop() ?? '';
  const events = parts
    .map((part) => {
      const lines = part.split('\n');
      const eventLine = lines.find((line) => line.startsWith('event: '));
      const dataLines = lines.filter((line) => line.startsWith('data: '));
      if (!eventLine || dataLines.length === 0) return null;

      const event = eventLine.slice('event: '.length).trim() as SessionEventName;
      const data = dataLines.map((line) => line.slice('data: '.length)).join('\n');
      const payload = JSON.parse(data) as UnknownRecord;
      return normalizeSessionEvent(event, payload);
    })
    .filter((event): event is SessionAgentEvent => event !== null);

  return { events, rest };
}

function sessionMessageFromAnswer(answer: AgentUserAnswer): SessionMessage {
  return {
    type: 'collecting',
    stage: 'basic_info',
    question_mode: answer.questionBox ? 'question_box' : 'none',
    confirmed_info: {
      current_grade: '',
      major: '',
      learning_stage: '',
      has_clear_goal: '',
      learning_method_preference: '',
      learning_pace_preference: '',
      content_preference: [],
      need_guidance: '',
      knowledge_foundation: '',
      strengths: '',
      weaknesses: '',
      experience: '',
      short_term_goal: '',
      long_term_goal: '',
      weekly_available_time: '',
      constraints: '',
    },
    defaulted_fields: [],
    question_md: answer.userMessage,
    question_box: answer.questionBox ?? { question: '', options: [] },
    text: answer.userMessage,
  };
}

function toChatflowEvent(event: SessionAgentEvent): ChatflowAgentEvent {
  const agent = event.agentKey ?? event.agent;
  if (event.event === 'agent_step_started') {
    return {
      event: 'agent_started',
      agent,
      label: event.label,
      message: event.message,
      phase: event.phase,
    };
  }
  if (event.event === 'agent_step_completed') {
    return {
      event: 'agent_completed',
      agent,
      label: event.label,
      message: event.message,
      phase: event.phase,
    };
  }
  if (event.event === 'agent_step_failed' || event.event === 'orchestration_failed') {
    return {
      event: 'error',
      agent,
      label: event.label,
      message: event.error || event.message || '对话请求失败，请稍后重试',
      phase: event.phase,
    };
  }

  const answer = event.profile ?? (event.answer ? sessionMessageFromAnswer(event.answer) : undefined);
  return {
    event: 'completed',
    agent,
    label: event.label,
    message: event.message,
    execution_id: event.sessionId,
    conversation_id: event.sessionId,
    answer,
    completed: event.completed,
    final_result: event.completed ? event.profile ?? null : null,
    phase: event.phase,
    error: event.error,
  };
}

function chatflowTurnFromSession(turn: SessionTurn): ChatflowTurn {
  const answer = turn.profile ?? sessionMessageFromAnswer(turn.answer);
  return {
    executionId: turn.sessionId,
    conversationId: turn.sessionId,
    answer,
    completed: turn.completed,
    finalResult: turn.completed ? turn.profile : null,
  };
}

export async function startSession(token: string, query: string): Promise<SessionTurn> {
  const payload = await requestOrchestration<SessionResponse>(
    '/api/orchestration/sessions/start',
    token,
    { query },
  );
  return normalizeSessionResponse(payload);
}

export async function continueSession(token: string, sessionId: string, query: string): Promise<SessionTurn> {
  const payload = await requestOrchestration<SessionResponse>(
    '/api/orchestration/sessions/continue',
    token,
    { session_id: sessionId, query },
  );
  return normalizeSessionResponse(payload);
}

export async function startChatflow(token: string, query: string): Promise<ChatflowTurn> {
  const turn = await startSession(token, query);
  return chatflowTurnFromSession(turn);
}

export async function continueChatflow(token: string, executionId: string, query: string): Promise<ChatflowTurn> {
  const turn = await continueSession(token, executionId, query);
  return chatflowTurnFromSession(turn);
}

export async function streamSession(
  token: string,
  query: string,
  sessionId: string | null,
  onEvent: (event: SessionAgentEvent) => void,
): Promise<SessionTurn> {
  const path = sessionId ? '/api/orchestration/sessions/continue/stream' : '/api/orchestration/sessions/start/stream';
  const body = sessionId ? { session_id: sessionId, query } : { query };
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as ApiErrorResponse | null;
    throw new Error(getErrorMessage(error));
  }
  if (!response.body) {
    throw new Error('浏览器无法读取实时对话流，请稍后重试');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalTurn: SessionTurn | null = null;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    if (done && buffer.trim()) {
      buffer += '\n\n';
    }
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;

    parsed.events.forEach((event) => {
      onEvent(event);
      if (event.event === 'orchestration_failed' || event.event === 'agent_step_failed') {
        throw new Error(event.error || event.message || '对话请求失败，请稍后重试');
      }
      if (event.event === 'orchestration_completed' && event.answer && event.sessionId) {
        finalTurn = {
          sessionId: event.sessionId,
          answer: event.answer,
          agentTrace: event.agentTrace ?? [],
          completed: event.completed ?? false,
          profile: event.profile ?? null,
          learningPath: event.learningPath ?? null,
        };
      }
    });

    if (done) break;
  }

  if (!finalTurn) {
    throw new Error('对话流已结束，但没有收到最终结果');
  }

  return finalTurn;
}

export async function streamChatflow(
  token: string,
  query: string,
  executionId: string | null,
  onEvent: (event: ChatflowAgentEvent) => void,
): Promise<ChatflowTurn> {
  const turn = await streamSession(token, query, executionId, (event) => onEvent(toChatflowEvent(event)));
  return chatflowTurnFromSession(turn);
}
