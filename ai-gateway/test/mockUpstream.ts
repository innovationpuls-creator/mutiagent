import { type IncomingMessage, type Server, type ServerResponse, createServer } from "node:http";
import type { AddressInfo } from "node:net";

export interface MockRequest {
	url: string;
	headers: Record<string, string | string[] | undefined>;
	body: Record<string, any>;
}

export interface MockUpstream {
	url: string;
	requests: MockRequest[];
	/** Next responses by status; default 200 text. */
	script: Array<number>;
	reply: string;
	close(): Promise<void>;
}

/** Minimal OpenAI-compatible /chat/completions streaming server. */
export async function startMockUpstream(): Promise<MockUpstream> {
	const state: MockUpstream = {
		url: "",
		requests: [],
		script: [],
		reply: "OK",
		close: async () => {},
	};
	const server: Server = createServer((req: IncomingMessage, res: ServerResponse) => {
		const chunks: Buffer[] = [];
		req.on("data", (c) => chunks.push(c));
		req.on("end", () => {
			let body: Record<string, any> = {};
			try {
				body = JSON.parse(Buffer.concat(chunks).toString() || "{}");
			} catch {}
			state.requests.push({ url: req.url ?? "", headers: req.headers, body });
			const status = state.script.shift() ?? 200;
			if (status !== 200) {
				res.writeHead(status, { "content-type": "application/json" });
				res.end(JSON.stringify({ error: { message: `mock upstream ${status}`, type: "mock" } }));
				return;
			}
			const wantsTool = Array.isArray(body.tools) && body.tools.length > 0;
			res.writeHead(200, { "content-type": "text/event-stream" });
			const send = (obj: unknown) => res.write(`data: ${JSON.stringify(obj)}\n\n`);
			const base = { id: "c1", object: "chat.completion.chunk", created: 1, model: body.model };
			if (wantsTool) {
				send({ ...base, choices: [{ index: 0, delta: { role: "assistant", tool_calls: [{ index: 0, id: "call_1", type: "function", function: { name: "ping", arguments: '{"value":1}' } }] }, finish_reason: null }] });
				send({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } });
			} else {
				send({ ...base, choices: [{ index: 0, delta: { role: "assistant", content: state.reply }, finish_reason: null }] });
				send({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage: { prompt_tokens: 12, completion_tokens: 3, total_tokens: 15 } });
			}
			res.write("data: [DONE]\n\n");
			res.end();
		});
	});
	await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
	state.url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/v1`;
	state.close = () => new Promise((resolve) => server.close(() => resolve()));
	return state;
}
