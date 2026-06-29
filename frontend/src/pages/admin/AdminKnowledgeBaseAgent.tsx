import { SendHorizonal } from "lucide-react";
import {
	type FormEvent,
	type KeyboardEvent,
	useEffect,
	useRef,
	useState,
} from "react";
import type {
	KnowledgeBaseAgentGapHit,
	KnowledgeBaseAgentResponse,
	KnowledgeBaseAgentTextbookHit,
	KnowledgeBaseSourceResult,
	KnowledgeGapAdmin,
	KnowledgeSource,
	Textbook,
} from "../../api/knowledgeBase";

export interface AdminKnowledgeBaseAgentEntry {
	id: string;
	role: "user" | "assistant";
	content: string;
	timestamp: string;
	textbookHits: KnowledgeBaseAgentTextbookHit[];
	gapHits: KnowledgeBaseAgentGapHit[];
	sourceResults: KnowledgeBaseSourceResult[];
}

interface AdminKnowledgeBaseAgentProps {
	isBusy: boolean;
	sources: KnowledgeSource[];
	textbooks: Textbook[];
	gaps: KnowledgeGapAdmin[];
	selectedTextbookId: string;
	selectedTextbook: Textbook | null;
	entries: AdminKnowledgeBaseAgentEntry[];
	lastResponse: KnowledgeBaseAgentResponse | null;
	onSubmitMessage: (
		message: string,
	) => Promise<KnowledgeBaseAgentResponse | null>;
	onSelectTextbook: (textbookId: string) => void;
	onConfirmSourceResult: (
		sourceResult: KnowledgeBaseSourceResult,
	) => Promise<void>;
	onPublishSelected: () => Promise<void>;
	onUnpublishSelected: () => Promise<void>;
	onDeleteSelected: () => Promise<void>;
	onEditSelectedOutline: () => void;
}

function formatTime(value: string) {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "—";
	return new Intl.DateTimeFormat("zh-CN", {
		hour: "2-digit",
		minute: "2-digit",
	}).format(date);
}

function formatStatus(value: string) {
	switch (value) {
		case "published":
			return "已发布";
		case "draft":
			return "草稿";
		case "unpublished":
			return "已下架";
		case "archived":
			return "已归档";
		default:
			return value;
	}
}

function formatSourceCheckStatus(value: string) {
	switch (value) {
		case "verified":
		case "supported":
		case "reviewed":
		case "approved":
			return "已通过";
		case "failed":
		case "rejected":
			return "需处理";
		case "unverified":
		case "unreviewed":
			return "待检查";
		default:
			return "待检查";
	}
}

function formatGapStatus(value: string) {
	switch (value) {
		case "open":
			return "待处理";
		case "material_searching":
			return "查找中";
		case "material_found":
			return "已找到材料";
		case "resolved":
			return "已解决";
		case "closed":
			return "已关闭";
		default:
			return "待处理";
	}
}

function formatIngestionStatus(value: string) {
	switch (value) {
		case "not_started":
			return "待解析";
		case "processing":
			return "解析中";
		case "failed":
			return "解析失败";
		case "ready_for_outline_review":
			return "待检查大纲";
		case "completed":
			return "已完成";
		default:
			return "待解析";
	}
}

function formatOutlineStatus(value: string) {
	return value === "approved" ? "已确认" : "待确认";
}

function formatOutlineSummary(outline: unknown) {
	if (!outline || typeof outline !== "object") return "暂无大纲";
	const chapters = (outline as { chapters?: unknown }).chapters;
	if (Array.isArray(chapters)) {
		const sectionCount = chapters.reduce((total, chapter) => {
			if (!chapter || typeof chapter !== "object") return total;
			const sections = (chapter as { sections?: unknown }).sections;
			return total + (Array.isArray(sections) ? sections.length : 0);
		}, 0);
		return `${chapters.length} 章 · ${sectionCount} 节`;
	}
	const sections = (outline as { sections?: unknown }).sections;
	if (Array.isArray(sections)) {
		return `${sections.length} 节`;
	}
	return "暂无大纲";
}

export function AdminKnowledgeBaseAgent({
	isBusy,
	sources,
	textbooks,
	gaps,
	selectedTextbookId,
	selectedTextbook,
	entries,
	lastResponse,
	onSubmitMessage,
	onSelectTextbook,
	onConfirmSourceResult,
	onPublishSelected,
	onUnpublishSelected,
	onDeleteSelected,
	onEditSelectedOutline,
}: AdminKnowledgeBaseAgentProps) {
	const [draft, setDraft] = useState("");
	const threadRef = useRef<HTMLDivElement>(null);

	useEffect(() => {
		const thread = threadRef.current;
		if (!thread) return;
		thread.scrollTop = thread.scrollHeight;
	});

	const sendMessage = async (message: string) => {
		const nextMessage = message.trim();
		if (!nextMessage || isBusy) return;
		setDraft("");
		await onSubmitMessage(nextMessage);
	};

	const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		await sendMessage(draft);
	};

	const handleKeyDown = async (event: KeyboardEvent<HTMLTextAreaElement>) => {
		if (event.key !== "Enter" || event.shiftKey) return;
		event.preventDefault();
		await sendMessage(draft);
	};

	const renderSourceResults = (results: KnowledgeBaseSourceResult[]) => (
		<div className="admin-kb-hit-strip">
			{results.map((result) => (
				<article
					className="admin-kb-source-result"
					key={result.source_result_id}
				>
					<div className="admin-kb-rail-title">
						<strong>{result.title}</strong>
						<span>{result.is_recommended ? "推荐解析" : "可解析"}</span>
					</div>
					<p>
						{result.topic_summary || result.description || "可作为教材来源"}
					</p>
					<button
						type="button"
						className="admin-primary-action"
						disabled={isBusy}
						onClick={() => void onConfirmSourceResult(result)}
						aria-label={`确认解析 ${result.title}`}
					>
						<span>确认解析</span>
					</button>
				</article>
			))}
		</div>
	);

	return (
		<section className="admin-kb-workbench" aria-label="管理员对话工作台">
			<header className="admin-kb-workbench-header">
				<div className="admin-kb-workbench-summary">
					<p className="admin-kicker">admin / knowledge base</p>
					<h2>管理员知识库 Agent 工作台</h2>
				</div>
				<div className="admin-kb-workbench-status">
					<span>{sources.length} 个来源</span>
					<span>{textbooks.length} 本教材</span>
					<span>{gaps.length} 个待办</span>
				</div>
			</header>

			<div className="admin-kb-workbench-grid">
				<aside className="admin-kb-rail" aria-label="来源和待办">
					<section className="admin-kb-rail-panel">
						<div className="admin-kb-rail-head">
							<div>
								<p className="admin-kicker">sources</p>
								<h3>来源状态</h3>
							</div>
						</div>
						<div className="admin-kb-rail-list">
							{sources.length > 0 ? (
								sources.map((source) => (
									<article
										className="admin-kb-rail-card"
										key={source.source_id}
									>
										<div className="admin-kb-rail-title">
											<strong>{source.name}</strong>
											<span>
												{source.status === "enabled" ? "启用" : "停用"}
											</span>
										</div>
										<small>
											下载 {formatSourceCheckStatus(source.download_status)} ·
											解析 {formatSourceCheckStatus(source.parse_status)} · 人工{" "}
											{formatSourceCheckStatus(source.human_review_status)}
										</small>
									</article>
								))
							) : (
								<p className="admin-kb-empty">无来源。</p>
							)}
						</div>
					</section>

					<section className="admin-kb-rail-panel">
						<div className="admin-kb-rail-head">
							<div>
								<p className="admin-kicker">gaps</p>
								<h3>未覆盖待办</h3>
							</div>
						</div>
						<div className="admin-kb-rail-list">
							{gaps.length > 0 ? (
								gaps.slice(0, 6).map((gap) => (
									<article className="admin-kb-rail-card" key={gap.gap_id}>
										<div className="admin-kb-rail-title">
											<strong>{gap.normalized_topic}</strong>
											<span>{formatGapStatus(gap.status)}</span>
										</div>
										<p>{gap.student_goal_summaries[0] || "无摘要"}</p>
										<small>
											触发 {gap.trigger_count} 次 · 关注 {gap.follow_count} 人
										</small>
									</article>
								))
							) : (
								<p className="admin-kb-empty">无待办。</p>
							)}
						</div>
					</section>
				</aside>

				<section className="admin-kb-dialogue" aria-label="管理员对话">
					<header className="admin-kb-dialogue-head">
						<div>
							<p className="admin-kicker">agent</p>
							<h3>对话</h3>
						</div>
					</header>

					<div
						className="admin-kb-thread"
						role="log"
						aria-live="polite"
						ref={threadRef}
					>
						{entries.map((entry) => (
							<article
								key={entry.id}
								className={`admin-kb-bubble ${entry.role === "user" ? "is-user" : "is-agent"}`}
							>
								<div className="admin-kb-bubble-meta">
									<strong>{entry.role === "user" ? "管理员" : "agent"}</strong>
									<time>{formatTime(entry.timestamp)}</time>
								</div>
								<p>{entry.content}</p>
								{entry.role === "assistant" && entry.textbookHits.length > 0 ? (
									<div className="admin-kb-hit-strip">
										{entry.textbookHits.map((hit) => (
											<button
												key={hit.textbook_id}
												type="button"
												className={`admin-kb-hit ${hit.textbook_id === selectedTextbookId ? "is-active" : ""}`}
												onClick={() => onSelectTextbook(hit.textbook_id)}
											>
												<strong>{hit.title}</strong>
												<span>
													{formatStatus(hit.student_availability_status)} ·
													{hit.reason || hit.source_name}
												</span>
											</button>
										))}
									</div>
								) : null}
								{entry.role === "assistant" && entry.sourceResults.length > 0
									? renderSourceResults(entry.sourceResults)
									: null}
							</article>
						))}
					</div>

					<form className="admin-kb-composer" onSubmit={handleSubmit}>
						<label
							className="admin-kb-composer-label"
							htmlFor="admin-kb-message"
						>
							<span>消息</span>
						</label>
						<textarea
							id="admin-kb-message"
							value={draft}
							onChange={(event) => setDraft(event.target.value)}
							onKeyDown={handleKeyDown}
							placeholder="直接说你的教材"
							rows={4}
						/>
						<div className="admin-kb-composer-actions">
							<button
								type="submit"
								className="admin-primary-action"
								disabled={isBusy}
							>
								<SendHorizonal aria-hidden="true" />
								<span>{isBusy ? "发送中" : "发送"}</span>
							</button>
						</div>
					</form>
				</section>

				<aside className="admin-kb-inspector" aria-label="结果和教材详情">
					<section className="admin-kb-rail-panel">
						<div className="admin-kb-rail-head">
							<div>
								<p className="admin-kicker">matches</p>
								<h3>本轮结果</h3>
							</div>
						</div>
						<div className="admin-kb-rail-list">
							{lastResponse ? (
								<>
									{lastResponse.textbook_hits.length > 0 ? (
										lastResponse.textbook_hits.map((hit) => (
											<button
												key={hit.textbook_id}
												type="button"
												className={`admin-kb-match ${hit.textbook_id === selectedTextbookId ? "is-active" : ""}`}
												onClick={() => onSelectTextbook(hit.textbook_id)}
												aria-label={`命中教材 ${hit.title}`}
											>
												<div className="admin-kb-rail-title">
													<strong>{hit.title}</strong>
													<span>
														{formatStatus(hit.student_availability_status)}
													</span>
												</div>
												<p>{hit.reason || hit.source_name}</p>
											</button>
										))
									) : (
										<p className="admin-kb-empty">无直接命中。</p>
									)}
									{lastResponse.gap_hits.length > 0 ? (
										<div className="admin-kb-gap-block">
											{lastResponse.gap_hits.map((gap) => (
												<article
													className="admin-kb-rail-card"
													key={gap.gap_id}
												>
													<div className="admin-kb-rail-title">
														<strong>{gap.normalized_topic}</strong>
														<span>{formatGapStatus(gap.status)}</span>
													</div>
													<p>{gap.reason || "缺口命中"}</p>
												</article>
											))}
										</div>
									) : null}
								</>
							) : (
								<p className="admin-kb-empty">无结果。</p>
							)}
						</div>
					</section>

					<section className="admin-kb-rail-panel">
						<div className="admin-kb-rail-head">
							<div>
								<p className="admin-kicker">detail</p>
								<h3>当前教材</h3>
							</div>
						</div>
						{selectedTextbook ? (
							<div className="admin-kb-detail">
								<strong>{selectedTextbook.title}</strong>
								<p>
									{selectedTextbook.description ||
										selectedTextbook.original_title ||
										"暂无简介"}
								</p>
								<div className="admin-kb-detail-grid">
									<span>
										整理{" "}
										{formatIngestionStatus(selectedTextbook.ingestion_status)}
									</span>
									<span>
										大纲{" "}
										{formatOutlineStatus(
											selectedTextbook.outline_review_status,
										)}
									</span>
									<span>
										发布{" "}
										{formatStatus(selectedTextbook.student_availability_status)}
									</span>
								</div>
								<div className="admin-kb-detail-actions">
									<button
										type="button"
										className="admin-primary-action"
										disabled={isBusy}
										onClick={() => void onPublishSelected()}
									>
										<span>发布当前教材</span>
									</button>
									<button
										type="button"
										className="admin-secondary-action"
										disabled={isBusy}
										onClick={() => void onUnpublishSelected()}
									>
										<span>下架</span>
									</button>
									<button
										type="button"
										className="admin-secondary-action"
										disabled={isBusy}
										onClick={onEditSelectedOutline}
									>
										<span>编辑大纲</span>
									</button>
									<button
										type="button"
										className="admin-danger-action"
										disabled={isBusy}
										onClick={() => void onDeleteSelected()}
									>
										<span>删除</span>
									</button>
								</div>
								{selectedTextbook.outline && (
									<div className="admin-kb-detail-list">
										<p className="admin-kb-detail-list-label">大纲</p>
										<p>{formatOutlineSummary(selectedTextbook.outline)}</p>
									</div>
								)}
							</div>
						) : (
							<p className="admin-kb-empty">无教材。</p>
						)}
					</section>
				</aside>
			</div>
		</section>
	);
}
