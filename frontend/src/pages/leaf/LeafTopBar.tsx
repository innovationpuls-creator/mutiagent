import { useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, PenTool, Sparkles } from 'lucide-react';
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
    <header className="flex flex-col xl:flex-row xl:items-center justify-between gap-6 p-5 bg-[var(--glass-bg)] backdrop-blur-md rounded-xl border border-[var(--glass-border)] shadow-[var(--shadow-sm)] w-full relative z-10">
      <div className="flex items-center gap-6">
        <button
          type="button"
          className="flex items-center justify-center w-10 h-10 rounded-full bg-[var(--color-surface-raised)] border border-[var(--glass-border)] text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] hover:-translate-y-[1px] hover:shadow-sm transition-all shrink-0"
          onClick={() => navigate('/branch')}
          title="返回路径"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>

        <div className="flex flex-col justify-center min-w-0">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold flex items-center gap-1.5 mb-1">
            <BookOpen className="w-3 h-3" /> leaf course
          </span>
          <h1 className="text-xl font-medium text-[var(--color-secondary)] truncate">{course.course_or_chapter_theme}</h1>
          <p className="text-sm text-[var(--color-text-secondary)] truncate mt-1">
            {selectedSection ? getLeafSectionHeading(selectedSection) : course.course_goal}
          </p>
        </div>
      </div>

      <div className="flex items-center flex-wrap gap-3 xl:justify-end">
        <span className="px-3 py-1.5 rounded-full bg-[var(--color-secondary-soft)] text-[var(--color-secondary)] text-xs font-medium border border-[var(--glass-border)]">
          {courseStatusLabel(course.status)}
        </span>

        {statusMessage ? (
          <span className="px-3 py-1.5 rounded-full bg-[oklch(93%_0.04_135)] text-[var(--color-text-primary)] text-xs font-medium border border-[var(--glass-border)] flex items-center gap-1.5" role="status">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse"></span>
            {statusMessage}
          </span>
        ) : null}

        <button
          type="button"
          className="px-4 py-2 rounded-full bg-[var(--color-surface-raised)] text-[var(--color-secondary)] text-sm font-medium border border-[var(--glass-border)] hover:-translate-y-[1px] hover:shadow-sm transition-all flex items-center gap-2"
          onClick={() => navigate(`/forest/${encodeURIComponent(course.course_node_id)}?chapter_id=${encodeURIComponent(chapterId)}`)}
        >
          <PenTool className="w-4 h-4" />
          <span>章节测验</span>
        </button>

        {canGenerate ? (
          <button
            type="button"
            className="px-5 py-2 rounded-full bg-[var(--gradient-coral)] text-white text-sm font-medium shadow-[var(--shadow-sm)] hover:-translate-y-[1px] hover:shadow-[var(--shadow-md)] transition-all flex items-center gap-2"
            onClick={onGenerate}
          >
            <Sparkles className="w-4 h-4" />
            <span>让 AI 生成本章内容</span>
          </button>
        ) : null}
      </div>
    </header>
  );
}
