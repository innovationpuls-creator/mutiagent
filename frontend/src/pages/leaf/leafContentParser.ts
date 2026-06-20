import type {
	LeafComposedSection,
	LeafCourseResponse,
	LeafSection,
} from "../../types/leaf";

function cleanText(value: string | null | undefined): string {
	const text = (value ?? "").trim();
	if (!text) return "";
	const normalized = text.toLowerCase();
	if (normalized === "none" || normalized === "null") return "";
	return text;
}

function toChineseChapterNumber(sectionId: string): string {
	const digits: Record<string, string> = {
		"0": "零",
		"1": "一",
		"2": "二",
		"3": "三",
		"4": "四",
		"5": "五",
		"6": "六",
		"7": "七",
		"8": "八",
		"9": "九",
	};
	const value = Number(sectionId);
	if (!Number.isInteger(value) || value <= 0) return sectionId;
	if (value < 10) return digits[String(value)];
	if (value === 10) return "十";
	if (value < 20) return `十${digits[String(value % 10)]}`;

	const tens = Math.floor(value / 10);
	const ones = value % 10;
	if (ones === 0) return `${digits[String(tens)]}十`;
	return `${digits[String(tens)]}十${digits[String(ones)]}`;
}

function stripTopLevelTitlePrefix(title: string): string {
	if (!title) return "";
	const prefixes = [
		"第一章：",
		"第二章：",
		"第三章：",
		"第四章：",
		"第五章：",
		"第六章：",
		"第七章：",
		"第八章：",
		"第九章：",
		"第十章：",
	];
	const numericPattern = /^第\d+章：/;
	for (const prefix of prefixes) {
		if (title.startsWith(prefix)) return title.slice(prefix.length).trim();
	}
	if (numericPattern.test(title))
		return title.replace(numericPattern, "").trim();
	return title;
}

export function getOrderedLeafSections(sections: LeafSection[]): LeafSection[] {
	return [...sections].sort(
		(left, right) => left.order_index - right.order_index,
	);
}

export function getLeafChildSections(
	sections: LeafSection[],
	parentSectionId: string | null,
): LeafSection[] {
	return getOrderedLeafSections(sections).filter(
		(section) => section.parent_section_id === parentSectionId,
	);
}

export function getLeafSectionLabel(sectionId: string): string {
	return sectionId.includes(".")
		? sectionId
		: `第${toChineseChapterNumber(sectionId)}章`;
}

export function getLeafSectionHeading(section: LeafSection): string {
	const rawTitle = cleanText(section.title);
	const title = section.section_id.includes(".")
		? rawTitle
		: stripTopLevelTitlePrefix(rawTitle);
	const label = getLeafSectionLabel(section.section_id);
	if (!title) return label;
	return section.section_id.includes(".")
		? `${label} ${title}`
		: `${label}：${title}`;
}

export function getLeafSectionDescription(section: LeafSection): string {
	return cleanText(section.description) || "本节内容等待课程 Agent 补充。";
}

export function getLeafComposedSection(
	response: LeafCourseResponse,
	sectionId: string | null,
): LeafComposedSection | null {
	if (!sectionId) return null;
	return response.section_composed_markdowns[sectionId] ?? null;
}

export function hasLeafComposedContent(
	response: LeafCourseResponse,
	sectionId: string,
): boolean {
	const composed = response.section_composed_markdowns[sectionId];
	if (!composed) return false;
	return composed.blocks.length > 0 || cleanText(composed.markdown).length > 0;
}

export function isLeafSection(
	sections: LeafSection[],
	section: LeafSection,
): boolean {
	return !sections.some(
		(item) => item.parent_section_id === section.section_id,
	);
}

export function getDefaultLeafSectionId(
	response: LeafCourseResponse,
): string | null {
	const orderedSections = getOrderedLeafSections(response.sections);
	const generatedLeafSection = orderedSections.find(
		(section) =>
			isLeafSection(orderedSections, section) &&
			hasLeafComposedContent(response, section.section_id),
	);
	if (generatedLeafSection) return generatedLeafSection.section_id;

	const firstTopLevelSection = orderedSections.find(
		(section) => section.parent_section_id === null,
	);
	return (
		firstTopLevelSection?.section_id ?? orderedSections[0]?.section_id ?? null
	);
}

export function findLeafSectionById(
	sections: LeafSection[],
	sectionId: string | null,
): LeafSection | null {
	if (!sectionId) return null;
	return sections.find((section) => section.section_id === sectionId) ?? null;
}

export function getTopLevelSectionForLeaf(
	sections: LeafSection[],
	section: LeafSection | null,
): LeafSection | null {
	if (!section) return null;
	let currentSection = section;
	while (currentSection.parent_section_id) {
		const parentSection = findLeafSectionById(
			sections,
			currentSection.parent_section_id,
		);
		if (!parentSection) return currentSection;
		currentSection = parentSection;
	}
	return currentSection;
}
