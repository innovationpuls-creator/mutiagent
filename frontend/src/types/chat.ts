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

export interface AgentUserAnswer {
  userMessage: string;
  questionBox: QuestionBox | null;
}

export interface AgentTraceStep {
  stepId: string;
  agentKey: string;
  label: string;
  phase: string;
  status: string;
  message: string;
  kind: string;
  dependsOn: string[];
  parallelGroup: string | null;
}

export interface LearningPathResult {
  learning_goal: {
    target_course_or_skill: string;
    target_completion_time: string;
    goal_type: '考试' | '课程学习' | '项目实践' | '能力提升' | '就业准备' | '其他';
    desired_outcome: string;
  };
  gap_analysis: {
    current_mastered_content: string[];
    current_weaknesses: string[];
    required_capabilities: string[];
    main_gaps: string[];
  };
  foundation_path: {
    stages: Array<{
      stage_id: string;
      stage_name: string;
      learning_goal: string;
      learning_content: string[];
      learning_tasks: string[];
      recommended_methods: string[];
      completion_standard: string[];
    }>;
  };
  generated_path: {
    overall_goal: string;
    stage_routes: Array<{ stage_id: string; route_summary: string }>;
    schedule: Array<{ period: string; focus: string; milestone: string }>;
    task_checklist: string[];
    recommended_resource_types: string[];
    stage_acceptance_criteria: Array<{ stage_id: string; criteria: string[] }>;
    next_actions: string[];
  };
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

export type AgentRunStepKind = 'agent' | 'route' | 'answer' | 'data' | 'system';

export type AgentRunStepStatus = 'running' | 'success' | 'error' | 'skipped';

export interface AgentRunStep {
  stepId: string;
  kind: AgentRunStepKind;
  status: AgentRunStepStatus;
  title: string;
  summary?: string;
  agent?: string | null;
  durationMs?: number;
  dependsOn?: string[];
  parallelGroup?: string | null;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  timestamp: number;
  sessionMessage?: SessionMessage | null;
  agentAnswer?: AgentUserAnswer | null;
  learningPath?: LearningPathResult | null;
  runTrace?: AgentRunStep[];
  activeStepId?: string | null;
  error?: string;
}

export type ChatState = 'idle' | 'connecting' | 'streaming' | 'error';
