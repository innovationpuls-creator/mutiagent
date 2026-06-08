import type { LeafCourse, LeafSection } from '../../types/leaf';

type LeafGenerationChapter = Pick<LeafSection, 'section_id' | 'title'>;
type LeafGenerationMode = 'generate' | 'regenerate';

export function buildLeafGenerationPrompt(
  course: LeafCourse,
  chapter: LeafGenerationChapter,
  mode: LeafGenerationMode = 'generate',
): string {
  return [
    `帮我生成《${course.course_or_chapter_theme}》${chapter.title}的教学内容。`,
    '',
    '[LEAF_RESOURCE_GENERATION]',
    `course_node_id: ${course.course_node_id}`,
    `chapter_section_id: ${chapter.section_id}`,
    'scope: chapter_sections',
    `mode: ${mode}`,
    '[/LEAF_RESOURCE_GENERATION]',
    '',
    '要求：生成这一章所有叶子小节的 Markdown、视频资源、HTML 动画，并拼装保存。',
  ].join('\n');
}

export function buildCourseOutlineGenerationPrompt(course: LeafCourse): string {
  return `帮我生成《${course.course_or_chapter_theme}》的大纲`;
}
