import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
	type AdminKnowledgeBaseApi,
	adminKnowledgeBaseApi as defaultKnowledgeBaseApi,
	type KnowledgeBaseAgentResponse,
	type KnowledgeBaseAgentStreamEvent,
	type KnowledgeBaseIngestionJob,
	type KnowledgeBaseSourceResult,
	type KnowledgeGapAdmin,
	type KnowledgeSource,
	type Textbook,
	type TextbookSectionContent,
} from "../../api/knowledgeBase";
import { useAuth } from "../../contexts/AuthContext";
import {
	AdminKnowledgeBaseAgent,
	type AdminKnowledgeBaseAgentEntry,
	type AdminKnowledgeBaseAgentStreamStep,
} from "./AdminKnowledgeBaseAgent";
import { AdminTextbookBrowser } from "./AdminTextbookBrowser";
import { OutlineEditor } from "./OutlineEditor";
import "./admin.css";

interface AdminKnowledgeBasePageProps {
	knowledgeBaseApi?: AdminKnowledgeBaseApi;
}

function formatStreamEventName(event: string): string {
	switch (event) {
		case "started":
			return "已收到管理员消息。";
		case "context_loaded":
			return "已读取知识库现状。";
		case "textbook_search_started":
			return "正在做教材精确匹配。";
		case "textbook_search_completed":
			return "教材精确匹配完成。";
		case "hybrid_search_started":
			return "正在扩展检索教材内容。";
		case "hybrid_search_completed":
			return "扩展检索完成。";
		case "textbook_hits_ready":
			return "已整理教材命中结果。";
		case "gap_search_started":
			return "正在检查未覆盖待办。";
		case "gap_search_completed":
			return "待办检查完成。";
		case "source_search_started":
			return "正在联网查找真实教材来源。";
		case "source_search_completed":
			return "真实教材来源查找完成。";
		case "reply_ready":
			return "已生成管理员回复。";
		case "completed":
			return "本轮已完成。";
		case "error":
			return "处理失败。";
		default:
			return event;
	}
}

function formatStreamEventMeta(event: KnowledgeBaseAgentStreamEvent): string {
	const parts: string[] = [];
	if (
		typeof event.source_count === "number" ||
		typeof event.textbook_count === "number" ||
		typeof event.gap_count === "number"
	) {
		parts.push(
			`${event.source_count ?? 0} 个来源 · ${event.textbook_count ?? 0} 本教材 · ${event.gap_count ?? 0} 个待办`,
		);
	}
	if (typeof event.match_count === "number") {
		parts.push(`匹配 ${event.match_count} 本教材`);
	}
	if (typeof event.hit_count === "number") {
		parts.push(`命中 ${event.hit_count} 条`);
	}
	if (typeof event.result_count === "number") {
		parts.push(`找到 ${event.result_count} 个来源`);
	}
	if (typeof event.reply_length === "number") {
		parts.push(`回复 ${event.reply_length} 字`);
	}
	if (typeof event.normalized_length === "number") {
		parts.push(`输入 ${event.normalized_length} 字`);
	}
	return parts.join(" · ");
}

function assertIngestionJobSucceeded(job: KnowledgeBaseIngestionJob): void {
	if (job.status !== "failed") return;
	throw new Error(job.error_message || "教材整理失败");
}

export function AdminKnowledgeBasePage({
	knowledgeBaseApi = defaultKnowledgeBaseApi,
}: AdminKnowledgeBasePageProps) {
	const { token } = useAuth();
	const [sources, setSources] = useState<KnowledgeSource[]>([]);
	const [textbooks, setTextbooks] = useState<Textbook[]>([]);
	const [gaps, setGaps] = useState<KnowledgeGapAdmin[]>([]);
	const [textbookSections, setTextbookSections] = useState<
		TextbookSectionContent[]
	>([]);
	const [selectedTextbookId, setSelectedTextbookId] = useState("");
	const [activeTab, setActiveTab] = useState<"agent" | "browser">("agent");
	const [entries, setEntries] = useState<AdminKnowledgeBaseAgentEntry[]>([]);
	const [streamSteps, setStreamSteps] = useState<
		AdminKnowledgeBaseAgentStreamStep[]
	>([]);
	const [lastResponse, setLastResponse] =
		useState<KnowledgeBaseAgentResponse | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [isEditingOutline, setIsEditingOutline] = useState(false);

	const selectedTextbook =
		textbooks.find((textbook) => textbook.textbook_id === selectedTextbookId) ??
		textbooks[0] ??
		null;
	const selectedTextbookSections = selectedTextbook
		? textbookSections.filter(
				(section) => section.textbook_id === selectedTextbook.textbook_id,
			)
		: [];

	const replaceTextbook = useCallback((nextTextbook: Textbook) => {
		setTextbooks((current) =>
			current.map((textbook) =>
				textbook.textbook_id === nextTextbook.textbook_id
					? nextTextbook
					: textbook,
			),
		);
	}, []);

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

	const appendStreamStep = useCallback(
		(event: KnowledgeBaseAgentStreamEvent) => {
			setStreamSteps((current) => {
				const nextStep: AdminKnowledgeBaseAgentStreamStep = {
					id: `${Date.now()}-${current.length}-${event.event}`,
					event: event.event,
					message: event.message || formatStreamEventName(event.event),
					timestamp: new Date().toISOString(),
					meta: formatStreamEventMeta(event),
					status:
						event.event === "error"
							? "error"
							: event.event === "completed"
								? "success"
								: "running",
				};
				return [...current, nextStep].slice(-3);
			});
		},
		[],
	);

	const submitAgentMessage = useCallback(
		async (message: string) => {
			if (!token) return null;
			setBusy(true);
			setError(null);
			const userEntry: AdminKnowledgeBaseAgentEntry = {
				id: `user-${Date.now()}`,
				role: "user",
				content: message,
				timestamp: new Date().toISOString(),
				textbookHits: [],
				gapHits: [],
				sourceResults: [],
			};
			setEntries((current) => [...current, userEntry]);
			setStreamSteps([]);
			try {
				const response = knowledgeBaseApi.streamAgent
					? await knowledgeBaseApi.streamAgent(token, message, appendStreamStep)
					: await knowledgeBaseApi.runAgent(token, message);
				setLastResponse(response);
				setEntries((current) => [
					...current,
					{
						id: `assistant-${Date.now()}`,
						role: "assistant",
						content: response.reply_text,
						timestamp: new Date().toISOString(),
						textbookHits: response.textbook_hits ?? [],
						gapHits: response.gap_hits ?? [],
						sourceResults: response.source_results ?? [],
					},
				]);
				if (response.selected_textbook_id) {
					setSelectedTextbookId(response.selected_textbook_id);
				}
				const [nextSources, nextTextbooks, nextGaps] = await Promise.all([
					knowledgeBaseApi.listSources(token),
					knowledgeBaseApi.listTextbooks(token),
					knowledgeBaseApi.listGaps(token),
				]);
				setSources(nextSources);
				setTextbooks(nextTextbooks);
				setGaps(nextGaps);
				if (response.selected_textbook_id) {
					setSelectedTextbookId(response.selected_textbook_id);
				}
				return response;
			} catch (submitError) {
				const messageText =
					submitError instanceof Error ? submitError.message : "对话发送失败";
				setError(messageText);
				setEntries((current) => [
					...current,
					{
						id: `assistant-error-${Date.now()}`,
						role: "assistant",
						content: messageText,
						timestamp: new Date().toISOString(),
						textbookHits: [],
						gapHits: [],
						sourceResults: [],
					},
				]);
				return null;
			} finally {
				setBusy(false);
			}
		},
		[appendStreamStep, knowledgeBaseApi, token],
	);

	const confirmSourceResult = useCallback(
		async (sourceResult: KnowledgeBaseSourceResult) => {
			if (!token) return;
			setBusy(true);
			setError(null);
			try {
				const response = await knowledgeBaseApi.confirmSourceResult(
					token,
					sourceResult,
				);
				setTextbooks((current) => [response.textbook, ...current]);
				setSelectedTextbookId(response.textbook.textbook_id);
				const job = await knowledgeBaseApi.runIngestionJob(
					token,
					response.job.job_id,
				);
				assertIngestionJobSucceeded(job);
				await loadKnowledgeBase();
			} catch (confirmError) {
				setError(
					confirmError instanceof Error ? confirmError.message : "确认解析失败",
				);
			} finally {
				setBusy(false);
			}
		},
		[knowledgeBaseApi, loadKnowledgeBase, token],
	);

	const organizeSelected = useCallback(async () => {
		if (!token || !selectedTextbook) return;
		setBusy(true);
		setError(null);
		try {
			const job = await knowledgeBaseApi.organizeTextbook(
				token,
				selectedTextbook.textbook_id,
			);
			assertIngestionJobSucceeded(job);
			await loadKnowledgeBase();
		} catch (organizeError) {
			setError(
				organizeError instanceof Error ? organizeError.message : "教材整理失败",
			);
		} finally {
			setBusy(false);
		}
	}, [knowledgeBaseApi, loadKnowledgeBase, selectedTextbook, token]);

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

	const publishSelected = useCallback(async () => {
		if (!token || !selectedTextbook) return;
		setBusy(true);
		setError(null);
		try {
			const updated = await knowledgeBaseApi.publishTextbook(
				token,
				selectedTextbook.textbook_id,
			);
			replaceTextbook(updated);
		} catch (publishError) {
			setError(
				publishError instanceof Error ? publishError.message : "教材发布失败",
			);
		} finally {
			setBusy(false);
		}
	}, [knowledgeBaseApi, replaceTextbook, selectedTextbook, token]);

	const unpublishTextbook = useCallback(
		async (textbook: Textbook) => {
			if (!token) return;
			setBusy(true);
			setError(null);
			try {
				const updated = await knowledgeBaseApi.unpublishTextbook(
					token,
					textbook.textbook_id,
				);
				replaceTextbook(updated);
			} catch (unpublishError) {
				setError(
					unpublishError instanceof Error
						? unpublishError.message
						: "教材下架失败",
				);
			} finally {
				setBusy(false);
			}
		},
		[knowledgeBaseApi, replaceTextbook, token],
	);

	const deleteTextbook = useCallback(
		async (textbook: Textbook) => {
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
			} catch (deleteError) {
				setError(
					deleteError instanceof Error ? deleteError.message : "教材删除失败",
				);
			} finally {
				setBusy(false);
			}
		},
		[knowledgeBaseApi, token],
	);

	useEffect(() => {
		void loadKnowledgeBase();
	}, [loadKnowledgeBase]);

	useEffect(() => {
		if (!token || !selectedTextbook) {
			setTextbookSections([]);
			return;
		}
		let isCurrent = true;
		knowledgeBaseApi
			.listTextbookSections(token, selectedTextbook.textbook_id)
			.then((sections) => {
				if (!isCurrent) return;
				setTextbookSections(sections);
			})
			.catch((sectionError) => {
				if (!isCurrent) return;
				setTextbookSections([]);
				setError(
					sectionError instanceof Error
						? sectionError.message
						: "教材正文加载失败",
				);
			});
		return () => {
			isCurrent = false;
		};
	}, [knowledgeBaseApi, selectedTextbook, token]);

	if (isEditingOutline && selectedTextbook) {
		return (
			<>
				<header className="admin-header">
					<div>
						<p className="admin-kicker">outline</p>
						<h1 id="admin-knowledge-title">
							《{selectedTextbook.title}》教材大纲与正文
						</h1>
					</div>
					<div className="admin-header-actions">
						<button
							className="admin-secondary-action"
							type="button"
							onClick={() => setIsEditingOutline(false)}
							aria-label="返回教材工作台"
						>
							返回工作台
						</button>
					</div>
				</header>

				{error ? <p className="admin-error">{error}</p> : null}

				<OutlineEditor
					textbook={selectedTextbook}
					sections={selectedTextbookSections}
					onSave={handleSaveOutline}
				/>
			</>
		);
	}

	return (
		<>
			<header className="admin-header admin-kb-header">
				<div>
					<p className="admin-kicker">knowledge-base</p>
					<h1 id="admin-knowledge-title">知识库</h1>
					
					{/* Tabs */}
					<div className="admin-kb-tabs" role="tablist">
						<button
							role="tab"
							aria-selected={activeTab === "agent"}
							className={`admin-kb-tab ${activeTab === "agent" ? "is-active" : ""}`}
							type="button"
							onClick={() => setActiveTab("agent")}
						>
							💬 AI 智能助理
						</button>
						<button
							role="tab"
							aria-selected={activeTab === "browser"}
							className={`admin-kb-tab ${activeTab === "browser" ? "is-active" : ""}`}
							type="button"
							onClick={() => setActiveTab("browser")}
						>
							📚 教材库浏览
						</button>
					</div>
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
					{selectedTextbook ? (
						<button
							className="admin-primary-action"
							type="button"
							disabled={busy}
							onClick={() => setIsEditingOutline(true)}
						>
							<span>查看教材</span>
						</button>
					) : null}
				</div>
			</header>

			{error ? <p className="admin-error">{error}</p> : null}

			{activeTab === "agent" ? (
				<AdminKnowledgeBaseAgent
					isBusy={busy}
					sources={sources}
					textbooks={textbooks}
					gaps={gaps.filter((gap) => gap.status !== "closed")}
					selectedTextbookId={selectedTextbookId}
					selectedTextbook={selectedTextbook}
					entries={entries}
					streamSteps={streamSteps}
					lastResponse={lastResponse}
					onSubmitMessage={submitAgentMessage}
					onSelectTextbook={(textbookId) => setSelectedTextbookId(textbookId)}
					onConfirmSourceResult={confirmSourceResult}
					onOrganizeSelected={organizeSelected}
					onPublishSelected={publishSelected}
					onUnpublishSelected={async () => {
						if (!selectedTextbook) return;
						await unpublishTextbook(selectedTextbook);
					}}
					onDeleteSelected={async () => {
						if (!selectedTextbook) return;
						await deleteTextbook(selectedTextbook);
					}}
					onEditSelectedOutline={() => setIsEditingOutline(true)}
					selectedTextbookSections={selectedTextbookSections}
				/>
			) : (
				<AdminTextbookBrowser
					textbooks={textbooks}
					selectedTextbookId={selectedTextbookId}
					selectedTextbook={selectedTextbook}
					selectedTextbookSections={selectedTextbookSections}
					isBusy={busy}
					onSelectTextbook={(textbookId) => setSelectedTextbookId(textbookId)}
					onOrganizeSelected={organizeSelected}
					onPublishSelected={publishSelected}
					onUnpublishSelected={async () => {
						if (!selectedTextbook) return;
						await unpublishTextbook(selectedTextbook);
					}}
					onDeleteSelected={async () => {
						if (!selectedTextbook) return;
						await deleteTextbook(selectedTextbook);
					}}
					onEditSelectedOutline={() => setIsEditingOutline(true)}
				/>
			)}
		</>
	);
}
