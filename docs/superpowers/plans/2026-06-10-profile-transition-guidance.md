# Onboarding Profile Transition Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化从画像生成到学习路径的过渡体验，实现步骤进度指示器、画像完成底部常驻锁定控制台、学习路径生成概要开屏（PathInitOverlay）以及首个叶子节点引导气泡（LeafCoachmark）。

**Architecture:** 
1. 在 `AiGreetingInput.tsx` 增加 `StepProgressBar` 组件以常驻顶部显示收集进度；当画像完成后，将原有打字框替换为 `开启我的学习路径` 底部常驻控制台。
2. 在 `PathInitOverlay.tsx` 中创建毛玻璃全屏遮罩，并渐显揭示路径概要信息，然后显现“开始第一门课”按钮。
3. 在 `BranchPage.tsx` 中挂载 `PathInitOverlay` 与首叶 Coachmark Tooltip。

**Tech Stack:** React 18, TypeScript, styled-components, Framer Motion, react-router-dom

---

### Task 1: 实现 `StepProgressBar` 常驻进度指示器与空状态文案

**Files:**
- Modify: `frontend/src/components/onboarding/AiGreetingInput.tsx`
- Modify: `frontend/src/components/onboarding/__tests__/AiGreetingInput.test.tsx`

- [ ] **Step 1: 在测试中编写关于步骤指示器渲染与更新的单元测试**

  修改 `frontend/src/components/onboarding/__tests__/AiGreetingInput.test.tsx`，添加以下单元测试用例：
  ```typescript
  it('renders progress bar indicating the active collection stage', () => {
    renderWithRouter(<AiGreetingInput />);
    
    // 检查空状态初始引导语
    expect(screen.getByText(/欢迎！告诉我你的年级、专业或学习方向。/)).toBeTruthy();
    
    // 检查进度节点渲染
    expect(screen.getByText('基础信息')).toBeTruthy();
    expect(screen.getByText('学习偏好')).toBeTruthy();
    expect(screen.getByText('能力基础')).toBeTruthy();
    expect(screen.getByText('目标约束')).toBeTruthy();
  });
  ```

- [ ] **Step 2: 运行测试并确保它失败**

  运行：`npm run test -- AiGreetingInput.test.tsx`
  预期：失败，因为指示器尚未实现，且空状态引导语不匹配。

- [ ] **Step 3: 实现 StepProgressBar 样式与逻辑，更新空状态文案**

  修改 `frontend/src/components/onboarding/AiGreetingInput.tsx`：
  1. 查找并更新空状态引导语：
     ```tsx
     // 修改前：
     <div className="chat-empty-state">
       告诉我你的年级、专业、学习偏好或近期目标，我会先判断意图，再进入基础画像对话。
     </div>
     // 修改后：
     <div className="chat-empty-state">
       🌱 欢迎！告诉我你的年级、专业或学习方向。定制你的自适应课程藤蔓仅需约 1-2 分钟。
     </div>
     ```
  2. 在 `AiGreetingInput` 组件头部或 `.chat-flow` 的上方，添加 `StepProgressBar` 渲染逻辑：
     ```tsx
     // 插入进度条：
     const getActiveStepIndex = (): number => {
       const confirmed = store.messages[store.messages.length - 1]?.confirmed_info || {};
       if (confirmed.short_term_goal || confirmed.constraints) return 3; // 目标约束
       if (confirmed.knowledge_foundation || confirmed.strengths) return 2; // 能力基础
       if (confirmed.learning_stage || confirmed.learning_method_preference) return 1; // 学习偏好
       return 0; // 基础信息
     };

     const activeStep = getActiveStepIndex();
     const steps = ['基础信息', '学习偏好', '能力基础', '目标约束'];
     ```
     并在 JSX 中添加指示器渲染结构，运用 OKLCH 语义色及过渡：
     ```tsx
     <div className="onboarding-step-bar">
       {steps.map((label, index) => (
         <div key={label} className={`step-node ${index <= activeStep ? 'active' : ''} ${index < activeStep ? 'completed' : ''}`}>
           <span className="node-dot">{index < activeStep ? '✓' : index + 1}</span>
           <span className="node-label">{label}</span>
           {index < steps.length - 1 && <span className="node-line" />}
         </div>
       ))}
     </div>
     ```
  3. 在 `StyledWrapper` 底部的样式中追加指示器样式定义：
     ```css
     .onboarding-step-bar {
       display: flex;
       align-items: center;
       justify-content: space-between;
       padding: var(--space-12) var(--space-16);
       background: var(--color-surface);
       border-bottom: 1px solid var(--color-border);
       margin-bottom: var(--space-12);
     }
     .step-node {
       display: flex;
       align-items: center;
       gap: var(--space-6);
       position: relative;
       flex: 1;
       justify-content: center;
     }
     .step-node:not(:last-child) {
       flex-grow: 1;
     }
     .node-dot {
       width: 20px;
       height: 20px;
       border-radius: var(--radius-full);
       background: var(--color-surface-inset);
       border: 1px solid var(--color-border);
       font-size: var(--text-caption);
       display: flex;
       align-items: center;
       justify-content: center;
       color: var(--color-text-muted);
       transition: all var(--duration-lazy-hover) var(--ease-lazy);
     }
     .step-node.active .node-dot {
       background: var(--color-primary-soft);
       border-color: var(--color-primary);
       color: var(--color-primary);
       box-shadow: 0 0 6px var(--color-primary-soft);
     }
     .step-node.completed .node-dot {
       background: var(--color-success);
       border-color: var(--color-success);
       color: var(--color-text-inverse);
     }
     .node-label {
       font-size: var(--text-caption);
       color: var(--color-text-secondary);
     }
     .step-node.active .node-label {
       color: var(--color-text-primary);
       font-weight: var(--font-weight-medium);
     }
     .node-line {
       position: absolute;
       right: -50%;
       left: 50%;
       margin-left: 40px;
       height: 1px;
       background: var(--color-border);
       z-index: 1;
     }
     ```

- [ ] **Step 4: 运行测试并确保它通过**

  Run: `npm run test -- AiGreetingInput.test.tsx`
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/src/components/onboarding/AiGreetingInput.tsx frontend/src/components/onboarding/__tests__/AiGreetingInput.test.tsx
  git commit -m "feat: add sticky step progress bar to onboarding widget"
  ```

---

### Task 2: 实现画像完成底部常驻锁定控制台

**Files:**
- Modify: `frontend/src/components/onboarding/AiGreetingInput.tsx`
- Modify: `frontend/src/components/onboarding/ChatCard.tsx`
- Modify: `frontend/src/components/onboarding/__tests__/AiGreetingInput.test.tsx`

- [ ] **Step 1: 在测试中增加验证画像完成后输入框收起并显示 CTA 按钮的用例**

  在 `AiGreetingInput.test.tsx` 中编写测试：
  ```typescript
  it('hides composer and displays sticky bottom CTA on profile completion', () => {
    // 模拟 hasCompleteProfileRef.current 为 true
    // 验证 .chat-composer 元素不渲染
    // 验证渲染的“开启我的学习路径”按钮存在
  });
  ```

- [ ] **Step 2: 运行测试并确保它失败**

  Run: `npm run test -- AiGreetingInput.test.tsx`
  Expected: FAIL

- [ ] **Step 3: 修改 ChatCard.tsx 的跳转，传递 justGeneratedProfile 状态**

  修改 `frontend/src/components/onboarding/ChatCard.tsx`：
  在 `handleOpenPath` 函数中，修改路由跳转，加入 `location` state 的传递：
  ```tsx
  const handleOpenPath = () => {
    setWidgetState('WIDGET');
    navigate('/branch', { state: { justGeneratedProfile: true } });
  };
  ```

- [ ] **Step 4: 修改 AiGreetingInput.tsx 底部表单渲染逻辑，当画像生成后用常驻 CTA 代替原有表单**

  修改 `frontend/src/components/onboarding/AiGreetingInput.tsx`：
  1. 在 `composer-container` 内，当 `hasCompleteProfileRef.current` 为 true 时，不渲染 `<form className="chat-composer"...>`，而是渲染常驻 CTA 控制台：
     ```tsx
     {hasCompleteProfileRef.current ? (
       <div className="composer-completed-cta-panel">
         <button className="cta-completed-btn" onClick={handleOpenPath} type="button">
           <span>开启我的学习路径</span>
           <span className="arrow">➔</span>
         </button>
       </div>
     ) : (
       <form className="chat-composer" ...>
     )}
     ```
  2. 实现点击处理函数 `handleOpenPath`（导入 `useNavigate` 并调用它）：
     ```tsx
     const handleOpenPath = () => {
       setWidgetState('WIDGET');
       navigate('/branch', { state: { justGeneratedProfile: true } });
     };
     ```
  3. 追加相关 CSS 样式：
     ```css
     .composer-completed-cta-panel {
       padding: var(--space-8) var(--space-12);
       background: var(--color-surface);
       border-top: 1px solid var(--color-border);
       display: flex;
       justify-content: center;
     }
     .cta-completed-btn {
       width: 100%;
       padding: var(--space-12) var(--space-24);
       border: none;
       border-radius: var(--radius-full);
       background: var(--color-primary);
       color: var(--color-text-inverse);
       font-family: var(--font-body);
       font-size: var(--text-body-sm);
       font-weight: var(--font-weight-medium);
       cursor: pointer;
       display: flex;
       align-items: center;
       justify-content: center;
       gap: var(--space-6);
       box-shadow: var(--shadow-md);
       transition: transform var(--duration-lazy-hover) var(--ease-lazy);
     }
     .cta-completed-btn:hover {
       transform: translateY(-2px);
     }
     .cta-completed-btn .arrow {
       transition: transform var(--duration-lazy-hover) var(--ease-lazy);
     }
     .cta-completed-btn:hover .arrow {
       transform: translateX(4px);
     }
     ```

- [ ] **Step 5: 运行测试并确保它通过**

  Run: `npm run test -- AiGreetingInput.test.tsx`
  Expected: PASS

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/components/onboarding/AiGreetingInput.tsx frontend/src/components/onboarding/ChatCard.tsx frontend/src/components/onboarding/__tests__/AiGreetingInput.test.tsx
  git commit -m "feat: hide text composer and show sticky bottom CTA on profile completion"
  ```

---

### Task 3: 实现 `PathInitOverlay` 画像概要展示遮罩

**Files:**
- Create: `frontend/src/components/onboarding/PathInitOverlay.tsx`
- Create: `frontend/src/components/onboarding/__tests__/PathInitOverlay.test.tsx`

- [ ] **Step 1: 新建 PathInitOverlay 单元测试文件，声明验证动画及按钮回调**

  新建 `frontend/src/components/onboarding/__tests__/PathInitOverlay.test.tsx`：
  ```typescript
  import { render, screen, fireEvent } from '@testing-library/react';
  import { describe, expect, it, vi } from 'vitest';
  import { PathInitOverlay } from '../PathInitOverlay';

  describe('PathInitOverlay', () => {
    it('renders text phases and triggers completion callback on button click', async () => {
      const mockComplete = vi.fn();
      render(<PathInitOverlay onComplete={mockComplete} />);
      
      // 检查标题与描述
      expect(screen.getByText('你的自适应学习路径已顺利编织完成。')).toBeTruthy();
      
      // 模拟完成动画步骤
      // 验证“开始第一门课”按钮的渲染并模拟点击
      const btn = screen.getByRole('button', { name: '开始第一门课' });
      fireEvent.click(btn);
      expect(mockComplete).toHaveBeenCalled();
    });
  });
  ```

- [ ] **Step 2: 运行测试并确保它失败**

  Run: `npm run test -- PathInitOverlay.test.tsx`
  Expected: FAIL

- [ ] **Step 3: 创建 PathInitOverlay.tsx 主文件，实现毛玻璃与打字机概要动效**

  创建 `frontend/src/components/onboarding/PathInitOverlay.tsx`，运用 Framer Motion 实现打字式序列展现：
  ```tsx
  import React, { useEffect, useState } from 'react';
  import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
  import { motionTokens, DURATION_INSTANT } from '../../styles/motion-tokens';

  interface Props {
    onComplete?: () => void;
  }

  export function PathInitOverlay({ onComplete }: Props) {
    const [phase, setPhase] = useState<number>(0);
    const reduceMotion = useReducedMotion();

    useEffect(() => {
      if (reduceMotion) {
        setPhase(2);
        return;
      }
      const t1 = setTimeout(() => setPhase(1), 1200); // 概要文本淡入
      const t2 = setTimeout(() => setPhase(2), 2800); // 按钮滑入
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }, [reduceMotion]);

    return (
      <motion.div
        initial={reduceMotion ? false : { opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={reduceMotion ? { duration: DURATION_INSTANT } : motionTokens.route}
        style={{
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          backgroundColor: 'oklch(97% 0.02 75 / 0.45)',
          backdropFilter: 'blur(56px)',
          WebkitBackdropFilter: 'blur(56px)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
        }}
      >
        <div style={{ maxWidth: '600px', padding: '0 var(--space-24)' }}>
          <motion.h1
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={motionTokens.editorial}
            style={{ fontFamily: 'var(--font-heading)', fontSize: '32px', color: 'oklch(28% 0.01 60)', fontWeight: 400, margin: '0 0 var(--space-24) 0' }}
          >
            你的自适应学习路径已顺利编织完成。
          </motion.h1>
          
          <AnimatePresence>
            {phase >= 1 && (
              <motion.p
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={motionTokens.editorial}
                style={{ fontFamily: 'var(--font-body)', fontSize: '18px', color: 'oklch(55% 0.02 60)', lineHeight: 1.8, margin: '0 0 var(--space-32) 0' }}
              >
                系统已根据你的画像基础，为你自动<strong>剪枝精简了 2 门</strong>已知的基础课程，并针对你的薄弱点<strong>融入了 1 门</strong>专项强化课。
              </motion.p>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {phase >= 2 && (
              <motion.button
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={motionTokens.lazy}
                onClick={onComplete}
                style={{
                  padding: 'var(--space-12) var(--space-32)',
                  borderRadius: 'var(--radius-full)',
                  background: 'var(--color-primary)',
                  color: 'var(--color-text-inverse)',
                  fontFamily: 'var(--font-body)',
                  fontSize: '16px',
                  fontWeight: 'var(--font-weight-medium)',
                  border: 'none',
                  cursor: 'pointer',
                  boxShadow: 'var(--shadow-md)',
                }}
              >
                开始第一门课
              </motion.button>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    );
  }
  ```

- [ ] **Step 4: 运行测试并确保它通过**

  Run: `npm run test -- PathInitOverlay.test.tsx`
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/src/components/onboarding/PathInitOverlay.tsx frontend/src/components/onboarding/__tests__/PathInitOverlay.test.tsx
  git commit -m "feat: add PathInitOverlay component for path generation summary screen"
  ```

---

### Task 4: 在 `BranchPage.tsx` 中集成 `PathInitOverlay` 与 `LeafCoachmark` 引导气泡

**Files:**
- Modify: `frontend/src/pages/branch/BranchPage.tsx`
- Modify: `frontend/src/pages/branch/BranchPage.test.tsx`

- [ ] **Step 1: 修改 BranchPage.test.tsx 增加覆盖新过渡遮罩和气泡渲染逻辑的测试**

  修改 `frontend/src/pages/branch/BranchPage.test.tsx`，模拟路由中的 location state 并断言 overlay 挂载：
  ```typescript
  it('renders PathInitOverlay when justGeneratedProfile state is passed', () => {
    // mock useLocation 返回 { state: { justGeneratedProfile: true } }
    // 验证渲染 of PathInitOverlay 标题存在
  });
  ```

- [ ] **Step 2: 运行测试并确保它失败**

  Run: `npm run test -- BranchPage.test.tsx`
  Expected: FAIL

- [ ] **Step 3: 修改 BranchPage.tsx 导入依赖，获取路由状态并挂载 PathInitOverlay**

  修改 `frontend/src/pages/branch/BranchPage.tsx`：
  1. 在头部导入部分添加 `useLocation`：
     ```typescript
     import { useLocation, useNavigate } from 'react-router-dom';
     import { PathInitOverlay } from '../../components/onboarding/PathInitOverlay';
     import { AnimatePresence } from 'framer-motion';
     ```
  2. 在 `BranchPage` 组件内部添加状态接收及遮罩和气泡的控制状态：
     ```typescript
     const location = useLocation();
     const [showPathOverlay, setShowPathOverlay] = useState(() => {
       return location.state?.justGeneratedProfile === true;
     });
     const [showCoachmark, setShowCoachmark] = useState(false);
     ```
  3. 在 `BranchPage` 返回的 JSX 根部（与 `motion.main` 并列）挂载 `PathInitOverlay`：
     ```tsx
     <AnimatePresence>
       {showPathOverlay && (
         <PathInitOverlay
           onComplete={() => {
             setShowPathOverlay(false);
             setShowCoachmark(true);
           }}
         />
       )}
     </AnimatePresence>
     ```

- [ ] **Step 4: 在 PathSession 的第一个当前活跃节点插槽中实现 LeafCoachmark 引导气泡**

  修改 `frontend/src/pages/branch/BranchPage.tsx` 中的 `PathSession` 组件：
  1. 为 `PathSession` 的 Props 新增 `showCoachmark` 与 `onCloseCoachmark` 回调定义：
     ```typescript
     showCoachmark?: boolean;
     onCloseCoachmark?: () => void;
     ```
  2. 找到渲染 `stage.center` 的插槽节点（`.branch-stage-slot-center`），使其在相对定位内部渲染气泡：
     ```tsx
     {stage.center ? (
       <div className="branch-stage-slot branch-stage-slot-center branch-node-center" style={{ position: 'relative' }}>
         <div className="branch-mascot" aria-hidden="true">
           <MascotBlob />
         </div>
         
         {showCoachmark && (
           <div className="leaf-coachmark-balloon" onClick={onCloseCoachmark}>
             <span>✨ 点击此处，开启第一章学习</span>
             <div className="balloon-arrow" />
           </div>
         )}
         ...
     ```
  3. 将点击课程卡片的 `handleCourseClick` 事件触发以及页面任意点击绑定到关闭气泡的回调中，保证交互即销毁。
  4. 追加 Coachmark 气泡的相关 CSS 样式到 `branch.css` 中：
     ```css
     .leaf-coachmark-balloon {
       position: absolute;
       bottom: 110%;
       left: 50%;
       transform: translateX(-50%);
       z-index: 100;
       background: var(--color-primary-soft);
       color: var(--color-primary);
       padding: var(--space-8) var(--space-16);
       border-radius: var(--radius-md);
       border: 1px solid var(--color-primary);
       font-family: var(--font-body);
       font-size: var(--text-caption);
       white-space: nowrap;
       cursor: pointer;
       animation: coachmark-float 2s ease-in-out infinite, fade-in-hint 0.4s var(--ease-editorial);
       box-shadow: 0 0 12px var(--color-primary-soft);
     }
     .balloon-arrow {
       position: absolute;
       top: 100%;
       left: 50%;
       transform: translateX(-50%);
       border: 6px solid transparent;
       border-top-color: var(--color-primary);
     }
     @keyframes coachmark-float {
       0%, 100% { transform: translate(-50%, 0); }
       50% { transform: translate(-50%, -6px); }
     }
     ```

- [ ] **Step 5: 运行集成测试验证功能符合设计要求**

  Run: `npm run test -- onboarding`
  Run: `npm run test -- BranchPage.test.tsx`
  Expected: PASS

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/src/pages/branch/BranchPage.tsx frontend/src/pages/branch/BranchPage.test.tsx frontend/src/pages/branch/branch.css
  git commit -m "feat: integrate PathInitOverlay and LeafCoachmark on Branch page"
  ```
