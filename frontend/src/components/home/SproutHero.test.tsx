import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { SproutHero } from './SproutHero';
import { AuthProvider } from '../../contexts/AuthContext';

const fetchProfileDashboardMock = vi.fn();

vi.mock('../../api/profile', () => ({
  fetchProfileDashboard: (...args: unknown[]) => fetchProfileDashboardMock(...args),
}));

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function LocationProbe() {
  const location = useLocation();
  return (
    <div>
      <span data-testid="current-path">{location.pathname}</span>
    </div>
  );
}

function renderSproutHero() {
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
      <MemoryRouter initialEntries={['/sprout']} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route
            path="/sprout"
            element={(
              <>
                <SproutHero />
                <LocationProbe />
              </>
            )}
          />
          <Route path="/branch" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>
    </AuthProvider>,
  );
}

describe('SproutHero', () => {
  it('navigates to /branch when start learning is available', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大四',
        major: '软件工程',
        learningStage: '毕业项目冲刺',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成毕业项目',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: '最新路径课程',
        description: '继续当前课程',
        source: '学习路径智能体',
        currentLearningCourse: {
          grade_id: 'year_4',
          course_node_id: 'year_4_course_1',
          course_or_chapter_theme: '最新路径课程',
          course_goal: '完成最新路径课程',
          time_arrangement: {
            semester_scope: '下学期',
            duration: '8 周',
            pace_reason: '围绕毕业项目推进',
          },
          current_focus: '正在学习最新路径课程',
          progress_state: 'in_progress',
          next_action: '继续最新路径课程',
        },
        currentCourseDetail: {
          course_node_id: 'year_4_course_1',
          grade_id: 'year_4',
          course_or_chapter_theme: '最新路径课程',
          time_arrangement: {
            semester_scope: '下学期',
            duration: '8 周',
            pace_reason: '围绕毕业项目推进',
          },
          course_goal: '完成最新路径课程',
          prerequisite_node_ids: [],
          chapter_nodes: [],
          core_knowledge_points: [],
          key_points: ['新知识点'],
          difficult_points: ['新难点'],
          learning_sequence: ['新步骤'],
          knowledge_relations: [],
          downstream_resource_direction_ids: [],
          acceptance_criteria: ['新验收'],
        },
        currentCourseOutline: null,
        followingCourses: [],
      },
      recommendations: [],
    });

    renderSproutHero();

    await waitFor(() => {
      expect(screen.getByText('最新路径课程')).toBeTruthy();
    });

    fireEvent.click(screen.getByRole('button', { name: '开始学习' }));

    expect(screen.getByTestId('current-path').textContent).toBe('/branch');
  });

  it('does not expose a start-learning button when the current course is already completed', async () => {
    fetchProfileDashboardMock.mockResolvedValue({
      profile: {
        currentGrade: '大三',
        major: '软件工程',
        learningStage: '阶段收尾',
        hasClearGoal: '是',
        learningMethodPreference: '项目驱动',
        learningPacePreference: '周末集中',
        contentPreference: ['实践'],
        needGuidance: '需要',
        knowledgeFoundation: '有基础',
        strengths: '执行力强',
        weaknesses: '部署经验不足',
        experience: '做过课程项目',
        shortTermGoal: '完成当前阶段',
        longTermGoal: '成为 AI 应用开发者',
        weeklyAvailableTime: '每周 8 小时',
        constraints: '周末集中',
      },
      profileCompleteness: 100,
      profileSummaryText: '测试摘要',
      todayLearning: {
        title: 'AI Agent 项目实战',
        description: '当前阶段课程已全部完成',
        source: '学习路径智能体',
        currentLearningCourse: {
          grade_id: 'year_3',
          course_node_id: 'year_3_course_2',
          course_or_chapter_theme: 'AI Agent 项目实战',
          course_goal: '完成 AI Agent 项目实战',
          time_arrangement: {
            semester_scope: '下学期',
            duration: '8 周',
            pace_reason: '围绕项目节奏推进',
          },
          current_focus: '当前阶段课程已全部完成',
          progress_state: 'completed',
          next_action: '当前阶段课程已全部完成',
        },
        currentCourseDetail: {
          course_node_id: 'year_3_course_2',
          grade_id: 'year_3',
          course_or_chapter_theme: 'AI Agent 项目实战',
          time_arrangement: {
            semester_scope: '下学期',
            duration: '8 周',
            pace_reason: '围绕项目节奏推进',
          },
          course_goal: '完成 AI Agent 项目实战',
          prerequisite_node_ids: [],
          chapter_nodes: [],
          core_knowledge_points: [],
          key_points: ['联调'],
          difficult_points: ['部署'],
          learning_sequence: ['实现', '验收'],
          knowledge_relations: [],
          downstream_resource_direction_ids: [],
          acceptance_criteria: ['完整交付'],
        },
        currentCourseOutline: null,
        followingCourses: [],
      },
      recommendations: [],
    });

    renderSproutHero();

    await waitFor(() => {
      expect(screen.getByText('AI Agent 项目实战')).toBeTruthy();
    });

    expect(screen.queryByRole('button', { name: '开始学习' })).toBeNull();
    expect(screen.getByRole('button', { name: '打开今日学习详情' })).toBeTruthy();
  });
});
