import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { adminDataApi } from "../../api/adminData";
import { adminProgramApi } from "../../api/adminProgram";
import type {
	GraphEdge,
	GraphNode,
} from "../../components/graph/OrganicCanvas";
import { OrganicCanvas } from "../../components/graph/OrganicCanvas";
import { useAuth } from "../../contexts/AuthContext";
import type { BranchCourseNode } from "../../types/branch";
import { ProgramDetailDrawer } from "./components/ProgramDetailDrawer";
import type { ProgramScope } from "./components/ProgramScopePanel";
import { ProgramScopePanel } from "./components/ProgramScopePanel";
import { ProgramTreeTable } from "./components/ProgramTreeTable";
import type { SemesterStatItem } from "./components/SemesterBarChart";
import { SemesterBarChart } from "./components/SemesterBarChart";
import "./admin-programs.css";

export type ProgramPageState = "empty" | "editor" | "error";

const MAX_PROGRAM_JSON_BYTES = 2 * 1024 * 1024;
const VALID_STATUSES = new Set<BranchCourseNode["status"]>([
	"completed",
	"current",
	"locked",
]);

const PROGRAM_JSON_TEMPLATE: BranchCourseNode[] = [
	{
		course_node_id: "course_1",
		course_or_chapter_theme: "示例课程",
		course_goal: "填写该课程的教学目标",
		status: "locked",
		has_outline: false,
		is_custom: true,
		prerequisite_ids: [],
		time_arrangement: {
			semester_scope: "1",
			duration: "48学时/3学分",
			pace_reason: "可选：说明开课先修顺序",
		},
		key_points: ["核心知识点 1"],
		difficult_points: ["难点说明 1"],
		acceptance_criteria: ["验收标准 1"],
	},
];

const motionTokens = {
	lazy: { duration: 0.42, ease: [0.33, 1, 0.68, 1] },
} as const;

function asStringArray(value: unknown): string[] | undefined {
	if (!Array.isArray(value)) return undefined;
	return value
		.filter((item): item is string => typeof item === "string")
		.map((item) => item.trim())
		.filter(Boolean);
}

function normalizeImportedCourse(
	raw: unknown,
	index: number,
): BranchCourseNode {
	if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
		throw new Error(`第 ${index + 1} 项不是有效的课程对象`);
	}
	const item = raw as Record<string, unknown>;
	const id =
		typeof item.course_node_id === "string" ? item.course_node_id.trim() : "";
	const theme =
		typeof item.course_or_chapter_theme === "string"
			? item.course_or_chapter_theme.trim()
			: "";
	if (!id || !theme) {
		throw new Error(
			`第 ${index + 1} 项缺少必填字段 course_node_id 或 course_or_chapter_theme`,
		);
	}
	const rawTime =
		item.time_arrangement &&
		typeof item.time_arrangement === "object" &&
		!Array.isArray(item.time_arrangement)
			? (item.time_arrangement as Record<string, unknown>)
			: null;
	const semesterScope =
		rawTime && typeof rawTime.semester_scope === "string"
			? rawTime.semester_scope.trim() || "1"
			: "1";
	const duration =
		rawTime && typeof rawTime.duration === "string"
			? rawTime.duration.trim()
			: "";
	const paceReason =
		rawTime && typeof rawTime.pace_reason === "string"
			? rawTime.pace_reason.trim()
			: undefined;
	const statusCandidate = item.status as BranchCourseNode["status"];
	const status = VALID_STATUSES.has(statusCandidate)
		? statusCandidate
		: "locked";

	return {
		course_node_id: id,
		course_or_chapter_theme: theme,
		course_goal: typeof item.course_goal === "string" ? item.course_goal : "",
		status,
		has_outline: Boolean(item.has_outline),
		is_custom: true,
		prerequisite_ids: asStringArray(item.prerequisite_ids),
		time_arrangement: {
			semester_scope: semesterScope,
			duration,
			...(paceReason ? { pace_reason: paceReason } : {}),
		},
		key_points: asStringArray(item.key_points),
		difficult_points: asStringArray(item.difficult_points),
		acceptance_criteria: asStringArray(item.acceptance_criteria),
	};
}

export function parseProgramCoursesJson(rawText: string): BranchCourseNode[] {
	let parsed: unknown;
	try {
		parsed = JSON.parse(rawText);
	} catch {
		throw new Error("文件内容不是合法的 JSON 格式");
	}
	const rawList = Array.isArray(parsed)
		? parsed
		: parsed &&
				typeof parsed === "object" &&
				"courses" in parsed &&
				Array.isArray((parsed as { courses?: unknown }).courses)
			? (parsed as { courses: unknown[] }).courses
			: null;
	if (!rawList) {
		throw new Error("JSON 根节点必须是课程数组或包含 courses 数组的对象");
	}
	if (rawList.length === 0) {
		throw new Error("JSON 中的课程列表不能为空");
	}
	const courses = rawList.map((item, index) =>
		normalizeImportedCourse(item, index),
	);
	const seenIds = new Set<string>();
	for (const course of courses) {
		if (seenIds.has(course.course_node_id)) {
			throw new Error(`存在重复的课程编号：${course.course_node_id}`);
		}
		seenIds.add(course.course_node_id);
	}
	return courses;
}

function createNextCourseNode(
	existingCourses: BranchCourseNode[],
): BranchCourseNode {
	const existingIds = new Set(existingCourses.map((c) => c.course_node_id));
	let counter = existingCourses.length + 1;
	while (existingIds.has(`course_${counter}`)) {
		counter += 1;
	}
	return {
		course_node_id: `course_${counter}`,
		course_or_chapter_theme: `新课程 ${counter}`,
		course_goal: "",
		status: "locked",
		has_outline: false,
		is_custom: true,
		time_arrangement: {
			semester_scope: "1",
			duration: "48学时/3学分",
		},
		key_points: [],
		difficult_points: [],
		acceptance_criteria: [],
	};
}

function readJsonFileText(file: File): Promise<string> {
	if (typeof file.text === "function") {
		return file.text();
	}
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () =>
			resolve(typeof reader.result === "string" ? reader.result : "");
		reader.onerror = () => reject(new Error("读取 JSON 文件失败"));
		reader.readAsText(file, "utf-8");
	});
}

function downloadJsonFile(filename: string, data: unknown): void {
	const json = JSON.stringify(data, null, 2);
	const blob = new Blob([json], { type: "application/json;charset=utf-8" });
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement("a");
	anchor.href = url;
	anchor.download = filename;
	document.body.append(anchor);
	anchor.click();
	anchor.remove();
	URL.revokeObjectURL(url);
}

export function AdminProgramsPage() {
	const { user, token } = useAuth();
	const reduceMotion = useReducedMotion();
	const fileInputRef = useRef<HTMLInputElement>(null);
	const [pageState, setPageState] = useState<ProgramPageState>("empty");
	const [courses, setCourses] = useState<BranchCourseNode[]>([]);
	const [activeCourseId, setActiveCourseId] = useState<string | null>(null);
	const [fileError, setFileError] = useState<string | null>(null);
	const [toastMessage, setToastMessage] = useState<string | null>(null);
	const [programScopeOptions, setProgramScopeOptions] = useState<
		ProgramScope[]
	>([]);
	const [programScope, setProgramScope] = useState<ProgramScope>({
		school: "",
		major: "",
		className: "",
	});
	const [activeTab, setActiveTab] = useState<"editor" | "graph">("editor");

	useEffect(() => {
		if (!user) return;
		setProgramScope({
			school: user.school,
			major: user.major,
			className: user.class_name,
		});
	}, [user]);

	const graphData = useMemo(() => {
		const nodeStatusMap: Record<string, string> = {};
		const nodes: GraphNode[] = courses.map((c) => {
			const status =
				c.course_node_id === activeCourseId
					? "in-progress"
					: c.is_custom || (c.key_points && c.key_points.length > 0)
						? "completed"
						: "locked";
			nodeStatusMap[c.course_node_id] = status;

			return {
				id: c.course_node_id,
				title: c.course_or_chapter_theme,
				status,
				agentMessage: `第 ${c.time_arrangement?.semester_scope ?? "?"} 学期`,
				completedConcepts: c.key_points?.length || 0,
				totalConcepts:
					(c.key_points?.length || 0) + (c.difficult_points?.length || 0) || 5,
			};
		});

		const edges: GraphEdge[] = [];
		courses.forEach((c) => {
			if (c.prerequisite_ids && c.prerequisite_ids.length > 0) {
				c.prerequisite_ids.forEach((pId) => {
					const sourceStatus = nodeStatusMap[pId];
					const targetStatus = nodeStatusMap[c.course_node_id];
					const edgeStatus =
						sourceStatus === "completed" && targetStatus === "completed"
							? "completed"
							: "future";

					edges.push({
						id: `${pId}-${c.course_node_id}`,
						source: pId,
						target: c.course_node_id,
						status: edgeStatus,
					});
				});
			}
		});

		return { nodes, edges };
	}, [courses, activeCourseId]);

	const handleCanvasClick = (event: React.MouseEvent<HTMLElement>) => {
		const target = event.target as HTMLElement;
		const nodeWrapper = target.closest(".node-wrapper");
		if (nodeWrapper) {
			const nodeId = nodeWrapper.getAttribute("data-node-id");
			if (nodeId) {
				setActiveCourseId(nodeId);
			}
		}
	};

	const semesterStats = useMemo(() => {
		const stats: SemesterStatItem[] = Array.from({ length: 8 }, (_, i) => ({
			semester: String(i + 1),
			credits: 0,
			hours: 0,
			completedCourses: 0,
			totalCourses: 0,
		}));

		courses.forEach((c) => {
			const sem = parseInt(c.time_arrangement?.semester_scope ?? "1", 10);
			if (sem >= 1 && sem <= 8) {
				const durationStr = c.time_arrangement?.duration || "";
				const hourMatch = durationStr.match(/(\d+)学时/);
				const creditMatch = durationStr.match(/(\d+)学分/);

				const hours = hourMatch ? parseInt(hourMatch[1], 10) : 0;
				const credits = creditMatch ? parseInt(creditMatch[1], 10) : 0;

				stats[sem - 1].hours += hours;
				stats[sem - 1].credits += credits;
				stats[sem - 1].totalCourses += 1;
				if (c.is_custom || (c.key_points && c.key_points.length > 0)) {
					stats[sem - 1].completedCourses += 1;
				}
			}
		});

		return stats;
	}, [courses]);

	useEffect(() => {
		if (!token) return;
		let cancelled = false;
		adminDataApi
			.programs(token)
			.then((programs) => {
				if (cancelled) return;
				setProgramScopeOptions(
					programs.map((program) => ({
						school: program.school,
						major: program.major,
						className: program.class_name,
					})),
				);
			})
			.catch(() => {
				if (!cancelled) setProgramScopeOptions([]);
			});
		adminProgramApi
			.getProgram(token)
			.then((program) => {
				if (cancelled || !program) return;
				setCourses(
					program.courses.map((course) => ({ ...course, is_custom: true })),
				);
				setProgramScope({
					school: program.school,
					major: program.major,
					className: program.class_name,
				});
				setPageState("editor");
			})
			.catch((programError) => {
				if (cancelled) return;
				setFileError(
					programError instanceof Error
						? programError.message
						: "人培方案加载失败",
				);
				setPageState("error");
			});
		return () => {
			cancelled = true;
		};
	}, [token]);

	const showToast = (message: string, duration = 1800) => {
		setToastMessage(message);
		setTimeout(() => {
			setToastMessage(null);
		}, duration);
	};

	const handleImportFile = async (file: File) => {
		const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
		if (ext !== ".json") {
			setFileError("仅支持导入 .json 格式的培养方案文件");
			setPageState("error");
			return;
		}
		if (file.size > MAX_PROGRAM_JSON_BYTES) {
			setFileError("JSON 文件大小不能超过 2MB");
			setPageState("error");
			return;
		}
		try {
			const text = await readJsonFileText(file);
			const imported = parseProgramCoursesJson(text);
			setCourses(imported);
			setActiveCourseId(null);
			setFileError(null);
			setPageState("editor");
			showToast(`已导入 ${imported.length} 门课程`);
		} catch (error) {
			setFileError(error instanceof Error ? error.message : "JSON 导入失败");
			setPageState("error");
		}
	};

	const handleJsonFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		event.target.value = "";
		if (file) {
			void handleImportFile(file);
		}
	};

	const handleAddCourse = () => {
		const nextCourse = createNextCourseNode(courses);
		setCourses((prev) => [...prev, nextCourse]);
		setActiveCourseId(nextCourse.course_node_id);
		setActiveTab("editor");
		setFileError(null);
		setPageState("editor");
	};

	const handleDeleteCourse = (courseNodeId: string) => {
		setCourses((prev) => {
			const remaining = prev.filter((c) => c.course_node_id !== courseNodeId);
			if (remaining.length === 0) {
				setPageState("empty");
			}
			return remaining;
		});
		setActiveCourseId(null);
	};

	const handleExportJson = () => {
		downloadJsonFile("cultivation-program.json", courses);
		showToast("已导出 JSON 文件");
	};

	const handleDownloadTemplate = () => {
		downloadJsonFile(
			"cultivation-program-template.json",
			PROGRAM_JSON_TEMPLATE,
		);
	};

	const handleSave = async () => {
		const scope = {
			school: programScope.school.trim(),
			major: programScope.major.trim(),
			className: programScope.className.trim(),
		};
		if (!scope.school || !scope.major || !scope.className) {
			showToast("请填写学校、专业、班级；这些值必须和学生账号完全一致");
			return;
		}
		const publishedCourses = courses.map((course) => ({
			...course,
			is_custom: true,
		}));
		setCourses(publishedCourses);
		if (token) {
			try {
				await adminProgramApi.publishProgram(token, publishedCourses, scope);
			} catch (programError) {
				showToast(
					programError instanceof Error
						? programError.message
						: "人培方案发布失败",
				);
				return;
			}
		}
		showToast("人培方案已成功发布并对齐！", 1500);
	};

	const handleReset = () => {
		if (window.confirm("确定要清空当前培养方案吗？当前未发布修改将被覆盖。")) {
			setCourses([]);
			setActiveCourseId(null);
			setPageState("empty");
		}
	};

	const renderContent = () => {
		switch (pageState) {
			case "error":
				return (
					<div className="error-panel">
						<div className="error-icon">✕</div>
						<h3 className="error-title">JSON 导入失败</h3>
						<p className="error-message">{fileError}</p>
						<button
							type="button"
							className="btn btn-secondary"
							onClick={() => {
								setFileError(null);
								setPageState(courses.length > 0 ? "editor" : "empty");
							}}
						>
							返回
						</button>
					</div>
				);
			case "editor":
				if (activeTab === "graph") {
					return (
						<div className="graph-view-container">
							<div className="canvas-panel">
								<div className="canvas-header">
									<h3>方案依赖图谱</h3>
									<p>培养方案中课程前置依赖与关系拓扑图</p>
								</div>
								<button
									type="button"
									className="canvas-wrapper"
									onClick={handleCanvasClick}
								>
									<OrganicCanvas
										nodes={graphData.nodes}
										edges={graphData.edges}
									/>
								</button>
							</div>
							<div className="stats-distribution-panel">
								<div className="distribution-card">
									<h4>学期学分分布 (Credits per Semester)</h4>
									<SemesterBarChart data={semesterStats} type="credits" />
								</div>
								<div className="distribution-card">
									<h4>学期课时分布 (Hours per Semester)</h4>
									<SemesterBarChart data={semesterStats} type="hours" />
								</div>
							</div>
						</div>
					);
				}
				return (
					<div className="editor-layout">
						<div className="editor-main">
							<ProgramTreeTable
								courses={courses}
								activeCourseId={activeCourseId}
								onSelectCourse={setActiveCourseId}
							/>
						</div>
					</div>
				);
			default:
				return (
					<div className="program-import-card">
						<h3 className="program-import-title">创建或导入培养方案</h3>
						<p className="program-import-hint">
							支持手动逐门添加编辑课程，或导入符合系统 JSON
							结构的培养方案文件（.json，不超过 2MB）。
						</p>
						<div className="program-import-actions">
							<button
								type="button"
								className="btn btn-primary"
								onClick={handleAddCourse}
							>
								手动添加课程
							</button>
							<button
								type="button"
								className="btn btn-secondary"
								onClick={() => fileInputRef.current?.click()}
							>
								导入 JSON
							</button>
							<button
								type="button"
								className="btn btn-secondary"
								onClick={handleDownloadTemplate}
							>
								下载 JSON 模板
							</button>
						</div>
					</div>
				);
		}
	};

	return (
		<>
			<input
				ref={fileInputRef}
				type="file"
				className="file-input-hidden"
				accept=".json,application/json"
				data-testid="json-file-input"
				onChange={handleJsonFileChange}
			/>

			<header className="admin-header">
				<div>
					<p className="admin-kicker">curriculum</p>
					<h1 id="admin-programs-title">人培方案</h1>
				</div>
				<div className="admin-header-actions">
					{courses.length > 0 && pageState === "editor" && (
						<>
							<button
								type="button"
								className="admin-secondary-action"
								onClick={handleAddCourse}
							>
								添加课程
							</button>
							<button
								type="button"
								className="admin-secondary-action"
								onClick={() => fileInputRef.current?.click()}
							>
								导入 JSON
							</button>
							<button
								type="button"
								className="admin-secondary-action"
								onClick={handleExportJson}
							>
								导出 JSON
							</button>
							<button
								type="button"
								className="admin-secondary-action"
								onClick={handleReset}
							>
								清空方案
							</button>
							<button
								type="button"
								className="admin-primary-action"
								onClick={() => void handleSave()}
							>
								保存并发布
							</button>
						</>
					)}
				</div>
			</header>

			<ProgramScopePanel
				scope={programScope}
				scopeOptions={programScopeOptions}
				onChange={setProgramScope}
			/>

			{courses.length > 0 && pageState === "editor" ? (
				<div
					className="program-nav-tabs"
					role="tablist"
					aria-label="人培方案视图"
					style={{ alignSelf: "start" }}
				>
					<button
						type="button"
						className={`program-tab ${activeTab === "editor" ? "tab-active" : ""}`}
						onClick={() => setActiveTab("editor")}
					>
						大纲对齐编辑
					</button>
					<button
						type="button"
						className={`program-tab ${activeTab === "graph" ? "tab-active" : ""}`}
						onClick={() => setActiveTab("graph")}
					>
						方案依赖图谱
					</button>
				</div>
			) : null}

			{renderContent()}

			<AnimatePresence>
				{activeCourseId && (
					<ProgramDetailDrawer
						course={
							courses.find((c) => c.course_node_id === activeCourseId) || null
						}
						onClose={() => setActiveCourseId(null)}
						onDeleteCourse={handleDeleteCourse}
						onUpdateCourse={(updated) => {
							setCourses((prev) =>
								prev.map((c) =>
									c.course_node_id === updated.course_node_id ? updated : c,
								),
							);
						}}
					/>
				)}
			</AnimatePresence>

			<AnimatePresence>
				{toastMessage && (
					<motion.div
						key="toast"
						className="toast-message"
						initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
						animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
						exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 20 }}
						transition={reduceMotion ? { duration: 0.12 } : motionTokens.lazy}
					>
						{toastMessage}
					</motion.div>
				)}
			</AnimatePresence>
		</>
	);
}
