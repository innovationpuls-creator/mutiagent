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
	TextbookSectionContent,
} from "../../api/knowledgeBase";
import { AdminTextbookInspector } from "./AdminTextbookInspector";

export interface AdminKnowledgeBaseAgentEntry {
	id: string;
	role: "user" | "assistant";
	content: string;
	timestamp: string;
	textbookHits: KnowledgeBaseAgentTextbookHit[];
	gapHits: KnowledgeBaseAgentGapHit[];
	sourceResults: KnowledgeBaseSourceResult[];
}

export interface AdminKnowledgeBaseAgentStreamStep {
	id: string;
	event: string;
	message: string;
	timestamp: string;
	meta: string;
	status: "running" | "success" | "error";
}

interface AdminKnowledgeBaseAgentProps {
	isBusy: boolean;
	sources: KnowledgeSource[];
	textbooks: Textbook[];
	gaps: KnowledgeGapAdmin[];
	selectedTextbookId: string;
	selectedTextbook: Textbook | null;
	entries: AdminKnowledgeBaseAgentEntry[];
	streamSteps: AdminKnowledgeBaseAgentStreamStep[];
	lastResponse: KnowledgeBaseAgentResponse | null;
	onSubmitMessage: (
		message: string,
	) => Promise<KnowledgeBaseAgentResponse | null>;
	onSelectTextbook: (textbookId: string) => void;
	onConfirmSourceResult: (
		sourceResult: KnowledgeBaseSourceResult,
	) => Promise<void>;
	onOrganizeSelected: () => Promise<void>;
	onPublishSelected: () => Promise<void>;
	onUnpublishSelected: () => Promise<void>;
	onDeleteSelected: () => Promise<void>;
	onEditSelectedOutline: () => void;
	selectedTextbookSections: TextbookSectionContent[];
}

function formatTime(value: string) {
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return "—";
	return new Intl.DateTimeFormat("zh-CN", {
		hour: "2-digit",
		minute: "2-digit",
		second: "2-digit",
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

function formatSourceType(value: string) {
	switch (value) {
		case "pdf":
			return "PDF";
		case "html":
			return "HTML open textbook";
		default:
			return value;
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

export function AdminKnowledgeBaseAgent({
	isBusy,
	sources,
	textbooks,
	gaps,
	selectedTextbookId,
	selectedTextbook,
	entries,
	streamSteps,
	lastResponse,
	onSubmitMessage,
	onSelectTextbook,
	onConfirmSourceResult,
	onOrganizeSelected,
	onPublishSelected,
	onUnpublishSelected,
	onDeleteSelected,
	onEditSelectedOutline,
	selectedTextbookSections,
}: AdminKnowledgeBaseAgentProps) {
	const [draft, setDraft] = useState("");
	const [isResourcesExpanded, setIsResourcesExpanded] = useState(false);
	const threadRef = useRef<HTMLDivElement>(null);
	const lastTextbookHits = lastResponse?.textbook_hits ?? [];
	const lastGapHits = lastResponse?.gap_hits ?? [];

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
					<div className="admin-kb-source-meta">
						<span>原始语言：{result.language || "未知"}</span>
						<span>来源类型：{formatSourceType(result.source_type)}</span>
					</div>
					<a
						className="admin-kb-source-url"
						href={result.source_url}
						target="_blank"
						rel="noreferrer"
					>
						{result.source_url}
					</a>
					<p>
						{result.topic_summary || result.description || "可作为教材来源"}
					</p>
					{result.parseability_reason ? (
						<p className="admin-kb-source-parseability">
							{result.parseability_reason}
						</p>
					) : null}
					{result.already_imported ? (
						<button
							type="button"
							className="admin-secondary-action"
							onClick={() =>
								result.textbook_id && onSelectTextbook(result.textbook_id)
							}
							aria-label={`去查看已入库教材 ${result.title}`}
						>
							<span>已入库 (去查看)</span>
						</button>
					) : (
						<button
							type="button"
							className="admin-primary-action"
							disabled={isBusy}
							onClick={() => void onConfirmSourceResult(result)}
							aria-label={`确认解析 ${result.title}`}
						>
							<span>确认解析</span>
						</button>
					)}
				</article>
			))}
		</div>
	);

	const renderStreamSteps = () => (
		<section className="admin-kb-stream-panel" aria-label="实时反馈">
			<div className="admin-kb-rail-head">
				<div>
					<p className="admin-kicker">stream</p>
					<h3>实时反馈</h3>
				</div>
			</div>
			<div className="admin-kb-stream-list">
				{streamSteps.length > 0 ? (
					streamSteps.map((step) => (
						<article
							className={`admin-kb-stream-step is-${step.status}`}
							key={step.id}
						>
							<div className="admin-kb-stream-dot" aria-hidden="true" />
							<div>
								<div className="admin-kb-rail-title">
									<strong>{step.message}</strong>
									<time>{formatTime(step.timestamp)}</time>
								</div>
								{step.meta ? <small>{step.meta}</small> : null}
							</div>
						</article>
					))
				) : (
					<p className="admin-kb-empty">发送消息后显示实时步骤。</p>
				)}
			</div>
		</section>
	);

	return (
		<section className="admin-kb-workspace" aria-label="管理员对话工作台">
			<div className="admin-kb-layout">
				{/* 左侧：智能对话工作台 */}
				<section className="admin-kb-left-panel" aria-label="对话工作台">
					<div className="admin-kb-panel-header">
						<h3>💬 AI 知识库助手</h3>
						<p>通过对话导入教材、解析大纲或关联未覆盖的知识点</p>
					</div>

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
									<strong>{entry.role === "user" ? "管理员" : "Agent"}</strong>
									<time>{formatTime(entry.timestamp)}</time>
								</div>
								<p className="admin-kb-bubble-content">{entry.content}</p>
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
													{formatStatus(hit.student_availability_status)} ·{" "}
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
						{renderStreamSteps()}
					</div>

					<form className="admin-kb-composer" onSubmit={handleSubmit}>
						<label className="sr-only" htmlFor="admin-kb-message">
							消息
						</label>
						<textarea
							id="admin-kb-message"
							value={draft}
							onChange={(event) => setDraft(event.target.value)}
							onKeyDown={handleKeyDown}
							placeholder="直接说你的教材，或描述待对齐的内容..."
							rows={3}
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

					{/* 底部折叠式数据源与待办抽屉 */}
					<div className="admin-kb-resources-drawer">
						<button
							type="button"
							className={`admin-kb-drawer-toggle ${isResourcesExpanded ? "is-active" : ""}`}
							onClick={() => setIsResourcesExpanded(!isResourcesExpanded)}
							aria-expanded={isResourcesExpanded}
						>
							<span className="admin-kb-drawer-title">
								📚 <span>来源状态</span>与<span>未覆盖待办</span>
							</span>
							<span className="admin-kb-drawer-count">
								{sources.length} 来源 · {gaps.length} 待办
							</span>
							<span className="admin-kb-drawer-chevron">
								{isResourcesExpanded ? "▲" : "▼"}
							</span>
						</button>
						{isResourcesExpanded && (
							<div className="admin-kb-drawer-content">
								<div className="admin-kb-drawer-grid">
									<section className="admin-kb-drawer-section">
										<h4>数据源状态 ({sources.length})</h4>
										<div className="admin-kb-drawer-list">
											{sources.length > 0 ? (
												sources.map((source) => (
													<div
														className="admin-kb-drawer-card"
														key={source.source_id}
													>
														<div className="admin-kb-drawer-card-title">
															<strong>{source.name}</strong>
															<span
																className={`status-pill is-${source.status}`}
															>
																{source.status === "enabled" ? "启用" : "停用"}
															</span>
														</div>
														<small>
															下载{" "}
															{formatSourceCheckStatus(source.download_status)}{" "}
															· 解析{" "}
															{formatSourceCheckStatus(source.parse_status)} ·
															人工{" "}
															{formatSourceCheckStatus(
																source.human_review_status,
															)}
														</small>
													</div>
												))
											) : (
												<p className="admin-kb-drawer-empty">无数据源</p>
											)}
										</div>
									</section>

									<section className="admin-kb-drawer-section">
										<h4>未覆盖待办 ({gaps.length})</h4>
										<div className="admin-kb-drawer-list">
											{gaps.length > 0 ? (
												gaps.slice(0, 6).map((gap) => (
													<div
														className="admin-kb-drawer-card"
														key={gap.gap_id}
													>
														<div className="admin-kb-drawer-card-title">
															<strong>{gap.normalized_topic}</strong>
															<span className="status-pill">
																{formatGapStatus(gap.status)}
															</span>
														</div>
														<p>{gap.student_goal_summaries[0] || "无摘要"}</p>
														<small>
															触发 {gap.trigger_count} 次 · 关注{" "}
															{gap.follow_count} 人
														</small>
													</div>
												))
											) : (
												<p className="admin-kb-drawer-empty">无待办事项</p>
											)}
										</div>
									</section>
								</div>
							</div>
						)}
					</div>
				</section>

				{/* 右侧：教材大纲与资源详情审查面板 */}
				<section className="admin-kb-right-panel" aria-label="详情审查面板">
					<div className="admin-kb-panel-header">
						<h3>📖 教材与解析详情</h3>
						<p>查看教材大纲与管理操作 (已录入 {textbooks.length} 本教材)</p>
					</div>

					<div className="admin-kb-inspector-content">
						{/* 命中的匹配结果 */}
						{lastResponse &&
							(lastTextbookHits.length > 0 || lastGapHits.length > 0) && (
								<div className="admin-kb-matches-section">
									<h4>🎯 本轮智能匹配结果</h4>
									<div className="admin-kb-rail-list">
										{lastTextbookHits.map((hit) => (
											<button
												key={hit.textbook_id}
												type="button"
												className={`admin-kb-match ${hit.textbook_id === selectedTextbookId ? "is-active" : ""}`}
												onClick={() => onSelectTextbook(hit.textbook_id)}
												aria-label={`选中教材 ${hit.title}`}
											>
												<div className="admin-kb-match-header">
													<strong>{hit.title}</strong>
													<span className="status-badge">
														{formatStatus(hit.student_availability_status)}
													</span>
												</div>
												<p>{hit.reason || hit.source_name}</p>
											</button>
										))}
										{lastGapHits.map((gap) => (
											<div className="admin-kb-match-gap-card" key={gap.gap_id}>
												<div className="admin-kb-match-header">
													<strong>{gap.normalized_topic}</strong>
													<span className="status-badge">
														{formatGapStatus(gap.status)}
													</span>
												</div>
												<p>{gap.reason || "缺口匹配成功"}</p>
											</div>
										))}
									</div>
								</div>
							)}

						<AdminTextbookInspector
							selectedTextbook={selectedTextbook}
							selectedTextbookSections={selectedTextbookSections}
							isBusy={isBusy}
							onOrganizeSelected={onOrganizeSelected}
							onPublishSelected={onPublishSelected}
							onUnpublishSelected={onUnpublishSelected}
							onDeleteSelected={onDeleteSelected}
							onEditSelectedOutline={onEditSelectedOutline}
						/>
					</div>
				</section>
			</div>
		</section>
	);
}
