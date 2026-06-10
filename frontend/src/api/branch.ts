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

function normalizeCanopyStatus(value: unknown): CanopyCourseStatus {
  if (value === 'completed' || value === 'locked') {
    return value;
  }
  if (value === 'current') {
    return 'in_progress';
  }
  throw new Error('成森数据格式不正确');
}

function normalizeCourse(value: unknown): BranchCourseNode {
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
  return {
    course_node_id: courseId,
    course_or_chapter_theme: theme,
    course_goal: goal,
    status,
    has_outline: hasOutline,
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
    || !Array.isArray(prerequisiteIds)
    || prerequisiteIds.some((item) => typeof item !== 'string')
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
  };
}
