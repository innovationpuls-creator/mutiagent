import { useEffect } from 'react';
import { useAnimate, motion, stagger, useReducedMotion } from 'framer-motion';
import './AgentSandtable.css';

interface AgentSandtableProps {
  setStageIndex: (index: number) => void;
}

/* ═══ 终端流式字符组件 ═══ */
function TermLine({ id, prefix, text }: { id: string; prefix: string; text: string }) {
  const full = prefix + text;
  return (
    <div
      id={id}
      className="term-line hide-on-reset"
      style={{ opacity: 0, display: 'flex', flexWrap: 'wrap', minHeight: '16px', alignItems: 'center' }}
    >
      {full.split('').map((c, i) => (
        <span
          key={i}
          className={`term-char term-char-${id}`}
          style={{
            opacity: 0,
            display: 'inline-block',
            fontFamily: 'var(--font-mono, monospace)',
            fontSize: '10px',
            color: i < prefix.length ? 'oklch(70% 0.06 45)' : 'var(--color-text-secondary)',
            letterSpacing: '0.01em',
          }}
        >
          {c === ' ' ? '\u00A0' : c}
        </span>
      ))}
    </div>
  );
}

/* ═══ 坐标系统 ═══
 * CSS: 百分比定位 (left/top %)
 * SVG: viewBox 0 0 1000 1000, preserveAspectRatio="none"
 * 映射: svgX = percentage × 10, svgY = percentage × 10
 * 这样 SVG 坐标严格对齐 CSS 百分比
 */
const NODES = {
  user:     { left: '8%',  top: '27%', sx: 80,  sy: 270 },
  planner:  { left: '27%', top: '27%', sx: 270, sy: 270 },
  research: { left: '56%', top: '27%', sx: 560, sy: 270 },
  path:     { left: '80%', top: '27%', sx: 800, sy: 270 },
} as const;

// Sub-agent 弹射 (从 Researcher 中心出发的像素偏移)
const SUBS = [
  { id: 'sub-0', label: 'Google', dx: -48, dy: -60, floatClass: 'sub-float-1' },
  { id: 'sub-1', label: 'arXiv',  dx: 0,   dy: -75, floatClass: 'sub-float-2' },
  { id: 'sub-2', label: 'GitHub', dx: 48,  dy: -60, floatClass: 'sub-float-3' },
] as const;

// Tree topology 分支 (从 Path Engine 中心出发的像素偏移)
const BRANCHES = [
  { id: 'leaf-0', label: '单元一', dx: 55, dy: -50 },
  { id: 'leaf-1', label: '单元二', dx: 70, dy: 0 },
  { id: 'leaf-2', label: '单元三', dx: 55, dy: 50 },
] as const;

// Planner 任务拆解项
const TASKS = ['拆解用户意图', '识别知识边界', '分配执行序列'];

/* ═══ 共享样式 ═══ */
const nodeBase: React.CSSProperties = {
  position: 'relative',
  display: 'flex',
  flexDirection: 'column',
  padding: '10px 12px',
  backgroundColor: 'var(--color-surface-elevated)',
  border: '1px solid var(--color-border-subtle)',
  borderRadius: 'var(--radius-lg)',
  backdropFilter: 'blur(16px)',
  boxShadow: 'var(--shadow-sm)',
};

const dot = (color: string): React.CSSProperties => ({
  width: 5, height: 5, borderRadius: '50%',
  backgroundColor: color, boxShadow: `0 0 8px ${color}`, flexShrink: 0,
});

/* ═══ 主组件 ═══ */
export function AgentSandtable({ setStageIndex }: AgentSandtableProps) {
  const [scope, animate] = useAnimate();
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    const runAnimate = (...args: Parameters<typeof animate>) => {
      if (!scope.current) return;
      animate(...args);
    };

    /* ── 无障碍：prefers-reduced-motion 静态降级 ── */
    if (reduceMotion) {
      runAnimate('.node-el', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0 });
      runAnimate('.task-item', { opacity: 1, x: 0 }, { duration: 0 });
      runAnimate('.check-icon', { opacity: 1, scale: 1 }, { duration: 0 });
      runAnimate('.sandtable-line', { pathLength: 1 }, { duration: 0 });
      SUBS.forEach(s => runAnimate(`#${s.id}`, { x: s.dx, y: s.dy, scale: 1, opacity: 1 }, { duration: 0 }));
      runAnimate('.sub-line-path', { opacity: 0.4 }, { duration: 0 });
      runAnimate('#tree-trunk', { pathLength: 1 }, { duration: 0 });
      runAnimate('.tree-branch', { pathLength: 1 }, { duration: 0 });
      BRANCHES.forEach(b => runAnimate(`#${b.id}`, { x: b.dx, y: b.dy, scale: 1, opacity: 1 }, { duration: 0 }));
      runAnimate('.term-line', { opacity: 1 }, { duration: 0 });
      runAnimate('.term-char', { opacity: 1 }, { duration: 0 });
      runAnimate('.terminal-cursor', { opacity: 1 }, { duration: 0 });
      return;
    }

    let alive = true;
    const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

    const run = async () => {
      const ed: [number, number, number, number] = [0.4, 0, 0.2, 1];

      await wait(2600);

      while (alive) {
        /* ════════════ RESET ════════════ */
        runAnimate('.node-el', { opacity: 0, filter: 'blur(10px)', scale: 0.88 }, { duration: 0 });
        runAnimate('.task-item', { opacity: 0, x: -10 }, { duration: 0 });
        runAnimate('.check-icon', { opacity: 0, scale: 0 }, { duration: 0 });
        runAnimate('.sandtable-line', { pathLength: 0 }, { duration: 0 });
        runAnimate('.sub-dot', { opacity: 0, scale: 0, x: 0, y: 0 }, { duration: 0 });
        runAnimate('.sub-line-path', { opacity: 0 }, { duration: 0 });
        runAnimate('#tree-trunk', { pathLength: 0 }, { duration: 0 });
        runAnimate('.tree-branch', { pathLength: 0 }, { duration: 0 });
        runAnimate('.tree-leaf', { opacity: 0, scale: 0, x: 0, y: 0 }, { duration: 0 });
        runAnimate('.term-line', { opacity: 0 }, { duration: 0 });
        runAnimate('.term-char', { opacity: 0 }, { duration: 0 });
        runAnimate('.terminal-cursor', { opacity: 0 }, { duration: 0 });
        runAnimate('#pulse-line', { opacity: 0, pathLength: 0, pathOffset: 0 }, { duration: 0 });

        await wait(350);
        if (!alive) break;

        /* ════════════ 0.35s: USER INPUT ════════════ */
        runAnimate('#user-input', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.7, ease: ed });
        await wait(600);
        if (!alive) break;

        /* ════════════ PLANNER — 任务拆解清单 ════════════ */
        setStageIndex(0);

        // 终端 Line 1: 极速逐字流淌 (与标题 AnimatePresence 同步触发)
        runAnimate('#term-1', { opacity: 1 }, { duration: 0.01 });
        runAnimate('.term-char-term-1', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        runAnimate('.terminal-cursor', { opacity: 1 }, { duration: 0.01 });

        runAnimate('#line-0', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(600);
        runAnimate('#planner-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(860);

        // 任务项依次滑入
        runAnimate('.task-item', { opacity: 1, x: 0 }, { duration: 0.3, delay: stagger(0.16), ease: 'easeOut' });
        await wait(1250);

        // 打勾 ✓ 依次弹出
        runAnimate('.check-icon', { opacity: 1, scale: 1 }, { duration: 0.2, delay: stagger(0.2), ease: 'easeOut' });
        await wait(1350);

        // 终端 Line 2
        runAnimate('#term-2', { opacity: 1 }, { duration: 0.01 });
        runAnimate('.term-char-term-2', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        await wait(940);
        if (!alive) break;

        /* ════════════ RESEARCHER — 集群分裂 ════════════ */
        setStageIndex(1);

        // 终端 Line 3: 并行唤醒 (与标题 AnimatePresence 同步触发)
        runAnimate('#term-3', { opacity: 1 }, { duration: 0.01 });
        runAnimate('.term-char-term-3', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });

        runAnimate('#line-1', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(600);
        runAnimate('#researcher-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(700);

        // Sub-agents 从中心弹射 (近临界阻尼 spring — 丝滑落位, 零过冲)
        for (const s of SUBS) {
          runAnimate(`#${s.id}`, { x: s.dx, y: s.dy, scale: 1, opacity: 1 }, {
            type: 'spring', stiffness: 170, damping: 24,
          });
          await wait(95);
        }
        await wait(220);

        // 虚线连线淡入
        runAnimate('.sub-line-path', { opacity: 0.45 }, { duration: 0.4, delay: stagger(0.08), ease: 'easeOut' });

        // 终端 Line 4: 降维清洗 (具体数字)
        runAnimate('#term-4', { opacity: 1 }, { duration: 0.01 });
        runAnimate('.term-char-term-4', { opacity: 1 }, { duration: 0.01, delay: stagger(0.016) });
        await wait(1555);
        await wait(1640);
        if (!alive) break;

        /* ════════════ PATH ENGINE — 拓扑爆炸 ════════════ */
        setStageIndex(2);

        // 终端 Line 5: 路径收敛 (与标题 AnimatePresence 同步触发)
        runAnimate('#term-5', { opacity: 1 }, { duration: 0.01 });
        runAnimate('.term-char-term-5', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });

        // 标题先出，视觉动画 0.5s 后启动
        await wait(500);

        runAnimate('#line-2', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(600);
        runAnimate('#path-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(700);

        // 主干生长
        runAnimate('#tree-trunk', { pathLength: 1 }, { duration: 0.45, ease: 'easeOut' });
        await wait(500);

        // 三根分支藤蔓展开
        runAnimate('.tree-branch', { pathLength: 1 }, { duration: 0.35, delay: stagger(0.1), ease: 'easeOut' });
        await wait(500);

        // 叶子节点弹射 (近临界阻尼 — 舒展丝滑, 零过冲)
        for (const b of BRANCHES) {
          runAnimate(`#${b.id}`, { x: b.dx, y: b.dy, scale: 1, opacity: 1 }, {
            type: 'spring', stiffness: 190, damping: 25,
          });
          await wait(120);
        }

        await wait(1840);
        if (!alive) break;

        /* ════════════ 8.5s: 认知流光脉冲 ════════════ */
        runAnimate('#pulse-line', {
          opacity: [0, 0.8, 0.8, 0],
          pathLength: [0, 0.3, 0.3, 0],
          pathOffset: [0, 0, 0.7, 1],
        }, { duration: 2.5, times: [0, 0.2, 0.8, 1], ease: 'easeInOut' });
        await wait(2800);
        if (!alive) break;

        /* ════════════ 退场 (仅 opacity — 合规 docs/07) ════════════ */
        await runAnimate('.hide-on-reset', { opacity: 0 }, {
          duration: 1, ease: 'easeInOut', delay: stagger(0.02),
        });
        await wait(350);
      }
    };

    run();
    return () => { alive = false; };
  }, [animate, setStageIndex, reduceMotion]);

  /* ── SVG 路径计算 ── */
  const { user: u, planner: p, research: r, path: pe } = NODES;
  const line0 = `M ${u.sx} ${u.sy} L ${p.sx} ${p.sy}`;
  const line1 = `M ${p.sx} ${p.sy} C ${p.sx + 100} ${p.sy}, ${r.sx - 100} ${r.sy}, ${r.sx} ${r.sy}`;
  const line2 = `M ${r.sx} ${r.sy} C ${r.sx + 80} ${r.sy}, ${pe.sx - 80} ${pe.sy}, ${pe.sx} ${pe.sy}`;
  const fullPath = [
    `M ${u.sx} ${u.sy} L ${p.sx} ${p.sy}`,
    `C ${p.sx + 100} ${p.sy}, ${r.sx - 100} ${r.sy}, ${r.sx} ${r.sy}`,
    `C ${r.sx + 80} ${r.sy}, ${pe.sx - 80} ${pe.sy}, ${pe.sx} ${pe.sy}`,
  ].join(' ');

  // Tree 主干像素长度 (分支从主干末端扇出)
  const TRUNK_DX = 28;

  return (
    <div ref={scope} className="agent-sandtable">
      <div className="agent-sandtable__stage">
      {/* ═══════════ SVG 底层 ═══════════ */}
      <svg
        viewBox="0 0 1000 1000"
        preserveAspectRatio="none"
        style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', zIndex: 0, pointerEvents: 'none' }}
      >
        <defs>
          <filter id="glow-soft">
            <feGaussianBlur stdDeviation="4" result="b" />
            <feMerge><feMergeNode in="b" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        {/* 主干连线 */}
        <motion.path id="line-0" className="sandtable-line hide-on-reset" d={line0} fill="none" stroke="var(--color-border-subtle)" strokeWidth={2} />
        <motion.path id="line-1" className="sandtable-line hide-on-reset" d={line1} fill="none" stroke="var(--color-border-subtle)" strokeWidth={2} />
        <motion.path id="line-2" className="sandtable-line hide-on-reset" d={line2} fill="none" stroke="var(--color-border-subtle)" strokeWidth={2} />

        {/* 认知流光脉冲 */}
        <motion.path
          id="pulse-line"
          d={fullPath}
          fill="none"
          stroke="var(--color-intent-active)"
          strokeWidth={4}
          filter="url(#glow-soft)"
          opacity={0}
        />
      </svg>

      {/* ═══════════ NODE 0: User Input ═══════════ */}
      <div style={{ position: 'absolute', left: u.left, top: u.top, transform: 'translate(-50%, -50%)', zIndex: 10 }}>
        <motion.div
          id="user-input"
          className="node-el hide-on-reset"
          initial={{ opacity: 0, filter: 'blur(10px)', scale: 0.88 }}
          style={{
            padding: '5px 14px',
            borderRadius: '20px',
            backgroundColor: 'var(--color-surface-elevated)',
            color: 'var(--color-text-primary)',
            fontSize: '10px',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            border: '1px solid var(--color-border-subtle)',
            boxShadow: 'var(--shadow-sm)',
            whiteSpace: 'nowrap',
          }}
        >
          <div style={dot('var(--color-intent-info)')} />
          User Prompt
        </motion.div>
      </div>

      {/* ═══════════ NODE 1: Planner + 任务拆解 ═══════════ */}
      <div style={{ position: 'absolute', left: p.left, top: p.top, transform: 'translate(-50%, -50%)', zIndex: 10 }}>
        <motion.div
          id="planner-node"
          className="node-el hide-on-reset"
          initial={{ opacity: 0, filter: 'blur(10px)', scale: 0.88 }}
          style={{ ...nodeBase, minWidth: '115px' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 8 }}>
            <div style={dot('var(--color-intent-info)')} />
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--color-text-primary)', letterSpacing: '0.3px' }}>
              〇 Planner
            </span>
          </div>
          {/* 任务拆解清单 */}
          {TASKS.map((t, i) => (
            <motion.div
              key={i}
              className="task-item hide-on-reset"
              style={{
                opacity: 0, x: -10,
                display: 'flex', alignItems: 'center', gap: 5,
                marginTop: i === 0 ? 0 : 4,
              }}
            >
              <motion.div
                className="check-icon"
                style={{
                  opacity: 0, scale: 0,
                  width: 11, height: 11, borderRadius: '50%',
                  border: '1.5px solid var(--color-border-subtle)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: '7px', color: 'var(--color-intent-success)',
                  lineHeight: 1, flexShrink: 0,
                }}
              >
                ✓
              </motion.div>
              <span style={{ fontSize: '9px', color: 'var(--color-text-secondary)', letterSpacing: '0.2px' }}>
                {t}
              </span>
            </motion.div>
          ))}
        </motion.div>
      </div>

      {/* ═══════════ NODE 2: Researcher ═══════════ */}
      <div style={{ position: 'absolute', left: r.left, top: r.top, transform: 'translate(-50%, -50%)', zIndex: 10 }}>
        <motion.div
          id="researcher-node"
          className="node-el hide-on-reset"
          initial={{ opacity: 0, filter: 'blur(10px)', scale: 0.88 }}
          style={{ ...nodeBase, minWidth: '105px' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={dot('var(--color-intent-success)')} />
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--color-text-primary)', letterSpacing: '0.3px' }}>
              ✦ Researcher
            </span>
          </div>
          {/* 活动指示条 */}
          <div style={{ display: 'flex', gap: 3, marginTop: 6 }}>
            <div style={{ height: 3, flex: 1, background: 'var(--color-border-subtle)', borderRadius: 1.5 }} />
            <div style={{ height: 3, flex: 1, background: 'var(--color-border-subtle)', borderRadius: 1.5 }} />
            <div style={{ height: 3, flex: 0.6, background: 'var(--color-intent-success)', opacity: 0.5, borderRadius: 1.5 }} />
          </div>
        </motion.div>
      </div>

      {/* ═══════════ SUB-AGENT 连线 (像素空间, 锚定 Researcher 中心 — 与圆点同源同偏移, 任意视口都贴合) ═══════════ */}
      <svg
        className="sub-connectors"
        style={{ position: 'absolute', left: r.left, top: r.top, width: 0, height: 0, overflow: 'visible', zIndex: 8, pointerEvents: 'none' }}
      >
        {SUBS.map((s, i) => (
          <line
            key={`sl-${i}`}
            className="sub-line-path hide-on-reset"
            x1={0} y1={0} x2={s.dx} y2={s.dy}
            stroke="var(--color-intent-success)"
            strokeWidth={1}
            strokeDasharray="5 4"
            opacity={0}
          />
        ))}
      </svg>

      {/* ═══════════ SUB-AGENTS (从 Researcher 弹射) ═══════════ */}
      {SUBS.map((s) => (
        <motion.div
          key={s.id}
          id={s.id}
          className="sub-dot hide-on-reset"
          style={{
            position: 'absolute',
            left: r.left,
            top: r.top,
            transform: 'translate(-50%, -50%)',
            opacity: 0,
            scale: 0,
            zIndex: 9,
          }}
        >
          <div
            className={s.floatClass}
            style={{
              padding: '3px 8px',
              borderRadius: '12px',
              backgroundColor: 'var(--color-surface-elevated)',
              border: '1px solid var(--color-intent-success)',
              fontSize: '8px',
              color: 'var(--color-text-secondary)',
              whiteSpace: 'nowrap',
              boxShadow: '0 0 8px oklch(72% 0.09 145 / 0.25)',
              backdropFilter: 'blur(8px)',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}
          >
            <div style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--color-intent-success)', boxShadow: '0 0 6px var(--color-intent-success)' }} />
            {s.label}
          </div>
        </motion.div>
      ))}

      {/* ═══════════ NODE 3: Path Engine ═══════════ */}
      <div style={{ position: 'absolute', left: pe.left, top: pe.top, transform: 'translate(-50%, -50%)', zIndex: 10 }}>
        <motion.div
          id="path-node"
          className="node-el hide-on-reset"
          initial={{ opacity: 0, filter: 'blur(10px)', scale: 0.88 }}
          style={{ ...nodeBase, minWidth: '80px' }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            <div style={dot('var(--color-intent-warning)')} />
            <span style={{ fontSize: '11px', fontWeight: 500, color: 'var(--color-text-primary)', letterSpacing: '0.3px' }}>
              ⎔ Path
            </span>
          </div>
        </motion.div>
      </div>

      {/* ═══════════ TREE 连线 (像素空间, 锚定 Path 中心 — 主干 + 分支与叶子同源同偏移) ═══════════ */}
      <svg
        className="tree-connectors"
        style={{ position: 'absolute', left: pe.left, top: pe.top, width: 0, height: 0, overflow: 'visible', zIndex: 8, pointerEvents: 'none' }}
      >
        <motion.path
          id="tree-trunk"
          className="tree-line hide-on-reset"
          d={`M 0 0 L ${TRUNK_DX} 0`}
          fill="none"
          stroke="var(--color-intent-warning)"
          strokeWidth={2}
        />
        {BRANCHES.map((b, i) => (
          <motion.path
            key={`tb-${i}`}
            className="tree-line tree-branch hide-on-reset"
            d={`M ${TRUNK_DX} 0 L ${b.dx} ${b.dy}`}
            fill="none"
            stroke="var(--color-intent-warning)"
            strokeWidth={1.5}
          />
        ))}
      </svg>

      {/* ═══════════ TREE LEAVES (从 Path Engine 弹射) ═══════════ */}
      {BRANCHES.map((b) => (
        <motion.div
          key={b.id}
          id={b.id}
          className="tree-leaf hide-on-reset"
          style={{
            position: 'absolute',
            left: pe.left,
            top: pe.top,
            transform: 'translate(-50%, -50%)',
            opacity: 0,
            scale: 0,
            zIndex: 9,
          }}
        >
          <div
            className="leaf-float"
            style={{
              padding: '3px 8px',
              borderRadius: '10px',
              backgroundColor: 'var(--color-surface-elevated)',
              border: '1px solid var(--color-intent-warning)',
              fontSize: '8px',
              color: 'var(--color-text-secondary)',
              whiteSpace: 'nowrap',
              boxShadow: '0 0 5px oklch(76% 0.10 70 / 0.22)',
              backdropFilter: 'blur(8px)',
            }}
          >
            {b.label}
          </div>
        </motion.div>
      ))}
      </div>

      {/* ═══════════ 沙色终端 (Soft Terminal) ═══════════ */}
      <div className="agent-sandtable__terminal">
        {/* Terminal 标题栏 */}
        <div className="agent-sandtable__terminal-header">
          <div className="agent-sandtable__traffic-lights">
            <span className="agent-sandtable__traffic-light agent-sandtable__traffic-light--red" />
            <span className="agent-sandtable__traffic-light agent-sandtable__traffic-light--yellow" />
            <span className="agent-sandtable__traffic-light agent-sandtable__traffic-light--green" />
          </div>
          <span className="agent-sandtable__terminal-title">
            运行日志
          </span>
        </div>
        {/* Terminal 输出区 */}
        <div className="agent-sandtable__terminal-body">
          <div className="agent-sandtable__terminal-logs">
            <TermLine id="term-1" prefix="[Planner] " text="解析目标: 构建前端架构地图..." />
            <TermLine id="term-2" prefix="[Planner] " text="拆解为 3 个子任务 ✓" />
            <TermLine id="term-3" prefix="[Swarm]   " text="并行唤醒 3 个知识寻源体..." />
            <TermLine id="term-4" prefix="[Swarm]   " text="正在降维清洗 1204 个图谱节点..." />
            <TermLine id="term-5" prefix="[Path]    " text="收敛最优拓扑 · 路径已生成 ✓" />
          </div>
          <div className="terminal-cursor hide-on-reset" style={{ opacity: 0 }} />
        </div>
      </div>
    </div>
  );
}
