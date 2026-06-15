import type { BranchOverview, BranchYear, BranchCourseNode, BranchCourseStatus } from '../types/branch';
import type {
  CanopyCourseNode,
  CanopyCourseStatus,
  CanopyMilestone,
  CanopyOverview,
} from '../types/canopy';
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from './http';

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function isStatus(value: unknown): value is BranchCourseStatus {
  return value === 'completed' || value === 'current' || value === 'locked';
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === 'string');
}

function normalizeCanopyStatus(value: unknown): CanopyCourseStatus {
  if (value === 'completed' || value === 'locked') {
    return value;
  }
  if (value === 'current') {
    return 'in_progress';
  }
  throw new Error('成森数据格式不正确');
}

function normalizeTimeArrangement(value: unknown): BranchCourseNode['time_arrangement'] {
  if (!isRecord(value)) {
    return undefined;
  }
  const sem = value.semester_scope;
  const dur = value.duration;
  const pace = value.pace_reason;
  if (typeof sem === 'string' && typeof dur === 'string') {
    return {
      semester_scope: sem,
      duration: dur,
      pace_reason: typeof pace === 'string' ? pace : undefined,
    };
  }
  return undefined;
}

export function normalizeCourse(value: unknown): BranchCourseNode {
  if (!isRecord(value)) {
    throw new Error('繁枝数据格式不正确');
  }
  const courseId = value.course_node_id;
  const theme = value.course_or_chapter_theme;
  const goal = value.course_goal;
  const status = value.status;
  const hasOutline = value.has_outline;
  if (
    typeof courseId !== 'string'
    || typeof theme !== 'string'
    || typeof goal !== 'string'
    || !isStatus(status)
    || typeof hasOutline !== 'boolean'
  ) {
    throw new Error('繁枝数据格式不正确');
  }
  
  const isCustom = typeof value.is_custom === 'boolean' ? value.is_custom : undefined;
  const parentPresetId = typeof value.parent_preset_id === 'string' ? value.parent_preset_id : undefined;
  const prerequisiteIds = isStringArray(value.prerequisite_ids)
    ? value.prerequisite_ids
    : undefined;
    
  const timeArrangement = normalizeTimeArrangement(value.time_arrangement);
  
  const keyPoints = isStringArray(value.key_points) ? value.key_points : undefined;
  const difficultPoints = isStringArray(value.difficult_points) ? value.difficult_points : undefined;
  const acceptanceCriteria = isStringArray(value.acceptance_criteria) ? value.acceptance_criteria : undefined;

  return {
    course_node_id: courseId,
    course_or_chapter_theme: theme,
    course_goal: goal,
    status,
    has_outline: hasOutline,
    is_custom: isCustom,
    parent_preset_id: parentPresetId,
    prerequisite_ids: prerequisiteIds,
    time_arrangement: timeArrangement,
    key_points: keyPoints,
    difficult_points: difficultPoints,
    acceptance_criteria: acceptanceCriteria,
  };
}

function normalizeCanopyCourse(value: unknown): CanopyCourseNode {
  if (!isRecord(value)) {
    throw new Error('成森数据格式不正确');
  }
  const id = value.id;
  const title = value.title;
  const grade = value.grade;
  const status = value.status;
  const score = value.score;
  const description = value.description;
  const prerequisiteIds = value.prerequisite_ids;
  if (
    typeof id !== 'string'
    || typeof title !== 'string'
    || typeof grade !== 'string'
    || !(score === null || score === undefined || typeof score === 'number')
    || typeof description !== 'string'
    || !isStringArray(prerequisiteIds)
  ) {
    throw new Error('成森数据格式不正确');
  }
  return {
    id,
    title,
    grade,
    status: normalizeCanopyStatus(status),
    score: typeof score === 'number' ? score : undefined,
    description,
    prerequisite_ids: prerequisiteIds,
  };
}

function normalizeQualityScores(raw: unknown): Record<string, import('../types/canopy').CourseQualityScore> {
  if (!raw || typeof raw !== 'object') return {};
  const result: Record<string, import('../types/canopy').CourseQualityScore> = {};
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (isRecord(value)) {
      result[key] = {
        accuracy: typeof value.accuracy === 'number' ? value.accuracy : 0,
        difficulty_fit: typeof value.difficulty_fit === 'number' ? value.difficulty_fit : 0,
        completeness: typeof value.completeness === 'number' ? value.completeness : 0,
        overall: typeof value.overall === 'number' ? value.overall : 0,
        suggestions: Array.isArray(value.suggestions)
          ? value.suggestions.filter((s): s is string => typeof s === 'string')
          : [],
        scored_at: typeof value.scored_at === 'string' ? value.scored_at : null,
      };
    }
  }
  return result;
}

function normalizeCanopyMilestone(value: unknown): CanopyMilestone {
  if (!isRecord(value)) {
    throw new Error('成森数据格式不正确');
  }
  const date = value.date;
  const title = value.title;
  const desc = value.desc;
  const reached = value.reached;
  if (
    typeof date !== 'string'
    || typeof title !== 'string'
    || typeof desc !== 'string'
    || typeof reached !== 'boolean'
  ) {
    throw new Error('成森数据格式不正确');
  }
  return { date, title, desc, reached };
}

function normalizeYear(value: unknown): BranchYear {
  if (!isRecord(value)) {
    throw new Error('繁枝数据格式不正确');
  }
  const gradeId = value.grade_id;
  const gradeName = value.grade_name;
  const hasCourses = value.has_courses;
  const hasOutlineContent = value.has_outline_content;
  const isClickable = value.is_clickable;
  const currentCourseId = value.current_course_id;
  const courses = value.courses;
  if (
    typeof gradeId !== 'string'
    || typeof gradeName !== 'string'
    || typeof hasCourses !== 'boolean'
    || typeof hasOutlineContent !== 'boolean'
    || typeof isClickable !== 'boolean'
    || !(currentCourseId === null || typeof currentCourseId === 'string')
    || !Array.isArray(courses)
  ) {
    throw new Error('繁枝数据格式不正确');
  }
  return {
    grade_id: gradeId,
    grade_name: gradeName,
    has_courses: hasCourses,
    has_outline_content: hasOutlineContent,
    is_clickable: isClickable,
    current_course_id: currentCourseId,
    courses: courses.map(normalizeCourse),
  };
}

export async function fetchBranchOverview(token: string): Promise<BranchOverview> {
  const response = await fetch(`${API_BASE_URL}/api/branch/overview`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '繁枝数据加载失败');
  }

  const payload = (await response.json()) as {
    years: unknown;
    updated_at: string | null;
  };

  if (!isRecord(payload.years)) {
    throw new Error('繁枝数据格式不正确');
  }

  const years = Object.fromEntries(
    Object.entries(payload.years).map(([gradeId, year]) => [gradeId, normalizeYear(year)]),
  );

  return {
    years,
    updatedAt: payload.updated_at,
  };
}

export async function fetchCanopyOverview(token: string): Promise<CanopyOverview> {
  const response = await fetch(`${API_BASE_URL}/api/branch/canopy`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '成森数据加载失败');
  }

  const payload = (await response.json()) as {
    courses: unknown;
    growth_stage: unknown;
    completed_count: unknown;
    active_rate: unknown;
    avg_score: unknown;
    focused_hours: unknown;
    milestones: unknown;
    quality_scores: unknown;
  };

  if (
    !Array.isArray(payload.courses)
    || typeof payload.growth_stage !== 'number'
    || typeof payload.completed_count !== 'number'
    || typeof payload.active_rate !== 'number'
    || typeof payload.avg_score !== 'number'
    || typeof payload.focused_hours !== 'number'
    || !Array.isArray(payload.milestones)
  ) {
    throw new Error('成森数据格式不正确');
  }

  return {
    courses: payload.courses.map(normalizeCanopyCourse),
    growthStage: payload.growth_stage,
    completedCount: payload.completed_count,
    activeRate: payload.active_rate,
    avgScore: payload.avg_score,
    focusedHours: payload.focused_hours,
    milestones: payload.milestones.map(normalizeCanopyMilestone),
    qualityScores: normalizeQualityScores(payload.quality_scores),
  };
}
