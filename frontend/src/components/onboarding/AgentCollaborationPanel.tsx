import React from 'react';
import styled from 'styled-components';
import type { AgentRunStep } from '../../types/chat';
import { buildAgentCollaborationNodes } from './agentCollaboration';

interface AgentCollaborationPanelProps {
  steps: AgentRunStep[];
}

const STATUS_LABELS = {
  waiting: '等待中',
  running: '运行中',
  success: '已完成',
  error: '失败重试',
  skipped: '已跳过',
} as const;

function formatDuration(ms?: number): string {
  if (typeof ms !== 'number' || Number.isNaN(ms) || ms <= 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

export function AgentCollaborationPanel({ steps }: AgentCollaborationPanelProps) {
  const nodes = buildAgentCollaborationNodes(steps);
  if (nodes.length === 0) return null;

  return (
    <Shell aria-label="Agent collaboration panel" data-testid="agent-collaboration-panel">
      <div className="panel-head">
        <span className="eyebrow">multi-agent</span>
        <strong>协作编排现场</strong>
      </div>
      <div className="agent-grid">
        {nodes.map((node) => (
          <article
            key={node.agent}
            className="agent-column"
            data-status={node.status}
            data-testid={`agent-column-${node.agent}`}
          >
            <div className="agent-topline">
              <span className="status-dot" aria-hidden="true" />
              <span className="status-label">{STATUS_LABELS[node.status]}</span>
              {node.parallelGroup && <span className="parallel-label">{node.parallelGroup}</span>}
            </div>
            <h3>{node.label}</h3>
            <dl>
              <div>
                <dt>输入</dt>
                <dd>{node.inputSummary}</dd>
              </div>
              <div>
                <dt>输出</dt>
                <dd>{node.outputSummary}</dd>
              </div>
            </dl>
            <div className="agent-meta">
              <span>{node.stepCount} 步</span>
              {formatDuration(node.durationMs) && <span>{formatDuration(node.durationMs)}</span>}
            </div>
          </article>
        ))}
      </div>
    </Shell>
  );
}

const Shell = styled.section`
  padding: var(--space-12);
  border-bottom: 1px solid var(--dark-border);

  .panel-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: var(--space-12);
    margin-bottom: var(--space-12);
  }

  .eyebrow {
    color: var(--dark-text-muted);
    font-family: var(--font-mono);
    font-size: var(--text-caption);
  }

  .panel-head strong {
    color: var(--dark-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
  }

  .agent-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
    gap: var(--space-8);
  }

  .agent-column {
    min-width: 0;
    padding: var(--space-12);
    border: 1px solid var(--dark-border);
    border-radius: var(--radius-md);
    background: var(--dark-surface-elevated);
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  .agent-topline,
  .agent-meta {
    display: flex;
    align-items: center;
    gap: var(--space-8);
    color: var(--dark-text-muted);
    font-size: var(--text-caption);
  }

  .status-dot {
    width: 0.5rem;
    height: 0.5rem;
    border-radius: 999px;
    background: var(--dark-text-muted);
    flex: 0 0 auto;
  }

  .agent-column[data-status='running'] .status-dot {
    background: var(--status-running);
  }

  .agent-column[data-status='success'] .status-dot {
    background: var(--status-running);
  }

  .agent-column[data-status='error'] .status-dot {
    background: var(--status-error);
  }

  .parallel-label {
    margin-left: auto;
    font-family: var(--font-mono);
  }

  h3 {
    color: var(--dark-text-primary);
    font-size: var(--text-body-sm);
    line-height: 1.35;
    font-weight: var(--font-weight-medium);
    margin: 0;
    word-break: break-word;
  }

  dl {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-8);
  }

  dt {
    color: var(--dark-text-muted);
    font-size: var(--text-caption);
  }

  dd {
    margin: 0;
    color: var(--dark-text-secondary);
    font-size: var(--text-caption);
    line-height: 1.45;
    word-break: break-word;
  }

`;
