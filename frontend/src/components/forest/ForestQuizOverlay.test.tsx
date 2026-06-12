import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ForestQuizOverlay } from './ForestQuizOverlay';
import type { CanopyOverview, ChapterWeaknessData, ForestAttempt } from '../../types/forest';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function baseAttempt(overrides: Partial<ForestAttempt> = {}): ForestAttempt {
  return {
    attempt_id: 'a1',
    quiz_id: 'q1',
    score: 85,
    passed: true,
    answers: { q1: 'A' },
    grading_result: { score: 85, passed: true, question_results: [], summary: '通过。' },
    created_at: '2026-06-09T00:00:00Z',
    ...overrides,
  };
}

function baseCanopy(overrides: Partial<CanopyOverview> = {}): CanopyOverview {
  return {
    total_courses: 5,
    completed_courses: 2,
    total_chapters: 20,
    completed_chapters: 6,
    avg_score: 80,
    total_focus_hours: 15,
    growth_tree_stage: 3,
    growth_advanced_steps: 2,
    milestones: [],
    ...overrides,
  };
}

function renderOverlay(props: Partial<Parameters<typeof ForestQuizOverlay>[0]> = {}) {
  return render(
    <MemoryRouter>
      <ForestQuizOverlay
        isOpen={true}
        onClose={vi.fn()}
        attempt={baseAttempt()}
        canopyOverview={baseCanopy()}
        nextUnlockedChapterId="ch2"
        nextCourseId={null}
        courseNodeId="year_3_course_2"
        weaknesses={[]}
        reduceMotion={true}
        {...props}
      />
    </MemoryRouter>,
  );
}

describe('ForestQuizOverlay', () => {
  it('renders nothing when isOpen is false', () => {
    renderOverlay({ isOpen: false });
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('displays score and pass status', () => {
    renderOverlay();
    expect(screen.getByText('85')).toBeTruthy();
    expect(screen.getByText('分')).toBeTruthy();
    expect(screen.getByText('CONGRATULATIONS')).toBeTruthy();
    expect(screen.getByText('恭喜通关！本次测验表现优异。')).toBeTruthy();
  });

  it('displays failure status when not passed', () => {
    renderOverlay({ attempt: baseAttempt({ passed: false, score: 40 }) });
    expect(screen.getByText('40')).toBeTruthy();
    expect(screen.getByText('KEEP WORKING')).toBeTruthy();
    expect(screen.getByText('未达到通关分数，AI 已记录薄弱方向。')).toBeTruthy();
  });

  it('displays canopy stats', () => {
    renderOverlay();
    expect(screen.getByText('2 / 5')).toBeTruthy();
    expect(screen.getByText('6 / 20')).toBeTruthy();
    expect(screen.getByText('80 分')).toBeTruthy();
    expect(screen.getByText('15 小时')).toBeTruthy();
  });

  it('displays growth stage badge', () => {
    renderOverlay();
    expect(screen.getByText('繁枝期 — 分叉成长')).toBeTruthy();
  });

  it('displays weakness tags when present', () => {
    const weaknesses: ChapterWeaknessData[] = [
      { weakness_id: 'w1', knowledge_point_id: 'kp1', knowledge_point_name: '递归', severity: 2 },
      { weakness_id: 'w2', knowledge_point_id: 'kp2', knowledge_point_name: '动态规划', severity: 1 },
    ];
    renderOverlay({ weaknesses });
    expect(screen.getByText('递归')).toBeTruthy();
    expect(screen.getByText('动态规划')).toBeTruthy();
    expect(screen.getByText('// 薄弱方向收录')).toBeTruthy();
  });

  it('does not show weakness section when empty', () => {
    renderOverlay({ weaknesses: [] });
    expect(screen.queryByText('// 薄弱方向收录')).toBeNull();
  });

  it('shows "解锁下一章" button when passed and next chapter exists', () => {
    renderOverlay({ nextUnlockedChapterId: 'ch2' });
    expect(screen.getByText('解锁下一章 →')).toBeTruthy();
  });

  it('hides "解锁下一章" button when not passed', () => {
    renderOverlay({
      attempt: baseAttempt({ passed: false }),
      nextUnlockedChapterId: 'ch2',
    });
    expect(screen.queryByText('解锁下一章 →')).toBeNull();
  });

  it('navigates to canopy on "返回雨林" click', () => {
    const onClose = vi.fn();
    renderOverlay({ onClose });
    fireEvent.click(screen.getByText('返回雨林'));
    expect(onClose).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/canopy');
  });

  it('navigates to next chapter on "解锁下一章" click', () => {
    const onClose = vi.fn();
    renderOverlay({ onClose, nextUnlockedChapterId: 'ch2' });
    fireEvent.click(screen.getByText('解锁下一章 →'));
    expect(onClose).toHaveBeenCalled();
    expect(navigateMock).toHaveBeenCalledWith('/leaf/year_3_course_2?chapter_id=ch2');
  });

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn();
    renderOverlay({ onClose });
    fireEvent.click(screen.getByLabelText('关闭'));
    expect(onClose).toHaveBeenCalled();
  });
});
