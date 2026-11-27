import { useEffect, useMemo, useRef, useState } from "react";
import {
	type CatalogProvider,
	modelConfigApi,
	PROTOCOLS,
	type ProviderUpsert,
	type ProviderView,
} from "../../api/modelConfig";
import { providerStatus } from "../../components/models/modelOptions";
import { useDialogAccessibility } from "../../components/ui/useDialogAccessibility";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import { CustomModelsPanel } from "./CustomModelsPanel";
import { OAuthDialog } from "./OAuthDialog";
import { ProbeButton } from "./ProbeBadges";

interface DrawerTarget {
	providerId: string;
	isNew: boolean;
	isBuiltin: boolean;
}

interface HeaderRow {
	key: string;
	value: string;
}

function slugify(value: string): string {
	return value
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9-]+/g, "-")
		.replace(/^-+|-+$/g, "")
		.slice(0, 48);
}

function ProviderDrawer({
	target,
	catalogEntry,
	provider,
	onClose,
	onOAuth,
	onReopen,
}: {
	target: DrawerTarget;
	catalogEntry: CatalogProvider | undefined;
	provider: ProviderView | undefined;
	onClose: () => void;
	onOAuth: (providerId: string, name: string) => void;
	onReopen: (providerId: string) => void;
}) {
	const { token } = useAuth();
	const { config, refresh } = useModelConfig();
	const closeRef = useRef<HTMLButtonElement>(null);
	useDialogAccessibility({ isOpen: true, onClose, initialFocusRef: closeRef });

	const [providerId, setProviderId] = useState(target.providerId);
	const [displayName, setDisplayName] = useState(
		provider?.display_name ?? catalogEntry?.name ?? "",
	);
	const [protocol, setProtocol] = useState<string>(
		provider?.protocol || PROTOCOLS[0].value,
	);
	const [baseUrl, setBaseUrl] = useState(provider?.base_url ?? "");
	const [apiKey, setApiKey] = useState("");
	const [clearKey, setClearKey] = useState(false);
	const [enabled, setEnabled] = useState(provider?.enabled ?? true);
	const [authType, setAuthType] = useState<"api_key" | "oauth">(
		provider?.auth_type ?? "api_key",
	);
	const [headers, setHeaders] = useState<HeaderRow[]>([]);
	const [clearHeaders, setClearHeaders] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [busy, setBusy] = useState(false);
	const [confirmDelete, setConfirmDelete] = useState(false);

	const existingHeaderNames = Object.keys(provider?.headers ?? {});
	const supportsOAuth =
		target.isBuiltin && Boolean(catalogEntry?.supports_oauth);
	const customModels = (config?.custom_models ?? []).filter(
		(m) => m.provider_id === providerId,
	);
	const title = target.isNew
		? target.isBuiltin
			? `配置 ${displayName || providerId}`
			: "新增自定义 Provider / 中转站"
		: `配置 ${provider?.display_name || providerId}`;
	const exampleModel = catalogEntry?.models[0]?.id ?? null;

	const save = async () => {
		if (!token) return;
		setError(null);
		const id =
			target.isNew && !target.isBuiltin ? slugify(providerId) : providerId;
		if (!id) return setError("请填写 Provider 标识（英文、数字、短横线）");
		if (!target.isBuiltin) {
			if (!baseUrl.trim()) return setError("自定义 Provider 必须填写 Base URL");
			if (!/^https?:\/\//i.test(baseUrl.trim()))
				return setError("Base URL 需要以 http:// 或 https:// 开头");
		}
		const filledHeaders = headers.filter((row) => row.key.trim());
		if (filledHeaders.some((row) => !row.value.trim()))
			return setError("请求头需要同时填写名称和值");
		const body: ProviderUpsert = {
			display_name: displayName.trim() || null,
			is_builtin: target.isBuiltin,
			protocol: target.isBuiltin
				? null
				: (protocol as ProviderUpsert["protocol"]),
			base_url: baseUrl.trim() || null,
			auth_type: authType,
			enabled,
		};
		if (authType === "api_key") {
			if (clearKey) body.api_key = "";
			else if (apiKey.trim()) body.api_key = apiKey.trim();
		}
		if (clearHeaders) body.headers = {};
		else if (filledHeaders.length > 0) {
			body.headers = Object.fromEntries(
				filledHeaders.map((row) => [row.key.trim(), row.value.trim()]),
			);
		}
		setBusy(true);
		try {
			await modelConfigApi.saveProvider(token, id, body);
			await refresh();
			if (
				authType === "oauth" &&
				supportsOAuth &&
				provider?.oauth_status !== "authorized"
			) {
				onClose();
				onOAuth(id, displayName || id);
				return;
			}
			if (target.isNew && !target.isBuiltin) onReopen(id);
			else onClose();
		} catch (err) {
			setError(err instanceof Error ? err.message : "保存失败，请稍后重试");
		} finally {
			setBusy(false);
		}
	};

	const remove = async () => {
		if (!token) return;
		setBusy(true);
		setError(null);
		try {
			await modelConfigApi.deleteProvider(token, providerId);
			await refresh();
			onClose();
		} catch (err) {
			setError(err instanceof Error ? err.message : "删除失败，请稍后重试");
		} finally {
			setBusy(false);
		}
	};

	return (
		<div className="mc-backdrop">
			<aside
				className="mc-drawer"
				role="dialog"
				aria-modal="true"
				aria-labelledby="mc-drawer-title"
			>
				<header className="mc-dialog-head">
					<h2 id="mc-drawer-title">{title}</h2>
					<button
						ref={closeRef}
						type="button"
						className="mc-btn mc-btn-ghost"
						onClick={onClose}
					>
						关闭
					</button>
				</header>
				<div className="mc-drawer-body">
					<div className="mc-form">
						{target.isNew && !target.isBuiltin && (
							<label className="mc-field">
								<span>Provider 标识</span>
								<input
									value={providerId}
									onChange={(e) => setProviderId(e.target.value)}
									placeholder="例如 my-relay"
								/>
							</label>
						)}
						<label className="mc-field">
							<span>展示名</span>
							<input
								value={displayName}
								onChange={(e) => setDisplayName(e.target.value)}
							/>
						</label>
						{!target.isBuiltin && (
							<label className="mc-field">
								<span>接口协议</span>
								<select
									value={protocol}
									onChange={(e) => setProtocol(e.target.value)}
								>
									{PROTOCOLS.map((item) => (
										<option key={item.value} value={item.value}>
											{item.label}
										</option>
									))}
								</select>
							</label>
						)}
						<label className="mc-field">
							<span>
								{target.isBuiltin
									? "Base URL（可选，覆写默认地址）"
									: "Base URL"}
							</span>
							<input
								value={baseUrl}
								onChange={(e) => setBaseUrl(e.target.value)}
								placeholder="https://api.example.com/v1"
							/>
						</label>
						{supportsOAuth && (
							<fieldset className="mc-checks">
								<legend>认证方式</legend>
								<label>
									<input
										type="radio"
										name="auth"
										checked={authType === "api_key"}
										onChange={() => setAuthType("api_key")}
									/>
									API Key
								</label>
								<label>
									<input
										type="radio"
										name="auth"
										checked={authType === "oauth"}
										onChange={() => setAuthType("oauth")}
									/>
									OAuth 登录
								</label>
							</fieldset>
						)}
						{authType === "api_key" && (
							<div className="mc-field">
								<label htmlFor="mc-api-key">API Key</label>
								<input
									id="mc-api-key"
									type="password"
									autoComplete="off"
									value={apiKey}
									onChange={(e) => {
										setApiKey(e.target.value);
										setClearKey(false);
									}}
									placeholder={
										provider?.has_secret
											? `已保存 ${provider.secret_mask ?? "••••"}，留空表示不修改`
											: "sk-…（本地无需密钥的服务可留空）"
									}
								/>
								{provider?.has_secret && (
									<label className="mc-inline">
										<input
											type="checkbox"
											checked={clearKey}
											onChange={(e) => setClearKey(e.target.checked)}
										/>
										清除已保存的 Key
									</label>
								)}
							</div>
						)}
						{authType === "oauth" && provider?.oauth_status && (
							<p className="mc-hint">
								当前状态：{providerStatus(provider).label}
								{provider.oauth_account_label
									? `（${provider.oauth_account_label}）`
									: ""}
							</p>
						)}
						<details className="mc-details">
							<summary>
								自定义请求头
								{existingHeaderNames.length
									? `（已设置 ${existingHeaderNames.length} 个）`
									: ""}
							</summary>
							<div className="mc-stack">
								{existingHeaderNames.length > 0 && (
									<p className="mc-hint">
										已设置：{existingHeaderNames.join("、")}
										（值已隐藏）。填写新的请求头将整体替换。
									</p>
								)}
								{headers.map((row, index) => (
									// biome-ignore lint/suspicious/noArrayIndexKey: rows are positional drafts
									<div className="mc-grid-2" key={index}>
										<input
											aria-label={`请求头名称 ${index + 1}`}
											value={row.key}
											onChange={(e) =>
												setHeaders(
													headers.map((r, i) =>
														i === index ? { ...r, key: e.target.value } : r,
													),
												)
											}
											placeholder="X-Header"
										/>
										<input
											aria-label={`请求头值 ${index + 1}`}
											value={row.value}
											onChange={(e) =>
												setHeaders(
													headers.map((r, i) =>
														i === index ? { ...r, value: e.target.value } : r,
													),
												)
											}
											placeholder="value"
										/>
									</div>
								))}
								<div className="mc-row">
									<button
										type="button"
										className="mc-btn mc-btn-ghost"
										onClick={() =>
											setHeaders([...headers, { key: "", value: "" }])
										}
									>
										添加请求头
									</button>
									{existingHeaderNames.length > 0 && (
										<label className="mc-inline">
											<input
												type="checkbox"
												checked={clearHeaders}
												onChange={(e) => setClearHeaders(e.target.checked)}
											/>
											清空已有请求头
										</label>
									)}
								</div>
							</div>
						</details>
						<label className="mc-inline">
							<input
								type="checkbox"
								checked={enabled}
								onChange={(e) => setEnabled(e.target.checked)}
							/>
							启用此 Provider
						</label>
						{error && (
							<p className="mc-error" role="alert">
								{error}
							</p>
						)}
						<div className="mc-row">
							<button
								type="button"
								className="mc-btn mc-btn-primary"
								disabled={busy}
								onClick={() => void save()}
							>
								{busy ? "保存中…" : "保存"}
							</button>
							{provider && authType === "oauth" && supportsOAuth && (
								<button
									type="button"
									className="mc-btn"
									onClick={() => {
										onClose();
										onOAuth(providerId, provider.display_name || providerId);
									}}
								>
									OAuth 登录
								</button>
							)}
							{provider &&
								!target.isNew &&
								(confirmDelete ? (
									<button
										type="button"
										className="mc-btn mc-btn-danger"
										disabled={busy}
										onClick={() => void remove()}
									>
										确认删除
									</button>
								) : (
									<button
										type="button"
										className="mc-btn mc-btn-danger"
										onClick={() => setConfirmDelete(true)}
									>
										删除配置
									</button>
								))}
						</div>
						{provider && (
							<ProbeButton
								providerId={providerId}
								modelId={
									target.isBuiltin
										? exampleModel
										: (customModels[0]?.model_id ?? null)
								}
							/>
						)}
					</div>
					{!target.isBuiltin && !target.isNew && (
						<CustomModelsPanel
							providerId={providerId}
							models={customModels}
							onChanged={refresh}
						/>
					)}
					{!target.isBuiltin && target.isNew && (
						<p className="mc-hint">保存 Provider 后即可添加自定义模型。</p>
					)}
				</div>
			</aside>
		</div>
	);
}

export function ProviderSection({
	reauthProvider,
}: {
	reauthProvider: string | null;
}) {
	const { config, catalog, catalogError, refresh } = useModelConfig();
	const [drawer, setDrawer] = useState<DrawerTarget | null>(null);
	const [oauth, setOauth] = useState<{ id: string; name: string } | null>(null);
	const [filter, setFilter] = useState("");
	const [pickId, setPickId] = useState("");

	const providers = config?.providers ?? [];
	const byId = useMemo(
		() => new Map(providers.map((p) => [p.provider_id, p])),
		[providers],
	);
	const catalogById = useMemo(
		() => new Map(catalog.map((c) => [c.id, c])),
		[catalog],
	);

	const reauthDone = useRef<string | null>(null);
	useEffect(() => {
		if (!reauthProvider || reauthDone.current === reauthProvider || !config)
			return;
		reauthDone.current = reauthProvider;
		const name =
			byId.get(reauthProvider)?.display_name ||
			catalogById.get(reauthProvider)?.name ||
			reauthProvider;
		setOauth({ id: reauthProvider, name });
	}, [reauthProvider, config, byId, catalogById]);

	const configured = providers.filter(
		(p) =>
			p.provider_id.toLowerCase().includes(filter.toLowerCase()) ||
			p.display_name.toLowerCase().includes(filter.toLowerCase()),
	);
	const addable = catalog.filter((c) => !byId.has(c.id));

	const firstModelId = (provider: ProviderView): string | null => {
		if (provider.is_builtin)
			return catalogById.get(provider.provider_id)?.models[0]?.id ?? null;
		return (
			config?.custom_models.find(
				(m) => m.provider_id === provider.provider_id && m.enabled,
			)?.model_id ?? null
		);
	};

	return (
		<section className="mc-section" aria-labelledby="mc-providers-title">
			<header className="mc-section-head">
				<div>
					<h2 id="mc-providers-title">Provider 与凭证</h2>
					<p className="mc-hint">
						添加你自己的 API Key、OAuth
						登录或自建中转站；密钥加密保存，只显示掩码。
					</p>
				</div>
				<button
					type="button"
					className="mc-btn mc-btn-primary"
					onClick={() =>
						setDrawer({ providerId: "", isNew: true, isBuiltin: false })
					}
				>
					新增自定义 Provider / 中转站
				</button>
			</header>
			{catalogError && <p className="mc-warn">{catalogError}</p>}
			<div className="mc-row mc-wrap">
				<label className="mc-field mc-grow">
					<span>添加内置厂商</span>
					<select value={pickId} onChange={(e) => setPickId(e.target.value)}>
						<option value="">选择厂商…</option>
						{addable.map((c) => (
							<option key={c.id} value={c.id}>
								{c.name}
							</option>
						))}
					</select>
				</label>
				<button
					type="button"
					className="mc-btn"
					disabled={!pickId}
					onClick={() => {
						setDrawer({ providerId: pickId, isNew: true, isBuiltin: true });
						setPickId("");
					}}
				>
					配置
				</button>
				{providers.length > 6 && (
					<label className="mc-field mc-grow">
						<span>筛选已配置</span>
						<input value={filter} onChange={(e) => setFilter(e.target.value)} />
					</label>
				)}
			</div>
			{configured.length === 0 ? (
				<p className="mc-empty">
					还没有配置任何 Provider。选择一个内置厂商，或新增自定义中转站。
				</p>
			) : (
				<ul className="mc-cards">
					{configured.map((provider) => {
						const status = providerStatus(provider);
						const entry = catalogById.get(provider.provider_id);
						return (
							<li key={provider.provider_id} className="mc-card">
								<div className="mc-row mc-between">
									<strong>
										{provider.display_name || provider.provider_id}
									</strong>
									<span className={`mc-badge mc-badge-${status.tone}`}>
										{status.label}
									</span>
								</div>
								<small>
									{provider.is_builtin
										? "内置厂商"
										: `自定义 · ${provider.protocol}`}
									{provider.secret_mask ? ` · ${provider.secret_mask}` : ""}
								</small>
								<div className="mc-row mc-wrap">
									<button
										type="button"
										className="mc-btn"
										onClick={() =>
											setDrawer({
												providerId: provider.provider_id,
												isNew: false,
												isBuiltin: provider.is_builtin,
											})
										}
									>
										配置
									</button>
									{entry?.supports_oauth && (
										<button
											type="button"
											className="mc-btn"
											onClick={() =>
												setOauth({
													id: provider.provider_id,
													name: provider.display_name || provider.provider_id,
												})
											}
										>
											OAuth 登录
										</button>
									)}
								</div>
								<ProbeButton
									providerId={provider.provider_id}
									modelId={firstModelId(provider)}
								/>
							</li>
						);
					})}
				</ul>
			)}
			{drawer && (
				<ProviderDrawer
					key={`${drawer.providerId}-${drawer.isNew}`}
					target={drawer}
					catalogEntry={catalogById.get(drawer.providerId)}
					provider={byId.get(drawer.providerId)}
					onClose={() => setDrawer(null)}
					onOAuth={(id, name) => setOauth({ id, name })}
					onReopen={(id) =>
						setDrawer({ providerId: id, isNew: false, isBuiltin: false })
					}
				/>
			)}
			{oauth && (
				<OAuthDialog
					providerId={oauth.id}
					providerName={oauth.name}
					onClose={() => setOauth(null)}
					onAuthorized={() => void refresh()}
				/>
			)}
		</section>
	);
}
