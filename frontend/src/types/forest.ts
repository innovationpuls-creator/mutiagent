import type { LeafCourse, LeafSection } from './leaf';

export type ForestQuestionType = 'single_choice' | 'code' | 'image_upload';
export type ForestProgressState = 'locked' | 'available' | 'passed';
export type ForestQuizStatus = 'generating' | 'ready' | 'error';

export interface ForestQuizQuestion {
  question_id: string;
  type: ForestQuestionType;
  prompt: string;
  options: Array<{ option_id: string; text: string }>;
  starter_code: string;
  image_prompt: string;
  points: number;
}

export interface ForestQuiz {
  quiz_id: string;
  course_node_id: string;
  chapter_id: string;
  status: ForestQuizStatus;
  questions: ForestQuizQuestion[];
  generation_error: string;
  created_at: string;
  updated_at: string;
}

export interface ForestAttempt {
  attempt_id: string;
  quiz_id: string;
  score: number;
  passed: boolean;
  answers: Record<string, unknown>;
  grading_result: Record<string, unknown>;
  created_at: string;
}

export interface ForestChapterProgress {
  course_node_id: string;
  chapter_id: string;
  state: ForestProgressState;
  best_score: number;
  latest_attempt_id: string | null;
  passed_at: string | null;
  updated_at: string;
}

export interface ForestQuizSession {
  course: LeafCourse;
  chapter: LeafSection;
  quiz: ForestQuiz | null;
  latest_attempt: ForestAttempt | null;
  progress: ForestChapterProgress;
  next_unlocked_chapter_id: string | null;
  next_course_id: string | null;
}

export interface ForestAiContext {
  course_node_id: string;
  chapter_id: string;
  quiz_id: string | null;
  question_id: string | null;
  question: ForestQuizQuestion | null;
  answer: unknown;
  grading_result: Record<string, unknown> | null;
}

export interface ForestAiEvent {
  event: 'forest_ai_text_chunk' | 'forest_ai_completed' | 'forest_error';
  chunk?: string;
  message?: string;
}
