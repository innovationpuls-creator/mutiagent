import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { motionTokens } from "../../styles/motion-tokens";
import type {
	CanopyOverview,
	ChapterWeaknessData,
	ForestAttempt,
} from "../../types/forest";

interface ForestQuizOverlayProps {
	isOpen: boolean;
	onClose(): void;
	attempt: ForestAttempt;
	canopyOverview: CanopyOverview;
	nextUnlockedChapterId: string | null;
	nextCourseId: string | null;
	courseNodeId: string;
	weaknesses: ChapterWeaknessData[];
	reduceMotion?: boolean;
}

function GrowthTreeSVG({ stage }: { stage: number }) {
	// Color tokens using OKLCH CSS variables
	const leafColor = "var(--color-intent-success, oklch(72% 0.09 145))";
	const trunkColor = "var(--color-text-primary, oklch(35% 0.005 80))";
	const fruitColor = "oklch(82% 0.08 60)"; // Peach glow accent

	return (
		<svg
			width="180"
			height="180"
			viewBox="0 0 200 200"
			className="forest-tree-svg"
			aria-label={`成长树阶段: ${stage}`}
		>
			<defs>
				<radialGradient id="glow" cx="50%" cy="50%" r="50%">
					<stop offset="0%" stopColor="oklch(75% 0.09 135 / 0.15)" />
					<stop offset="100%" stopColor="oklch(75% 0.09 135 / 0)" />
				</radialGradient>
			</defs>

			{/* Background glow sphere */}
			<circle cx="100" cy="120" r="70" fill="url(#glow)" />

			{/* Dirt Mound */}
			<path
				d="M60,180 C80,175 120,175 140,180"
				stroke={trunkColor}
				strokeWidth="3"
				strokeLinecap="round"
				fill="none"
			/>

			{/* Stage 1: Seedling Sprout */}
			{stage >= 1 && (
				<path
					d="M100,180 Q100,150 100,135"
					stroke={trunkColor}
					strokeWidth={stage === 1 ? "3" : "4"}
					strokeLinecap="round"
					fill="none"
				/>
			)}
			{stage === 1 && (
				<>
					<path
						d="M100,135 C90,128 82,130 85,138 C90,138 96,136 100,135"
						fill={leafColor}
					/>
					<path
						d="M100,135 C110,128 118,130 115,138 C110,138 104,136 100,135"
						fill={leafColor}
					/>
				</>
			)}

			{/* Stage 2: Stem with minor leaves */}
			{stage >= 2 && (
				<>
					<path
						d="M100,135 Q97,120 100,105"
						stroke={trunkColor}
						strokeWidth={stage === 2 ? "3.5" : "4.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{stage === 2 && (
						<>
							{/* Lower leaves */}
							<path
								d="M99,145 C90,140 85,142 88,148 C92,148 96,146 99,145"
								fill={leafColor}
							/>
							<path
								d="M101,138 C110,133 115,135 112,141 C108,141 104,139 101,138"
								fill={leafColor}
							/>
							{/* Top sprout */}
							<path
								d="M100,105 C92,98 86,102 90,108 C94,108 98,106 100,105"
								fill={leafColor}
							/>
							<path
								d="M100,105 C108,98 114,102 110,108 C106,108 102,106 100,105"
								fill={leafColor}
							/>
						</>
					)}
				</>
			)}

			{/* Stage 3: Small sapling with branch splits */}
			{stage >= 3 && (
				<>
					<path
						d="M100,105 Q102,90 95,80"
						stroke={trunkColor}
						strokeWidth={stage === 3 ? "4" : "5"}
						strokeLinecap="round"
						fill="none"
					/>
					{/* Left Branch */}
					<path
						d="M99,120 Q85,110 80,102"
						stroke={trunkColor}
						strokeWidth={stage === 3 ? "3" : "3.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{/* Right Branch */}
					<path
						d="M101,112 Q115,102 122,96"
						stroke={trunkColor}
						strokeWidth={stage === 3 ? "3" : "3.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{stage === 3 && (
						<>
							{/* Left Branch Leaves */}
							<path
								d="M80,102 C72,96 68,100 72,106 C76,106 78,104 80,102"
								fill={leafColor}
							/>
							<path
								d="M80,102 C85,94 90,96 87,102 C84,102 82,102 80,102"
								fill={leafColor}
							/>
							{/* Right Branch Leaves */}
							<path
								d="M122,96 C130,90 134,94 130,100 C126,100 124,98 122,96"
								fill={leafColor}
							/>
							{/* Top Leaves */}
							<path
								d="M95,80 C87,73 83,77 87,83 C91,83 93,81 95,80"
								fill={leafColor}
							/>
							<path
								d="M95,80 C103,73 107,77 103,83 C99,83 97,81 95,80"
								fill={leafColor}
							/>
						</>
					)}
				</>
			)}

			{/* Stage 4: Sturdier branched tree */}
			{stage >= 4 && (
				<>
					<path
						d="M95,80 Q98,65 92,55"
						stroke={trunkColor}
						strokeWidth={stage === 4 ? "4.5" : "5.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{/* Secondary Left Branch */}
					<path
						d="M96,95 Q80,88 74,80"
						stroke={trunkColor}
						strokeWidth={stage === 4 ? "3" : "3.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{/* Secondary Right Branch */}
					<path
						d="M98,88 Q115,78 120,68"
						stroke={trunkColor}
						strokeWidth={stage === 4 ? "3" : "3.5"}
						strokeLinecap="round"
						fill="none"
					/>
					{stage === 4 && (
						<>
							{/* Foliage blocks */}
							<circle cx="80" cy="102" r="10" fill={leafColor} opacity="0.9" />
							<circle cx="122" cy="96" r="11" fill={leafColor} opacity="0.9" />
							<circle cx="74" cy="80" r="10" fill={leafColor} opacity="0.9" />
							<circle cx="120" cy="68" r="11" fill={leafColor} opacity="0.9" />
							<circle cx="92" cy="55" r="12" fill={leafColor} opacity="0.9" />
						</>
					)}
				</>
			)}

			{/* Stage 5: Mature tree */}
			{stage >= 5 && (
				<>
					<path
						d="M92,55 Q94,42 90,32"
						stroke={trunkColor}
						strokeWidth={stage === 5 ? "5" : "6"}
						strokeLinecap="round"
						fill="none"
					/>
					{stage === 5 && (
						<>
							{/* Thick foliage clusters */}
							<circle cx="80" cy="102" r="14" fill={leafColor} opacity="0.85" />
							<circle cx="122" cy="96" r="15" fill={leafColor} opacity="0.85" />
							<circle cx="74" cy="80" r="14" fill={leafColor} opacity="0.85" />
							<circle cx="120" cy="68" r="15" fill={leafColor} opacity="0.85" />
							<circle cx="92" cy="55" r="18" fill={leafColor} opacity="0.85" />
							<circle cx="90" cy="32" r="16" fill={leafColor} opacity="0.9" />
							<circle cx="104" cy="45" r="14" fill={leafColor} opacity="0.8" />
							<circle cx="80" cy="55" r="13" fill={leafColor} opacity="0.8" />
						</>
					)}
				</>
			)}

			{/* Stage 6: Lush 成森/成林 canopy with peach fruits */}
			{stage >= 6 && (
				<>
					<circle cx="80" cy="102" r="16" fill={leafColor} opacity="0.85" />
					<circle cx="122" cy="96" r="18" fill={leafColor} opacity="0.85" />
					<circle cx="71" cy="78" r="16" fill={leafColor} opacity="0.85" />
					<circle cx="122" cy="66" r="18" fill={leafColor} opacity="0.85" />
					<circle cx="92" cy="50" r="22" fill={leafColor} opacity="0.85" />
					<circle cx="90" cy="28" r="18" fill={leafColor} opacity="0.9" />
					<circle cx="106" cy="40" r="16" fill={leafColor} opacity="0.8" />
					<circle cx="76" cy="48" r="15" fill={leafColor} opacity="0.8" />
					<circle cx="60" cy="65" r="12" fill={leafColor} opacity="0.75" />
					<circle cx="138" cy="80" r="12" fill={leafColor} opacity="0.75" />

					{/* Little glowing fruits/blossoms */}
					<circle cx="75" cy="75" r="3" fill={fruitColor} />
					<circle cx="115" cy="60" r="3.5" fill={fruitColor} />
					<circle cx="95" cy="38" r="3" fill={fruitColor} />
					<circle cx="90" cy="70" r="4" fill={fruitColor} />
					<circle cx="125" cy="88" r="3" fill={fruitColor} />
				</>
			)}
		</svg>
	);
}

function getGrowthStageName(stage: number): string {
	switch (stage) {
		case 1:
			return "萌芽期 — 树苗初现";
		case 2:
			return "幼株期 — 展开绿叶";
		case 3:
			return "繁枝期 — 分叉成长";
		case 4:
			return "成木期 — 结构稳定";
		case 5:
			return "叶茂期 — 浓荫渐成";
		case 6:
			return "成林期 — 硕果累累";
		default:
			return "雨林生机";
	}
}

export function ForestQuizOverlay({
	isOpen,
	onClose,
	attempt,
	canopyOverview,
	nextUnlockedChapterId,
	nextCourseId,
	courseNodeId,
	weaknesses,
	reduceMotion = false,
}: ForestQuizOverlayProps) {
	const navigate = useNavigate();

	if (!isOpen) return null;

	const score = attempt.score;
	const passed = attempt.passed;
	const stage = canopyOverview.growth_tree_stage || 1;

	const handleGoCanopy = () => {
		onClose();
		navigate("/canopy");
	};

	const handleGoNext = () => {
		onClose();
		if (nextUnlockedChapterId) {
			navigate(`/leaf/${courseNodeId}?chapter_id=${nextUnlockedChapterId}`);
		} else if (nextCourseId) {
			navigate(`/leaf/${nextCourseId}`);
		}
	};

	return (
		<div className="forest-overlay-backdrop" role="dialog" aria-modal="true">
			<motion.div
				className="forest-overlay-panel"
				initial={
					reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 16 }
				}
				animate={reduceMotion ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }}
				exit={
					reduceMotion ? { opacity: 0 } : { opacity: 0, scale: 0.96, y: 16 }
				}
				transition={motionTokens.editorial}
			>
				<button
					type="button"
					className="forest-overlay-close-btn"
					onClick={onClose}
					aria-label="关闭"
				>
					✕
				</button>

				<header className="forest-overlay-header">
					<span className="whisper-badge">
						<span
							className={`whisper-dot ${passed ? "feedback" : "active"}`}
							style={{
								backgroundColor: passed
									? "var(--color-intent-success)"
									: "var(--color-intent-warning)",
							}}
						/>
						{passed ? "CONGRATULATIONS" : "KEEP WORKING"}
					</span>
					<h1 className="forest-overlay-score-title">
						<span className="score-num">{score}</span>
						<span className="score-unit">分</span>
					</h1>
					<p className="forest-overlay-status-desc">
						{passed
							? "恭喜通关！本次测验表现优异。"
							: "未达到通关分数，AI 已记录薄弱方向。"}
					</p>
				</header>

				<div className="forest-overlay-content-grid">
					{/* Left Column: Growth Tree Visualization */}
					<div className="forest-overlay-tree-section">
						<div className="tree-container">
							<GrowthTreeSVG stage={stage} />
						</div>
						<span className="growth-stage-badge">
							{getGrowthStageName(stage)}
						</span>
					</div>

					{/* Right Column: Canopy Metrics & Adaptive Notes */}
					<div className="forest-overlay-stats-section">
						<div className="forest-stats-summary-card">
							<h2>雨林成森进度</h2>
							<div className="stats-row">
								<div className="stat-item">
									<span className="stat-label">点亮课程</span>
									<span className="stat-value">
										{canopyOverview.completed_courses} /{" "}
										{canopyOverview.total_courses}
									</span>
								</div>
								<div className="stat-item">
									<span className="stat-label">通关章节</span>
									<span className="stat-value">
										{canopyOverview.completed_chapters} /{" "}
										{canopyOverview.total_chapters}
									</span>
								</div>
							</div>
							<div
								className="stats-row"
								style={{ marginTop: "var(--space-12)" }}
							>
								<div className="stat-item">
									<span className="stat-label">测验均分</span>
									<span className="stat-value">
										{Math.round(canopyOverview.avg_score)} 分
									</span>
								</div>
								<div className="stat-item">
									<span className="stat-label">专注时长</span>
									<span className="stat-value">
										{canopyOverview.total_focus_hours} 小时
									</span>
								</div>
							</div>
						</div>

						{/* Weaknesses Adaptive Section */}
						{weaknesses.length > 0 && (
							<div className="forest-weaknesses-card">
								<h3>// 薄弱方向收录</h3>
								<p>
									AI
									已根据你本次错题定位以下知识点，并将在后续教学资源中自动侧重：
								</p>
								<div className="weakness-tag-list">
									{weaknesses.map((w) => (
										<span
											key={`${w.knowledge_point_id}:${w.knowledge_point_name}:${w.severity}`}
											className="weakness-tag"
											style={{
												borderColor:
													w.severity >= 2
														? "var(--color-intent-warning)"
														: "var(--color-border)",
											}}
										>
											{w.knowledge_point_name || w.knowledge_point_id}
										</span>
									))}
								</div>
							</div>
						)}
					</div>
				</div>

				{/* Action CTAs */}
				<div className="forest-overlay-footer-actions">
					<button
						type="button"
						className="forest-btn-secondary"
						onClick={handleGoCanopy}
					>
						返回雨林
					</button>

					{(nextUnlockedChapterId || nextCourseId) && passed && (
						<button
							type="button"
							className="forest-btn-primary"
							onClick={handleGoNext}
						>
							解锁下一章 →
						</button>
					)}
				</div>
			</motion.div>
		</div>
	);
}
