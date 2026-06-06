import {
  isCourseKnowledgeResult,
  isLearningPathResult,
  type ChatMessage,
  type SessionMessage,
  type CourseKnowledgeResult,
  type LearningPathResult,
} from '../types/chat';
import { hasCompleteBasicProfileRecord } from '../lib/profileContract';
import { notifyAuthInvalidFromError, readApiError, type ApiErrorResponse } from './http';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface UnknownRecord {
  [key: string]: unknown;
}

const REQUIRED_PROFILE_KEYS = [
  'current_grade',
  'major',
  'learning_stage',
  'has_clear_goal',
  'learning_method_preference',
  'learning_pace_preference',
  'content_preference',
  'need_guidance',
  'knowledge_foundation',
  'strengths',
  'weaknesses',
  'experience',
  'short_term_goal',
  'long_term_goal',
  'weekly_available_time',
  'constraints',
] as const;

// ── New backend response shapes ──

interface ChatStartResponse {
  session_id: string;
  reply_text: string | null;
  profile: Record<string, unknown> | null;
  year_learning_paths: Record<string, unknown> | null;
  latest_grade_year?: string | null;
  course_knowledge: Record<string, unknown> | null;
}

interface SessionStateResponse {
  session_id: string;
  user_uid: string;
  messages: unknown[];
  profile: Record<string, unknown> | null;
  year_learning_paths: Record<string, unknown> | null;
  latest_grade_year?: string | null;
  course_knowledge: Record<string, unknown> | null;
  updated_at: string;
}

// ── SSE event types (matches backend graph.py) ──

export type SessionEventName =
  | 'session_started'
  | 'supervisor_thinking'
  | 'supervisor_plan'
  | 'agent_calling'
  | 'agent_progress'
  | 'agent_result'
  | 'text_chunk'
  | 'data_update'
  | 'message_completed'
  | 'session_completed'
  | 'error';

export interface SessionAgentEvent {
  event: SessionEventName;
  stepId?: string;
  session_id?: string;
  query?: string;
  message?: string;
  agent?: string;
  label?: string;
  reason?: string;
  args?: string;
  success?: boolean;
  error?: string;
  summary?: string;
  chunk?: string;
  update_type?: string;
  years?: string[];
  full_text?: string;
  has_profile?: boolean;
  has_paths?: boolean;
  has_outline?: boolean;
  recoverable?: boolean;
  retryable?: boolean;
  retryAction?: 'retry_learning_path';
  // Timeline / orchestration detail fields (forward-compatible with detailed backend events)
  dependsOn?: string[];
  parallelGroup?: string;
  toolName?: string;
  output?: string;
  schemaName?: string;
  intent?: string;
  status?: string;
  kind?: string;
  course_id?: string;
  chapter_section_id?: string;
  section_id?: string;
  phase?: string;
}

export interface SessionTurn {
  sessionId: string;
  text: string;
  hasProfile: boolean;
  hasPaths: boolean;
  hasOutline: boolean;
}

export interface SessionStructuredData {
  profile: SessionMessage | null;
  learningPath: LearningPathResult | null;
  courseKnowledge: CourseKnowledgeResult | null;
}

export interface SessionRecoveryData extends SessionStructuredData {
  sessionId: string;
  messages: ChatMessage[];
  hasCompleteProfile: boolean;
}

export class SessionStreamError extends Error {
  sessionId: string | null;

  constructor(message: string, sessionId: string | null) {
    super(message);
    this.name = 'SessionStreamError';
    this.sessionId = sessionId;
  }
}

// ── Helpers ──

function getErrorMessage(error: ApiErrorResponse | null): string {
  if (!error?.detail) return '对话请求失败，请稍后重试';
  if (typeof error.detail === 'string') return error.detail;
  return '输入内容不完整，请检查后重试';
}

function getString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

function getBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function getStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.every((item) => typeof item === 'string') ? value : undefined;
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return value !== null && typeof value === 'object';
}

function isNullableUnknownRecord(value: unknown): value is UnknownRecord | null {
  return value === null || isUnknownRecord(value);
}

function normalizeChatStartResponse(value: unknown): ChatStartResponse {
  if (!isUnknownRecord(value)) {
    throw new Error('会话数据格式不正确');
  }

  if (
    typeof value.session_id !== 'string'
    || !(value.reply_text === null || value.reply_text === undefined || typeof value.reply_text === 'string')
    || !isNullableUnknownRecord(value.profile)
    || !isNullableUnknownRecord(value.year_learning_paths)
    || !(
      value.latest_grade_year === undefined
      || value.latest_grade_year === null
      || typeof value.latest_grade_year === 'string'
    )
    || !isNullableUnknownRecord(value.course_knowledge)
  ) {
    throw new Error('会话数据格式不正确');
  }

  return {
    session_id: value.session_id,
    reply_text: value.reply_text ?? null,
    profile: value.profile ?? null,
    year_learning_paths: value.year_learning_paths ?? null,
    latest_grade_year: value.latest_grade_year,
    course_knowledge: value.course_knowledge ?? null,
  };
}

function normalizeSessionStateResponse(value: unknown): SessionStateResponse {
  if (!isUnknownRecord(value)) {
    throw new Error('会话数据格式不正确');
  }

  const messages = value.messages;
  if (!(messages === undefined || Array.isArray(messages))) {
    throw new Error('会话数据格式不正确');
  }

  if (
    typeof value.session_id !== 'string'
    || typeof value.user_uid !== 'string'
    || !isNullableUnknownRecord(value.profile)
    || !isNullableUnknownRecord(value.year_learning_paths)
    || !(
      value.latest_grade_year === undefined
      || value.latest_grade_year === null
      || typeof value.latest_grade_year === 'string'
    )
    || !isNullableUnknownRecord(value.course_knowledge)
    || typeof value.updated_at !== 'string'
  ) {
    throw new Error('会话数据格式不正确');
  }

  return {
    session_id: value.session_id,
    user_uid: value.user_uid,
    messages: messages ?? [],
    profile: value.profile ?? null,
    year_learning_paths: value.year_learning_paths ?? null,
    latest_grade_year: value.latest_grade_year,
    course_knowledge: value.course_knowledge ?? null,
    updated_at: value.updated_at,
  };
}

function pickLearningPath(
  yearLearningPaths: Record<string, unknown> | null,
  courseKnowledge: CourseKnowledgeResult | null,
  latestGradeYear?: string | null,
): LearningPathResult | null {
  if (!isUnknownRecord(yearLearningPaths)) return null;
  const validPaths = Object.values(yearLearningPaths).filter(isLearningPathResult);
  if (validPaths.length === 0) return null;

  if (courseKnowledge) {
    const matchedPath = validPaths.find(
      (path) => path.current_learning_course.course_node_id === courseKnowledge.course_id,
    );
    if (matchedPath) return matchedPath;
  }

  if (typeof latestGradeYear === 'string' && latestGradeYear.trim()) {
    const preferredPath = yearLearningPaths[latestGradeYear];
    if (isLearningPathResult(preferredPath)) return preferredPath;
  }

  return validPaths[0] ?? null;
}

function pickCourseKnowledge(courseKnowledge: Record<string, unknown> | null): CourseKnowledgeResult | null {
  if (!courseKnowledge) return null;
  return isCourseKnowledgeResult(courseKnowledge) ? courseKnowledge : null;
}

function pickProfile(profile: Record<string, unknown> | null): SessionMessage | null {
  if (!isUnknownRecord(profile)) return null;
  if (profile.type !== 'basic_profile' && profile.type !== 'collecting') return null;
  if (profile.type === 'basic_profile' && !hasCompleteBasicProfileRecord(profile, REQUIRED_PROFILE_KEYS)) {
    return null;
  }
  if (typeof profile.stage !== 'string') return null;
  if (typeof profile.question_mode !== 'string') return null;
  if (!isUnknownRecord(profile.confirmed_info)) return null;
  if (!Array.isArray(profile.defaulted_fields)) return null;
  if (typeof profile.question_md !== 'string') return null;
  if (!isUnknownRecord(profile.question_box)) return null;
  if (!Array.isArray(profile.question_box.options)) return null;
  if (typeof profile.question_box.question !== 'string') return null;
  if (typeof profile.text !== 'string') return null;
  return profile as unknown as SessionMessage;
}

function pickProfileSummaryText(profile: Record<string, unknown> | null): string | null {
  if (!isUnknownRecord(profile)) return null;
  return getString(profile.summary_text) ?? null;
}

function isGeneratedProfileCompletionContent(content: string): boolean {
  return content === '基础画像已完成' || content === '你的画像已生成';
}

function isCombinedLearningResultCompletionContent(content: string): boolean {
  return content === '学习路径和课程大纲已生成';
}

export function isLearningPathStructuredCompletionContent(content: string): boolean {
  return content.startsWith('学习路径已生成')
    || content.startsWith('你的学习路径里已经有这些课程：')
    || isCombinedLearningResultCompletionContent(content);
}

export function isCourseKnowledgeStructuredCompletionContent(content: string): boolean {
  return content.startsWith('课程大纲已生成')
    || content.startsWith('课程大纲 · ')
    || isCombinedLearningResultCompletionContent(content);
}

function hasCompleteProfile(profile: Record<string, unknown> | null): boolean {
  if (!isUnknownRecord(profile)) return false;
  return hasCompleteBasicProfileRecord(profile, REQUIRED_PROFILE_KEYS);
}

function parsePersistedMessages(
  sessionId: string,
  updatedAt: string,
  rawMessages: unknown[],
): ChatMessage[] {
  const parsedUpdatedAt = Date.parse(updatedAt);
  const baseTimestamp = Number.isFinite(parsedUpdatedAt) ? parsedUpdatedAt : Date.now();
  const messages: ChatMessage[] = [];

  rawMessages.forEach((rawMessage, index) => {
    if (!isUnknownRecord(rawMessage)) return;
    const type = getString(rawMessage.type);
    const data = isUnknownRecord(rawMessage.data) ? rawMessage.data : null;
    const content = data ? getString(data.content) : undefined;
    if (!type || !content) return;

    if (type === 'human') {
      messages.push({
        id: `recovered-${sessionId}-${index}`,
        role: 'user',
        content,
        status: 'completed',
        timestamp: baseTimestamp + index,
      });
      return;
    }

    if (type === 'ai') {
      messages.push({
        id: `recovered-${sessionId}-${index}`,
        role: 'assistant',
        content,
        status: 'completed',
        timestamp: baseTimestamp + index,
        runTrace: [],
        activeStepId: null,
      });
    }
  });

  return messages;
}

function buildSessionStructuredData(payload: SessionStateResponse): SessionStructuredData {
  const rawCourseKnowledge = pickCourseKnowledge(payload.course_knowledge);
  const learningPath = pickLearningPath(
    payload.year_learning_paths,
    rawCourseKnowledge,
    payload.latest_grade_year,
  );
  const courseKnowledge = (
    rawCourseKnowledge
    && learningPath
    && learningPath.current_learning_course.course_node_id !== rawCourseKnowledge.course_id
  )
    ? null
    : rawCourseKnowledge;
  return {
    profile: pickProfile(payload.profile),
    learningPath,
    courseKnowledge,
  };
}

function findLastMatchingAssistantMessageIndex(
  messages: ChatMessage[],
  predicate: (content: string) => boolean,
): number {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role !== 'assistant') continue;
    if (predicate(message.content.trim())) return index;
  }
  return -1;
}

function attachStructuredDataToRecoveredMessages(
  messages: ChatMessage[],
  structuredData: SessionStructuredData,
  profileSummaryText: string | null,
): ChatMessage[] {
  const profileTargetIndex = structuredData.profile
    ? findLastMatchingAssistantMessageIndex(messages, (content) => (
      content === structuredData.profile?.text
      || (
        structuredData.profile?.type === 'basic_profile'
        && structuredData.profile.stage === 'generated'
        && isGeneratedProfileCompletionContent(content)
      )
      || (profileSummaryText !== null && content === profileSummaryText)
    ))
    : -1;

  const learningPathTargetIndex = structuredData.learningPath
    ? findLastMatchingAssistantMessageIndex(messages, (content) => (
      isLearningPathStructuredCompletionContent(content)
    ))
    : -1;

  const courseKnowledgeTargetIndex = structuredData.courseKnowledge
    ? findLastMatchingAssistantMessageIndex(messages, (content) => (
      isCourseKnowledgeStructuredCompletionContent(content)
    ))
    : -1;

  if (
    profileTargetIndex < 0
    && learningPathTargetIndex < 0
    && courseKnowledgeTargetIndex < 0
  ) {
    return messages;
  }

  const nextMessages = [...messages];

  if (profileTargetIndex >= 0) {
    const target = nextMessages[profileTargetIndex];
    nextMessages[profileTargetIndex] = {
      ...target,
      sessionMessage: structuredData.profile,
    };
  }

  if (learningPathTargetIndex >= 0) {
    const target = nextMessages[learningPathTargetIndex];
    nextMessages[learningPathTargetIndex] = {
      ...target,
      learningPath: structuredData.learningPath,
    };
  }

  if (courseKnowledgeTargetIndex >= 0) {
    const target = nextMessages[courseKnowledgeTargetIndex];
    nextMessages[courseKnowledgeTargetIndex] = {
      ...target,
      learningPath: target.learningPath ?? null,
      courseKnowledge: structuredData.courseKnowledge,
    };
  }

  return nextMessages;
}

// ── SSE parsing ──

function normalizeSessionEvent(rawEvent: string, payload: UnknownRecord): SessionAgentEvent {
  // For "message" events, the real event type is in payload.type
  const event = (rawEvent === 'message' ? getString(payload.type) : rawEvent) as SessionEventName;

  return {
    event,
    stepId: getString(payload.stepId),
    session_id: getString(payload.session_id),
    query: getString(payload.query),
    message: getString(payload.message),
    agent: getString(payload.agent),
    label: getString(payload.label),
    reason: getString(payload.reason),
    args: getString(payload.args),
    success: getBoolean(payload.success),
    error: getString(payload.error),
    summary: getString(payload.summary),
    chunk: getString(payload.chunk),
    update_type: getString(payload.update_type),
    years: getStringArray(payload.years),
    full_text: getString(payload.full_text),
    has_profile: getBoolean(payload.has_profile),
    has_paths: getBoolean(payload.has_paths),
    has_outline: getBoolean(payload.has_outline),
    recoverable: getBoolean(payload.recoverable),
    retryable: getBoolean(payload.retryable),
    retryAction: getString(payload.retryAction) === 'retry_learning_path'
      ? 'retry_learning_path'
      : undefined,
    dependsOn: getStringArray(payload.dependsOn),
    parallelGroup: getString(payload.parallelGroup),
    toolName: getString(payload.toolName),
    output: getString(payload.output),
    schemaName: getString(payload.schemaName),
    intent: getString(payload.intent),
    status: getString(payload.status),
    kind: getString(payload.kind),
    course_id: getString(payload.course_id),
    chapter_section_id: getString(payload.chapter_section_id),
    section_id: getString(payload.section_id),
    phase: getString(payload.phase),
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

      const rawEvent = eventLine.slice('event: '.length).trim();
      const data = dataLines.map((line) => line.slice('data: '.length)).join('\n');
      const payload = JSON.parse(data) as UnknownRecord;
      return normalizeSessionEvent(rawEvent, payload);
    })
    .filter((event): event is SessionAgentEvent => event !== null);

  return { events, rest };
}

// ── API calls ──

async function requestChat<TResponse>(
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
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error(getErrorMessage(error));
  }

  return (await response.json()) as TResponse;
}

async function requestSessionState(
  token: string,
  sessionId: string,
): Promise<SessionStateResponse> {
  const response = await fetch(`${API_BASE_URL}/api/chat/sessions/${sessionId}`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error(getErrorMessage(error));
  }

  return normalizeSessionStateResponse(await response.json());
}

export async function startSession(token: string, query: string): Promise<SessionTurn> {
  const payload = normalizeChatStartResponse(await requestChat<unknown>(
    '/api/chat/start',
    token,
    { query },
  ));
  const courseKnowledge = pickCourseKnowledge(payload.course_knowledge);
  return {
    sessionId: payload.session_id,
    text: payload.reply_text ?? '',
    hasProfile: hasCompleteProfile(payload.profile),
    hasPaths: pickLearningPath(
      payload.year_learning_paths,
      courseKnowledge,
      payload.latest_grade_year,
    ) !== null,
    hasOutline: courseKnowledge !== null,
  };
}

export async function fetchSessionState(
  token: string,
  sessionId: string,
): Promise<SessionStructuredData> {
  const payload = await requestSessionState(token, sessionId);
  return buildSessionStructuredData(payload);
}

export async function fetchSessionRecoveryData(
  token: string,
  sessionId: string,
): Promise<SessionRecoveryData> {
  const payload = await requestSessionState(token, sessionId);
  const structuredData = buildSessionStructuredData(payload);
  const messages = attachStructuredDataToRecoveredMessages(
    parsePersistedMessages(payload.session_id, payload.updated_at, payload.messages),
    structuredData,
    pickProfileSummaryText(payload.profile),
  );

  return {
    sessionId: payload.session_id,
    messages,
    hasCompleteProfile: hasCompleteProfile(payload.profile),
    ...structuredData,
  };
}

export async function streamSession(
  token: string,
  query: string,
  sessionId: string | null,
  onEvent: (event: SessionAgentEvent) => void,
): Promise<SessionTurn> {
  // If no sessionId, create one first via /api/chat/start
  let activeSessionId = sessionId;
  let greetingText = '';

  if (!activeSessionId) {
    const startPayload = normalizeChatStartResponse(await requestChat<unknown>(
      '/api/chat/start',
      token,
      { query },
    ));
    activeSessionId = startPayload.session_id;
    greetingText = startPayload.reply_text ?? '';
  }

  // Now send the actual user message via SSE stream
  const response = await fetch(`${API_BASE_URL}/api/chat/message`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      Accept: 'text/event-stream',
    },
    body: JSON.stringify({ session_id: activeSessionId, message: query }),
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new SessionStreamError(getErrorMessage(error), activeSessionId);
  }
  if (!response.body) {
    throw new SessionStreamError('浏览器无法读取实时对话流，请稍后重试', activeSessionId);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullText = '';
  let completedSessionId: string | null = null;
  let hasProfile = false;
  let hasPaths = false;
  let hasOutline = false;

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    if (done && buffer.trim()) {
      buffer += '\n\n';
    }
    const parsed = parseSseChunk(buffer);
    buffer = parsed.rest;

    for (const event of parsed.events) {
      onEvent(event);

      if (event.event === 'error') {
        throw new SessionStreamError(
          event.message || event.error || '对话请求失败，请稍后重试',
          completedSessionId ?? activeSessionId,
        );
      }

      if (event.event === 'text_chunk' && event.chunk) {
        fullText += event.chunk;
      }

      if (event.event === 'message_completed' && event.full_text) {
        fullText = event.full_text;
      }

      if (event.event === 'session_completed') {
        completedSessionId = event.session_id ?? activeSessionId;
        hasProfile = event.has_profile ?? false;
        hasPaths = event.has_paths ?? false;
        hasOutline = event.has_outline ?? false;
      }
    }

    if (done) break;
  }

  return {
    sessionId: completedSessionId ?? activeSessionId,
    text: fullText || greetingText,
    hasProfile,
    hasPaths,
    hasOutline,
  };
}
