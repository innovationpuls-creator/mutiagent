import type { components } from "../../types/api";
import type { ChatMessage, SessionMessage } from "../../types/chat";

type KnowledgeGapRead = components["schemas"]["KnowledgeGapRead"];
type KnowledgeGapFollowRead = components["schemas"]["KnowledgeGapFollowRead"];
type KnowledgeGapNoticeRead = components["schemas"]["KnowledgeGapNoticeRead"];
type KnowledgeSourceRead = components["schemas"]["KnowledgeSourceRead"];
type TextbookExtensionResourceRead =
	components["schemas"]["TextbookExtensionResourceRead"];
type TextbookRead = components["schemas"]["TextbookRead"];
type TextbookSectionContentFixture =
	components["schemas"]["TextbookSectionContentCreateRequest"] & {
		textbook_id: string;
	};

const createdAt = "2026-06-27T10:00:00Z";

export const enabledKnowledgeSource: KnowledgeSourceRead = {
	source_id: "source-enabled-api",
	name: "开放教材来源",
	base_url: "https://example.edu/open",
	status: "enabled",
	source_kind: "open_textbook",
	download_requirement: "direct",
	ai_search_requirement: "allowed",
	download_status: "verified",
	parse_status: "supported",
	license_review_status: "approved",
	human_review_status: "reviewed",
};

export const unpublishedKnowledgeTextbook: TextbookRead = {
	textbook_id: "textbook-draft-api",
	source_id: enabledKnowledgeSource.source_id,
	title: "概率论草稿",
	original_title: "Probability Draft",
	language: "en",
	translated_language: "zh",
	description: "覆盖概率论基础，尚未发布。",
	tags: ["概率论"],
	download_url: "https://example.edu/probability.pdf",
	file_asset_url: "/assets/probability.pdf",
	outline: { sections: [{ section_id: "1", title: "随机事件" }] },
	ingestion_status: "ready_for_outline_review",
	outline_review_status: "unreviewed",
	student_availability_status: "draft",
	ingestion_error_message: "",
	published_at: null,
	unpublished_at: null,
	archived_at: null,
};

export const publishedKnowledgeTextbook: TextbookRead = {
	...unpublishedKnowledgeTextbook,
	textbook_id: "textbook-linear-api",
	title: "线性代数",
	description: "覆盖矩阵、向量空间和概率论衔接。",
	tags: ["矩阵", "概率论"],
	ingestion_status: "completed",
	outline_review_status: "approved",
	student_availability_status: "published",
	published_at: createdAt,
};

export const archivedKnowledgeTextbook: TextbookRead = {
	...publishedKnowledgeTextbook,
	textbook_id: "textbook-archived-api",
	title: "已归档教材",
	student_availability_status: "archived",
	archived_at: "2026-06-28T10:00:00Z",
};

export const continuousKnowledgeSections: TextbookSectionContentFixture[] = [
	{
		section_content_id: "section-content-1",
		textbook_id: publishedKnowledgeTextbook.textbook_id,
		section_id: "1.1",
		parent_section_id: "1",
		order_index: 1,
		title: "矩阵乘法",
		original_title: "Matrix Multiplication",
		content_original: "Matrix multiplication original content.",
		content_zh: "矩阵乘法正文。",
		content_char_count: 7,
	},
	{
		section_content_id: "section-content-2",
		textbook_id: publishedKnowledgeTextbook.textbook_id,
		section_id: "1.2",
		parent_section_id: "1",
		order_index: 2,
		title: "向量空间",
		original_title: "Vector Spaces",
		content_original: "Vector spaces original content.",
		content_zh: "向量空间正文。",
		content_char_count: 7,
	},
];

export const overLimitKnowledgeSections: TextbookSectionContentFixture[] = [
	{
		...continuousKnowledgeSections[0],
		section_content_id: "section-content-over-limit-1",
		section_id: "2.1",
		order_index: 10,
		content_zh: "概".repeat(4100),
		content_char_count: 4100,
	},
	{
		...continuousKnowledgeSections[1],
		section_content_id: "section-content-over-limit-2",
		section_id: "2.2",
		order_index: 11,
		content_zh: "率".repeat(4100),
		content_char_count: 4100,
	},
];

export const uncoveredKnowledgeGap: KnowledgeGapRead = {
	gap_id: "gap-api",
	normalized_topic: "概率论",
	trigger_count: 1,
	follow_count: 0,
	latest_triggered_at: createdAt,
	student_goal_summaries: ["希望学习概率基础"],
	status: "open",
	resolved_textbook_id: null,
	resolved_at: null,
};

export const followedKnowledgeGap: KnowledgeGapFollowRead = {
	follow_id: "gap-follow-followed-student",
	gap_id: uncoveredKnowledgeGap.gap_id,
	user_uid: "user-followed-gap",
	created_at: createdAt,
};

export const resolvedKnowledgeGapNotice: KnowledgeGapNoticeRead = {
	notice_id: "gap-notice-api",
	gap_id: uncoveredKnowledgeGap.gap_id,
	user_uid: "user-1",
	notice_type: "knowledge_gap_resolved",
	title: "概率论 已补齐",
	body: "知识库已发布覆盖该主题的教材。",
	action_label: "重新生成学习路径",
	action_payload: {
		action: "regenerate_learning_path_intake",
		learning_topic: uncoveredKnowledgeGap.normalized_topic,
		textbook_id: publishedKnowledgeTextbook.textbook_id,
	},
	read_at: null,
	created_at: "2026-06-28T10:00:00Z",
};

export const extensionResourcesThree: TextbookExtensionResourceRead[] = [
	"reader",
	"video",
	"webpage",
].map((renderMode, index) => ({
	resource_id: `resource-${index + 1}`,
	textbook_id: publishedKnowledgeTextbook.textbook_id,
	section_id: continuousKnowledgeSections[0].section_id,
	resource_type: "supplement",
	title_zh: `扩展资料 ${index + 1}`,
	description_zh: "用于补充当前章节。",
	render_mode: renderMode as TextbookExtensionResourceRead["render_mode"],
	url: `https://example.edu/resource-${index + 1}`,
	cover_url: "",
	source_name: "开放教材来源",
	status: "active",
}));

export const extensionResourcesFour: TextbookExtensionResourceRead[] = [
	...extensionResourcesThree,
	{
		...extensionResourcesThree[0],
		resource_id: "resource-4",
		title_zh: "扩展资料 4",
		url: "https://example.edu/resource-4",
	},
];

export const profileWithKnowledgeGap: SessionMessage = {
	type: "collecting",
	stage: "goal_constraint",
	question_mode: "none",
	confirmed_info: {
		current_grade: "大三",
		major: "软件工程",
		learning_stage: "有基础",
		has_clear_goal: "大致有方向",
		learning_method_preference: "项目驱动学习",
		learning_pace_preference: "按项目里程碑推进",
		content_preference: ["代码实践"],
		need_guidance: "需要轻量提醒",
		knowledge_foundation: "软件工程基础",
		strengths: "工程实现",
		weaknesses: "概率基础薄弱",
		experience: "做过课程项目",
		short_term_goal: "补齐概率论",
		long_term_goal: "形成 AI 应用开发能力",
		weekly_available_time: "每周 8 小时",
		constraints: "时间有限",
	},
	defaulted_fields: [],
	question_md: "当前知识库还没有覆盖概率论。",
	question_box: {
		question: "",
		options: [],
	},
	text: "当前知识库还没有覆盖概率论。你可以关注该主题，补齐后会收到提醒。",
	gap_id: uncoveredKnowledgeGap.gap_id,
};

export const knowledgeGapProfileSessionCache = {
	userUid: "user-1",
	savedAt: 1000,
	messages: [
		{
			id: "knowledge-gap-user-message",
			role: "user",
			content: "我想学概率论",
			status: "completed",
			timestamp: 1000,
		},
		{
			id: "knowledge-gap-assistant-message",
			role: "assistant",
			content: profileWithKnowledgeGap.text,
			status: "completed",
			timestamp: 1001,
			sessionMessage: {
				...profileWithKnowledgeGap,
				type: "collecting",
			},
			runTrace: [],
			activeStepId: null,
		},
	],
} satisfies {
	userUid: string;
	savedAt: number;
	messages: ChatMessage[];
};
