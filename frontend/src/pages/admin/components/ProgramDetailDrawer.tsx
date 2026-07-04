import { motion, useReducedMotion } from "framer-motion";
import type { BranchCourseNode } from "../../../types/branch";

interface FieldProps {
	course: BranchCourseNode;
	onChange: (key: string, value: unknown) => void;
}

export function GeneralFields({ course, onChange }: FieldProps) {
	return (
		<div className="form-section">
			<div className="form-group">
				<label htmlFor="course_theme">课程名称</label>
				<input
					id="course_theme"
					type="text"
					value={course.course_or_chapter_theme}
					onChange={(e) => onChange("course_or_chapter_theme", e.target.value)}
					placeholder="请输入课程名称"
					className="drawer-input"
				/>
			</div>
			<div className="form-group">
				<label htmlFor="course_goal">课程目标</label>
				<textarea
					id="course_goal"
					value={course.course_goal}
					onChange={(e) => onChange("course_goal", e.target.value)}
					placeholder="请输入课程目标"
					className="drawer-textarea"
					rows={3}
				/>
			</div>
		</div>
	);
}

export function TimeFields({ course, onChange }: FieldProps) {
	const time = course.time_arrangement;
	return (
		<div className="form-section">
			<h3 className="section-title">时间编排</h3>
			<div className="form-row">
				<div className="form-group half">
					<label htmlFor="semester_scope">建议学期</label>
					<select
						id="semester_scope"
						value={time?.semester_scope ?? "1"}
						onChange={(e) => onChange("semester_scope", e.target.value)}
						className="drawer-select"
					>
						{[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
							<option key={s} value={String(s)}>
								学期 {s}
							</option>
						))}
					</select>
				</div>
				<div className="form-group half">
					<label htmlFor="duration">课程时长/学分</label>
					<input
						id="duration"
						type="text"
						value={time?.duration ?? ""}
						onChange={(e) => onChange("duration", e.target.value)}
						placeholder="如：64学时/4学分"
						className="drawer-input"
					/>
				</div>
			</div>
			<div className="form-group">
				<label htmlFor="pace_reason">开课原因（可选）</label>
				<textarea
					id="pace_reason"
					value={time?.pace_reason ?? ""}
					onChange={(e) => onChange("pace_reason", e.target.value)}
					placeholder="例如：为后续数据结构奠定编程基础"
					className="drawer-textarea"
					rows={2}
				/>
			</div>
		</div>
	);
}

export function PointFields({ course, onChange }: FieldProps) {
	const handleArrayChange = (
		key: "key_points" | "difficult_points" | "acceptance_criteria",
		text: string,
	) => {
		const arr = text
			.split("\n")
			.map((s) => s.trim())
			.filter(Boolean);
		onChange(key, arr);
	};

	return (
		<div className="form-section">
			<h3 className="section-title">课程要点</h3>
			<div className="form-group">
				<label htmlFor="key_points">核心要点 (每行一个)</label>
				<textarea
					id="key_points"
					value={course.key_points?.join("\n") ?? ""}
					onChange={(e) => handleArrayChange("key_points", e.target.value)}
					placeholder="请输入核心要点，每行一个"
					className="drawer-textarea"
					rows={3}
				/>
			</div>
			<div className="form-group">
				<label htmlFor="difficult_points">难点说明 (每行一个)</label>
				<textarea
					id="difficult_points"
					value={course.difficult_points?.join("\n") ?? ""}
					onChange={(e) =>
						handleArrayChange("difficult_points", e.target.value)
					}
					placeholder="请输入难点说明，每行一个"
					className="drawer-textarea"
					rows={3}
				/>
			</div>
			<div className="form-group">
				<label htmlFor="acceptance_criteria">验收标准 (每行一个)</label>
				<textarea
					id="acceptance_criteria"
					value={course.acceptance_criteria?.join("\n") ?? ""}
					onChange={(e) =>
						handleArrayChange("acceptance_criteria", e.target.value)
					}
					placeholder="请输入验收标准，每行一个"
					className="drawer-textarea"
					rows={3}
				/>
			</div>
		</div>
	);
}

interface DrawerFormProps {
	course: BranchCourseNode;
	onUpdateCourse: (updated: BranchCourseNode) => void;
}

export function DrawerForm({ course, onUpdateCourse }: DrawerFormProps) {
	const handleChange = (key: string, value: unknown) => {
		if (["semester_scope", "duration", "pace_reason"].includes(key)) {
			onUpdateCourse({
				...course,
				time_arrangement: {
					semester_scope: course.time_arrangement?.semester_scope ?? "1",
					duration: course.time_arrangement?.duration ?? "",
					pace_reason: course.time_arrangement?.pace_reason,
					[key]: value as string,
				},
			});
		} else {
			onUpdateCourse({
				...course,
				[key]: value,
			} as unknown as BranchCourseNode);
		}
	};

	return (
		<form className="drawer-form" onSubmit={(e) => e.preventDefault()}>
			<GeneralFields course={course} onChange={handleChange} />
			<TimeFields course={course} onChange={handleChange} />
			<PointFields course={course} onChange={handleChange} />
		</form>
	);
}

interface ProgramDetailDrawerProps {
	course: BranchCourseNode | null;
	onClose: () => void;
	onUpdateCourse: (updated: BranchCourseNode) => void;
}

export function ProgramDetailDrawer({
	course,
	onClose,
	onUpdateCourse,
}: ProgramDetailDrawerProps) {
	const reduceMotion = useReducedMotion();
	if (!course) return null;

	return (
		<div className="drawer-overlay" onClick={onClose}>
			<motion.div
				className="detail-drawer"
				onClick={(e) => e.stopPropagation()}
				initial={reduceMotion ? { opacity: 0 } : { x: "100%" }}
				animate={reduceMotion ? { opacity: 1 } : { x: 0 }}
				exit={reduceMotion ? { opacity: 0 } : { x: "100%" }}
				transition={
					reduceMotion
						? { duration: 0.12 }
						: { duration: 0.42, ease: [0.33, 1, 0.68, 1] }
				}
			>
				<div className="drawer-header">
					<h2 className="drawer-title">编辑课程大纲</h2>
					<button type="button" className="drawer-close-btn" onClick={onClose}>
						✕
					</button>
				</div>
				<div className="drawer-body">
					<DrawerForm course={course} onUpdateCourse={onUpdateCourse} />
				</div>
			</motion.div>
		</div>
	);
}
