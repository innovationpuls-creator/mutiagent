import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import {
	actionHintVariants,
	breathingGlowClassName,
	whisperVariants,
} from "../../lib/motion";
import "../../styles/node-card.css";

export type NodeStatus = "locked" | "in-progress" | "completed";

export interface NodeCardProps {
	id: string;
	title: string;
	status: NodeStatus;
	agentMessage?: string;
	completedConcepts: number;
	totalConcepts: number;
}

export function NodeCard({
	id,
	title,
	status,
	agentMessage,
	completedConcepts,
	totalConcepts,
}: NodeCardProps) {
	const hasConcepts = totalConcepts > 0;
	const progressRatio = hasConcepts
		? Math.round((completedConcepts / totalConcepts) * 100)
		: 0;
	const isAgentActive = Boolean(agentMessage);

	return (
		<motion.div
			className={
				status === "in-progress"
					? `node-card ${breathingGlowClassName}`
					: "node-card"
			}
			layoutId={`node-card-${id}`}
			initial="rest"
			whileHover="hover"
			animate="rest"
		>
			<div className="node-header">
				<AnimatePresence mode="wait">
					{isAgentActive ? (
						<motion.div
							key="agent-message"
							className="whisper-badge"
							layoutId={`node-agent-${id}`}
							layout="position"
							variants={whisperVariants}
							initial="initial"
							animate="animate"
							exit="exit"
						>
							<span
								className={`whisper-dot ${status === "in-progress" ? "active" : "planner"}`}
							/>
							{agentMessage}
						</motion.div>
					) : (
						<motion.div
							key="course-type"
							className="whisper-badge"
							variants={whisperVariants}
							initial="initial"
							animate="animate"
							exit="exit"
						>
							<span className="whisper-dot feedback" />
							核心概念
						</motion.div>
					)}
				</AnimatePresence>
			</div>

			<div className="node-body">
				<motion.h3
					className="node-title"
					layoutId={`node-title-${id}`}
					layout="position"
				>
					{title}
				</motion.h3>
			</div>

			<div className="node-footer">
				{hasConcepts ? (
					<>
						<span className="node-progress-label">
							知识要点 {completedConcepts}/{totalConcepts}
						</span>
						<span className="node-progress-track" aria-hidden="true">
							<span
								className={`node-progress-fill ${status === "in-progress" ? "active" : ""}`}
								style={{ width: `${progressRatio}%` }}
							/>
						</span>
					</>
				) : (
					<span className="node-progress-label">尚未梳理知识要点</span>
				)}
			</div>

			<motion.div className="action-hint" variants={actionHintVariants}>
				<ArrowRight size={16} strokeWidth={2.5} />
			</motion.div>
		</motion.div>
	);
}
