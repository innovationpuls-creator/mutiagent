import ReactMarkdown from 'react-markdown';
import { Play, BookOpen, Lightbulb, CheckCircle2, FileText, LayoutDashboard } from 'lucide-react';
import type {
  LeafAnimationBlock,
  LeafComposedSection,
  LeafContentBlock,
  LeafSection,
  LeafVideoBlock,
} from '../../types/leaf';
import { getLeafSectionDescription, getLeafSectionHeading, getLeafSectionLabel } from './leafContentParser';

interface LeafContentProps {
  section: LeafSection | null;
  composedSection: LeafComposedSection | null;
  lockedReason: string | null;
}

function renderMarkdown(markdown: string, index: number) {
  return (
    <div className="flex flex-col md:flex-row gap-8" key={`markdown-${index}`}>
      <div className="flex-1 space-y-4">
        <ReactMarkdown
          components={{
            h1: ({ node, ...props }) => <h1 className="text-2xl font-bold text-[var(--color-text-primary)] mt-8 mb-4 tracking-tight" {...props} />,
            h2: ({ node, ...props }) => <h2 className="text-xl font-medium text-[var(--color-primary)] mt-8 mb-4 tracking-tight" {...props} />,
            h3: ({ node, ...props }) => <h3 className="text-lg font-medium text-[var(--color-text-primary)] mt-6 mb-2 tracking-tight" {...props} />,
            p: ({ node, ...props }) => <p className="text-base text-[var(--color-text-primary)] leading-relaxed mb-4" {...props} />,
            ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-6 text-[var(--color-text-primary)] marker:text-[var(--color-primary)]" {...props} />,
            ol: ({ node, ...props }) => <ol className="list-decimal pl-5 mb-6 text-[var(--color-text-primary)] marker:text-[var(--color-primary)]" {...props} />,
            li: ({ node, ...props }) => <li className="pl-1 mb-2 leading-relaxed" {...props} />,
            blockquote: ({ node, ...props }) => (
              <div className="bg-[var(--color-surface-raised)] p-4 md:p-6 rounded-xl border-l-4 border-[var(--color-primary)] my-8 shadow-sm">
                <blockquote className="text-base text-[var(--color-text-secondary)] italic m-0" {...props} />
              </div>
            ),
            code: ({ node, className, children, ...props }) => (
              <code className={className ? `${className} bg-[var(--color-surface-inset)] px-1.5 py-0.5 rounded text-[var(--color-secondary)] font-mono text-sm` : 'bg-[var(--color-surface-inset)] px-1.5 py-0.5 rounded text-[var(--color-secondary)] font-mono text-sm'} {...props}>
                {children}
              </code>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>

      {/* Side Callout Box - Optional contextual helper for reading mode */}
      <div className="md:w-64 shrink-0">
        <div className="bg-[var(--color-primary-soft)] p-6 rounded-xl shadow-[var(--shadow-sm)] border border-[var(--glass-border)] sticky top-6">
          <h4 className="font-medium text-sm text-[var(--color-primary)] mb-2 flex items-center gap-2">
            <Lightbulb className="w-4 h-4" /> Key Concept
          </h4>
          <p className="text-sm text-[var(--color-text-primary)] leading-relaxed opacity-90">
            This section explores foundational concepts that will be essential for the upcoming exercises and quizzes. Pay close attention to the terminology.
          </p>
        </div>
      </div>
    </div>
  );
}

function renderVideo(block: LeafVideoBlock, index: number) {
  const firstVideo = block.videos[0] ?? null;
  if (block.status !== 'available' || !firstVideo?.url) {
    return (
      <section className="bg-[var(--color-surface-raised)] p-6 rounded-xl border-2 border-dashed border-[var(--color-border)] opacity-70" key={`${block.brief_id}-${index}`}>
        <div className="flex flex-col items-center justify-center text-center py-8">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold mb-2">video</span>
          <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">{block.title}</h3>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-md">{block.purpose}</p>
          <div className="mt-4 px-4 py-2 bg-[var(--color-error-bg)] text-[var(--color-error)] text-xs rounded-full inline-flex items-center gap-2">
            视频资源暂时不可用
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-[var(--glass-bg)] backdrop-blur-md rounded-xl p-4 md:p-6 shadow-[var(--shadow-md)] border border-[var(--glass-border)] group" key={`${block.brief_id}-${index}`}>
      <div className="mb-4">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-primary)] font-bold mb-1 block">Video Resource</span>
        <h3 className="text-lg font-medium text-[var(--color-text-primary)]">{block.title}</h3>
        <p className="text-sm text-[var(--color-text-secondary)] mt-1">{block.purpose}</p>
      </div>

      <a href={firstVideo.url} target="_blank" rel="noreferrer" className="block relative w-full aspect-video rounded-lg overflow-hidden bg-[var(--color-surface-inset)] cursor-pointer group-hover:shadow-[var(--shadow-lg)] transition-shadow">
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="w-16 h-16 bg-[var(--color-surface-elevated)] backdrop-blur-sm rounded-full flex items-center justify-center shadow-lg group-hover:scale-110 group-hover:bg-[var(--color-primary-soft)] group-hover:text-[var(--color-primary)] transition-all duration-300">
            <Play className="w-8 h-8 ml-1 text-[var(--color-text-primary)] group-hover:text-[var(--color-primary)]" fill="currentColor" />
          </div>
        </div>

        {/* Abstract background for video placeholder since we don't have a real thumbnail */}
        <div className="w-full h-full bg-gradient-to-br from-[var(--color-secondary-soft)] to-[var(--color-primary-soft)] opacity-80" />

        <div className="absolute bottom-0 left-0 w-full p-4 bg-gradient-to-t from-black/60 to-transparent flex justify-between items-end">
          <div>
            <h3 className="font-medium text-sm text-white">{firstVideo.title || block.title}</h3>
            <p className="text-xs opacity-80 text-white mt-1 flex items-center gap-1">
              <Play className="w-3 h-3" /> External Resource
            </p>
          </div>
        </div>
      </a>
    </section>
  );
}

function renderAnimation(block: LeafAnimationBlock, index: number) {
  if (block.status !== 'available' || !block.html.trim()) {
    return (
      <section className="bg-[var(--color-surface-raised)] p-6 rounded-xl border-2 border-dashed border-[var(--color-border)] opacity-70" key={`${block.brief_id}-${index}`}>
        <div className="flex flex-col items-center justify-center text-center py-8">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold mb-2">animation</span>
          <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">{block.title}</h3>
          <div className="mt-4 px-4 py-2 bg-[var(--color-error-bg)] text-[var(--color-error)] text-xs rounded-full inline-flex items-center gap-2">
            动画暂时不可用
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-[var(--glass-bg)] backdrop-blur-md rounded-xl p-4 md:p-6 shadow-[var(--shadow-md)] border border-[var(--glass-border)]" key={`${block.brief_id}-${index}`}>
      <div className="mb-4">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-secondary)] font-bold mb-1 block">Interactive Canvas</span>
        <h3 className="text-lg font-medium text-[var(--color-text-primary)]">{block.title}</h3>
      </div>
      <div className="w-full aspect-[4/3] md:aspect-[16/9] min-h-[300px] border border-[var(--color-border)] rounded-xl overflow-hidden bg-[var(--color-surface-raised)] shadow-[var(--shadow-inset)] relative">
        <iframe
          title={block.title}
          className="w-full h-full absolute inset-0"
          sandbox="allow-scripts"
          srcDoc={block.html}
        />
      </div>
    </section>
  );
}

function renderContentBlock(block: LeafContentBlock, index: number) {
  if (block.type === 'markdown') return renderMarkdown(block.markdown, index);
  if (block.type === 'video') return renderVideo(block, index);
  return renderAnimation(block, index);
}

export function LeafContent({ section, composedSection, lockedReason }: LeafContentProps) {
  if (!section) {
    return (
      <article className="flex flex-col items-center justify-center text-center py-20 px-6 bg-[var(--glass-bg)] rounded-2xl border border-[var(--glass-border)] shadow-sm">
        <div className="w-16 h-16 rounded-full bg-[var(--color-surface-inset)] flex items-center justify-center mb-6">
          <LayoutDashboard className="w-8 h-8 text-[var(--color-text-muted)]" />
        </div>
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-bold mb-2">// empty</span>
        <h2 className="text-xl font-medium text-[var(--color-text-primary)] mb-2">课程章节还没有准备好</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">{lockedReason ?? '等待课程 Agent 生成章节结构。'}</p>
      </article>
    );
  }

  return (
    <article className="w-full flex flex-col">
      {/* Content Header */}
      <div className="mb-10">
        <div className="inline-flex items-center gap-2 bg-[var(--color-surface-raised)] px-4 py-1.5 rounded-full mb-6 border border-[var(--glass-border)] shadow-sm">
          <BookOpen className="w-4 h-4 text-[var(--color-primary)]" />
          <span className="text-xs font-bold text-[var(--color-primary)] uppercase tracking-wider">{getLeafSectionLabel(section.section_id)}</span>
        </div>
        <h1 className="text-3xl md:text-[40px] font-bold text-[var(--color-text-primary)] mb-4 tracking-tight leading-tight">{getLeafSectionHeading(section)}</h1>
        <p className="text-lg text-[var(--color-text-secondary)] max-w-2xl leading-relaxed">{getLeafSectionDescription(section)}</p>
      </div>

      {composedSection ? (
        <div className="flex flex-col gap-12">
          {composedSection.blocks.length > 0
            ? composedSection.blocks.map(renderContentBlock)
            : renderMarkdown(composedSection.markdown, 0)}

          {/* Interactive Quiz Tab Placeholder */}
          <section className="mt-8 bg-[var(--glass-bg)] rounded-xl shadow-[var(--shadow-md)] overflow-hidden border border-[var(--glass-border)]">
            <div className="flex border-b border-[var(--glass-border)] px-4 pt-2 bg-[var(--color-surface-raised)]/50">
              <button className="px-6 py-4 font-medium text-sm text-[var(--color-primary)] border-b-2 border-[var(--color-primary)] relative bg-transparent">
                Lesson Quiz
              </button>
              <button className="px-6 py-4 font-medium text-sm text-[var(--color-text-secondary)] hover:text-[var(--color-primary)] transition-colors bg-transparent">
                Chapter Review
              </button>
            </div>

            <div className="p-6 md:p-10">
              <div className="mb-8">
                <span className="inline-block px-3 py-1 bg-[var(--color-surface-inset)] text-[var(--color-text-secondary)] rounded text-[10px] font-bold uppercase tracking-wider mb-4 border border-[var(--glass-border)]">Question 1 of 3</span>
                <h3 className="text-xl font-medium text-[var(--color-text-primary)] leading-snug">What is the primary objective covered in this specific section?</h3>
              </div>

              <div className="space-y-3">
                <label className="flex items-center p-4 rounded-xl border-2 border-[var(--color-border)] hover:border-[var(--color-primary-soft)] bg-[var(--color-canvas-surface)] cursor-pointer transition-colors group">
                  <div className="w-5 h-5 rounded-full border-2 border-[var(--color-text-muted)] group-hover:border-[var(--color-primary-soft)] bg-transparent shrink-0"></div>
                  <span className="ml-4 text-base text-[var(--color-text-primary)] leading-relaxed">It provides a foundational overview.</span>
                </label>

                <label className="flex items-center p-4 rounded-xl border-2 border-[var(--color-primary)] bg-[var(--color-primary-soft)]/20 cursor-pointer transition-colors">
                  <div className="w-5 h-5 rounded-full border-2 border-[var(--color-primary)] bg-transparent shrink-0 flex items-center justify-center">
                    <div className="w-2.5 h-2.5 bg-[var(--color-primary)] rounded-full"></div>
                  </div>
                  <span className="ml-4 text-base text-[var(--color-text-primary)] font-medium leading-relaxed">To introduce practical applications of the theory.</span>
                </label>

                <label className="flex items-center p-4 rounded-xl border-2 border-[var(--color-border)] hover:border-[var(--color-primary-soft)] bg-[var(--color-canvas-surface)] cursor-pointer transition-colors group">
                  <div className="w-5 h-5 rounded-full border-2 border-[var(--color-text-muted)] group-hover:border-[var(--color-primary-soft)] bg-transparent shrink-0"></div>
                  <span className="ml-4 text-base text-[var(--color-text-primary)] leading-relaxed">It serves only as a historical reference.</span>
                </label>
              </div>

              <div className="mt-10 flex justify-end">
                <button className="bg-[var(--gradient-coral)] text-white hover:opacity-90 font-medium text-sm px-8 py-3 rounded-full transition-transform hover:scale-[1.02] active:scale-95 shadow-[var(--shadow-md)] flex items-center gap-2">
                  Submit Answer <CheckCircle2 className="w-4 h-4" />
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : (
        <section className="flex flex-col items-center justify-center text-center py-20 px-6 bg-[var(--color-surface-raised)] rounded-2xl border-2 border-dashed border-[var(--color-border)] opacity-80 mt-4">
          <div className="w-12 h-12 rounded-full bg-[var(--color-primary-soft)] flex items-center justify-center mb-6 shadow-sm">
            <FileText className="w-5 h-5 text-[var(--color-primary)]" />
          </div>
          <h3 className="text-xl font-medium text-[var(--color-text-primary)] mb-3">这一节还没有生成内容</h3>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-sm">可以从本章入口请 AI 生成 Markdown、视频资源和 HTML 动画。</p>
        </section>
      )}
    </article>
  );
}
