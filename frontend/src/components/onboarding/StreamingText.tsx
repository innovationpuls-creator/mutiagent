import React, { useMemo } from 'react';
import type { MessageStatus } from '../../types/chat';
import { SkeletonBlock } from './SkeletonBlock';
import { MarkdownRenderer } from '../markdown';

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
    return <MarkdownRenderer content={content} variant="compact" />;
  }

  if (blocks.length === 0) {
    return isStreaming ? <SkeletonBlock type="paragraph" /> : null;
  }

  return (
    <div>
      {blocks.map((block) => {
        if (!block.complete) {
          return <SkeletonBlock key={block.id} type={block.type} />;
        }

        return (
          <div key={block.id} data-block-type={block.type}>
            <MarkdownRenderer content={block.content} variant="compact" />
          </div>
        );
      })}
    </div>
  );
}
