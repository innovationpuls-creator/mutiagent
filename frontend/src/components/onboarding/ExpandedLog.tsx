import { motion } from "framer-motion";
import React, { useEffect, useState } from "react";
import styled from "styled-components";
import type { AgentRunStep, ThoughtChunkEntry } from "../../types/chat";
import { formatStepKind, formatStepTitle } from "./stepLabels";

interface ExpandedLogProps {
	steps: AgentRunStep[];
}

function formatDuration(ms?: number): string {
	if (typeof ms !== "number" || Number.isNaN(ms) || ms < 0) return "";
	if (ms < 10) return `${ms.toFixed(1)}ms`;
	if (ms < 1000) return `${Math.round(ms)}ms`;
	return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}s`;
}

function StatusSymbol({ status }: { status: string }) {
	switch (status) {
		case "running":
			return <span className="console-cursor">_</span>;
		case "success":
			return <span className="console-check">✓</span>;
		case "error":
			return <span className="console-error">✗</span>;
		case "skipped":
			return <span className="console-skip">-</span>;
		default:
			return <span>{status}</span>;
	}
}

function getAgentKey(step: AgentRunStep): string | null {
	return step.agent ?? null;
}

function getStepContextDetails(step: AgentRunStep): string[] {
	const details: string[] = [];
	if (step.parallelGroup) details.push(`并行组 ${step.parallelGroup}`);
	if (step.dependsOn && step.dependsOn.length > 0)
		details.push(`依赖 ${step.dependsOn.join(" / ")}`);
	return details;
}

function getKindLabel(step: AgentRunStep): string {
	if (step.kind === "agent") return "智能体";
	return formatStepKind(step);
}

function ThoughtStream({ entries }: { entries: ThoughtChunkEntry[] }) {
	const fullText = entries.map((e) => e.text).join("");
	if (!fullText.trim()) return null;
	return (
		<ThoughtStreamShell>
			<span className="thought-text">{fullText}</span>
		</ThoughtStreamShell>
	);
}

const ThoughtStreamShell = styled.div`
  color: var(--dark-text-muted);

  .thought-text {
    word-break: break-word;
    white-space: pre-wrap;
  }
`;

export function ExpandedLog({ steps }: ExpandedLogProps) {
	const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

	useEffect(() => {
		if (
			typeof window === "undefined" ||
			typeof window.matchMedia !== "function"
		)
			return;

		const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
		const updatePreference = (event?: MediaQueryListEvent) => {
			setPrefersReducedMotion(event?.matches ?? mediaQuery.matches);
		};

		updatePreference();

		if (typeof mediaQuery.addEventListener === "function") {
			mediaQuery.addEventListener("change", updatePreference);
			return () => mediaQuery.removeEventListener("change", updatePreference);
		}

		mediaQuery.addListener(updatePreference);
		return () => mediaQuery.removeListener(updatePreference);
	}, []);

	return (
		<Shell data-testid="agent-log-stream">
			{steps.map((step, idx) => {
				const contextDetails = getStepContextDetails(step);
				const showDetails =
					step.summary ||
					contextDetails.length > 0 ||
					(step.status === "running" &&
						step.thoughtLog &&
						step.thoughtLog.length > 0);

				return (
					<StepRow
						key={step.stepId}
						data-testid={`agent-log-row-${step.stepId}`}
						data-status={step.status}
						data-kind={step.kind}
						data-highlighted={step.status === "running" ? "true" : "false"}
						as={motion.div}
						initial={
							prefersReducedMotion ? { opacity: 0 } : { opacity: 0, x: -4 }
						}
						animate={{ opacity: 1, x: 0 }}
						transition={{
							duration: prefersReducedMotion ? 0.12 : 0.35,
							ease: [0.22, 0.61, 0.36, 1],
							delay: idx * 0.04,
						}}
					>
						<div className="step-content">
							<div className="step-first-line">
								<span className="prompt" aria-hidden="true">
									&gt;
								</span>
								{getAgentKey(step) && (
									<span className="agent-key">[{getAgentKey(step)}]</span>
								)}
								<span className="name">{formatStepTitle(step)}</span>
								{step.durationMs !== undefined && (
									<span className="duration">
										({formatDuration(step.durationMs)})
									</span>
								)}
								<span className={`status status-${step.status}`}>
									<StatusSymbol status={step.status} />
								</span>
							</div>

							{showDetails && (
								<div className="step-details">
									{step.summary && (
										<div className="summary">{step.summary}</div>
									)}
									{contextDetails.length > 0 && (
										<div className="context">
											{contextDetails.map((detail) => (
												<span key={detail} className="context-item">
													{detail}
												</span>
											))}
										</div>
									)}
									{step.status === "running" &&
										step.thoughtLog &&
										step.thoughtLog.length > 0 && (
											<ThoughtStream entries={step.thoughtLog} />
										)}
								</div>
							)}
						</div>
					</StepRow>
				);
			})}
		</Shell>
	);
}

const Shell = styled.div`
  margin: 0;
  padding: var(--space-12);
  background: transparent;
  font-family: var(--font-mono);
  font-size: var(--text-caption);
  line-height: 1.4;
  color: var(--dark-text-secondary);
`;

const StepRow = styled.div`
  position: relative;
  transition: opacity var(--duration-reveal) var(--ease-editorial);

  &[data-status='success'], &[data-status='skipped'] {
    opacity: 0.8;
  }

  .step-content {
    display: flex;
    flex-direction: column;
  }

  .step-first-line {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    gap: var(--space-8);
  }

  .prompt {
    color: var(--dark-text-muted);
    font-weight: var(--font-weight-medium);
    flex-shrink: 0;
    width: 1.2ch;
  }

  .agent-key {
    color: var(--dark-text-muted);
  }

  .name {
    color: var(--dark-text-primary);
  }

  .duration {
    color: var(--dark-text-muted);
  }

  .status {
    display: flex;
    align-items: center;
  }

  .status-running {
    color: var(--status-running);
  }

  .status-success {
    color: var(--status-running);
  }

  .status-error {
    color: var(--status-error);
  }

  .step-details {
    padding-left: calc(1.2ch + var(--space-8));
    display: flex;
    flex-direction: column;
  }

  .summary {
    color: var(--dark-text-secondary);
    white-space: pre-wrap;
    word-break: break-word;
  }

  .context {
    color: var(--dark-text-muted);
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-8);
  }

  .context-item {
    white-space: pre-wrap;
  }

  .console-cursor {
    animation: console-blink 1s step-end infinite;
    font-weight: var(--font-weight-medium);
  }

  @keyframes console-blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }

  @media (prefers-reduced-motion: reduce) {
    transition: none;
    .console-cursor { animation: none; }
  }
`;
