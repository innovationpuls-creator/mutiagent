import { describe, expect, it } from "vitest";
import { normalizeCourse } from "./branch";

describe("normalizeCourse", () => {
	it("should parse minimal course correctly", () => {
		const raw = {
			course_node_id: "math_101",
			course_or_chapter_theme: "College Math",
			course_goal: "Learn basics of calculus",
			status: "locked",
			has_outline: false,
		};
		const result = normalizeCourse(raw);
		expect(result.course_node_id).toBe("math_101");
		expect(result.status).toBe("locked");
		expect(result.is_custom).toBeUndefined();
	});

	it("should parse full custom metadata correctly", () => {
		const raw = {
			course_node_id: "python_101",
			course_or_chapter_theme: "Python Intro",
			course_goal: "Intro to programming",
			status: "current",
			has_outline: true,
			is_custom: true,
			parent_preset_id: "cs_basics",
			prerequisite_ids: ["math_101"],
			time_arrangement: {
				semester_scope: "1",
				duration: "32学时",
				pace_reason: "First year first term",
			},
			key_points: ["Variables", "Loops"],
			difficult_points: ["Recursion"],
			acceptance_criteria: ["Write a script"],
		};
		const result = normalizeCourse(raw);
		expect(result.is_custom).toBe(true);
		expect(result.parent_preset_id).toBe("cs_basics");
		expect(result.prerequisite_ids).toEqual(["math_101"]);
		expect(result.time_arrangement?.semester_scope).toBe("1");
		expect(result.key_points).toContain("Loops");
	});

	it("should fallback to undefined for malformed optional metadata", () => {
		const raw = {
			course_node_id: "math_102",
			course_or_chapter_theme: "Advanced Math",
			course_goal: "Calculus II",
			status: "locked",
			has_outline: false,
			prerequisite_ids: [123, "math_101"], // contains number
			time_arrangement: { semester_scope: 1 }, // missing duration, invalid scope type
		};
		const result = normalizeCourse(raw);
		expect(result.prerequisite_ids).toBeUndefined();
		expect(result.time_arrangement).toBeUndefined();
	});

	it("should throw error on invalid format", () => {
		const raw = {
			course_node_id: 123, // 应该是 string
			course_or_chapter_theme: "Python Intro",
			course_goal: "Intro to programming",
			status: "invalid_status",
			has_outline: true,
		};
		expect(() => normalizeCourse(raw)).toThrow("繁枝数据格式不正确");
	});
});
