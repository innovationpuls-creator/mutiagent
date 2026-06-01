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

export type MessageRole = 'user' | 'assistant' | 'system';

export type MessageStatus = 'pending' | 'streaming' | 'completed' | 'error';

export type AgentRunStepKind = 'agent' | 'route' | 'answer';

export type AgentRunStepStatus = 'running' | 'success' | 'error' | 'skipped';

export interface AgentRunStep {
  stepId: string;
  kind: AgentRunStepKind;
  status: AgentRunStepStatus;
  title: string;
  summary?: string;
  agent?: string | null;
  durationMs?: number;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  timestamp: number;
  sessionMessage?: SessionMessage | null;
  runTrace?: AgentRunStep[];
  activeStepId?: string | null;
  error?: string;
}

export type ChatState = 'idle' | 'connecting' | 'streaming' | 'error';
