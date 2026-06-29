import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
	type AdminKnowledgeBaseApi,
	adminKnowledgeBaseApi as defaultKnowledgeBaseApi,
	type KnowledgeBaseAgentResponse,
	type KnowledgeBaseSourceResult,
	type KnowledgeGapAdmin,
	type KnowledgeSource,
	type Textbook,
} from "../../api/knowledgeBase";
import { useAuth } from "../../contexts/AuthContext";
import {
	AdminKnowledgeBaseAgent,
	type AdminKnowledgeBaseAgentEntry,
} from "./AdminKnowledgeBaseAgent";
import { OutlineEditor } from "./OutlineEditor";
import "./admin.css";

interface AdminKnowledgeBasePageProps {
	knowledgeBaseApi?: AdminKnowledgeBaseApi;
}

export function AdminKnowledgeBasePage({
	knowledgeBaseApi = defaultKnowledgeBaseApi,
}: AdminKnowledgeBasePageProps) {
	const { token } = useAuth();
	const [sources, setSources] = useState<KnowledgeSource[]>([]);
	const [textbooks, setTextbooks] = useState<Textbook[]>([]);
	const [gaps, setGaps] = useState<KnowledgeGapAdmin[]>([]);
	const [selectedTextbookId, setSelectedTextbookId] = useState("");
	const [entries, setEntries] = useState<AdminKnowledgeBaseAgentEntry[]>([]);
	const [lastResponse, setLastResponse] =
		useState<KnowledgeBaseAgentResponse | null>(null);
	const [busy, setBusy] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [isEditingOutline, setIsEditingOutline] = useState(false);

	const selectedTextbook =
		textbooks.find((textbook) => textbook.textbook_id === selectedTextbookId) ??
		textbooks[0] ??
		null;

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
			try {
				const response = await knowledgeBaseApi.runAgent(token, message);
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
		[knowledgeBaseApi, token],
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

	if (isEditingOutline && selectedTextbook) {
		return (
			<>
				<header className="admin-header">
					<div>
						<p className="admin-kicker">outline</p>
						<h1 id="admin-knowledge-title">
							《{selectedTextbook.title}》大纲微调
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

				<OutlineEditor textbook={selectedTextbook} onSave={handleSaveOutline} />
			</>
		);
	}

	return (
		<>
			<header className="admin-header admin-kb-header">
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
					{selectedTextbook ? (
						<button
							className="admin-primary-action"
							type="button"
							disabled={busy}
							onClick={() => setIsEditingOutline(true)}
						>
							<span>编辑当前大纲</span>
						</button>
					) : null}
				</div>
			</header>

			{error ? <p className="admin-error">{error}</p> : null}

			<AdminKnowledgeBaseAgent
				isBusy={busy}
				sources={sources}
				textbooks={textbooks}
				gaps={gaps.filter((gap) => gap.status !== "closed")}
				selectedTextbookId={selectedTextbookId}
				selectedTextbook={selectedTextbook}
				entries={entries}
				lastResponse={lastResponse}
				onSubmitMessage={submitAgentMessage}
				onSelectTextbook={(textbookId) => setSelectedTextbookId(textbookId)}
				onConfirmSourceResult={confirmSourceResult}
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
		</>
	);
}
