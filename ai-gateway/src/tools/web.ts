import type { AgentTool, AgentToolResult } from "@earendil-works/pi-agent-core";
import { int, obj, opt, str } from "@earendil-works/pi-schema";

/** DeepSeek-compatible Search/Fetch HTTP API (`POST {base}/v1/tools/search|fetch`). */
export interface WebConfig {
	baseUrl?: string;
	apiKey?: string;
	fetchImpl?: typeof fetch;
}

const MAX_RESULTS = 10;
const MAX_FETCH_CHARS = 12000;
const REQUEST_TIMEOUT_MS = 30000;

function text(value: string): AgentToolResult<unknown> {
	return { content: [{ type: "text", text: value }], details: undefined };
}

const STATUS_HINT: Record<number, string> = {
	401: "搜索服务 Key 无效",
	402: "搜索服务余额不足",
	403: "该地址被搜索服务的安全策略拒绝",
	404: "无法获取该页面内容",
	429: "搜索服务限流，请稍后再试",
};

async function call(config: WebConfig, path: string, body: unknown, signal?: AbortSignal): Promise<any> {
	if (!config.baseUrl || !config.apiKey) {
		throw new Error("联网搜索服务未配置（网关缺少 WEB_SEARCH_BASE_URL / WEB_SEARCH_API_KEY），请如实告知管理员，不要编造搜索结果。");
	}
	const timeout = AbortSignal.timeout(REQUEST_TIMEOUT_MS);
	const response = await (config.fetchImpl ?? fetch)(`${config.baseUrl.replace(/\/+$/, "")}${path}`, {
		method: "POST",
		headers: { Authorization: `Bearer ${config.apiKey}`, "Content-Type": "application/json" },
		body: JSON.stringify(body),
		signal: signal ? AbortSignal.any([signal, timeout]) : timeout,
	}).catch(() => {
		throw new Error("搜索服务暂时无法连接。");
	});
	if (!response.ok) {
		throw new Error(`${STATUS_HINT[response.status] ?? "搜索服务暂时不可用"}（HTTP ${response.status}）。`);
	}
	return response.json();
}

/** `web_search` + `web_fetch`: the agent decides what to look up and which pages to read. */
export function createWebTools(config: WebConfig): AgentTool<any>[] {
	const search: AgentTool<any> = {
		name: "web_search",
		label: "联网搜索",
		description:
			"联网搜索网页，返回标题、链接、站点、日期和摘要。支持 site:、\"精确短语\"、lang:zh,en、-排除词 等语法。需要核实、查找外部资料时使用。",
		parameters: obj({ query: str(), count: opt(int()) }),
		async execute(_id, params: { query: string; count?: number }, signal) {
			const query = String(params.query ?? "").trim().slice(0, 128);
			if (!query) throw new Error("query 不能为空。");
			const count = Math.max(1, Math.min(MAX_RESULTS, Math.trunc(params.count ?? 8)));
			const data = await call(config, "/v1/tools/search", { query, count }, signal);
			const results = (Array.isArray(data?.results) ? data.results : []).slice(0, count).map((item: any) => ({
				title: item.title,
				url: item.url,
				site: item.site_name,
				date: item.date,
				summary: String(item.summary || item.snippet || "").slice(0, 600),
			}));
			return text(results.length > 0 ? JSON.stringify(results) : "没有搜到结果，可以换个关键词再试。");
		},
	};
	const fetchPage: AgentTool<any> = {
		name: "web_fetch",
		label: "读取网页",
		description: "读取一个网页并返回 Markdown 正文（过长会截断）。用于确认某个链接真的是目标资料、查看目录结构。",
		parameters: obj({ url: str() }),
		async execute(_id, params: { url: string }, signal) {
			const url = String(params.url ?? "").trim();
			if (!/^https?:\/\//i.test(url)) throw new Error("url 必须是 http(s) 地址。");
			const page = await call(config, "/v1/tools/fetch", { url }, signal);
			const content = String(page?.content ?? "");
			const clipped = content.length > MAX_FETCH_CHARS ? `${content.slice(0, MAX_FETCH_CHARS)}\n…（已截断，原文 ${content.length} 字）` : content;
			return text(`# ${page?.title ?? ""}\n\n${clipped}`);
		},
	};
	return [search, fetchPage];
}
