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
	KnowledgeBaseSourceResult,
	KnowledgeGapAdmin,
	KnowledgeSource,
	Textbook,
	TextbookExtensionResource,
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
	description: "面向大二项目学习的 agent 入门教材",
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
				job: {
					job_id: "job-1",
					textbook_id: "textbook-1",
					job_type: "agent_organize",
					status: "queued",
					error_message: "",
					created_at: "2026-06-29T10:00:00Z",
					started_at: null,
					finished_at: null,
				},
			}),
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
		expect(screen.queryByText("https://example.test/books")).toBeNull();
		expect(screen.queryByText("source-result-ods-python")).toBeNull();
		expect(
			screen.queryByText("https://opendatastructures.org/ods-python.pdf"),
		).toBeNull();
		expect(screen.queryByText("PDF 稳定可访问。")).toBeNull();
		expect(screen.queryByText("queued")).toBeNull();
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
			runAgent: vi.fn().mockResolvedValue({
				reply_text: "当前没有更合适的教材。",
				selected_textbook_id: null,
				textbook_hits: [],
				gap_hits: [],
				source_results: [],
			}),
			confirmSourceResult: vi.fn().mockResolvedValue({
				textbook,
				job: {
					job_id: "job-1",
					textbook_id: "textbook-1",
					job_type: "agent_organize",
					status: "queued",
					error_message: "",
					created_at: "2026-06-29T10:00:00Z",
					started_at: null,
					finished_at: null,
				},
			}),
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
});
