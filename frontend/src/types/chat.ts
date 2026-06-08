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
  options: QuestionBoxOption[];
}

export interface QuestionBoxOption {
  label: string;
  value: string;
  description: string;
  target_fields: string[];
  fills: Record<string, string | string[]>;
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
  schema_version: 'learning_path.v2.course_node';
  learning_goal: {
    target_course_or_skill: string;
    goal_type: '考试' | '课程学习' | '项目实践' | '能力提升' | '就业准备' | '其他';
    desired_outcome: string;
    four_year_outcome: string;
  };
  learner_baseline: {
    current_grade: string;
    major: string;
    mastered_content: string[];
    weaknesses: string[];
    constraints: string[];
    weekly_available_time: string;
  };
  planning_rules: {
    node_unit: 'course_node';
    grade_boundary_rule: string;
    sequence_rule: string;
    resource_rule: string;
  };
  grade_plans: Partial<Record<GradeId, GradePlan>>;
  knowledge_graph: {
    global_relations: KnowledgeRelation[];
    critical_paths: CriticalPath[];
  };
  resource_generation_contract: {
    downstream_agents: ResourceAgent[];
    resource_directions: ResourceDirection[];
  };
  dynamic_update_contract: {
    trackable_metrics: string[];
    update_triggers: string[];
    adjustment_strategy: string;
  };
  current_learning_course: CurrentLearningCourse;
}

export interface CourseKnowledgeSection {
  section_id: string;
  parent_section_id: string | null;
  depth: number;
  title: string;
  order_index: number;
  description: string;
  key_knowledge_points: string[];
}

export interface CourseKnowledgeResult {
  course_id: string;
  course_name: string;
  grade_year: string;
  personalization_summary: string;
  sections: CourseKnowledgeSection[];
  learning_sequence: string[];
  total_estimated_hours: string;
}

function hasRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function hasString(value: unknown): value is string {
  return typeof value === 'string';
}

function hasArray(value: unknown): value is unknown[] {
  return Array.isArray(value);
}

function isCurrentLearningProgressState(value: unknown): value is CurrentLearningCourse['progress_state'] {
  return value === 'in_progress' || value === 'completed';
}

export function isLearningPathResult(value: unknown): value is LearningPathResult {
  if (!hasRecord(value)) return false;
  if (value.schema_version !== 'learning_path.v2.course_node') return false;

  const learningGoal = value.learning_goal;
  const learnerBaseline = value.learner_baseline;
  const gradePlans = value.grade_plans;
  const knowledgeGraph = value.knowledge_graph;
  const resourceContract = value.resource_generation_contract;
  const updateContract = value.dynamic_update_contract;
  const currentLearningCourse = value.current_learning_course;
  if (!hasRecord(learningGoal) || !hasRecord(learnerBaseline) || !hasRecord(gradePlans)) return false;
  if (!hasRecord(knowledgeGraph) || !hasRecord(resourceContract) || !hasRecord(updateContract)) return false;
  if (!hasRecord(currentLearningCourse)) return false;

  type GradePlanRecord = Record<string, unknown> & {
    grade_id: string;
    grade_name: string;
    grade_goal: string;
    course_nodes: unknown[];
  };

  const isGradePlan = (gradePlan: unknown): gradePlan is GradePlanRecord => hasRecord(gradePlan)
      && hasString(gradePlan.grade_id)
      && hasString(gradePlan.grade_name)
      && hasString(gradePlan.grade_goal)
      && hasArray(gradePlan.course_nodes);

  const hasGradePlan = (gradeId: string) => {
    const gradePlan = gradePlans[gradeId];
    return isGradePlan(gradePlan);
  };

  const hasAnyGradePlan = Object.values(gradePlans).some(isGradePlan);
  const currentGradeId = currentLearningCourse.grade_id;
  const hasCurrentGradePlan = hasString(currentGradeId) && hasGradePlan(currentGradeId);
  const currentGradePlan = hasString(currentGradeId) ? gradePlans[currentGradeId] : undefined;

  const hasCurrentCourseNode = hasCurrentGradePlan && isGradePlan(currentGradePlan) && currentGradePlan.course_nodes.some((courseNode) => (
    hasRecord(courseNode)
    && courseNode.course_node_id === currentLearningCourse.course_node_id
  ));

  const hasValidGradePlanKeys = Object.keys(gradePlans).every((gradeId) => (
    gradeId === 'year_1' || gradeId === 'year_2' || gradeId === 'year_3' || gradeId === 'year_4'
  ));

  const hasValidGradePlanIds = Object.entries(gradePlans).every(([gradeId, gradePlan]) => {
    if (!isGradePlan(gradePlan)) return false;
    return gradePlan.grade_id === gradeId;
  });

  if (!hasValidGradePlanKeys || !hasValidGradePlanIds) return false;

  const hasTimeArrangement = (value: unknown) => {
    if (!hasRecord(value)) return false;
    return hasString(value.semester_scope)
      && hasString(value.duration)
      && hasString(value.pace_reason);
  };

  const hasCourseNodeShape = (courseNode: unknown) => {
    if (!hasRecord(courseNode)) return false;
    return hasString(courseNode.course_node_id)
      && hasString(courseNode.grade_id)
      && hasString(courseNode.course_or_chapter_theme)
      && hasTimeArrangement(courseNode.time_arrangement)
      && hasString(courseNode.course_goal)
      && hasArray(courseNode.prerequisite_node_ids)
      && hasArray(courseNode.chapter_nodes)
      && hasArray(courseNode.core_knowledge_points)
      && hasArray(courseNode.key_points)
      && hasArray(courseNode.difficult_points)
      && hasArray(courseNode.learning_sequence)
      && hasArray(courseNode.knowledge_relations)
      && hasArray(courseNode.downstream_resource_direction_ids)
      && hasArray(courseNode.acceptance_criteria);
  };

  const hasValidCourseNodes = Object.entries(gradePlans).every(([gradeId, gradePlan]) => {
    if (!isGradePlan(gradePlan)) return false;
    return gradePlan.course_nodes.every((courseNode) => (
      hasCourseNodeShape(courseNode)
      && hasRecord(courseNode)
      && courseNode.grade_id === gradeId
    ));
  });

  return hasString(learningGoal.target_course_or_skill)
    && hasString(learningGoal.goal_type)
    && hasString(learningGoal.desired_outcome)
    && hasString(learningGoal.four_year_outcome)
    && hasString(learnerBaseline.current_grade)
    && hasString(learnerBaseline.major)
    && hasArray(learnerBaseline.mastered_content)
    && hasArray(learnerBaseline.weaknesses)
    && hasArray(learnerBaseline.constraints)
    && hasString(learnerBaseline.weekly_available_time)
    && hasAnyGradePlan
    && hasCurrentGradePlan
    && hasCurrentCourseNode
    && hasValidCourseNodes
    && hasArray(knowledgeGraph.global_relations)
    && hasArray(knowledgeGraph.critical_paths)
    && hasArray(resourceContract.downstream_agents)
    && hasArray(resourceContract.resource_directions)
    && hasArray(updateContract.trackable_metrics)
    && hasArray(updateContract.update_triggers)
    && hasString(updateContract.adjustment_strategy)
    && hasString(currentLearningCourse.grade_id)
    && hasString(currentLearningCourse.course_node_id)
    && hasString(currentLearningCourse.course_or_chapter_theme)
    && hasString(currentLearningCourse.course_goal)
    && hasTimeArrangement(currentLearningCourse.time_arrangement)
    && hasString(currentLearningCourse.current_focus)
    && isCurrentLearningProgressState(currentLearningCourse.progress_state)
    && hasString(currentLearningCourse.next_action);
}

export function isCourseKnowledgeResult(value: unknown): value is CourseKnowledgeResult {
  if (!hasRecord(value)) return false;
  if (!hasString(value.course_id)) return false;
  if (!hasString(value.course_name)) return false;
  if (!hasString(value.grade_year)) return false;
  if (!hasString(value.personalization_summary)) return false;
  if (!hasArray(value.sections)) return false;
  if (!hasArray(value.learning_sequence)) return false;
  if (!hasString(value.total_estimated_hours)) return false;

  return value.sections.every((section) =>
    hasRecord(section)
    && hasString(section.section_id)
    && (section.parent_section_id === null || hasString(section.parent_section_id))
    && typeof section.depth === 'number'
    && typeof section.order_index === 'number'
    && hasString(section.title)
    && hasString(section.description)
    && hasArray(section.key_knowledge_points),
  ) && value.learning_sequence.every((item) => hasString(item));
}

export type GradeId = 'year_1' | 'year_2' | 'year_3' | 'year_4';
export type SemesterScope = '上学期' | '下学期' | '寒假' | '暑假' | '全年级内弹性安排';
export type HierarchyLevel = '课程' | '章节' | '主题' | '知识点';
export type KnowledgePointLevel = '基础' | '核心' | '进阶' | '应用';
export type RelationType =
  | 'prerequisite'
  | 'contains'
  | 'parallel'
  | 'reinforces'
  | 'applies_to'
  | 'extends'
  | 'review_before'
  | 'resource_basis_for';
export type ResourceAgent =
  | 'learning_resource_agent'
  | 'question_bank_agent'
  | 'document_agent'
  | 'code_example_agent'
  | 'video_script_agent'
  | 'dynamic_update_agent';
export type ResourceType = '学习资源' | '题库' | '文档' | '代码示例' | '视频脚本' | '动态更新任务';
export type DifficultyLevel = '入门' | '基础' | '中级' | '高级';

export interface GradePlan {
  grade_id: GradeId;
  grade_name: string;
  grade_goal: string;
  course_nodes: CourseNode[];
}

export interface CourseNode {
  course_node_id: string;
  grade_id: GradeId;
  course_or_chapter_theme: string;
  time_arrangement: TimeArrangement;
  course_goal: string;
  prerequisite_node_ids: string[];
  chapter_nodes: ChapterNode[];
  core_knowledge_points: KnowledgePoint[];
  key_points: string[];
  difficult_points: string[];
  learning_sequence: string[];
  knowledge_relations: KnowledgeRelation[];
  downstream_resource_direction_ids: string[];
  acceptance_criteria: string[];
}

export interface CurrentLearningCourse {
  grade_id: GradeId;
  course_node_id: string;
  course_or_chapter_theme: string;
  course_goal: string;
  time_arrangement: TimeArrangement;
  current_focus: string;
  progress_state: 'in_progress' | 'completed';
  next_action: string;
}

export interface TimeArrangement {
  semester_scope: SemesterScope;
  duration: string;
  pace_reason: string;
}

export interface ChapterNode {
  chapter_node_id: string;
  chapter_theme: string;
  knowledge_hierarchy: KnowledgeHierarchyItem[];
  core_knowledge_point_ids: string[];
  key_points: string[];
  difficult_points: string[];
  prerequisite_node_ids: string[];
  learning_sequence: string[];
  knowledge_relations: KnowledgeRelation[];
  downstream_resource_direction_ids: string[];
}

export interface KnowledgeHierarchyItem {
  hierarchy_id: string;
  parent_hierarchy_id: string | null;
  hierarchy_level: HierarchyLevel;
  title: string;
  summary: string;
  knowledge_point_ids: string[];
}

export interface KnowledgePoint {
  knowledge_point_id: string;
  name: string;
  parent_knowledge_point_id: string | null;
  level: KnowledgePointLevel;
  description: string;
  mastery_standard: string;
}

export interface KnowledgeRelation {
  from_node_id: string;
  to_node_id: string;
  relation_type: RelationType;
  description: string;
}

export interface CriticalPath {
  path_id: string;
  purpose: string;
  ordered_node_ids: string[];
}

export interface ResourceDirection {
  resource_direction_id: string;
  target_node_ids: string[];
  resource_type: ResourceType;
  generation_goal: string;
  content_requirements: string[];
  difficulty_level: DifficultyLevel;
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

export type AgentRunStepKind = 'agent' | 'route' | 'answer' | 'data' | 'system' | 'thought' | 'tool_call';

export type AgentRunStepStatus = 'running' | 'success' | 'error' | 'skipped';

export interface ThoughtChunkEntry {
  stepId: string;
  text: string;
  timestamp: number;
}

export interface PartialStructuredData {
  schemaName: string;
  partialData: unknown;
  raw: string;
  timestamp: number;
}

export interface AgentRunStep {
  stepId: string;
  kind: AgentRunStepKind;
  status: AgentRunStepStatus;
  title: string;
  summary?: string;
  agent?: string | null;
  startedAtMs?: number;
  durationMs?: number;
  dependsOn?: string[];
  parallelGroup?: string | null;
  thoughtLog?: ThoughtChunkEntry[];
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
  courseKnowledge?: CourseKnowledgeResult | null;
  runTrace?: AgentRunStep[];
  activeStepId?: string | null;
  error?: string;
  retryAction?: 'retry_learning_path' | null;
  partialData?: PartialStructuredData | null;
}

export type ChatState = 'idle' | 'connecting' | 'streaming' | 'error';
