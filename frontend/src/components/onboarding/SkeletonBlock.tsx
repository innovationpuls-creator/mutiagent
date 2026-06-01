import React from 'react';
import styled from 'styled-components';

interface SkeletonBlockProps {
  type: 'table' | 'heading' | 'paragraph' | 'code' | 'divider' | 'list';
}

const HEIGHT_MAP: Record<string, string> = {
  table: '140px',
  heading: '24px',
  paragraph: '50px',
  code: '120px',
  divider: '1px',
  list: '80px',
};

export function SkeletonBlock({ type }: SkeletonBlockProps) {
  const height = HEIGHT_MAP[type] || '50px';

  return <SkeletonWrapper style={{ height }} data-testid="skeleton-block" />;
}

const SkeletonWrapper = styled.div`
  border-radius: var(--radius-sm);
  margin: 14px 0;
  background: linear-gradient(90deg, oklch(90% 0.03 73 / 0.6) 25%, oklch(95% 0.02 75 / 0.8) 50%, oklch(90% 0.03 73 / 0.6) 75%);
  background-size: 200% 100%;
  animation: skeletonShimmer 1.4s ease-in-out infinite;

  @keyframes skeletonShimmer {
    0%   { background-position: 200% 0; }
    100% { background-position: -200% 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    animation: none;
  }
`;
