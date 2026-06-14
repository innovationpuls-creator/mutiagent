import type {
  ForestAiContext,
  ForestAiEvent,
  ForestAttempt,
  ForestQuiz,
  ForestQuizAttemptCreateRequest,
  ForestQuizSession,
  ForestSubmitStreamDonePayload,
  ForestSubmitStreamEvent,
} from '../types/forest';
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from './http';

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function requireString(value: unknown, message: string): string {
  if (typeof value !== 'string') throw new Error(message);
  return value;
}

function normalizeForestQuizSession(value: unknown): ForestQuizSession {
  if (!isRecord(value) || !isRecord(value.course) || !isRecord(value.chapter) || !isRecord(value.progress)) {
    throw new Error('成林测验数据格式不正确');
  }
  return value as unknown as ForestQuizSession;
}

function normalizeForestQuiz(value: unknown): ForestQuiz {
  if (!isRecord(value) || typeof value.quiz_id !== 'string' || !Array.isArray(value.questions)) {
    throw new Error('成林题目数据格式不正确');
  }
  return value as unknown as ForestQuiz;
}

function normalizeForestAttempt(value: unknown): ForestAttempt {
  if (!isRecord(value) || typeof value.attempt_id !== 'string' || typeof value.quiz_id !== 'string') {
    throw new Error('成林测验提交数据格式不正确');
  }
  return value as unknown as ForestAttempt;
}

async function readForestError(response: Response, fallback: string): Promise<Error> {
  const error = await readApiError(response);
  notifyAuthInvalidFromError(response.status, error);
  return new Error((typeof error?.detail === 'string' ? error.detail : null) ?? fallback);
}

export async function fetchForestQuizSession(
  token: string,
  courseNodeId: string,
  chapterId: string,
): Promise<ForestQuizSession> {
  const response = await fetch(
    `${API_BASE_URL}/api/forest/courses/${encodeURIComponent(courseNodeId)}/chapters/${encodeURIComponent(chapterId)}/quiz`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!response.ok) throw await readForestError(response, '成林测验加载失败');
  return normalizeForestQuizSession(await response.json());
}

export async function generateForestQuiz(
  token: string,
  courseNodeId: string,
  chapterId: string,
  regenerate: boolean,
): Promise<ForestQuiz> {
  const response = await fetch(
    `${API_BASE_URL}/api/forest/courses/${encodeURIComponent(courseNodeId)}/chapters/${encodeURIComponent(chapterId)}/quiz/generate`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ regenerate }),
    },
  );
  if (!response.ok) throw await readForestError(response, '章节测验生成失败');
  return normalizeForestQuiz(await response.json());
}

export async function submitForestQuizAttempt(
  token: string,
  quizId: string,
  payload: ForestQuizAttemptCreateRequest,
): Promise<ForestAttempt> {
  const response = await fetch(
    `${API_BASE_URL}/api/forest/quizzes/${encodeURIComponent(quizId)}/attempts`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) throw await readForestError(response, '测验提交失败');
  return normalizeForestAttempt(await response.json());
}

export async function streamForestAi(
  token: string,
  context: ForestAiContext,
  message: string,
  onEvent: (event: ForestAiEvent) => void,
  imageAttachment?: string | null,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/forest/ai/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      course_node_id: context.course_node_id,
      chapter_id: context.chapter_id,
      quiz_id: context.quiz_id,
      question_id: context.question_id,
      message,
      active_question_context: context,
      image_attachment: imageAttachment || undefined,
    }),
  });
  if (!response.ok) throw await readForestError(response, 'Forest AI 暂时不可用');
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const eventLine = part.split('\n').find((line) => line.startsWith('event: '));
      const dataLine = part.split('\n').find((line) => line.startsWith('data: '));
      if (!eventLine || !dataLine) continue;
      const event = requireString(eventLine.slice('event: '.length), 'Forest AI 事件格式不正确');
      const data = JSON.parse(dataLine.slice('data: '.length)) as Record<string, unknown>;
      onEvent({ event: event as ForestAiEvent['event'], chunk: typeof data.chunk === 'string' ? data.chunk : undefined });
    }
  }
}

export async function submitForestQuizAttemptStream(
  token: string,
  quizId: string,
  payload: ForestQuizAttemptCreateRequest,
  onEvent: (event: ForestSubmitStreamEvent) => void,
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/forest/quizzes/${encodeURIComponent(quizId)}/attempts/stream`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) throw await readForestError(response, '测验提交失败');
  const reader = response.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';
    for (const part of parts) {
      const eventLine = part.split('\n').find((line) => line.startsWith('event: '));
      const dataLine = part.split('\n').find((line) => line.startsWith('data: '));
      if (!eventLine || !dataLine) continue;
      const eventName = requireString(eventLine.slice('event: '.length), '事件格式不正确');
      const dataText = dataLine.slice('data: '.length);
      const data = JSON.parse(dataText) as Record<string, unknown>;

      if (eventName === 'status') {
        onEvent({
          event: 'status',
          phase: data.phase as ForestSubmitStreamEvent['phase'],
          message: typeof data.message === 'string' ? data.message : undefined,
        });
      } else if (eventName === 'done') {
        onEvent({
          event: 'done',
          doneData: data as unknown as ForestSubmitStreamDonePayload,
        });
      } else if (eventName === 'error') {
        onEvent({
          event: 'error',
          message: typeof data.message === 'string' ? data.message : '测验提交时发生错误',
        });
      }
    }
  }
}
