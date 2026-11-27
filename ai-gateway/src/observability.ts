import { randomUUID } from "node:crypto";
import { AsyncLocalStorage } from "node:async_hooks";
import type { MiddlewareHandler } from "hono";
import { SERVICE_NAME } from "./config.js";

export const REQUEST_ID_HEADER = "X-Request-ID";
const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

interface RequestContext {
	requestId: string;
}

const requestContext = new AsyncLocalStorage<RequestContext>();

export function getRequestId(): string | undefined {
	return requestContext.getStore()?.requestId;
}

export function resolveRequestId(incoming: string | null | undefined): string {
	if (incoming && REQUEST_ID_PATTERN.test(incoming)) return incoming;
	return randomUUID().replaceAll("-", "");
}

export type LogSink = (line: string) => void;
export const stdoutSink: LogSink = (line) => {
	process.stdout.write(`${line}\n`);
};

export interface LogFields {
	level?: "INFO" | "WARNING" | "ERROR";
	message: string;
	request_id?: string | null;
	method?: string | null;
	path?: string | null;
	status_code?: number | null;
	duration_ms?: number | null;
}

/** Same field set/order as backend JsonFormatter, with this service's name. */
export function formatLogLine(fields: LogFields): string {
	return JSON.stringify({
		timestamp: new Date().toISOString(),
		level: fields.level ?? "INFO",
		service: SERVICE_NAME,
		request_id: fields.request_id ?? getRequestId() ?? null,
		method: fields.method ?? null,
		path: fields.path ?? null,
		status_code: fields.status_code ?? null,
		duration_ms: fields.duration_ms ?? null,
		message: fields.message,
	});
}

export interface Logger {
	info(message: string): void;
	warn(message: string): void;
	error(message: string): void;
}

export function createLogger(sink: LogSink = stdoutSink): Logger {
	return {
		info: (message) => sink(formatLogLine({ level: "INFO", message })),
		warn: (message) => sink(formatLogLine({ level: "WARNING", message })),
		error: (message) => sink(formatLogLine({ level: "ERROR", message })),
	};
}

/**
 * Outermost middleware: resolves/generates X-Request-ID, exposes it through
 * AsyncLocalStorage, echoes it on the response and writes one JSON access log.
 * Only the path is logged (never query strings, headers or bodies).
 */
export function requestIdMiddleware(sink: LogSink = stdoutSink): MiddlewareHandler {
	return async (c, next) => {
		const requestId = resolveRequestId(c.req.header(REQUEST_ID_HEADER));
		const startedAt = performance.now();
		c.header(REQUEST_ID_HEADER, requestId);
		await requestContext.run({ requestId }, async () => {
			try {
				await next();
			} finally {
				try {
					c.res.headers.set(REQUEST_ID_HEADER, requestId);
				} catch {
					// Immutable upstream responses already carry the header via c.header.
				}
				sink(
					formatLogLine({
						message: "request_completed",
						request_id: requestId,
						method: c.req.method,
						path: c.req.path,
						status_code: c.res.status,
						duration_ms: Math.round((performance.now() - startedAt) * 1000) / 1000,
					}),
				);
			}
		});
	};
}
