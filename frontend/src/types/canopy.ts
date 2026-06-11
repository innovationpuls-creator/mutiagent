export type CanopyCourseStatus = 'completed' | 'in_progress' | 'locked';

export interface CanopyCourseNode {
  id: string;
  title: string;
  grade: string;
  status: CanopyCourseStatus;
  score?: number;
  description: string;
  prerequisite_ids: string[];
}

export interface CanopyMilestone {
  date: string;
  title: string;
  desc: string;
  reached: boolean;
}

export interface CourseQualityScore {
  accuracy: number;
  difficulty_fit: number;
  completeness: number;
  overall: number;
  suggestions: string[];
  scored_at: string | null;
}

export interface CanopyOverview {
  courses: CanopyCourseNode[];
  growthStage: number;
  completedCount: number;
  activeRate: number;
  avgScore: number;
  focusedHours: number;
  milestones: CanopyMilestone[];
  qualityScores: Record<string, CourseQualityScore>;
}
