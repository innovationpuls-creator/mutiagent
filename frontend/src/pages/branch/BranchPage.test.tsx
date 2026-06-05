import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BranchPage } from './BranchPage';
import { AuthProvider } from '../../contexts/AuthContext';

const fetchBranchOverviewMock = vi.fn();
const fetchProfileDashboardMock = vi.fn();

vi.mock('../../api/branch', () => ({
  fetchBranchOverview: (...args: unknown[]) => fetchBranchOverviewMock(...args),
}));

vi.mock('../../api/profile', () => ({
  fetchProfileDashboard: (...args: unknown[]) => fetchProfileDashboardMock(...args),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
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
      <MemoryRouter>
        <BranchPage />
      </MemoryRouter>
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
});
