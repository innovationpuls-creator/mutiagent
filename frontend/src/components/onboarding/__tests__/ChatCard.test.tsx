import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { SessionMessage } from '../../../types/chat';
import { ChatCard } from '../ChatCard';

const generatedProfile: SessionMessage = {
  type: 'basic_profile',
  stage: 'generated',
  question_mode: 'none',
  confirmed_info: {
    current_grade: '大三',
    major: '软件工程',
    learning_stage: '',
    has_clear_goal: '',
    learning_method_preference: '项目制学习',
    learning_pace_preference: '',
    content_preference: ['案例', '代码'],
    need_guidance: '',
    knowledge_foundation: '',
    strengths: '',
    weaknesses: '',
    experience: '',
    short_term_goal: '完善个人项目',
    long_term_goal: '',
    weekly_available_time: '',
    constraints: '',
  },
  defaulted_fields: [],
  question_md: '',
  question_box: { question: '', options: [] },
  text: '【用户基础信息】\n你是大三软件工程学生，偏好通过项目推进学习。\n【学习建议】\n先围绕一个真实项目补齐工程能力。',
};

describe('ChatCard', () => {
  it('renders generated profile as structured readable sections', () => {
    render(<ChatCard message={generatedProfile} />);

    expect(screen.getByText('画像已整理成可继续更新的学习底稿')).toBeTruthy();
    expect(screen.getByText('已确认 5 项')).toBeTruthy();
    expect(screen.getByText('大三')).toBeTruthy();
    expect(screen.getByText('软件工程')).toBeTruthy();
    expect(screen.getByText('项目制学习')).toBeTruthy();
    expect(screen.getByText('案例、代码')).toBeTruthy();
    expect(screen.getAllByText('等待你继续补充。').length).toBeGreaterThan(0);
    expect(screen.getByText('先围绕一个真实项目补齐工程能力。')).toBeTruthy();
  });
});
