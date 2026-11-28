import type {
	InputHTMLAttributes,
	ReactNode,
	SelectHTMLAttributes,
	TextareaHTMLAttributes,
} from "react";
import { forwardRef, useId } from "react";

export type FieldStatus = "default" | "success" | "error";

interface BaseFieldProps {
	label: string;
	helperText?: string;
	errorMessage?: string;
	status?: FieldStatus;
	wrapperClassName?: string;
}

export interface TextFieldProps
	extends InputHTMLAttributes<HTMLInputElement>,
		BaseFieldProps {}

export interface TextAreaFieldProps
	extends TextareaHTMLAttributes<HTMLTextAreaElement>,
		BaseFieldProps {}

export interface SelectFieldProps
	extends SelectHTMLAttributes<HTMLSelectElement>,
		BaseFieldProps {
	children: ReactNode;
}

function resolveFieldStatus(
	status: FieldStatus | undefined,
	errorMessage: string | undefined,
): FieldStatus {
	if (errorMessage) return "error";
	return status ?? "default";
}

function joinDescribedBy(
	...ids: Array<string | undefined | false>
): string | undefined {
	const valid = ids.filter((value): value is string => Boolean(value));
	return valid.length > 0 ? valid.join(" ") : undefined;
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(
	function TextField(
		{
			label,
			helperText,
			errorMessage,
			status,
			wrapperClassName,
			className,
			id,
			...inputProps
		},
		ref,
	) {
		const generatedId = useId();
		const inputId = id ?? inputProps.name ?? generatedId;
		const helperId = helperText ? `${inputId}-helper` : undefined;
		const errorId = errorMessage ? `${inputId}-error` : undefined;
		const resolvedStatus = resolveFieldStatus(status, errorMessage);

		return (
			<div
				className={["text-field", wrapperClassName].filter(Boolean).join(" ")}
				data-status={resolvedStatus}
			>
				<label className="text-field-label" htmlFor={inputId}>
					{label}
				</label>
				<input
					ref={ref}
					id={inputId}
					className={["field-control", className].filter(Boolean).join(" ")}
					aria-invalid={
						resolvedStatus === "error" ? true : inputProps["aria-invalid"]
					}
					aria-describedby={joinDescribedBy(
						inputProps["aria-describedby"],
						helperId,
						errorId,
					)}
					{...inputProps}
				/>
				{helperText ? (
					<span className="text-field-helper" id={helperId}>
						{helperText}
					</span>
				) : null}
				{errorMessage ? (
					<p className="text-field-error" id={errorId} role="alert">
						{errorMessage}
					</p>
				) : null}
			</div>
		);
	},
);

export function TextAreaField({
	label,
	helperText,
	errorMessage,
	status,
	wrapperClassName,
	className,
	id,
	...textareaProps
}: TextAreaFieldProps) {
	const generatedId = useId();
	const inputId = id ?? textareaProps.name ?? generatedId;
	const helperId = helperText ? `${inputId}-helper` : undefined;
	const errorId = errorMessage ? `${inputId}-error` : undefined;
	const resolvedStatus = resolveFieldStatus(status, errorMessage);

	return (
		<div
			className={["text-field", wrapperClassName].filter(Boolean).join(" ")}
			data-status={resolvedStatus}
		>
			<label className="text-field-label" htmlFor={inputId}>
				{label}
			</label>
			<textarea
				id={inputId}
				className={["field-control", className].filter(Boolean).join(" ")}
				aria-invalid={
					resolvedStatus === "error" ? true : textareaProps["aria-invalid"]
				}
				aria-describedby={joinDescribedBy(
					textareaProps["aria-describedby"],
					helperId,
					errorId,
				)}
				{...textareaProps}
			/>
			{helperText ? (
				<span className="text-field-helper" id={helperId}>
					{helperText}
				</span>
			) : null}
			{errorMessage ? (
				<p className="text-field-error" id={errorId} role="alert">
					{errorMessage}
				</p>
			) : null}
		</div>
	);
}

export function SelectField({
	label,
	helperText,
	errorMessage,
	status,
	wrapperClassName,
	className,
	id,
	children,
	...selectProps
}: SelectFieldProps) {
	const generatedId = useId();
	const inputId = id ?? selectProps.name ?? generatedId;
	const helperId = helperText ? `${inputId}-helper` : undefined;
	const errorId = errorMessage ? `${inputId}-error` : undefined;
	const resolvedStatus = resolveFieldStatus(status, errorMessage);

	return (
		<div
			className={["text-field", wrapperClassName].filter(Boolean).join(" ")}
			data-status={resolvedStatus}
		>
			<label className="text-field-label" htmlFor={inputId}>
				{label}
			</label>
			<select
				id={inputId}
				className={["field-control", className].filter(Boolean).join(" ")}
				aria-invalid={
					resolvedStatus === "error" ? true : selectProps["aria-invalid"]
				}
				aria-describedby={joinDescribedBy(
					selectProps["aria-describedby"],
					helperId,
					errorId,
				)}
				{...selectProps}
			>
				{children}
			</select>
			{helperText ? (
				<span className="text-field-helper" id={helperId}>
					{helperText}
				</span>
			) : null}
			{errorMessage ? (
				<p className="text-field-error" id={errorId} role="alert">
					{errorMessage}
				</p>
			) : null}
		</div>
	);
}
