import React, { useState } from 'react';
import styled from 'styled-components';
import { motion, AnimatePresence } from 'framer-motion';
import { motionTokens } from '../../styles/motion-tokens';

interface CourseNode {
  id: string;
  title: string;
  grade: 'Year 1' | 'Year 2' | 'Year 3' | 'Year 4';
  status: 'completed' | 'in_progress' | 'locked';
  score?: number;
  description: string;
  x: number;
  y: number;
  connections: string[];
}

const INITIAL_COURSES: CourseNode[] = [
  // Year 1 - Seed & Roots
  { id: 'c1', title: '计算思维与算法基础', grade: 'Year 1', status: 'completed', score: 92, description: '掌握程序逻辑的基本单元与算法复杂度分析。', x: 200, y: 150, connections: ['c2', 'c3'] },
  { id: 'c2', title: '数据结构与高级应用', grade: 'Year 1', status: 'completed', score: 88, description: '树、图及哈希结构在解决实际工程问题中的应用。', x: 150, y: 280, connections: ['c4'] },
  { id: 'c3', title: 'Python 系统编程', grade: 'Year 1', status: 'completed', score: 95, description: '熟练运用异步编程、元编程及高并发开发模型。', x: 280, y: 240, connections: ['c4', 'c5'] },

  // Year 2 - Stem & Sprout
  { id: 'c4', title: '网络协议与微服务架构', grade: 'Year 2', status: 'completed', score: 90, description: '深入 TCP/IP、HTTP/3 及现代服务网格的通信原理。', x: 380, y: 340, connections: ['c6'] },
  { id: 'c5', title: '数据库内核与并发控制', grade: 'Year 2', status: 'in_progress', description: '探索 SQL 解析、锁机制与事务隔离级别的底层实现。', x: 480, y: 220, connections: ['c7'] },
  { id: 'c6', title: '机器学习算法导论', grade: 'Year 2', status: 'completed', score: 85, description: '从线性回归到深度神经网络的数学推导与代码实现。', x: 350, y: 480, connections: ['c8'] },

  // Year 3 - Branch & Leaf
  { id: 'c7', title: '大语言模型微调与 RAG', grade: 'Year 3', status: 'in_progress', description: '研究提示词工程、向量检索与模型参数高效微调技术。', x: 620, y: 200, connections: ['c9'] },
  { id: 'c8', title: '智能体(Agent) 决策流设计', grade: 'Year 3', status: 'in_progress', description: '利用 ReAct 框架、多分支反思树设计自主规划智能体。', x: 550, y: 450, connections: ['c9', 'c10'] },

  // Year 4 - Canopy & Bloom
  { id: 'c9', title: '多智能体协同与 Supervisor 架构', grade: 'Year 4', status: 'locked', description: '掌握复杂智能体网络的分级调度与共识协议。', x: 750, y: 320, connections: [] },
  { id: 'c10', title: '大模型系统化部署与端侧优化', grade: 'Year 4', status: 'locked', description: '在硬件受限设备上运行高效模型量化与分布式推理。', x: 700, y: 490, connections: [] },
];

const MILESTONES = [
  { date: '2026.06.01', title: '萌芽期 - 冷启动完成', desc: '成功分析用户画像并生成专属树苗' },
  { date: '2026.06.04', title: '繁枝期 - 点亮第一门选课', desc: '成功生成完整四学年路径树分支' },
  { date: '2026.06.07', title: '叶茂期 - 首次测验高分通关', desc: '《计算思维与算法基础》测验获得92分' },
  { date: '2026.06.09', title: '成林期 - 开启 AI 多模态手写', desc: '首次使用画板草图追问 AI 完成解题' },
];

export function CanopyPage() {
  const [courses, setCourses] = useState<CourseNode[]>(INITIAL_COURSES);
  const [selectedCourse, setSelectedCourse] = useState<CourseNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Statistics
  const completedCount = courses.filter((c) => c.status === 'completed').length;
  const activeRate = Math.round((completedCount / courses.length) * 100);
  const avgScore = Math.round(
    courses
      .filter((c) => c.status === 'completed' && c.score !== undefined)
      .reduce((acc, c) => acc + (c.score ?? 0), 0) / (completedCount || 1),
  );

  return (
    <PageWrapper aria-label="成森知识雨林页面">
      <div className="forest-ambient-sun" aria-hidden="true" />

      <main className="canopy-layout">
        {/* Left Side: Interactive Network Graph */}
        <section className="graph-section" aria-label="知识雨林图谱">
          <header className="section-header">
            <span>// knowledge canopy</span>
            <h2>知识雨林图谱</h2>
            <p>展示四学年学习节点的互联网络，星光相接代表知识序列的蔓延。</p>
          </header>

          <div className="network-container">
            <svg viewBox="0 0 900 600" className="network-svg">
              <defs>
                {/* Node gradient effects */}
                <radialGradient id="completed-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="oklch(78% 0.06 140 / 0.4)" />
                  <stop offset="100%" stopColor="oklch(78% 0.06 140 / 0)" />
                </radialGradient>
                <radialGradient id="inprogress-glow" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="oklch(76% 0.11 75 / 0.4)" />
                  <stop offset="100%" stopColor="oklch(76% 0.11 75 / 0)" />
                </radialGradient>
              </defs>

              {/* Connections (Lines) */}
              <g className="links">
                {courses.map((source) =>
                  source.connections.map((targetId) => {
                    const target = courses.find((c) => c.id === targetId);
                    if (!target) return null;
                    const isHighlighted =
                      hoveredNode === source.id || hoveredNode === target.id;
                    const isCompletedConnection =
                      source.status === 'completed' && target.status === 'completed';

                    return (
                      <line
                        key={`${source.id}-${targetId}`}
                        x1={source.x}
                        y1={source.y}
                        x2={target.x}
                        y2={target.y}
                        stroke={
                          isHighlighted
                            ? 'var(--color-primary)'
                            : isCompletedConnection
                            ? 'oklch(78% 0.06 140 / 0.4)'
                            : 'oklch(80% 0.02 240 / 0.12)'
                        }
                        strokeWidth={isHighlighted ? 2.5 : isCompletedConnection ? 2 : 1}
                        strokeDasharray={source.status === 'in_progress' ? '4,4' : undefined}
                        style={{ transition: 'stroke 0.3s, stroke-width 0.3s, all 0.3s ease' }}
                      />
                    );
                  })
                )}
              </g>

              {/* Nodes */}
              <g className="nodes">
                {courses.map((course) => {
                  const isHovered = hoveredNode === course.id;
                  const isSelected = selectedCourse?.id === course.id;

                  let fill = 'oklch(90% 0.01 240)'; // Locked (neutral)
                  let glowId = '';
                  let stroke = 'oklch(80% 0.02 240)';

                  if (course.status === 'completed') {
                    fill = 'oklch(78% 0.06 140)'; // Sage Green
                    glowId = 'completed-glow';
                    stroke = 'oklch(74% 0.08 140 / 0.6)';
                  } else if (course.status === 'in_progress') {
                    fill = 'oklch(76% 0.11 75)'; // Soft Coral/Orange
                    glowId = 'inprogress-glow';
                    stroke = 'oklch(72% 0.12 75 / 0.6)';
                  }

                  return (
                    <g
                      key={course.id}
                      transform={`translate(${course.x}, ${course.y})`}
                      onClick={() => setSelectedCourse(course)}
                      onMouseEnter={() => setHoveredNode(course.id)}
                      onMouseLeave={() => setHoveredNode(null)}
                      style={{ cursor: 'pointer' }}
                    >
                      {/* Glow Behind */}
                      {glowId && (
                        <circle
                          r={30}
                          fill={`url(#${glowId})`}
                          className="node-glow"
                          style={{
                            transform: isHovered || isSelected ? 'scale(1.3)' : 'scale(1)',
                            transition: 'transform 0.4s cubic-bezier(0.25, 1, 0.5, 1)',
                          }}
                        />
                      )}

                      {/* Main Node Circle */}
                      <circle
                        r={isHovered || isSelected ? 12 : 9}
                        fill={fill}
                        stroke={stroke}
                        strokeWidth={isHovered || isSelected ? 3 : 1.5}
                        style={{
                          transition: 'r 0.4s cubic-bezier(0.25, 1, 0.5, 1), stroke-width 0.4s',
                        }}
                      />

                      {/* Title Tag */}
                      <text
                        y={-20}
                        textAnchor="middle"
                        fill="var(--color-text-primary)"
                        fontSize="11px"
                        fontFamily="var(--font-body)"
                        className="node-text"
                        style={{
                          opacity: isHovered || isSelected ? 1 : 0.72,
                          fontWeight: isHovered || isSelected ? 500 : 400,
                          transition: 'opacity 0.3s, font-weight 0.3s',
                        }}
                      >
                        {course.title}
                      </text>
                    </g>
                  );
                })}
              </g>
            </svg>

            {/* Course Detail Card (Framer Motion overlay) */}
            <AnimatePresence>
              {selectedCourse && (
                <motion.div
                  className="course-overlay"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -12 }}
                  transition={motionTokens.lazy}
                >
                  <div className="overlay-header">
                    <span className="overlay-kicker">{selectedCourse.grade}</span>
                    <button onClick={() => setSelectedCourse(null)}>✕</button>
                  </div>
                  <h3>{selectedCourse.title}</h3>
                  <p className="overlay-desc">{selectedCourse.description}</p>
                  <div className="overlay-status-row">
                    <span className={`status-badge ${selectedCourse.status}`}>
                      {selectedCourse.status === 'completed'
                        ? '已点亮'
                        : selectedCourse.status === 'in_progress'
                        ? '生长中'
                        : '锁定中'}
                    </span>
                    {selectedCourse.score !== undefined && (
                      <span className="overlay-score">测验得分: {selectedCourse.score}</span>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </section>

        {/* Right Side: Growth Rings & Stats Dashboard */}
        <section className="stats-section" aria-label="年轮与统计指标">
          {/* Growth Rings */}
          <article className="stats-card rings-card">
            <header className="card-header">
              <span>// growth rings</span>
              <h3>成长年轮</h3>
            </header>
            <div className="rings-visualizer">
              <svg viewBox="0 0 200 200" className="rings-svg">
                {/* Tree Rings representing completed courses */}
                <circle cx="100" cy="100" r="90" fill="none" stroke="oklch(80% 0.02 240 / 0.06)" strokeWidth="6" />
                <circle cx="100" cy="100" r="72" fill="none" stroke="oklch(80% 0.02 240 / 0.1)" strokeWidth="5" />
                <circle cx="100" cy="100" r="54" fill="none" stroke="oklch(80% 0.02 240 / 0.16)" strokeWidth="4" />
                <circle cx="100" cy="100" r="36" fill="none" stroke="oklch(80% 0.02 240 / 0.22)" strokeWidth="3" />
                <circle cx="100" cy="100" r="18" fill="none" stroke="oklch(80% 0.02 240 / 0.28)" strokeWidth="2.5" />

                {/* Animated progress pointer */}
                <motion.circle
                  cx="100"
                  cy="100"
                  r="54"
                  fill="none"
                  stroke="var(--color-primary)"
                  strokeWidth="2.5"
                  strokeDasharray="339"
                  initial={{ strokeDashoffset: 339 }}
                  animate={{ strokeDashoffset: 339 - (339 * activeRate) / 100 }}
                  transition={{ duration: 1.5, ease: 'easeOut' }}
                />
              </svg>
              <div className="rings-label">
                <span className="percentage">{activeRate}%</span>
                <span className="desc">雨林点亮率</span>
              </div>
            </div>
            <div className="milestones-list">
              {MILESTONES.map((m, idx) => (
                <div key={idx} className="milestone-item">
                  <span className="date">{m.date}</span>
                  <div className="details">
                    <strong>{m.title}</strong>
                    <p>{m.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </article>

          {/* Stats Grid */}
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
              <div className="value">48.5小时</div>
            </article>
          </div>
        </section>
      </main>
    </PageWrapper>
  );
}

const PageWrapper = styled.section`
  position: relative;
  min-block-size: 100svh;
  overflow-x: hidden;
  padding-block: calc(var(--space-80) + var(--space-48)) var(--space-64);
  padding-inline: var(--section-padding-x, var(--space-64));
  color: var(--color-text-primary);
  background:
    radial-gradient(circle at 18% 10%, oklch(99% 0.02 80 / 0.48), transparent 32%),
    radial-gradient(circle at 86% 16%, oklch(84% 0.12 63 / 0.22), transparent 34%),
    var(--gradient-paper);

  .forest-ambient-sun {
    position: absolute;
    inset-block-start: calc(var(--space-64) * -1);
    inset-inline-end: calc(var(--space-64) * -1);
    inline-size: min(calc(var(--space-120) * 4), 72vw);
    aspect-ratio: 1;
    border-radius: var(--radius-full);
    background: var(--effect-sun-glow);
    filter: var(--effect-blur-sun);
    opacity: 0.68;
    pointer-events: none;
  }

  .canopy-layout {
    position: relative;
    z-index: 1;
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(320px, 380px);
    gap: var(--gap-lg);
    inline-size: min(1180px, 100%);
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
    display: flex;
    flex-direction: column;
    gap: var(--gap-md);
    padding: var(--space-40);
    position: relative;
  }

  .section-header {
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
  .overlay-desc,
  .milestone-item p {
    margin: 0;
    color: var(--color-text-secondary);
    font-size: var(--text-body-sm);
    line-height: 1.6;
    text-wrap: pretty;
  }

  .network-container {
    position: relative;
    width: 100%;
    aspect-ratio: 9/6;
    border-radius: var(--radius-md);
    background: var(--color-surface-inset);
    border: 1px solid var(--color-border);
    overflow: hidden;
  }

  .network-svg {
    width: 100%;
    height: 100%;
  }

  .course-overlay {
    position: absolute;
    bottom: var(--space-16);
    left: var(--space-16);
    right: var(--space-16);
    padding: var(--space-24);
    background: var(--color-surface);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-md);
    box-shadow: var(--shadow-md);
    display: flex;
    flex-direction: column;
    gap: var(--space-12);
  }

  .overlay-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .overlay-header button {
    background: none;
    border: none;
    cursor: pointer;
    font-size: var(--text-body);
    color: var(--color-text-secondary);
  }

  .overlay-header button:hover {
    color: var(--color-text-primary);
  }

  .overlay-kicker {
    font-size: var(--text-caption);
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
  }

  .course-overlay h3 {
    margin: 0;
    font-size: var(--text-h4);
    color: var(--color-secondary);
  }

  .overlay-status-row {
    display: flex;
    gap: var(--space-12);
    align-items: center;
  }

  .status-badge {
    padding: var(--space-4) var(--space-12);
    border-radius: var(--radius-full);
    font-size: var(--text-caption);
    font-weight: var(--font-weight-medium);
  }

  .status-badge.completed {
    background: oklch(78% 0.06 140 / 0.12);
    color: oklch(74% 0.08 140);
  }

  .status-badge.in_progress {
    background: oklch(76% 0.11 75 / 0.12);
    color: oklch(72% 0.12 75);
  }

  .status-badge.locked {
    background: var(--color-surface-inset);
    color: var(--color-text-secondary);
  }

  .overlay-score {
    font-size: var(--text-caption);
    color: var(--color-text-secondary);
  }

  .stats-section {
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

  .rings-visualizer {
    position: relative;
    width: 160px;
    height: 160px;
    margin: 0 auto;
  }

  .rings-svg {
    width: 100%;
    height: 100%;
    transform: rotate(-90deg);
  }

  .rings-label {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
  }

  .rings-label .percentage {
    font-size: var(--text-h2);
    font-weight: var(--font-weight-medium);
    color: var(--color-secondary);
    line-height: 1;
  }

  .rings-label .desc {
    font-size: var(--text-caption);
    color: var(--color-text-secondary);
    margin-block-start: var(--space-4);
  }

  .milestones-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-16);
    border-block-start: 1px solid var(--color-border);
    padding-block-start: var(--space-20);
  }

  .milestone-item {
    display: flex;
    gap: var(--space-12);
    align-items: flex-start;
  }

  .milestone-item .date {
    font-size: var(--text-caption);
    color: var(--color-primary);
    font-weight: var(--font-weight-medium);
    font-family: var(--font-code);
    background: var(--color-surface-inset);
    padding: var(--space-4) var(--space-8);
    border-radius: var(--radius-sm);
    white-space: nowrap;
  }

  .milestone-item .details strong {
    font-size: var(--text-body-sm);
    color: var(--color-text-primary);
    display: block;
    margin-block-end: var(--space-4);
  }

  .stats-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--gap-md);
  }

  .mini-card {
    padding: var(--space-20);
    display: flex;
    flex-direction: column;
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
  }

  .full-width {
    grid-column: span 2;
  }

  @media (max-width: 960px) {
    .canopy-layout {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 767px) {
    padding-block: calc(var(--space-80) + var(--space-24)) var(--space-48);
    padding-inline: var(--space-24);

    .graph-section,
    .stats-card {
      padding: var(--space-24);
    }
  }
`;
