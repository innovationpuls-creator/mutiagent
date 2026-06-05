import { useEffect } from 'react';
import { motion, useReducedMotion } from 'framer-motion';
import type { TodayLearning } from '../../types/profile';
import { motionTokens } from '../../styles/motion-tokens';
import {
  getChildSections,
  getOutlineHours,
  getOutlineSummary,
  getOrderedSections as getOrderedOutlineSections,
  getReadableLearningSequence,
  getSectionDescription,
  getSectionHeading,
  getSectionLabel,
} from '../learning/courseKnowledgeHelpers';
import './TodayLearningDetailOverlay.css';

interface TodayLearningDetailOverlayProps {
  isOpen: boolean;
  onClose: () => void;
  data: TodayLearning;
}

function renderList(items: string[]) {
  if (items.length === 0) {
    return <p className="today-detail-empty">等待课程 Agent 补充。</p>;
  }

  return (
    <ul>
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function renderOutlineSectionTree(
  sections: NonNullable<TodayLearning['currentCourseOutline']>['sections'],
  parentId: string | null,
) {
  const children = getChildSections(sections, parentId);
  if (children.length === 0) {
    return null;
  }

  return (
    <div className="today-detail-outline-children">
      {children.map((section) => (
        <div className="today-detail-outline-child" key={section.section_id}>
          <strong>{getSectionHeading(section)}</strong>
          <p>{getSectionDescription(section)}</p>
          {section.key_knowledge_points.length > 0 && renderList(section.key_knowledge_points)}
          {renderOutlineSectionTree(sections, section.section_id)}
        </div>
      ))}
    </div>
  );
}

export function TodayLearningDetailOverlay({
  isOpen,
  onClose,
  data,
}: TodayLearningDetailOverlayProps) {
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen || !data.currentCourseDetail || !data.currentLearningCourse) return null;

  const course = data.currentCourseDetail;
  const current = data.currentLearningCourse;
  const orderedSections = data.currentCourseOutline
    ? getOrderedOutlineSections(data.currentCourseOutline)
    : [];
  const topLevelSections = orderedSections.filter((section) => section.parent_section_id === null);
  const learningSequence = data.currentCourseOutline
    ? getReadableLearningSequence(data.currentCourseOutline)
    : course.learning_sequence;

  return (
    <div className="today-detail-portal">
      <motion.div
        className="today-detail-backdrop"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={motionTokens.editorial}
        onClick={onClose}
      />

      <motion.article
        className="today-detail-panel"
        role="dialog"
        aria-modal="true"
        aria-label="今日学习详情"
        initial={reduceMotion ? false : { opacity: 0, y: 16, scale: 0.98 }}
        animate={reduceMotion ? undefined : { opacity: 1, y: 0, scale: 1 }}
        exit={reduceMotion ? undefined : { opacity: 0, y: 16, scale: 0.98 }}
        transition={motionTokens.editorial}
      >
        <header className="today-detail-header">
          <span>今日推荐 · 当前课程</span>
          <button type="button" onClick={onClose} aria-label="关闭今日学习详情">
            ×
          </button>
        </header>

        <section className="today-detail-hero">
          <p>{current.progress_state}</p>
          <h2>{current.course_or_chapter_theme}</h2>
          <strong>{current.current_focus}</strong>
          <p>{current.next_action}</p>
        </section>

        <section className="today-detail-grid">
          <div className="today-detail-section">
            <h3>课程目标</h3>
            <p>{course.course_goal}</p>
          </div>

          <div className="today-detail-section">
            <h3>时间安排</h3>
            <p>{course.time_arrangement.semester_scope} · {course.time_arrangement.duration}</p>
            <p>{course.time_arrangement.pace_reason}</p>
          </div>

          <div className="today-detail-section">
            <h3>重点</h3>
            {renderList(course.key_points)}
          </div>

          <div className="today-detail-section">
            <h3>难点</h3>
            {renderList(course.difficult_points)}
          </div>

          <div className="today-detail-section">
            <h3>推荐学习步骤</h3>
            {renderList(learningSequence)}
          </div>

          <div className="today-detail-section">
            <h3>验收标准</h3>
            {renderList(course.acceptance_criteria)}
          </div>

          {data.currentCourseOutline && (
            <>
              <div className="today-detail-section">
                <h3>课程大纲说明</h3>
                <p>{getOutlineSummary(data.currentCourseOutline)}</p>
                <p>预计总投入：{getOutlineHours(data.currentCourseOutline)}</p>
              </div>

              <div className="today-detail-section today-detail-section--wide">
                <h3>章节主线</h3>
                <div className="today-detail-outline-stack">
                  {topLevelSections.map((section) => (
                    <article className="today-detail-outline-card" key={section.section_id}>
                      <div className="today-detail-outline-head">
                        <span>{getSectionLabel(section.section_id)}</span>
                        <div>
                          <strong>{getSectionHeading(section)}</strong>
                          <p>{getSectionDescription(section)}</p>
                        </div>
                      </div>
                      {section.key_knowledge_points.length > 0 && renderList(section.key_knowledge_points)}
                      {renderOutlineSectionTree(orderedSections, section.section_id)}
                    </article>
                  ))}
                </div>
              </div>
            </>
          )}
        </section>

        <section className="today-detail-following">
          <h3>同年级后续课程</h3>
          {data.followingCourses.length === 0 ? (
            <p className="today-detail-empty">当前年级后续课程已完成。</p>
          ) : (
            <ol>
              {data.followingCourses.map((item) => (
                <li key={item.course_node_id}>{item.course_or_chapter_theme}</li>
              ))}
            </ol>
          )}
        </section>
      </motion.article>
    </div>
  );
}
