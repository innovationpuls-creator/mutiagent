import { useState } from "react";
import type { BranchCourseNode } from "../../../types/branch";

interface CourseRowProps {
	course: BranchCourseNode;
	isActive: boolean;
	onClick: () => void;
}

export function CourseRow({ course, isActive, onClick }: CourseRowProps) {
	const semesterText = `学期 ${course.time_arrangement?.semester_scope ?? "?"}`;
	const durationText = course.time_arrangement?.duration ?? "";

	return (
		<div
			className={`course-row ${isActive ? "row-active" : ""}`}
			onClick={onClick}
		>
			<div className="course-info">
				<span className="course-semester">{semesterText}</span>
				<span className="course-theme">{course.course_or_chapter_theme}</span>
			</div>
			<div className="course-meta">
				<span className="course-duration">{durationText}</span>
				<span className="course-edit-badge">编辑</span>
			</div>
		</div>
	);
}

interface GradeSectionProps {
	gradeName: string;
	courses: BranchCourseNode[];
	activeCourseId: string | null;
	onSelectCourse: (id: string) => void;
}

export function GradeSection({
	gradeName,
	courses,
	activeCourseId,
	onSelectCourse,
}: GradeSectionProps) {
	const [isFolded, setIsFolded] = useState(false);

	return (
		<div className="grade-section">
			<button
				type="button"
				className="grade-header"
				onClick={() => setIsFolded(!isFolded)}
			>
				<span className="grade-title">{gradeName}</span>
				<span className="fold-icon">{isFolded ? "▲" : "▼"}</span>
			</button>
			{!isFolded && (
				<div className="grade-content">
					{courses.map((course) => (
						<CourseRow
							key={course.course_node_id}
							course={course}
							isActive={course.course_node_id === activeCourseId}
							onClick={() => onSelectCourse(course.course_node_id)}
						/>
					))}
				</div>
			)}
		</div>
	);
}

interface ProgramTreeTableProps {
	courses: BranchCourseNode[];
	activeCourseId: string | null;
	onSelectCourse: (id: string) => void;
}

function getGradeKey(semester: string): string {
	const sem = parseInt(semester, 10);
	if (sem <= 2) return "Freshman";
	if (sem <= 4) return "Sophomore";
	if (sem <= 6) return "Junior";
	return "Senior";
}

export function ProgramTreeTable({
	courses,
	activeCourseId,
	onSelectCourse,
}: ProgramTreeTableProps) {
	const grades = [
		{ key: "Freshman", name: "大一 (Freshman)" },
		{ key: "Sophomore", name: "大二 (Sophomore)" },
		{ key: "Junior", name: "大三 (Junior)" },
		{ key: "Senior", name: "大四 (Senior)" },
	];

	return (
		<div className="tree-table">
			{grades.map((grade) => {
				const gradeCourses = courses.filter(
					(c) =>
						getGradeKey(c.time_arrangement?.semester_scope ?? "1") ===
						grade.key,
				);
				return (
					<GradeSection
						key={grade.key}
						gradeName={grade.name}
						courses={gradeCourses}
						activeCourseId={activeCourseId}
						onSelectCourse={onSelectCourse}
					/>
				);
			})}
		</div>
	);
}
