import type { CourseKnowledgeResult, CourseKnowledgeSection } from '../../types/chat';

function cleanText(value: string | null | undefined): string {
  const text = (value ?? '').trim();
  if (!text) {
    return '';
  }
  const normalized = text.toLowerCase();
  if (normalized === 'none' || normalized === 'null') {
    return '';
  }
  return text;
}

function stripTopLevelTitlePrefix(title: string): string {
  if (!title) {
    return '';
  }
  const prefixes = ['第一章：', '第二章：', '第三章：', '第四章：', '第五章：', '第六章：', '第七章：', '第八章：', '第九章：', '第十章：'];
  const numericPattern = /^第\d+章：/;
  for (const prefix of prefixes) {
    if (title.startsWith(prefix)) {
      return title.slice(prefix.length).trim();
    }
  }
  if (numericPattern.test(title)) {
    return title.replace(numericPattern, '').trim();
  }
  return title;
}

export function getOutlineGradeLabel(outline: CourseKnowledgeResult): string {
  return cleanText(outline.grade_year) || '当前阶段';
}

export function getOutlineCourseName(outline: CourseKnowledgeResult): string {
  return cleanText(outline.course_name) || '课程大纲';
}

export function getOutlineSummary(outline: CourseKnowledgeResult): string {
  return cleanText(outline.personalization_summary) || '课程大纲已生成，等待进一步补充主线说明。';
}

export function getOutlineHours(outline: CourseKnowledgeResult): string {
  return cleanText(outline.total_estimated_hours) || '学时待补充';
}

export function getOrderedSections(outline: CourseKnowledgeResult): CourseKnowledgeSection[] {
  return [...outline.sections].sort((left, right) => left.order_index - right.order_index);
}

export function getChildSections(
  sections: CourseKnowledgeSection[],
  parentId: string | null,
): CourseKnowledgeSection[] {
  return sections
    .filter((section) => section.parent_section_id === parentId)
    .sort((left, right) => left.order_index - right.order_index);
}

export function getTopLevelSections(outline: CourseKnowledgeResult): CourseKnowledgeSection[] {
  return getChildSections(getOrderedSections(outline), null);
}

function toChineseChapterNumber(sectionId: string): string {
  const digits: Record<string, string> = {
    '0': '零',
    '1': '一',
    '2': '二',
    '3': '三',
    '4': '四',
    '5': '五',
    '6': '六',
    '7': '七',
    '8': '八',
    '9': '九',
  };
  const value = Number(sectionId);
  if (!Number.isInteger(value) || value <= 0) {
    return sectionId;
  }
  if (value < 10) {
    return digits[String(value)];
  }
  if (value === 10) {
    return '十';
  }
  if (value < 20) {
    return `十${digits[String(value % 10)]}`;
  }
  const tens = Math.floor(value / 10);
  const ones = value % 10;
  if (ones === 0) {
    return `${digits[String(tens)]}十`;
  }
  return `${digits[String(tens)]}十${digits[String(ones)]}`;
}

export function getSectionLabel(sectionId: string): string {
  return sectionId.includes('.') ? sectionId : `第${toChineseChapterNumber(sectionId)}章`;
}

export function getSectionHeading(section: CourseKnowledgeSection): string {
  const title = section.section_id.includes('.')
    ? cleanText(section.title)
    : stripTopLevelTitlePrefix(cleanText(section.title));
  const label = getSectionLabel(section.section_id);
  if (!title) {
    return label;
  }
  return section.section_id.includes('.') ? `${label} ${title}` : `${label}：${title}`;
}

export function getSectionDescription(section: CourseKnowledgeSection): string {
  return cleanText(section.description) || '围绕当前章节安排学习推进、实践验证与结果检查。';
}

export function getReadableLearningSequence(outline: CourseKnowledgeResult): string[] {
  const orderedSections = getOrderedSections(outline);
  const topLevelSections = getChildSections(orderedSections, null);
  const sectionMap = new Map(orderedSections.map((section) => [section.section_id, section]));
  const normalizedSequence = outline.learning_sequence
    .map((item) => cleanText(item))
    .filter((item) => item.length > 0);

  if (normalizedSequence.length === 0) {
    return topLevelSections.map((section) => getSectionHeading(section));
  }

  const allItemsAreIds = normalizedSequence.every((item) => sectionMap.has(item));
  if (allItemsAreIds) {
    return normalizedSequence.map((item) => {
      const section = sectionMap.get(item);
      return section ? getSectionHeading(section) : item;
    });
  }

  return normalizedSequence;
}
