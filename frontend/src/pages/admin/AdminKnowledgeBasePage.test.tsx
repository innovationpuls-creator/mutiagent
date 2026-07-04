import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
	AdminKnowledgeBaseApi,
	KnowledgeBaseAgentResponse,
	KnowledgeBaseSourceResult,
	KnowledgeGapAdmin,
	KnowledgeSource,
	Textbook,
	TextbookExtensionResource,
	TextbookSectionContent,
} from "../../api/knowledgeBase";
import { AuthProvider } from "../../contexts/AuthContext";
import type { AuthUser } from "../../types/auth";
import { AdminKnowledgeBasePage } from "./AdminKnowledgeBasePage";

const adminAccount: AuthUser = {
	uid: "admin-1",
	username: "admin",
	identifier: "admin@example.com",
	role: "admin",
	school: "南山大学",
	major: "软件工程",
	class_name: "一班",
	provider: "password",
	is_active: true,
	created_at: "2026-06-02T00:00:00Z",
	last_login_at: null,
};

const source: KnowledgeSource = {
	source_id: "source-1",
	name: "官方教材来源",
	base_url: "https://example.test/books",
	status: "enabled",
	source_kind: "official",
	download_requirement: "需要可下载 PDF",
	ai_search_requirement: "只允许主站检索",
	download_status: "verified",
	parse_status: "supported",
	license_review_status: "approved",
	human_review_status: "reviewed",
};

const textbook: Textbook = {
	textbook_id: "textbook-1",
	source_id: "source-1",
	title: "Agent 开发入门",
	original_title: "Agent Development Basics",
	language: "zh",
	translated_language: "en",
	description: "面向大二项目学习 of agent 入门教材",
	tags: ["agent", "backend"],
	download_url: "https://example.test/agent.pdf",
	file_asset_url: "",
	outline: { sections: [{ section_id: "1.1", title: "理解 Agent" }] },
	ingestion_status: "completed",
	outline_review_status: "approved",
	student_availability_status: "published",
	ingestion_error_message: "",
	published_at: "2026-06-25T09:00:00Z",
	unpublished_at: null,
	archived_at: null,
};

const gap: KnowledgeGapAdmin = {
	gap_id: "gap-1",
	normalized_topic: "agent 开发",
	trigger_count: 3,
	follow_count: 1,
	latest_triggered_at: "2026-06-27T12:30:00Z",
	student_goal_summaries: ["我想学习 agent 开发"],
	status: "open",
	resolved_textbook_id: null,
	resolved_at: null,
	sources: [source],
	actions: ["find_materials"],
};

const extensionResource: TextbookExtensionResource = {
	resource_id: "resource-1",
	textbook_id: "textbook-1",
	section_id: "1.1",
	resource_type: "webpage",
	title_zh: "Agent 基础阅读",
	description_zh: "补充说明",
	render_mode: "webpage",
	url: "https://example.test/resource",
	cover_url: "",
	source_name: "官方教材来源",
	status: "published",
};

const textbookSection: TextbookSectionContent = {
	section_content_id: "section-content-1",
	textbook_id: "textbook-1",
	section_id: "1.1",
	parent_section_id: null,
	order_index: 1,
	title: "理解 Agent",
	original_title: "Understanding Agent",
	content_original:
		"An agent is a software system that perceives, acts, and responds around goals.",
	content_zh: "",
	content_char_count: 79,
};

const sourceResult: KnowledgeBaseSourceResult = {
	source_result_id: "source-result-ods-python",
	title: "Open Data Structures",
	original_title: "Open Data Structures",
	language: "en",
	source_url: "https://opendatastructures.org/ods-python.pdf",
	source_type: "pdf",
	provider_name: "Open Data Structures",
	description: "Open textbook covering data structures.",
	tags: ["数据结构"],
	parseability_score: 95,
	parseability_reason: "PDF 稳定可访问。",
	topic_summary: "覆盖数据结构核心课程。",
	is_recommended: true,
};

const queuedJob = {
	job_id: "job-1",
	textbook_id: "textbook-1",
	job_type: "agent_organize",
	status: "queued" as const,
	error_message: "",
	created_at: "2026-06-29T10:00:00Z",
	started_at: null,
	finished_at: null,
};

const completedJob = {
	...queuedJob,
	status: "completed" as const,
	started_at: "2026-06-29T10:00:01Z",
	finished_at: "2026-06-29T10:00:02Z",
};

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

function stubAuth() {
	vi.stubGlobal("localStorage", {
		getItem: vi.fn((key: string) => {
			if (key !== "mutiagent-auth") return null;
			return JSON.stringify({ token: "token-1", user: adminAccount });
		}),
		setItem: vi.fn(),
		removeItem: vi.fn(),
	});
}

function renderPage(api: AdminKnowledgeBaseApi) {
	return render(
		<MemoryRouter
			initialEntries={["/admin/knowledge-base"]}
			future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
		>
			<AuthProvider>
				<AdminKnowledgeBasePage knowledgeBaseApi={api} />
			</AuthProvider>
		</MemoryRouter>,
	);
}

describe("AdminKnowledgeBasePage", () => {
	it("renders the agent workbench and sends the message to the backend agent", async () => {
		stubAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([source]),
			listTextbooks: vi.fn().mockResolvedValue([textbook]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			listTextbookSections: vi.fn().mockResolvedValue([textbookSection]),
			runAgent: vi.fn().mockResolvedValue({
				reply_text: "找到 1 个真实教材来源。",
				selected_textbook_id: null,
				selected_source_result_id: "source-result-ods-python",
				textbook_hits: [],
				gap_hits: [],
				source_results: [sourceResult],
			}),
			confirmSourceResult: vi.fn().mockResolvedValue({
				textbook,
				job: queuedJob,
			}),
			runIngestionJob: vi.fn().mockResolvedValue(completedJob),
			organizeTextbook: vi.fn().mockResolvedValue(completedJob),
			publishTextbook: vi.fn().mockResolvedValue(textbook),
			unpublishTextbook: vi.fn().mockResolvedValue({
				...textbook,
				student_availability_status: "unpublished",
			}),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
			updateOutline: vi.fn().mockResolvedValue(textbook),
		};

		renderPage(api);

		await waitFor(() => {
			expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
		});

		const dialog = screen.getByRole("region", { name: "管理员对话工作台" });
		fireEvent.change(screen.getByLabelText("消息"), {
			target: { value: "帮我找适合大二学习 agent 开发的教材" },
		});
		fireEvent.click(screen.getByRole("button", { name: "发送" }));

		await waitFor(() => {
			expect(api.runAgent).toHaveBeenCalledWith(
				"token-1",
				"帮我找适合大二学习 agent 开发的教材",
			);
		});
		expect(screen.getAllByText("找到 1 个真实教材来源。")).toHaveLength(1);
		await waitFor(() => {
			expect(
				screen.getAllByText("Open Data Structures").length,
			).toBeGreaterThan(0);
		});
		expect(screen.getAllByText("推荐解析").length).toBeGreaterThan(0);
		expect(screen.queryByText("source-result-ods-python")).toBeNull();
		expect(screen.getByText("原始语言：en")).toBeTruthy();
		expect(screen.getByText("来源类型：PDF")).toBeTruthy();
		expect(
			screen.getByRole("link", {
				name: "https://opendatastructures.org/ods-python.pdf",
			}),
		).toBeTruthy();
		expect(screen.getByText("PDF 稳定可访问。")).toBeTruthy();
		expect(screen.queryByText("queued")).toBeNull();
		await waitFor(() => {
			expect(api.listTextbookSections).toHaveBeenCalledWith(
				"token-1",
				"textbook-1",
			);
		});
		// Enter textbook viewing mode
		fireEvent.click(screen.getAllByRole("button", { name: "查看教材" })[0]);
		expect(screen.getByText(/章节正文/)).toBeTruthy();
		expect(screen.getByDisplayValue("理解 Agent")).toBeTruthy();
		expect(
			screen.getByText(
				"An agent is a software system that perceives, acts, and responds around goals.",
			),
		).toBeTruthy();
		// Exit back to main workspace
		fireEvent.click(screen.getByRole("button", { name: "返回教材工作台" }));

		expect(
			screen.getAllByRole("button", {
				name: "确认解析 Open Data Structures",
			}),
		).toHaveLength(1);
		fireEvent.click(
			screen.getAllByRole("button", {
				name: "确认解析 Open Data Structures",
			})[0],
		);
		await waitFor(() => {
			expect(api.confirmSourceResult).toHaveBeenCalledWith(
				"token-1",
				sourceResult,
			);
		});
		await waitFor(() => {
			expect(api.runIngestionJob).toHaveBeenCalledWith("token-1", "job-1");
		});

		fireEvent.click(screen.getByRole("button", { name: "发布当前教材" }));
		await waitFor(() => {
			expect(api.publishTextbook).toHaveBeenCalledWith("token-1", "textbook-1");
		});
		expect(dialog).toBeTruthy();
	});

	it("keeps the managed textbook actions available without the removed AI creation center", async () => {
		stubAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([source]),
			listTextbooks: vi.fn().mockResolvedValue([textbook]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			listTextbookSections: vi.fn().mockResolvedValue([textbookSection]),
			runAgent: vi.fn().mockResolvedValue({
				reply_text: "当前没有更合适的教材。",
				selected_textbook_id: null,
				textbook_hits: [],
				gap_hits: [],
				source_results: [],
			}),
			confirmSourceResult: vi.fn().mockResolvedValue({
				textbook,
				job: queuedJob,
			}),
			runIngestionJob: vi.fn().mockResolvedValue(completedJob),
			organizeTextbook: vi.fn().mockResolvedValue(completedJob),
			publishTextbook: vi.fn().mockResolvedValue(textbook),
			unpublishTextbook: vi.fn().mockResolvedValue(textbook),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
			updateOutline: vi.fn().mockResolvedValue(textbook),
		};

		renderPage(api);

		await waitFor(() => {
			expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
		});

		expect(screen.queryByText("AI 教材创作中心")).toBeNull();
		expect(screen.queryByText("AI 创作教材")).toBeNull();
		expect(screen.getByText("Agent 开发入门")).toBeTruthy();
		expect(screen.getByText("来源状态")).toBeTruthy();
		expect(screen.getByText("未覆盖待办")).toBeTruthy();
	});

	it("renders live stream feedback while the backend agent works", async () => {
		stubAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([source]),
			listTextbooks: vi.fn().mockResolvedValue([textbook]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			listTextbookSections: vi.fn().mockResolvedValue([textbookSection]),
			runAgent: vi.fn().mockResolvedValue({
				reply_text: "旧接口结果",
				selected_textbook_id: null,
				textbook_hits: [],
				gap_hits: [],
				source_results: [],
			}),
			streamAgent: vi.fn(async (_token, _message, onEvent) => {
				onEvent({
					event: "started",
					message: "已收到管理员消息。",
					normalized_length: 4,
				});
				onEvent({
					event: "context_loaded",
					message: "已读取知识库现状。",
					source_count: 1,
					textbook_count: 1,
					gap_count: 1,
				});
				onEvent({
					event: "textbook_search_completed",
					message: "精确匹配完成。",
					match_count: 1,
				});
				const response: KnowledgeBaseAgentResponse = {
					reply_text: "当前最合适的主教材是《Agent 开发入门》。",
					selected_textbook_id: "textbook-1",
					selected_source_result_id: null,
					textbook_hits: [
						{
							textbook_id: "textbook-1",
							title: "Agent 开发入门",
							source_name: "官方教材来源",
							student_availability_status: "published",
							score: 90,
							reason: "标题命中。",
						},
					],
					gap_hits: [],
					source_results: [],
				};
				onEvent({
					event: "completed",
					message: "本轮已完成。",
					response,
				});
				return response;
			}),
			confirmSourceResult: vi.fn().mockResolvedValue({
				textbook,
				job: queuedJob,
			}),
			runIngestionJob: vi.fn().mockResolvedValue(completedJob),
			organizeTextbook: vi.fn().mockResolvedValue(completedJob),
			publishTextbook: vi.fn().mockResolvedValue(textbook),
			unpublishTextbook: vi.fn().mockResolvedValue(textbook),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
			updateOutline: vi.fn().mockResolvedValue(textbook),
		};

		renderPage(api);

		await waitFor(() => {
			expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
		});

		fireEvent.change(screen.getByLabelText("消息"), {
			target: { value: "数据结构" },
		});
		fireEvent.click(screen.getByRole("button", { name: "发送" }));

		await waitFor(() => {
			expect(api.streamAgent).toHaveBeenCalledWith(
				"token-1",
				"数据结构",
				expect.any(Function),
			);
		});
		expect(screen.getByText("已读取知识库现状。")).toBeTruthy();
		expect(screen.getByText("1 个来源 · 1 本教材 · 1 个待办")).toBeTruthy();
		expect(screen.getByText("匹配 1 本教材")).toBeTruthy();
		expect(screen.queryByText("已收到管理员消息。")).toBeNull();
		expect(screen.getByText("本轮已完成。")).toBeTruthy();
		expect(screen.getAllByText(/\d{2}:\d{2}:\d{2}/).length).toBeGreaterThan(0);
		expect(
			screen.getByText("当前最合适的主教材是《Agent 开发入门》。"),
		).toBeTruthy();
		expect(api.runAgent).not.toHaveBeenCalled();
	});

	it("switches to the textbook browser tab, searches and filters textbooks", async () => {
		stubAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([source]),
			listTextbooks: vi.fn().mockResolvedValue([
				textbook,
				{
					...textbook,
					textbook_id: "textbook-2",
					title: "Python 编程基础",
					original_title: "Python Programming Basics",
					student_availability_status: "draft",
				},
			]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			listTextbookSections: vi.fn().mockResolvedValue([textbookSection]),
			runAgent: vi.fn().mockResolvedValue({
				reply_text: "",
				selected_textbook_id: null,
				textbook_hits: [],
				gap_hits: [],
				source_results: [],
			}),
			confirmSourceResult: vi.fn().mockResolvedValue({
				textbook,
				job: queuedJob,
			}),
			runIngestionJob: vi.fn().mockResolvedValue(completedJob),
			organizeTextbook: vi.fn().mockResolvedValue(completedJob),
			publishTextbook: vi.fn().mockResolvedValue(textbook),
			unpublishTextbook: vi.fn().mockResolvedValue(textbook),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
			updateOutline: vi.fn().mockResolvedValue(textbook),
		};

		renderPage(api);

		await waitFor(() => {
			expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
		});

		// Check tabs are rendered
		const chatTab = screen.getByRole("tab", { name: "💬 AI 智能助理" });
		const browserTab = screen.getByRole("tab", { name: "📚 教材库浏览" });
		expect(chatTab).toBeTruthy();
		expect(browserTab).toBeTruthy();

		// Click the browser tab
		fireEvent.click(browserTab);

		// Verify textbook browser elements are rendered
		await waitFor(() => {
			expect(
				screen.getByPlaceholderText("搜索教材标题、英文名或描述..."),
			).toBeTruthy();
		});
		expect(
			screen.getByRole("button", { name: "选中教材《Agent 开发入门》" }),
		).toBeTruthy();
		expect(
			screen.getByRole("button", { name: "选中教材《Python 编程基础》" }),
		).toBeTruthy();

		// Test search filter
		const searchInput = screen.getByPlaceholderText(
			"搜索教材标题、英文名或描述...",
		);
		fireEvent.change(searchInput, { target: { value: "Python" } });
		expect(
			screen.queryByRole("button", { name: "选中教材《Agent 开发入门》" }),
		).toBeNull();
		expect(
			screen.getByRole("button", { name: "选中教材《Python 编程基础》" }),
		).toBeTruthy();

		// Test status filter
		fireEvent.change(searchInput, { target: { value: "" } }); // reset search
		const statusSelect = screen.getByLabelText("状态过滤");
		fireEvent.change(statusSelect, { target: { value: "published" } });
		expect(
			screen.getByRole("button", { name: "选中教材《Agent 开发入门》" }),
		).toBeTruthy();
		expect(
			screen.queryByRole("button", { name: "选中教材《Python 编程基础》" }),
		).toBeNull(); // textbook-2 is draft

		// Click back to chat tab
		fireEvent.click(chatTab);
		await waitFor(() => {
			expect(
				screen.getByRole("region", { name: "管理员对话工作台" }),
			).toBeTruthy();
		});
	});
});
