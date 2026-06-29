import { motion, useReducedMotion } from "framer-motion";
import {
	BookOpen,
	Edit2,
	Loader2,
	Play,
	RefreshCw,
	Search,
	Trash2,
	Upload,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import {
	type AdminKnowledgeBaseApi,
	adminKnowledgeBaseApi as defaultKnowledgeBaseApi,
	type KnowledgeGapAdmin,
	type KnowledgeSource,
	type StructuredTextbookCreateRequest,
	type Textbook,
	type TextbookExtensionResource,
} from "../../api/knowledgeBase";
import { useAuth } from "../../contexts/AuthContext";
import { OutlineEditor } from "./OutlineEditor";
import "./admin.css";

interface AdminKnowledgeBasePageProps {
	knowledgeBaseApi?: AdminKnowledgeBaseApi;
}

type SectionSummary = {
	section_id: string;
	title: string;
};

const adminRoutes = [
	{ label: "账号管理", path: "/admin/accounts", hint: "用户账号管理" },
	{ label: "人培方案", path: "/admin/programs", hint: "上传与发布人培方案" },
	{ label: "数据管理", path: "/admin/data", hint: "学习数据与人培方案管理" },
	{
		label: "知识库",
		path: "/admin/knowledge-base",
		hint: "教材来源与未覆盖待办",
	},
];

const sourceStatusLabels = {
	status: {
		enabled: "启用",
		disabled: "停用",
	},
	download_status: {
		unverified: "未验证",
		verified: "已验证",
		failed: "失败",
	},
	parse_status: {
		unverified: "未验证",
		supported: "已支持",
		failed: "失败",
	},
	license_review_status: {
		unreviewed: "未审查",
		approved: "已通过",
		rejected: "已拒绝",
	},
	human_review_status: {
		unreviewed: "未审查",
		reviewed: "已复核",
	},
} satisfies {
	status: Record<KnowledgeSource["status"], string>;
	download_status: Record<KnowledgeSource["download_status"], string>;
	parse_status: Record<KnowledgeSource["parse_status"], string>;
	license_review_status: Record<
		KnowledgeSource["license_review_status"],
		string
	>;
	human_review_status: Record<KnowledgeSource["human_review_status"], string>;
};

const ingestionStatusLabels: Record<Textbook["ingestion_status"], string> = {
	not_started: "未开始",
	processing: "整理中",
	failed: "失败",
	ready_for_outline_review: "待校对大纲",
	completed: "已完成",
};

const outlineReviewStatusLabels: Record<
	Textbook["outline_review_status"],
	string
> = {
	unreviewed: "未校对",
	approved: "已通过",
};

const availabilityStatusLabels: Record<
	Textbook["student_availability_status"],
	string
> = {
	draft: "草稿",
	published: "已发布",
	unpublished: "已下架",
	archived: "已归档",
};

const gapStatusLabels: Record<KnowledgeGapAdmin["status"], string> = {
	open: "待处理",
	material_searching: "找素材中",
	material_found: "已找到素材",
	resolved: "已解决",
	closed: "已关闭",
};

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
	year: "numeric",
	month: "2-digit",
	day: "2-digit",
	hour: "2-digit",
	minute: "2-digit",
});

function formatDate(value: string | null | undefined) {
	if (!value) return "暂无";
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "暂无";
	return dateFormatter.format(date);
}

function missingAdmissionItems(source: KnowledgeSource) {
	const items: string[] = [];
	if (source.status !== "enabled") items.push("来源启用");
	if (source.download_status !== "verified") items.push("下载验证");
	if (source.parse_status !== "supported") items.push("解析支持");
	if (source.license_review_status !== "approved") items.push("许可通过");
	if (source.human_review_status !== "reviewed") items.push("人工复核");
	return items;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function outlineSections(textbook: Textbook): SectionSummary[] {
	const outline = textbook.outline;
	if (!isRecord(outline) || !Array.isArray(outline.sections)) return [];
	return outline.sections.flatMap((section) => {
		if (!isRecord(section)) return [];
		const sectionId = section.section_id;
		const title = section.title;
		if (typeof sectionId !== "string" || typeof title !== "string") return [];
		return [{ section_id: sectionId, title }];
	});
}

function extensionGapCount(
	textbook: Textbook,
	resources: TextbookExtensionResource[],
	openGaps: KnowledgeGapAdmin[],
) {
	if (openGaps.length > 0) return openGaps.length;
	const sections = outlineSections(textbook);
	if (sections.length === 0) return 0;
	const coveredSectionIds = new Set(
		resources
			.filter((resource) => resource.status === "published")
			.map((resource) => resource.section_id),
	);
	return sections.filter(
		(section) => !coveredSectionIds.has(section.section_id),
	).length;
}

function createUploadPayload(
	gap: KnowledgeGapAdmin,
): StructuredTextbookCreateRequest {
	const textbookId = `upload-${gap.gap_id}`;
	const title = `${gap.normalized_topic}补充教材`;
	const sourceId = gap.sources?.[0]?.source_id ?? "";
	return {
		textbook: {
			textbook_id: textbookId,
			source_id: sourceId,
			title,
			original_title: title,
			language: "zh",
			translated_language: "zh",
			description: `围绕${gap.normalized_topic}补齐未覆盖主题。`,
			tags: [gap.normalized_topic],
			download_url: "",
			file_asset_url: "",
			outline: {
				sections: [{ section_id: "1.1", title: gap.normalized_topic }],
			},
			ingestion_status: "completed",
			outline_review_status: "approved",
			student_availability_status: "draft",
			ingestion_error_message: "",
		},
		sections: [
			{
				section_content_id: `section-${textbookId}-1`,
				section_id: "1.1",
				parent_section_id: null,
				order_index: 1,
				title: gap.normalized_topic,
				original_title: gap.normalized_topic,
				content_zh: `${gap.normalized_topic}补充正文待管理员完善。`,
				content_char_count: 0,
			},
		],
	};
}

export function AdminKnowledgeBasePage({
	knowledgeBaseApi = defaultKnowledgeBaseApi,
}: AdminKnowledgeBasePageProps) {
	const { token, user } = useAuth();
	const reduceMotion = useReducedMotion();
	const [sources, setSources] = useState<KnowledgeSource[]>([]);
	const [textbooks, setTextbooks] = useState<Textbook[]>([]);
	const [gaps, setGaps] = useState<KnowledgeGapAdmin[]>([]);
	const [extensionResources, setExtensionResources] = useState<
		TextbookExtensionResource[]
	>([]);
	const [selectedTextbookId, setSelectedTextbookId] = useState("");
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [isEditingOutline, setIsEditingOutline] = useState(false);
	const [isGeneratingContent, setIsGeneratingContent] = useState(false);
	const [generationProgress, setGenerationProgress] = useState<{
		progress_percentage: number;
		status: string;
		current_section_title: string;
	} | null>(null);

	const selectedTextbook =
		textbooks.find((textbook) => textbook.textbook_id === selectedTextbookId) ??
		textbooks[0] ??
		null;
	const visibleGaps = useMemo(
		() => gaps.filter((gap) => gap.status !== "closed"),
		[gaps],
	);

	const loadKnowledgeBase = useCallback(async () => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			const [nextSources, nextTextbooks, nextGaps] = await Promise.all([
				knowledgeBaseApi.listSources(token),
				knowledgeBaseApi.listTextbooks(token),
				knowledgeBaseApi.listGaps(token),
			]);
			setSources(nextSources);
			setTextbooks(nextTextbooks);
			setGaps(nextGaps);
			setSelectedTextbookId(
				(current) => current || nextTextbooks[0]?.textbook_id || "",
			);
		} catch (loadError) {
			setError(
				loadError instanceof Error ? loadError.message : "知识库加载失败",
			);
		} finally {
			setBusy(false);
		}
	}, [knowledgeBaseApi, token]);

	// Polling AIGC Generation Progress
	useEffect(() => {
		if (
			!isEditingOutline ||
			!selectedTextbook ||
			!token ||
			!isGeneratingContent
		)
			return;
		let intervalId: ReturnType<typeof setInterval> | null = null;

		const checkProgress = async () => {
			try {
				const progress = await knowledgeBaseApi.getGenerationProgress(
					token,
					selectedTextbook.textbook_id,
				);
				setGenerationProgress(progress);
				if (progress.status === "completed" || progress.status === "failed") {
					setIsGeneratingContent(false);
					if (intervalId) clearInterval(intervalId);
					void loadKnowledgeBase();
				}
			} catch (err) {
				console.error("Failed to fetch generation progress:", err);
			}
		};

		void checkProgress();
		intervalId = setInterval(checkProgress, 2000);

		return () => {
			if (intervalId) clearInterval(intervalId);
		};
	}, [
		isEditingOutline,
		selectedTextbook,
		isGeneratingContent,
		token,
		knowledgeBaseApi,
		loadKnowledgeBase,
	]);

	const handleSaveOutline = async (outlineData: unknown) => {
		if (!token || !selectedTextbook) return;
		setBusy(true);
		setError(null);
		try {
			const updated = await knowledgeBaseApi.updateOutline(
				token,
				selectedTextbook.textbook_id,
				outlineData,
			);
			replaceTextbook(updated);
		} catch (err) {
			setError(err instanceof Error ? err.message : "更新大纲失败");
			throw err;
		} finally {
			setBusy(false);
		}
	};

	const handleGenerateOutline = async (prompt: string, tags: string[]) => {
		if (!token) throw new Error("未登录");
		setBusy(true);
		setError(null);
		try {
			const nextTextbook = await knowledgeBaseApi.generateOutline(
				token,
				prompt,
				tags,
			);
			setTextbooks((current) => {
				const filtered = current.filter(
					(t) => t.textbook_id !== nextTextbook.textbook_id,
				);
				return [...filtered, nextTextbook];
			});
			setSelectedTextbookId(nextTextbook.textbook_id);
			return nextTextbook;
		} catch (err) {
			setError(err instanceof Error ? err.message : "AI大纲协同生成失败");
			throw err;
		} finally {
			setBusy(false);
		}
	};

	const handleTriggerAigcContent = async () => {
		if (!token || !selectedTextbook) return;
		setBusy(true);
		setError(null);
		try {
			await knowledgeBaseApi.generateContent(
				token,
				selectedTextbook.textbook_id,
			);
			setIsGeneratingContent(true);
		} catch (err) {
			setError(err instanceof Error ? err.message : "一键正文生成任务启动失败");
		} finally {
			setBusy(false);
		}
	};

	useEffect(() => {
		void loadKnowledgeBase();
	}, [loadKnowledgeBase]);

	useEffect(() => {
		if (!token || !selectedTextbook) {
			setExtensionResources([]);
			return;
		}
		let cancelled = false;
		knowledgeBaseApi
			.listExtensionResources(token, selectedTextbook.textbook_id)
			.then((resources) => {
				if (!cancelled) setExtensionResources(resources);
			})
			.catch((resourceError) => {
				if (!cancelled) {
					setError(
						resourceError instanceof Error
							? resourceError.message
							: "扩展资料加载失败",
					);
				}
			});
		return () => {
			cancelled = true;
		};
	}, [knowledgeBaseApi, selectedTextbook, token]);

	const replaceTextbook = (nextTextbook: Textbook) => {
		setTextbooks((current) =>
			current.map((textbook) =>
				textbook.textbook_id === nextTextbook.textbook_id
					? nextTextbook
					: textbook,
			),
		);
	};

	const findMaterials = async (gap: KnowledgeGapAdmin) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			const response = await knowledgeBaseApi.findMaterials(token, gap.gap_id);
			setGaps((current) =>
				current.map((item) =>
					item.gap_id === gap.gap_id
						? { ...item, ...response.gap, sources: response.sources }
						: item,
				),
			);
		} catch (actionError) {
			setError(
				actionError instanceof Error ? actionError.message : "找素材失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const uploadGapMaterials = async (gap: KnowledgeGapAdmin) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			const response = await knowledgeBaseApi.uploadGapMaterials(
				token,
				gap.gap_id,
				createUploadPayload(gap),
			);
			replaceTextbook(response.textbook);
			setGaps((current) =>
				current.map((item) =>
					item.gap_id === gap.gap_id ? { ...item, ...response.gap } : item,
				),
			);
		} catch (actionError) {
			setError(actionError instanceof Error ? actionError.message : "上传失败");
		} finally {
			setBusy(false);
		}
	};

	const publishTextbook = async (textbook: Textbook) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			replaceTextbook(
				await knowledgeBaseApi.publishTextbook(token, textbook.textbook_id),
			);
		} catch (actionError) {
			setError(
				actionError instanceof Error ? actionError.message : "教材发布失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const unpublishTextbook = async (textbook: Textbook) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			replaceTextbook(
				await knowledgeBaseApi.unpublishTextbook(token, textbook.textbook_id),
			);
		} catch (actionError) {
			setError(
				actionError instanceof Error ? actionError.message : "教材下架失败",
			);
		} finally {
			setBusy(false);
		}
	};

	const deleteTextbook = async (textbook: Textbook) => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			await knowledgeBaseApi.deleteTextbook(token, textbook.textbook_id);
			setTextbooks((current) =>
				current.filter((item) => item.textbook_id !== textbook.textbook_id),
			);
			setSelectedTextbookId((current) =>
				current === textbook.textbook_id ? "" : current,
			);
		} catch (actionError) {
			setError(
				actionError instanceof Error ? actionError.message : "教材删除失败",
			);
		} finally {
			setBusy(false);
		}
	};

	if (isEditingOutline && selectedTextbook) {
		return (
			<motion.main
				className="admin-page"
				initial={reduceMotion ? false : { opacity: 0, y: 16 }}
				animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
				transition={
					reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }
				}
			>
				<div className="admin-ambient-sun" aria-hidden="true" />
				<div className="admin-paper-canvas" aria-hidden="true" />
				<section
					className="admin-shell"
					aria-labelledby="admin-knowledge-title"
				>
					<nav className="admin-menu" aria-label="管理员菜单">
						<button
							className="admin-logo-area"
							type="button"
							onClick={() => setIsEditingOutline(false)}
							aria-label="返回教材列表"
						>
							<span className="admin-logo-pebble" aria-hidden="true">
								&larr;
							</span>
							<span className="admin-logo-brand" style={{ fontSize: "1.2rem" }}>
								返回教材列表
							</span>
						</button>
						<span className="admin-user-chip">
							{user?.username ?? "管理员"}
						</span>
					</nav>

					<header
						className="admin-header"
						style={{
							display: "flex",
							justifyContent: "space-between",
							alignItems: "center",
						}}
					>
						<div>
							<p className="admin-kicker">outline & aigc</p>
							<h1 id="admin-knowledge-title" style={{ fontSize: "2rem" }}>
								《{selectedTextbook.title}》大纲微调与正文生成
							</h1>
						</div>
						<div
							className="admin-header-actions"
							style={{
								display: "flex",
								gap: "var(--space-16)",
								alignItems: "center",
							}}
						>
							{generationProgress && (
								<div
									className="aigc-progress-bar-container"
									style={{
										display: "flex",
										flexDirection: "column",
										alignItems: "flex-end",
										gap: "var(--space-4)",
									}}
								>
									<span
										style={{
											fontSize: "var(--text-caption)",
											color: "var(--color-text-muted)",
										}}
									>
										{generationProgress.current_section_title
											? `正在生成: ${generationProgress.current_section_title}`
											: "准备中..."}{" "}
										({generationProgress.progress_percentage.toFixed(0)}%)
									</span>
									<div
										className="progress-track"
										style={{
											width: "150px",
											height: "6px",
											background: "oklch(88% 0.02 75)",
											borderRadius: "3px",
											overflow: "hidden",
										}}
									>
										<div
											className="progress-fill"
											style={{
												width: `${generationProgress.progress_percentage}%`,
												height: "100%",
												background: "var(--gradient-coral)",
												transition: "width 0.3s ease",
											}}
										/>
									</div>
								</div>
							)}
							<button
								type="button"
								className="admin-primary-action"
								onClick={handleTriggerAigcContent}
								disabled={
									busy ||
									isGeneratingContent ||
									(generationProgress &&
										generationProgress.status === "running")
								}
								style={{
									padding: "var(--space-8) var(--space-16)",
									height: "40px",
									display: "flex",
									alignItems: "center",
									gap: "var(--space-8)",
								}}
							>
								{isGeneratingContent ? (
									<Loader2 className="spinner" size={16} />
								) : (
									<Play aria-hidden="true" size={16} />
								)}
								<span>
									{isGeneratingContent
										? "异步生成中..."
										: "一键异步生成教材正文 (AIGC)"}
								</span>
							</button>
						</div>
					</header>

					{error && <p className="admin-error">{error}</p>}

					<OutlineEditor
						textbook={selectedTextbook}
						onSave={handleSaveOutline}
						generateOutlineApi={handleGenerateOutline}
					/>
				</section>
			</motion.main>
		);
	}

	return (
		<motion.main
			className="admin-page"
			initial={reduceMotion ? false : { opacity: 0, y: 16 }}
			animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
			transition={
				reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }
			}
		>
			<div className="admin-ambient-sun" aria-hidden="true" />
			<div className="admin-paper-canvas" aria-hidden="true" />
			<section className="admin-shell" aria-labelledby="admin-knowledge-title">
				<nav className="admin-menu" aria-label="管理员菜单">
					<NavLink
						className="admin-logo-area"
						to="/admin/accounts"
						aria-label="回到后台首页"
					>
						<span className="admin-logo-pebble" aria-hidden="true">
							<img src="/logo.png" alt="" className="admin-logo-img" />
						</span>
						<span className="admin-logo-brand">one-tree</span>
					</NavLink>
					<span className="admin-menu-links">
						{adminRoutes.map((route) => (
							<NavLink
								key={route.path}
								to={route.path}
								className={({ isActive }) =>
									`admin-menu-link ${isActive ? "active" : ""}`
								}
								title={route.hint}
							>
								{route.label}
							</NavLink>
						))}
					</span>
					<span className="admin-user-chip">{user?.username ?? "管理员"}</span>
				</nav>

				<header className="admin-header">
					<div>
						<p className="admin-kicker">knowledge-base</p>
						<h1 id="admin-knowledge-title">知识库</h1>
					</div>
					<div className="admin-header-actions">
						<button
							className="admin-secondary-action"
							type="button"
							onClick={() => void loadKnowledgeBase()}
							disabled={busy}
						>
							<RefreshCw aria-hidden="true" />
							<span>刷新知识库</span>
						</button>
					</div>
				</header>

				{error ? <p className="admin-error">{error}</p> : null}

				<section className="admin-kb-grid" aria-label="知识库管理">
					<section className="admin-kb-panel" aria-label="来源清单">
						<header>
							<div>
								<p className="admin-kicker">sources</p>
								<h2>来源清单</h2>
							</div>
						</header>
						<div className="admin-kb-list">
							{sources.map((source) => {
								const missingItems = missingAdmissionItems(source);
								return (
									<article className="admin-kb-card" key={source.source_id}>
										<div className="admin-kb-card-title">
											<h3>{source.name}</h3>
											<span className="admin-status is-active">
												{sourceStatusLabels.status[source.status]}
											</span>
										</div>
										<p>{source.base_url || "暂无来源地址"}</p>
										<div className="admin-kb-pills">
											<span>
												下载：
												{
													sourceStatusLabels.download_status[
														source.download_status
													]
												}
											</span>
											<span>
												解析：
												{sourceStatusLabels.parse_status[source.parse_status]}
											</span>
											<span>
												许可审查：
												{
													sourceStatusLabels.license_review_status[
														source.license_review_status
													]
												}
											</span>
											<span>
												人工审查：
												{
													sourceStatusLabels.human_review_status[
														source.human_review_status
													]
												}
											</span>
										</div>
										<p className="admin-kb-note">
											缺少准入项：
											{missingItems.length > 0 ? missingItems.join("、") : "无"}
										</p>
									</article>
								);
							})}
							{sources.length === 0 ? (
								<p className="admin-empty">暂无来源。</p>
							) : null}
						</div>
					</section>

					<section
						className="admin-kb-panel admin-kb-panel-wide"
						aria-label="教材列表"
					>
						<header>
							<div>
								<p className="admin-kicker">textbooks</p>
								<h2>教材列表</h2>
							</div>
							<p className="admin-kb-note">下架仅适用于已发布教材。</p>
						</header>
						<div className="admin-kb-list">
							{textbooks.map((textbook) => {
								const resourcesForTextbook = extensionResources.filter(
									(resource) => resource.textbook_id === textbook.textbook_id,
								);
								const missingExtensionCount = extensionGapCount(
									textbook,
									resourcesForTextbook,
									visibleGaps,
								);
								return (
									<article className="admin-kb-card" key={textbook.textbook_id}>
										<div className="admin-kb-card-title">
											<h3>{textbook.title}</h3>
											<span className="admin-kb-source">
												{textbook.source_id}
											</span>
										</div>
										<div className="admin-kb-pills">
											<span>
												整理：{ingestionStatusLabels[textbook.ingestion_status]}
											</span>
											<span>
												校对：
												{
													outlineReviewStatusLabels[
														textbook.outline_review_status
													]
												}
											</span>
											<span>
												学生可用：
												{
													availabilityStatusLabels[
														textbook.student_availability_status
													]
												}
											</span>
										</div>
										<div className="admin-row-actions">
											<button
												type="button"
												className="admin-primary-action"
												disabled={busy}
												onClick={() => void publishTextbook(textbook)}
												aria-label={`发布 ${textbook.title} 未覆盖扩展资料 ${missingExtensionCount} 项`}
											>
												<BookOpen aria-hidden="true" />
												<span>发布</span>
												<small>未覆盖扩展资料 {missingExtensionCount} 项</small>
											</button>
											<button
												type="button"
												className="admin-secondary-action"
												disabled={
													busy ||
													textbook.student_availability_status !== "published"
												}
												onClick={() => void unpublishTextbook(textbook)}
												aria-label={`下架 ${textbook.title}`}
											>
												<span>下架</span>
											</button>
											<button
												type="button"
												className="admin-secondary-action"
												onClick={() => {
													setSelectedTextbookId(textbook.textbook_id);
													setIsEditingOutline(true);
												}}
												aria-label={`编辑大纲 ${textbook.title}`}
											>
												<Edit2
													aria-hidden="true"
													style={{
														width: "14px",
														height: "14px",
														marginRight: "4px",
													}}
												/>
												<span>编辑大纲</span>
											</button>
											<button
												type="button"
												className="admin-danger-action"
												disabled={busy}
												onClick={() => void deleteTextbook(textbook)}
												aria-label={`删除 ${textbook.title}`}
											>
												<Trash2 aria-hidden="true" />
												<span>删除</span>
											</button>
										</div>
									</article>
								);
							})}
							{textbooks.length === 0 ? (
								<p className="admin-empty">暂无教材。</p>
							) : null}
						</div>
						<div className="admin-kb-rules">
							<p>删除草稿：未绑定学生时移除教材、扩展资料和整理任务。</p>
							<p>删除已发布、已下架或已绑定教材：保留记录并归档。</p>
						</div>
					</section>

					<section className="admin-kb-panel" aria-label="未覆盖待办">
						<header>
							<div>
								<p className="admin-kicker">gaps</p>
								<h2>未覆盖待办</h2>
							</div>
						</header>
						<div className="admin-kb-list">
							{visibleGaps.map((gap) => (
								<article className="admin-kb-card" key={gap.gap_id}>
									<div className="admin-kb-card-title">
										<h3>{gap.normalized_topic}</h3>
										<span className="admin-status">
											{gapStatusLabels[gap.status]}
										</span>
									</div>
									<div className="admin-kb-metrics">
										<span>触发次数：{gap.trigger_count}</span>
										<span>关注人数：{gap.follow_count}</span>
										<span>最近触发：{formatDate(gap.latest_triggered_at)}</span>
									</div>
									<div className="admin-kb-goals">
										{gap.student_goal_summaries.map((summary) => (
											<span key={summary}>{summary}</span>
										))}
									</div>
									<div className="admin-row-actions">
										<button
											type="button"
											className="admin-secondary-action"
											disabled={busy}
											onClick={() => void findMaterials(gap)}
											aria-label={`一键找素材 ${gap.normalized_topic}`}
										>
											<Search aria-hidden="true" />
											<span>一键找素材</span>
										</button>
										<button
											type="button"
											className="admin-primary-action"
											disabled={busy}
											onClick={() => void uploadGapMaterials(gap)}
											aria-label={`自行上传 ${gap.normalized_topic}`}
										>
											<Upload aria-hidden="true" />
											<span>自行上传</span>
										</button>
									</div>
								</article>
							))}
							{visibleGaps.length === 0 ? (
								<p className="admin-empty">暂无未覆盖待办。</p>
							) : null}
						</div>
					</section>

					<section className="admin-kb-panel" aria-label="扩展资料绑定">
						<header>
							<div>
								<p className="admin-kicker">extensions</p>
								<h2>扩展资料绑定</h2>
							</div>
							<label className="admin-kb-select">
								<span>教材</span>
								<select
									value={selectedTextbook?.textbook_id ?? ""}
									onChange={(event) =>
										setSelectedTextbookId(event.target.value)
									}
								>
									{textbooks.map((textbook) => (
										<option
											key={textbook.textbook_id}
											value={textbook.textbook_id}
										>
											{textbook.title}
										</option>
									))}
								</select>
							</label>
						</header>
						<div className="admin-kb-list">
							{extensionResources.map((resource) => (
								<article className="admin-kb-card" key={resource.resource_id}>
									<div className="admin-kb-card-title">
										<h3>{resource.title_zh}</h3>
										<span className="admin-kb-source">
											{resource.section_id}
										</span>
									</div>
									<p>
										{resource.description_zh ||
											resource.source_name ||
											"暂无说明"}
									</p>
									<div className="admin-kb-pills">
										<span>{resource.render_mode}</span>
										<span>{resource.status}</span>
										<span>{resource.source_name || "未标注来源"}</span>
									</div>
								</article>
							))}
							{extensionResources.length === 0 ? (
								<p className="admin-empty">暂无扩展资料绑定。</p>
							) : null}
						</div>
					</section>
				</section>
			</section>
		</motion.main>
	);
}
