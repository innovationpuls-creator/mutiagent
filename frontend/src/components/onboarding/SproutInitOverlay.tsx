import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useAiWidget } from "../../context/AiWidgetContext";
import { DURATION_INSTANT, motionTokens } from "../../styles/motion-tokens";

interface Props {
	onComplete?: () => void;
}

export function SproutInitOverlay({ onComplete }: Props) {
	const [phase, setPhase] = useState<number>(0);
	const [isFinishing, setIsFinishing] = useState(false);
	const { widgetState, setWidgetState } = useAiWidget();
	const reduceMotion = useReducedMotion();

	useEffect(() => {
		if (reduceMotion) {
			setPhase(10);
			setWidgetState("CENTER_INPUT");
			return undefined;
		}

		// Compressed timeline pacing for a snappier intro (Total ~7.5s)
		const schedule = [
			{ delay: 400, phase: 1 }, // Blur in
			{ delay: 1000, phase: 2 }, // "你好" in
			{ delay: 2200, phase: 3 }, // "你好" out (Stay 1.2s)
			{ delay: 2600, phase: 4 }, // "Hello" in (Interval 0.4s)
			{ delay: 3800, phase: 5 }, // "Hello" out (Stay 1.2s)
			{ delay: 4200, phase: 6 }, // "欢迎来到 one-tree" in (Interval 0.4s)
			{ delay: 5700, phase: 7 }, // "欢迎来到 one-tree" out (Stay 1.5s)
			{ delay: 6300, phase: 8 }, // 正文 in (Interval 0.6s)
			{ delay: 6900, phase: 9 }, // 附注 in
			{ delay: 7500, phase: 10 }, // Chat panel in
		];

		const timeouts = schedule.map(({ delay, phase: p }) =>
			setTimeout(() => {
				setPhase(p);
				if (p === 10) {
					setWidgetState("CENTER_INPUT");
				}
			}, delay),
		);

		return () => timeouts.forEach(clearTimeout);
	}, [reduceMotion, setWidgetState]);

	useEffect(() => {
		if (phase >= 10 && widgetState === "WIDGET" && !isFinishing) {
			setIsFinishing(true);

			const sequence = async () => {
				// 等待小人回到右下角 (动画约 1.2s)
				await new Promise((resolve) => setTimeout(resolve, 1200));

				// 最后淡出背景模糊和文字
				onComplete?.();
			};

			sequence();
		}
	}, [phase, widgetState, onComplete, isFinishing]);

	return (
		<motion.div
			data-sprout-init-overlay="true"
			initial={reduceMotion ? false : { opacity: 0 }}
			animate={{ opacity: 1 }}
			exit={{ opacity: 0 }}
			transition={
				reduceMotion
					? { duration: DURATION_INSTANT }
					: { delay: 0.4, ...motionTokens.route }
			}
			style={{
				position: "fixed",
				inset: 0,
				zIndex: 9999,
				backgroundColor: "oklch(97% 0.02 75 / 0.36)",
				backdropFilter: "blur(56px)",
				WebkitBackdropFilter: "blur(56px)",
				pointerEvents: "none",
				display: "flex",
				flexDirection: "column",
				alignItems: "center",
				justifyContent: "center",
			}}
		>
			<div
				style={{
					display: "flex",
					flexDirection: "column",
					alignItems: "center",
					textAlign: "center",
					marginTop: "-10vh",
				}}
			>
				<AnimatePresence mode="wait">
					{phase >= 2 && phase < 3 && (
						<motion.h1
							key="t1"
							initial={reduceMotion ? false : { opacity: 0, y: 8 }}
							animate={{ opacity: 1, y: 0 }}
							exit={{
								opacity: 0,
								y: -8,
								transition: reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial,
							}}
							transition={
								reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial
							}
							style={{
								fontFamily: "var(--font-heading)",
								fontSize: "38px",
								fontWeight: 400,
								color: "oklch(28% 0.01 60)",
								letterSpacing: "0.02em",
								margin: 0,
							}}
						>
							你好
						</motion.h1>
					)}
					{phase >= 4 && phase < 5 && (
						<motion.h1
							key="t2"
							initial={reduceMotion ? false : { opacity: 0, y: 8 }}
							animate={{ opacity: 1, y: 0 }}
							exit={{
								opacity: 0,
								y: -8,
								transition: reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial,
							}}
							transition={
								reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial
							}
							style={{
								fontFamily: "var(--font-heading)",
								fontSize: "38px",
								fontWeight: 400,
								color: "oklch(28% 0.01 60)",
								letterSpacing: "0.02em",
								margin: 0,
							}}
						>
							Hello
						</motion.h1>
					)}
					{phase >= 6 && phase < 7 && (
						<motion.h1
							key="t3"
							initial={reduceMotion ? false : { opacity: 0, y: 8 }}
							animate={{ opacity: 1, y: 0 }}
							exit={{
								opacity: 0,
								y: -8,
								transition: reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial,
							}}
							transition={
								reduceMotion
									? { duration: DURATION_INSTANT }
									: motionTokens.editorial
							}
							style={{
								fontFamily: "var(--font-heading)",
								fontSize: "38px",
								fontWeight: 400,
								color: "oklch(28% 0.01 60)",
								letterSpacing: "0.02em",
								margin: 0,
							}}
						>
							欢迎来到{" "}
							<span
								style={{
									fontFamily: "var(--font-brand)",
									fontWeight: 500,
									color: "oklch(70% 0.12 45)",
									marginLeft: "8px",
									fontSize: "42px",
									transform: "translateY(2px)",
									display: "inline-block",
								}}
							>
								one-tree
							</span>
						</motion.h1>
					)}
				</AnimatePresence>

				{phase >= 8 && (
					<motion.div
						layout // smoothly transition height changes
						initial={reduceMotion ? false : { opacity: 0, y: 10 }}
						animate={{ opacity: 1, y: 0 }}
						transition={
							reduceMotion
								? { duration: DURATION_INSTANT }
								: motionTokens.editorial
						}
						style={{
							display: "flex",
							flexDirection: "column",
							alignItems: "center",
							gap: "var(--space-20)",
						}}
					>
						<motion.h2
							layout
							style={{
								fontFamily: "var(--font-heading)",
								fontSize: "38px",
								color: "oklch(28% 0.01 60)",
								margin: 0,
								fontWeight: 400,
								letterSpacing: "0.02em",
								lineHeight: 1.38,
							}}
						>
							在开启旅程之前，想先听听你的声音。
						</motion.h2>
						<AnimatePresence>
							{phase >= 9 && (
								<motion.p
									layout
									initial={reduceMotion ? false : { opacity: 0, y: 5 }}
									animate={{ opacity: 1, y: 0 }}
									transition={
										reduceMotion
											? { duration: DURATION_INSTANT }
											: motionTokens.editorial
									}
									style={{
										fontFamily: "var(--font-body)",
										fontSize: "18px",
										color: "oklch(55% 0.02 60)",
										margin: 0,
										letterSpacing: "0.04em",
									}}
								>
									关于你的专业、现在的状态，或是当下的困惑……随便聊聊。
								</motion.p>
							)}
						</AnimatePresence>
					</motion.div>
				)}
			</div>
		</motion.div>
	);
}
