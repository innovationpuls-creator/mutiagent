import { useState } from 'react';
import { useLocation } from 'react-router-dom';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import { SproutHero } from '../components/home/SproutHero';
import { SproutInitOverlay } from '../components/onboarding/SproutInitOverlay';
import '../components/home/BlankPage.css';

export function SproutPage() {
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const isFirstLogin = location.state?.isFirstLogin === true;
  const [showOverlay, setShowOverlay] = useState(isFirstLogin);

  return (
    <>
      <motion.main
        className="home-page"
        initial={reduceMotion ? false : { opacity: 0 }}
        animate={reduceMotion ? undefined : { opacity: 1 }}
        exit={
          reduceMotion
            ? { opacity: 0 }
            : { opacity: 0, filter: 'blur(10px)', transition: { duration: 0.4 } }
        }
      >
        {/* 背景层 — 保留 BlankPage 的暖色环境 */}
        <div className="home-ambient-sun" aria-hidden="true" />
        <div className="home-paper-canvas" aria-hidden="true" />

        {/* Hero 内容 */}
        <SproutHero />
      </motion.main>

      <AnimatePresence>
        {showOverlay && (
          <SproutInitOverlay onComplete={() => setShowOverlay(false)} />
        )}
      </AnimatePresence>
    </>
  );
}
