import { motion, useReducedMotion } from 'framer-motion';

export function MultiAgentHero() {
  const reduceMotion = useReducedMotion();
  return (
    <aside className="auth-art-console">
      <div className="console-mac-dots" aria-hidden="true">
        <span className="console-dot close" />
        <span className="console-dot min" />
        <span className="console-dot max" />
      </div>

      <div className="console-hero">
        <div className="console-hero-tag">「 A QUIET SPACE TO LEARN 」</div>
        <h1 className="console-hero-title">
          从一句轻声的提问，<br/>到一张<em>自然舒展</em>的学习地图。
        </h1>
        <div className="console-hero-subtitle">
          认知推演与未来重塑  |  多智能体协作网络
        </div>
      </div>

      <div className="console-sphere-area">
        <div className="agent-sphere-container">
          {reduceMotion ? (
            <div className="agent-sphere" aria-hidden="true" />
          ) : (
            <motion.div 
              className="agent-sphere" 
              aria-hidden="true" 
              animate={{ y: [0, -12, 0] }} 
              transition={{ duration: 4, repeat: Infinity, ease: 'easeInOut' }} 
            />
          )}
          <div className="agent-sphere-text">
            <h2>
              Softly, <br/>
              <em>AI connects the dots.</em>
            </h2>
            <p>
              你不必独自面对庞杂的信息。智能体在后台静默交织——拆解、寻源、复盘，为你理清一切，只留下一条从容的路径。
            </p>
          </div>
        </div>
        
        <div className="agent-player-bar" style={{ width: '100%' }}>
          <button className="player-btn" aria-label="Play sample" type="button">▶</button>
          <div className="player-info">
            <strong>Focus Agent</strong>
            <span>正在为你梳理脉络 · 14:12 on path</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
