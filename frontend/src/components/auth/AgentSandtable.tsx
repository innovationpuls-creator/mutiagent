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
  user:     { left: '8%',  top: '34%', sx: 80,  sy: 340 },
  planner:  { left: '27%', top: '34%', sx: 270, sy: 340 },
  research: { left: '56%', top: '34%', sx: 560, sy: 340 },
  path:     { left: '80%', top: '34%', sx: 800, sy: 340 },
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
    /* ── 无障碍：prefers-reduced-motion 静态降级 ── */
    if (reduceMotion) {
      animate('.node-el', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0 });
      animate('.task-item', { opacity: 1, x: 0 }, { duration: 0 });
      animate('.check-icon', { opacity: 1, scale: 1 }, { duration: 0 });
      animate('.sandtable-line', { pathLength: 1 }, { duration: 0 });
      SUBS.forEach(s => animate(`#${s.id}`, { x: s.dx, y: s.dy, scale: 1, opacity: 1 }, { duration: 0 }));
      animate('.sub-line-path', { opacity: 0.4 }, { duration: 0 });
      animate('#tree-trunk', { pathLength: 1 }, { duration: 0 });
      animate('.tree-branch', { pathLength: 1 }, { duration: 0 });
      BRANCHES.forEach(b => animate(`#${b.id}`, { x: b.dx, y: b.dy, scale: 1, opacity: 1 }, { duration: 0 }));
      animate('.term-line', { opacity: 1 }, { duration: 0 });
      animate('.term-char', { opacity: 1 }, { duration: 0 });
      animate('.terminal-cursor', { opacity: 1 }, { duration: 0 });
      return;
    }

    let alive = true;
    const wait = (ms: number) => new Promise<void>(r => setTimeout(r, ms));

    const run = async () => {
      const ed: [number, number, number, number] = [0.4, 0, 0.2, 1];

      while (alive) {
        /* ════════════ RESET ════════════ */
        animate('.node-el', { opacity: 0, filter: 'blur(10px)', scale: 0.88 }, { duration: 0 });
        animate('.task-item', { opacity: 0, x: -10 }, { duration: 0 });
        animate('.check-icon', { opacity: 0, scale: 0 }, { duration: 0 });
        animate('.sandtable-line', { pathLength: 0 }, { duration: 0 });
        animate('.sub-dot', { opacity: 0, scale: 0, x: 0, y: 0 }, { duration: 0 });
        animate('.sub-line-path', { opacity: 0 }, { duration: 0 });
        animate('#tree-trunk', { pathLength: 0 }, { duration: 0 });
        animate('.tree-branch', { pathLength: 0 }, { duration: 0 });
        animate('.tree-leaf', { opacity: 0, scale: 0, x: 0, y: 0 }, { duration: 0 });
        animate('.term-line', { opacity: 0 }, { duration: 0 });
        animate('.term-char', { opacity: 0 }, { duration: 0 });
        animate('.terminal-cursor', { opacity: 0 }, { duration: 0 });
        animate('#pulse-line', { opacity: 0, pathLength: 0, pathOffset: 0 }, { duration: 0 });

        await wait(350);
        if (!alive) break;

        /* ════════════ 0.35s: USER INPUT ════════════ */
        animate('#user-input', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.7, ease: ed });
        await wait(600);
        if (!alive) break;

        /* ════════════ 0.95s: PLANNER — 任务拆解清单 ════════════ */
        setStageIndex(0);
        animate('#line-0', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(300);
        animate('#planner-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(450);

        // 任务项依次滑入
        animate('.task-item', { opacity: 1, x: 0 }, { duration: 0.3, delay: stagger(0.16), ease: 'easeOut' });
        await wait(650);

        // 打勾 ✓ 依次弹出
        animate('.check-icon', { opacity: 1, scale: 1 }, { duration: 0.2, delay: stagger(0.2), ease: 'easeOut' });

        // 终端 Line 1: 极速逐字流淌
        animate('#term-1', { opacity: 1 }, { duration: 0.01 });
        animate('.term-char-term-1', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        animate('.terminal-cursor', { opacity: 1 }, { duration: 0.01 });
        await wait(650);

        // 终端 Line 2
        animate('#term-2', { opacity: 1 }, { duration: 0.01 });
        animate('.term-char-term-2', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        await wait(500);
        if (!alive) break;

        /* ════════════ 3.5s: RESEARCHER — 集群分裂 ════════════ */
        setStageIndex(1);
        animate('#line-1', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(300);
        animate('#researcher-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(350);

        // Sub-agents 从中心弹射 (spring 物理)
        for (const s of SUBS) {
          animate(`#${s.id}`, { x: s.dx, y: s.dy, scale: 1, opacity: 1 }, {
            type: 'spring', stiffness: 220, damping: 16,
          });
          await wait(90);
        }
        await wait(200);

        // 虚线连线淡入
        animate('.sub-line-path', { opacity: 0.4 }, { duration: 0.4, delay: stagger(0.08), ease: 'easeOut' });

        // 终端 Line 3
        animate('#term-3', { opacity: 1 }, { duration: 0.01 });
        animate('.term-char-term-3', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        await wait(1300);
        if (!alive) break;

        /* ════════════ 6.1s: PATH ENGINE — 拓扑爆炸 ════════════ */
        setStageIndex(2);
        animate('#line-2', { pathLength: 1 }, { duration: 0.6, ease: 'easeInOut' });
        await wait(300);
        animate('#path-node', { opacity: 1, filter: 'blur(0px)', scale: 1 }, { duration: 0.8, ease: ed });
        await wait(350);

        // 主干生长
        animate('#tree-trunk', { pathLength: 1 }, { duration: 0.45, ease: 'easeOut' });
        await wait(250);

        // 三根分支藤蔓展开
        animate('.tree-branch', { pathLength: 1 }, { duration: 0.35, delay: stagger(0.1), ease: 'easeOut' });
        await wait(250);

        // 叶子节点弹射
        for (const b of BRANCHES) {
          animate(`#${b.id}`, { x: b.dx, y: b.dy, scale: 1, opacity: 1 }, {
            type: 'spring', stiffness: 260, damping: 17,
          });
          await wait(70);
        }

        // 终端 Line 4
        animate('#term-4', { opacity: 1 }, { duration: 0.01 });
        animate('.term-char-term-4', { opacity: 1 }, { duration: 0.01, delay: stagger(0.018) });
        await wait(900);
        if (!alive) break;

        /* ════════════ 8.5s: 认知流光脉冲 ════════════ */
        animate('#pulse-line', {
          opacity: [0, 0.8, 0.8, 0],
          pathLength: [0, 0.3, 0.3, 0],
          pathOffset: [0, 0, 0.7, 1],
        }, { duration: 2.5, times: [0, 0.2, 0.8, 1], ease: 'easeInOut' });
        await wait(2800);
        if (!alive) break;

        /* ════════════ 11.3s: 退场 ════════════ */
        await animate('.hide-on-reset', { opacity: 0, filter: 'blur(8px)' }, {
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

  // Sub-agent 虚线 SVG (从 Researcher 中心射出)
  // 近似坐标: 像素偏移 / 预估容器尺寸 × 1000 + 节点 SVG 坐标
  const subSvgEnd = [
    { x: 560 - 89, y: 340 - 158 },  // Google  (-48px, -60px at ~540×380)
    { x: 560,       y: 340 - 197 },  // arXiv   (0, -75px)
    { x: 560 + 89,  y: 340 - 158 },  // GitHub  (48px, -60px)
  ];

  // Tree 主干 & 分支
  const trunkEnd = { x: pe.sx + 90, y: pe.sy };
  const branchSvgEnd = [
    { x: pe.sx + 102, y: pe.sy - 132 },  // 单元一 (55px, -50px)
    { x: pe.sx + 130, y: pe.sy },         // 单元二 (70px, 0)
    { x: pe.sx + 102, y: pe.sy + 132 },   // 单元三 (55px, 50px)
  ];

  return (
    <div
      ref={scope}
      style={{
        position: 'relative',
        width: '100%',
        height: '380px',
        marginTop: 'var(--space-8)',
        overflow: 'visible',
      }}
    >
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

        {/* Sub-agent 虚线 (从 Researcher 射向子节点) */}
        {subSvgEnd.map((e, i) => (
          <path
            key={`sl-${i}`}
            className="sub-line-path hide-on-reset"
            d={`M ${r.sx} ${r.sy} L ${e.x} ${e.y}`}
            fill="none"
            stroke="var(--color-intent-success)"
            strokeWidth={1}
            strokeDasharray="8 5"
            opacity={0}
          />
        ))}

        {/* Tree 主干 */}
        <motion.path
          id="tree-trunk"
          className="tree-line hide-on-reset"
          d={`M ${pe.sx} ${pe.sy} L ${trunkEnd.x} ${trunkEnd.y}`}
          fill="none"
          stroke="var(--color-intent-warning)"
          strokeWidth={2.5}
        />
        {/* Tree 分支 */}
        {branchSvgEnd.map((e, i) => (
          <motion.path
            key={`tb-${i}`}
            className="tree-line tree-branch hide-on-reset"
            d={`M ${trunkEnd.x} ${trunkEnd.y} L ${e.x} ${e.y}`}
            fill="none"
            stroke="var(--color-intent-warning)"
            strokeWidth={1.8}
          />
        ))}

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
              border: '1px solid oklch(78% 0.08 145 / 0.6)',
              fontSize: '8px',
              color: 'var(--color-text-secondary)',
              whiteSpace: 'nowrap',
              boxShadow: '0 0 8px oklch(75% 0.1 145 / 0.25)',
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
              border: '1px solid oklch(78% 0.1 60 / 0.5)',
              fontSize: '8px',
              color: 'var(--color-text-secondary)',
              whiteSpace: 'nowrap',
              boxShadow: '0 0 5px oklch(78% 0.1 60 / 0.2)',
            }}
          >
            {b.label}
          </div>
        </motion.div>
      ))}

      {/* ═══════════ 沙色终端 (Soft Terminal) ═══════════ */}
      <div
        style={{
          position: 'absolute',
          bottom: '3%',
          left: '3%',
          right: '3%',
          background: 'oklch(96% 0.01 60 / 0.55)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderRadius: 'var(--radius-md)',
          border: '1px solid var(--color-border-subtle)',
          boxShadow: 'var(--shadow-sm)',
          overflow: 'hidden',
          zIndex: 15,
        }}
      >
        {/* Terminal 标题栏 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '5px 10px', borderBottom: '1px solid var(--color-border-subtle)' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'oklch(75% 0.12 25)', display: 'block' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'oklch(82% 0.12 95)', display: 'block' }} />
            <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'oklch(80% 0.1 145)', display: 'block' }} />
          </div>
          <span style={{ fontSize: '9px', color: 'var(--color-text-whisper)', letterSpacing: '0.5px', fontFamily: 'var(--font-mono, monospace)' }}>
            Agent Runtime
          </span>
        </div>
        {/* Terminal 输出区 */}
        <div style={{ padding: '6px 10px', display: 'flex', flexDirection: 'column', gap: 2 }}>
          <TermLine id="term-1" prefix="[Planner] " text="解析目标: 构建前端架构地图..." />
          <TermLine id="term-2" prefix="[Planner] " text="拆解为 3 个子任务 ✓" />
          <TermLine id="term-3" prefix="[Swarm]   " text="并行唤醒 3 个知识寻源体..." />
          <TermLine id="term-4" prefix="[Path]    " text="收敛最优拓扑 · 路径已生成 ✓" />
          <div className="terminal-cursor hide-on-reset" style={{ opacity: 0, marginTop: 2 }} />
        </div>
      </div>
    </div>
  );
}
