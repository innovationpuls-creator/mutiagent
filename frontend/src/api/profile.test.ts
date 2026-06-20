import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchProfileDashboard } from "./profile";

describe("fetchProfileDashboard", () => {
	afterEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it("throws when dashboard payload contains unsupported current course progress state", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					profile: {
						currentGrade: "大三",
						major: "软件工程",
						learningStage: "项目实践",
						hasClearGoal: "是",
						learningMethodPreference: "项目驱动",
						learningPacePreference: "周末集中",
						contentPreference: ["实践"],
						needGuidance: "需要",
						knowledgeFoundation: "有基础",
						strengths: "执行力强",
						weaknesses: "部署经验不足",
						experience: "做过课程项目",
						shortTermGoal: "完成 AI 项目",
						longTermGoal: "成为 AI 应用开发者",
						weeklyAvailableTime: "每周 8 小时",
						constraints: "周末集中",
					},
					profileCompleteness: 100,
					profileSummaryText: "测试摘要",
					todayLearning: {
						title: "AI 应用开发项目课",
						description: "继续当前课程",
						source: "学习路径智能体",
						currentLearningCourse: {
							grade_id: "year_3",
							course_node_id: "year_3_course_1",
							course_or_chapter_theme: "AI 应用开发项目课",
							course_goal: "完成项目",
							time_arrangement: {
								semester_scope: "上学期",
								duration: "6 周",
								pace_reason: "围绕项目节奏推进",
							},
							current_focus: "需求拆解",
							progress_state: "paused",
							next_action: "继续第一章",
						},
						currentCourseDetail: null,
						currentCourseOutline: null,
						gradeCourses: [],
						followingCourses: [],
					},
					recommendations: [],
				}),
			}),
		);

		await expect(fetchProfileDashboard("token-1")).rejects.toThrow(
			"画像数据格式不正确",
		);
	});
});
