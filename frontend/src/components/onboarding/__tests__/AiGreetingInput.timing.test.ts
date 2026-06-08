import { expect, test } from 'vitest';
import type { SessionAgentEvent } from '../../../api/orchestration';
import {
  getSessionEventStartTime,
  rememberSessionEventStartTime,
} from '../AiGreetingInput';

test('matches section progress and result timing by structured event fields when step ids differ', () => {
  const starts: Record<string, number> = {};
  const progress: SessionAgentEvent = {
    event: 'agent_progress',
    stepId: 'leaf-section-1.1',
    kind: 'course_resource_section',
    agent: 'section_markdown_agent',
    label: '1.1 小节智能体',
    message: '正在生成文案，并写入视频与动画占位要求',
    course_id: 'year_3_course_1',
    chapter_section_id: '1',
    section_id: '1.1',
    phase: 'markdown',
    status: 'running',
  };
  const result: SessionAgentEvent = {
    event: 'agent_result',
    stepId: 'leaf-section-1.1-markdown',
    kind: 'course_resource_section',
    agent: 'section_markdown_agent',
    label: '1.1 文案',
    summary: '文案与资源 brief 已生成，正在交接给视频和动画智能体',
    course_id: 'year_3_course_1',
    chapter_section_id: '1',
    section_id: '1.1',
    phase: 'markdown',
    status: 'completed',
    success: true,
  };

  rememberSessionEventStartTime(starts, progress, 1000);

  expect(getSessionEventStartTime(starts, result, 46000)).toBe(1000);
});

test('keeps parallel section resource timings from falling back to previous result time', () => {
  const starts: Record<string, number> = {};
  const sectionIds = ['1.1', '1.2', '1.3'];
  const progressEvents = sectionIds.map<SessionAgentEvent>((sectionId) => ({
    event: 'agent_progress',
    stepId: `leaf-section-${sectionId}-resources`,
    kind: 'course_resource_section',
    agent: 'section_resource_agents',
    label: `${sectionId} 资源`,
    message: '视频检索和 HTML 动画生成正在推进',
    course_id: 'year_3_course_1',
    chapter_section_id: '1',
    section_id: sectionId,
    phase: 'resources',
    status: 'running',
  }));
  const resultEvents = sectionIds.map<SessionAgentEvent>((sectionId) => ({
    event: 'agent_result',
    stepId: `leaf-section-${sectionId}-resources`,
    kind: 'course_resource_section',
    agent: 'section_resource_agents',
    label: `${sectionId} 资源`,
    summary: '视频、动画与正文已拼装保存',
    course_id: 'year_3_course_1',
    chapter_section_id: '1',
    section_id: sectionId,
    phase: 'compose',
    status: 'completed',
    success: true,
  }));

  progressEvents.forEach((event) => rememberSessionEventStartTime(starts, event, 2000));

  expect(getSessionEventStartTime(starts, resultEvents[0], 318000)).toBe(2000);
  expect(getSessionEventStartTime(starts, resultEvents[1], 318010)).toBe(2000);
  expect(getSessionEventStartTime(starts, resultEvents[2], 318020)).toBe(2000);
});
