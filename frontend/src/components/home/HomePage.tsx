import { motion, useReducedMotion } from 'framer-motion';
import './HomePage.css';

export function HomePage() {
  const reduceMotion = useReducedMotion();

  return (
    <motion.main 
      className="home-page"
      initial={reduceMotion ? false : { opacity: 0 }}
      animate={reduceMotion ? undefined : { opacity: 1 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, filter: 'blur(10px)', transition: { duration: 0.4 } }}
    >
      <div className="home-ambient-sun" aria-hidden="true" />
      <div className="home-paper-canvas" aria-hidden="true" />
      
      <section className="home-content">
        <h2>主页</h2>
        <p>思绪的留白画布。</p>
        
        {/* Placeholder for scroll testing */}
        <div style={{ marginTop: '20vh', height: '120vh', display: 'flex', flexDirection: 'column', gap: '40vh' }}>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontStyle: 'italic', opacity: 0.7 }}>
            向下滚动以测试导航栏玻璃态效果...
          </p>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontStyle: 'italic', opacity: 0.5 }}>
            滚动中 (Scrolled &gt; 50px)...
          </p>
          <p style={{ color: 'var(--color-text-muted)', fontSize: '14px', fontStyle: 'italic', opacity: 0.3 }}>
            页面底部。
          </p>
        </div>
      </section>
    </motion.main>
  );
}
