import React from 'react';
import styled from 'styled-components';

interface MessageBubbleProps {
  content: string;
}

export function MessageBubble({ content }: MessageBubbleProps) {
  return (
    <BubbleWrapper>
      <div className="bubble">
        <span className="avatar">U</span>
        <p className="text">{content}</p>
      </div>
    </BubbleWrapper>
  );
}

const BubbleWrapper = styled.article`
  display: flex;
  justify-content: flex-end;
  max-inline-size: min(100%, var(--container-narrow));
  inline-size: fit-content;
  align-self: flex-end;

  .bubble {
    display: flex;
    align-items: flex-start;
    gap: var(--space-12);
    background: oklch(86% 0.06 60 / 0.22);
    border: 1px solid oklch(82% 0.06 60 / 0.24);
    border-radius: var(--radius-lg);
    padding: var(--space-12) var(--space-16);
    box-shadow: var(--shadow-sm);
  }

  .avatar {
    inline-size: var(--space-32);
    block-size: var(--space-32);
    border-radius: var(--radius-full);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--text-caption);
    font-weight: var(--font-weight-medium);
    flex-shrink: 0;
  }

  .text {
    margin: 0;
    color: var(--color-text-primary);
    line-height: 1.6;
    font-size: var(--text-body);
    font-family: var(--font-body);
    align-self: center;
  }
`;
