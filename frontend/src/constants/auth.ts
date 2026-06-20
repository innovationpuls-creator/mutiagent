import type { OAuthProvider } from "../types/auth";

export const agentEvents = [
	"理解学习目标",
	"召回历史偏好",
	"分配规划智能体",
	"生成能力地图",
	"筛选学习资源",
] as const;

export const mindMapBranches = ["目标", "能力", "路径", "资源"] as const;

export const resourceCards = ["课程片段", "项目练习", "复盘清单"] as const;

export const providerLabels: Record<OAuthProvider, string> = {
	qq: "QQ",
	xuexitong: "学习通",
};
