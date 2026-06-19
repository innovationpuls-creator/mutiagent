import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import React from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { BranchPage } from './BranchPage';
import { AuthProvider } from '../../contexts/AuthContext';
import { AiWidgetProvider } from '../../context/AiWidgetContext';

vi.mock('../../context/AiWidgetContext', () => ({
  useAiWidget: () => ({
    setWidgetState: vi.fn(),
    openWithMessage: vi.fn(),
    openWithDraft: vi.fn(),
  }),
  AiWidgetProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const fetchBranchOverviewMock = vi.fn();
const fetchProfileDashboardMock = vi.fn();
const getMatchedProgramMock = vi.fn();

vi.mock('../../api/branch', () => ({
  fetchBranchOverview: (...args: unknown[]) => fetchBranchOverviewMock(...args),
}));

vi.mock('../../api/profile', () => ({
  fetchProfileDashboard: (...args: unknown[]) => fetchProfileDashboardMock(...args),
}));

vi.mock('../../api/teacherProgram', () => ({
  teacherProgramApi: {
    getMatchedProgram: (...args: unknown[]) => getMatchedProgramMock(...args),
  },
}));

vi.mock('framer-motion', async () => {
  const actual = await vi.importActual<typeof import('framer-motion')>('framer-motion');
  return {
    ...actual,
    useReducedMotion: () => true,
  };
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

beforeEach(() => {
  getMatchedProgramMock.mockResolvedValue(null);
});

function renderBranchPage() {
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => {
      if (key !== 'mutiagent-auth') {
        return null;
      }
      return JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'user-1',
          username: '测试用户',
          identifier: 'user@example.com',
          role: 'student',
          school: '南山大学',
          major: '软件工程',
          class_name: '一班',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      });
    }),
    setItem: vi.fn(),
    removeItem: vi.fn(),
  });

  return render(
    <AuthProvider>
      <AiWidgetProvider>
        <MemoryRouter>
          <BranchPage />
        </MemoryRouter>
      </AiWidgetProvider>
    </AuthProvider>,
  );
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderBranchWithLeafRoute() {
  return render(
    <AuthProvider>
      <AiWidgetProvider>
        <MemoryRouter initialEntries={['/branch']}>
          <Routes>
            <Route path="/branch" element={<><LocationProbe /><BranchPage /></>} />
            <Route path="/leaf/:courseNodeId" element={<LocationProbe />} />
          </Routes>
        </MemoryRouter>
      </AiWidgetProvider>
    </AuthProvider>,
  );
}

describe('BranchPage', () => {
  it('defaults to profile.currentGrade even when another year is the first clickable option', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_1_course_1',
          courses: [
            {
              course_node_id: 'year_1_course_1',
              course_or_chapter_theme: '编程基础',
              course_goal: '打基础',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_3_course_1',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成项目',
              status: 'current',
              has_outline: true,
            },
          ],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('AI 应用开发项目课')).toBeTruthy();
    });

    expect(screen.queryByText('编程基础')).toBeNull();
  });

  it('falls back to the first clickable year when profile.currentGrade maps to a locked year', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_1_course_1',
          courses: [
            {
              course_node_id: 'year_1_course_1',
              course_or_chapter_theme: '编程基础',
              course_goal: '打基础',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('编程基础')).toBeTruthy();
    });

    expect(screen.queryByText('这个年级还没有课程路径')).toBeNull();
  });

  it('falls back to the first clickable year when profile.currentGrade cannot be mapped', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '暂未确认',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_2_course_1',
          courses: [
            {
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '工程化 Web 开发基础',
              course_goal: '建立工程能力',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_3_course_1',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成项目',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('工程化 Web 开发基础')).toBeTruthy();
    });

    expect(screen.queryByText('AI 应用开发项目课')).toBeNull();
  });

  it('falls back to the first clickable year when profile.currentGrade is unsupported postgraduate grade', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '研一',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_2_course_1',
          courses: [
            {
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '工程化 Web 开发基础',
              course_goal: '建立工程能力',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'year_3_course_1',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成项目',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('工程化 Web 开发基础')).toBeTruthy();
    });

    expect(screen.queryByText('AI 应用开发项目课')).toBeNull();
  });

  it('keeps the completed current course in center focus when the latest course is already finished', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大二',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_2_course_3',
          courses: [
            {
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '数据结构基础',
              course_goal: '打基础',
              status: 'completed',
              has_outline: true,
            },
            {
              course_node_id: 'year_2_course_2',
              course_or_chapter_theme: '数据库系统',
              course_goal: '打基础',
              status: 'completed',
              has_outline: true,
            },
            {
              course_node_id: 'year_2_course_3',
              course_or_chapter_theme: '后端接口实战',
              course_goal: '完成项目',
              status: 'completed',
              has_outline: true,
            },
          ],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    const { container } = renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('后端接口实战')).toBeTruthy();
    });

    const centerNode = container.querySelector('.branch-node-center');
    expect(centerNode?.textContent).toContain('后端接口实战');
    expect(centerNode?.textContent).toContain('已完成');
  });

  it('uses the upper course nodes instead of rendering a lower course rail', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_3_course_2',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发基础能力搭建',
              course_goal: '完成最小功能闭环',
              status: 'completed',
              has_outline: true,
            },
            {
              course_node_id: 'year_3_course_2',
              course_or_chapter_theme: 'AI 应用开发项目实战',
              course_goal: '完成项目验收',
              status: 'current',
              has_outline: true,
            },
            {
              course_node_id: 'year_3_course_3',
              course_or_chapter_theme: 'AI 应用部署与监控实战',
              course_goal: '完成部署与监控闭环',
              status: 'locked',
              has_outline: false,
            },
          ],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: false,
          has_outline_content: false,
          is_clickable: false,
          current_course_id: null,
          courses: [],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    const { container } = renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('这一学年共 3 门课程，按顺序慢慢推进。')).toBeTruthy();
    });

    expect(screen.queryByText('第 1 门 · AI 应用开发基础能力搭建')).toBeNull();
    expect(screen.queryByText('第 2 门 · AI 应用开发项目实战')).toBeNull();
    expect(screen.queryByText('第 3 门 · AI 应用部署与监控实战')).toBeNull();
    expect(container.querySelector('.branch-course-rail')).toBeNull();

    let centerNode = container.querySelector('.branch-node-center');
    expect(centerNode?.textContent).toContain('AI 应用开发项目实战');

    fireEvent.click(screen.getByRole('button', { name: /大三第 1 门课程（自选课程）：AI 应用开发基础能力搭建，已完成/ }));

    await waitFor(() => {
      const nextCenterNode = container.querySelector('.branch-node-center');
      expect(nextCenterNode?.textContent).toContain('AI 应用开发基础能力搭建');
    });

    centerNode = container.querySelector('.branch-node-center');
    expect(centerNode?.textContent).toContain('AI 应用开发基础能力搭建');
  });

  it('navigates completed and current courses to leaf while locked courses stay on branch', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });
    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: { grade_id: 'year_1', grade_name: '大一', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_3_course_2',
          courses: [
            { course_node_id: 'year_3_course_1', course_or_chapter_theme: '已完成课程', course_goal: '复习', status: 'completed', has_outline: true },
            { course_node_id: 'year_3_course_2', course_or_chapter_theme: '当前课程', course_goal: '学习', status: 'current', has_outline: true },
            { course_node_id: 'year_3_course_3', course_or_chapter_theme: '锁定课程', course_goal: '以后学习', status: 'locked', has_outline: false },
          ],
        },
        year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => key === 'mutiagent-auth'
        ? JSON.stringify({
          token: 'token-1',
          user: { uid: 'user-1', username: '测试用户', identifier: 'user@example.com', role: 'student', school: '南山大学', major: '软件工程', class_name: '一班', provider: 'password', is_active: true, created_at: '2026-06-02T00:00:00Z', last_login_at: null },
        })
        : null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });

    const completedView = renderBranchWithLeafRoute();
    await waitFor(() => expect(screen.getByText('当前课程')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /大三第 1 门课程（自选课程）：已完成课程，已完成/ }));
    fireEvent.click(screen.getByRole('button', { name: /大三第 1 门课程（自选课程）：已完成课程，已完成/ }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/leaf/year_3_course_1'));
    completedView.unmount();

    const currentView = renderBranchWithLeafRoute();
    await waitFor(() => expect(screen.getByText('当前课程')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /大三第 2 门课程（自选课程）：当前课程，进行中/ }));
    await waitFor(() => expect(screen.getByTestId('location').textContent).toBe('/leaf/year_3_course_2'));
    currentView.unmount();

    renderBranchWithLeafRoute();
    await waitFor(() => expect(screen.getByText('当前课程')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /大三第 3 门课程（自选课程）：锁定课程，未开放/ }));
    expect(screen.getByTestId('location').textContent).toBe('/branch');
    expect(screen.getByRole('status').textContent).toBe('「锁定课程」还未开放，先完成前面的课程。');
  });

  it('switches the stage content when the user selects another clickable year', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: null,
          courses: [
            {
              course_node_id: 'year_1_course_1',
              course_or_chapter_theme: '编程基础',
              course_goal: '打基础',
              status: 'completed',
              has_outline: false,
            },
          ],
        },
        year_2: {
          grade_id: 'year_2',
          grade_name: '大二',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: null,
          courses: [
            {
              course_node_id: 'year_2_course_1',
              course_or_chapter_theme: '工程化 Web 开发基础',
              course_goal: '建立工程能力',
              status: 'completed',
              has_outline: false,
            },
          ],
        },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_3_course_1',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成项目',
              status: 'current',
              has_outline: true,
            },
          ],
        },
        year_4: {
          grade_id: 'year_4',
          grade_name: '大四',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: null,
          courses: [
            {
              course_node_id: 'year_4_course_1',
              course_or_chapter_theme: '就业级作品集与迭代优化',
              course_goal: '完成作品集整理',
              status: 'locked',
              has_outline: false,
            },
          ],
        },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('AI 应用开发项目课')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '大四' }));

    await waitFor(() => {
      expect(screen.getByText('就业级作品集与迭代优化')).toBeTruthy();
    });

    expect(screen.queryByText('AI 应用开发项目课')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '大二' }));

    await waitFor(() => {
      expect(screen.getByText('工程化 Web 开发基础')).toBeTruthy();
    });

    expect(screen.queryByText('就业级作品集与迭代优化')).toBeNull();

    fireEvent.click(screen.getByRole('button', { name: '大一' }));

    await waitFor(() => {
      expect(screen.getByText('编程基础')).toBeTruthy();
    });

    expect(screen.queryByText('工程化 Web 开发基础')).toBeNull();
  });

  it('renders PathInitOverlay when justGeneratedProfile state is passed, and shows coachmark after completion', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: { grade_id: 'year_1', grade_name: '大一', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_3: {
          grade_id: 'year_3',
          grade_name: '大三',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'year_3_course_1',
          courses: [
            {
              course_node_id: 'year_3_course_1',
              course_or_chapter_theme: 'AI 应用开发项目课',
              course_goal: '完成项目',
              status: 'current',
              has_outline: true,
            },
          ],
        },
        year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => {
        if (key !== 'mutiagent-auth') {
          return null;
        }
        return JSON.stringify({
          token: 'token-1',
          user: {
            uid: 'user-1',
            username: '测试用户',
            identifier: 'user@example.com',
            role: 'student',
            school: '南山大学',
            major: '软件工程',
            class_name: '一班',
            provider: 'password',
            is_active: true,
            created_at: '2026-06-02T00:00:00Z',
            last_login_at: null,
          },
        });
      }),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    });

    render(
      <AuthProvider>
        <MemoryRouter initialEntries={[{ pathname: '/branch', state: { justGeneratedProfile: true } }]}>
          <Routes>
            <Route path="/branch" element={<BranchPage />} />
          </Routes>
        </MemoryRouter>
      </AuthProvider>,
    );

    // Verify overlay is shown
    await waitFor(() => {
      expect(screen.getByText('你的自适应学习路径已顺利编织完成。')).toBeTruthy();
    });

    // Since useReducedMotion returns true, the button is immediately rendered
    const btn = screen.getByRole('button', { name: '开始《AI 应用开发项目课》' });
    expect(btn).toBeTruthy();

    // Click button to close overlay and trigger coachmark
    fireEvent.click(btn);

    // Wait for overlay to disappear
    await waitFor(() => {
      expect(screen.queryByText('你的自适应学习路径已顺利编织完成。')).toBeNull();
    });

    // Verify coachmark balloon is rendered
    expect(screen.getByText('✨ 点击此处，开启第一章学习')).toBeTruthy();

    // Click coachmark to dismiss it
    const coachmark = screen.getByText('✨ 点击此处，开启第一章学习');
    fireEvent.click(coachmark);

    // Verify coachmark is dismissed
    await waitFor(() => {
      expect(screen.queryByText('✨ 点击此处，开启第一章学习')).toBeNull();
    });
  });

  it('refreshes branch overview when the learning path update event is dispatched', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '项目实践',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成 AI 项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock
      .mockResolvedValueOnce({
        years: {
          year_1: { grade_id: 'year_1', grade_name: '大一', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
          year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
          year_3: {
            grade_id: 'year_3',
            grade_name: '大三',
            has_courses: true,
            has_outline_content: false,
            is_clickable: true,
            current_course_id: 'year_3_course_1',
            courses: [
              {
                course_node_id: 'year_3_course_1',
                course_or_chapter_theme: '旧课程路径',
                course_goal: '等待更新',
                status: 'current',
                has_outline: false,
              },
            ],
          },
          year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        },
        updatedAt: '2026-06-05T00:00:00Z',
      })
      .mockResolvedValueOnce({
        years: {
          year_1: { grade_id: 'year_1', grade_name: '大一', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
          year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
          year_3: {
            grade_id: 'year_3',
            grade_name: '大三',
            has_courses: true,
            has_outline_content: true,
            is_clickable: true,
            current_course_id: 'year_3_course_1',
            courses: [
              {
                course_node_id: 'year_3_course_1',
                course_or_chapter_theme: 'AI Agent 开发基础能力搭建',
                course_goal: '完成最小功能闭环',
                status: 'current',
                has_outline: true,
              },
            ],
          },
          year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        },
        updatedAt: '2026-06-05T00:01:00Z',
      });

    renderBranchPage();

    await waitFor(() => {
      expect(screen.getByText('旧课程路径')).toBeTruthy();
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('mutiagent-learning-path-updated', {
        detail: { sessionId: 'session-follow-up' },
      }));
    });

    await waitFor(() => {
      expect(fetchBranchOverviewMock).toHaveBeenCalledTimes(2);
      expect(screen.getByText('AI Agent 开发基础能力搭建')).toBeTruthy();
    });

    expect(screen.queryByText('旧课程路径')).toBeNull();
  });

  it('merges preset courses from localStorage, unlocks custom nodes when parent is completed, and renders highlight paths when clicked', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大一',
        major: '计算机科学',
        learningStage: '基础学年',
        hasClearGoal: '是',
        learningMethodPreference: '系统学习',
        learningPacePreference: '标准节奏',
        contentPreference: ['理论'],
        needGuidance: '是',
        knowledgeFoundation: '零基础',
        strengths: '逻辑思维',
        weaknesses: '无实践经验',
        experience: '无',
        shortTermGoal: '掌握基础',
        longTermGoal: '做一名后端工程师',
        weeklyAvailableTime: '每周 10 小时',
        constraints: '无',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: true,
          is_clickable: true,
          current_course_id: 'preset_parent_1',
          courses: [
            {
              course_node_id: 'preset_parent_1',
              course_or_chapter_theme: '编程导论',
              course_goal: '基础编程',
              status: 'completed',
              has_outline: true,
            },
          ],
        },
        year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_3: { grade_id: 'year_3', grade_name: '大三', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });

    const customPresetCourse = {
      course_node_id: 'custom_child_1',
      course_or_chapter_theme: 'C++ 高级编程',
      course_goal: '面向对象与泛型',
      status: 'locked',
      has_outline: true,
      is_custom: true,
      parent_preset_id: 'preset_parent_1',
      prerequisite_ids: ['preset_parent_1'],
      time_arrangement: {
        semester_scope: '1',
        duration: '4 weeks',
      },
    };
    getMatchedProgramMock.mockResolvedValue({
      program_id: 'program-1',
      teacher_uid: 'teacher-1',
      teacher_name: '测试教师',
      teacher_identifier: 'teacher@example.com',
      school: '南山大学',
      major: '软件工程',
      class_name: '一班',
      courses: [customPresetCourse],
      published_at: '2026-06-15T10:00:00.000Z',
      updated_at: '2026-06-15T10:00:00.000Z',
    });

    const store: Record<string, string> = {
      'mutiagent-auth': JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'user-1',
          username: '测试用户',
          identifier: 'student@example.com',
          role: 'student',
          school: '南山大学',
          major: '软件工程',
          class_name: '一班',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      }),
    };

    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
    });

    render(
      <AuthProvider>
        <AiWidgetProvider>
          <MemoryRouter>
            <BranchPage />
          </MemoryRouter>
        </AiWidgetProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('编程导论')).toBeTruthy();
      expect(screen.getByText('C++ 高级编程')).toBeTruthy();
    });

    const customCardButton = screen.getByRole('button', { name: /C\+\+/ });
    expect(customCardButton).toBeTruthy();

    fireEvent.click(customCardButton);

    await waitFor(() => {
      const paths = screen.getAllByTestId('branch-highlight-path');
      expect(paths.length).toBeGreaterThan(0);
    });
  });

  it('renders source labels for self-selected and teacher-program courses', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大一',
        major: '软件工程',
        learningStage: '基础学习',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '稳定推进',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '算法薄弱',
        experience: '做过课程项目',
        shortTermGoal: '完成基础课',
        longTermGoal: '成为工程师',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '课余时间',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'self_course_1',
          courses: [
            {
              course_node_id: 'self_course_1',
              course_or_chapter_theme: '编程导论',
              course_goal: '建立编程基础',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_3: { grade_id: 'year_3', grade_name: '大三', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });
    getMatchedProgramMock.mockResolvedValue({
      program_id: 'program-1',
      teacher_uid: 'teacher-1',
      teacher_name: '测试教师',
      teacher_identifier: 'teacher@example.com',
      school: '南山大学',
      major: '软件工程',
      class_name: '一班',
      courses: [
        {
          course_node_id: 'teacher_course_1',
          course_or_chapter_theme: 'C++ 高级编程',
          course_goal: '补充学校培养方案课程',
          status: 'locked',
          has_outline: true,
          is_custom: false,
          time_arrangement: {
            semester_scope: '1',
            duration: '4 周',
          },
        },
      ],
      published_at: '2026-06-15T10:00:00.000Z',
      updated_at: '2026-06-15T10:00:00.000Z',
    });

    const store: Record<string, string> = {
      'mutiagent-auth': JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'user-1',
          username: '测试用户',
          identifier: 'student@example.com',
          role: 'student',
          school: '南山大学',
          major: '软件工程',
          class_name: '一班',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      }),
    };

    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
    });

    render(
      <AuthProvider>
        <AiWidgetProvider>
          <MemoryRouter>
            <BranchPage />
          </MemoryRouter>
        </AiWidgetProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('编程导论')).toBeTruthy();
      expect(screen.getByText('C++ 高级编程')).toBeTruthy();
    });

    expect(screen.getByRole('button', { name: /^大一第 1 门课程（自选课程）：编程导论，进行中$/ })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^大一第 2 门课程（人培课程）：C\+\+ 高级编程，未开放$/ })).toBeTruthy();
    expect(screen.getByText('自选课程')).toBeTruthy();
    expect(screen.getByText('人培课程')).toBeTruthy();
  });

  it('loads teacher-program courses from the student teacher binding', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大一',
        major: '软件工程',
        learningStage: '基础学习',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '稳定推进',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '算法薄弱',
        experience: '做过课程项目',
        shortTermGoal: '完成基础课',
        longTermGoal: '成为工程师',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '课余时间',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '今日学习',
        description: '测试',
        source: '学习路径智能体',
        currentLearningCourse: null,
        currentCourseDetail: null,
        currentCourseOutline: null,
        gradeCourses: [],
        followingCourses: [],
      },
      recommendations: [],
    });

    fetchBranchOverviewMock.mockResolvedValue({
      years: {
        year_1: {
          grade_id: 'year_1',
          grade_name: '大一',
          has_courses: true,
          has_outline_content: false,
          is_clickable: true,
          current_course_id: 'self_course_1',
          courses: [
            {
              course_node_id: 'self_course_1',
              course_or_chapter_theme: '编程导论',
              course_goal: '建立编程基础',
              status: 'current',
              has_outline: false,
            },
          ],
        },
        year_2: { grade_id: 'year_2', grade_name: '大二', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_3: { grade_id: 'year_3', grade_name: '大三', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
        year_4: { grade_id: 'year_4', grade_name: '大四', has_courses: false, has_outline_content: false, is_clickable: false, current_course_id: null, courses: [] },
      },
      updatedAt: '2026-06-05T00:00:00Z',
    });
    getMatchedProgramMock.mockResolvedValue({
      program_id: 'program-1',
      teacher_uid: 'teacher-1',
      teacher_name: '测试教师',
      teacher_identifier: 'teacher@example.com',
      school: '南山大学',
      major: '软件工程',
      class_name: '一班',
      courses: [
        {
          course_node_id: 'teacher_course_1',
          course_or_chapter_theme: 'C++ 高级编程',
          course_goal: '补充学校培养方案课程',
          status: 'locked',
          has_outline: true,
          is_custom: false,
          time_arrangement: {
            semester_scope: '1',
            duration: '4 周',
          },
        },
      ],
      published_at: '2026-06-15T10:00:00.000Z',
      updated_at: '2026-06-15T10:00:00.000Z',
    });

    const store: Record<string, string> = {
      'mutiagent-auth': JSON.stringify({
        token: 'token-1',
        user: {
          uid: 'student-1',
          username: '测试学生',
          identifier: 'student@example.com',
          role: 'student',
          school: '南山大学',
          major: '软件工程',
          class_name: '一班',
          provider: 'password',
          is_active: true,
          created_at: '2026-06-02T00:00:00Z',
          last_login_at: null,
        },
      }),
    };

    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => store[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        store[key] = value;
      }),
      removeItem: vi.fn((key: string) => {
        delete store[key];
      }),
    });

    render(
      <AuthProvider>
        <AiWidgetProvider>
          <MemoryRouter>
            <BranchPage />
          </MemoryRouter>
        </AiWidgetProvider>
      </AuthProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('编程导论')).toBeTruthy();
      expect(screen.getByText('C++ 高级编程')).toBeTruthy();
    });

    expect(screen.getByRole('button', { name: /^大一第 2 门课程（人培课程）：C\+\+ 高级编程，未开放$/ })).toBeTruthy();
  });
});
