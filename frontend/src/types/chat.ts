export type ChatStage = 'basic_info' | 'learning_preference' | 'ability_basis' | 'goal_constraint' | 'generated';
export type QuestionMode = 'question_md' | 'question_box' | 'none';

export interface ConfirmedInfo {
  current_grade: string;
  major: string;
  learning_stage: string;
  has_clear_goal: string;
  learning_method_preference: string;
  learning_pace_preference: string;
  content_preference: string[];
  need_guidance: string;
  knowledge_foundation: string;
  strengths: string;
  weaknesses: string;
  experience: string;
  short_term_goal: string;
  long_term_goal: string;
  weekly_available_time: string;
  constraints: string;
}

export interface QuestionBox {
  question: string;
  options: string[];
}

export interface SessionMessage {
  type: 'collecting' | 'basic_profile';
  stage: ChatStage;
  question_mode: QuestionMode;
  confirmed_info: ConfirmedInfo;
  defaulted_fields: string[];
  question_md: string;
  question_box: QuestionBox;
  text: string;
}
