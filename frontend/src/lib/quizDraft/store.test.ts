import "fake-indexeddb/auto";
import { describe, expect, it } from "vitest";
import {
	DraftConflict,
	type DraftScope,
	deleteDraft,
	draftKey,
	readDraft,
	writeDraft,
} from "./store";

const scope = (uid: string, version = "v1"): DraftScope => ({
	uid,
	version,
	courseId: "course",
	chapterId: "1",
	quizId: "quiz",
});
const record = (
	id: DraftScope,
	answers: Record<string, unknown> = { choice: "A", code: "print('hello')" },
) => ({
	key: draftKey(id),
	scope: id,
	revision: 0,
	answers,
	selectedQuestionId: "code",
	pending: null,
});
describe("native IndexedDB quiz drafts", () => {
	it("restores choice and full code answers with selected question", async () => {
		const id = scope("restore");
		const saved = await writeDraft(record(id), 0);
		const { draft } = await readDraft(id);
		expect(draft).toEqual(saved);
	});
	it("isolates users and versions while preserving outdated drafts", async () => {
		const id = scope("isolation");
		await writeDraft(record(id), 0);
		expect((await readDraft(scope("other"))).draft).toBeNull();
		expect(await readDraft(scope("isolation", "v2"))).toEqual({
			draft: null,
			outdated: true,
		});
		expect((await readDraft(id)).draft?.answers.choice).toBe("A");
	});
	it("detects concurrent revisions and permits explicit overwrite", async () => {
		const id = scope("conflict");
		const first = await writeDraft(record(id), 0);
		const next = await writeDraft(
			{ ...first, answers: { choice: "B" } },
			first.revision,
		);
		await expect(
			writeDraft({ ...first, answers: { choice: "C" } }, first.revision),
		).rejects.toBeInstanceOf(DraftConflict);
		expect((await readDraft(id)).draft?.answers.choice).toBe("B");
		const replacement = await writeDraft(
			{ ...next, answers: { choice: "C" } },
			null,
		);
		expect(replacement.revision).toBe(3);
	});
	it("keeps immutable submission identity across reload and protects newer draft on cleanup", async () => {
		const id = scope("pending");
		const pending = {
			client_submission_id: "request-1",
			quiz_version: "v1",
			answers: { choice: "A" },
		};
		const first = await writeDraft({ ...record(id), pending }, 0);
		expect((await readDraft(id)).draft?.pending).toEqual(pending);
		await expect(
			writeDraft({ ...first, pending: null }, null),
		).rejects.toBeInstanceOf(DraftConflict);
		const next = await writeDraft(
			{ ...first, answers: { choice: "B" } },
			first.revision,
		);
		expect(next.pending).toEqual(pending);
		const changed = await writeDraft(
			{ ...next, pending: { ...pending, answers: { choice: "C" } } },
			next.revision,
		);
		expect(changed.pending).toEqual(pending);
		expect((await readDraft(id)).draft?.pending).toEqual(pending);
		await deleteDraft(id, first.revision);
		expect((await readDraft(id)).draft?.revision).toBe(changed.revision);
		await deleteDraft(id, changed.revision);
		expect((await readDraft(id)).draft).toBeNull();
	});
});
