import {
	cleanup,
	fireEvent,
	render,
	screen,
	waitFor,
	within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type {
	AdminKnowledgeBaseApi,
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

const admittedSource: KnowledgeSource = {
	source_id: "source-admitted",
	name: "已准入来源",
	base_url: "https://example.test/admitted",
	status: "enabled",
	source_kind: "official",
	download_requirement: "需要可下载 PDF",
	ai_search_requirement: "只允许主站检索",
	download_status: "verified",
	parse_status: "supported",
	license_review_status: "approved",
	human_review_status: "reviewed",
};

const blockedSource: KnowledgeSource = {
	source_id: "source-blocked",
	name: "待审来源",
	base_url: "https://example.test/blocked",
	status: "disabled",
	source_kind: "website",
	download_requirement: "需要人工确认下载入口",
	ai_search_requirement: "未开放 Agent 检索",
	download_status: "unverified",
	parse_status: "failed",
	license_review_status: "unreviewed",
	human_review_status: "unreviewed",
};

const draftTextbook: Textbook = {
	textbook_id: "textbook-draft",
	source_id: "source-admitted",
	title: "线性代数入门",
	original_title: "Linear Algebra Basics",
	language: "en",
	translated_language: "zh",
	description: "矩阵与向量空间",
	tags: ["math"],
	download_url: "https://example.test/linear.pdf",
	file_asset_url: "",
	outline: { sections: [{ section_id: "1.1", title: "矩阵乘法" }] },
	ingestion_status: "ready_for_outline_review",
	outline_review_status: "unreviewed",
	student_availability_status: "draft",
	ingestion_error_message: "",
	published_at: null,
	unpublished_at: null,
	archived_at: null,
};

const publishedTextbook: Textbook = {
	...draftTextbook,
	textbook_id: "textbook-published",
	title: "概率论基础",
	ingestion_status: "completed",
	outline_review_status: "approved",
	student_availability_status: "published",
	published_at: "2026-06-25T09:00:00Z",
};

const gap: KnowledgeGapAdmin = {
	gap_id: "gap-linear",
	normalized_topic: "矩阵分解",
	trigger_count: 7,
	follow_count: 3,
	latest_triggered_at: "2026-06-27T12:30:00Z",
	student_goal_summaries: ["考研复习线性代数", "项目中需要理解推荐算法"],
	status: "open",
	resolved_textbook_id: null,
	resolved_at: null,
	sources: [blockedSource],
	actions: ["find_materials", "upload"],
};

const extensionResource: TextbookExtensionResource = {
	resource_id: "resource-linear",
	textbook_id: "textbook-draft",
	section_id: "1.1",
	resource_type: "webpage",
	title_zh: "矩阵乘法扩展阅读",
	description_zh: "补充例题",
	render_mode: "webpage",
	url: "https://example.test/linear-extra",
	cover_url: "",
	source_name: "已准入来源",
	status: "published",
};

afterEach(() => {
	cleanup();
	vi.unstubAllGlobals();
});

function stubStoredAuth() {
	vi.stubGlobal("localStorage", {
		getItem: vi.fn((key: string) => {
			if (key !== "mutiagent-auth") return null;
			return JSON.stringify({
				token: "token-1",
				user: adminAccount,
			});
		}),
		setItem: vi.fn(),
		removeItem: vi.fn(),
	});
}

function renderKnowledgeBasePage(api: AdminKnowledgeBaseApi) {
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
	it("renders sources, textbooks, gaps and extension resources", async () => {
		stubStoredAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([admittedSource, blockedSource]),
			listTextbooks: vi
				.fn()
				.mockResolvedValue([draftTextbook, publishedTextbook]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			findMaterials: vi.fn().mockResolvedValue({
				gap: { ...gap, status: "material_searching", sources: [blockedSource] },
				sources: [blockedSource],
			}),
			uploadGapMaterials: vi.fn().mockResolvedValue({
				gap: {
					...gap,
					status: "resolved",
					resolved_textbook_id: "textbook-draft",
				},
				textbook: draftTextbook,
			}),
			publishTextbook: vi.fn().mockResolvedValue({
				...draftTextbook,
				student_availability_status: "published",
			}),
			unpublishTextbook: vi.fn().mockResolvedValue({
				...publishedTextbook,
				student_availability_status: "unpublished",
				unpublished_at: "2026-06-28T09:00:00Z",
			}),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
		};

		renderKnowledgeBasePage(api);

		await waitFor(() => {
			expect(screen.getByRole("heading", { name: "知识库" })).toBeTruthy();
		});

		expect(api.listSources).toHaveBeenCalledWith("token-1");
		expect(api.listTextbooks).toHaveBeenCalledWith("token-1");
		expect(api.listGaps).toHaveBeenCalledWith("token-1");
		await waitFor(() => {
			expect(api.listExtensionResources).toHaveBeenCalledWith(
				"token-1",
				"textbook-draft",
			);
		});

		const sourceSection = screen.getByRole("region", { name: "来源清单" });
		expect(within(sourceSection).getByText("已准入来源")).toBeTruthy();
		expect(within(sourceSection).getByText("下载：已验证")).toBeTruthy();
		expect(within(sourceSection).getByText("解析：已支持")).toBeTruthy();
		expect(within(sourceSection).getByText("许可审查：已通过")).toBeTruthy();
		expect(within(sourceSection).getByText("人工审查：已复核")).toBeTruthy();
		expect(within(sourceSection).getByText("待审来源")).toBeTruthy();
		expect(
			within(sourceSection).getByText(
				"缺少准入项：来源启用、下载验证、解析支持、许可通过、人工复核",
			),
		).toBeTruthy();

		const textbookSection = screen.getByRole("region", { name: "教材列表" });
		expect(within(textbookSection).getByText("线性代数入门")).toBeTruthy();
		expect(within(textbookSection).getByText("整理：待校对大纲")).toBeTruthy();
		expect(within(textbookSection).getByText("校对：未校对")).toBeTruthy();
		expect(within(textbookSection).getByText("学生可用：草稿")).toBeTruthy();

		const gapSection = screen.getByRole("region", { name: "未覆盖待办" });
		expect(within(gapSection).getByText("矩阵分解")).toBeTruthy();
		expect(within(gapSection).getByText("触发次数：7")).toBeTruthy();
		expect(within(gapSection).getByText("关注人数：3")).toBeTruthy();
		expect(within(gapSection).getByText(/最近触发：2026/)).toBeTruthy();
		expect(within(gapSection).getByText("考研复习线性代数")).toBeTruthy();
		expect(within(gapSection).getByText("项目中需要理解推荐算法")).toBeTruthy();
		expect(
			within(gapSection).getByRole("button", { name: "一键找素材 矩阵分解" }),
		).toBeTruthy();
		expect(
			within(gapSection).getByRole("button", { name: "自行上传 矩阵分解" }),
		).toBeTruthy();

		const extensionSection = screen.getByRole("region", {
			name: "扩展资料绑定",
		});
		expect(within(extensionSection).getByText("矩阵乘法扩展阅读")).toBeTruthy();

		fireEvent.click(
			within(gapSection).getByRole("button", { name: "一键找素材 矩阵分解" }),
		);
		await waitFor(() => {
			expect(api.findMaterials).toHaveBeenCalledWith("token-1", "gap-linear");
		});

		fireEvent.click(
			within(gapSection).getByRole("button", { name: "自行上传 矩阵分解" }),
		);
		await waitFor(() => {
			expect(api.uploadGapMaterials).toHaveBeenCalledWith(
				"token-1",
				"gap-linear",
				expect.objectContaining({
					textbook: expect.objectContaining({
						textbook_id: "upload-gap-linear",
						title: "矩阵分解补充教材",
					}),
				}),
			);
		});
	});

	it("shows extension gap count on publish and follows textbook lifecycle actions", async () => {
		stubStoredAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([admittedSource]),
			listTextbooks: vi
				.fn()
				.mockResolvedValue([draftTextbook, publishedTextbook]),
			listGaps: vi.fn().mockResolvedValue([gap]),
			listExtensionResources: vi.fn().mockResolvedValue([extensionResource]),
			findMaterials: vi.fn(),
			uploadGapMaterials: vi.fn(),
			publishTextbook: vi.fn().mockResolvedValue({
				...draftTextbook,
				student_availability_status: "published",
				published_at: "2026-06-28T09:00:00Z",
			}),
			unpublishTextbook: vi.fn().mockResolvedValue({
				...publishedTextbook,
				student_availability_status: "unpublished",
				unpublished_at: "2026-06-28T10:00:00Z",
			}),
			deleteTextbook: vi.fn().mockResolvedValue(undefined),
		};

		renderKnowledgeBasePage(api);

		const textbookSection = await screen.findByRole("region", {
			name: "教材列表",
		});

		fireEvent.click(
			within(textbookSection).getByRole("button", {
				name: "发布 线性代数入门 未覆盖扩展资料 1 项",
			}),
		);
		await waitFor(() => {
			expect(api.publishTextbook).toHaveBeenCalledWith(
				"token-1",
				"textbook-draft",
			);
		});

		fireEvent.click(
			within(textbookSection).getByRole("button", { name: "下架 概率论基础" }),
		);
		await waitFor(() => {
			expect(api.unpublishTextbook).toHaveBeenCalledWith(
				"token-1",
				"textbook-published",
			);
		});

		fireEvent.click(
			within(textbookSection).getByRole("button", {
				name: "删除 线性代数入门",
			}),
		);
		await waitFor(() => {
			expect(api.deleteTextbook).toHaveBeenCalledWith(
				"token-1",
				"textbook-draft",
			);
		});

		expect(
			screen.getByText("删除草稿：未绑定学生时移除教材、扩展资料和整理任务。"),
		).toBeTruthy();
		expect(
			screen.getByText("删除已发布、已下架或已绑定教材：保留记录并归档。"),
		).toBeTruthy();
		expect(screen.getByText("下架仅适用于已发布教材。")).toBeTruthy();
	});

	it("renders outline editor takeover and allows outline updating and AI outline generation", async () => {
		stubStoredAuth();
		const api: AdminKnowledgeBaseApi = {
			listSources: vi.fn().mockResolvedValue([admittedSource]),
			listTextbooks: vi.fn().mockResolvedValue([draftTextbook]),
			listGaps: vi.fn().mockResolvedValue([]),
			listExtensionResources: vi.fn().mockResolvedValue([]),
			findMaterials: vi.fn(),
			uploadGapMaterials: vi.fn(),
			publishTextbook: vi.fn(),
			unpublishTextbook: vi.fn(),
			deleteTextbook: vi.fn(),
			generateOutline: vi.fn().mockResolvedValue({
				...draftTextbook,
				title: "AI 生成教材大纲",
				outline: {
					chapters: [
						{
							chapter_number: 1,
							title: "第1章 AI协同入门",
							sections: [
								{ section_id: "1.1", title: "1.1 协同理念" },
								{ section_id: "1.2", title: "1.2 协同操作" },
								{ section_id: "1.3", title: "1.3 协同验证" },
							],
						},
					],
				},
			}),
			updateOutline: vi.fn().mockResolvedValue(draftTextbook),
			generateContent: vi.fn().mockResolvedValue({}),
			getGenerationProgress: vi.fn().mockResolvedValue({
				progress_percentage: 50.0,
				status: "running",
				current_section_title: "1.1 协同理念",
			}),
		};

		renderKnowledgeBasePage(api);

		const textbookSection = await screen.findByRole("region", {
			name: "教材列表",
		});

		// 1. Click Edit Outline button to take over
		fireEvent.click(
			within(textbookSection).getByRole("button", {
				name: "编辑大纲 线性代数入门",
			}),
		);

		await waitFor(() => {
			expect(
				screen.getByText("《线性代数入门》大纲微调与正文生成"),
			).toBeTruthy();
		});

		// 2. Add a new chapter
		fireEvent.click(screen.getByRole("button", { name: "添加新章节" }));
		expect(screen.getByDisplayValue("第2章 新增章节")).toBeTruthy();

		// 3. Test AI Copilot Outline Generation
		const copilotTextarea = screen.getByPlaceholderText(/例如：生成一份/);
		fireEvent.change(copilotTextarea, { target: { value: "生成AI协同入门" } });
		fireEvent.click(screen.getByRole("button", { name: "AI 协同创作大纲" }));

		await waitFor(() => {
			expect(api.generateOutline).toHaveBeenCalledWith(
				"token-1",
				"生成AI协同入门",
				[],
			);
			expect(
				screen.getByText("《AI 生成教材大纲》大纲微调与正文生成"),
			).toBeTruthy();
		});

		// 4. Test Trigger AIGC Content Generation
		fireEvent.click(
			screen.getByRole("button", { name: "一键异步生成教材正文 (AIGC)" }),
		);
		await waitFor(() => {
			expect(api.generateContent).toHaveBeenCalledWith(
				"token-1",
				"textbook-draft",
			);
			expect(screen.getByText("正在生成: 1.1 协同理念 (50%)")).toBeTruthy();
		});
	});
});
