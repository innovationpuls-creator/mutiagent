import { useReducedMotion } from "framer-motion";
import { ArrowUpRight, Leaf, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import type {
	GrowthReport,
	ReportAction,
	ReportEvidence,
	ReportInsight,
	ReportStage,
} from "../../api/growthReport";
import "./growth-report.css";

const STAGES: Record<ReportStage, string> = {
	collecting: "正在整理学习记录",
	analyzing: "正在分析测验表现",
	writing: "正在生成报告",
};

function EvidenceDetails({
	ids,
	evidence,
}: {
	ids: string[];
	evidence: ReportEvidence[];
}) {
	const sources = evidence.filter((item) => ids.includes(item.id));
	return (
		<details className="growth-report-evidence">
			<summary>查看依据 · {sources.length}</summary>
			{sources.map((item) => (
				<div key={item.id}>
					<strong>{item.title}</strong>
					<p>{item.detail}</p>
				</div>
			))}
		</details>
	);
}

function InsightColumn({
	title,
	items,
	evidence,
	empty,
}: {
	title: string;
	items: ReportInsight[];
	evidence: ReportEvidence[];
	empty: string;
}) {
	return (
		<section className="growth-report-column">
			<h3>{title}</h3>
			{items.length ? (
				items.map((item) => (
					<article key={`${item.title}-${item.evidence_ids.join()}`}>
						<h4>{item.title}</h4>
						<p>{item.body}</p>
						<EvidenceDetails ids={item.evidence_ids} evidence={evidence} />
					</article>
				))
			) : (
				<p className="growth-report-muted">{empty}</p>
			)}
		</section>
	);
}

function ActionItem({
	action,
	index,
	evidence,
}: {
	action: ReportAction;
	index: number;
	evidence: ReportEvidence[];
}) {
	const navigate = useNavigate();
	return (
		<article className="growth-report-action">
			<span className="growth-report-number" aria-hidden="true">
				{String(index + 1).padStart(2, "0")}
			</span>
			<div>
				<h4>{action.title}</h4>
				<p>{action.body}</p>
				<p className="growth-report-check">
					<span>完成标准</span>
					{action.check}
				</p>
				<EvidenceDetails ids={action.evidence_ids} evidence={evidence} />
				{action.course_id && (
					<button
						className="growth-report-link"
						type="button"
						onClick={() =>
							navigate(`/leaf/${encodeURIComponent(action.course_id ?? "")}`)
						}
					>
						前往对应课程 <ArrowUpRight size={16} aria-hidden="true" />
					</button>
				)}
			</div>
		</article>
	);
}

function ReportStats({ report }: { report: GrowthReport }) {
	return (
		<dl className="growth-report-stats">
			<div>
				<dt>已通关章节</dt>
				<dd>
					{report.stats.passed_chapters}
					<span>章</span>
				</dd>
			</div>
			<div>
				<dt>参与测验章节</dt>
				<dd>
					{report.stats.tested_chapters}
					<span>章</span>
				</dd>
			</div>
			<div>
				<dt>累计作答</dt>
				<dd>
					{report.stats.attempts}
					<span>次</span>
				</dd>
			</div>
		</dl>
	);
}

function ReportBody({ report }: { report: GrowthReport }) {
	return (
		<>
			<p className="growth-report-overview">{report.overview}</p>
			<ReportStats report={report} />
			<div className="growth-report-insights">
				<InsightColumn
					title="已表现出的优势"
					items={report.strengths}
					evidence={report.evidence}
					empty={
						report.stats.attempts
							? "现有记录还不足以归纳稳定优势，继续通过练习积累证据。"
							: "尚无测验记录，学习表现待验证。"
					}
				/>
				<InsightColumn
					title="值得巩固的内容"
					items={report.improvements}
					evidence={report.evidence}
					empty="当前记录没有足够依据指出具体薄弱点。"
				/>
			</div>
			<section className="growth-report-actions">
				<h3>下一步，继续生长</h3>
				{report.actions.length ? (
					report.actions.map((action, index) => (
						<ActionItem
							key={`${action.title}-${action.evidence_ids.join()}`}
							action={action}
							index={index}
							evidence={report.evidence}
						/>
					))
				) : (
					<p className="growth-report-muted">
						先完善学习画像与路径，再开始课程学习。
					</p>
				)}
			</section>
			<details className="growth-report-coverage">
				<summary>数据范围与统计口径</summary>
				<p>{report.coverage}</p>
				<p>
					通关章节依据章节通关记录；参与测验章节按课程与章节去重；累计作答包含重复尝试。
				</p>
			</details>
		</>
	);
}

interface ReportPanelProps {
	report: GrowthReport | null;
	stage: ReportStage | null;
	error: string | null;
	onGenerate: () => void;
}

function ReportHeader({
	report,
	stage,
	onGenerate,
}: Omit<ReportPanelProps, "error">) {
	return (
		<header className="growth-report-header">
			<div>
				<span className="growth-report-eyebrow">
					<Leaf size={16} aria-hidden="true" /> 每一步，都在生长
				</span>
				<h2>AI 成长报告</h2>
				{report && (
					<p className="growth-report-muted">
						截至{" "}
						{new Date(report.generated_at).toLocaleString("zh-CN", {
							hour12: false,
						})}{" "}
						· 累计学习回顾
					</p>
				)}
			</div>
			{report && (
				<button
					type="button"
					className="growth-report-link"
					disabled={!!stage}
					onClick={onGenerate}
				>
					<RotateCcw size={16} aria-hidden="true" /> 重新生成
				</button>
			)}
		</header>
	);
}

function ReportFeedback({
	stage,
	error,
	onGenerate,
}: Omit<ReportPanelProps, "report">) {
	return (
		<>
			{stage && (
				<div role="status" className="growth-report-status">
					<Leaf className="growth-report-breath" size={24} aria-hidden="true" />
					<div>
						<p>{STAGES[stage]}</p>
						<span>将学习足迹整理成一份清晰的回顾</span>
					</div>
				</div>
			)}
			{error && (
				<div role="alert" className="growth-report-error">
					<p>{error}</p>
					<button
						className="growth-report-link"
						type="button"
						onClick={onGenerate}
						disabled={!!stage}
					>
						重试
					</button>
				</div>
			)}
		</>
	);
}

export function GrowthReportPanel({
	report,
	stage,
	error,
	onGenerate,
}: ReportPanelProps) {
	const panel = useRef<HTMLElement>(null);
	const reduceMotion = useReducedMotion();
	useEffect(() => {
		if (stage === "collecting") {
			panel.current?.scrollIntoView({
				behavior: reduceMotion ? "instant" : "smooth",
				block: "start",
			});
		}
	}, [stage, reduceMotion]);
	if (!report && !stage && !error) return null;
	return (
		<section
			className="growth-report"
			ref={panel}
			id="growth-report"
			aria-label="AI 成长报告"
		>
			<ReportHeader report={report} stage={stage} onGenerate={onGenerate} />
			<ReportFeedback stage={stage} error={error} onGenerate={onGenerate} />
			{report ? (
				<ReportBody report={report} />
			) : (
				stage && (
					<div className="growth-report-skeleton" aria-hidden="true">
						<i />
						<i />
						<i />
						<i />
					</div>
				)
			)}
		</section>
	);
}
