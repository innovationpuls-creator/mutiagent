import { AnimatePresence, motion } from "framer-motion";
import { PenTool, X } from "lucide-react";
import { type ChangeEvent, useState } from "react";
import { Link } from "react-router-dom";
import { MarkdownRenderer } from "../../components/markdown/MarkdownRenderer";
import {
	type ModelErrorInfo,
	ModelGuidanceCard,
} from "../../components/models/ModelGuidanceCard";
import { ModelQuickSwitcher } from "../../components/models/ModelQuickSwitcher";
import { MessageBubble } from "../../components/onboarding/MessageBubble";
import { Button } from "../../components/ui/Button";
import {
	FeedbackState,
	type FeedbackStateVariant,
} from "../../components/ui/FeedbackState";
import { HandwritingCanvas } from "../../components/ui/HandwritingCanvas";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { motionTokens } from "../../styles/motion-tokens";
import type {
	ForestAiContext,
	ForestAttempt,
	ForestQuiz,
	ForestQuizQuestion,
	ForestQuizSession,
} from "../../types/forest";
export interface ForestMessage {
	id: string;
	role: "user" | "assistant";
	content: string;
	imageAttachment?: string | null;
}

export type ForestPageStatus = "idle" | "loading" | "ready" | "error";
export type ForestAiStatus = "idle" | "streaming" | "error";

export interface ForestAnswerDraft {
	question_id: string;
	value: unknown;
}

export interface EmptyForestStateProps {
	variant: FeedbackStateVariant;
	title: string;
	message: string;
	ariaLabel: string;
}

export interface ForestQuestionPanelProps {
	session: ForestQuizSession;
	quiz: ForestQuiz | null;
	attempt: ForestAttempt | null;
	selectedQuestion: ForestQuizQuestion | null;
	selectedAnswer: unknown;
	canSubmit: boolean;
	isSubmitting: boolean;
	isGenerating: boolean;
	errorMessage: string | null;
	reduceMotion: boolean;
	onSelectQuestion(questionId: string): void;
	onUpdateAnswer(questionId: string, value: unknown): void;
	onImageReading?(reading: boolean): void;
	onGenerateQuiz(): void;
	onSubmit(): void;
}

export interface ForestQuestionCardProps {
	question: ForestQuizQuestion;
	selectedAnswer: unknown;
	reduceMotion: boolean;
	onUpdateAnswer(questionId: string, value: unknown): void;
	onImageReading?(reading: boolean): void;
}

export interface ForestAiPanelProps {
	quiz: ForestQuiz | null;
	attempt: ForestAttempt | null;
	selectedQuestion: ForestQuizQuestion | null;
	aiStatus: ForestAiStatus;
	aiGuidance?: ModelErrorInfo | null;
	messages: ForestMessage[];
	reduceMotion: boolean;
	onAskForestAi(customMessage?: string, attachment?: string | null): void;
}

export function getAnswerValue(
	answers: ForestAnswerDraft[],
	questionId: string,
): unknown {
	return (
		answers.find((answer) => answer.question_id === questionId)?.value ?? ""
	);
}

export function toAnswerRecord(
	answers: ForestAnswerDraft[],
): Record<string, unknown> {
	return answers.reduce<Record<string, unknown>>((record, answer) => {
		if (typeof answer.value === "string" && answer.value.trim() === "")
			return record;
		record[answer.question_id] = answer.value;
		return record;
	}, {});
}

export function getQuestionResult(
	attempt: ForestAttempt | null,
	questionId: string | null,
): Record<string, unknown> | null {
	const questionResults = attempt?.grading_result.question_results;
	if (!Array.isArray(questionResults) || !questionId) return null;
	const result = questionResults.find(
		(item) =>
			item !== null &&
			typeof item === "object" &&
			"question_id" in item &&
			item.question_id === questionId,
	);
	return result && typeof result === "object"
		? (result as Record<string, unknown>)
		: null;
}

export function getResultText(attempt: ForestAttempt | null): string {
	if (!attempt) return "提交后，AI 助教会结合判题结果继续讲解。";
	const summary = attempt.grading_result.summary;
	if (typeof summary === "string" && summary.trim()) return summary;
	return attempt.passed ? "本次测验已通过。" : "本次测验还需要继续打磨。";
}

export function getUploadedFileName(answer: unknown): string {
	if (answer === null || typeof answer !== "object" || !("file_name" in answer))
		return "";
	const fileName = answer.file_name;
	return typeof fileName === "string" ? fileName : "";
}

export function readImageAnswer(file: File): Promise<Record<string, string>> {
	return new Promise((resolve, reject) => {
		const reader = new FileReader();
		reader.onload = () => {
			resolve({
				file_name: file.name,
				mime_type: file.type,
				data_url: typeof reader.result === "string" ? reader.result : "",
			});
		};
		reader.onerror = () => reject(new Error("图片读取失败"));
		reader.readAsDataURL(file);
	});
}

export function buildAiContext(
	courseNodeId: string,
	chapterId: string,
	quiz: ForestQuiz | null,
	question: ForestQuizQuestion | null,
	answer: unknown,
	attempt: ForestAttempt | null,
): ForestAiContext {
	return {
		course_node_id: courseNodeId,
		chapter_id: chapterId,
		quiz_id: quiz?.quiz_id ?? null,
		question_id: question?.question_id ?? null,
		question,
		answer,
		grading_result:
			getQuestionResult(attempt, question?.question_id ?? null) ??
			attempt?.grading_result ??
			null,
	};
}

export function initAnswers(
	questions: ForestQuizQuestion[],
): ForestAnswerDraft[] {
	return questions
		.filter((q) => q.type === "code" && q.starter_code)
		.map((q) => ({ question_id: q.question_id, value: q.starter_code }));
}

const QUESTION_TYPE_LABELS: Record<ForestQuizQuestion["type"], string> = {
	single_choice: "单选题",
	code: "代码题",
	image_upload: "图片题",
};

export function EmptyForestState({
	variant,
	title,
	message,
	ariaLabel,
}: EmptyForestStateProps) {
	return (
		<section className="forest-quiz-page" aria-label={ariaLabel}>
			<FeedbackState
				className="forest-empty-state"
				variant={variant}
				title={title}
				description={message}
				actions={
					<>
						<Link className="button button-secondary button-sm" to="/forest">
							返回章节列表
						</Link>
						<Button size="sm" onClick={() => window.location.reload()}>
							重新加载
						</Button>
					</>
				}
			/>
		</section>
	);
}

export function ForestQuestionCard({
	question,
	selectedAnswer,
	reduceMotion,
	onUpdateAnswer,
	onImageReading,
}: ForestQuestionCardProps) {
	const [imageError, setImageError] = useState("");
	const handleImageChange = async (event: ChangeEvent<HTMLInputElement>) => {
		const file = event.target.files?.[0];
		if (!file) return;
		onImageReading?.(true);
		setImageError("");
		try {
			onUpdateAnswer(question.question_id, await readImageAnswer(file));
		} catch {
			setImageError("图片读取失败，请重新选择图片");
		} finally {
			onImageReading?.(false);
		}
	};
	const uploadedFileName = getUploadedFileName(selectedAnswer);

	return (
		<motion.article
			key={question.question_id}
			className="forest-question-card"
			initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
			animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
			exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
			transition={motionTokens.lazy}
		>
			<div className="forest-question-meta">
				<StatusBadge variant="pill" tone="info" showDot={false}>
					{QUESTION_TYPE_LABELS[question.type]}
				</StatusBadge>
				<StatusBadge variant="pill" tone="accent" showDot={false}>
					{question.points} 分
				</StatusBadge>
			</div>
			<h2>{question.prompt}</h2>
			{imageError && <p role="alert">{imageError}</p>}
			{question.type === "single_choice" ? (
				<div className="forest-options" role="radiogroup" aria-label="选择答案">
					{question.options.map((option) => (
						<label key={option.option_id} className="forest-option">
							<input
								type="radio"
								name={question.question_id}
								value={option.option_id}
								checked={selectedAnswer === option.option_id}
								onChange={() =>
									onUpdateAnswer(question.question_id, option.option_id)
								}
							/>
							<span>{option.text}</span>
						</label>
					))}
				</div>
			) : question.type === "image_upload" ? (
				<label className="forest-upload-box">
					<input
						type="file"
						accept="image/png,image/jpeg,image/webp"
						onChange={handleImageChange}
					/>
					<span>
						{uploadedFileName || question.image_prompt || "上传图片答案"}
					</span>
				</label>
			) : (
				<textarea
					className="forest-answer-box"
					aria-label="代码答案"
					value={typeof selectedAnswer === "string" ? selectedAnswer : ""}
					onChange={(event) =>
						onUpdateAnswer(question.question_id, event.target.value)
					}
					placeholder={
						question.type === "code"
							? question.starter_code
							: question.image_prompt
					}
				/>
			)}
		</motion.article>
	);
}

export function ForestQuestionPanel({
	session,
	quiz,
	attempt,
	selectedQuestion,
	selectedAnswer,
	canSubmit,
	isSubmitting,
	isGenerating,
	errorMessage,
	reduceMotion,
	onSelectQuestion,
	onUpdateAnswer,
	onImageReading,
	onGenerateQuiz,
	onSubmit,
}: ForestQuestionPanelProps) {
	return (
		<motion.div
			className="forest-question-panel"
			initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
			animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
			transition={motionTokens.editorial}
		>
			<header className="forest-panel-header">
				<span>章节测验</span>
				<h1>{session.chapter.title}</h1>
				<p>{session.course.course_or_chapter_theme}</p>
			</header>

			{quiz ? (
				<>
					<nav className="forest-question-tabs" aria-label="题目列表">
						{quiz.questions.map((question, index) => (
							<button
								key={question.question_id}
								type="button"
								className={
									question.question_id === selectedQuestion?.question_id
										? "is-active"
										: ""
								}
								onClick={() => onSelectQuestion(question.question_id)}
							>
								{index + 1}
							</button>
						))}
					</nav>

					<AnimatePresence mode="wait">
						{selectedQuestion && (
							<ForestQuestionCard
								question={selectedQuestion}
								selectedAnswer={selectedAnswer}
								reduceMotion={reduceMotion}
								onUpdateAnswer={onUpdateAnswer}
								onImageReading={onImageReading}
							/>
						)}
					</AnimatePresence>

					<div className="forest-actions">
						<p>{getResultText(attempt)}</p>
						<Button onClick={onSubmit} disabled={!canSubmit || isSubmitting}>
							{isSubmitting ? "提交中" : "提交测验"}
						</Button>
					</div>
				</>
			) : (
				<div className="forest-empty-quiz">
					<h2>这一章还没有题目</h2>
					<p>生成后即可开始作答，AI 助教会结合当前题目为你讲解。</p>
					<Button onClick={onGenerateQuiz} disabled={isGenerating}>
						{isGenerating ? "生成中" : "生成测验"}
					</Button>
				</div>
			)}

			{errorMessage && <p className="forest-inline-error">{errorMessage}</p>}
		</motion.div>
	);
}

export function ForestAiPanel({
	quiz,
	aiStatus,
	aiGuidance,
	messages,
	reduceMotion,
	onAskForestAi,
}: ForestAiPanelProps) {
	const [showCanvas, setShowCanvas] = useState(false);
	const [imageAttachment, setImageAttachment] = useState<string | null>(null);
	const [inputValue, setInputValue] = useState("");

	return (
		<motion.aside
			className="forest-ai-panel"
			initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 16 }}
			animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
			transition={motionTokens.editorial}
			aria-label="AI 助教对话解析"
		>
			<header className="forest-ai-header">
				<span>AI 助教</span>
			</header>
			{messages.length > 0 && (
				<div className="forest-ai-messages-scroll">
					<div className="forest-ai-messages-list">
						{messages.map((message) => {
							if (message.role === "user") {
								return (
									<div
										key={message.id}
										className="forest-message-bubble-user-container"
									>
										<MessageBubble
											content={message.content}
											imageAttachment={message.imageAttachment}
										/>
									</div>
								);
							} else {
								return (
									<div
										key={message.id}
										className="forest-message-bubble-assistant"
									>
										<MarkdownRenderer content={message.content} />
									</div>
								);
							}
						})}
					</div>
				</div>
			)}
			{messages.length === 0 && (
				<Button
					className="forest-ask-initial-button"
					onClick={() => onAskForestAi()}
					disabled={aiStatus === "streaming" || !quiz}
				>
					{aiStatus === "streaming" ? "解析中" : "请 AI 助教解析"}
				</Button>
			)}

			{aiGuidance && <ModelGuidanceCard info={aiGuidance} />}
			{quiz && (
				<div className="forest-composer-container">
					<ModelQuickSwitcher />
					{imageAttachment && (
						<div className="image-preview-box">
							<img
								src={imageAttachment}
								alt="预览"
								className="preview-thumbnail"
							/>
							<Button
								variant="icon"
								size="sm"
								className="delete-preview-button"
								aria-label="移除图片"
								icon={<X aria-hidden="true" />}
								onClick={() => setImageAttachment(null)}
							/>
						</div>
					)}
					<form
						className="chat-composer"
						onSubmit={(e) => {
							e.preventDefault();
							if (
								aiStatus === "streaming" ||
								(!inputValue.trim() && !imageAttachment)
							)
								return;
							onAskForestAi(inputValue, imageAttachment);
							setInputValue("");
							setImageAttachment(null);
						}}
					>
						<Button
							variant="icon"
							size="sm"
							className="pen-button"
							onClick={() => setShowCanvas(true)}
							title="手写画板"
							aria-label="手写画板"
							disabled={aiStatus === "streaming"}
							icon={<PenTool aria-hidden="true" />}
						/>
						<textarea
							value={inputValue}
							onChange={(e) => setInputValue(e.target.value)}
							rows={1}
							placeholder="向 AI 助教追问…"
							disabled={aiStatus === "streaming"}
							onKeyDown={(e) => {
								if (e.key === "Enter" && !e.shiftKey) {
									e.preventDefault();
									if (
										aiStatus === "streaming" ||
										(!inputValue.trim() && !imageAttachment)
									)
										return;
									onAskForestAi(inputValue, imageAttachment);
									setInputValue("");
									setImageAttachment(null);
								}
							}}
						/>
						<Button
							type="submit"
							size="sm"
							className="submit-button"
							disabled={
								aiStatus === "streaming" ||
								(!inputValue.trim() && !imageAttachment)
							}
						>
							发送
						</Button>
					</form>
				</div>
			)}

			{showCanvas && (
				<HandwritingCanvas
					onSave={(data) => {
						setImageAttachment(data);
						setShowCanvas(false);
					}}
					onClose={() => setShowCanvas(false)}
				/>
			)}
		</motion.aside>
	);
}
