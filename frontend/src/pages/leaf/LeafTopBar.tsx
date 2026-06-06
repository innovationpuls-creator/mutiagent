import { useNavigate } from 'react-router-dom';
import type { LeafCourse, LeafGenerationStatus, LeafSection } from '../../types/leaf';
import { getLeafSectionHeading } from './leafContentParser';

interface LeafTopBarProps {
  course: LeafCourse;
  selectedSection: LeafSection | null;
  generationStatus: LeafGenerationStatus | null;
  liveGenerationMessage: string | null;
  canGenerate: boolean;
  onGenerate: () => void;
}

function courseStatusLabel(status: LeafCourse['status']): string {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'current':
      return '进行中';
    case 'locked':
      return '未开放';
  }
}

export function LeafTopBar({
  course,
  selectedSection,
  generationStatus,
  liveGenerationMessage,
  canGenerate,
  onGenerate,
}: LeafTopBarProps) {
  const navigate = useNavigate();
  const statusMessage = liveGenerationMessage ?? generationStatus?.message ?? null;
  const chapterId = selectedSection?.parent_section_id ?? selectedSection?.section_id ?? '1';

  return (
    <header className="leaf-topbar">
      <button type="button" className="leaf-back-button" onClick={() => navigate('/branch')}>
        <span aria-hidden="true">{'<'}</span>
        <span>返回路径</span>
      </button>

      <div className="leaf-topbar-title">
        <span className="leaf-eyebrow">leaf course</span>
        <h1>{course.course_or_chapter_theme}</h1>
        <p>{selectedSection ? getLeafSectionHeading(selectedSection) : course.course_goal}</p>
      </div>

      <div className="leaf-topbar-actions">
        <span className="leaf-course-status">{courseStatusLabel(course.status)}</span>
        {statusMessage ? (
          <span className="leaf-generation-pill" role="status">{statusMessage}</span>
        ) : null}
        <button
          type="button"
          className="leaf-quiz-button"
          onClick={() => navigate(`/forest/${encodeURIComponent(course.course_node_id)}?chapter_id=${encodeURIComponent(chapterId)}`)}
        >
          <span aria-hidden="true">//</span>
          <span>章节测验</span>
        </button>
        {canGenerate ? (
          <button type="button" className="leaf-generate-button" onClick={onGenerate}>
            <span aria-hidden="true">+</span>
            <span>让 AI 生成本章内容</span>
          </button>
        ) : null}
      </div>
    </header>
  );
}
