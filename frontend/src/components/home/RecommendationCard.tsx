import { motion, useReducedMotion } from "framer-motion";
import { motionTokens } from "../../styles/motion-tokens";
import type {
	LearningRecommendation,
	RecommendationAccent,
} from "../../types/profile";

interface RecommendationCardProps {
	data: LearningRecommendation;
	index: number;
}

/**
 * 底部推荐小卡片
 * 复刻 Headspace 底部 3 个场景化推荐（通勤/会前/收件箱）的版式
 * 每张卡片使用不同的柔色背景（lavender / sage / peach）
 */
export function RecommendationCard({ data, index }: RecommendationCardProps) {
	const reduceMotion = useReducedMotion();

	return (
		<motion.button
			className={`rec-card rec-card--${data.accent}`}
			type="button"
			initial={reduceMotion ? false : { opacity: 0, y: 16 }}
			animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
			transition={{ ...motionTokens.editorial, delay: 0.5 + index * 0.1 }}
			aria-label={`${data.title} — ${data.duration}`}
		>
			<div className={`rec-dot rec-dot--${data.accent}`} aria-hidden="true" />
			<h4 className="rec-title">{data.title}</h4>
			<p className="rec-meta">
				{data.duration} · {data.description}
			</p>
		</motion.button>
	);
}
