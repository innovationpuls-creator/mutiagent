import { motion, useReducedMotion } from 'framer-motion';
import type { TodayLearning } from '../../types/profile';
import { motionTokens } from '../../styles/motion-tokens';

interface TodayLearningCardProps {
  data: TodayLearning;
}

/**
 * 副卡片 — 今日学习建议
 * 复刻 Headspace 右侧深色 "FOR TONIGHT" 卡片的版式
 */
export function TodayLearningCard({ data }: TodayLearningCardProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.div
      className="today-card"
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ ...motionTokens.editorial, delay: 0.35 }}
    >
      <div>
        <span className="today-card-whisper">今日推荐</span>
      </div>

      <div>
        <h3 className="today-card-title">{data.title}</h3>
        <p className="today-card-desc">{data.description}</p>
      </div>

      <div className="today-card-footer">
        <button
          className="today-play-btn"
          type="button"
          aria-label="开始学习"
        >
          <span className="today-play-icon" aria-hidden="true" />
        </button>
        <span className="today-source-label">{data.source}</span>
      </div>

      {/* 装饰光点 — 对应 Headspace 深色卡上的微妙视觉锚 */}
      <span className="today-card-glow" aria-hidden="true" />
    </motion.div>
  );
}
