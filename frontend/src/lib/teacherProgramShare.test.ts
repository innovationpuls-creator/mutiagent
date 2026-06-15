import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { AuthUser } from '../types/auth';
import type { BranchCourseNode } from '../types/branch';
import {
  buildTeacherProgramInviteCode,
  getBoundTeacherProgramForStudent,
  importTeacherProgramByCode,
  publishTeacherProgramShare,
  STUDENT_TEACHER_PROGRAM_BINDINGS_KEY,
  TEACHER_PROGRAM_SHARE_REGISTRY_KEY,
} from './teacherProgramShare';

const teacher: AuthUser = {
  uid: 'teacher-1',
  username: '测试教师',
  identifier: 'teacher@example.com',
  role: 'teacher',
  provider: 'password',
  is_active: true,
  created_at: '2026-06-02T00:00:00Z',
  last_login_at: null,
};

const student: AuthUser = {
  uid: 'student-1',
  username: '测试学生',
  identifier: 'student@example.com',
  role: 'student',
  provider: 'password',
  is_active: true,
  created_at: '2026-06-02T00:00:00Z',
  last_login_at: null,
};

const course: BranchCourseNode = {
  course_node_id: 'teacher_course_1',
  course_or_chapter_theme: '高等数学 I',
  course_goal: '教师发布的人培课程',
  status: 'locked',
  has_outline: false,
  is_custom: false,
  time_arrangement: { semester_scope: '1', duration: '64学时/4学分' },
};

describe('teacherProgramShare', () => {
  let store: Record<string, string>;

  beforeEach(() => {
    store = {};
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] ?? null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
      clear: vi.fn(() => {
        store = {};
      }),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('publishes a fixed teacher invite code and stores courses as human-program courses', () => {
    const inviteCode = buildTeacherProgramInviteCode(teacher);

    const record = publishTeacherProgramShare(teacher, [course], new Date('2026-06-15T10:00:00Z'));

    expect(record.inviteCode).toBe(inviteCode);
    expect(record.teacherUid).toBe('teacher-1');
    expect(record.teacherName).toBe('测试教师');
    expect(record.publishedAt).toBe('2026-06-15T10:00:00.000Z');

    const registry = JSON.parse(store[TEACHER_PROGRAM_SHARE_REGISTRY_KEY]);
    expect(registry[inviteCode].courses[0].course_node_id).toBe('teacher_course_1');
    expect(registry[inviteCode].courses[0].is_custom).toBe(true);
  });

  it('binds a student to the teacher program by invite code and reads the bound program later', () => {
    const record = publishTeacherProgramShare(teacher, [course], new Date('2026-06-15T10:00:00Z'));

    const result = importTeacherProgramByCode(student, ` ${record.inviteCode.toLowerCase()} `, new Date('2026-06-15T11:00:00Z'));

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.record.inviteCode).toBe(record.inviteCode);

    const bindings = JSON.parse(store[STUDENT_TEACHER_PROGRAM_BINDINGS_KEY]);
    expect(bindings['student-1'].inviteCode).toBe(record.inviteCode);
    expect(bindings['student-1'].teacherName).toBe('测试教师');
    expect(bindings['student-1'].importedAt).toBe('2026-06-15T11:00:00.000Z');

    const boundProgram = getBoundTeacherProgramForStudent('student-1');
    expect(boundProgram?.binding.teacherUid).toBe('teacher-1');
    expect(boundProgram?.record.courses[0].is_custom).toBe(true);
  });

  it('returns a clear error when the invite code does not match a published program', () => {
    const result = importTeacherProgramByCode(student, 'OT-NONE1');

    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.message).toBe('没有找到这个教师口令对应的人培方案。');
  });
});
