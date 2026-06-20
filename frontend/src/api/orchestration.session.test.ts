import { beforeEach, describe, expect, it, vi } from "vitest";
import { getMyLearningPath } from "./learningPath";
import {
	type SessionAgentEvent,
	startSession,
	streamSession,
} from "./orchestration";

function makeCompleteProfile() {
	return {
		type: "basic_profile",
		stage: "generated",
		question_mode: "question_box",
		confirmed_info: {
			current_grade: "大三",
			major: "软件工程",
			learning_stage: "项目实践",
			has_clear_goal: "是",
			learning_method_preference: "项目驱动学习",
			learning_pace_preference: "按项目里程碑推进",
			content_preference: ["代码实践"],
			need_guidance: "需要轻量提醒",
			knowledge_foundation: "软件工程基础",
			strengths: "工程实现",
			weaknesses: "大型项目实战经验",
			experience: "做过课程项目",
			short_term_goal: "完成 AI 功能模块",
			long_term_goal: "形成 AI 应用开发能力",
			weekly_available_time: "每周 8 小时",
			constraints: "时间有限",
		},
		defaulted_fields: [],
		question_md: "画像已生成，是否继续生成学习路径？",
		question_box: {
			question: "画像已生成，下一步要继续生成学习路径吗？",
			options: [],
		},
		text: "画像已生成",
	};
}

function makeLearningPath() {
	return {
		schema_version: "learning_path.v2.course_node",
		learning_goal: {
			target_course_or_skill: "AI 应用开发",
			goal_type: "项目实践",
			desired_outcome: "完成一个 AI 功能模块",
			four_year_outcome: "形成 AI 应用开发能力",
		},
		learner_baseline: {
			current_grade: "大三",
			major: "软件工程",
			mastered_content: ["Python 基础"],
			weaknesses: ["部署经验不足"],
			constraints: ["时间有限"],
			weekly_available_time: "每周 8 小时",
		},
		planning_rules: {
			node_unit: "course_node",
			grade_boundary_rule: "按年级拆分",
			sequence_rule: "先基础后项目",
			resource_rule: "每个节点补充学习资源",
		},
		grade_plans: {
			year_1: {
				grade_id: "year_1",
				grade_name: "大一",
				grade_goal: "夯实基础",
				course_nodes: [],
			},
			year_2: {
				grade_id: "year_2",
				grade_name: "大二",
				grade_goal: "建立工程能力",
				course_nodes: [],
			},
			year_3: {
				grade_id: "year_3",
				grade_name: "大三",
				grade_goal: "完成 AI 项目闭环",
				course_nodes: [
					{
						course_node_id: "year_3_course_1",
						grade_id: "year_3",
						course_or_chapter_theme: "AI Agent 开发基础能力搭建",
						time_arrangement: {
							semester_scope: "上学期",
							duration: "6 周",
							pace_reason: "项目驱动",
						},
						course_goal: "完成最小功能闭环",
						prerequisite_node_ids: [],
						chapter_nodes: [],
						core_knowledge_points: [],
						key_points: ["接口接入"],
						difficult_points: ["错误处理"],
						learning_sequence: ["需求拆解", "接口接入"],
						knowledge_relations: [],
						downstream_resource_direction_ids: [],
						acceptance_criteria: ["完成一个可运行模块"],
					},
				],
			},
			year_4: {
				grade_id: "year_4",
				grade_name: "大四",
				grade_goal: "作品集沉淀",
				course_nodes: [],
			},
		},
		knowledge_graph: {
			global_relations: [],
			critical_paths: [],
		},
		resource_generation_contract: {
			downstream_agents: [],
			resource_directions: [],
		},
		dynamic_update_contract: {
			trackable_metrics: [],
			update_triggers: [],
			adjustment_strategy: "按周调整",
		},
		current_learning_course: {
			grade_id: "year_3",
			course_node_id: "year_3_course_1",
			course_or_chapter_theme: "AI Agent 开发基础能力搭建",
			course_goal: "完成最小功能闭环",
			time_arrangement: {
				semester_scope: "上学期",
				duration: "6 周",
				pace_reason: "项目驱动",
			},
			current_focus: "需求拆解",
			progress_state: "in_progress",
			next_action: "继续学习第一章",
		},
	};
}

describe("session orchestration API", () => {
	beforeEach(() => {
		vi.restoreAllMocks();
		vi.unstubAllGlobals();
	});

	it("POSTs to /api/chat/start with correct payload", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: async () => ({
				session_id: "sess-1",
				reply_text: "你好！",
				profile: null,
				year_learning_paths: null,
				course_knowledge: null,
			}),
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await startSession("token-1", "你好");

		expect(fetchMock).toHaveBeenCalledWith(
			"http://127.0.0.1:8000/api/chat/start",
			expect.objectContaining({
				method: "POST",
				headers: expect.objectContaining({ Authorization: "Bearer token-1" }),
				body: JSON.stringify({ query: "你好" }),
			}),
		);
		expect(result.sessionId).toBe("sess-1");
		expect(result.text).toBe("你好！");
		expect(result.hasProfile).toBe(false);
	});

	it("reflects year_learning_paths presence from start response", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					session_id: "sess-2",
					reply_text: null,
					profile: makeCompleteProfile(),
					year_learning_paths: { year_3: makeLearningPath() },
					course_knowledge: null,
				}),
			}),
		);

		const result = await startSession("token-1", "开始");
		expect(result.hasProfile).toBe(true);
		expect(result.hasPaths).toBe(true);
		expect(result.hasOutline).toBe(false);
	});

	it("keeps collecting profile incomplete in start response", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					session_id: "sess-collecting",
					reply_text: null,
					profile: {
						type: "collecting",
						stage: "basic_info",
						question_mode: "question_md",
						confirmed_info: {
							current_grade: "大三",
							major: "",
							learning_stage: "",
							has_clear_goal: "",
							learning_method_preference: "",
							learning_pace_preference: "",
							content_preference: [],
							need_guidance: "",
							knowledge_foundation: "",
							strengths: "",
							weaknesses: "",
							experience: "",
							short_term_goal: "",
							long_term_goal: "",
							weekly_available_time: "",
							constraints: "",
						},
						defaulted_fields: [],
						question_md: "为了生成基础画像，请先告诉我你的专业。",
						question_box: { question: "", options: [] },
						text: "为了生成基础画像，请先告诉我你的专业。",
					},
					year_learning_paths: { year_3: makeLearningPath() },
					course_knowledge: null,
				}),
			}),
		);

		const result = await startSession("token-1", "开始");

		expect(result.hasProfile).toBe(false);
		expect(result.hasPaths).toBe(true);
	});

	it("does not mark summary-only legacy basic_profile as completed in start response", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					session_id: "sess-summary-only",
					reply_text: null,
					profile: {
						type: "basic_profile",
						summary_text:
							"【基础学习画像总结】大三软件工程，当前以 AI 应用开发为主线。",
					},
					year_learning_paths: { year_3: makeLearningPath() },
					course_knowledge: null,
				}),
			}),
		);

		const result = await startSession("token-1", "开始");

		expect(result.hasProfile).toBe(false);
		expect(result.hasPaths).toBe(true);
		expect(result.hasOutline).toBe(false);
	});

	it("does not mark unsupported postgraduate basic_profile as completed in start response", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					session_id: "sess-unsupported-grade",
					reply_text: null,
					profile: {
						...makeCompleteProfile(),
						confirmed_info: {
							...makeCompleteProfile().confirmed_info,
							current_grade: "研一",
						},
						text: "当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
						summary_text:
							"当前学习路径只支持大一到大四。你当前提供的年级是「研一」，请先确认对应的本科年级。",
					},
					year_learning_paths: { year_3: makeLearningPath() },
					course_knowledge: null,
				}),
			}),
		);

		const result = await startSession("token-1", "开始");

		expect(result.hasProfile).toBe(false);
		expect(result.hasPaths).toBe(true);
		expect(result.hasOutline).toBe(false);
	});

	it("streams SSE events and returns a SessionTurn", async () => {
		const encoder = new TextEncoder();
		const body = new ReadableStream({
			start(controller) {
				controller.enqueue(
					encoder.encode(
						[
							"event: session_started",
							'data: {"session_id":"sess-stream","query":"开始"}',
							"",
							"event: supervisor_thinking",
							'data: {"message":"正在分析..."}',
							"",
							"event: agent_calling",
							'data: {"agent":"profile_agent","label":"画像智能体","args":""}',
							"",
							"event: agent_result",
							'data: {"agent":"profile_agent","label":"画像智能体","success":true,"summary":"画像已生成"}',
							"",
							"event: text_chunk",
							'data: {"chunk":"你的画像"}',
							"",
							"event: text_chunk",
							'data: {"chunk":"已生成"}',
							"",
							"event: message_completed",
							'data: {"full_text":"你的画像已生成"}',
							"",
							"event: session_completed",
							'data: {"session_id":"sess-stream","has_profile":true,"has_paths":false,"has_outline":false}',
							"",
						].join("\n"),
					),
				);
				controller.close();
			},
		});

		// First call: /api/chat/start (because sessionId is null)
		const fetchMock = vi
			.fn()
			.mockResolvedValueOnce({
				ok: true,
				json: async () => ({
					session_id: "sess-stream",
					reply_text: "greeting",
					profile: null,
					year_learning_paths: null,
					course_knowledge: null,
				}),
			})
			.mockResolvedValueOnce(new Response(body, { status: 200 }));
		vi.stubGlobal("fetch", fetchMock);

		const events: SessionAgentEvent[] = [];
		const turn = await streamSession("token-1", "开始", null, (e) =>
			events.push(e),
		);

		expect(turn.sessionId).toBe("sess-stream");
		expect(turn.text).toBe("你的画像已生成");
		expect(turn.hasProfile).toBe(true);
		expect(events.map((e) => e.event)).toEqual([
			"session_started",
			"supervisor_thinking",
			"agent_calling",
			"agent_result",
			"text_chunk",
			"text_chunk",
			"message_completed",
			"session_completed",
		]);
		expect(events[2].agent).toBe("profile_agent");
		expect(events[2].label).toBe("画像智能体");
	});

	it("reads saved learning path via getMyLearningPath", async () => {
		const fetchMock = vi.fn().mockResolvedValue({
			ok: true,
			json: async () => ({
				year_learning_paths: {
					year_2: {
						schema_version: "learning_path.v2.course_node",
						learning_goal: {
							target_course_or_skill: "数据结构",
							goal_type: "课程学习",
							desired_outcome: "掌握数据结构核心内容",
							four_year_outcome: "完成计算机基础课程体系",
						},
						learner_baseline: {
							current_grade: "大二",
							major: "计算机科学与技术",
							mastered_content: ["程序设计基础"],
							weaknesses: ["抽象数据结构理解不足"],
							constraints: ["每周时间有限"],
							weekly_available_time: "每周 6 小时",
						},
						planning_rules: {
							node_unit: "course_node",
							grade_boundary_rule: "按年级拆分",
							sequence_rule: "先线性结构再非线性结构",
							resource_rule: "每个节点补充练习资源",
						},
						grade_plans: {
							year_1: {
								grade_id: "year_1",
								grade_name: "大一",
								grade_goal: "完成基础预备",
								course_nodes: [],
							},
							year_2: {
								grade_id: "year_2",
								grade_name: "大二",
								grade_goal: "掌握数据结构",
								course_nodes: [
									{
										course_node_id: "year_2_course_1",
										grade_id: "year_2",
										course_or_chapter_theme: "数据结构基础",
										time_arrangement: {
											semester_scope: "上学期",
											duration: "8 周",
											pace_reason: "配合校内课程节奏",
										},
										course_goal: "掌握线性表、树和图",
										prerequisite_node_ids: [],
										chapter_nodes: [],
										core_knowledge_points: [],
										key_points: ["线性表", "树", "图"],
										difficult_points: ["图的遍历"],
										learning_sequence: ["线性表", "树", "图"],
										knowledge_relations: [],
										downstream_resource_direction_ids: [],
										acceptance_criteria: ["能完成课程项目"],
									},
								],
							},
							year_3: {
								grade_id: "year_3",
								grade_name: "大三",
								grade_goal: "完成算法强化",
								course_nodes: [],
							},
							year_4: {
								grade_id: "year_4",
								grade_name: "大四",
								grade_goal: "完成综合应用",
								course_nodes: [],
							},
						},
						knowledge_graph: {
							global_relations: [],
							critical_paths: [],
						},
						resource_generation_contract: {
							downstream_agents: [],
							resource_directions: [],
						},
						dynamic_update_contract: {
							trackable_metrics: [],
							update_triggers: [],
							adjustment_strategy: "按双周复盘调整",
						},
						current_learning_course: {
							grade_id: "year_2",
							course_node_id: "year_2_course_1",
							course_or_chapter_theme: "数据结构基础",
							course_goal: "掌握线性表、树和图",
							time_arrangement: {
								semester_scope: "上学期",
								duration: "8 周",
								pace_reason: "配合校内课程节奏",
							},
							current_focus: "线性表",
							progress_state: "in_progress",
							next_action: "继续学习树结构",
						},
					},
				},
				updated_at: "2026-06-01T12:00:00Z",
			}),
		});
		vi.stubGlobal("fetch", fetchMock);

		const result = await getMyLearningPath("token-1");

		expect(fetchMock).toHaveBeenCalledWith(
			"http://127.0.0.1:8000/api/learning-path/me",
			expect.objectContaining({
				headers: { Authorization: "Bearer token-1" },
			}),
		);
		expect(result.yearLearningPaths.year_2.schema_version).toBe(
			"learning_path.v2.course_node",
		);
		expect(
			result.yearLearningPaths.year_2.grade_plans.year_2.course_nodes[0]
				.course_or_chapter_theme,
		).toBe("数据结构基础");
		expect(result.updatedAt).toBe("2026-06-01T12:00:00Z");
	});

	it("accepts a single-grade saved learning path with all course nodes", async () => {
		const path = makeLearningPath();
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					year_learning_paths: {
						year_3: {
							...path,
							grade_plans: {
								year_3: {
									grade_id: "year_3",
									grade_name: "大三",
									grade_goal: "完成 AI Agent 学习路径",
									course_nodes: [
										path.grade_plans.year_3.course_nodes[0],
										{
											...path.grade_plans.year_3.course_nodes[0],
											course_node_id: "year_3_course_2",
											course_or_chapter_theme: "多轮对话记忆管理与 RAG 增强",
										},
										{
											...path.grade_plans.year_3.course_nodes[0],
											course_node_id: "year_3_course_3",
											course_or_chapter_theme: "生产级部署、监控与性能调优",
										},
									],
								},
							},
						},
					},
					updated_at: "2026-06-01T12:00:00Z",
				}),
			}),
		);

		const result = await getMyLearningPath("token-1");

		expect(
			result.yearLearningPaths.year_3.grade_plans.year_3.course_nodes,
		).toHaveLength(3);
	});

	it("rejects saved learning path with unsupported current progress_state", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					year_learning_paths: {
						year_2: {
							...makeLearningPath(),
							current_learning_course: {
								...makeLearningPath().current_learning_course,
								grade_id: "year_2",
								course_node_id: "year_2_course_1",
								course_or_chapter_theme: "数据结构基础",
								course_goal: "掌握线性表、树和图",
								progress_state: "not_started",
							},
						},
					},
					updated_at: "2026-06-01T12:00:00Z",
				}),
			}),
		);

		await expect(getMyLearningPath("token-1")).rejects.toThrow(
			"学习路径数据格式不正确",
		);
	});

	it("rejects legacy learning path payloads from getMyLearningPath", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn().mockResolvedValue({
				ok: true,
				json: async () => ({
					year_learning_paths: {
						year_2: {
							grade_year: "year_2",
							grade_name: "大二",
							grade_goal: "数据结构",
							courses: [],
							recommended_sequence: [],
							personalization_notes: "旧版结构",
						},
					},
					updated_at: "2026-06-01T12:00:00Z",
				}),
			}),
		);

		await expect(getMyLearningPath("token-1")).rejects.toThrow(
			"学习路径数据格式不正确",
		);
	});
});
