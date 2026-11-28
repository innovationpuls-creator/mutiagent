import { describe, expect, it } from "vitest";
import {
	CONFIRMED_KEYS,
	quotesStudent,
	buildBasicProfile,
	buildCollectingProfile,
	emptyConfirmedInfo,
	isCompleteProfile,
	isSupportedGrade,
	mergeConfirmed,
	nextQuestionCard,
	normalizeConfirmed,
} from "../src/chat/profileContract.js";
import { FULL_CONFIRMED } from "./chatHarness.js";

/** Mirrors frontend pickProfile() + hasCompleteBasicProfileRecord(). */
function frontendAccepts(profile: Record<string, any>): boolean {
	if (profile.type !== "basic_profile" && profile.type !== "collecting") return false;
	if (profile.type === "basic_profile") {
		if (!isSupportedGrade(profile.confirmed_info?.current_grade)) return false;
		if (!CONFIRMED_KEYS.every((key) => Object.hasOwn(profile.confirmed_info, key))) return false;
	}
	return (
		typeof profile.stage === "string" &&
		typeof profile.question_mode === "string" &&
		typeof profile.confirmed_info === "object" &&
		Array.isArray(profile.defaulted_fields) &&
		typeof profile.question_md === "string" &&
		typeof profile.question_box === "object" &&
		Array.isArray(profile.question_box.options) &&
		typeof profile.question_box.question === "string" &&
		typeof profile.text === "string"
	);
}

describe("profile contract builders", () => {
	it("collecting and basic profiles satisfy the frontend contract", () => {
		const collecting = buildCollectingProfile({
			confirmed: emptyConfirmedInfo(),
			questionMd: "你的专业是？",
			options: [],
			stage: "basic_info",
		});
		expect(frontendAccepts(collecting as never)).toBe(true);
		const basic = buildBasicProfile({ confirmed: normalizeConfirmed(FULL_CONFIRMED), defaulted: [], summary: "总结" });
		expect(frontendAccepts(basic as never)).toBe(true);
		expect(isCompleteProfile(basic as never)).toBe(true);
	});

	it("grade support matches the frontend map", () => {
		for (const ok of ["大一", "大2", "三年级", "我是大四"]) expect(isSupportedGrade(ok)).toBe(true);
		for (const bad of ["研二", "大五", "高三", "", undefined]) expect(isSupportedGrade(bad)).toBe(false);
	});

	it("a default-fill quote must really be in the student's message", () => {
		expect(quotesStudent("直接按默认帮我生成画像", "按默认帮我生成")).toBe(true);
		expect(quotesStudent("你们看着办吧，我不想答了", "你们看着办吧")).toBe(true);
		expect(quotesStudent("我大三软件工程", "按默认补全")).toBe(false);
		expect(quotesStudent("我大三软件工程", "")).toBe(false);
		expect(quotesStudent("我大三软件工程", undefined)).toBe(false);
	});

	it("merging never erases data with empty/unknown values", () => {
		const base = normalizeConfirmed({ current_grade: "大三", major: "软件工程" });
		const merged = mergeConfirmed(base, { current_grade: "", major: "未知", learning_stage: "刚入门" });
		expect(merged).toMatchObject({ current_grade: "大三", major: "软件工程", learning_stage: "刚入门" });
	});

	it("the fallback card walks the core fields in order and handles bad grades", () => {
		expect(nextQuestionCard(emptyConfirmedInfo()).text).toContain("年级和专业");
		const withGrade = nextQuestionCard(normalizeConfirmed({ current_grade: "大二" }));
		expect(withGrade.text).toContain("专业");
		const bad = nextQuestionCard(normalizeConfirmed({ current_grade: "研一", major: "软件工程" }));
		expect(bad.confirmed_info.current_grade).toBe("");
		expect(bad.text).toContain("研一");
		const multi = nextQuestionCard(normalizeConfirmed({ current_grade: "大三", major: "软件工程" }));
		expect(multi.question_box.options.length).toBeGreaterThan(0);
	});

	it("an incomplete or non-basic profile is never 'complete'", () => {
		expect(isCompleteProfile(null)).toBe(false);
		expect(isCompleteProfile({ type: "collecting", confirmed_info: FULL_CONFIRMED })).toBe(false);
		expect(isCompleteProfile({ type: "basic_profile", confirmed_info: { ...FULL_CONFIRMED, current_grade: "研二" } })).toBe(false);
	});
});
