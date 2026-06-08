import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Play, BookOpen, FileText, LayoutDashboard } from 'lucide-react';
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

// Helper to recursively extract text content from children
function getTextBlock(children: React.ReactNode): string {
  let text = '';
  React.Children.forEach(children, (child) => {
    if (typeof child === 'string' || typeof child === 'number') {
      text += child;
    } else if (React.isValidElement(child) && child.props && child.props.children) {
      text += getTextBlock(child.props.children);
    }
  });
  return text;
}

// Helper to recursively clean alert prefixes from strings
function cleanAlertPrefix(children: React.ReactNode): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === 'string') {
      return child.replace(/\[!(NOTE|IMPORTANT|WARNING|TIP|CAUTION)\]/g, '');
    }
    if (React.isValidElement(child) && child.props && child.props.children) {
      return React.cloneElement(child as React.ReactElement<any>, {
        children: cleanAlertPrefix(child.props.children),
      });
    }
    return child;
  });
}

function renderMarkdown(markdown: string, index: number) {
  return (
    <article className="prose prose-stone max-w-none prose-headings:text-[var(--color-text-primary)] prose-headings:font-medium prose-headings:tracking-normal prose-p:text-[var(--color-text-primary)] prose-a:text-[var(--color-primary)] prose-strong:text-[var(--color-text-primary)] mb-10" key={`markdown-${index}`}>
      <ReactMarkdown 
        remarkPlugins={[remarkGfm]}
        components={{
          h2: ({ node, ...props }) => (
            <h2 
              className="text-2xl font-medium border-l-4 border-[var(--color-primary)] pl-3 mt-8 mb-4 text-[var(--color-text-primary)]" 
              {...props} 
            />
          ),
          h3: ({ node, ...props }) => (
            <h3 
              className="text-lg font-medium bg-[var(--color-surface-raised)] border border-[var(--color-border)] p-3 rounded-lg mt-6 mb-3 text-[var(--color-text-primary)]" 
              {...props} 
            />
          ),
          blockquote: ({ node, ...props }) => {
            const contentText = getTextBlock(props.children);
            let alertClass = "border-l-4 border-gray-300 bg-gray-50/50";
            let alertLabel = "NOTE";
            
            if (contentText.includes("[!IMPORTANT]") || contentText.includes("[!CAUTION]")) {
              alertClass = "border-l-4 border-[var(--color-error)] bg-[var(--color-error-bg)] opacity-95";
              alertLabel = contentText.includes("[!IMPORTANT]") ? "IMPORTANT" : "CAUTION";
            } else if (contentText.includes("[!WARNING]")) {
              alertClass = "border-l-4 border-[var(--color-warning)] bg-[var(--color-surface-raised)]";
              alertLabel = "WARNING";
            } else if (contentText.includes("[!TIP]")) {
              alertClass = "border-l-4 border-[var(--color-primary)] bg-[var(--color-surface-raised)]";
              alertLabel = "TIP";
            } else if (contentText.includes("[!NOTE]")) {
              alertClass = "border-l-4 border-[var(--color-primary)] bg-[var(--color-surface-raised)]";
              alertLabel = "NOTE";
            }
            
            const cleanChildren = cleanAlertPrefix(props.children);
            
            return (
              <blockquote className={`p-4 my-4 rounded-r-lg ${alertClass} text-[var(--color-text-primary)]`} {...props}>
                <div className="text-[10px] font-semibold uppercase tracking-wider mb-2 opacity-70 flex items-center gap-1.5 text-[var(--color-text-whisper)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
                  {alertLabel}
                </div>
                <div>{cleanChildren}</div>
              </blockquote>
            );
          },
          table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-6 border border-[var(--color-border)] rounded-xl shadow-[var(--shadow-sm)]">
              <table className="w-full text-left border-collapse" {...props} />
            </div>
          ),
          th: ({ node, ...props }) => (
            <th className="bg-[var(--color-surface-raised)] border-b border-[var(--color-border)] p-3 text-sm font-semibold text-[var(--color-text-primary)]" {...props} />
          ),
          td: ({ node, ...props }) => (
            <td className="border-b border-[var(--color-border)] p-3 text-sm text-[var(--color-text-primary)]" {...props} />
          ),
          code: ({ node, className, children, ...props }) => {
            const inline = !className || !className.includes('language-');
            if (inline) {
              return (
                <code className="bg-[var(--color-surface-raised)] border border-[var(--color-border)] text-[var(--color-primary)] px-1.5 py-0.5 rounded font-mono text-xs" {...props}>
                  {children}
                </code>
              );
            }
            // Code block component
            const match = /language-(\w+)/.exec(className || '');
            const lang = match ? match[1] : 'code';
            const codeString = String(children).replace(/\n$/, '');
            return (
              <div className="my-6 rounded-xl border border-[var(--color-border)] overflow-hidden shadow-[var(--shadow-sm)]">
                <div className="bg-[var(--color-surface-raised)] border-b border-[var(--color-border)] px-4 py-2 flex justify-between items-center text-xs text-[var(--color-text-whisper)] font-mono">
                  <span>{lang.toUpperCase()}</span>
                  <button 
                    onClick={() => navigator.clipboard.writeText(codeString)}
                    className="hover:text-[var(--color-primary)] transition-colors px-2 py-0.5 border border-[var(--color-border)] rounded bg-[var(--color-surface-raised)] active:scale-95"
                  >
                    COPY
                  </button>
                </div>
                <pre className="p-4 bg-[var(--color-surface-inset)] overflow-x-auto text-sm font-mono text-[var(--color-text-primary)]">
                  <code {...props}>{children}</code>
                </pre>
              </div>
            );
          },
          li: ({ node, children, ...props }) => {
            // Check if it's a task checklist item
            const isCheckbox = node && node.properties && typeof node.properties.className === 'object' && (node.properties.className as string[]).includes('task-list-item');
            
            // Wait, react-markdown 10+ handles checkboxes by passing "checked" prop in props (we can destructure checked from props)
            const checked = (props as any).checked;
            if (checked !== undefined || isCheckbox) {
              return (
                <li className={`flex items-start gap-2.5 my-1.5 list-none ${checked ? 'opacity-65 line-through' : ''}`} {...props}>
                  <span className={`w-4 h-4 rounded mt-1 border flex items-center justify-center flex-shrink-0 transition-all ${
                    checked ? 'bg-[var(--color-primary)] border-[var(--color-primary)] text-white' : 'border-[var(--color-border)]'
                  }`}>
                    {checked && (
                      <svg className="w-2.5 h-2.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="4">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </span>
                  <div>{children}</div>
                </li>
              );
            }
            return <li className="my-1 text-[var(--color-text-primary)]" {...props}>{children}</li>;
          }
        }}
      >
        {markdown}
      </ReactMarkdown>
    </article>
  );
}

function renderVideo(block: LeafVideoBlock, index: number) {
  const firstVideo = block.videos[0] ?? null;
  if (block.status !== 'available' || !firstVideo?.url) {
    return (
      <section className="bg-[var(--color-surface-raised)] p-6 rounded-xl border-2 border-dashed border-[var(--color-border)] opacity-70" key={`${block.brief_id}-${index}`}>
        <div className="flex flex-col items-center justify-center text-center py-8">
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium mb-2">video</span>
          <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">{block.title}</h3>
          <p className="text-sm text-[var(--color-text-secondary)] max-w-md">{block.purpose}</p>
          <div className="mt-4 px-4 py-2 bg-[var(--color-error-bg)] text-[var(--color-error)] text-xs rounded-full inline-flex items-center gap-2">
            视频生成失败
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-[var(--glass-bg)] backdrop-blur-md rounded-2xl p-4 md:p-5 shadow-[var(--shadow-md)] border border-[var(--glass-border)] group" key={`${block.brief_id}-${index}`}>
      <a href={firstVideo.url} target="_blank" rel="noreferrer" className="block relative w-full aspect-video rounded-xl overflow-hidden bg-[var(--color-surface-inset)] cursor-pointer group-hover:shadow-[var(--shadow-lg)] transition-shadow">
        <div className="absolute inset-0 flex items-center justify-center z-10">
          <div className="w-16 h-16 bg-[var(--glass-bg)] backdrop-blur-sm rounded-full flex items-center justify-center shadow-lg group-hover:scale-110 group-hover:bg-[var(--color-primary-soft)] group-hover:text-[var(--color-primary)] transition-all duration-300">
            <Play className="w-8 h-8 ml-1 text-[var(--color-text-primary)] group-hover:text-[var(--color-primary)]" fill="currentColor" />
          </div>
        </div>

        <div className="w-full h-full bg-[var(--color-surface-raised)] opacity-80" />

        <div className="absolute bottom-0 left-0 w-full p-6 bg-[var(--glass-dark-bg)] flex justify-between items-end">
          <div>
            <h3 className="font-medium text-base text-white">{firstVideo.title || block.title}</h3>
            <p className="text-sm opacity-80 text-white mt-1 flex items-center gap-1">
              <Play className="w-3 h-3" /> 视频资源
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
          <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium mb-2">animation</span>
          <h3 className="text-lg font-medium text-[var(--color-text-primary)] mb-2">{block.title}</h3>
          <div className="mt-4 px-4 py-2 bg-[var(--color-error-bg)] text-[var(--color-error)] text-xs rounded-full inline-flex items-center gap-2">
            动画生成失败
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="bg-[var(--glass-bg)] backdrop-blur-md rounded-xl p-4 md:p-6 shadow-[var(--shadow-md)] border border-[var(--glass-border)]" key={`${block.brief_id}-${index}`}>
      <div className="mb-4">
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-secondary)] font-medium mb-1 block">Interactive Canvas</span>
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
        <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-muted)] font-medium mb-2">// empty</span>
        <h2 className="text-xl font-medium text-[var(--color-text-primary)] mb-2">课程章节还没有准备好</h2>
        <p className="text-sm text-[var(--color-text-secondary)]">{lockedReason ?? '等待课程 Agent 生成章节结构。'}</p>
      </article>
    );
  }

  return (
    <article className="w-full flex flex-col">
      {/* Content Header */}
      <div className="mb-10">
        <div className="inline-flex items-center gap-2 bg-[var(--color-surface-raised)] px-4 py-1.5 rounded-full mb-6 border border-[var(--glass-border)] shadow-[var(--shadow-sm)]">
          <BookOpen className="w-4 h-4 text-[var(--color-primary)]" />
          <span className="text-xs font-medium text-[var(--color-primary)] uppercase tracking-wider">{getLeafSectionLabel(section.section_id)}</span>
        </div>
        <h1 className="text-4xl md:text-5xl font-medium text-[var(--color-text-primary)] mb-4 tracking-normal leading-tight">{getLeafSectionHeading(section)}</h1>
        <p className="text-lg text-[var(--color-text-secondary)] max-w-2xl leading-relaxed">{getLeafSectionDescription(section)}</p>
      </div>

      {composedSection ? (
        <div className="flex flex-col gap-12">
          {composedSection.blocks.length > 0
            ? composedSection.blocks.map(renderContentBlock)
            : renderMarkdown(composedSection.markdown, 0)}
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
