import { render, screen, within } from '@testing-library/react';
import React from 'react';
import { expect, test } from 'vitest';
import type { AgentRunStep } from '../../../types/chat';
import { AgentCollaborationPanel } from '../AgentCollaborationPanel';
import { buildAgentCollaborationNodes } from '../agentCollaboration';

test('builds ordered Agent nodes from timeline steps', () => {
  const steps: AgentRunStep[] = [
    {
      stepId: 'learning-path',
      kind: 'agent',
      status: 'running',
      title: '学习路径智能体',
      summary: '正在拆解四年学习路径',
      agent: 'learning_path_agent',
      dependsOn: ['profile_agent'],
      parallelGroup: 'path',
      startedAtMs: 1000,
    },
    {
      stepId: 'profile',
      kind: 'agent',
      status: 'success',
      title: '画像智能体',
      summary: '画像已生成',
      agent: 'profile_agent',
      durationMs: 1200,
    },
  ];

  const nodes = buildAgentCollaborationNodes(steps);

  expect(nodes.map((node) => node.agent)).toEqual(['profile_agent', 'learning_path_agent']);
  expect(nodes[0].status).toBe('success');
  expect(nodes[1].status).toBe('running');
  expect(nodes[1].inputSummary).toBe('输入来自：profile_agent');
  expect(nodes[1].parallelGroup).toBe('path');
});

test('trims Agent ids before ordering and dependency labels', () => {
  const steps: AgentRunStep[] = [
    {
      stepId: 'custom',
      kind: 'agent',
      status: 'success',
      title: '自定义智能体',
      summary: '自定义智能体已完成',
      agent: 'custom_agent',
    },
    {
      stepId: 'learning-path',
      kind: 'agent',
      status: 'success',
      title: '学习路径智能体',
      agent: ' learning_path_agent ',
    },
  ];

  const nodes = buildAgentCollaborationNodes(steps);

  expect(nodes.map((node) => node.agent)).toEqual(['learning_path_agent', 'custom_agent']);
  expect(nodes[0].inputSummary).toBe('等待画像完成');
});

test('renders each Agent as a status column with input and output summaries', () => {
  const steps: AgentRunStep[] = [
    {
      stepId: 'profile',
      kind: 'agent',
      status: 'success',
      title: '画像智能体',
      summary: '画像已生成',
      agent: 'profile_agent',
      durationMs: 1200,
    },
    {
      stepId: 'learning-path',
      kind: 'agent',
      status: 'running',
      title: '学习路径智能体',
      summary: '正在拆解四年学习路径',
      agent: 'learning_path_agent',
      dependsOn: ['profile_agent'],
      parallelGroup: 'path',
      startedAtMs: 1000,
    },
  ];

  render(<AgentCollaborationPanel steps={steps} />);

  const panel = screen.getByTestId('agent-collaboration-panel');
  expect(within(panel).getByText('协作编排现场')).toBeTruthy();

  const profileColumn = screen.getByTestId('agent-column-profile_agent');
  expect(profileColumn.getAttribute('data-status')).toBe('success');
  expect(within(profileColumn).getByText('画像已生成')).toBeTruthy();

  const pathColumn = screen.getByTestId('agent-column-learning_path_agent');
  expect(pathColumn.getAttribute('data-status')).toBe('running');
  expect(within(pathColumn).getByText('输入来自：profile_agent')).toBeTruthy();
  expect(within(pathColumn).getByText('path')).toBeTruthy();
});

test('renders failed Agent results as retry-worthy failure state', () => {
  const steps: AgentRunStep[] = [
    {
      stepId: 'video',
      kind: 'agent',
      status: 'error',
      title: '视频搜索智能体',
      summary: '视频资源质量不合格。',
      agent: 'section_video_search_agent',
      dependsOn: ['section_markdown_agent'],
      durationMs: 900,
    },
  ];

  render(<AgentCollaborationPanel steps={steps} />);

  const videoColumn = screen.getByTestId('agent-column-section_video_search_agent');
  expect(videoColumn.getAttribute('data-status')).toBe('error');
  expect(within(videoColumn).getByText('失败重试')).toBeTruthy();
  expect(within(videoColumn).getByText('视频资源质量不合格。')).toBeTruthy();
});
