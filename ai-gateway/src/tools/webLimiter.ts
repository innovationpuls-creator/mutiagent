/** Sliding 24h window of web search/fetch calls per user (in-process; resets on restart). */
export class WebUsageLimiter {
	private readonly calls = new Map<string, number[]>();

	constructor(
		private readonly windowMs = 24 * 60 * 60 * 1000,
		private readonly now: () => number = Date.now,
	) {}

	/** Count one call if the user is still under `limit`; false when the quota is spent. */
	take(userUid: string, limit: number): boolean {
		const cutoff = this.now() - this.windowMs;
		const recent = (this.calls.get(userUid) ?? []).filter((at) => at > cutoff);
		if (recent.length >= limit) {
			this.calls.set(userUid, recent);
			return false;
		}
		recent.push(this.now());
		this.calls.set(userUid, recent);
		return true;
	}

	used(userUid: string): number {
		const cutoff = this.now() - this.windowMs;
		return (this.calls.get(userUid) ?? []).filter((at) => at > cutoff).length;
	}
}
