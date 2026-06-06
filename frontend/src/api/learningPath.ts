import { isLearningPathResult, type LearningPathResult } from '../types/chat';
import { notifyAuthInvalidFromError, readApiError } from './http';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export interface LearningPathRead {
  yearLearningPaths: Record<string, LearningPathResult>;
  updatedAt: string | null;
}

function isUnknownRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function normalizeYearLearningPaths(value: unknown): Record<string, LearningPathResult> {
  if (!isUnknownRecord(value)) {
    throw new Error('学习路径数据格式不正确');
  }

  const entries = Object.entries(value);
  if (entries.some(([, path]) => !isLearningPathResult(path))) {
    throw new Error('学习路径数据格式不正确');
  }

  return Object.fromEntries(entries) as Record<string, LearningPathResult>;
}

export async function getMyLearningPath(token: string): Promise<LearningPathRead> {
  const response = await fetch(`${API_BASE_URL}/api/learning-path/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '还没有生成学习路径');
  }

  const payload = (await response.json()) as {
    year_learning_paths: unknown;
    updated_at: string | null;
  };
  return {
    yearLearningPaths: normalizeYearLearningPaths(payload.year_learning_paths),
    updatedAt: payload.updated_at,
  };
}
