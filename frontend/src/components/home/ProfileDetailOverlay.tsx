import { useEffect, useRef } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { UserProfile } from '../../types/profile';
import { motionTokens } from '../../styles/motion-tokens';
import './ProfileDetailOverlay.css';

interface ProfileDetailOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  profile: UserProfile;
}

const renderField = (value: string | undefined | null, fallback = '暂无限制，自由探索') => {
  if (!value || value.trim() === '' || value === '未提供') {
    return <span className="overlay-placeholder">{fallback}</span>;
  }
  return value;
};

export function ProfileDetailOverlay({ isOpen, onClose, profile }: ProfileDetailOverlayProps) {
  const reduceMotion = useReducedMotion();
  const overlayRef = useRef<HTMLDivElement>(null);

  // 展开时锁定背景滚动
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="overlay-portal">
      {/* 用于遮蔽背后零碎元素的底层毛玻璃，防止穿帮 */}
      <motion.div
        className="overlay-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={motionTokens.editorial}
        onClick={onClose}
      />
      
      {/* 与首页小卡片联动的 Hero 形变容器 */}
      <motion.div
        layoutId="profile-card-container"
        ref={overlayRef}
        className="overlay-content"
        role="dialog"
        aria-modal="true"
        initial={reduceMotion ? false : { borderRadius: 'var(--radius-lg)' }}
        animate={reduceMotion ? undefined : { borderRadius: 'var(--radius-2xl, 32px)' }}
        exit={reduceMotion ? undefined : { borderRadius: 'var(--radius-lg)' }}
        transition={{ ...motionTokens.editorial, duration: 0.5, type: 'spring', bounce: 0, damping: 25, stiffness: 200 }}
      >
        <div className="overlay-header">
          <h2 className="overlay-title">我的完整画像</h2>
          <button className="overlay-close-btn" onClick={onClose} aria-label="关闭">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div className="overlay-scroll-area">
          <div className="overlay-body">
            
            <div className="overlay-intro">
              <div className="overlay-sphere" aria-hidden="true" />
              <div className="intro-text">
                <h3>看见自己，</h3>
                <p>才能走得更远</p>
              </div>
            </div>

            {/* 分组 1: 你的方向 (Goals) */}
            <section className="overlay-section">
              <div className="section-header">
                <span className="section-dot dot-lavender" aria-hidden="true" />
                <h3 className="section-title">你的方向</h3>
              </div>
              <div className="section-grid">
                <div className="field-group">
                  <h4 className="field-label">短期目标</h4>
                  <p className="field-value">{renderField(profile.shortTermGoal, '暂无明确短期目标，正在摸索')}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">长期目标</h4>
                  <p className="field-value">{renderField(profile.longTermGoal, '暂无明确长期目标，自由生长')}</p>
                </div>
                <div className="field-group full-width">
                  <h4 className="field-label">目标清晰度</h4>
                  <p className="field-value">{renderField(profile.hasClearGoal)}</p>
                </div>
              </div>
            </section>

            {/* 分组 2: 你的现状 (Status) */}
            <section className="overlay-section">
              <div className="section-header">
                <span className="section-dot dot-sage" aria-hidden="true" />
                <h3 className="section-title">你的现状</h3>
              </div>
              <div className="section-grid">
                <div className="field-group">
                  <h4 className="field-label">知识储备</h4>
                  <p className="field-value">{renderField(profile.knowledgeFoundation, '正在构建知识体系')}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">实战经验</h4>
                  <p className="field-value">{renderField(profile.experience, '准备开始第一次实战')}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">你的优势</h4>
                  <p className="field-value">{renderField(profile.strengths, '等待被发掘的潜力')}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">当前瓶颈</h4>
                  <p className="field-value">{renderField(profile.weaknesses, '一帆风顺，暂无阻碍')}</p>
                </div>
              </div>
            </section>

            {/* 分组 3: 你的节奏 (Preferences) */}
            <section className="overlay-section">
              <div className="section-header">
                <span className="section-dot dot-peach" aria-hidden="true" />
                <h3 className="section-title">你的节奏</h3>
              </div>
              <div className="section-grid">
                <div className="field-group">
                  <h4 className="field-label">学习偏好</h4>
                  <p className="field-value">{renderField(profile.learningMethodPreference)}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">节奏偏好</h4>
                  <p className="field-value">{renderField(profile.learningPacePreference)}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">每周可用时间</h4>
                  <p className="field-value">{renderField(profile.weeklyAvailableTime, '按需调节，时间自由')}</p>
                </div>
                <div className="field-group">
                  <h4 className="field-label">指导需求</h4>
                  <p className="field-value">{renderField(profile.needGuidance)}</p>
                </div>
                <div className="field-group full-width">
                  <h4 className="field-label">约束条件</h4>
                  <p className="field-value">{renderField(profile.constraints, '暂无限制，自由探索')}</p>
                </div>
              </div>
            </section>
          </div>
        </div>
      </motion.div>
    </div>
  );
}
