import React, { useRef } from 'react';
import { motion, useMotionValue, useSpring, useTransform } from 'framer-motion';
import styled from 'styled-components';
import { AiEyes } from './AiEyes';
import { useAiWidget } from '../../context/AiWidgetContext';

export function AiGreetingInput() {
  const { widgetState, setWidgetState } = useAiWidget();
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const mouseXSpring = useSpring(x, { stiffness: 150, damping: 20 });
  const mouseYSpring = useSpring(y, { stiffness: 150, damping: 20 });
  const rotateX = useTransform(mouseYSpring, [-0.5, 0.5], ['15deg', '-15deg']);
  const rotateY = useTransform(mouseXSpring, [-0.5, 0.5], ['-15deg', '15deg']);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (widgetState !== 'CENTER_INPUT' && widgetState !== 'WIDGET') return;
    const rect = e.currentTarget.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    const xPct = mouseX / width - 0.5;
    const yPct = mouseY / height - 0.5;
    x.set(xPct);
    y.set(yPct);
  };

  const handleMouseLeave = () => {
    x.set(0);
    y.set(0);
  };

  return (
    <StyledWrapper onMouseMove={handleMouseMove} onMouseLeave={handleMouseLeave}>
      <div className="container-ai-input">
        <label className="container-wrap">
          <input type="checkbox" />
          <motion.div 
            layout
            className="card" 
            variants={{
              initial: { width: 260, height: 160, borderRadius: 48 },
              expanded: { width: '85vw', height: '85vh', borderRadius: 32 }
            }}
            initial="initial"
            animate={widgetState === 'EXPANDED' ? 'expanded' : 'initial'}
            style={{ 
              rotateX: widgetState === 'EXPANDED' ? 0 : rotateX, 
              rotateY: widgetState === 'EXPANDED' ? 0 : rotateY,
              overflow: 'hidden',
              backgroundColor: widgetState === 'EXPANDED' ? 'var(--color-bg-surface, #ffffff)' : 'transparent'
            }}
          >
            {widgetState === 'EXPANDED' ? (
              <div style={{ display: 'flex', flexDirection: 'column', width: '100%', height: '100%', padding: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <AiEyes layoutId="eyes" isHappy />
                  <button onClick={() => setWidgetState('WIDGET')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '8px' }}>
                    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 15l-6-6-6 6"/></svg>
                  </button>
                </div>
                <div className="ChatFlow" style={{ flex: 1, padding: '0 var(--space-16, 16px)' }} />
                <div className="chat" style={{ marginTop: 'auto', background: 'var(--color-bg-subtle, #f5f5f5)', borderRadius: '16px', padding: '8px' }}>
                  <div className="chat-bot">
                    <textarea placeholder="Imagine Something...✦˚" name="chat_bot" id="chat_bot" defaultValue={""} style={{ width: '100%', minHeight: '60px', padding: '8px', border: 'none', background: 'transparent', outline: 'none' }} />
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
                <div className="container-ai-chat">
                  <div className="chat">
                    <div className="chat-bot">
                      <textarea placeholder="Imagine Something...✦˚" name="chat_bot" id="chat_bot" defaultValue={""} />
                    </div>
                    <div className="options">
                      <div className="btns-add">
                        <button>
                          <svg viewBox="0 0 24 24" height={20} width={20} xmlns="http://www.w3.org/2000/svg">
                            <path d="M7 8v8a5 5 0 1 0 10 0V6.5a3.5 3.5 0 1 0-7 0V15a2 2 0 0 0 4 0V8" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" stroke="currentColor" fill="none" />
                          </svg>
                        </button>
                        <button>
                          <svg xmlns="http://www.w3.org/2000/svg" width={20} height={20} viewBox="0 0 24 24">
                            <path fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zm0 10a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1zm10 0a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v4a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1zm0-8h6m-3-3v6" />
                          </svg>
                        </button>
                        <button>
                          <svg xmlns="http://www.w3.org/2000/svg" width={20} height={20} viewBox="0 0 24 24">
                            <path fill="currentColor" d="M12 22C6.477 22 2 17.523 2 12S6.477 2 12 2s10 4.477 10 10s-4.477 10-10 10m-2.29-2.333A17.9 17.9 0 0 1 8.027 13H4.062a8.01 8.01 0 0 0 5.648 6.667M10.03 13c.151 2.439.848 4.73 1.97 6.752A15.9 15.9 0 0 0 13.97 13zm9.908 0h-3.965a17.9 17.9 0 0 1-1.683 6.667A8.01 8.01 0 0 0 19.938 13M4.062 11h3.965A17.9 17.9 0 0 1 9.71 4.333A8.01 8.01 0 0 0 4.062 11m5.969 0h3.938A15.9 15.9 0 0 0 12 4.248A15.9 15.9 0 0 0 10.03 11m4.259-6.667A17.9 17.9 0 0 1 15.973 11h3.965a8.01 8.01 0 0 0-5.648-6.667" />
                          </svg>
                        </button>
                      </div>
                      <button className="btn-submit">
                        <i>
                          <svg viewBox="0 0 512 512">
                            <path d="M473 39.05a24 24 0 0 0-25.5-5.46L47.47 185h-.08a24 24 0 0 0 1 45.16l.41.13l137.3 58.63a16 16 0 0 0 15.54-3.59L422 80a7.07 7.07 0 0 1 10 10L226.66 310.26a16 16 0 0 0-3.59 15.54l58.65 137.38c.06.2.12.38.19.57c3.2 9.27 11.3 15.81 21.09 16.25h1a24.63 24.63 0 0 0 23-15.46L478.39 64.62A24 24 0 0 0 473 39.05" fill="currentColor" />
                          </svg>
                        </i>
                      </button>
                    </div>
                  </div>
                </div>
              </>
            )}
          </motion.div>
        </label>
      </div>
    </StyledWrapper>
  );
}

const StyledWrapper = styled.div`
  /* Include all CSS exactly as provided in the design spec input, mapping background-color to var(--color-bg-surface) where appropriate to blend properly. */
  .container-ai-input {
    --perspective: 1000px;
    --translateY: 45px;
    position: absolute;
    left: 0;
    right: 0;
    top: -2.5rem;
    bottom: -2.5rem;
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    transform-style: preserve-3d;
  }
  
  .container-wrap {
    display: flex;
    align-items: center;
    justify-items: center;
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateX(-50%) translateY(-50%);
    z-index: 9;
    transform-style: preserve-3d;
    cursor: pointer;
    padding: 4px;
    transition: all 0.3s ease;
  }

  .container-wrap:hover {
    padding: 0;
  }

  .container-wrap:active {
    transform: translateX(-50%) translateY(-50%) scale(0.95);
  }

  .container-wrap:after {
    content: "";
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateX(-50%) translateY(-55%);
    width: 12rem;
    height: 11rem;
    background-color: var(--color-bg-subtle, #dedfe0);
    border-radius: 3.2rem;
    transition: all 0.3s ease;
  }

  .container-wrap:hover:after {
    transform: translateX(-50%) translateY(-50%);
    height: 12rem;
  }

  .container-wrap input {
    opacity: 0;
    width: 0;
    height: 0;
    position: absolute;
  }

  .container-wrap input:checked + .card .eyes {
    opacity: 0;
  }

  .container-wrap input:checked + .card .content-card {
    width: 260px;
    height: 160px;
  }

  .container-wrap input:checked + .card .background-blur-balls {
    border-radius: 20px;
  }

  .container-wrap input:checked + .card .container-ai-chat {
    opacity: 1;
    visibility: visible;
    z-index: 99999;
    pointer-events: visible;
  }

  .card {
    width: 100%;
    height: 100%;
    transform-style: preserve-3d;
    will-change: transform;
    transition: all 0.6s ease;
    border-radius: 3rem;
    display: flex;
    align-items: center;
    transform: translateZ(50px);
    justify-content: center;
  }

  .card:hover {
    box-shadow:
      0 10px 40px rgba(0, 0, 60, 0.25),
      inset 0 0 10px rgba(255, 255, 255, 0.5);
  }

  .background-blur-balls {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateX(-50%) translateY(-50%);
    width: 100%;
    height: 100%;
    z-index: -10;
    border-radius: 3rem;
    transition: all 0.3s ease;
    background-color: var(--color-bg-glass, rgba(255, 255, 255, 0.1));
    overflow: hidden;
  }
  .balls {
    position: absolute;
    left: 50%;
    top: 50%;
    transform: translateX(-50%) translateY(-50%);
    animation: rotate-background-balls 10s linear infinite;
  }

  .container-wrap:hover .balls {
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
    width: 12rem;
    height: 12rem;
    display: flex;
    border-radius: 3rem;
    transition: all 0.3s ease;
    overflow: hidden;
  }

  .background-blur-card {
    width: 100%;
    height: 100%;
    backdrop-filter: blur(50px);
  }

  .eyes {
    position: absolute;
    left: 50%;
    bottom: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    justify-content: center;
    height: 52px;
    gap: 2rem;
    transition: all 0.3s ease;

    & .eye {
      width: 26px;
      height: 52px;
      background-color: var(--color-text-primary, #fff);
      border-radius: 16px;
      animation: animate-eyes 10s infinite linear;
      transition: all 0.3s ease;
    }
  }

  .eyes.happy {
    display: none;
    color: var(--color-text-primary, #fff);
    gap: 0;

    & svg {
      width: 60px;
    }
  }

  .container-wrap:hover .eyes .eye {
    display: none;
  }

  .container-wrap:hover .eyes.happy {
    display: flex;
  }

  .container-ai-chat {
    position: absolute;
    width: 100%;
    height: 100%;
    padding: 6px;
    opacity: 0;
    pointer-events: none;
  }

  .container-wrap .card .chat {
    display: flex;
    justify-content: space-between;
    flex-direction: column;
    border-radius: 15px;
    width: 100%;
    height: 100%;
    padding: 4px;
    overflow: hidden;
    background-color: var(--color-bg-surface, #ffffff);
  }

  .container-wrap .card .chat .chat-bot {
    position: relative;
    display: flex;
    height: 100%;
    transition: all 0.3s ease;
  }

  .card .chat .chat-bot textarea {
    background-color: transparent;
    border-radius: 16px;
    border: none;
    width: 100%;
    height: 100%;
    color: var(--color-text-secondary, #8b8b8b);
    font-family: var(--font-body), sans-serif;
    font-size: 14px;
    font-weight: 400;
    padding: 10px;
    resize: none;
    outline: none;

    &::-webkit-scrollbar {
      width: 6px;
      height: 10px;
    }

    &::-webkit-scrollbar-track {
      background: transparent;
    }

    &::-webkit-scrollbar-thumb {
      background: var(--color-border-subtle, #dedfe0);
      border-radius: 5px;
    }

    &::-webkit-scrollbar-thumb:hover {
      background: var(--color-text-secondary, #8b8b8b);
      cursor: pointer;
    }

    &::placeholder {
      color: var(--color-text-whisper, #dedfe0);
      transition: all 0.3s ease;
    }
    &:focus::placeholder {
      color: var(--color-text-secondary, #8b8b8b);
    }
  }

  .card .chat .options {
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    padding: 10px;

    & button {
      transition: all 0.3s ease;
    }
  }

  .card .chat .options .btns-add {
    display: flex;
    gap: 8px;

    & button {
      display: flex;
      color: var(--color-text-whisper, rgba(0, 0, 0, 0.1));
      background-color: transparent;
      border: none;
      cursor: pointer;
      transition: all 0.3s ease;

      &:hover {
        transform: translateY(-5px);
        color: var(--color-text-secondary, #8b8b8b);
      }
    }
  }

  .card .chat .options .btn-submit {
    display: flex;
    padding: 2px;
    background-image: linear-gradient(to top, #ff4141, #9147ff, #3b82f6);
    border-radius: 10px;
    box-shadow: inset 0 6px 2px -4px rgba(255, 255, 255, 0.5);
    cursor: pointer;
    border: none;
    outline: none;
    opacity: 0.7;
    transition: all 0.15s ease;

    & i {
      width: 30px;
      height: 30px;
      padding: 6px;
      background: rgba(0, 0, 0, 0.1);
      border-radius: 10px;
      backdrop-filter: blur(3px);
      color: #cfcfcf;
    }
    & svg {
      transition: all 0.3s ease;
    }
    &:hover {
      opacity: 1;
      & svg {
        color: #f3f6fd;
        filter: drop-shadow(0 0 5px #ffffff);
      }
    }

    &:focus svg {
      color: #f3f6fd;
      filter: drop-shadow(0 0 5px #ffffff);
      transform: scale(1.2) rotate(45deg) translateX(-2px) translateY(1px);
    }

    &:active {
      transform: scale(0.92);
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

  @keyframes animate-eyes {
    46% { height: 52px; }
    48% { height: 20px; }
    50% { height: 52px; }
    96% { height: 52px; }
    98% { height: 20px; }
    100% { height: 52px; }
  }
`;
