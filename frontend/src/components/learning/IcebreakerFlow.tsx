import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { whisperVariants } from "../../lib/motion";
import { Button } from "../ui/Button";
import { PebbleSlider } from "../ui/PebbleSlider";
import "../../styles/icebreaker.css";

const INTENSITY_OPTIONS = ["漫游 (Casual)", "常态 (Steady)", "极客 (Intense)"];

export function IcebreakerFlow() {
	const navigate = useNavigate();
	const [intensity, setIntensity] = useState(INTENSITY_OPTIONS[1]); // Default to Steady
	const [isGenerating, setIsGenerating] = useState(false);

	const handleGenerate = () => {
		setIsGenerating(true);
		// Simulate generation delay before going to canvas
		setTimeout(() => {
			navigate("/canvas");
		}, 1500);
	};

	return (
		<motion.main
			className="icebreaker-flow-root"
			exit={{ opacity: 0, filter: "blur(10px)", transition: { duration: 0.5 } }}
		>
			<div className="icebreaker-chat-container">
				<AnimatePresence mode="wait">
					<motion.div
						className="icebreaker-agent-bubble"
						initial={{ opacity: 0, y: 10 }}
						animate={{ opacity: 1, y: 0 }}
						transition={{ duration: 1, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
					>
						<motion.div
							className="whisper-badge"
							style={{ marginBottom: "var(--space-md)" }}
							variants={whisperVariants}
							initial="initial"
							animate="animate"
						>
							<span className="whisper-dot planner" />
							Planner Agent
						</motion.div>

						<h2 className="icebreaker-agent-text">
							欢迎来到你的专属空间。在为你编织知识星图之前，
							<br />
							<span style={{ color: "var(--color-text-secondary)" }}>
								你希望这次的学习节奏是怎样的？
							</span>
						</h2>
					</motion.div>

					<motion.div
						className="icebreaker-user-bubble"
						initial={{ opacity: 0, y: 10 }}
						animate={{ opacity: 1, y: 0 }}
						transition={{ duration: 0.8, delay: 1, ease: [0.16, 1, 0.3, 1] }}
					>
						<PebbleSlider
							options={INTENSITY_OPTIONS}
							value={intensity}
							onChange={setIntensity}
						/>
					</motion.div>

					<motion.div
						className="icebreaker-action-row"
						initial={{ opacity: 0 }}
						animate={{ opacity: 1 }}
						transition={{ duration: 0.8, delay: 1.5 }}
					>
						<Button
							onClick={handleGenerate}
							loading={isGenerating}
							icon={!isGenerating ? <ArrowRight size={18} /> : undefined}
						>
							生成学习星图
						</Button>
					</motion.div>
				</AnimatePresence>
			</div>
		</motion.main>
	);
}
