import type { BranchCourseNode } from "../types/branch";
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from "./http";

export interface CultivationProgram {
	program_id: string;
	teacher_uid: string;
	teacher_name: string;
	teacher_identifier: string;
	school: string;
	major: string;
	class_name: string;
	courses: BranchCourseNode[];
	published_at: string | null;
	updated_at: string;
}

export interface ProgramScopePayload {
	school: string;
	major: string;
	className: string;
}

function programBody(courses: BranchCourseNode[], scope?: ProgramScopePayload) {
	if (!scope) return { courses };
	return {
		courses,
		school: scope.school,
		major: scope.major,
		class_name: scope.className,
	};
}

async function requestProgram<TResponse>(
	token: string,
	path: string,
	init: RequestInit = {},
): Promise<TResponse> {
	const response = await fetch(`${API_BASE_URL}${path}`, {
		...init,
		headers: {
			...(init.body ? { "Content-Type": "application/json" } : {}),
			Authorization: `Bearer ${token}`,
			...init.headers,
		},
	});

	if (!response.ok) {
		const error = await readApiError(response);
		notifyAuthInvalidFromError(response.status, error);
		throw new Error(
			(typeof error?.detail === "string" ? error.detail : null) ??
				"人培方案操作失败",
		);
	}

	return (await response.json()) as TResponse;
}

export const teacherProgramApi = {
	getTeacherProgram(token: string) {
		return requestProgram<CultivationProgram | null>(
			token,
			"/api/teacher/program",
		);
	},
	saveTeacherProgram(
		token: string,
		courses: BranchCourseNode[],
		scope?: ProgramScopePayload,
	) {
		return requestProgram<CultivationProgram>(token, "/api/teacher/program", {
			method: "PUT",
			body: JSON.stringify(programBody(courses, scope)),
		});
	},
	publishTeacherProgram(
		token: string,
		courses: BranchCourseNode[],
		scope?: ProgramScopePayload,
	) {
		return requestProgram<CultivationProgram>(
			token,
			"/api/teacher/program/publish",
			{
				method: "POST",
				body: JSON.stringify(programBody(courses, scope)),
			},
		);
	},
	getMatchedProgram(token: string) {
		return requestProgram<CultivationProgram | null>(
			token,
			"/api/student/matched-program",
		);
	},
};
