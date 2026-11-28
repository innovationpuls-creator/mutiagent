import { Hono } from "hono";
import { type AuthVariables, jwtAuth } from "../auth.js";
import type { BackendClient } from "../backendClient.js";
import { GatewayError } from "../errors.js";
import { builtinCapabilities, listCatalog } from "./catalog.js";
import type { OAuthSessions } from "./oauth.js";
import { probeModel } from "./probe.js";
import type { ModelRuntime } from "./runtime.js";
import { SCENES, type Scene } from "./types.js";

async function jsonBody(request: Request): Promise<Record<string, unknown>> {
	try {
		const body = (await request.json()) as unknown;
		return body && typeof body === "object" ? (body as Record<string, unknown>) : {};
	} catch {
		return {};
	}
}

function requireString(body: Record<string, unknown>, key: string): string {
	const value = body[key];
	if (typeof value !== "string" || value === "") {
		throw new GatewayError(422, undefined, `缺少参数：${key}`);
	}
	return value;
}

export interface ModelRouteDeps {
	jwtSecret: string;
	backend: BackendClient;
	runtime: ModelRuntime;
	oauth: OAuthSessions;
	builtinOverride?: Parameters<typeof listCatalog>[0];
}

/** Authenticated, user-facing model routes (mounted under /api/ai). */
export function modelRoutes(deps: ModelRouteDeps) {
	const app = new Hono<{ Variables: AuthVariables }>();
	const auth = jwtAuth(deps.jwtSecret, deps.backend);

	app.get("/models/catalog", auth, (c) => c.json({ providers: listCatalog(deps.builtinOverride) }));

	app.post("/models/probe", auth, async (c) => {
		const body = await jsonBody(c.req.raw);
		const entry = await deps.runtime.getEntry(c.get("auth").userUid);
		return c.json(await probeModel(entry, requireString(body, "provider_id"), requireString(body, "model_id")));
	});

	// Which model(s) a scene would use for this user; 428 when nothing is configured.
	app.post("/models/scene-check", auth, async (c) => {
		const body = await jsonBody(c.req.raw);
		const scene = requireString(body, "scene") as Scene;
		if (!SCENES.includes(scene)) throw new GatewayError(422, undefined, "未知的场景");
		const { resolved } = await deps.runtime.resolve(c.get("auth").userUid, scene);
		return c.json({
			scene,
			targets: resolved.targets,
			thinking_level: resolved.thinkingLevel,
		});
	});

	app.post("/oauth/:provider/start", auth, async (c) =>
		c.json(await deps.oauth.start(c.get("auth").userUid, c.req.param("provider"))),
	);

	app.post("/oauth/:provider/complete", auth, async (c) => {
		const body = await jsonBody(c.req.raw);
		const result = await deps.oauth.complete(
			c.get("auth").userUid,
			c.req.param("provider"),
			requireString(body, "state"),
			requireString(body, "code"),
		);
		return c.json(result);
	});

	app.get("/oauth/:provider/status", auth, (c) =>
		c.json(deps.oauth.status(c.get("auth").userUid, c.req.param("provider"), c.req.query("state") ?? "")),
	);

	return app;
}

/** Python -> gateway routes (already behind the internal-token middleware). */
export function internalModelRoutes(deps: Pick<ModelRouteDeps, "runtime" | "builtinOverride">) {
	const app = new Hono();

	app.post("/cache/invalidate-user-model-config", async (c) => {
		const body = await jsonBody(c.req.raw);
		const dropped = deps.runtime.invalidate(requireString(body, "user_uid"));
		return c.json({ status: "ok", invalidated: dropped });
	});

	app.post("/models/capabilities", async (c) => {
		const body = await jsonBody(c.req.raw);
		const refs = Array.isArray(body.refs) ? (body.refs as Array<{ provider_id: string; model_id: string }>) : [];
		return c.json({ capabilities: builtinCapabilities(refs, deps.builtinOverride) });
	});

	return app;
}
