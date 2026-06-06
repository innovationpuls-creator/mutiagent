import ReactMarkdown from 'react-markdown';
import type {
  LeafAnimationBlock,
  LeafComposedSection,
  LeafContentBlock,
  LeafSection,
  LeafVideoBlock,
} from '../../types/leaf';
import { getLeafSectionDescription, getLeafSectionHeading } from './leafContentParser';

interface LeafContentProps {
  section: LeafSection | null;
  composedSection: LeafComposedSection | null;
  lockedReason: string | null;
}

function renderMarkdown(markdown: string, index: number) {
  return (
    <div className="leaf-markdown" key={`markdown-${index}`}>
      <ReactMarkdown
        components={{
          h1: ({ node, ...props }) => <h1 className="leaf-markdown-h1" {...props} />,
          h2: ({ node, ...props }) => <h2 className="leaf-markdown-h2" {...props} />,
          h3: ({ node, ...props }) => <h3 className="leaf-markdown-h3" {...props} />,
          p: ({ node, ...props }) => <p className="leaf-markdown-p" {...props} />,
          ul: ({ node, ...props }) => <ul className="leaf-markdown-list" {...props} />,
          ol: ({ node, ...props }) => <ol className="leaf-markdown-list" {...props} />,
          li: ({ node, ...props }) => <li className="leaf-markdown-item" {...props} />,
          blockquote: ({ node, ...props }) => <blockquote className="leaf-markdown-quote" {...props} />,
          code: ({ node, className, children, ...props }) => (
            <code className={className ? `${className} leaf-markdown-code` : 'leaf-markdown-code'} {...props}>
              {children}
            </code>
          ),
        }}
      >
        {markdown}
      </ReactMarkdown>
    </div>
  );
}

function renderVideo(block: LeafVideoBlock, index: number) {
  const firstVideo = block.videos[0] ?? null;
  if (block.status !== 'available' || !firstVideo?.url) {
    return (
      <section className="leaf-resource leaf-resource-unavailable" key={`${block.brief_id}-${index}`}>
        <div>
          <span className="leaf-eyebrow">video</span>
          <h3>{block.title}</h3>
          <p>{block.purpose}</p>
        </div>
        <p className="leaf-resource-fallback">视频资源暂时不可用</p>
      </section>
    );
  }

  return (
    <section className="leaf-resource" key={`${block.brief_id}-${index}`}>
      <div>
        <span className="leaf-eyebrow">video</span>
        <h3>{block.title}</h3>
        <p>{block.purpose}</p>
      </div>
      <a href={firstVideo.url} target="_blank" rel="noreferrer">
        {firstVideo.title || block.title}
      </a>
    </section>
  );
}

function renderAnimation(block: LeafAnimationBlock, index: number) {
  if (block.status !== 'available' || !block.html.trim()) {
    return (
      <section className="leaf-resource leaf-resource-unavailable" key={`${block.brief_id}-${index}`}>
        <div>
          <span className="leaf-eyebrow">animation</span>
          <h3>{block.title}</h3>
        </div>
        <p className="leaf-resource-fallback">动画暂时不可用</p>
      </section>
    );
  }

  return (
    <section className="leaf-resource" key={`${block.brief_id}-${index}`}>
      <div>
        <span className="leaf-eyebrow">animation</span>
        <h3>{block.title}</h3>
      </div>
      <iframe
        title={block.title}
        className="leaf-animation-frame"
        sandbox="allow-scripts"
        srcDoc={block.html}
      />
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
      <article className="leaf-content leaf-content-empty">
        <span className="leaf-eyebrow">// empty</span>
        <h2>课程章节还没有准备好</h2>
        <p>{lockedReason ?? '等待课程 Agent 生成章节结构。'}</p>
      </article>
    );
  }

  return (
    <article className="leaf-content">
      <header className="leaf-content-header">
        <span className="leaf-eyebrow">reading leaf</span>
        <h2>{getLeafSectionHeading(section)}</h2>
        <p>{getLeafSectionDescription(section)}</p>
      </header>

      {composedSection ? (
        <div className="leaf-content-blocks">
          {composedSection.blocks.length > 0
            ? composedSection.blocks.map(renderContentBlock)
            : renderMarkdown(composedSection.markdown, 0)}
        </div>
      ) : (
        <section className="leaf-content-placeholder">
          <span aria-hidden="true">*</span>
          <h3>这一节还没有生成内容</h3>
          <p>可以从本章入口请 AI 生成 Markdown、视频资源和 HTML 动画。</p>
        </section>
      )}
    </article>
  );
}
