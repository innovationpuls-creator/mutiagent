import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminProgramApi } from "../api/adminProgram";
import { fetchBranchOverview } from "../api/branch";
import { fetchLeafCourse } from "../api/leaf";
import { useAuth } from "../contexts/AuthContext";
import {
	mergeProgramCourses,
	normalizeProgramCourses,
} from "../lib/studentCourses";
import type { BranchOverview } from "../types/branch";
import type { LeafCourseResponse } from "../types/leaf";
import "./student-workspace.css";

export function StudentCoursesPage({ mode }: { mode: "learn" | "quiz" }) {
	const { token } = useAuth();
	const [overview, setOverview] = useState<BranchOverview | null>(null);
	const [courseId, setCourseId] = useState<string | null>(null);
	const [detail, setDetail] = useState<LeafCourseResponse | null>(null);
	const [error, setError] = useState<string | null>(null);
	const [retry, setRetry] = useState(0);
	const [loading, setLoading] = useState(true);
	useEffect(() => {
		if (!token) return;
		void retry;
		let cancelled = false;
		setLoading(true);
		setError(null);
		Promise.all([
			fetchBranchOverview(token),
			adminProgramApi.getMatchedProgram(token),
		])
			.then(([data, program]) => {
				if (cancelled) return;
				mergeProgramCourses(data, normalizeProgramCourses(program?.courses));
				setOverview(data);
			})
			.catch((e) => {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "课程加载失败");
			})
			.finally(() => {
				if (!cancelled) setLoading(false);
			});
		return () => {
			cancelled = true;
		};
	}, [token, retry]);
	useEffect(() => {
		if (!token || !courseId || mode !== "quiz") return;
		void retry;
		let cancelled = false;
		setDetail(null);
		setError(null);
		fetchLeafCourse(token, courseId)
			.then((data) => {
				if (!cancelled) setDetail(data);
			})
			.catch((e) => {
				if (!cancelled)
					setError(e instanceof Error ? e.message : "章节加载失败");
			});
		return () => {
			cancelled = true;
		};
	}, [token, courseId, mode, retry]);
	const courses = Object.values(overview?.years ?? {}).flatMap(
		(year) => year.courses,
	);
	return (
		<section
			className="student-workspace"
			aria-label={mode === "learn" ? "课程学习" : "章节测验"}
		>
			<header>
				<h1>{mode === "learn" ? "课程学习" : "章节测验"}</h1>
				<p>
					{mode === "learn"
						? "继续当前课程，或回顾已经完成的内容。"
						: "选择课程与章节，检验理解，再继续下一步。"}
				</p>
			</header>
			{error && (
				<div role="alert">
					<p>{error}</p>
					<button type="button" onClick={() => setRetry((n) => n + 1)}>
						重新加载
					</button>
				</div>
			)}
			{loading ? (
				<p role="status">正在加载课程…</p>
			) : !courses.length ? (
				<div>
					<h2>还没有学习课程</h2>
					<p>先完善学习画像，再规划学习路径。</p>
					<Link to="/sprout">返回学习首页</Link>
				</div>
			) : (
				<div className="student-course-layout">
					<ul className="student-course-list">
						{courses.map((course) => (
							<li key={course.course_node_id}>
								<div>
									<h2>{course.course_or_chapter_theme}</h2>
									<p>{course.course_goal}</p>
									<span>
										{course.status === "locked"
											? "尚未解锁"
											: course.status === "completed"
												? "已完成"
												: "可学习"}
									</span>
								</div>
								{course.status !== "locked" &&
									(mode === "learn" ? (
										<Link
											to={`/leaf/${encodeURIComponent(course.course_node_id)}`}
										>
											{course.status === "completed" ? "回顾课程" : "进入课程"}
										</Link>
									) : (
										<button
											type="button"
											aria-pressed={courseId === course.course_node_id}
											onClick={() => setCourseId(course.course_node_id)}
										>
											查看章节
										</button>
									))}
							</li>
						))}
					</ul>
					{mode === "quiz" && courseId && (
						<section className="student-chapters" aria-label="章节进度">
							{!detail && !error ? (
								<p role="status">正在加载章节…</p>
							) : (
								detail &&
								(detail.access_state === "locked" ? (
									<p>{detail.locked_reason}</p>
								) : !detail.chapter_progress?.length ? (
									<div>
										<p>这门课程还没有章节大纲。</p>
										<Link to={`/leaf/${encodeURIComponent(courseId)}`}>
											进入课程准备大纲
										</Link>
									</div>
								) : (
									<>
										<h2>{detail.course.course_or_chapter_theme}</h2>
										<ol>
											{detail.chapter_progress.map((chapter) => (
												<li key={chapter.chapter_id}>
													<div>
														<h3>
															{detail.sections.find(
																(s) => s.section_id === chapter.chapter_id,
															)?.title ?? chapter.chapter_id}
														</h3>
														<p>
															{chapter.state === "passed"
																? "已通过"
																: chapter.state === "locked"
																	? "通过上一章后解锁"
																	: "可测验"}
															{chapter.latest_attempt_id
																? ` · 最好成绩 ${chapter.best_score} 分`
																: ""}
														</p>
													</div>
													{chapter.state !== "locked" && (
														<Link
															to={`/forest/${encodeURIComponent(courseId)}?chapter_id=${encodeURIComponent(chapter.chapter_id)}`}
														>
															{chapter.state === "passed"
																? "再次测验"
																: "开始测验"}
														</Link>
													)}
												</li>
											))}
										</ol>
									</>
								))
							)}
						</section>
					)}
				</div>
			)}
		</section>
	);
}
