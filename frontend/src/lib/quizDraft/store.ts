export interface DraftScope {
	uid: string;
	courseId: string;
	chapterId: string;
	quizId: string;
	version: string;
}
export interface PendingSubmission {
	client_submission_id: string;
	quiz_version: string;
	answers: Record<string, unknown>;
}
export interface QuizDraft {
	key: string;
	scope: DraftScope;
	revision: number;
	answers: Record<string, unknown>;
	selectedQuestionId: string | null;
	pending: PendingSubmission | null;
}
export class DraftConflict extends Error {
	constructor(message = "另一窗口已保存此测验，请选择要保留的草稿") {
		super(message);
	}
}
export const draftKey = (scope: DraftScope) =>
	JSON.stringify([
		scope.uid,
		scope.courseId,
		scope.chapterId,
		scope.quizId,
		scope.version,
	]);
let database: Promise<IDBDatabase> | null = null;
function openDatabase(): Promise<IDBDatabase> {
	if (!database)
		database = new Promise<IDBDatabase>((resolve, reject) => {
			const request = indexedDB.open("onetree-quiz-drafts", 2);
			let abandoned = false;
			request.onupgradeneeded = () => {
				const db = request.result;
				const store = db.objectStoreNames.contains("drafts")
					? request.transaction?.objectStore("drafts")
					: db.createObjectStore("drafts", { keyPath: "key" });
				if (store && !store.indexNames.contains("chapter"))
					store.createIndex("chapter", [
						"scope.uid",
						"scope.courseId",
						"scope.chapterId",
					]);
			};
			request.onerror = () => {
				database = null;
				reject(request.error ?? new Error("本机草稿存储不可用"));
			};
			request.onblocked = () => {
				abandoned = true;
				database = null;
				reject(new Error("请关闭旧版本学习窗口后重试保存"));
			};
			request.onsuccess = () => {
				const db = request.result;
				if (abandoned) {
					db.close();
					return;
				}
				db.onversionchange = () => {
					db.close();
					database = null;
				};
				resolve(db);
			};
		}).catch((error) => {
			database = null;
			throw error;
		});
	return database;
}
function imageBlob(value: unknown): unknown {
	if (
		!value ||
		typeof value !== "object" ||
		!("data_url" in value) ||
		typeof value.data_url !== "string"
	)
		return value;
	const [header, base64] = value.data_url.split(",");
	if (!base64) return value;
	const binary = atob(base64);
	const bytes = Uint8Array.from(binary, (c) => c.charCodeAt(0));
	const { data_url: _, ...metadata } = value;
	return {
		...metadata,
		blob: new Blob([bytes], {
			type: header.split(":")[1]?.split(";")[0] ?? "image/png",
		}),
	};
}
function imageAnswer(value: unknown): Promise<unknown> {
	if (
		!value ||
		typeof value !== "object" ||
		!("blob" in value) ||
		!(value.blob instanceof Blob)
	)
		return Promise.resolve(value);
	const { blob, ...metadata } = value;
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => resolve({ ...metadata, data_url: reader.result });
		reader.onerror = () => reject(new Error("图片草稿读取失败"));
		reader.readAsDataURL(blob);
	});
}
const encodeAnswers = (answers: Record<string, unknown>) =>
	Object.fromEntries(
		Object.entries(answers).map(([key, value]) => [key, imageBlob(value)]),
	);
const decodeAnswers = async (answers: Record<string, unknown>) =>
	Object.fromEntries(
		await Promise.all(
			Object.entries(answers).map(async ([key, value]) => [
				key,
				await imageAnswer(value),
			]),
		),
	);
async function decode(draft: QuizDraft): Promise<QuizDraft> {
	return {
		...draft,
		answers: await decodeAnswers(draft.answers),
		pending: draft.pending
			? {
					...draft.pending,
					answers: await decodeAnswers(draft.pending.answers),
				}
			: null,
	};
}
export async function readDraft(
	scope: DraftScope,
): Promise<{ draft: QuizDraft | null; outdated: boolean }> {
	const db = await openDatabase();
	const { stored, keys } = await new Promise<{
		stored: QuizDraft | undefined;
		keys: IDBValidKey[];
	}>((resolve, reject) => {
		const tx = db.transaction("drafts", "readonly");
		const store = tx.objectStore("drafts");
		const record = store.get(draftKey(scope));
		const siblings = store
			.index("chapter")
			.getAllKeys([scope.uid, scope.courseId, scope.chapterId]);
		tx.oncomplete = () =>
			resolve({ stored: record.result, keys: siblings.result });
		tx.onabort = () => reject(tx.error ?? new Error("草稿读取失败"));
	});
	return {
		draft: stored ? await decode(stored) : null,
		outdated: keys.some((key) => key !== draftKey(scope)),
	};
}
export async function writeDraft(
	draft: QuizDraft,
	expectedRevision: number | null,
): Promise<QuizDraft> {
	const db = await openDatabase();
	const encoded = {
		...draft,
		answers: encodeAnswers(draft.answers),
		pending: draft.pending
			? { ...draft.pending, answers: encodeAnswers(draft.pending.answers) }
			: null,
	};
	return new Promise((resolve, reject) => {
		const transaction = db.transaction("drafts", "readwrite");
		const store = transaction.objectStore("drafts");
		const request = store.get(draft.key);
		let error: Error | null = null;
		request.onsuccess = () => {
			const current = request.result as QuizDraft | undefined;
			if (
				expectedRevision !== null &&
				(current?.revision ?? 0) !== expectedRevision
			) {
				error = new DraftConflict();
				transaction.abort();
				return;
			}
			if (
				current?.pending &&
				(expectedRevision === null ||
					current.pending.client_submission_id !==
						draft.pending?.client_submission_id)
			) {
				error = new DraftConflict(
					"另一窗口的提交正在确认中，请读取已保存草稿查询结果；当前输入仍保留",
				);
				transaction.abort();
				return;
			}
			if (current?.pending) {
				if (current.pending.quiz_version !== draft.pending?.quiz_version) {
					error = new DraftConflict(
						"提交快照的题目版本不可更改，请读取已保存草稿",
					);
					transaction.abort();
					return;
				}
				encoded.pending = current.pending;
			}
			encoded.revision = (current?.revision ?? 0) + 1;
			store.put(encoded);
		};
		transaction.oncomplete = () => {
			void decode(encoded).then(resolve, reject);
		};
		transaction.onabort = () =>
			reject(error ?? transaction.error ?? new Error("草稿保存失败，请重试"));
		transaction.onerror = () => {
			error ??= new Error("本机空间不足或草稿保存失败，请重试");
		};
	});
}
export async function deleteDraft(
	scope: DraftScope,
	revision: number,
): Promise<void> {
	const db = await openDatabase();
	await new Promise<void>((resolve, reject) => {
		const tx = db.transaction("drafts", "readwrite");
		const store = tx.objectStore("drafts");
		const request = store.get(draftKey(scope));
		request.onsuccess = () => {
			if (request.result?.revision === revision) store.delete(draftKey(scope));
		};
		tx.oncomplete = () => resolve();
		tx.onabort = () => reject(tx.error ?? new Error("本机草稿清理失败"));
	});
}
