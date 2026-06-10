import styled from 'styled-components';

export const CardWrapper = styled.article`
  max-inline-size: min(100%, var(--container-narrow));
  inline-size: fit-content;
  align-self: flex-start;
  color: var(--color-text-primary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-24);
  box-shadow: var(--shadow-md);

  &[data-state='basic_profile'] {
    inline-size: min(100%, var(--container-default));
    background:
      radial-gradient(circle at 10% 0%, oklch(84% 0.12 63 / 0.22), transparent 34%),
      radial-gradient(circle at 100% 18%, oklch(75% 0.09 135 / 0.16), transparent 32%),
      var(--color-surface-raised);
    border-color: oklch(84% 0.03 73 / 0.76);
    box-shadow: var(--shadow-lg);
  }

  .card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--gap-sm);
    margin-block-end: var(--space-16);
  }

  .card-kicker,
  .card-state {
    font-size: var(--text-caption);
    line-height: 1.4;
    color: var(--color-text-secondary);
  }

  .card-state {
    display: inline-flex;
    align-items: center;
    gap: var(--space-8);
  }

  .card-state::before {
    content: '';
    inline-size: var(--space-8);
    block-size: var(--space-8);
    border-radius: var(--radius-full);
    background: var(--color-success);
  }

  h3,
  h4,
  p {
    margin: 0;
  }

  h3 {
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
  }

  h4 {
    font-size: var(--text-h6);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
    color: var(--color-text-secondary);
  }

  .confirmed-panel,
  .question-panel,
  .profile-section,
  .profile-hero,
  .profile-narrative section {
    border-radius: var(--radius-md);
    background: var(--color-surface-raised);
    padding: var(--space-16);
  }

  .confirmed-panel,
  .question-panel {
    display: grid;
    gap: var(--gap-sm);
  }

  .confirmed-list {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
  }

  .info-chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-8);
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .info-chip strong {
    color: var(--color-text-primary);
    font-weight: var(--font-weight-medium);
  }

  .info-chip[data-streaming='true'],
  .profile-section div[data-streaming='true'] {
    box-shadow: 0 0 6px var(--color-primary);
    animation: field-pulse 0.8s var(--ease-editorial) infinite alternate;
  }

  .muted-copy,
  .defaulted-note {
    color: var(--color-text-muted);
    font-size: var(--text-body-sm);
    line-height: 1.8;
  }

  .defaulted-note {
    margin-block: var(--space-12);
  }

  .question-panel {
    margin-block-start: var(--space-16);
  }

  .question-panel {
    display: grid;
    gap: var(--space-8);
  }

  .question-list p {
    color: var(--color-text-primary);
    line-height: 1.8;
  }

  .question-list p::before {
    content: '//';
    color: var(--color-primary);
    margin-inline-end: var(--space-8);
  }

  .question-list ul,
  .question-list ol {
    margin: 0;
    padding-inline-start: var(--space-24);
    color: var(--color-text-primary);
    line-height: 1.8;
  }

  .question-list li {
    margin-block-end: var(--space-4);
  }

  .options-grid {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-12);
    margin-block-start: var(--space-16);
  }

  .option-btn,
  .input-groove button {
    border: 1px solid var(--color-border);
    border-radius: var(--radius-full);
    background: var(--color-surface-inset);
    color: var(--color-text-primary);
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    cursor: pointer;
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  .option-btn {
    display: inline-flex;
    flex-direction: column;
    align-items: flex-start;
    gap: var(--space-4);
    min-block-size: 44px;
    padding: var(--space-12) var(--space-24);
    text-align: start;
  }

  .option-btn span {
    line-height: 1.4;
  }

  .option-btn small {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
    line-height: 1.5;
  }

  .option-btn:hover,
  .input-groove button:hover {
    transform: translateY(calc(var(--space-4) * -1));
  }

  .input-groove {
    display: flex;
    align-items: center;
    gap: var(--space-8);
    background: var(--color-surface-inset);
    box-shadow: var(--shadow-inset);
    border-radius: var(--radius-full);
    padding: var(--space-4);
    margin-block-start: var(--space-16);
  }

  .input-pebble {
    min-inline-size: 0;
    flex: 1;
    min-block-size: 0;
    background: transparent;
    border: none;
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    color: var(--color-text-primary);
    outline: none;
    padding-inline: var(--space-12);
  }

  .input-groove button {
    inline-size: var(--space-32);
    block-size: var(--space-32);
    min-inline-size: var(--space-32);
    min-block-size: var(--space-32);
    font-size: var(--text-h4);
    line-height: 1;
  }

  .option-btn:disabled,
  .input-pebble:disabled,
  .input-groove button:disabled {
    cursor: not-allowed;
    opacity: 0.64;
  }

  .profile-hero {
    display: grid;
    gap: var(--space-12);
    margin-block-end: var(--space-16);
    padding: var(--space-24);
  }

  .profile-hero h3 {
    font-size: var(--text-h3);
    color: var(--color-text-primary);
  }

  .profile-hero p,
  .profile-narrative p {
    color: var(--color-text-secondary);
    line-height: 1.9;
  }

  .profile-eyebrow {
    inline-size: fit-content;
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-primary-soft);
    color: var(--color-text-primary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .profile-meter {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
    margin-block-start: var(--space-4);
  }

  .profile-meter span {
    border-radius: var(--radius-full);
    padding: var(--space-8) var(--space-12);
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.4;
  }

  .profile-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--gap-sm);
  }

  .profile-section {
    display: grid;
    gap: var(--space-12);
    align-content: start;
    min-block-size: auto;
  }

  .profile-section dl {
    display: grid;
    gap: var(--space-8);
    margin: 0;
  }

  .profile-section div {
    display: grid;
    gap: var(--space-4);
  }

  .profile-section dt {
    color: var(--color-text-muted);
    font-size: var(--text-caption);
  }

  .profile-section dd {
    margin: 0;
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    line-height: 1.7;
  }

  .profile-section[data-empty='true'] {
    background: var(--color-background);
  }

  .profile-section[data-empty='true'] p {
    color: var(--color-text-muted);
    font-size: var(--text-body-sm);
    line-height: 1.8;
  }

  .profile-narrative {
    display: grid;
    gap: var(--space-12);
    margin-block-start: var(--space-16);
  }

  @media (max-width: 767px) {
    inline-size: 100%;
    max-inline-size: 100%;

    .profile-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .option-btn,
    .input-groove button {
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }

    .info-chip[data-streaming='true'],
    .profile-section div[data-streaming='true'] {
      animation: none;
    }

    .badge-dot {
      animation: none;
    }

    .cta-open-path-btn,
    .cta-open-path-btn .arrow {
      transition: none;
      transform: none;
    }
  }

  .profile-transition-banner {
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
    border-radius: var(--radius-md);
    background: var(--color-primary-soft);
    padding: var(--space-24) var(--space-20);
    margin-bottom: var(--space-16);
    border: 1px solid oklch(90% 0.04 140 / 0.3);
  }

  .completed-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-pill-padding);
    background: var(--color-surface);
    padding: var(--space-4) var(--space-12);
    border-radius: var(--radius-full);
    font-size: var(--text-caption);
    color: var(--color-text-secondary);
    border: 1px solid var(--color-border);
    margin-bottom: var(--space-16);
  }

  .badge-dot {
    width: 6px;
    height: 6px;
    background: var(--color-success);
    border-radius: var(--radius-full);
    box-shadow: 0 0 6px var(--color-success);
    animation: status-pulse 1.6s ease-in-out infinite alternate;
  }

  .sprout-avatar-container {
    display: flex;
    justify-content: center;
    margin-bottom: var(--space-12);
  }

  .sprout-orb {
    width: 72px;
    height: 72px;
    background: radial-gradient(circle, oklch(92% 0.06 140) 0%, oklch(98% 0.02 140) 100%);
    border-radius: var(--radius-full);
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: var(--shadow-sm);
  }

  .profile-transition-banner h3 {
    font-size: var(--text-h5);
    color: var(--color-text-primary);
    margin-bottom: var(--space-8);
  }

  .transition-explanation {
    font-size: var(--text-body-sm);
    color: var(--color-text-secondary);
    line-height: 1.6;
    margin-bottom: var(--space-16);
    text-wrap: pretty;
  }

  .cta-open-path-btn {
    width: 100%;
    max-width: 240px;
    padding: var(--space-8) var(--space-20);
    border: none;
    border-radius: var(--radius-full);
    background: var(--color-primary);
    color: var(--color-text-inverse);
    font-family: var(--font-body);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-pill-padding);
    box-shadow: var(--shadow-sm);
    transition: transform var(--duration-lazy-hover) var(--ease-lazy);
  }

  .cta-open-path-btn:hover {
    transform: translateY(-2px);
  }

  .cta-open-path-btn .arrow {
    transition: transform var(--duration-lazy-hover) var(--ease-lazy);
  }

  .cta-open-path-btn:hover .arrow {
    transform: translateX(4px);
  }

  @keyframes status-pulse {
    from { opacity: 0.4; }
    to { opacity: 1; }
  }

  @keyframes field-pulse {
    from { box-shadow: 0 0 4px var(--color-primary); }
    to { box-shadow: 0 0 12px var(--color-primary); }
  }
`;
