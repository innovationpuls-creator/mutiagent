import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import React, { useEffect, useState } from "react";
import { breathingGlowVariants, whisperVariants } from "../../lib/motion";
import { EditorialMarkdown } from "./EditorialMarkdown";
import "../../styles/node-learning-view.css";

interface NodeLearningViewProps {
	nodeId: string;
	title: string;
	agentMessage: string;
	onClose: () => void;
	// In a real app, markdownContent would be fetched dynamically
	markdownContent?: string;
}

// Graceful Hydration Skeleton
function SkeletonHydration() {
	return (
		<motion.div
			className="skeleton-container"
			initial={{ opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
		>
			<div className="skeleton-line" />
			<div className="skeleton-line medium" />
			<div className="skeleton-line" />
			<div className="skeleton-line short" />
			<div style={{ height: "var(--space-lg)" }} />
			<div className="skeleton-line medium" />
			<div className="skeleton-line" />
			<div className="skeleton-line short" />
		</motion.div>
	);
}

export function NodeLearningView({
	nodeId,
	title,
	agentMessage,
	onClose,
	markdownContent,
}: NodeLearningViewProps) {
	const [isLoaded, setIsLoaded] = useState(false);

	// Simulate network fetching delay for the deep knowledge blocks
	useEffect(() => {
		const timer = setTimeout(() => {
			setIsLoaded(true);
		}, 2500);
		return () => clearTimeout(timer);
	}, []);

	return (
		<motion.div
			className="learning-view-root"
			layoutId={`node-card-${nodeId}`} // The Shared Layout Transition anchor
			initial={{ borderRadius: 32 }}
			animate={{ borderRadius: 0 }}
			exit={{ borderRadius: 32 }}
			transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
		>
			<button className="learning-close-btn" onClick={onClose}>
				<X size={20} />
			</button>

			{/* The Editorial Canvas (Left) */}
			<div className="learning-left-pane">
				<div className="learning-content-wrapper">
					<div className="learning-title-area">
						{/* layout="position" acts as the absolute defense against font stretching */}
						<motion.h1
							className="editorial-h1"
							layoutId={`node-title-${nodeId}`}
							layout="position"
							style={{ margin: 0 }}
						>
							{title}
						</motion.h1>
					</div>

					<AnimatePresence mode="wait">
						{!isLoaded || !markdownContent ? (
							<SkeletonHydration key="skeleton" />
						) : (
							<motion.div
								key="content"
								initial={{ opacity: 0, y: 10 }}
								animate={{ opacity: 1, y: 0 }}
								transition={{ duration: 0.6, ease: [0.25, 1, 0.5, 1] }}
							>
								<EditorialMarkdown content={markdownContent} />
							</motion.div>
						)}
					</AnimatePresence>
				</div>
			</div>

			{/* The Agent Glass-Hub (Right) */}
			<motion.div
				className="learning-right-pane"
				initial={{ opacity: 0, x: 20 }}
				animate={{ opacity: 1, x: 0 }}
				transition={{ delay: 0.2, duration: 0.5 }}
			>
				<div className="agent-hub-header">
					{/* Agent Whisper transitioning seamlessly into the header */}
					<motion.div
						className="whisper-badge"
						layoutId={`node-agent-${nodeId}`}
						layout="position"
					>
						<motion.span
							className="whisper-dot active"
							variants={breathingGlowVariants}
							animate="animate"
						/>
						{agentMessage || "Agent is monitoring your progress..."}
					</motion.div>
				</div>

				{/* Agent conversational interface would go here */}
				<div style={{ flex: 1 }} />
			</motion.div>
		</motion.div>
	);
}
