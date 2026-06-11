import { useEffect, useMemo, useState, type KeyboardEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import styled from 'styled-components';
import { motion, useReducedMotion } from 'framer-motion';
import { GrowthTreeSVG } from '../../components/canopy/GrowthTreeSVG';
import { fetchCanopyOverview } from '../../api/branch';
import { useAuth } from '../../contexts/AuthContext';
import { motionTokens } from '../../styles/motion-tokens';
import type { CanopyCourseNode, CanopyCourseStatus, CanopyMilestone } from '../../types/canopy';

interface SlotPoint {
  x: number;
  y: number;
}

interface PositionedCourse extends CanopyCourseNode, SlotPoint {
  gradeLabel: string;
}

interface CourseConnection {
  id: string;
  source: PositionedCourse;
  target: PositionedCourse;
}

const PREDEFINED_SLOTS: SlotPoint[] = [
  { x: 180, y: 150 },
  { x: 130, y: 260 },
  { x: 260, y: 230 },
  { x: 370, y: 320 },
  { x: 470, y: 210 },
  { x: 340, y: 450 },
  { x: 600, y: 180 },
  { x: 530, y: 410 },
  { x: 650, y: 320 },
  { x: 780, y: 230 },
  { x: 740, y: 440 },
  { x: 820, y: 350 },
];

const GRADE_TO_SLOT_OFFSET: Record<string, number> = {
  year_1: 0,
  year_2: 3,
  year_3: 6,
  year_4: 9,
};

const GRADE_LABELS: Record<string, string> = {
  year_1: '大一',
  year_2: '大二',
  year_3: '大三',
  year_4: '大四',
};

const STAGE_LABELS: Record<number, string> = {
  1: '种子',
  2: '萌芽',
  3: '繁枝',
  4: '叶茂',
  5: '成林',
  6: '成森',
};

function statusLabel(status: CanopyCourseStatus): string {
  switch (status) {
    case 'completed':
      return '已点亮';
    case 'in_progress':
      return '生长中';
    default:
      return '锁定中';
  }
}

function truncateLabel(title: string): string {
  return title.length > 12 ? `${title.slice(0, 12)}...` : title;
}

function mapCoursesToSlots(courses: CanopyCourseNode[]): PositionedCourse[] {
  const countsByGrade: Record<string, number> = {};
  const positioned: PositionedCourse[] = [];

  courses.forEach((course) => {
    const offset = GRADE_TO_SLOT_OFFSET[course.grade];
    if (offset === undefined) {
      return;
    }

    const indexInGrade = countsByGrade[course.grade] ?? 0;
    countsByGrade[course.grade] = indexInGrade + 1;
    const slot = PREDEFINED_SLOTS[offset + indexInGrade];
    if (!slot) {
      return;
    }

    positioned.push({
      ...course,
      x: slot.x,
      y: slot.y,
      gradeLabel: GRADE_LABELS[course.grade] ?? course.grade,
    });
  });

  return positioned;
}

function mapConnections(courses: PositionedCourse[]): CourseConnection[] {
  const byId = new Map(courses.map((course) => [course.id, course]));
  return courses.flatMap((target) =>
    target.prerequisite_ids.flatMap((sourceId) => {
      const source = byId.get(sourceId);
      return source ? [{ id: `${source.id}-${target.id}`, source, target }] : [];
    }),
  );
}

function milestoneState(milestones: CanopyMilestone[], index: number): string {
  const milestone = milestones[index];
  if (!milestone.reached) {
    return 'locked';
  }
  const nextMilestone = milestones[index + 1];
  return !nextMilestone || !nextMilestone.reached ? 'active' : 'reached';
}

export function CanopyPage() {
  const reduceMotion = useReducedMotion();
  const navigate = useNavigate();
  const { token, isAuthReady } = useAuth();
  const [courses, setCourses] = useState<CanopyCourseNode[]>([]);
  const [milestones, setMilestones] = useState<CanopyMilestone[]>([]);
  const [growthStage, setGrowthStage] = useState(1);
  const [completedCount, setCompletedCount] = useState(0);
  const [activeRate, setActiveRate] = useState(0);
  const [avgScore, setAvgScore] = useState(0);
  const [focusedHours, setFocusedHours] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [qualityScores, setQualityScores] = useState<Record<string, import('../../types/canopy').CourseQualityScore>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadCanopy() {
      if (!isAuthReady) {
        return;
      }

      if (!token) {
        if (!cancelled) {
          setLoading(false);
          setError('登录后可查看成森进度。');
        }
        return;
      }

      if (!cancelled) {
        setLoading(true);
        setError(null);
      }

      try {
        const overview = await fetchCanopyOverview(token);
        if (cancelled) {
          return;
        }
        setCourses(overview.courses);
        setMilestones(overview.milestones);
        setGrowthStage(overview.growthStage);
        setCompletedCount(overview.completedCount);
        setActiveRate(overview.activeRate);
        setAvgScore(overview.avgScore);
        setFocusedHours(overview.focusedHours);
        setQualityScores(overview.qualityScores ?? {});
      } catch (loadError) {
        if (cancelled) {
          return;
        }
        setCourses([]);
        setMilestones([]);
        setError(loadError instanceof Error ? loadError.message : '成森数据加载失败');
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadCanopy();

    return () => {
      cancelled = true;
    };
  }, [isAuthReady, token]);

  const positionedCourses = useMemo(() => mapCoursesToSlots(courses), [courses]);
  const connections = useMemo(() => mapConnections(positionedCourses), [positionedCourses]);
  const stageLabel = STAGE_LABELS[growthStage] ?? STAGE_LABELS[1];

  function handleCourseClick(course: PositionedCourse) {
    navigate(`/leaf/${course.id}`);
  }

  function handleCourseKeyDown(event: KeyboardEvent<SVGGElement>, course: PositionedCourse) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    event.preventDefault();
    handleCourseClick(course);
  }

  return (
    <PageWrapper aria-label="成森知识雨林页面">
      <div className="forest-ambient-sun" aria-hidden="true" />
      <div className="forest-paper-canvas" aria-hidden="true" />

      <motion.main
        className="canopy-layout"
        initial={reduceMotion ? false : { opacity: 0, y: 16 }}
        animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -16 }}
        transition={motionTokens.editorial}
      >
        <section className="graph-section" aria-label="知识雨林图谱">
          <header className="section-header">
            <span>// knowledge canopy</span>
            <h2>知识雨林图谱</h2>
            <p>当前阶段：{stageLabel} · 雨林点亮率 {activeRate}%</p>
          </header>

          <div className="network-container">
            {loading ? (
              <div className="feedback-panel" role="status">
                <p>正在加载成森进度</p>
                <span>请稍候片刻。</span>
              </div>
            ) : error ? (
              <div className="feedback-panel" role="alert">
                <p>成森进度暂时不可用</p>
                <span>{error}</span>
              </div>
            ) : (
              <>
                <svg viewBox="0 0 900 600" className="network-svg" aria-hidden={positionedCourses.length === 0}>
                  <defs>
                    <radialGradient id="completed-glow" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="oklch(75% 0.09 135 / 0.42)" />
                      <stop offset="100%" stopColor="oklch(75% 0.09 135 / 0)" />
                    </radialGradient>
                    <radialGradient id="inprogress-glow" cx="50%" cy="50%" r="50%">
                      <stop offset="0%" stopColor="oklch(76% 0.12 55 / 0.42)" />
                      <stop offset="100%" stopColor="oklch(76% 0.12 55 / 0)" />
                    </radialGradient>
                  </defs>

                  <g className="links">
                    {connections.map((connection) => {
                      const isHighlighted =
                        hoveredNode === connection.source.id || hoveredNode === connection.target.id;
                      const isCompletedConnection =
                        connection.source.status === 'completed' && connection.target.status === 'completed';

                      return (
                        <line
                          key={connection.id}
                          x1={connection.source.x}
                          y1={connection.source.y}
                          x2={connection.target.x}
                          y2={connection.target.y}
                          className={[
                            'network-link',
                            isHighlighted ? 'is-highlighted' : '',
                            isCompletedConnection ? 'is-completed' : '',
                          ].join(' ')}
                          strokeDasharray={connection.target.status === 'in_progress' ? '4 8' : undefined}
                        />
                      );
                    })}
                  </g>

                  <g className="nodes">
                    {positionedCourses.map((course) => {
                      const isHovered = hoveredNode === course.id;
                      return (
                        <g
                          key={course.id}
                          className={`course-node course-node-${course.status} ${isHovered ? 'is-hovered' : ''}`}
                          transform={`translate(${course.x}, ${course.y})`}
                          role="link"
                          tabIndex={0}
                          aria-label={`${course.title}，${statusLabel(course.status)}`}
                          onClick={() => handleCourseClick(course)}
                          onKeyDown={(event) => handleCourseKeyDown(event, course)}
                          onMouseEnter={() => setHoveredNode(course.id)}
                          onMouseLeave={() => setHoveredNode(null)}
                          onFocus={() => setHoveredNode(course.id)}
                          onBlur={() => setHoveredNode(null)}
                        >
                          <title>{`${course.gradeLabel} · ${course.title}`}</title>
                          <circle className="node-glow" r="42" />
                          <circle className="node-shell" r="15" />
                          <circle className="node-core" r="7" />
                          <text y="-30" textAnchor="middle" className="node-text">
                            {truncateLabel(course.title)}
                          </text>
                          <text y="40" textAnchor="middle" className="node-meta">
                            {course.gradeLabel}
                          </text>
                          {qualityScores[course.id] && (
                            <g transform="translate(18, -18)">
                              <circle
                                r="8"
                                fill={
                                  qualityScores[course.id].overall >= 80
                                    ? 'oklch(75% 0.12 145)'
                                    : qualityScores[course.id].overall >= 60
                                      ? 'oklch(78% 0.12 85)'
                                      : 'oklch(65% 0.15 25)'
                                }
                              />
                              <text
                                textAnchor="middle"
                                dominantBaseline="central"
                                fill="oklch(99% 0 0)"
                                fontSize="8"
                                fontWeight="600"
                              >
                                {qualityScores[course.id].overall >= 80 ? '✓' : qualityScores[course.id].overall >= 60 ? '~' : '!'}
                              </text>
                            </g>
                          )}
                        </g>
                      );
                    })}
                  </g>
                </svg>

                {hoveredNode && qualityScores[hoveredNode] && (
                  <div
                    style={{
                      background: 'var(--glass-bg)',
                      backdropFilter: 'blur(12px)',
                      border: '1px solid var(--glass-border)',
                      borderRadius: 'var(--radius-lg)',
                      padding: 'var(--space-16)',
                      marginTop: 'var(--space-12)',
                    }}
                  >
                    <h4 style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: 'var(--space-8)' }}>资源质量评估</h4>
                    {[
                      { label: '内容准确性', value: qualityScores[hoveredNode].accuracy },
                      { label: '难度适配度', value: qualityScores[hoveredNode].difficulty_fit },
                      { label: '内容完整性', value: qualityScores[hoveredNode].completeness },
                    ].map((item) => (
                      <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-8)', fontSize: '0.8rem', marginBottom: 'var(--space-4)' }}>
                        <span style={{ minWidth: '5rem' }}>{item.label}</span>
                        <div style={{ flex: 1, height: '6px', background: 'var(--color-surface-inset)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ height: '100%', width: `${item.value}%`, background: 'var(--color-primary)', borderRadius: '3px' }} />
                        </div>
                        <span>{item.value}</span>
                      </div>
                    ))}
                    {qualityScores[hoveredNode].suggestions.length > 0 && (
                      <ul style={{ marginTop: 'var(--space-8)', fontSize: '0.75rem', color: 'var(--color-text-muted)', listStyle: 'disc', paddingLeft: 'var(--space-16)' }}>
                        {qualityScores[hoveredNode].suggestions.map((s, i) => (
                          <li key={i}>{s}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                )}

                {positionedCourses.length === 0 ? (
                  <div className="empty-state" role="status">
                    <span aria-hidden="true">*</span>
                    <p>画像评估尚未完成，请先进行冷启动评估生成你专属的学业树。</p>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </section>

        <section className="stats-section" aria-label="成森统计指标">
          <article className="stats-card tree-card">
            <header className="card-header">
              <span>// growth tree</span>
              <h3>成长树</h3>
            </header>
            <div className="growth-tree-panel">
              <GrowthTreeSVG stage={growthStage} />
            </div>
            <div className="tree-stage-label">
              <strong>{stageLabel}</strong>
              <span>{activeRate}%</span>
            </div>
          </article>

          <div className="stats-grid">
            <article className="stats-card mini-card">
              <span>已点亮叶片数</span>
              <div className="value">{completedCount}</div>
            </article>
            <article className="stats-card mini-card">
              <span>测验平均得分</span>
              <div className="value">{avgScore}分</div>
            </article>
            <article className="stats-card mini-card full-width">
              <span>专注学习时长</span>
              <div className="value">{focusedHours.toFixed(1)}小时</div>
            </article>
          </div>

        </section>

        <article className="stats-card timeline-card">
          <header className="card-header">
            <span>// milestones</span>
            <h3>成长里程</h3>
          </header>
          <div className="milestones-list">
            {milestones.map((milestone, index) => {
              const state = milestoneState(milestones, index);
              return (
                <div key={milestone.title} className={`milestone-item milestone-${state}`}>
                  <span className="milestone-dot" aria-hidden="true" />
                  <span className="date">{milestone.date}</span>
                  <div className="details">
                    <strong>{milestone.title}</strong>
                    <p>{milestone.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </article>
      </motion.main>
    </PageWrapper>
  );
}

const PageWrapper = styled.section`
  position: relative;
  min-block-size: 100svh;
  overflow-x: hidden;
  padding-block: calc(var(--space-80) + var(--space-48)) var(--space-64);
  padding-inline: var(--space-64);
  color: var(--color-text-primary);
  background-color: oklch(96% 0.02 75);
  background-image:
    radial-gradient(circle at 85% 95%, oklch(80% 0.05 320 / 0.8) 0%, transparent 55%),
    radial-gradient(circle at 10% 75%, oklch(85% 0.1 55 / 0.8) 0%, transparent 65%),
    radial-gradient(circle at 15% 15%, oklch(96% 0.04 75 / 0.6) 0%, transparent 50%),
    linear-gradient(135deg, oklch(96% 0.03 75) 0%, oklch(93% 0.04 70) 100%);

  .forest-ambient-sun {
    position: absolute;
    inset-block-start: calc(var(--space-120) * -1);
    inset-inline-end: calc(var(--space-120) * -1);
    inline-size: min(calc(var(--space-120) * 4), 72vw);
    block-size: min(calc(var(--space-120) * 4), 72vw);
    border-radius: var(--radius-full);
    background: linear-gradient(135deg, oklch(98% 0.05 85), oklch(84% 0.14 55));
    filter: blur(2px);
    box-shadow:
      0 0 var(--space-120) 0 oklch(88% 0.12 60 / 0.4),
      inset calc(var(--space-24) * -1) calc(var(--space-24) * -1) var(--space-64) 0 oklch(75% 0.16 45 / 0.15);
    z-index: 0;
    pointer-events: none;
    animation: forest-sun-breathe 15000ms ease-in-out infinite alternate;
  }

  .forest-paper-canvas {
    position: absolute;
    inset: 0;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noiseFilter'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noiseFilter)'/%3E%3C/svg%3E");
    opacity: 0.06;
    mix-blend-mode: multiply;
    pointer-events: none;
    z-index: 1;
  }

  .canopy-layout {
    position: relative;
    z-index: 10;
    display: grid;
    grid-template-columns: minmax(0, 1.72fr) minmax(calc(var(--space-80) * 4), 0.88fr);
    grid-template-areas:
      "graph stats"
      "timeline timeline";
    align-items: start;
    gap: var(--gap-lg);
    inline-size: min(1520px, 100%);
    margin-inline: auto;
  }

  .graph-section,
  .stats-card {
    border: 1px solid var(--glass-border);
    border-radius: var(--radius-lg);
    background: var(--glass-bg);
    box-shadow: var(--shadow-sm);
    backdrop-filter: var(--glass-blur);
  }

  .graph-section {
    grid-area: graph;
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
    padding: var(--space-40);
    min-block-size: min(760px, calc(100svh - var(--space-120)));
  }

  .section-header,
  .card-header {
    display: grid;
    gap: var(--space-8);
  }

  .section-header span,
  .card-header span {
    color: var(--color-primary);
    font-size: var(--text-caption);
    font-weight: var(--font-weight-medium);
    line-height: 1.4;
  }

  .section-header h2,
  .card-header h3 {
    margin: 0;
    color: var(--color-secondary);
    font-weight: var(--font-weight-medium);
    letter-spacing: 0;
  }

  .section-header h2 {
    font-size: var(--text-h2);
    line-height: 1.3;
  }

  .section-header p,
  .milestone-item p,
  .feedback-panel span,
  .empty-state p {
    margin: 0;
    color: var(--color-text-secondary);
    font-size: var(--text-body-sm);
    line-height: 1.6;
    text-wrap: pretty;
  }

  .network-container {
    flex: 1;
    position: relative;
    width: 100%;
    min-block-size: calc(var(--space-120) * 4.5);
    border-radius: var(--radius-md);
    background: var(--color-surface-inset);
    border: 1px solid var(--color-border);
    overflow: hidden;
  }

  .network-svg {
    width: 100%;
    height: 100%;
  }

  .network-link {
    stroke: oklch(42% 0.035 235 / 0.18);
    stroke-width: 2.25;
    opacity: 0.72;
  }

  .network-link.is-completed {
    stroke: oklch(75% 0.09 135 / 0.48);
  }

  .network-link.is-highlighted {
    stroke: var(--color-primary);
    opacity: 1;
  }

  .course-node {
    cursor: pointer;
    outline: none;
  }

  .course-node .node-glow,
  .course-node .node-shell,
  .course-node .node-core {
    transform-box: fill-box;
    transform-origin: center;
    transition:
      transform var(--duration-lazy-hover) var(--ease-lazy),
      opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  .course-node .node-glow {
    opacity: 0;
  }

  .course-node-completed .node-glow {
    fill: url(#completed-glow);
    opacity: 0.9;
  }

  .course-node-in_progress .node-glow {
    fill: url(#inprogress-glow);
    opacity: 0.9;
    animation: canopy-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  }

  .course-node-locked .node-glow {
    fill: oklch(80% 0.02 240 / 0.18);
    opacity: 0.34;
  }

  .course-node-completed .node-shell {
    fill: oklch(75% 0.09 135);
    stroke: oklch(66% 0.09 135);
  }

  .course-node-in_progress .node-shell {
    fill: var(--color-primary);
    stroke: var(--color-primary-hover);
  }

  .course-node-locked .node-shell {
    fill: oklch(90% 0.01 240);
    stroke: oklch(80% 0.02 240);
  }

  .node-shell {
    stroke-width: 2;
  }

  .node-core {
    fill: var(--color-surface-raised);
    opacity: 0.84;
  }

  .course-node.is-hovered .node-glow,
  .course-node:focus-visible .node-glow {
    transform: scale(1.22);
    opacity: 1;
  }

  .course-node.is-hovered .node-shell,
  .course-node:focus-visible .node-shell {
    transform: scale(1.12);
  }

  .node-text,
  .node-meta {
    fill: var(--color-text-primary);
    font-family: var(--font-body);
    letter-spacing: 0;
    pointer-events: none;
    transition: opacity var(--duration-lazy-hover) var(--ease-lazy);
  }

  .node-text {
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    opacity: 0.78;
  }

  .node-meta {
    font-size: var(--text-caption);
    fill: var(--color-text-muted);
    opacity: 0.7;
  }

  .course-node.is-hovered .node-text,
  .course-node:focus-visible .node-text,
  .course-node.is-hovered .node-meta,
  .course-node:focus-visible .node-meta {
    opacity: 1;
  }

  .feedback-panel,
  .empty-state {
    position: absolute;
    inset: var(--space-24);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-12);
    border-radius: var(--radius-md);
    background: oklch(97% 0.02 75 / 0.72);
    text-align: center;
    backdrop-filter: var(--glass-blur);
  }

  .feedback-panel p {
    margin: 0;
    color: var(--color-secondary);
    font-size: var(--text-h5);
    font-weight: var(--font-weight-medium);
  }

  .empty-state span {
    display: grid;
    place-items: center;
    inline-size: var(--space-48);
    block-size: var(--space-48);
    border-radius: var(--radius-full);
    background: var(--color-primary-soft);
    color: var(--color-primary);
    font-size: var(--text-h3);
    font-weight: var(--font-weight-medium);
  }

  .empty-state p {
    max-inline-size: calc(var(--space-120) * 3);
  }

  .stats-section {
    grid-area: stats;
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
  }

  .stats-card {
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
    padding: var(--space-32);
  }

  .growth-tree-panel {
    position: relative;
    display: grid;
    place-items: center;
    inline-size: min(100%, calc(var(--space-120) * 3.2));
    margin-inline: auto;
    aspect-ratio: 1;
    border-radius: var(--radius-full);
    background: var(--color-surface-inset);
    border: 1px solid var(--color-border);
    box-shadow: var(--shadow-inset);
    overflow: hidden;
  }

  .growth-tree-svg {
    inline-size: 88%;
    block-size: 88%;
    overflow: visible;
  }

  .tree-stage {
    opacity: 0;
    transform-box: fill-box;
    transform-origin: center;
    transform: translateY(var(--space-12)) scale(0.96);
    transition:
      opacity var(--duration-reveal) var(--ease-editorial),
      transform var(--duration-reveal) var(--ease-editorial);
  }

  .tree-stage.is-visible {
    opacity: 1;
    transform: translateY(0) scale(1);
  }

  .canopy-breathe {
    animation: canopy-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  }

  .tree-stage.canopy-breathe {
    animation: none;
  }

  .tree-stage.is-visible.canopy-breathe {
    animation: canopy-breathe var(--duration-breathe) var(--ease-breathe) infinite alternate;
  }

  .tree-stage-label {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-12);
    border-radius: var(--radius-full);
    background: oklch(99% 0.01 80 / 0.72);
    border: 1px solid var(--glass-border);
    padding: var(--space-8) var(--space-16);
    backdrop-filter: var(--glass-blur);
  }

  .tree-stage-label strong,
  .tree-stage-label span {
    font-size: var(--text-caption);
    color: var(--color-secondary);
    font-weight: var(--font-weight-medium);
  }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--gap-md);
  }

  .mini-card {
    padding: var(--space-24);
    gap: var(--space-8);
  }

  .mini-card span {
    font-size: var(--text-caption);
    color: var(--color-text-secondary);
  }

  .mini-card .value {
    font-size: var(--text-h3);
    color: var(--color-secondary);
    font-weight: var(--font-weight-medium);
    line-height: 1.2;
  }

  .full-width {
    grid-column: span 2;
  }

  .timeline-card {
    grid-area: timeline;
  }

  .milestones-list {
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    gap: var(--gap-md);
  }

  .milestone-item {
    position: relative;
    display: grid;
    grid-template-columns: var(--space-24) minmax(0, 1fr);
    gap: var(--space-12);
    align-items: flex-start;
    align-content: start;
    padding-block-start: var(--space-40);
  }

  .milestone-item::before {
    content: '';
    position: absolute;
    inset-block-start: var(--space-12);
    inset-inline-start: var(--space-24);
    inset-inline-end: calc(var(--gap-md) * -1);
    border-block-start: 1px dashed oklch(84% 0.03 73);
  }

  .milestone-item:last-child::before {
    display: none;
  }

  .milestone-dot {
    inline-size: var(--space-24);
    block-size: var(--space-24);
    border-radius: var(--radius-full);
    background: var(--color-surface-inset);
    border: 1px solid var(--color-border);
  }

  .milestone-reached .milestone-dot,
  .milestone-active .milestone-dot {
    background: var(--color-accent-sage);
    border-color: var(--color-accent-sage);
  }

  .milestone-active .milestone-dot {
    box-shadow: var(--shadow-glow);
  }

  .milestone-locked {
    opacity: 0.58;
  }

  .milestone-item .date {
    grid-column: 2;
    width: fit-content;
    font-size: var(--text-caption);
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
    font-family: var(--font-mono);
    background: var(--color-surface-inset);
    padding: var(--space-4) var(--space-8);
    border-radius: var(--radius-sm);
    white-space: nowrap;
  }

  .milestone-item .details strong {
    display: block;
    margin-block-end: var(--space-4);
    color: var(--color-text-primary);
    font-size: var(--text-body-sm);
    font-weight: var(--font-weight-medium);
    line-height: 1.5;
  }

  .milestone-item .details {
    grid-column: 2;
  }

  @keyframes canopy-breathe {
    from {
      transform: scale(0.98);
      opacity: 0.72;
    }
    to {
      transform: scale(1.03);
      opacity: 0.9;
    }
  }

  @keyframes forest-sun-breathe {
    from {
      transform: scale(0.98) translate(var(--space-4), calc(var(--space-4) * -1));
    }
    to {
      transform: scale(1.02) translate(calc(var(--space-4) * -1), var(--space-4));
    }
  }

  @media (max-width: 960px) {
    .canopy-layout {
      grid-template-columns: 1fr;
      grid-template-areas:
        "graph"
        "stats"
        "timeline";
    }

    .graph-section {
      min-block-size: auto;
    }

    .network-container {
      min-block-size: auto;
      aspect-ratio: 3 / 2;
    }

    .milestones-list {
      grid-template-columns: 1fr;
    }

    .milestone-item {
      grid-template-columns: var(--space-24) auto 1fr;
      padding-block-start: 0;
    }

    .milestone-item::before {
      inset-block-start: var(--space-24);
      inset-block-end: calc(var(--space-16) * -1);
      inset-inline-start: var(--space-12);
      inset-inline-end: auto;
      transform: translateX(-50%);
      border-block-start: none;
      border-inline-start: 1px dashed oklch(84% 0.03 73);
    }

    .milestone-item .date,
    .milestone-item .details {
      grid-column: auto;
    }
  }

  @media (max-width: 767px) {
    padding-block: calc(var(--space-80) + var(--space-24)) var(--space-48);
    padding-inline: var(--space-24);

    .graph-section,
    .stats-card {
      padding: var(--space-24);
    }

    .stats-grid {
      grid-template-columns: 1fr;
    }

    .full-width {
      grid-column: auto;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .forest-ambient-sun,
    .canopy-breathe,
    .course-node .node-glow,
    .course-node .node-shell,
    .course-node .node-core,
    .tree-stage {
      animation: none;
      transition: opacity var(--duration-instant) ease;
      transform: none;
    }
  }
`;
