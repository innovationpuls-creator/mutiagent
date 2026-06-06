import { useEffect, useState } from 'react';
import '../../components/home/BlankPage.css';
import './branch.css';
import { motion, useReducedMotion } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';
import { SegmentedControl } from '../../components/ui/SegmentedControl';
import { fetchBranchOverview } from '../../api/branch';
import { fetchProfileDashboard } from '../../api/profile';
import { useAuth } from '../../contexts/AuthContext';
import { profileYearIdFromCurrentGrade } from '../../lib/profileContract';
import type { BranchCourseNode, BranchOverview } from '../../types/branch';

const YEAR_ORDER = ['year_1', 'year_2', 'year_3', 'year_4'] as const;

const YEAR_LABELS = {
  year_1: '大一',
  year_2: '大二',
  year_3: '大三',
  year_4: '大四',
} as const;

type YearId = keyof typeof YEAR_LABELS;
type StageSlot = 'left' | 'center' | 'right';

interface StageCourse {
  slot: StageSlot;
  course: BranchCourseNode;
}

interface StageCourseSet {
  left: BranchCourseNode | null;
  center: BranchCourseNode | null;
  right: BranchCourseNode | null;
}

function statusLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'current':
      return '进行中';
    default:
      return '未开放';
  }
}

function focusLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return '已完成';
    case 'current':
      return '当前焦点';
    default:
      return '未开放';
  }
}

function iconLabel(status: BranchCourseNode['status']): string {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'current':
      return 'current';
    default:
      return 'locked';
  }
}

function defaultFocusCourseId(courses: BranchCourseNode[], currentCourseId: string | null): string | null {
  if (courses.length === 0) {
    return null;
  }

  const currentIndex = courses.findIndex((course) => course.status === 'current');
  const currentCourseIndex = currentCourseId
    ? courses.findIndex((course) => course.course_node_id === currentCourseId)
    : -1;
  const firstOutlinedIndex = courses.findIndex((course) => course.has_outline);
  const focusIndex = currentIndex >= 0
    ? currentIndex
    : (currentCourseIndex >= 0 ? currentCourseIndex : (firstOutlinedIndex >= 0 ? firstOutlinedIndex : 0));

  return courses[focusIndex]?.course_node_id ?? null;
}

function resolveFocusIndex(
  courses: BranchCourseNode[],
  currentCourseId: string | null,
  focusedCourseId: string | null,
): number {
  if (focusedCourseId) {
    const focusedIndex = courses.findIndex((course) => course.course_node_id === focusedCourseId);
    if (focusedIndex >= 0) {
      return focusedIndex;
    }
  }

  const fallbackCourseId = defaultFocusCourseId(courses, currentCourseId);
  return fallbackCourseId
    ? courses.findIndex((course) => course.course_node_id === fallbackCourseId)
    : -1;
}

function pickStageCourses(
  courses: BranchCourseNode[],
  currentCourseId: string | null,
  focusedCourseId: string | null,
): StageCourse[] {
  if (courses.length === 0) {
    return [];
  }

  const focusIndex = resolveFocusIndex(courses, currentCourseId, focusedCourseId);
  if (focusIndex < 0) {
    return [];
  }

  const stageCourses: StageCourse[] = [];
  const leftCourse = focusIndex > 0 ? courses[focusIndex - 1] : null;
  const centerCourse = courses[focusIndex] ?? null;
  const rightCourse = focusIndex < courses.length - 1 ? courses[focusIndex + 1] : null;

  if (leftCourse) {
    stageCourses.push({ slot: 'left', course: leftCourse });
  }
  if (centerCourse) {
    stageCourses.push({ slot: 'center', course: centerCourse });
  }
  if (rightCourse) {
    stageCourses.push({ slot: 'right', course: rightCourse });
  }

  return stageCourses;
}

function stageLabel(courseCount: number): string {
  return `这一学年共 ${courseCount} 门课程，按顺序慢慢推进。`;
}

function railTitle(index: number, theme: string): string {
  return `第 ${index + 1} 门 · ${theme}`;
}

function railAriaLabel(gradeName: string, index: number, course: BranchCourseNode): string {
  return `${gradeName}第 ${index + 1} 门课程：${course.course_or_chapter_theme}，${statusLabel(course.status)}`;
}

function toStageCourseSet(stageCourses: StageCourse[]): StageCourseSet {
  let left: BranchCourseNode | null = null;
  let center: BranchCourseNode | null = null;
  let right: BranchCourseNode | null = null;

  for (const item of stageCourses) {
    if (item.slot === 'left') {
      left = item.course;
    } else if (item.slot === 'center') {
      center = item.course;
    } else {
      right = item.course;
    }
  }

  return { left, center, right };
}

function yearIdFromProfileGrade(currentGrade: string): YearId | null {
  return profileYearIdFromCurrentGrade(currentGrade);
}

function MascotBlob() {
  return (
    <svg aria-hidden="true" className="branch-mascot-svg" viewBox="0 0 120 120">
      <path
        className="branch-mascot-body"
        d="M60 18C84 18 96 36 96 58C96 82 78 98 60 98C38 98 20 84 20 58C20 36 34 18 60 18Z"
      />
      <circle cx="46" cy="52" r="4" className="branch-mascot-face" />
      <circle cx="74" cy="52" r="4" className="branch-mascot-face" />
      <ellipse cx="38" cy="62" rx="6" ry="4" className="branch-mascot-cheek" />
      <ellipse cx="82" cy="62" rx="6" ry="4" className="branch-mascot-cheek" />
      <path d="M47 70C51 76 56 79 60 79C64 79 69 76 73 70" className="branch-mascot-smile" />
    </svg>
  );
}

function StageIcon({ kind }: { kind: string }) {
  if (kind === 'completed') {
    return (
      <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
        <path d="M18 24.5L22 28.5L30 19.5" className="branch-stage-icon-stroke" />
      </svg>
    );
  }

  if (kind === 'current') {
    return (
      <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
        <circle cx="24" cy="24" r="8" className="branch-stage-icon-stroke" />
        <circle cx="16" cy="18" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
        <circle cx="32" cy="18" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
        <circle cx="24" cy="32" r="2.2" className="branch-stage-icon-stroke branch-stage-icon-dot" />
      </svg>
    );
  }

  return (
    <svg aria-hidden="true" className="branch-stage-icon-svg" viewBox="0 0 48 48">
      <rect x="14" y="21" width="20" height="14" rx="4" className="branch-stage-icon-stroke" />
      <path d="M18 21V17C18 13.7 20.7 11 24 11C27.3 11 30 13.7 30 17V21" className="branch-stage-icon-stroke" />
    </svg>
  );
}

function PathSession({
  gradeName,
  courses,
  currentCourseId,
}: {
  gradeName: string;
  courses: BranchCourseNode[];
  currentCourseId: string | null;
}) {
  const reduceMotion = useReducedMotion();
  const [focusedCourseId, setFocusedCourseId] = useState<string | null>(
    defaultFocusCourseId(courses, currentCourseId),
  );

  useEffect(() => {
    const nextDefaultFocusCourseId = defaultFocusCourseId(courses, currentCourseId);
    setFocusedCourseId((currentFocusedCourseId) => {
      if (
        currentFocusedCourseId
        && courses.some((course) => course.course_node_id === currentFocusedCourseId)
      ) {
        return currentFocusedCourseId;
      }
      return nextDefaultFocusCourseId;
    });
  }, [courses, currentCourseId]);

  const stageCourses = pickStageCourses(courses, currentCourseId, focusedCourseId);
  const stage = toStageCourseSet(stageCourses);

  return (
    <section className="branch-session" aria-label={`${gradeName}课程路径`}>
      <div className="branch-session-header">
        <h1 className="branch-session-title">你的路径</h1>
        <p className="branch-session-subtitle">慢一点，你正在稳稳向前。</p>
        {courses.length > 0 ? (
          <p className="branch-session-caption">{stageLabel(courses.length)}</p>
        ) : null}
      </div>

      <div className="branch-stage">
        <div className="branch-stage-particle branch-stage-particle-1" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-2" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-3" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-4" aria-hidden="true" />
        <div className="branch-stage-particle branch-stage-particle-5" aria-hidden="true" />

        {stageCourses.length > 0 ? (
          <div className="branch-stage-canvas">
            <svg className="branch-stage-curve" aria-hidden="true" viewBox="0 0 1000 500" preserveAspectRatio="none">
              <path
                className="branch-stage-curve-path"
                d="M 0 200 C 250 200, 300 250, 500 250 C 700 250, 750 300, 1000 300"
              />
            </svg>
            <div className="branch-stage-layout">
              {stage.left ? (
                <div className="branch-stage-slot branch-stage-slot-left">
                  <motion.article
                    className={`branch-blob-card branch-blob-card-${iconLabel(stage.left.status)}`}
                    whileHover={reduceMotion ? undefined : { y: -5, scale: 1.05 }}
                    whileTap={reduceMotion ? undefined : { y: -1, scale: 1.01 }}
                    transition={motionTokens.lazy}
                  >
                    <div className={`branch-blob-icon branch-blob-icon-${iconLabel(stage.left.status)}`} aria-hidden="true">
                      <StageIcon kind={iconLabel(stage.left.status)} />
                    </div>
                    <div className="branch-blob-text">
                      <h2 className="branch-blob-title">{stage.left.course_or_chapter_theme}</h2>
                      <p className={`branch-blob-status branch-blob-status-${iconLabel(stage.left.status)}`}>{statusLabel(stage.left.status)}</p>
                    </div>
                  </motion.article>
                </div>
              ) : null}

              {stage.center ? (
                <div className="branch-stage-slot branch-stage-slot-center branch-node-center">
                  <div className="branch-mascot" aria-hidden="true">
                    <MascotBlob />
                  </div>
                  <motion.article
                    className="branch-blob-card-shell branch-blob-card-shell-current"
                    animate={reduceMotion ? undefined : { scale: [1, 1.05, 1] }}
                    transition={reduceMotion ? undefined : {
                      duration: 4,
                      repeat: Number.POSITIVE_INFINITY,
                      ease: 'easeInOut',
                    }}
                  >
                    <div className="branch-current-glow" aria-hidden="true" />
                    <motion.div
                      className="branch-blob-card branch-blob-card-current"
                      whileHover={reduceMotion ? undefined : { y: -5, scale: 1.02 }}
                      whileTap={reduceMotion ? undefined : { y: -1, scale: 1.005 }}
                      transition={motionTokens.lazy}
                    >
                      <div className="branch-blob-copy-current">
                        <div className="branch-blob-icon branch-blob-icon-current" aria-hidden="true">
                          <StageIcon kind={iconLabel(stage.center.status)} />
                        </div>
                        <div className="branch-blob-text">
                          <span className="branch-blob-eyebrow">{focusLabel(stage.center.status)}</span>
                          <h2 className="branch-blob-title branch-blob-title-current">
                            {stage.center.course_or_chapter_theme}
                          </h2>
                        </div>
                      </div>
                      <motion.button
                        className="branch-focus-button"
                        type="button"
                        whileHover={reduceMotion ? undefined : { y: -2 }}
                        whileTap={reduceMotion ? undefined : { y: 0, scale: 0.992 }}
                        transition={motionTokens.lazy}
                      >
                        <span>专注模式</span>
                        <motion.span
                          className="branch-focus-button-arrow"
                          aria-hidden="true"
                          whileHover={reduceMotion ? undefined : { x: 4 }}
                          transition={motionTokens.lazy}
                        >
                          →
                        </motion.span>
                      </motion.button>
                    </motion.div>
                  </motion.article>
                </div>
              ) : null}

              {stage.right ? (
                <div className="branch-stage-slot branch-stage-slot-right">
                  <motion.article
                    className={`branch-blob-card branch-blob-card-${iconLabel(stage.right.status)}`}
                    whileHover={reduceMotion ? undefined : { y: -3, scale: 1.02 }}
                    transition={motionTokens.lazy}
                  >
                    <div className={`branch-blob-icon branch-blob-icon-${iconLabel(stage.right.status)}`} aria-hidden="true">
                      <StageIcon kind={iconLabel(stage.right.status)} />
                    </div>
                    <div className="branch-blob-text">
                      <h2 className="branch-blob-title">{stage.right.course_or_chapter_theme}</h2>
                      <p className={`branch-blob-status branch-blob-status-${iconLabel(stage.right.status)}`}>{statusLabel(stage.right.status)}</p>
                    </div>
                  </motion.article>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="branch-stage-empty">
            <p className="branch-stage-empty-title">这个年级还没有课程路径</p>
            <span className="branch-stage-empty-text">生成课程后，这里会展示该年级自己的学习节奏。</span>
          </div>
        )}
      </div>

      {courses.length > 0 ? (
        <div className="branch-course-rail" aria-label={`${gradeName}整学年课程脉络`}>
          {courses.map((course, index) => {
            const isFocused = course.course_node_id === focusedCourseId;
            const isCurrentCourse = course.course_node_id === currentCourseId || course.status === 'current';

            return (
              <motion.button
                key={course.course_node_id}
                className={`branch-course-rail-card${isFocused ? ' branch-course-rail-card-focused' : ''}`}
                type="button"
                aria-label={railAriaLabel(gradeName, index, course)}
                aria-pressed={isFocused}
                whileHover={reduceMotion ? undefined : { y: -3, scale: 1.01 }}
                whileTap={reduceMotion ? undefined : { y: -1, scale: 0.995 }}
                transition={motionTokens.lazy}
                onClick={() => {
                  setFocusedCourseId(course.course_node_id);
                }}
              >
                <div className="branch-course-rail-copy">
                  <span className="branch-course-rail-index">{`第 ${index + 1} 门`}</span>
                  <h3 className="branch-course-rail-title">{railTitle(index, course.course_or_chapter_theme)}</h3>
                  <p className="branch-course-rail-goal">{course.course_goal}</p>
                </div>
                <div className="branch-course-rail-meta">
                  <span className={`branch-course-rail-status branch-course-rail-status-${iconLabel(course.status)}`}>
                    {statusLabel(course.status)}
                  </span>
                  {isCurrentCourse ? (
                    <span className="branch-course-rail-badge">当前推进</span>
                  ) : null}
                  {course.has_outline ? (
                    <span className="branch-course-rail-badge">已生成章节</span>
                  ) : null}
                </div>
              </motion.button>
            );
          })}
        </div>
      ) : null}

    </section>
  );
}

export function BranchPage() {
  const reduceMotion = useReducedMotion();
  const { token, isAuthReady } = useAuth();
  const [overview, setOverview] = useState<BranchOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeYear, setActiveYear] = useState<YearId>('year_1');

  useEffect(() => {
    let cancelled = false;

    async function loadOverview() {
      if (!isAuthReady) {
        return;
      }

      if (!token) {
        if (!cancelled) {
          setOverview(null);
          setLoading(false);
          setError('登录后可查看课程路径。');
        }
        return;
      }

      if (!cancelled) {
        setLoading(true);
        setError(null);
      }

      try {
        const [nextOverview, dashboard] = await Promise.all([
          fetchBranchOverview(token),
          fetchProfileDashboard(token),
        ]);
        if (cancelled) {
          return;
        }

        setOverview(nextOverview);
        const mappedProfileYear = yearIdFromProfileGrade(dashboard.profile.currentGrade);
        const firstClickable = YEAR_ORDER.find((yearId) => nextOverview.years[yearId]?.is_clickable);
        const preferredYear = mappedProfileYear && nextOverview.years[mappedProfileYear]?.is_clickable
          ? mappedProfileYear
          : null;
        setActiveYear(preferredYear ?? firstClickable ?? 'year_1');
      } catch (loadError) {
        if (cancelled) {
          return;
        }

        const message = loadError instanceof Error ? loadError.message : '课程路径加载失败';
        setOverview(null);
        setError(message);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadOverview();

    return () => {
      cancelled = true;
    };
  }, [isAuthReady, token]);

  const options = YEAR_ORDER.map((yearId) => overview?.years[yearId]?.grade_name ?? YEAR_LABELS[yearId]);
  const labelToYearId = Object.fromEntries(
    YEAR_ORDER.map((yearId, index) => [options[index], yearId]),
  ) as Record<string, YearId>;
  const disabledOptions = YEAR_ORDER
    .filter((yearId) => !(overview?.years[yearId]?.is_clickable ?? false))
    .map((yearId) => overview?.years[yearId]?.grade_name ?? YEAR_LABELS[yearId]);
  const activeLabel = overview?.years[activeYear]?.grade_name ?? YEAR_LABELS[activeYear];
  const activeYearData = overview?.years[activeYear] ?? null;

  return (
    <motion.main
      className="home-page"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={reduceMotion ? undefined : { opacity: 1 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, transition: { duration: 0.4 } }}
    >
      <div className="home-ambient-sun" aria-hidden="true" />
      <div className="home-paper-canvas" aria-hidden="true" />

      <div className="home-content branch-content">
        <nav className="branch-nav" aria-label="年级切换">
          <SegmentedControl
            options={options}
            active={activeLabel}
            onChange={(label) => {
              const yearId = labelToYearId[label];
              if (yearId) {
                setActiveYear(yearId);
              }
            }}
            disabledOptions={disabledOptions}
          />
        </nav>

        <div className="branch-view-container">
          {loading ? (
            <div className="branch-feedback-card">
              <p className="branch-feedback-title">正在加载课程路径</p>
              <span className="branch-feedback-text">请稍候片刻。</span>
            </div>
          ) : error ? (
            <div className="branch-feedback-card">
              <p className="branch-feedback-title">课程路径暂时不可用</p>
              <span className="branch-feedback-text">{error}</span>
            </div>
          ) : (
            <motion.div
              key={activeYear}
              initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={motionTokens.editorial}
              style={{ width: '100%' }}
            >
              <PathSession
                gradeName={activeYearData?.grade_name ?? YEAR_LABELS[activeYear]}
                courses={activeYearData?.courses ?? []}
                currentCourseId={activeYearData?.current_course_id ?? null}
              />
            </motion.div>
          )}
        </div>
      </div>
    </motion.main>
  );
}
