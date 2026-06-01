import type { LearningPathResult } from '../types/chat';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

export interface LearningPathRead {
  learningPath: LearningPathResult;
  updatedAt: string;
}

export async function getMyLearningPath(token: string): Promise<LearningPathRead> {
  const response = await fetch(`${API_BASE_URL}/api/learning-path/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error('还没有生成学习路径');
  }

  const payload = (await response.json()) as { learning_path: LearningPathResult; updated_at: string };
  return { learningPath: payload.learning_path, updatedAt: payload.updated_at };
}
