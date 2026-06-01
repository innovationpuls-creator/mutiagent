import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import { useAuth } from '../../contexts/AuthContext';
import { fetchProfileDashboard } from '../../api/profile';
import type { ProfileDashboardData } from '../../types/profile';
import { ProfileCard } from './ProfileCard';
import { TodayLearningCard } from './TodayLearningCard';
import { RecommendationCard } from './RecommendationCard';
import { motionTokens } from '../../styles/motion-tokens';
import './SproutHero.css';

/**
 * 获取当前时段的中文问候语
 */
function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 6) return '夜深了';
  if (hour < 12) return '早上好';
  if (hour < 14) return '中午好';
  if (hour < 18) return '下午好';
  return '晚上好';
}

/**
 * 获取当前星期的中文名
 */
function getWeekday(): string {
  const days = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];
  return days[new Date().getDay()];
}

/**
 * SproutHero — 萌芽页面的 Hero 仪表板
 *
 * 复刻 Headspace 的版式和信息层级：
 * 1. 问候区 — 个性化 whisper + 大标题
 * 2. 辅助信息条 — 完成度 · 专业 · 阶段
 * 3. 双卡区 — 画像主卡 + 今日学习副卡
 * 4. 底部推荐行 — 3 列柔色小卡
 */
export function SproutHero() {
  const auth = useAuth();
  const reduceMotion = useReducedMotion();
  const [data, setData] = useState<ProfileDashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const username = auth.user?.username ?? '同学';

  useEffect(() => {
    if (!auth.token) {
      setError('请先登录后查看画像数据。');
      return;
    }

    const token = auth.token;
    let alive = true;
    const loadDashboard = () => {
      fetchProfileDashboard(token)
      .then((dashboard) => {
        if (!alive) return;
        setData(dashboard);
        setError(null);
      })
      .catch((err) => {
        if (!alive) return;
        setError(err instanceof Error ? err.message : '画像数据加载失败');
      });
    };

    loadDashboard();
    window.addEventListener('mutiagent-profile-updated', loadDashboard);

    return () => {
      alive = false;
      window.removeEventListener('mutiagent-profile-updated', loadDashboard);
    };
  }, [auth.token]);

  if (error) {
    return (
      <section className="sprout-hero">
        <div className="hero-greeting-zone">
          <p className="hero-whisper">{error}</p>
        </div>
      </section>
    );
  }

  /* 加载态：skeleton 呼吸 */
  if (!data) {
    return (
      <section className="sprout-hero">
        <div className="hero-greeting-zone">
          <motion.div
            style={{
              width: 200,
              height: 20,
              borderRadius: 'var(--radius-full)',
              background: 'var(--color-surface)',
            }}
            animate={reduceMotion ? undefined : { opacity: [0.56, 0.86, 0.56] }}
            transition={{ duration: 2.1, repeat: Infinity, ease: 'easeInOut' }}
          />
        </div>
      </section>
    );
  }

  return (
    <section className="sprout-hero">
      {/* ── 问候区 ── */}
      <div className="hero-greeting-zone">
        <motion.p
          className="hero-whisper"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={reduceMotion ? undefined : { opacity: 1 }}
          transition={motionTokens.editorial}
        >
          {getWeekday()} · {getGreeting()}，{username}
        </motion.p>

        <motion.h1
          className="hero-title"
          initial={reduceMotion ? false : { opacity: 0, y: 12 }}
          animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
          transition={{ ...motionTokens.editorial, delay: 0.1 }}
        >
          了解自己，是成长的
          <span className="hero-title-accent">第一步</span>
          。
        </motion.h1>

        {/* 辅助信息条 — 对应 Headspace 的 streak / sunrise */}
        <motion.div
          className="hero-meta-strip"
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={reduceMotion ? undefined : { opacity: 1 }}
          transition={{ ...motionTokens.editorial, delay: 0.15 }}
        >
          <span className="hero-meta-highlight">
            <span className="hero-whisper-dot" aria-hidden="true" />
            画像完成度 {data.profileCompleteness}%
          </span>
          <span className="hero-meta-separator" aria-hidden="true" />
          <span>{data.profile.major}</span>
          <span className="hero-meta-separator" aria-hidden="true" />
          <span>{data.profile.currentGrade}</span>
        </motion.div>
      </div>

      {/* ── 双卡区 ── */}
      <div className="hero-cards-row">
        <ProfileCard
          profile={data.profile}
          completeness={data.profileCompleteness}
          summaryText={data.profileSummaryText}
        />
        <TodayLearningCard data={data.todayLearning} />
      </div>

      {/* ── 底部推荐行 ── */}
      <div className="hero-recs-row">
        {data.recommendations.map((rec, i) => (
          <RecommendationCard key={rec.id} data={rec} index={i} />
        ))}
      </div>
    </section>
  );
}
