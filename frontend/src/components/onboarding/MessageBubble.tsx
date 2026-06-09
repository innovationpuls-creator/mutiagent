import React from 'react';
import styled from 'styled-components';

interface MessageBubbleProps {
  content: string;
  imageAttachment?: string | null;
}

export function MessageBubble({ content, imageAttachment }: MessageBubbleProps) {
  return (
    <BubbleWrapper>
      <div className="bubble">
        <span className="avatar">U</span>
        <div className="bubble-content">
          {content && <p className="text">{content}</p>}
          {imageAttachment && (
            <div className="image-container">
              <img
                src={imageAttachment}
                alt="Attachment"
                className="bubble-image"
              />
            </div>
          )}
        </div>
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

  .bubble-content {
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  .image-container {
    border-radius: var(--radius-md);
    border: 1px solid var(--color-border);
    overflow: hidden;
    box-shadow: var(--shadow-sm);
    background: var(--color-surface);
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .bubble-image {
    display: block;
    max-block-size: 200px;
    max-inline-size: 100%;
    object-fit: contain;
  }

  .text {
    margin: 0;
    color: var(--color-text-primary);
    line-height: 1.6;
    font-size: var(--text-body);
    font-family: var(--font-body);
    align-self: flex-start;
  }
`;
