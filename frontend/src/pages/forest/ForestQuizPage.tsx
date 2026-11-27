import { useReducedMotion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
	ForestSubmissionError,
	fetchForestQuizSession,
	fetchForestSubmission,
	generateForestQuiz,
	streamForestAi,
	submitForestQuizAttemptStream,
} from "../../api/forest";
import { ForestQuizOverlay } from "../../components/forest/ForestQuizOverlay";
import { useAuth } from "../../contexts/AuthContext";
import { DraftNavigationGuard } from "../../lib/quizDraft/DraftNavigationGuard";
import type { PendingSubmission, QuizDraft } from "../../lib/quizDraft/store";
import { useQuizDraft } from "../../lib/quizDraft/useQuizDraft";
import type {
	ForestAttempt,
	ForestQuiz,
	ForestQuizSession,
	ForestSubmitStreamDonePayload,
} from "../../types/forest";
import {
	buildAiContext,
	EmptyForestState,
	ForestAiPanel,
	type ForestAiStatus,
	type ForestAnswerDraft,
	type ForestMessage,
	type ForestPageStatus,
	ForestQuestionPanel,
	getAnswerValue,
	initAnswers,
	toAnswerRecord,
} from "./ForestQuizPanels";
import "./forest-quiz.css";

export function ForestQuizPage() {
	const { courseNodeId } = useParams<{ courseNodeId: string }>();
	const [searchParams] = useSearchParams();
	const { token, user } = useAuth();
	const reduceMotion = useReducedMotion() ?? false;
	const chapterId = searchParams.get("chapter_id");

	const routeIdentity = `${user?.uid}/${courseNodeId}/${chapterId}`;
	const routeIdentityRef = useRef(routeIdentity);
	routeIdentityRef.current = routeIdentity;
	const [loadedIdentity, setLoadedIdentity] = useState("");

	const [status, setStatus] = useState<ForestPageStatus>("idle");
	const [session, setSession] = useState<ForestQuizSession | null>(null);
	const [quiz, setQuiz] = useState<ForestQuiz | null>(null);
	const [attempt, setAttempt] = useState<ForestAttempt | null>(null);
	const [selectedQuestionId, setSelectedQuestionId] = useState<string | null>(
		null,
	);
	const [answers, setAnswers] = useState<ForestAnswerDraft[]>([]);
	const [errorMessage, setErrorMessage] = useState<string | null>(null);
	const [isGenerating, setIsGenerating] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [submitStatusMessage, setSubmitStatusMessage] = useState<string | null>(
		null,
	);
	const [aiStatus, setAiStatus] = useState<ForestAiStatus>("idle");
	const [messages, setMessages] = useState<ForestMessage[]>([]);

	const selectQuestion = useCallback((questionId: string | null) => {
		setSelectedQuestionId(questionId);
		setMessages([]);
	}, []);

	const selectedQuestion = useMemo(() => {
		if (!quiz) return null;
		return (
			quiz.questions.find(
				(question) => question.question_id === selectedQuestionId,
			) ??
			quiz.questions[0] ??
			null
		);
	}, [quiz, selectedQuestionId]);

	const selectedAnswer = selectedQuestion
		? getAnswerValue(answers, selectedQuestion.question_id)
		: "";
	const [imageReading, setImageReading] = useState(false);
	const canSubmit = Boolean(
		!imageReading &&
			quiz &&
			quiz.questions.length > 0 &&
			Object.keys(toAnswerRecord(answers)).length === quiz.questions.length,
	);

	const loadSession = useCallback(async () => {
		if (!token || !courseNodeId || !chapterId) return;
		const requestIdentity = routeIdentity;
		setStatus("loading");
		setImageReading(false);
		setErrorMessage(null);
		try {
			const nextSession = await fetchForestQuizSession(
				token,
				courseNodeId,
				chapterId,
			);
			if (requestIdentity !== routeIdentityRef.current) return;
			setLoadedIdentity(requestIdentity);
			setSession(nextSession);
			setQuiz(nextSession.quiz);
			setAttempt(nextSession.latest_attempt);
			selectQuestion(nextSession.quiz?.questions[0]?.question_id ?? null);
			if (
				nextSession.latest_attempt?.quiz_version &&
				nextSession.latest_attempt.quiz_version ===
					nextSession.quiz?.quiz_version
			) {
				const attemptAnswers = Object.entries(
					nextSession.latest_attempt.answers,
				).map(([qId, val]) => ({
					question_id: qId,
					value: val,
				}));
				setAnswers(attemptAnswers);
			} else if (nextSession.quiz) {
				setAnswers(initAnswers(nextSession.quiz.questions));
			} else {
				setAnswers([]);
			}
			setStatus("ready");
		} catch (error) {
			if (requestIdentity !== routeIdentityRef.current) return;
			setErrorMessage(
				error instanceof Error ? error.message : "成林测验加载失败",
			);
			setStatus("error");
		}
	}, [chapterId, courseNodeId, selectQuestion, token, routeIdentity]);

	useEffect(() => {
		void loadSession();
	}, [loadSession]);

	const draftAnswers = useMemo(() => toAnswerRecord(answers), [answers]);
	const scope = useMemo(
		() =>
			loadedIdentity === routeIdentity &&
			status === "ready" &&
			user &&
			quiz?.quiz_version &&
			courseNodeId &&
			chapterId
				? {
						uid: user.uid,
						courseId: courseNodeId,
						chapterId,
						quizId: quiz.quiz_id,
						version: quiz.quiz_version,
					}
				: null,
		[
			user,
			quiz,
			courseNodeId,
			chapterId,
			loadedIdentity,
			routeIdentity,
			status,
		],
	);
	const restoreDraft = useCallback((saved: QuizDraft) => {
		setAnswers(
			Object.entries(saved.answers).map(([question_id, value]) => ({
				question_id,
				value,
			})),
		);
		setSelectedQuestionId(saved.selectedQuestionId);
	}, []);
	const draft = useQuizDraft(
		scope,
		draftAnswers,
		selectedQuestionId,
		restoreDraft,
	);
	const saveBeforeLeaving = useCallback(async () => {
		if (imageReading) throw new Error("图片仍在读取，请稍后重试保存");
		await draft.save();
	}, [imageReading, draft.save]);
	const scopeIdentity = `${user?.uid}/${courseNodeId}/${chapterId}/${quiz?.quiz_version}`;
	const scopeIdentityRef = useRef(scopeIdentity);
	scopeIdentityRef.current = scopeIdentity;
	const submissionBusyRef = useRef(false);
	const [submissionInvalid, setSubmissionInvalid] = useState(false);

	const updateAnswer = useCallback(
		(questionId: string, value: unknown) => {
			if (submissionBusyRef.current || draft.pending) return;
			draft.markDirty();
			setAnswers((currentAnswers) => {
				const exists = currentAnswers.some(
					(answer) => answer.question_id === questionId,
				);
				if (exists) {
					return currentAnswers.map((answer) =>
						answer.question_id === questionId
							? { question_id: questionId, value }
							: answer,
					);
				}
				return [...currentAnswers, { question_id: questionId, value }];
			});
		},
		[draft.pending, draft.markDirty],
	);

	const handleGenerateQuiz = useCallback(async () => {
		if (!token || !courseNodeId || !chapterId) return;
		const requestIdentity = routeIdentity;
		setIsGenerating(true);
		setErrorMessage(null);
		try {
			const nextQuiz = await generateForestQuiz(
				token,
				courseNodeId,
				chapterId,
				false,
			);
			if (requestIdentity !== routeIdentityRef.current) return;
			setQuiz(nextQuiz);
			selectQuestion(nextQuiz.questions[0]?.question_id ?? null);
			setAnswers(initAnswers(nextQuiz.questions));
			setAttempt(null);
		} catch (error) {
			if (requestIdentity !== routeIdentityRef.current) return;
			setErrorMessage(
				error instanceof Error ? error.message : "章节测验生成失败",
			);
		} finally {
			if (requestIdentity === routeIdentityRef.current) setIsGenerating(false);
		}
	}, [chapterId, courseNodeId, selectQuestion, token, routeIdentity]);

	const askForestAi = useCallback(
		async (
			customMessage?: string,
			attachment?: string | null,
			nextAttempt: ForestAttempt | null = attempt,
		) => {
			if (!token || !courseNodeId || !chapterId) return;
			const context = buildAiContext(
				courseNodeId,
				chapterId,
				quiz,
				selectedQuestion,
				selectedAnswer,
				nextAttempt,
			);

			const promptText =
				customMessage || "请结合当前题目、我的答案与判题结果，给出简洁解析。";

			const userMsg: ForestMessage = {
				id: `user-${Date.now()}`,
				role: "user",
				content: promptText,
				imageAttachment: attachment,
			};

			const assistantMsgId = `assistant-${Date.now()}`;
			const assistantMsg: ForestMessage = {
				id: assistantMsgId,
				role: "assistant",
				content: "",
			};

			setMessages((prev) => [...prev, userMsg, assistantMsg]);
			setAiStatus("streaming");

			try {
				await streamForestAi(
					token,
					context,
					promptText,
					(event) => {
						if (event.event === "forest_ai_text_chunk" && event.chunk) {
							setMessages((prev) =>
								prev.map((msg) =>
									msg.id === assistantMsgId
										? { ...msg, content: msg.content + event.chunk }
										: msg,
								),
							);
						}
						if (event.event === "forest_error") {
							setAiStatus("error");
							setMessages((prev) =>
								prev.map((msg) =>
									msg.id === assistantMsgId
										? {
												...msg,
												content: event.message ?? "Forest AI 暂时不可用",
											}
										: msg,
								),
							);
						}
						if (event.event === "forest_ai_completed") {
							setAiStatus("idle");
						}
					},
					attachment,
				);
			} catch (error) {
				setAiStatus("error");
				const errMsg =
					error instanceof Error ? error.message : "Forest AI 暂时不可用";
				setMessages((prev) =>
					prev.map((msg) =>
						msg.id === assistantMsgId ? { ...msg, content: errMsg } : msg,
					),
				);
			}
		},
		[
			chapterId,
			courseNodeId,
			quiz,
			selectedAnswer,
			selectedQuestion,
			token,
			attempt,
		],
	);

	// ----------- Overlay state -----------
	const [overlayOpen, setOverlayOpen] = useState(false);
	const doneDataRef = useRef<ForestSubmitStreamDonePayload | null>(null);

	const acceptResult = useCallback(
		async (result: ForestSubmitStreamDonePayload) => {
			setAttempt(result.attempt);
			doneDataRef.current = result;
			setOverlayOpen(true);
			setErrorMessage(null);
			setSubmitStatusMessage(null);
			try {
				await draft.complete();
			} catch {
				setErrorMessage(
					"成绩已保存，本机草稿清理失败；再次进入时会重新确认结果",
				);
			}
		},
		[draft.complete],
	);
	const confirmSubmission = useCallback(
		async (pending: PendingSubmission) => {
			if (!token || !quiz || !courseNodeId || !chapterId) return false;
			const identity = scopeIdentityRef.current;
			setSubmitStatusMessage("正在确认本次提交结果…");
			try {
				const result = await fetchForestSubmission(
					token,
					quiz.quiz_id,
					pending.client_submission_id,
				);
				if (identity !== scopeIdentityRef.current) return false;
				if (result) {
					await acceptResult(result);
					return true;
				}
				const current = await fetchForestQuizSession(
					token,
					courseNodeId,
					chapterId,
				);
				if (current.quiz?.quiz_version !== pending.quiz_version) {
					setSubmissionInvalid(true);
					setErrorMessage("题目已更新，原草稿仍保留。请重新加载当前题目。");
					return false;
				}
				setErrorMessage(
					"尚未确认本次提交是否保存。请重新查询，或使用原答案重试；本机草稿仍保留。",
				);
			} catch (error) {
				if (identity === scopeIdentityRef.current) {
					if (
						error instanceof ForestSubmissionError &&
						[403, 404, 409].includes(error.status)
					)
						setSubmissionInvalid(true);
					setErrorMessage(
						error instanceof Error ? error.message : "结果查询失败，请重试",
					);
				}
			} finally {
				if (identity === scopeIdentityRef.current) setSubmitStatusMessage(null);
			}
			return false;
		},
		[token, quiz, acceptResult, courseNodeId, chapterId],
	);
	const resumedSubmissionRef = useRef("");
	useEffect(() => {
		if (!draft.ready || !draft.pending || !quiz || submissionBusyRef.current)
			return;
		const key = `${scopeIdentity}/${draft.pending.client_submission_id}`;
		if (resumedSubmissionRef.current === key) return;
		resumedSubmissionRef.current = key;
		void confirmSubmission(draft.pending);
	}, [draft.ready, draft.pending, quiz, scopeIdentity, confirmSubmission]);
	const handleSubmit = useCallback(async () => {
		if (
			!token ||
			!quiz ||
			(!canSubmit && !draft.pending) ||
			submissionBusyRef.current ||
			!draft.ready
		)
			return;
		const identity = scopeIdentityRef.current;
		submissionBusyRef.current = true;
		setIsSubmitting(true);
		setErrorMessage(null);
		const pending = draft.pending ?? {
			client_submission_id: crypto.randomUUID(),
			quiz_version: quiz.quiz_version,
			answers: toAnswerRecord(answers),
		};
		let result: ForestSubmitStreamDonePayload | null = null;
		let snapshotSaved = false;
		try {
			await draft.save(false, pending);
			snapshotSaved = true;
			await submitForestQuizAttemptStream(
				token,
				quiz.quiz_id,
				pending,
				(event) => {
					if (identity !== scopeIdentityRef.current) return;
					if (event.event === "status")
						setSubmitStatusMessage(event.message ?? "正在提交…");
					if (event.event === "done" && event.doneData) result = event.doneData;
					if (event.event === "error")
						throw new Error(event.message ?? "测验提交失败");
				},
			);
			if (result && identity === scopeIdentityRef.current) {
				await acceptResult(result);
				void askForestAi(
					undefined,
					null,
					(result as ForestSubmitStreamDonePayload).attempt,
				);
			} else if (identity === scopeIdentityRef.current)
				await confirmSubmission(pending);
		} catch (error) {
			if (identity === scopeIdentityRef.current) {
				setErrorMessage(
					error instanceof Error ? error.message : "测验提交失败",
				);
				if (
					error instanceof ForestSubmissionError &&
					[403, 404, 409].includes(error.status)
				)
					setSubmissionInvalid(true);
				else if (snapshotSaved) await confirmSubmission(pending);
			}
		} finally {
			submissionBusyRef.current = false;
			if (identity === scopeIdentityRef.current) {
				setIsSubmitting(false);
				setSubmitStatusMessage(null);
			}
		}
	}, [
		token,
		quiz,
		canSubmit,
		draft.pending,
		draft.ready,
		draft.save,
		answers,
		acceptResult,
		confirmSubmission,
		askForestAi,
	]);

	const handleAskForestAi = useCallback(
		(customMessage?: string, attachment?: string | null) => {
			void askForestAi(customMessage, attachment, attempt);
		},
		[askForestAi, attempt],
	);

	if (!token || !courseNodeId) {
		return null;
	}

	if (!chapterId) {
		return (
			<EmptyForestState
				ariaLabel="成林测验缺少章节"
				label="// forest"
				title="还没有选中章节"
				message="请从叶茂章节进入成林测验。"
			/>
		);
	}

	if (
		status === "loading" ||
		status === "idle" ||
		(status === "ready" && loadedIdentity !== routeIdentity)
	) {
		return (
			<EmptyForestState
				ariaLabel="成林测验加载中"
				label="// loading"
				title="正在准备章节测验"
				message="Forest AI 会在题目旁边等你。"
			/>
		);
	}

	if (status === "error" || !session) {
		return (
			<EmptyForestState
				ariaLabel="成林测验加载失败"
				label="// error"
				title="测验加载失败"
				message={errorMessage ?? "请稍后再试。"}
			/>
		);
	}

	return (
		<section
			className="forest-quiz-page"
			aria-label={`${session.chapter.title}章节测验`}
		>
			<div className="forest-paper-canvas" aria-hidden="true" />
			<DraftNavigationGuard
				dirty={draft.dirty || imageReading}
				save={saveBeforeLeaving}
			/>
			<div className="forest-draft-status" aria-live="polite">
				<p>{draft.message}</p>
				{draft.notice && <p>{draft.notice}</p>}
				{(draft.dirty || draft.conflict) && (
					<button
						type="button"
						onClick={() => {
							void draft.save().catch(() => {});
						}}
					>
						重试保存
					</button>
				)}
				{draft.conflict && (
					<>
						<button
							type="button"
							onClick={() => {
								void draft
									.reload()
									.catch(() => setErrorMessage("草稿读取失败，请重试"));
							}}
						>
							读取已保存草稿
						</button>
						<button
							type="button"
							onClick={() => {
								void draft.save(true).catch(() => {});
							}}
						>
							保留当前输入
						</button>
					</>
				)}
				{draft.pending && !isSubmitting && !submissionInvalid && (
					<>
						<button
							type="button"
							onClick={() => {
								if (draft.pending) void confirmSubmission(draft.pending);
							}}
						>
							重新查询提交结果
						</button>
						<button
							type="button"
							onClick={() => {
								void handleSubmit();
							}}
						>
							使用原答案重试
						</button>
						<Link to="/forest">返回章节列表</Link>
					</>
				)}
			</div>
			{submissionInvalid && (
				<div role="alert">
					<p>{errorMessage}</p>
					<button type="button" onClick={() => window.location.reload()}>
						重新加载题目
					</button>
					<Link to="/forest">返回章节列表</Link>
				</div>
			)}
			<main className="forest-quiz-shell">
				<fieldset
					className="forest-answer-fieldset"
					disabled={
						(Boolean(quiz) && !draft.ready) ||
						imageReading ||
						isSubmitting ||
						Boolean(draft.pending)
					}
				>
					<ForestQuestionPanel
						session={session}
						quiz={quiz}
						attempt={attempt}
						selectedQuestion={selectedQuestion}
						selectedAnswer={selectedAnswer}
						canSubmit={canSubmit && draft.ready && !draft.conflict}
						isSubmitting={isSubmitting}
						isGenerating={isGenerating}
						errorMessage={errorMessage}
						reduceMotion={reduceMotion}
						onSelectQuestion={(id) => {
							draft.markDirty();
							selectQuestion(id);
						}}
						onUpdateAnswer={updateAnswer}
						onImageReading={setImageReading}
						onGenerateQuiz={handleGenerateQuiz}
						onSubmit={handleSubmit}
					/>
				</fieldset>
				<details className="forest-ai-disclosure">
					<summary>AI 解析与帮助</summary>
					<ForestAiPanel
						quiz={quiz}
						attempt={attempt}
						selectedQuestion={selectedQuestion}
						aiStatus={aiStatus}
						messages={messages}
						reduceMotion={reduceMotion}
						onAskForestAi={handleAskForestAi}
					/>
				</details>
			</main>

			{submitStatusMessage && (
				<p className="forest-submit-status">{submitStatusMessage}</p>
			)}

			{doneDataRef.current && attempt && (
				<ForestQuizOverlay
					isOpen={overlayOpen}
					onClose={() => setOverlayOpen(false)}
					attempt={attempt}
					canopyOverview={doneDataRef.current.canopy_overview}
					nextUnlockedChapterId={doneDataRef.current.next_unlocked_chapter_id}
					nextCourseId={doneDataRef.current.next_course_id}
					courseNodeId={courseNodeId}
					weaknesses={doneDataRef.current.weaknesses}
					reduceMotion={reduceMotion}
				/>
			)}
		</section>
	);
}
