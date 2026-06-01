import React, { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import styled from 'styled-components';
import type { MessageStatus } from '../../types/chat';
import { SkeletonBlock } from './SkeletonBlock';

interface StreamingBlock {
  id: string;
  type: 'paragraph' | 'table' | 'heading' | 'divider' | 'code' | 'list';
  content: string;
  complete: boolean;
}

interface StreamingTextProps {
  content: string;
  status: MessageStatus;
}

function detectBlockType(block: string): StreamingBlock['type'] {
  const trimmed = block.trim();
  if (
    /^\|.*\|/.test(trimmed) &&
    /^\|[-| :]+\|/.test(trimmed.split('\n')[1] || '')
  ) {
    return 'table';
  }
  if (/^```/.test(trimmed)) return 'code';
  if (/^#{1,4}\s/.test(trimmed)) return 'heading';
  if (/^(---|\*\*\*|___)$/.test(trimmed)) return 'divider';
  if (/^[\s]*[-*+]\s/.test(trimmed) || /^[\s]*\d+[.)]\s/.test(trimmed))
    return 'list';
  return 'paragraph';
}

function stableBlockId(content: string, index: number): string {
  let hash = 0;
  for (let i = 0; i < Math.min(content.length, 80); i++) {
    hash = ((hash << 5) - hash + content.charCodeAt(i)) | 0;
  }
  return `block-${index}-${hash}`;
}

export function StreamingText({ content, status }: StreamingTextProps) {
  const isStreaming = status === 'streaming' || status === 'pending';

  const blocks = useMemo(() => {
    const rawBlocks = content.split(/\n\n/);
    return rawBlocks
      .filter((b) => b.trim().length > 0)
      .map((blockContent, i) => ({
        id: stableBlockId(blockContent, i),
        type: detectBlockType(blockContent),
        content: blockContent,
        complete: !isStreaming || i < rawBlocks.length - 1,
      }));
  }, [content, isStreaming]);

  if (status === 'pending' && !content) return null;

  if (status === 'error' && content) {
    return (
      <MarkdownBody>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
      </MarkdownBody>
    );
  }

  if (blocks.length === 0) {
    return isStreaming ? <SkeletonBlock type="paragraph" /> : null;
  }

  return (
    <MarkdownBody>
      {blocks.map((block) => {
        if (!block.complete) {
          return <SkeletonBlock key={block.id} type={block.type} />;
        }

        return (
          <div key={block.id} data-block-type={block.type}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.content}</ReactMarkdown>
          </div>
        );
      })}
    </MarkdownBody>
  );
}

const MarkdownBody = styled.div`
  color: var(--color-text-primary);
  line-height: 1.75;
  font-size: var(--text-body);
  font-family: var(--font-body);
  overflow-wrap: break-word;

  p {
    margin: 0 0 var(--space-12);
    &:last-child {
      margin-bottom: 0;
    }
  }

  p:first-of-type {
    font-size: var(--text-body);
    line-height: 1.7;
    color: var(--color-text-secondary);
  }

  h1, h2, h3, h4 {
    font-family: var(--font-heading);
    font-weight: var(--font-weight-medium);
    color: var(--color-text-primary);
  }

  h1 { font-size: var(--text-h2); line-height: 1.2; margin: var(--space-32) 0 var(--space-8); }
  h2 { font-size: var(--text-h3); line-height: 1.25; margin: var(--space-24) 0 var(--space-8); }
  h3 { font-size: var(--text-h4); line-height: 1.3; margin: var(--space-16) 0 var(--space-8); }

  em {
    font-style: italic;
    color: var(--color-primary);
  }

  strong {
    font-weight: var(--font-weight-medium);
    color: var(--color-text-primary);
  }

  blockquote {
    margin: var(--space-24) 0;
    padding: 0 0 0 var(--space-16);
    border-left: 2px solid oklch(78% 0.12 55 / 0.5);
    background: none;
    color: var(--color-text-secondary);
    font-family: var(--font-heading);
    font-size: var(--text-body);
    line-height: 1.7;
    font-style: normal;
  }

  ul, ol {
    margin: 0 0 var(--space-12);
    padding-left: var(--space-24);
  }

  li {
    margin: var(--space-8) 0;
  }

  hr {
    margin: var(--space-24) 0;
    border: none;
    height: 1px;
    background: linear-gradient(to right, oklch(78% 0.12 55 / 0.2), transparent);
  }

  pre {
    background: oklch(20% 0.04 235);
    color: oklch(92% 0.025 75);
    padding: var(--space-12);
    border-radius: var(--radius-md);
    overflow-x: auto;
    margin: var(--space-16) 0;
    font-family: var(--font-mono);
    font-size: var(--text-caption);
    line-height: 1.45;
  }

  code {
    background: var(--color-surface-inset);
    color: var(--color-primary);
    padding: 2px 4px;
    border-radius: var(--radius-sm);
    font-size: 0.9em;
    font-family: var(--font-mono);
  }

  pre code {
    background: transparent;
    color: inherit;
    padding: 0;
    border-radius: 0;
    font-size: inherit;
  }

  a {
    color: var(--color-primary);
    text-decoration: none;
    &:hover { text-decoration: underline; }
  }

  table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: var(--space-16) 0;
    border-radius: var(--radius-md);
    overflow: hidden;
    border: 1px solid var(--color-border);
  }

  th {
    background: oklch(84% 0.03 73 / 0.6);
    padding: var(--space-12) var(--space-16);
    text-align: left;
    font-weight: var(--font-weight-medium);
    font-size: var(--text-body-sm);
    border-bottom: 1px solid var(--color-border);
  }

  td {
    padding: var(--space-8) var(--space-16);
    border-bottom: 1px solid var(--color-border);
    font-size: var(--text-body-sm);
  }

  tr:last-child td {
    border-bottom: none;
  }

  tr:nth-child(even) td {
    background: oklch(90% 0.03 73 / 0.3);
  }
`;
