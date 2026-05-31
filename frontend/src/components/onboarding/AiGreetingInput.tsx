import React, { useEffect, useRef } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import styled from 'styled-components';
import { AiEyes } from './AiEyes';
import { useAiWidget } from '../../context/AiWidgetContext';
import { ChatCard } from './ChatCard';
import type { SessionMessage } from '../../types/chat';

const mockMessages: SessionMessage[] = [
  {
    type: "collecting",
    stage: "basic_info",
    question_mode: "question_md",
    confirmed_info: {} as any,
    defaulted_fields: [],
    question_md: "✅ 已确认信息：\n- 当前年级：暂未确认\n- 所学专业：暂未确认\n\n❓ 接下来需要了解：\n- 你目前是几年级？\n- 你所学的专业是什么？",
    question_box: { question: "", options: [] },
    text: "✅ 已确认信息：\n- 当前年级：暂未确认\n- 所学专业：暂未确认\n\n❓ 接下来需要了解：\n- 你目前是几年级？\n- 你所学的专业是什么？"
  },
  {
    type: "collecting",
    stage: "basic_info",
    question_mode: "question_box",
    confirmed_info: {} as any,
    defaulted_fields: [],
    question_md: "",
    question_box: { question: "你更倾向于以下哪种长期目标？", options: ["前端工程化", "后端微服务架构", "AI 应用开发", "暂不确定，先打基础"] },
    text: "简要说明：关于学习方向，我们需要做一个选择。"
  },
  {
    type: "basic_profile",
    stage: "generated",
    question_mode: "none",
    confirmed_info: {} as any,
    defaulted_fields: [],
    question_md: "",
    question_box: { question: "", options: [] },
    text: "【用户基础信息】\n用户当前为大二软件工程相关专业学生，处于课程学习与项目实践并行阶段，已有一定学习方向，但仍需要进一步细化目标。\n\n【学习方式偏好】\n用户更适合案例驱动和实践驱动的学习方式，适合按照阶段目标逐步推进，并通过反馈不断修正学习路径。\n\n【学习内容偏好】\n用户适合结合视频、文档、练习题、代码实践和项目案例进行学习，其中项目案例和代码实践可以作为主要学习载体。\n\n【当前能力基础】\n用户具备一定编程基础和软件工程课程基础，擅长项目理解、需求拆解和页面设计表达，薄弱点主要在系统化知识梳理、长期学习节奏和部分底层原理。\n\n【学习目标】\n近期目标是完善课程学习和项目实践能力，长期目标是提升软件开发与 AI 应用项目能力。\n\n【学习约束】\n用户每周预计可投入 6-10 小时学习，主要困难是时间较分散、目标容易变化，需要更清晰的学习路径和阶段性反馈。\n\n【后续规划建议】\n后续可以先围绕当前专业课程和项目方向建立学习路径，将知识点拆分为基础概念、核心技能、实践任务和阶段评估四类内容，并结合练习题、代码实践和项目案例进行动态更新。"
  }
];

export function AiGreetingInput() {
  const { widgetState, setWidgetState } = useAiWidget();
  const cardRef = useRef<HTMLDivElement>(null);
  
  // Global mouse tracking for 3D parallax effect
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const mouseXSpring = useSpring(x, { stiffness: 150, damping: 20 });
  const mouseYSpring = useSpring(y, { stiffness: 150, damping: 20 });
  
  // Transform percentage to degrees
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ['15deg', '-15deg']);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ['-15deg', '15deg']);

  useEffect(() => {
    const handleGlobalMouseMove = (e: MouseEvent) => {
      // Only tilt in 3D when it's floating as a card or widget
      if (widgetState !== 'CENTER_INPUT' && widgetState !== 'WIDGET') return;
      if (!cardRef.current) return;
      
      const rect = cardRef.current.getBoundingClientRect();
      const cardCenterX = rect.left + rect.width / 2;
      const cardCenterY = rect.top + rect.height / 2;
      
      const diffX = e.clientX - cardCenterX;
      const diffY = e.clientY - cardCenterY;
      
      // Normalize to a percentage of screen width to give a consistent parallax depth
      const xPct = Math.max(-0.5, Math.min(0.5, diffX / window.innerWidth));
      const yPct = Math.max(-0.5, Math.min(0.5, diffY / window.innerHeight));
      
      x.set(xPct);
      y.set(yPct);
    };

    const handleGlobalMouseLeave = () => {
      x.set(0);
      y.set(0);
    };

    window.addEventListener('mousemove', handleGlobalMouseMove);
    document.addEventListener('mouseleave', handleGlobalMouseLeave);

    return () => {
      window.removeEventListener('mousemove', handleGlobalMouseMove);
      document.removeEventListener('mouseleave', handleGlobalMouseLeave);
    };
  }, [widgetState, x, y]);

  const handleCardClick = () => {
    if (widgetState === 'CENTER_INPUT' || widgetState === 'WIDGET') {
      // Reset tilt so the expanded modal lays perfectly flat against the screen
      x.set(0);
      y.set(0);
      setWidgetState('EXPANDED');
    }
  };

  return (
    <StyledWrapper>
      <motion.div 
        ref={cardRef}
        layout
        onClick={handleCardClick}
        className={`card ${widgetState === 'CENTER_INPUT' ? 'initial' : widgetState}`} 
        variants={{
          initial: { width: 260, height: 160 },
          expanded: { width: '85vw', height: '85vh' },
          widget: { width: 100, height: 100 }
        }}
        initial="initial"
        animate={
          widgetState === 'EXPANDED' ? 'expanded' : 
          widgetState === 'WIDGET' ? 'widget' : 'initial'
        }
        transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        style={{ 
          rotateX: widgetState === 'EXPANDED' ? 0 : rotateX, 
          rotateY: widgetState === 'EXPANDED' ? 0 : rotateY,
          backgroundColor: widgetState === 'EXPANDED' ? 'var(--color-bg-surface, #ffffff)' : 'transparent',
          cursor: widgetState === 'EXPANDED' ? 'default' : 'pointer'
        }}
      >
        {widgetState === 'EXPANDED' ? (
          <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', padding: '24px', overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <AiEyes layoutId="eyes" isHappy />
              <button 
                onClick={(e) => {
                  e.stopPropagation();
                  setWidgetState('WIDGET');
                }} 
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px', color: 'var(--color-text-primary, #333)' }}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 15l-6-6-6 6"/></svg>
              </button>
            </div>
            <div className="ChatFlow" style={{ flex: 1, padding: '0 var(--space-16, 16px)', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-24, 24px)' }}>
              {mockMessages.map((msg, idx) => (
                <ChatCard key={idx} message={msg} />
              ))}
            </div>
            <div className="chat" style={{ marginTop: 'auto', background: 'var(--color-bg-subtle, #f5f5f5)', borderRadius: '16px', padding: '12px' }}>
              <div className="chat-bot" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <textarea placeholder="Imagine Something...✦˚" name="chat_bot" id="chat_bot" defaultValue={""} style={{ width: '100%', minHeight: '60px', padding: '8px', border: 'none', background: 'transparent', outline: 'none', resize: 'none', fontFamily: 'var(--font-body), sans-serif', color: 'var(--color-text-primary, #333)' }} />
                <div className="options" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '8px' }}>
                  <div className="btns-add" style={{ display: 'flex', gap: '8px' }}>
                    <button className="icon-btn">
                      <svg viewBox="0 0 24 24" height={20} width={20} xmlns="http://www.w3.org/2000/svg">
                        <path d="M7 8v8a5 5 0 1 0 10 0V6.5a3.5 3.5 0 1 0-7 0V15a2 2 0 0 0 4 0V8" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" stroke="currentColor" fill="none" />
                      </svg>
                    </button>
                    <button className="icon-btn">
                      <svg xmlns="http://www.w3.org/2000/svg" width={20} height={20} viewBox="0 0 24 24">
                        <path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zm0 10a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zm10 0a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1zm0-8h6m-3-3v6" />
                      </svg>
                    </button>
                  </div>
                  <button className="btn-submit">
                    <i>
                      <svg viewBox="0 0 512 512" height={20} width={20}>
                        <path d="M473 39.05a24 24 0 0 0-25.5-5.46L47.47 185h-.08a24 24 0 0 0 1 45.16l.41.13l137.3 58.63a16 16 0 0 0 15.54-3.59L422 80a7.07 7.07 0 0 1 10 10L226.66 310.26a16 16 0 0 0-3.59 15.54l58.65 137.38c.06.2.12.38.19.57c3.2 9.27 11.3 15.81 21.09 16.25h1a24.63 24.63 0 0 0 23-15.46L478.39 64.62A24 24 0 0 0 473 39.05" fill="currentColor" />
                      </svg>
                    </i>
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <>
            <div className="background-blur-balls">
              <div className="balls">
                <span className="ball rosa" />
                <span className="ball violet" />
                <span className="ball green" />
                <span className="ball cyan" />
              </div>
            </div>
            <div className="content-card">
              <div className="background-blur-card">
                <AiEyes layoutId="eyes" />
                <AiEyes isHappy />
              </div>
            </div>
          </>
        )}
      </motion.div>
    </StyledWrapper>
  );
}

const StyledWrapper = styled.div`
  perspective: 1000px;
  display: flex;
  align-items: center;
  justify-content: center;

  /* Explicit border radius mapping to beat the 3D overflow bug in WebKit */
  .card.initial,
  .card.initial .background-blur-balls,
  .card.initial .content-card {
    border-radius: 48px;
    transition: border-radius 0.6s ease;
  }
  
  .card.EXPANDED, .card.WIDGET,
  .card.EXPANDED .background-blur-balls, .card.WIDGET .background-blur-balls,
  .card.EXPANDED .content-card, .card.WIDGET .content-card {
    border-radius: 32px;
    transition: border-radius 0.6s ease;
  }

  .card {
    transform-style: preserve-3d;
    will-change: transform, width, height;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 0 10px 40px rgba(0, 0, 60, 0.1);
    transition: box-shadow 0.3s ease;
  }

  /* 3D Hover Effect Only for Normal/Widget State */
  .card.initial:hover,
  .card.WIDGET:hover {
    box-shadow:
      0 15px 45px rgba(0, 0, 60, 0.15),
      inset 0 0 10px rgba(255, 255, 255, 0.5);
  }

  .background-blur-balls {
    position: absolute;
    left: 0;
    top: 0;
    width: 100%;
    height: 100%;
    z-index: -10;
    background-color: rgba(255, 255, 255, 0.8);
    overflow: hidden;
  }
  
  .balls {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateX(-50%) translateY(-50%);
    animation: rotate-background-balls 10s linear infinite;
  }

  /* Pause background rotation on hover */
  .card:hover .balls {
    animation-play-state: paused;
  }

  .background-blur-balls .ball {
    width: 6rem;
    height: 6rem;
    position: absolute;
    border-radius: 50%;
    filter: blur(30px);
  }

  .background-blur-balls .ball.violet {
    top: 0;
    left: 50%;
    transform: translateX(-50%);
    background-color: #9147ff;
  }

  .background-blur-balls .ball.green {
    bottom: 0;
    left: 50%;
    transform: translateX(-50%);
    background-color: #34d399;
  }

  .background-blur-balls .ball.rosa {
    top: 50%;
    left: 0;
    transform: translateY(-50%);
    background-color: #ec4899;
  }

  .background-blur-balls .ball.cyan {
    top: 50%;
    right: 0;
    transform: translateY(-50%);
    background-color: #05e0f5;
  }

  .content-card {
    width: 100%;
    height: 100%;
    display: flex;
    overflow: hidden;
    transform: translateZ(50px);
    transform-style: preserve-3d;
  }

  .background-blur-card {
    width: 100%;
    height: 100%;
    backdrop-filter: blur(50px);
    display: flex;
    align-items: center;
    justify-content: center;
    transform-style: preserve-3d;
  }

  /* Hide happy eyes by default inside the normal content card */
  .content-card .eyes.happy {
    display: none;
  }
  
  /* Handle Eye Hover State natively */
  .card:hover .content-card .eyes:not(.happy) {
    display: none;
  }
  .card:hover .content-card .eyes.happy {
    display: flex;
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--color-text-whisper, rgba(0, 0, 0, 0.2));
    background-color: transparent;
    border: none;
    cursor: pointer;
    transition: all 0.3s ease;

    &:hover {
      transform: translateY(-2px);
      color: var(--color-text-secondary, #8b8b8b);
    }
  }

  .btn-submit {
    display: flex;
    padding: 2px;
    background-image: linear-gradient(to top, #ff4141, #9147ff, #3b82f6);
    border-radius: 10px;
    box-shadow: inset 0 6px 2px -4px rgba(255, 255, 255, 0.5);
    cursor: pointer;
    border: none;
    outline: none;
    opacity: 0.8;
    transition: all 0.2s ease;

    & i {
      display: flex;
      align-items: center;
      justify-content: center;
      width: 32px;
      height: 32px;
      background: rgba(0, 0, 0, 0.1);
      border-radius: 8px;
      backdrop-filter: blur(3px);
      color: #fff;
    }
    
    & svg {
      transition: all 0.3s ease;
    }
    
    &:hover {
      opacity: 1;
      & svg {
        filter: drop-shadow(0 0 5px #ffffff);
      }
    }

    &:focus svg {
      filter: drop-shadow(0 0 5px #ffffff);
      transform: scale(1.1) rotate(45deg);
    }

    &:active {
      transform: scale(0.95);
    }
  }

  @keyframes rotate-background-balls {
    from {
      transform: translateX(-50%) translateY(-50%) rotate(360deg);
    }
    to {
      transform: translateX(-50%) translateY(-50%) rotate(0);
    }
  }
`;
