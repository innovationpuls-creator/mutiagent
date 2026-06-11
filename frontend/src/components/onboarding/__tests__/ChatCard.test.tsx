import { fireEvent, render, screen, cleanup } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SessionMessage } from '../../../types/chat';
import { ChatCard } from '../ChatCard';

const mockNavigate = vi.fn();
const mockSetWidgetState = vi.fn();
const mockOpenWithDraft = vi.fn();

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
    openWithDraft: mockOpenWithDraft,
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

  it('renders the completed profile transition card and opens a learning path draft', () => {
    render(<ChatCard message={generatedProfile} />);

    expect(screen.getByText('基础画像分析完成')).toBeTruthy();
    expect(screen.getByText('了解自己，是成长的第一步。')).toBeTruthy();
    expect(screen.getByText('生成学习路径')).toBeTruthy();

    const ctaBtn = screen.getByRole('button', { name: '生成学习路径 ➔' });
    fireEvent.click(ctaBtn);

    expect(mockOpenWithDraft).toHaveBeenCalledWith('请根据我的基础画像生成学习路径。');
    expect(mockSetWidgetState).not.toHaveBeenCalledWith('WIDGET');
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('renders dynamic question form, handles single/multi select choices, and submits correctly', () => {
    const onSendReply = vi.fn();
    const formProfile: SessionMessage = {
      type: 'collecting',
      stage: 'learning_preference',
      question_mode: 'question_box',
      confirmed_info: {
        current_grade: '大三',
        major: '软件工程',
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
      question_md: '',
      question_box: { question: '', options: [] },
      question_form: {
        title: '完善学习偏好',
        description: '请填写以下学习偏好信息。',
        stage: 'learning_preference',
        submit_label: '确认并提交',
        questions: [
          {
            field_name: 'learning_stage',
            label: '你目前的学习阶段是？',
            description: '请选择符合你当前情况的阶段',
            input_type: 'single_choice',
            required: true,
            options: [
              { label: '刚入门', value: '刚入门', description: '', target_fields: [], fills: {} },
              { label: '有基础', value: '有基础', description: '', target_fields: [], fills: {} },
              { label: '其他', value: '__free_text__', description: '', target_fields: [], fills: {} },
            ],
          },
          {
            field_name: 'content_preference',
            label: '你偏好什么内容形式？',
            description: '可多选',
            input_type: 'multi_choice',
            required: true,
            options: [
              { label: '文档为主', value: '文档', description: '', target_fields: [], fills: {} },
              { label: '视频为主', value: '视频', description: '', target_fields: [], fills: {} },
            ],
          },
        ],
      },
      text: '完善学习偏好',
    };

    render(<ChatCard message={formProfile} onSendReply={onSendReply} />);

    // Renders form title and questions
    expect(screen.getByText('完善学习偏好')).toBeTruthy();
    expect(screen.getByText('你目前的学习阶段是？')).toBeTruthy();
    expect(screen.getByText('你偏好什么内容形式？')).toBeTruthy();

    // Check button initially disabled/enabled correctly
    const submitBtn = screen.getByRole('button', { name: '确认并提交' });
    expect(submitBtn.hasAttribute('disabled')).toBe(true);

    // Select single choice option
    fireEvent.click(screen.getByRole('button', { name: '刚入门' }));

    // Select multi choice options
    fireEvent.click(screen.getByRole('button', { name: '文档为主' }));
    fireEvent.click(screen.getByRole('button', { name: '视频为主' }));

    // Verify submit button is now enabled
    expect(submitBtn.hasAttribute('disabled')).toBe(false);

    // Submit form
    fireEvent.click(submitBtn);

    expect(onSendReply).toHaveBeenCalledWith(
      '画像表单提交：\n' +
      'learning_stage：刚入门\n' +
      'content_preference：文档、视频'
    );
  });

  it('renders free text input when other option is selected and submits it', () => {
    const onSendReply = vi.fn();
    const formProfile: SessionMessage = {
      type: 'collecting',
      stage: 'learning_preference',
      question_mode: 'question_box',
      confirmed_info: {
        current_grade: '大三',
        major: '软件工程',
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
      question_md: '',
      question_box: { question: '', options: [] },
      question_form: {
        title: '完善学习偏好',
        description: '请填写以下学习偏好信息。',
        stage: 'learning_preference',
        submit_label: '确认并提交',
        questions: [
          {
            field_name: 'learning_stage',
            label: '你目前的学习阶段是？',
            description: '请选择符合你当前情况的阶段',
            input_type: 'single_choice',
            required: true,
            options: [
              { label: '刚入门', value: '刚入门', description: '', target_fields: [], fills: {} },
              { label: '其他', value: '__free_text__', description: '', target_fields: [], fills: {} },
            ],
          },
        ],
      },
      text: '完善学习偏好',
    };

    render(<ChatCard message={formProfile} onSendReply={onSendReply} />);

    const submitBtn = screen.getByRole('button', { name: '确认并提交' });
    expect(submitBtn.hasAttribute('disabled')).toBe(true);

    // Click on other option
    fireEvent.click(screen.getByRole('button', { name: '其他' }));

    // Input text in other input box
    const otherInput = screen.getByPlaceholderText('请补充其他内容...');
    fireEvent.change(otherInput, { target: { value: '我的特定阶段' } });

    // Verify submit button is now enabled
    expect(submitBtn.hasAttribute('disabled')).toBe(false);

    // Submit form
    fireEvent.click(submitBtn);

    expect(onSendReply).toHaveBeenCalledWith(
      '画像表单提交：\n' +
      'learning_stage：我的特定阶段'
    );
  });
});
