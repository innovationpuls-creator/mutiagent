import { useCallback, useEffect, useRef, useState } from "react";
import {
	DraftConflict,
	type DraftScope,
	deleteDraft,
	draftKey,
	type PendingSubmission,
	type QuizDraft,
	readDraft,
	writeDraft,
} from "./store";
export function useQuizDraft(
	scope: DraftScope | null,
	answers: Record<string, unknown>,
	selectedQuestionId: string | null,
	onRestore: (draft: QuizDraft) => void,
) {
	const key = scope ? draftKey(scope) : "";
	const [ready, setReady] = useState(false);
	const [message, setMessage] = useState("");
	const [notice, setNotice] = useState("");
	const [dirty, setDirty] = useState(false);
	const [conflict, setConflict] = useState(false);
	const [pending, setPending] = useState<PendingSubmission | null>(null);
	const state = useRef({
		key: "",
		scope: null as DraftScope | null,
		revision: 0,
		pending: null as PendingSubmission | null,
		blocked: false,
		hydrated: false,
	});
	const queue = useRef<Promise<void>>(Promise.resolve());
	const latest = useRef({ answers, selectedQuestionId, onRestore });
	latest.current = { answers, selectedQuestionId, onRestore };
	useEffect(() => {
		const active = {
			key,
			scope,
			revision: 0,
			pending: null as PendingSubmission | null,
			blocked: false,
			hydrated: false,
		};
		state.current = active;
		setReady(false);
		setDirty(false);
		setConflict(false);
		setPending(null);
		setMessage("");
		setNotice("");
		if (!scope) return;
		let cancelled = false;
		readDraft(scope)
			.then(({ draft, outdated }) => {
				if (cancelled) return;
				if (draft) {
					active.revision = draft.revision;
					active.pending = draft.pending;
					setPending(draft.pending);
					latest.current.onRestore(draft);
				}
				setNotice(
					outdated ? "题目已更新，旧草稿仍保留在本机，未套用到新题" : "",
				);
				setMessage(draft ? "已恢复本机草稿" : "");
			})
			.catch(() => {
				if (!cancelled)
					setMessage("本机草稿读取失败，请重试；当前输入仍可保留");
			})
			.finally(() => {
				if (!cancelled) {
					active.hydrated = true;
					setReady(true);
				}
			});
		return () => {
			cancelled = true;
		};
	}, [key, scope]);
	const save = useCallback(
		(
			force = false,
			nextPending?: PendingSubmission | null,
			values?: {
				answers: Record<string, unknown>;
				selectedQuestionId: string | null;
			},
		) => {
			const active = state.current;
			const snapshot = values ?? {
				answers: latest.current.answers,
				selectedQuestionId: latest.current.selectedQuestionId,
			};
			const task = queue.current
				.catch(() => {})
				.then(async () => {
					if (!active.scope || active !== state.current)
						throw new Error("测验已切换，请重新进入当前章节");
					if (active.blocked && !force) throw new DraftConflict();
					const saved = await writeDraft(
						{
							key: active.key,
							scope: active.scope,
							revision: active.revision,
							...snapshot,
							pending: nextPending === undefined ? active.pending : nextPending,
						},
						force ? null : active.revision,
					);
					if (active !== state.current) return;
					active.revision = saved.revision;
					active.pending = saved.pending;
					setPending(saved.pending);
					active.blocked = false;
					setDirty(
						snapshot.answers !== latest.current.answers ||
							snapshot.selectedQuestionId !== latest.current.selectedQuestionId,
					);
					setConflict(false);
					setMessage("已保存到本机");
				})
				.catch((error) => {
					if (active === state.current) {
						setDirty(true);
						setConflict(error instanceof DraftConflict);
						active.blocked = error instanceof DraftConflict;
						setMessage(
							error instanceof Error
								? error.message
								: "本机草稿保存失败，请重试",
						);
					}
					throw error;
				});
			queue.current = task.catch(() => {});
			return task;
		},
		[],
	);
	useEffect(() => {
		if (
			!ready ||
			!scope ||
			!state.current.hydrated ||
			state.current.key !== key
		)
			return;
		setDirty(true);
		void save(false, undefined, { answers, selectedQuestionId }).catch(
			() => {},
		);
	}, [answers, selectedQuestionId, ready, scope, save, key]);
	const markDirty = useCallback(() => {
		setDirty(true);
		setMessage("正在保存到本机…");
	}, []);
	const reload = useCallback(async () => {
		const active = state.current;
		if (!active.scope) return;
		const { draft } = await readDraft(active.scope);
		if (active !== state.current) return;
		active.revision = draft?.revision ?? 0;
		active.blocked = false;
		setConflict(false);
		active.pending = draft?.pending ?? null;
		setPending(active.pending);
		if (draft) latest.current.onRestore(draft);
		else {
			setDirty(true);
			setMessage("已保存的草稿已被另一窗口清除，当前输入仍保留，请重新保存");
			return;
		}
		setDirty(false);
		setMessage("已读取最新草稿");
	}, []);
	const complete = useCallback(async () => {
		const active = state.current;
		await queue.current;
		if (!active.scope || active !== state.current) return;
		await deleteDraft(active.scope, active.revision);
		active.pending = null;
		active.revision = 0;
		setPending(null);
		setDirty(false);
		setMessage("本次提交已保存");
	}, []);
	return {
		ready,
		message,
		notice,
		dirty,
		conflict,
		pending,
		save,
		reload,
		complete,
		markDirty,
	};
}
