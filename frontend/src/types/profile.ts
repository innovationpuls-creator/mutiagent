import type { CourseKnowledgeResult, CourseNode, LearningPathResult } from './chat';

/**
 * 用户画像数据类型
 * 基于 Dify Agent 的 basic_profile → generated 阶段输出的 confirmed_info 结构
 */

export interface UserProfile {
  currentGrade: string;
  major: string;
  learningStage: string;
  hasClearGoal: string;
  learningMethodPreference: string;
  learningPacePreference: string;
  contentPreference: string[];
  needGuidance: string;
  knowledgeFoundation: string;
  strengths: string;
  weaknesses: string;
  experience: string;
  shortTermGoal: string;
  longTermGoal: string;
  weeklyAvailableTime: string;
  constraints: string;
}

export type RecommendationAccent = 'lavender' | 'sage' | 'peach';

export interface LearningRecommendation {
  id: string;
  title: string;
  duration: string;
  description: string;
  accent: RecommendationAccent;
}

export interface TodayLearning {
  title: string;
  description: string;
  source: string;
  currentLearningCourse: LearningPathResult['current_learning_course'] | null;
  currentCourseDetail: CourseNode | null;
  currentCourseOutline: CourseKnowledgeResult | null;
  followingCourses: CourseNode[];
}

export interface ProfileDashboardData {
  profile: UserProfile;
  profileCompleteness: number;
  profileSummaryText: string;
  todayLearning: TodayLearning;
  recommendations: LearningRecommendation[];
}
