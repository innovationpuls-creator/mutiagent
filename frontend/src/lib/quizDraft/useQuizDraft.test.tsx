import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
	type DraftScope,
	draftKey,
	type QuizDraft,
	readDraft,
	writeDraft,
} from "./store";
import { useQuizDraft } from "./useQuizDraft";

vi.mock("./store", async (importOriginal) => ({
	...(await importOriginal<typeof import("./store")>()),
	readDraft: vi.fn(),
	writeDraft: vi.fn(),
	deleteDraft: vi.fn(),
}));
const scope: DraftScope = {
	uid: "user",
	courseId: "course",
	chapterId: "1",
	quizId: "quiz",
	version: "v1",
};
const answers = { code: "original code" };
const pending = {
	client_submission_id: "submission",
	quiz_version: "v1",
	answers,
};
const restore = vi.fn();
const record: QuizDraft = {
	key: draftKey(scope),
	scope,
	revision: 1,
	answers,
	selectedQuestionId: "code",
	pending: null,
};
beforeEach(() => {
	vi.mocked(readDraft).mockResolvedValue({ draft: null, outdated: false });
	vi.mocked(writeDraft).mockImplementation(async (draft) => ({
		...draft,
		revision: draft.revision + 1,
	}));
});
afterEach(() => {
	cleanup();
	vi.resetAllMocks();
});
function setup() {
	return renderHook(() => useQuizDraft(scope, answers, "code", restore));
}

describe("submission snapshot persistence", () => {
	it("does not lock answers or publish a pending submission before the transaction succeeds", async () => {
		const { result } = setup();
		await waitFor(() => expect(result.current.message).toBe("已保存到本机"));
		vi.mocked(writeDraft).mockRejectedValueOnce(new Error("quota exceeded"));
		await act(async () => {
			await expect(result.current.save(false, pending)).rejects.toThrow(
				"quota exceeded",
			);
		});
		expect(result.current.pending).toBeNull();
		expect(result.current.dirty).toBe(true);
		expect(result.current.message).toBe("quota exceeded");
		await act(async () => {
			await result.current.save();
		});
		expect(result.current.pending).toBeNull();
		expect(result.current.dirty).toBe(false);
		await act(async () => {
			await result.current.save(false, pending);
		});
		expect(result.current.pending).toEqual(pending);
	});
	it("keeps queued answer saves separate from a later submission snapshot", async () => {
		const { result } = setup();
		await waitFor(() => expect(result.current.message).toBe("已保存到本机"));
		vi.mocked(writeDraft).mockClear();
		await act(async () => {
			const answerSave = result.current.save();
			const snapshotSave = result.current.save(false, pending);
			await Promise.all([answerSave, snapshotSave]);
		});
		expect(vi.mocked(writeDraft).mock.calls[0][0].pending).toBeNull();
		expect(vi.mocked(writeDraft).mock.calls[1][0].pending).toEqual(pending);
	});
	it("retains current input when another window has cleared the saved draft", async () => {
		vi.mocked(readDraft).mockResolvedValueOnce({
			draft: { ...record, pending },
			outdated: false,
		});
		const { result } = setup();
		await waitFor(() => expect(result.current.pending).toEqual(pending));
		await act(async () => {
			await result.current.reload();
		});
		expect(result.current.pending).toBeNull();
		expect(result.current.dirty).toBe(true);
		expect(result.current.message).toContain("当前输入仍保留");
	});
});
