import type { SessionAgentEvent } from '../../api/orchestration';

export const LEAF_GENERATION_EVENT = 'mutiagent-leaf-generation-event';
export const LEAF_GENERATION_COMPLETED_EVENT = 'mutiagent-leaf-generation-completed';

export interface LeafGenerationEventDetail {
  courseId: string;
  chapterSectionId: string;
  sectionId: string | null;
  phase: string;
  status: string;
  message: string;
}

export function dispatchLeafGenerationEvent(event: SessionAgentEvent) {
  if (!event.course_id || !event.chapter_section_id) return;
  if (event.kind !== 'course_resource_section' && event.kind !== 'course_resource_chapter') return;
  window.dispatchEvent(new CustomEvent<LeafGenerationEventDetail>(LEAF_GENERATION_EVENT, {
    detail: {
      courseId: event.course_id,
      chapterSectionId: event.chapter_section_id,
      sectionId: event.section_id ?? null,
      phase: event.phase ?? '',
      status: event.status ?? '',
      message: event.message ?? event.summary ?? '',
    },
  }));
}

export function dispatchLeafGenerationCompleted(courseId: string) {
  window.dispatchEvent(new CustomEvent(LEAF_GENERATION_COMPLETED_EVENT, { detail: { courseId } }));
}
