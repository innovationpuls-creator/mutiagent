import type { SessionMessage } from '../types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface StartChatflowResponse {
  execution_id: string;
  conversation_id: string;
  answer: SessionMessage;
  completed: boolean;
  final_result: SessionMessage | null;
}

interface ContinueChatflowResponse {
  conversation_id: string;
  answer: SessionMessage;
  completed: boolean;
  final_result: SessionMessage | null;
}

interface ApiErrorResponse {
  detail?: string | { msg?: string }[];
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

async function requestChatflow<TResponse>(
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

export async function startChatflow(token: string, query: string): Promise<ChatflowTurn> {
  const payload = await requestChatflow<StartChatflowResponse>(
    '/api/orchestration/chatflow/start',
    token,
    { query },
  );

  return {
    executionId: payload.execution_id,
    conversationId: payload.conversation_id,
    answer: payload.answer,
    completed: payload.completed,
    finalResult: payload.final_result,
  };
}

export async function continueChatflow(
  token: string,
  executionId: string,
  query: string,
): Promise<ChatflowTurn> {
  const payload = await requestChatflow<ContinueChatflowResponse>(
    '/api/orchestration/chatflow/continue',
    token,
    { execution_id: executionId, query },
  );

  return {
    executionId,
    conversationId: payload.conversation_id,
    answer: payload.answer,
    completed: payload.completed,
    finalResult: payload.final_result,
  };
}

function parseSseChunk(buffer: string): { events: ChatflowAgentEvent[]; rest: string } {
  const parts = buffer.split('\n\n');
  const rest = parts.pop() ?? '';
  const events = parts
    .map((part) => {
      const eventLine = part.split('\n').find((line) => line.startsWith('event: '));
      const dataLine = part.split('\n').find((line) => line.startsWith('data: '));
      if (!eventLine || !dataLine) return null;

      const event = eventLine.slice('event: '.length).trim() as AgentEventName;
      const data = JSON.parse(dataLine.slice('data: '.length)) as Omit<ChatflowAgentEvent, 'event'>;
      return { event, ...data };
    })
    .filter((event): event is ChatflowAgentEvent => event !== null);

  return { events, rest };
}

export async function streamChatflow(
  token: string,
  query: string,
  executionId: string | null,
  onEvent: (event: ChatflowAgentEvent) => void,
): Promise<ChatflowTurn> {
  const path = executionId ? '/api/orchestration/chatflow/continue/stream' : '/api/orchestration/chatflow/start/stream';
  const body = executionId ? { execution_id: executionId, query } : { query };
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
  let finalTurn: ChatflowTurn | null = null;

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
      if (event.event === 'error') {
        throw new Error(event.message || '对话请求失败，请稍后重试');
      }
      if (event.event === 'completed' && event.error) {
        throw new Error(event.error);
      }
      if (event.event === 'completed' && event.answer && event.execution_id) {
        finalTurn = {
          executionId: event.execution_id,
          conversationId: event.conversation_id ?? '',
          answer: event.answer,
          completed: event.completed ?? false,
          finalResult: event.final_result ?? null,
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
