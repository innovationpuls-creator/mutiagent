import type { BranchOverview, BranchYear, BranchCourseNode, BranchCourseStatus } from '../types/branch';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface ApiErrorResponse {
  detail?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object';
}

function isStatus(value: unknown): value is BranchCourseStatus {
  return value === 'completed' || value === 'current' || value === 'locked';
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
    const error = (await response.json().catch(() => null)) as ApiErrorResponse | null;
    throw new Error(error?.detail ?? '繁枝数据加载失败');
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
