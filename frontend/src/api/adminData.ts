import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from './http';
import type { AuthUser } from '../types/auth';
import type { CultivationProgram } from './teacherProgram';

export interface DataOverview {
  accounts: Record<string, number>;
  cohorts: number;
  programs: number;
  learning_data: Record<string, number>;
}

export interface DataCohort {
  school: string;
  major: string;
  class_name: string;
  student_count: number;
  teacher_count: number;
  admin_count: number;
  has_program: boolean;
  program_teacher_name: string | null;
  program_updated_at: string | null;
}

export interface UserLearningData {
  user: AuthUser;
  profile: Record<string, unknown> | null;
  year_learning_paths: Record<string, unknown>[];
  course_outlines: Record<string, unknown>[];
  chapter_quizzes: Record<string, unknown>[];
  chapter_progress: Record<string, unknown>[];
  chapter_weaknesses: Record<string, unknown>[];
  resource_quality: Record<string, unknown>[];
  conversation_sessions: Record<string, unknown>[];
}

async function requestAdminData<TResponse>(
  token: string,
  path: string,
  init: RequestInit = {},
): Promise<TResponse> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init.body ? { 'Content-Type': 'application/json' } : {}),
      Authorization: `Bearer ${token}`,
      ...init.headers,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '数据管理操作失败');
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

export const adminDataApi = {
  overview(token: string) {
    return requestAdminData<DataOverview>(token, '/api/admin/data/overview');
  },
  cohorts(token: string) {
    return requestAdminData<DataCohort[]>(token, '/api/admin/data/cohorts');
  },
  programs(token: string) {
    return requestAdminData<CultivationProgram[]>(token, '/api/admin/data/programs');
  },
  userLearningData(token: string, uid: string) {
    return requestAdminData<UserLearningData>(token, `/api/admin/data/users/${uid}/learning-data`);
  },
  deleteUserLearningData(token: string, uid: string) {
    return requestAdminData<void>(token, `/api/admin/data/users/${uid}/learning-data`, {
      method: 'DELETE',
    });
  },
  deleteCohortProgram(token: string, cohort: Pick<DataCohort, 'school' | 'major' | 'class_name'>) {
    const school = encodeURIComponent(cohort.school);
    const major = encodeURIComponent(cohort.major);
    const className = encodeURIComponent(cohort.class_name);
    return requestAdminData<void>(token, `/api/admin/data/cohorts/${school}/${major}/${className}/program`, {
      method: 'DELETE',
    });
  },
};
