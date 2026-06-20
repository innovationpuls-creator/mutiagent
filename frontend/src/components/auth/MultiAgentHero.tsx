import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

import { AgentSandtable } from "./AgentSandtable";

const STAGES = [
	{ title: "意图解析", subtitle: "Planner Agent 倾听你的原始需求", icon: "〇" },
	{ title: "知识寻源", subtitle: "Researcher Agent 编织信息网络", icon: "✦" },
	{ title: "路径规划", subtitle: "Path Agent 构建有机学习序列", icon: "⎔" },
];

export function MultiAgentHero() {
	const reduceMotion = useReducedMotion();
	const [stageIndex, setStageIndex] = useState(0);

	return (
		<aside className="auth-art-canvas">
			{/* 巨大的呼吸光晕 */}
			{reduceMotion ? (
				<div className="ambient-sun" aria-hidden="true" />
			) : (
				<motion.div
					className="ambient-sun"
					aria-hidden="true"
					animate={{ scale: [0.96, 1.04], opacity: [0.66, 0.86] }}
					transition={{
						duration: 6,
						repeat: Infinity,
						ease: "easeInOut",
						repeatType: "reverse",
					}}
				/>
			)}

			{/* 几何化符号点缀 (Removed * symbol as requested) */}

			<div
				className="canvas-hero"
				style={{
					display: "flex",
					flexDirection: "column",
					justifyContent: "flex-start",
					width: "100%",
					maxWidth: "none",
					flex: 1,
					minHeight: 0,
				}}
			>
				{/* Top Area: Prelude and Branding */}
				<div
					style={{
						display: "flex",
						flexDirection: "column",
						justifyContent: "flex-start",
						alignItems: "flex-start",
						width: "100%",
						maxWidth: "none",
					}}
				>
					{/* Brand Header — Logo + 品牌名 + 系统定义 */}
					<motion.div
						className="hero-brand-header"
						initial={reduceMotion ? false : { opacity: 0, filter: "blur(8px)" }}
						animate={
							reduceMotion ? undefined : { opacity: 1, filter: "blur(0px)" }
						}
						transition={
							reduceMotion
								? undefined
								: { duration: 1.5, delay: 2.5, ease: "easeOut" }
						}
						style={{
							display: "flex",
							alignItems: "center",
							gap: "var(--space-12)",
							marginBottom: "var(--hero-brand-gap, var(--space-24))",
						}}
					>
						<div className="logo-pebble">
							<img src="/logo.png" alt="one-tree logo" className="hero-logo" />
						</div>
						<div
							style={{
								display: "flex",
								flexDirection: "column",
								gap: "var(--space-4)",
							}}
						>
							<div className="hero-brand-text" style={{ lineHeight: 1 }}>
								one-tree
							</div>
							<div
								className="hero-shoulder"
								style={{
									fontFamily: "var(--font-body)",
									fontSize: "var(--text-body-sm)",
									fontWeight: "var(--font-weight-regular)",
									color: "oklch(55% 0.06 55)",
									letterSpacing: "0.02em",
								}}
							>
								动态更新的多Agent协同学习系统
							</div>
						</div>
					</motion.div>

					{/* Prelude — 主标题 */}
					<motion.h2
						className="hero-prelude"
						initial={reduceMotion ? false : { opacity: 0, y: 20 }}
						animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
						transition={
							reduceMotion
								? undefined
								: { duration: 1.2, delay: 0.3, ease: "easeOut" }
						}
						style={{ fontFamily: "var(--font-heading)", margin: 0 }}
					>
						从一句轻声的提问，到一张
						<motion.span
							initial={
								reduceMotion ? false : { opacity: 0, filter: "blur(8px)" }
							}
							animate={
								reduceMotion ? undefined : { opacity: 1, filter: "blur(0px)" }
							}
							transition={
								reduceMotion
									? undefined
									: { duration: 1.5, delay: 0.9, ease: "easeOut" }
							}
							style={{ color: "oklch(70% 0.08 60)" }}
						>
							自然舒展
						</motion.span>
						的学习地图。
					</motion.h2>
				</div>

				{/* Bottom Area: Dynamic Choreography for Multi-Agent Features */}
				<motion.div
					style={{
						paddingTop: "var(--hero-sandtable-gap, var(--space-24))",
						flex: 1,
						minHeight: 0,
						display: "flex",
						flexDirection: "column",
						gap: "var(--hero-stage-gap, var(--space-24))",
					}}
					initial={reduceMotion ? false : { opacity: 0 }}
					animate={reduceMotion ? undefined : { opacity: 1 }}
					transition={reduceMotion ? undefined : { duration: 1, delay: 2.6 }}
				>
					<div
						style={{
							minHeight: "var(--hero-stage-header-height, var(--space-64))",
							flexShrink: 0,
							display: "flex",
							alignItems: "center",
						}}
					>
						<AnimatePresence mode="wait">
							<motion.div
								key={stageIndex}
								initial={
									reduceMotion
										? false
										: { opacity: 0, y: 15, filter: "blur(4px)" }
								}
								animate={
									reduceMotion
										? undefined
										: { opacity: 1, y: 0, filter: "blur(0px)" }
								}
								exit={
									reduceMotion
										? undefined
										: { opacity: 0, y: -15, filter: "blur(4px)" }
								}
								transition={
									reduceMotion ? undefined : { duration: 0.8, ease: "easeOut" }
								}
								style={{
									display: "flex",
									alignItems: "center",
									gap: "var(--space-16)",
								}}
							>
								<div
									style={{
										fontFamily: "var(--font-mono)",
										fontSize: "var(--text-h2)",
										color: "var(--color-intent-active)",
										opacity: 0.8,
									}}
								>
									{STAGES[stageIndex].icon}
								</div>
								<div>
									<div
										style={{
											fontFamily: "var(--font-heading)",
											fontSize: "var(--text-h3)",
											fontWeight: "var(--font-weight-medium)",
											color: "var(--color-text-primary)",
											letterSpacing: "1px",
											marginBottom: "var(--space-4)",
										}}
									>
										{STAGES[stageIndex].title}
									</div>
									<div
										style={{
											fontFamily: "var(--font-body)",
											fontSize: "var(--text-body-sm)",
											color: "var(--color-text-whisper)",
											letterSpacing: "0.5px",
										}}
									>
										{STAGES[stageIndex].subtitle}
									</div>
								</div>
							</motion.div>
						</AnimatePresence>
					</div>

					<AgentSandtable setStageIndex={setStageIndex} />
				</motion.div>
			</div>
		</aside>
	);
}
