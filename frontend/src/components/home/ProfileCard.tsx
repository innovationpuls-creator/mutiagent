import { useState } from 'react';
import { motion, AnimatePresence, useReducedMotion } from 'framer-motion';
import type { UserProfile } from '../../types/profile';
import { motionTokens } from '../../styles/motion-tokens';

interface ProfileCardProps {
  profile: UserProfile;
  completeness: number;
  summaryText: string;
}

const renderField = (value: string | undefined | null, fallback = '暂无限制，自由探索') => {
  if (!value || value.trim() === '' || value === '未提供') {
    return <span className="profile-placeholder">{fallback}</span>;
  }
  return value;
};

/**
 * 主卡片 — 用户画像摘要 (支持内联展开)
 * 复刻 Headspace 主推荐卡片的版式：左侧装饰球体 + 右侧内容摘要
 */
export function ProfileCard({ profile, completeness, summaryText }: ProfileCardProps) {
  const reduceMotion = useReducedMotion();
  const [isExpanded, setIsExpanded] = useState(false);

  const topTags = profile.contentPreference.slice(0, 3);

  return (
    <motion.div
      layout
      className={`profile-card profile-card--interactive ${isExpanded ? 'is-expanded' : ''}`}
      onClick={() => setIsExpanded(!isExpanded)}
      role="button"
      tabIndex={0}
      initial={reduceMotion ? false : { opacity: 0, y: 20 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={{ ...motionTokens.editorial, delay: 0.2 }}
    >
      {/* Whisper badge — 对应 Headspace 的 "TODAY · 10 MIN" */}
      <motion.div layout="position" className="profile-card-whisper">
        <span className="whisper-dot active" />
        <span>今天 · 你的画像</span>
        <span className="whisper-action">
          {isExpanded ? '收起详情' : '查看完整详情'} 
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: 4, transform: isExpanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.3s ease' }}>
            <polyline points="9 18 15 12 9 6"></polyline>
          </svg>
        </span>
      </motion.div>

      {/* 装饰性发光球体 — 对应 Headspace 的 3D 金色球 */}
      <motion.div layout="position" className="profile-sphere-wrap">
        <div className="profile-sphere" aria-hidden="true" />
      </motion.div>

      {/* 画像内容区 */}
      <motion.div layout="position" className="profile-body">
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
      </motion.div>

      {/* 呼吸指示条 — 对应 Headspace 的 "breathe in" 指示器 */}
      <motion.div layout="position" className="profile-breathe-strip">
        <span className="breathe-indicator-dot" aria-hidden="true" />
        <span className="breathe-label">画像完成度</span>
        <div className="breathe-track" role="progressbar" aria-valuenow={completeness} aria-valuemin={0} aria-valuemax={100}>
          <div className="breathe-fill" style={{ width: `${completeness}%` }} />
        </div>
      </motion.div>

      {/* 展开的详细信息内容 */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            className="profile-expanded-content"
            initial={{ opacity: 0, height: 0, marginTop: 0 }}
            animate={{ opacity: 1, height: 'auto', marginTop: 32 }}
            exit={{ opacity: 0, height: 0, marginTop: 0 }}
            transition={motionTokens.editorial}
          >
            <div className="expanded-sections">
              {/* 分组 1: 你的方向 */}
              <div className="expanded-section">
                <div className="section-header">
                  <span className="section-dot dot-lavender" aria-hidden="true" />
                  <h4 className="section-title">你的方向</h4>
                </div>
                <div className="section-grid">
                  <div className="field-group">
                    <span className="field-label">短期目标</span>
                    <span className="field-value">{renderField(profile.shortTermGoal, '暂无明确短期目标，正在摸索')}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">长期目标</span>
                    <span className="field-value">{renderField(profile.longTermGoal, '暂无明确长期目标，自由生长')}</span>
                  </div>
                </div>
              </div>

              {/* 分组 2: 你的现状 */}
              <div className="expanded-section">
                <div className="section-header">
                  <span className="section-dot dot-sage" aria-hidden="true" />
                  <h4 className="section-title">你的现状</h4>
                </div>
                <div className="section-grid">
                  <div className="field-group">
                    <span className="field-label">知识储备</span>
                    <span className="field-value">{renderField(profile.knowledgeFoundation, '正在构建知识体系')}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">实战经验</span>
                    <span className="field-value">{renderField(profile.experience, '准备开始第一次实战')}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">你的优势</span>
                    <span className="field-value">{renderField(profile.strengths, '等待被发掘的潜力')}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">当前瓶颈</span>
                    <span className="field-value">{renderField(profile.weaknesses, '一帆风顺，暂无阻碍')}</span>
                  </div>
                </div>
              </div>

              {/* 分组 3: 你的节奏 */}
              <div className="expanded-section">
                <div className="section-header">
                  <span className="section-dot dot-peach" aria-hidden="true" />
                  <h4 className="section-title">你的节奏</h4>
                </div>
                <div className="section-grid">
                  <div className="field-group">
                    <span className="field-label">学习偏好</span>
                    <span className="field-value">{renderField(profile.learningMethodPreference)}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">节奏偏好</span>
                    <span className="field-value">{renderField(profile.learningPacePreference)}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">可用时间</span>
                    <span className="field-value">{renderField(profile.weeklyAvailableTime, '按需调节，时间自由')}</span>
                  </div>
                  <div className="field-group">
                    <span className="field-label">约束条件</span>
                    <span className="field-value">{renderField(profile.constraints, '暂无限制，自由探索')}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
