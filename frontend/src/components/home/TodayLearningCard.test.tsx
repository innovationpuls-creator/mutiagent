import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TodayLearning } from "../../types/profile";
import { TodayLearningCard } from "./TodayLearningCard";

afterEach(() => {
	cleanup();
});

const todayLearning: TodayLearning = {
	title: "基于画像规划下一步",
	description: "默认描述",
	source: "学习路径智能体",
	currentLearningCourse: {
		grade_id: "year_3",
		course_node_id: "year_3_course_1",
		course_or_chapter_theme: "AI 应用开发项目课",
		course_goal: "完成一个 AI 功能模块并接入 Web 应用",
		time_arrangement: {
			semester_scope: "上学期",
			duration: "6 周",
			pace_reason: "围绕平时学习节奏安排",
		},
		current_focus: "正在学习 AI 应用开发项目课",
		progress_state: "in_progress",
		next_action: "开始第一章需求拆解",
	},
	currentCourseDetail: {
		course_node_id: "year_3_course_1",
		grade_id: "year_3",
		course_or_chapter_theme: "AI 应用开发项目课",
		time_arrangement: {
			semester_scope: "上学期",
			duration: "6 周",
			pace_reason: "围绕平时学习节奏安排",
		},
		course_goal: "完成一个 AI 功能模块并接入 Web 应用",
		prerequisite_node_ids: [],
		chapter_nodes: [],
		core_knowledge_points: [],
		key_points: ["AI API 调用"],
		difficult_points: ["工程化部署"],
		learning_sequence: ["需求拆解"],
		knowledge_relations: [],
		downstream_resource_direction_ids: [],
		acceptance_criteria: ["能独立演示完整功能"],
	},
	currentCourseOutline: {
		course_id: "year_3_course_1",
		course_name: "AI 应用开发项目课",
		grade_year: "year_3",
		personalization_summary: "先完成需求拆解，再进入接口接入与联调演示。",
		sections: [
			{
				section_id: "1",
				parent_section_id: null,
				depth: 1,
				title: "需求拆解",
				order_index: 1,
				description: "确认功能边界与验收标准。",
				key_knowledge_points: ["功能边界"],
			},
			{
				section_id: "1.1",
				parent_section_id: "1",
				depth: 2,
				title: "学习目标",
				order_index: 2,
				description: "明确本章学完后的目标。",
				key_knowledge_points: ["功能边界", "验收标准"],
			},
			{
				section_id: "1.2",
				parent_section_id: "1",
				depth: 2,
				title: "任务拆解",
				order_index: 3,
				description: "梳理本章实现步骤。",
				key_knowledge_points: ["任务拆分"],
			},
			{
				section_id: "1.3",
				parent_section_id: "1",
				depth: 2,
				title: "检查点",
				order_index: 4,
				description: "确认本章是否可进入下一章。",
				key_knowledge_points: ["完成确认"],
			},
		],
		learning_sequence: ["第一章：需求拆解"],
		total_estimated_hours: "6-8 小时",
	},
	gradeCourses: [
		{
			course_node_id: "year_3_course_1",
			grade_id: "year_3",
			course_or_chapter_theme: "AI 应用开发项目课",
			time_arrangement: {
				semester_scope: "上学期",
				duration: "6 周",
				pace_reason: "围绕平时学习节奏安排",
			},
			course_goal: "完成一个 AI 功能模块并接入 Web 应用",
			prerequisite_node_ids: [],
			chapter_nodes: [],
			core_knowledge_points: [],
			key_points: ["AI API 调用"],
			difficult_points: ["工程化部署"],
			learning_sequence: ["需求拆解"],
			knowledge_relations: [],
			downstream_resource_direction_ids: [],
			acceptance_criteria: ["能独立演示完整功能"],
		},
	],
	followingCourses: [],
};

describe("TodayLearningCard", () => {
	it("renders current learning course theme and focus", () => {
		render(<TodayLearningCard data={todayLearning} />);

		expect(screen.getByText("AI 应用开发项目课")).toBeTruthy();
		expect(screen.getByText("正在学习 AI 应用开发项目课")).toBeTruthy();
		expect(screen.getByText("已生成课程大纲")).toBeTruthy();
		expect(screen.getByText("课程大纲主线")).toBeTruthy();
		expect(screen.getByText("第一章")).toBeTruthy();
		expect(screen.getByText("第一章：需求拆解")).toBeTruthy();
		expect(
			screen.getByText("先完成需求拆解，再进入接口接入与联调演示。"),
		).toBeTruthy();
	});

	it("opens detail only from the dedicated detail button", () => {
		const onClick = vi.fn();
		render(<TodayLearningCard data={todayLearning} onClick={onClick} />);

		const detailButton = screen.getByRole("button", {
			name: "打开今日学习详情",
		});
		fireEvent.click(detailButton);

		expect(onClick).toHaveBeenCalledTimes(1);
	});

	it("triggers start learning without bubbling to the card click handler", () => {
		const onClick = vi.fn();
		const onStartLearning = vi.fn();
		render(
			<TodayLearningCard
				data={todayLearning}
				onClick={onClick}
				onStartLearning={onStartLearning}
			/>,
		);

		fireEvent.click(screen.getAllByRole("button", { name: "开始学习" })[0]);

		expect(onStartLearning).toHaveBeenCalledTimes(1);
		expect(onClick).toHaveBeenCalledTimes(0);
	});

	it("does not render a start button when no start action is available", () => {
		render(<TodayLearningCard data={todayLearning} />);

		expect(screen.queryByRole("button", { name: "开始学习" })).toBeNull();
	});
});
