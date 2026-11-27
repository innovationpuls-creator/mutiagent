import type { Credential, CredentialInfo, CredentialStore } from "@earendil-works/pi-ai";
import type { BackendClient } from "../backendClient.js";
import { BackendBusinessError } from "../errors.js";
import type { RuntimeConfig } from "./types.js";

/** Process-wide per (user, provider) mutex: refresh must be single-flight. */
const chains = new Map<string, Promise<unknown>>();

async function withLock<T>(key: string, task: () => Promise<T>): Promise<T> {
	const previous = chains.get(key) ?? Promise.resolve();
	const run = previous.catch(() => undefined).then(task);
	const tail = run.catch(() => undefined);
	chains.set(key, tail);
	try {
		return await run;
	} finally {
		if (chains.get(key) === tail) chains.delete(key);
	}
}

function toCredential(raw: Record<string, unknown>): Credential {
	return { ...raw, type: "oauth" } as Credential;
}

function expiresIso(credential: Record<string, unknown>): string | null {
	const expires = credential.expires;
	return typeof expires === "number" ? new Date(expires).toISOString() : null;
}

/**
 * Pi CredentialStore backed by the Python backend. API keys come from the loaded
 * runtime config; OAuth credentials are refreshed under the in-process mutex and
 * written with a row-locked compare-and-swap on the refresh-token fingerprint.
 */
export function createBackendCredentialStore(
	userUid: string,
	config: RuntimeConfig,
	backend: BackendClient,
): CredentialStore {
	const apiKeys = new Map<string, string>();
	const oauth = new Map<string, { credential: Record<string, unknown>; fingerprint: string | null }>();
	for (const provider of config.providers) {
		if (!provider.enabled) continue;
		if (provider.api_key) apiKeys.set(provider.provider_id, provider.api_key);
		if (provider.oauth_credential) {
			oauth.set(provider.provider_id, {
				credential: provider.oauth_credential,
				fingerprint: provider.oauth_refresh_fingerprint,
			});
		}
	}

	const read = async (providerId: string): Promise<Credential | undefined> => {
		const key = apiKeys.get(providerId);
		if (key) return { type: "api_key", key };
		const entry = oauth.get(providerId);
		return entry ? toCredential(entry.credential) : undefined;
	};

	return {
		read,
		async list(): Promise<readonly CredentialInfo[]> {
			return [
				...[...apiKeys.keys()].map((providerId) => ({ providerId, type: "api_key" as const })),
				...[...oauth.keys()].map((providerId) => ({ providerId, type: "oauth" as const })),
			];
		},
		async modify(providerId, fn) {
			if (apiKeys.has(providerId)) return fn(await read(providerId));
			return withLock(`${userUid}:${providerId}`, async () => {
				// Re-read under the lock so a concurrent refresher's result is observed.
				let current: Record<string, unknown> | undefined;
				let fingerprint: string | null = null;
				try {
					const locked = await backend.oauthRefreshLock(userUid, providerId, {});
					current = locked.credential;
					fingerprint = locked.refresh_fingerprint;
					oauth.set(providerId, { credential: current, fingerprint });
				} catch (error) {
					if (!(error instanceof BackendBusinessError && error.status === 404)) throw error;
				}
				const next = await fn(current ? toCredential(current) : undefined);
				if (!next || next.type !== "oauth") return current ? toCredential(current) : undefined;
				const { type: _type, ...plain } = next;
				if (current) {
					const result = await backend.oauthRefreshLock(userUid, providerId, {
						previous_refresh_fingerprint: fingerprint,
						new_credential: plain,
						expires_at: expiresIso(plain),
					});
					oauth.set(providerId, { credential: result.credential, fingerprint: result.refresh_fingerprint });
					return toCredential(result.credential);
				}
				await backend.saveOAuthCredential(userUid, providerId, {
					credential: plain,
					expires_at: expiresIso(plain),
				});
				oauth.set(providerId, { credential: plain, fingerprint: null });
				return next;
			});
		},
		async delete(providerId) {
			oauth.delete(providerId);
			apiKeys.delete(providerId);
		},
	};
}
