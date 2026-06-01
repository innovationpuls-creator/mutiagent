import { motion, useReducedMotion } from 'framer-motion';
import type { UserProfile } from '../../types/profile';
import { motionTokens } from '../../styles/motion-tokens';

interface ProfileCardProps {
  profile: UserProfile;
  completeness: number;
  summaryText: string;
}

/**
 * 主卡片 — 用户画像摘要
 * 复刻 Headspace 主推荐卡片的版式：左侧装饰球体 + 右侧内容摘要
 */
export function ProfileCard({ profile, completeness, summaryText }: ProfileCardProps) {
  const reduceMotion = useReducedMotion();

  const topTags = profile.contentPreference.slice(0, 3);

  return (
    <motion.div
      className="profile-card"
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ ...motionTokens.editorial, delay: 0.2 }}
    >
      {/* Whisper badge — 对应 Headspace 的 "TODAY · 10 MIN" */}
      <div className="profile-card-whisper">
        <span className="whisper-dot active" />
        今天 · 你的画像
      </div>

      {/* 装饰性发光球体 — 对应 Headspace 的 3D 金色球 */}
      <div className="profile-sphere-wrap">
        <div className="profile-sphere" aria-hidden="true" />
      </div>

      {/* 画像内容区 */}
      <div className="profile-body">
        <h3 className="profile-summary-title">
          看见自己，
        </h3>
        <p className="profile-summary-subtitle">
          才能走得更远
        </p>

        <p className="profile-summary-text">
          {summaryText}
        </p>

        {/* 标签区 — 对应 Headspace 的教师信息 + breath badge */}
        <div className="profile-tags">
          <span className="profile-tag-avatar" aria-hidden="true">
            {profile.major.charAt(0)}
          </span>
          <span className="profile-tag-name">{profile.major}</span>
          <span className="profile-tag-role">{profile.currentGrade} · {profile.learningStage}</span>
          {topTags.map((tag) => (
            <span className="profile-tag-pill" key={tag}>{tag}</span>
          ))}
        </div>
      </div>

      {/* 呼吸指示条 — 对应 Headspace 的 "breathe in" 指示器 */}
      <div className="profile-breathe-strip">
        <span className="breathe-indicator-dot" aria-hidden="true" />
        <span className="breathe-label">画像完成度</span>
        <div className="breathe-track" role="progressbar" aria-valuenow={completeness} aria-valuemin={0} aria-valuemax={100}>
          <div className="breathe-fill" style={{ width: `${completeness}%` }} />
        </div>
      </div>
    </motion.div>
  );
}
