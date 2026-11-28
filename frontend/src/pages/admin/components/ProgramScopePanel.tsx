import { ChevronDown, PencilLine } from "lucide-react";
import { useState } from "react";
import { Button } from "../../../components/ui/Button";
import { StatusBadge } from "../../../components/ui/StatusBadge";

export interface ProgramScope {
	school: string;
	major: string;
	className: string;
}

interface ProgramScopePanelProps {
	scope: ProgramScope;
	scopeOptions: ProgramScope[];
	onChange: (nextScope: ProgramScope) => void;
}

type ProgramScopeKey = keyof ProgramScope;

function uniqueValues(values: string[]): string[] {
	return Array.from(
		new Set(values.map((value) => value.trim()).filter(Boolean)),
	);
}

export function ProgramScopePanel({
	scope,
	scopeOptions,
	onChange,
}: ProgramScopePanelProps) {
	const [openField, setOpenField] = useState<ProgramScopeKey | null>(null);
	const setScopeField = (key: ProgramScopeKey, value: string) => {
		onChange({ ...scope, [key]: value });
	};

	const currentSchool = scope.school.trim();
	const currentMajor = scope.major.trim();
	const schoolOptions = uniqueValues(
		scopeOptions.map((option) => option.school),
	);
	const schoolMatchedScopes = scopeOptions.filter(
		(option) => !currentSchool || option.school === currentSchool,
	);
	const majorSourceScopes =
		schoolMatchedScopes.length > 0 ? schoolMatchedScopes : scopeOptions;
	const majorOptions = uniqueValues(
		majorSourceScopes.map((option) => option.major),
	);
	const majorMatchedScopes = majorSourceScopes.filter(
		(option) => !currentMajor || option.major === currentMajor,
	);
	const classSourceScopes =
		majorMatchedScopes.length > 0 ? majorMatchedScopes : majorSourceScopes;
	const classNameOptions = uniqueValues(
		classSourceScopes.map((option) => option.className),
	);
	const scopeItems = [
		{
			key: "school",
			label: "学校",
			value: scope.school,
			placeholder: schoolOptions[0] ?? "填写学生账号中的学校",
			helper: "需与学生账号中填写的学校名称完全一致。",
			options: schoolOptions,
		},
		{
			key: "major",
			label: "专业",
			value: scope.major,
			placeholder: majorOptions[0] ?? "填写学生账号中的专业",
			helper: "选定学校后，会优先提示该学校已有专业。",
			options: majorOptions,
		},
		{
			key: "className",
			label: "班级",
			value: scope.className,
			placeholder: classNameOptions[0] ?? "填写学生账号中的班级",
			helper: "发布后只匹配这个班的学生。",
			options: classNameOptions,
		},
	] as const;
	const hasCompleteScope = scopeItems.every((item) => item.value.trim());
	// 已填完整的范围默认收起成一行摘要，把首屏留给课程编排；未填完时展开表单。
	// null 表示跟随数据自动判断（范围异步加载完成后自动收起）；用户一旦聚焦输入框就进入显式编辑，避免输入中途被收起。
	const [editMode, setEditMode] = useState<boolean | null>(null);
	const isEditing = editMode ?? !hasCompleteScope;
	const setIsEditing = (next: boolean) => setEditMode(next);

	if (hasCompleteScope && !isEditing) {
		return (
			<section
				className="program-scope-panel program-scope-collapsed"
				aria-labelledby="program-scope-title"
			>
				<h2 id="program-scope-title">发布范围</h2>
				<p className="program-scope-inline">
					{scope.school} · {scope.major} · {scope.className}
				</p>
				<Button
					variant="ghost"
					size="sm"
					icon={<PencilLine aria-hidden="true" />}
					onClick={() => setIsEditing(true)}
				>
					修改
				</Button>
			</section>
		);
	}

	return (
		<section
			className="program-scope-panel"
			aria-labelledby="program-scope-title"
		>
			<div className="program-scope-copy">
				<h2 id="program-scope-title">发布范围</h2>
				<p>
					这份方案发给哪个班：学生账号里的学校、专业、班级与这里完全一致时，才会用这份方案生成学习路径。
				</p>
			</div>
			<div className="program-scope-summary">
				<div className="program-scope-fields">
					{scopeItems.map((item) => (
						<div className="program-scope-field" key={item.key}>
							<label htmlFor={`program-${item.key}`}>{item.label}</label>
							<div className="program-scope-combobox">
								<input
									id={`program-${item.key}`}
									aria-label={item.label}
									aria-expanded={openField === item.key}
									aria-controls={`program-${item.key}-listbox`}
									aria-autocomplete="list"
									role="combobox"
									value={item.value}
									onFocus={() => {
										setOpenField(item.key);
										setEditMode(true);
									}}
									onChange={(event) => {
										setScopeField(item.key, event.target.value);
										setOpenField(item.key);
									}}
									placeholder={item.placeholder}
								/>
								<button
									type="button"
									aria-label={`展开${item.label}选项`}
									className="program-scope-dropdown-btn"
									onClick={() =>
										setOpenField(openField === item.key ? null : item.key)
									}
								>
									<ChevronDown size={14} aria-hidden="true" />
								</button>
								{openField === item.key ? (
									<div
										className="program-scope-listbox"
										id={`program-${item.key}-listbox`}
										role="listbox"
										aria-label={`${item.label}选项`}
									>
										{item.options.length > 0 ? (
											item.options.slice(0, 8).map((option) => (
												<button
													type="button"
													className={
														option === item.value.trim()
															? "program-scope-list-option is-active"
															: "program-scope-list-option"
													}
													key={option}
													role="option"
													aria-selected={option === item.value.trim()}
													onMouseDown={(event) => event.preventDefault()}
													onClick={() => {
														setScopeField(item.key, option);
														setOpenField(null);
													}}
												>
													{option}
												</button>
											))
										) : (
											<span className="program-scope-list-empty">
												暂无已有数据，可手动填写。
											</span>
										)}
									</div>
								) : null}
							</div>
							<small>{item.helper}</small>
						</div>
					))}
				</div>
				<div className="program-scope-footer">
					<StatusBadge
						className="program-scope-status"
						tone={hasCompleteScope ? "success" : "warning"}
					>
						{hasCompleteScope
							? "发布范围已填写，请确认和学生账号完全一致"
							: "学校、专业、班级都填写后才能发布"}
					</StatusBadge>
					{hasCompleteScope ? (
						<Button
							variant="secondary"
							size="sm"
							onClick={() => {
								setOpenField(null);
								setIsEditing(false);
							}}
						>
							完成
						</Button>
					) : null}
				</div>
			</div>
		</section>
	);
}
