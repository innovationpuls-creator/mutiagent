import type { Textbook, TextbookSectionContent } from "../../api/knowledgeBase";

interface AdminTextbookInspectorProps {
	selectedTextbook: Textbook | null;
	selectedTextbookSections: TextbookSectionContent[];
	isBusy: boolean;
	onOrganizeSelected?: () => Promise<void>;
	onPublishSelected: () => Promise<void>;
	onUnpublishSelected: () => Promise<void>;
	onDeleteSelected: () => Promise<void>;
	onEditSelectedOutline: () => void;
}

function formatStatus(value: string) {
	switch (value) {
		case "published":
			return "已发布";
		case "draft":
			return "草稿";
		case "unpublished":
			return "已下架";
		case "archived":
			return "已归档";
		default:
			return value;
	}
}

function formatIngestionStatus(value: string) {
	switch (value) {
		case "not_started":
			return "待解析";
		case "processing":
			return "解析中";
		case "failed":
			return "解析失败";
		case "ready_for_outline_review":
			return "待检查大纲";
		case "completed":
			return "已完成";
		default:
			return "待解析";
	}
}

function formatOutlineStatus(value: string) {
	return value === "approved" ? "已确认" : "待确认";
}

function formatOutlineSummary(outline: unknown) {
	if (!outline || typeof outline !== "object") return "暂无大纲";
	const chapters = (outline as { chapters?: unknown }).chapters;
	if (Array.isArray(chapters)) {
		const sectionCount = chapters.reduce((total, chapter) => {
			if (!chapter || typeof chapter !== "object") return total;
			const sections = (chapter as { sections?: unknown }).sections;
			return total + (Array.isArray(sections) ? sections.length : 0);
		}, 0);
		return `${chapters.length} 章 · ${sectionCount} 节`;
	}
	const sections = (outline as { sections?: unknown }).sections;
	if (Array.isArray(sections)) {
		return `${sections.length} 节`;
	}
	return "暂无大纲";
}

export function AdminTextbookInspector({
	selectedTextbook,
	selectedTextbookSections,
	isBusy,
	onPublishSelected,
	onUnpublishSelected,
	onDeleteSelected,
	onEditSelectedOutline,
}: AdminTextbookInspectorProps) {
	if (!selectedTextbook) {
		return (
			<div className="admin-kb-empty-details">
				<p>未选中任何教材。</p>
				<p>请在左侧列表中选择或通过对话引入新教材大纲。</p>
			</div>
		);
	}

	return (
		<div className="admin-kb-selected-textbook">
			<div className="admin-kb-textbook-header">
				<h4>{selectedTextbook.title}</h4>
				{selectedTextbook.original_title && (
					<small className="admin-kb-original-title">
						原名：{selectedTextbook.original_title}
					</small>
				)}
			</div>
			<p className="admin-kb-textbook-desc">
				{selectedTextbook.description || "暂无教材简介描述。"}
			</p>

			<div className="admin-kb-detail-grid">
				<div className="detail-status-item">
					<span className="label">整理</span>
					<strong className="value">
						{formatIngestionStatus(selectedTextbook.ingestion_status)}
					</strong>
				</div>
				<div className="detail-status-item">
					<span className="label">大纲</span>
					<strong className="value">
						{formatOutlineStatus(selectedTextbook.outline_review_status)}
					</strong>
				</div>
				<div className="detail-status-item">
					<span className="label">发布</span>
					<strong className="value">
						{formatStatus(selectedTextbook.student_availability_status)}
					</strong>
				</div>
			</div>

			<div className="admin-kb-detail-actions">
				<button
					type="button"
					className="admin-primary-action"
					disabled={isBusy}
					onClick={() => void onPublishSelected()}
				>
					<span>发布当前教材</span>
				</button>
				<button
					type="button"
					className="admin-secondary-action"
					disabled={isBusy}
					onClick={() => void onUnpublishSelected()}
				>
					<span>下架</span>
				</button>
				<button
					type="button"
					className="admin-secondary-action"
					disabled={isBusy}
					onClick={onEditSelectedOutline}
				>
					<span>查看教材</span>
				</button>
				<button
					type="button"
					className="admin-danger-action"
					disabled={isBusy}
					onClick={() => void onDeleteSelected()}
				>
					<span>删除</span>
				</button>
			</div>

			{selectedTextbook.outline && (
				<div className="admin-kb-outline-structure">
					<h5>大纲结构</h5>
					<p className="outline-summary">
						{formatOutlineSummary(selectedTextbook.outline)}
					</p>
				</div>
			)}
		</div>
	);
}
