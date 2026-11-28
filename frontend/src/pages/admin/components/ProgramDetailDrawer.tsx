import { Button } from "../../../components/ui/Button";
import { Drawer } from "../../../components/ui/Drawer";
import {
	SelectField,
	TextAreaField,
	TextField,
} from "../../../components/ui/TextField";
import type { BranchCourseNode } from "../../../types/branch";

interface FieldProps {
	course: BranchCourseNode;
	onChange: (key: string, value: unknown) => void;
}

export function GeneralFields({ course, onChange }: FieldProps) {
	return (
		<div className="form-section">
			<TextField
				label="课程名称"
				id="course_theme"
				type="text"
				value={course.course_or_chapter_theme}
				onChange={(e) => onChange("course_or_chapter_theme", e.target.value)}
				placeholder="请输入课程名称"
			/>
			<TextAreaField
				label="课程目标"
				id="course_goal"
				value={course.course_goal}
				onChange={(e) => onChange("course_goal", e.target.value)}
				placeholder="请输入课程目标"
				rows={3}
			/>
		</div>
	);
}

export function TimeFields({ course, onChange }: FieldProps) {
	const time = course.time_arrangement;
	return (
		<div className="form-section">
			<h3 className="section-title">时间编排</h3>
			<div className="form-row">
				<SelectField
					label="建议学期"
					id="semester_scope"
					wrapperClassName="half"
					value={time?.semester_scope ?? "1"}
					onChange={(e) => onChange("semester_scope", e.target.value)}
				>
					{[1, 2, 3, 4, 5, 6, 7, 8].map((s) => (
						<option key={s} value={String(s)}>
							学期 {s}
						</option>
					))}
				</SelectField>
				<TextField
					label="课程时长/学分"
					id="duration"
					type="text"
					wrapperClassName="half"
					value={time?.duration ?? ""}
					onChange={(e) => onChange("duration", e.target.value)}
					placeholder="如：64学时/4学分"
				/>
			</div>
			<TextAreaField
				label="开课原因（可选）"
				id="pace_reason"
				value={time?.pace_reason ?? ""}
				onChange={(e) => onChange("pace_reason", e.target.value)}
				placeholder="例如：为后续数据结构奠定编程基础"
				rows={2}
			/>
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
			<TextAreaField
				label="核心要点 (每行一个)"
				id="key_points"
				value={course.key_points?.join("\n") ?? ""}
				onChange={(e) => handleArrayChange("key_points", e.target.value)}
				placeholder="请输入核心要点，每行一个"
				rows={3}
			/>
			<TextAreaField
				label="难点说明 (每行一个)"
				id="difficult_points"
				value={course.difficult_points?.join("\n") ?? ""}
				onChange={(e) => handleArrayChange("difficult_points", e.target.value)}
				placeholder="请输入难点说明，每行一个"
				rows={3}
			/>
			<TextAreaField
				label="验收标准 (每行一个)"
				id="acceptance_criteria"
				value={course.acceptance_criteria?.join("\n") ?? ""}
				onChange={(e) =>
					handleArrayChange("acceptance_criteria", e.target.value)
				}
				placeholder="请输入验收标准，每行一个"
				rows={3}
			/>
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
	onDeleteCourse?: (courseNodeId: string) => void;
}

export function ProgramDetailDrawer({
	course,
	onClose,
	onUpdateCourse,
	onDeleteCourse,
}: ProgramDetailDrawerProps) {
	return (
		<Drawer
			isOpen={Boolean(course)}
			onClose={onClose}
			title="编辑课程大纲"
			closeAriaLabel="关闭课程大纲抽屉"
			headerActions={
				course && onDeleteCourse ? (
					<Button
						variant="danger"
						size="sm"
						onClick={() => onDeleteCourse(course.course_node_id)}
					>
						删除课程
					</Button>
				) : null
			}
		>
			{course ? (
				<DrawerForm course={course} onUpdateCourse={onUpdateCourse} />
			) : null}
		</Drawer>
	);
}
