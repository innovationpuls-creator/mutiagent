import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SessionMessage } from '../../../types/chat';
import { ChatCard } from '../ChatCard';

const mockNavigate = vi.fn();
const mockSetWidgetState = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('../../../context/AiWidgetContext', () => ({
  useAiWidget: () => ({
    setWidgetState: mockSetWidgetState,
  }),
}));

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

const questionProfile: SessionMessage = {
  type: 'collecting',
  stage: 'basic_info',
  question_mode: 'question_box',
  confirmed_info: {
    current_grade: '',
    major: '',
    learning_stage: '',
    has_clear_goal: '',
    learning_method_preference: '',
    learning_pace_preference: '',
    content_preference: [],
    need_guidance: '',
    knowledge_foundation: '',
    strengths: '',
    weaknesses: '',
    experience: '',
    short_term_goal: '',
    long_term_goal: '',
    weekly_available_time: '',
    constraints: '',
  },
  defaulted_fields: [],
  question_md: '请选择你的年级',
  question_box: {
    question: '请选择你的年级',
    options: [
      {
        label: '大一',
        value: '大一',
        description: '大学一年级',
        target_fields: ['current_grade'],
        fills: { current_grade: '大一' },
      },
      {
        label: '大二',
        value: '大二',
        description: '大学二年级',
        target_fields: ['current_grade'],
        fills: { current_grade: '大二' },
      },
    ],
  },
  text: '请选择你的年级',
};

describe('ChatCard', () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

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

  it('hides question controls immediately after an option is selected', () => {
    const onSendReply = vi.fn();
    render(<ChatCard message={questionProfile} onSendReply={onSendReply} />);

    expect(screen.getByPlaceholderText('输入你的学习情况...')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '大一' }));

    expect(onSendReply).toHaveBeenCalledWith('大一');
    expect(screen.queryByRole('button', { name: '大一' })).toBeNull();
    expect(screen.queryByRole('button', { name: '大二' })).toBeNull();
  });

  it('keeps free-text input visible even when AI provides suggested options', () => {
    const onSendReply = vi.fn();
    render(<ChatCard message={questionProfile} onSendReply={onSendReply} />);

    fireEvent.change(screen.getByPlaceholderText('输入你的学习情况...'), {
      target: { value: '我是转专业过来的' },
    });
    fireEvent.keyDown(screen.getByPlaceholderText('输入你的学习情况...'), { key: 'Enter' });

    expect(onSendReply).toHaveBeenCalledWith('我是转专业过来的');
  });

  it('renders the completed profile transition card and handles path opening', () => {
    render(<ChatCard message={generatedProfile} />);

    expect(screen.getByText('基础画像分析完成')).toBeTruthy();
    expect(screen.getByText('了解自己，是成长的第一步。')).toBeTruthy();
    expect(screen.getByText('开启我的学习路径')).toBeTruthy();

    const ctaBtn = screen.getByRole('button', { name: '开启我的学习路径 ➔' });
    fireEvent.click(ctaBtn);

    expect(mockSetWidgetState).toHaveBeenCalledWith('WIDGET');
    expect(mockNavigate).toHaveBeenCalledWith('/branch');
  });
});
