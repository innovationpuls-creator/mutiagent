import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { fetchProfileDashboard } from "../../api/profile";
import { useAiWidget } from "../../contexts/AiWidgetContext";
import { useAuth } from "../../contexts/AuthContext";
import { motionTokens } from "../../styles/motion-tokens";
import type { ProfileDashboardData } from "../../types/profile";
import { ProfileCard } from "./ProfileCard";
import { ProfileDetailOverlay } from "./ProfileDetailOverlay";
import { RecommendationCard } from "./RecommendationCard";
import { TodayLearningCard } from "./TodayLearningCard";
import { TodayLearningDetailOverlay } from "./TodayLearningDetailOverlay";
import "./SproutHero.css";

/**
 * 获取当前时段的中文问候语
 */
function getGreeting(): string {
	const hour = new Date().getHours();
	if (hour < 6) return "夜深了";
	if (hour < 12) return "早上好";
	if (hour < 14) return "中午好";
	if (hour < 18) return "下午好";
	return "晚上好";
}

/**
 * 获取当前星期的中文名
 */
function getWeekday(): string {
	const days = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
	return days[new Date().getDay()];
}

/**
 * SproutHero — 萌芽页面的 Hero 仪表板
 *
 * 复刻 Headspace 的版式和信息层级：
 * 1. 问候区 — 个性化 whisper + 大标题
 * 2. 辅助信息条 — 完成度 · 专业 · 阶段
 * 3. 双卡区 — 画像主卡 + 今日学习副卡
 * 4. 底部推荐行 — 3 列柔色小卡
 */
export function SproutHero() {
	const auth = useAuth();
	const navigate = useNavigate();
	const { setWidgetState } = useAiWidget();
	const [params, setParams] = useSearchParams();
	const reduceMotion = useReducedMotion();
	const [data, setData] = useState<ProfileDashboardData | null>(null);
	const [retry, setRetry] = useState(0);
	const [error, setError] = useState<string | null>(null);
	const [isOverlayOpen, setIsOverlayOpen] = useState(false);
	const [isTodayOverlayOpen, setIsTodayOverlayOpen] = useState(false);

	const username = auth.user?.username ?? "同学";

	useEffect(() => {
		if (!auth.token) {
			setError("请先登录后查看画像数据。");
			return;
		}

		const token = auth.token;
		void retry;
		let alive = true;
		const loadDashboard = () => {
			fetchProfileDashboard(token)
				.then((dashboard) => {
					if (!alive) return;
					setData(dashboard);
					setError(null);
				})
				.catch((err) => {
					if (!alive) return;
					setError(err instanceof Error ? err.message : "画像数据加载失败");
				});
		};

		loadDashboard();
		window.addEventListener("mutiagent-profile-updated", loadDashboard);

		return () => {
			alive = false;
			window.removeEventListener("mutiagent-profile-updated", loadDashboard);
		};
	}, [auth.token, retry]);

	useEffect(() => {
		if (params.get("panel") === "profile" && data) setIsOverlayOpen(true);
	}, [params, data]);

	if (error) {
		return (
			<section className="sprout-hero">
				<div className="hero-greeting-zone">
					<p role="alert">{error}</p>
					<button type="button" onClick={() => setRetry((n) => n + 1)}>
						重新加载
					</button>
				</div>
			</section>
		);
	}

	/* 加载态：skeleton 呼吸 */
	if (!data) {
		return (
			<section className="sprout-hero">
				<div className="hero-greeting-zone">
					<motion.div
						style={{
							width: 200,
							height: 20,
							borderRadius: "var(--radius-full)",
							background: "var(--color-surface)",
						}}
						animate={reduceMotion ? undefined : { opacity: [0.56, 0.86, 0.56] }}
						transition={{ duration: 2.1, repeat: Infinity, ease: "easeInOut" }}
					/>
				</div>
			</section>
		);
	}

	const currentLearningCourse = data.todayLearning.currentLearningCourse;
	const canStartCurrentLearning = Boolean(
		currentLearningCourse &&
			currentLearningCourse.progress_state !== "completed",
	);

	return (
		<section className="sprout-hero">
			{/* ── 问候区 ── */}
			<div className="hero-greeting-zone">
				<motion.p
					className="hero-whisper"
					initial={reduceMotion ? false : { opacity: 0 }}
					animate={reduceMotion ? undefined : { opacity: 1 }}
					transition={motionTokens.editorial}
				>
					{getWeekday()} · {getGreeting()}，{username}
				</motion.p>

				<motion.h1
					className="hero-title"
					initial={reduceMotion ? false : { opacity: 0, y: 12 }}
					animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
					transition={{ ...motionTokens.editorial, delay: 0.1 }}
				>
					{canStartCurrentLearning
						? "继续今天的学习"
						: data.hasCompleteProfile
							? "准备好，迈出下一步"
							: "从了解自己开始"}
				</motion.h1>

				{/* 辅助信息条 — 对应 Headspace 的 streak / sunrise */}
				<motion.div
					className="hero-meta-strip"
					initial={reduceMotion ? false : { opacity: 0 }}
					animate={reduceMotion ? undefined : { opacity: 1 }}
					transition={{ ...motionTokens.editorial, delay: 0.15 }}
				>
					<span className="hero-meta-highlight">
						<span className="hero-whisper-dot" aria-hidden="true" />
						画像完成度 {data.profileCompleteness}%
					</span>
					<span className="hero-meta-separator" aria-hidden="true" />
					<span>{data.profile.major}</span>
					<span className="hero-meta-separator" aria-hidden="true" />
					<span>{data.profile.currentGrade}</span>
				</motion.div>
			</div>

			{(!data.hasCompleteProfile || !canStartCurrentLearning) && (
				<div className="hero-primary-actions">
					{!data.hasCompleteProfile && (
						<button
							className="hero-primary-action"
							type="button"
							onClick={() => setWidgetState("EXPANDED")}
						>
							完善学习画像
						</button>
					)}
					{!canStartCurrentLearning && data.hasCompleteProfile && (
						<button
							className="hero-primary-action"
							type="button"
							onClick={() => navigate("/branch")}
						>
							查看学习路径
						</button>
					)}
					<button type="button" onClick={() => setIsOverlayOpen(true)}>
						查看学习画像
					</button>
				</div>
			)}
			{/* ── 双卡区 ── */}
			<div className="hero-cards-row">
				<ProfileCard
					profile={data.profile}
					completeness={data.profileCompleteness}
					summaryText={data.profileSummaryText}
					onClick={() => setIsOverlayOpen(true)}
				/>
				<TodayLearningCard
					data={data.todayLearning}
					onClick={
						currentLearningCourse
							? () => setIsTodayOverlayOpen(true)
							: undefined
					}
					onStartLearning={
						canStartCurrentLearning
							? () =>
									navigate(
										`/leaf/${encodeURIComponent(currentLearningCourse?.course_node_id ?? "")}`,
									)
							: undefined
					}
				/>
			</div>

			{data.hasCompleteProfile && canStartCurrentLearning && (
				<div className="hero-primary-actions">
					<button type="button" onClick={() => setIsOverlayOpen(true)}>
						查看学习画像
					</button>
				</div>
			)}
			{/* ── 底部推荐行 ── */}
			<div className="hero-recs-row">
				{data.recommendations.map((rec, i) => (
					<RecommendationCard key={rec.id} data={rec} index={i} />
				))}
			</div>

			<AnimatePresence>
				{isOverlayOpen && (
					<ProfileDetailOverlay
						isOpen={isOverlayOpen}
						onClose={() => {
							setIsOverlayOpen(false);
							if (params.has("panel")) {
								const next = new URLSearchParams(params);
								next.delete("panel");
								setParams(next, { replace: true });
							}
						}}
						profile={data.profile}
					/>
				)}
				{isTodayOverlayOpen && (
					<TodayLearningDetailOverlay
						isOpen={isTodayOverlayOpen}
						onClose={() => setIsTodayOverlayOpen(false)}
						data={data.todayLearning}
					/>
				)}
			</AnimatePresence>
		</section>
	);
}
