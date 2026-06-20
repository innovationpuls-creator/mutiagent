import { motion, useReducedMotion } from "framer-motion";
import { motionTokens } from "../../styles/motion-tokens";
import type { TodayLearning } from "../../types/profile";
import {
	getOutlineHours,
	getOutlineSummary,
	getSectionDescription,
	getSectionHeading,
	getSectionLabel,
	getTopLevelSections,
} from "../learning/courseKnowledgeHelpers";

interface TodayLearningCardProps {
	data: TodayLearning;
	onClick?: () => void;
	onStartLearning?: () => void;
}

/**
 * 副卡片 — 今日学习建议
 * 复刻 Headspace 右侧深色 "FOR TONIGHT" 卡片的版式
 */
export function TodayLearningCard({
	data,
	onClick,
	onStartLearning,
}: TodayLearningCardProps) {
	const reduceMotion = useReducedMotion();
	const hasDetailAction = typeof onClick === "function";
	const hasStartAction = typeof onStartLearning === "function";
	const outlineSectionCount = data.currentCourseOutline?.sections.length ?? 0;
	const topLevelSections = data.currentCourseOutline
		? getTopLevelSections(data.currentCourseOutline).slice(0, 2)
		: [];

	return (
		<motion.div
			className="today-card"
			initial={reduceMotion ? false : { opacity: 0, y: 20 }}
			animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
			transition={{ ...motionTokens.editorial, delay: 0.35 }}
		>
			<div>
				<div className="today-card-whisper-row">
					<span className="today-card-whisper">今日推荐</span>
					{outlineSectionCount > 0 && (
						<span className="today-card-outline-tag">已生成课程大纲</span>
					)}
				</div>
			</div>

			<div>
				<h3 className="today-card-title">
					{data.currentLearningCourse?.course_or_chapter_theme ?? data.title}
				</h3>
				<p className="today-card-desc">
					{data.currentLearningCourse?.current_focus ?? data.description}
				</p>
				{outlineSectionCount > 0 && (
					<p className="today-card-outline-meta">
						共 {outlineSectionCount} 个章节节点，已可展开查看详细学习顺序。
					</p>
				)}
				{data.currentCourseOutline && (
					<section
						className="today-card-outline-preview"
						aria-label="课程大纲主线"
					>
						<div className="today-card-outline-preview-head">
							<strong>课程大纲主线</strong>
							<span>{getOutlineHours(data.currentCourseOutline)}</span>
						</div>
						<p className="today-card-outline-summary">
							{getOutlineSummary(data.currentCourseOutline)}
						</p>
						<div className="today-card-outline-list">
							{topLevelSections.map((section) => (
								<article
									className="today-card-outline-item"
									key={section.section_id}
								>
									<span>{getSectionLabel(section.section_id)}</span>
									<div>
										<strong>{getSectionHeading(section)}</strong>
										<p>{getSectionDescription(section)}</p>
									</div>
								</article>
							))}
						</div>
					</section>
				)}
			</div>

			<div className="today-card-footer">
				<div className="today-card-actions">
					{hasStartAction && (
						<button
							className="today-play-btn"
							type="button"
							aria-label="开始学习"
							onClick={() => {
								onStartLearning();
							}}
						>
							<span className="today-play-icon" aria-hidden="true" />
						</button>
					)}
					{hasDetailAction && (
						<button
							className="today-detail-btn"
							type="button"
							aria-label="打开今日学习详情"
							onClick={() => {
								onClick?.();
							}}
						>
							查看详情
						</button>
					)}
				</div>
				<span className="today-source-label">{data.source}</span>
			</div>

			{/* 装饰光点 — 对应 Headspace 深色卡上的微妙视觉锚 */}
			<span className="today-card-glow" aria-hidden="true" />
		</motion.div>
	);
}
