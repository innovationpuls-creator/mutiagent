import type { AuthUser } from '../types/auth';
import type { BranchCourseNode } from '../types/branch';

export const TEACHER_PROGRAM_SHARE_REGISTRY_KEY = 'teacher_cultivation_program_share_registry';
export const STUDENT_TEACHER_PROGRAM_BINDINGS_KEY = 'student_teacher_program_bindings';
export const TEACHER_PROGRAM_IMPORTED_EVENT = 'teacher-program-imported';

export interface TeacherProgramShareRecord {
  inviteCode: string;
  teacherUid: string;
  teacherName: string;
  teacherIdentifier: string;
  courses: BranchCourseNode[];
  publishedAt: string;
}

export interface StudentTeacherProgramBinding {
  studentUid: string;
  inviteCode: string;
  teacherUid: string;
  teacherName: string;
  importedAt: string;
}

type ShareRegistry = Record<string, TeacherProgramShareRecord>;
type StudentBindingRegistry = Record<string, StudentTeacherProgramBinding>;

type ImportTeacherProgramResult =
  | { ok: true; record: TeacherProgramShareRecord; binding: StudentTeacherProgramBinding }
  | { ok: false; message: string };

function readJsonObject(key: string): Record<string, unknown> {
  try {
    const stored = localStorage.getItem(key);
    if (!stored) return {};
    const parsed: unknown = JSON.parse(stored);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed)
      ? parsed as Record<string, unknown>
      : {};
  } catch {
    return {};
  }
}

function isBranchCourseNode(value: unknown): value is BranchCourseNode {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const course = value as Partial<BranchCourseNode>;
  return typeof course.course_node_id === 'string'
    && typeof course.course_or_chapter_theme === 'string'
    && typeof course.course_goal === 'string'
    && typeof course.status === 'string'
    && typeof course.has_outline === 'boolean';
}

function normalizeHumanProgramCourses(courses: BranchCourseNode[]): BranchCourseNode[] {
  return courses.map((course) => ({
    ...course,
    is_custom: true,
  }));
}

function isShareRecord(value: unknown): value is TeacherProgramShareRecord {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const record = value as Partial<TeacherProgramShareRecord>;
  return typeof record.inviteCode === 'string'
    && typeof record.teacherUid === 'string'
    && typeof record.teacherName === 'string'
    && typeof record.teacherIdentifier === 'string'
    && typeof record.publishedAt === 'string'
    && Array.isArray(record.courses)
    && record.courses.every(isBranchCourseNode);
}

function readShareRegistry(): ShareRegistry {
  const parsed = readJsonObject(TEACHER_PROGRAM_SHARE_REGISTRY_KEY);
  return Object.entries(parsed).reduce<ShareRegistry>((registry, [inviteCode, value]) => {
    if (isShareRecord(value)) {
      registry[inviteCode] = {
        ...value,
        courses: normalizeHumanProgramCourses(value.courses),
      };
    }
    return registry;
  }, {});
}

function writeShareRegistry(registry: ShareRegistry) {
  localStorage.setItem(TEACHER_PROGRAM_SHARE_REGISTRY_KEY, JSON.stringify(registry));
}

function readStudentBindings(): StudentBindingRegistry {
  const parsed = readJsonObject(STUDENT_TEACHER_PROGRAM_BINDINGS_KEY);
  return Object.entries(parsed).reduce<StudentBindingRegistry>((bindings, [studentUid, value]) => {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return bindings;
    const binding = value as Partial<StudentTeacherProgramBinding>;
    if (
      typeof binding.studentUid === 'string'
      && typeof binding.inviteCode === 'string'
      && typeof binding.teacherUid === 'string'
      && typeof binding.teacherName === 'string'
      && typeof binding.importedAt === 'string'
    ) {
      bindings[studentUid] = binding as StudentTeacherProgramBinding;
    }
    return bindings;
  }, {});
}

function writeStudentBindings(bindings: StudentBindingRegistry) {
  localStorage.setItem(STUDENT_TEACHER_PROGRAM_BINDINGS_KEY, JSON.stringify(bindings));
}

export function buildTeacherProgramInviteCode(user: Pick<AuthUser, 'uid' | 'identifier' | 'username'>): string {
  const seed = `${user.uid}|${user.identifier}|${user.username}`;
  let hash = 0;

  for (let index = 0; index < seed.length; index += 1) {
    hash = ((hash * 31) + seed.charCodeAt(index)) >>> 0;
  }

  return `OT-${hash.toString(36).toUpperCase().padStart(6, '0').slice(0, 6)}`;
}

export function publishTeacherProgramShare(
  teacher: AuthUser,
  courses: BranchCourseNode[],
  now: Date = new Date(),
): TeacherProgramShareRecord {
  const inviteCode = buildTeacherProgramInviteCode(teacher);
  const registry = readShareRegistry();
  const record: TeacherProgramShareRecord = {
    inviteCode,
    teacherUid: teacher.uid,
    teacherName: teacher.username,
    teacherIdentifier: teacher.identifier,
    courses: normalizeHumanProgramCourses(courses),
    publishedAt: now.toISOString(),
  };

  registry[inviteCode] = record;
  writeShareRegistry(registry);
  return record;
}

export function importTeacherProgramByCode(
  student: AuthUser,
  rawInviteCode: string,
  now: Date = new Date(),
): ImportTeacherProgramResult {
  const inviteCode = rawInviteCode.trim().toUpperCase();
  if (!inviteCode) {
    return { ok: false, message: '请输入教师口令。' };
  }

  const registry = readShareRegistry();
  const record = registry[inviteCode];
  if (!record) {
    return { ok: false, message: '没有找到这个教师口令对应的人培方案。' };
  }

  const bindings = readStudentBindings();
  const binding: StudentTeacherProgramBinding = {
    studentUid: student.uid,
    inviteCode: record.inviteCode,
    teacherUid: record.teacherUid,
    teacherName: record.teacherName,
    importedAt: now.toISOString(),
  };

  bindings[student.uid] = binding;
  writeStudentBindings(bindings);
  return { ok: true, record, binding };
}

export function getBoundTeacherProgramForStudent(studentUid: string): {
  binding: StudentTeacherProgramBinding;
  record: TeacherProgramShareRecord;
} | null {
  const binding = readStudentBindings()[studentUid];
  if (!binding) return null;

  const record = readShareRegistry()[binding.inviteCode];
  if (!record) return null;

  return { binding, record };
}
