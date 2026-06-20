import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import React from "react";
import {
	actionHintVariants,
	breathingGlowVariants,
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
	// Ensure we don't go below 15% width so the pill remains beautifully pebble-shaped
	const rawRatio =
		totalConcepts > 0 ? (completedConcepts / totalConcepts) * 100 : 0;
	const progressRatio = Math.max(15, rawRatio);
	const isAgentActive = Boolean(agentMessage);

	return (
		<motion.div
			className="node-card"
			layoutId={`node-card-${id}`}
			initial="rest"
			whileHover="hover"
			animate={status === "in-progress" ? ["rest", "animate"] : "rest"}
			variants={status === "in-progress" ? breathingGlowVariants : undefined}
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
				<div className="pill-track">
					<div
						className={`pill-inner ${status === "in-progress" ? "active" : ""}`}
						style={{ width: `${progressRatio}%` }}
					>
						<span className="pill-label">
							{completedConcepts}/{totalConcepts}
						</span>
					</div>
				</div>
			</div>

			<motion.div className="action-hint" variants={actionHintVariants}>
				<ArrowRight size={16} strokeWidth={2.5} />
			</motion.div>
		</motion.div>
	);
}
