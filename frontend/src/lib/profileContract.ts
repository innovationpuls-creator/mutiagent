import type { GradeId, SessionMessage } from '../types/chat';

const SUPPORTED_PROFILE_GRADE_TO_YEAR_ID: Record<string, GradeId> = {
  大一: 'year_1',
  大1: 'year_1',
  一年级: 'year_1',
  大二: 'year_2',
  大2: 'year_2',
  二年级: 'year_2',
  大三: 'year_3',
  大3: 'year_3',
  三年级: 'year_3',
  大四: 'year_4',
  大4: 'year_4',
  四年级: 'year_4',
};

export function profileYearIdFromCurrentGrade(currentGrade: string): GradeId | null {
  const normalized = currentGrade.trim();
  if (!normalized) {
    return null;
  }

  for (const [label, yearId] of Object.entries(SUPPORTED_PROFILE_GRADE_TO_YEAR_ID)) {
    if (normalized.includes(label)) {
      return yearId;
    }
  }

  return null;
}

export function isSupportedProfileCurrentGrade(currentGrade: unknown): boolean {
  return typeof currentGrade === 'string' && profileYearIdFromCurrentGrade(currentGrade) !== null;
}

export function hasCompleteBasicProfileRecord(
  profile: Record<string, unknown> | null,
  requiredKeys: readonly string[],
): boolean {
  if (!profile || profile.type !== 'basic_profile') return false;
  const confirmedInfo = profile.confirmed_info;
  if (!confirmedInfo || typeof confirmedInfo !== 'object') return false;
  if (!isSupportedProfileCurrentGrade((confirmedInfo as Record<string, unknown>).current_grade)) return false;
  return requiredKeys.every((key) => Object.prototype.hasOwnProperty.call(confirmedInfo, key));
}

export function hasCompleteBasicProfileSessionMessage(profile: SessionMessage | null | undefined): boolean {
  if (!profile || profile.type !== 'basic_profile') return false;
  return isSupportedProfileCurrentGrade(profile.confirmed_info.current_grade);
}
