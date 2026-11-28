import {
	createContext,
	type ReactNode,
	useCallback,
	useContext,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import {
	aiModelsApi,
	type CatalogProvider,
	type ModelConfigView,
	type ModelRef,
	modelConfigApi,
	type ThinkingLevel,
} from "../api/modelConfig";
import {
	buildModelOptions,
	type ModelOption,
} from "../components/models/modelOptions";
import { useAuth } from "./AuthContext";

export interface ModelConfigState {
	config: ModelConfigView | null;
	catalog: CatalogProvider[];
	catalogError: string | null;
	options: ModelOption[];
	isLoading: boolean;
	loadError: string | null;
	/** True once loaded and the user has no usable default model yet. */
	needsSetup: boolean;
	refresh(): Promise<void>;
	setConfig(next: ModelConfigView): void;
	quickSwitch(input: {
		model_ref?: ModelRef | null;
		thinking_level?: ThinkingLevel | null;
	}): Promise<void>;
}

const noop = async () => {};
const DEFAULT_STATE: ModelConfigState = {
	config: null,
	catalog: [],
	catalogError: null,
	options: [],
	isLoading: false,
	loadError: null,
	needsSetup: false,
	refresh: noop,
	setConfig: () => {},
	quickSwitch: noop,
};

function isModelConfig(value: unknown): value is ModelConfigView {
	if (!value || typeof value !== "object") return false;
	const candidate = value as Partial<ModelConfigView>;
	return (
		Array.isArray(candidate.providers) &&
		Array.isArray(candidate.custom_models) &&
		typeof candidate.preferences === "object" &&
		candidate.preferences !== null
	);
}

const ModelConfigContext = createContext<ModelConfigState>(DEFAULT_STATE);

export function ModelConfigProvider({ children }: { children: ReactNode }) {
	const { token, user } = useAuth();
	const [config, setConfig] = useState<ModelConfigView | null>(null);
	const [catalog, setCatalog] = useState<CatalogProvider[]>([]);
	const [catalogError, setCatalogError] = useState<string | null>(null);
	const [isLoading, setIsLoading] = useState(false);
	const [loadError, setLoadError] = useState<string | null>(null);
	const generation = useRef(0);

	const refresh = useCallback(async () => {
		if (!token) return;
		const current = ++generation.current;
		setIsLoading(true);
		try {
			const [nextConfig, nextCatalog] = await Promise.allSettled([
				modelConfigApi.get(token),
				aiModelsApi.catalog(token),
			]);
			if (generation.current !== current) return;
			if (
				nextConfig.status === "fulfilled" &&
				isModelConfig(nextConfig.value)
			) {
				setConfig(nextConfig.value);
				setLoadError(null);
			} else if (nextConfig.status === "fulfilled") {
				setLoadError("模型配置数据格式不正确");
			} else {
				setLoadError(
					nextConfig.reason instanceof Error
						? nextConfig.reason.message
						: "模型配置加载失败",
				);
			}
			if (
				nextCatalog.status === "fulfilled" &&
				Array.isArray(nextCatalog.value)
			) {
				setCatalog(nextCatalog.value);
				setCatalogError(null);
			} else {
				setCatalogError("模型目录暂时无法加载，预置服务商的模型列表可能不完整");
			}
		} finally {
			if (generation.current === current) setIsLoading(false);
		}
	}, [token]);

	useEffect(() => {
		generation.current += 1;
		if (!token || !user) {
			setConfig(null);
			setCatalog([]);
			setLoadError(null);
			setCatalogError(null);
			setIsLoading(false);
			return;
		}
		void refresh();
	}, [token, user, refresh]);

	const options = useMemo(
		() => buildModelOptions(config, catalog),
		[config, catalog],
	);

	const needsSetup = useMemo(() => {
		if (!config) return false;
		const ref = config.preferences.default_model_ref;
		if (!ref) return true;
		if (options.length === 0 && catalog.length === 0) {
			// catalog unavailable: judge by provider rows only
			return !config.providers.some(
				(p) => p.enabled && (p.has_secret || !p.is_builtin),
			);
		}
		return !options.some(
			(option) =>
				option.ref.provider_id === ref.provider_id &&
				option.ref.model_id === ref.model_id,
		);
	}, [config, options, catalog.length]);

	const quickSwitch = useCallback<ModelConfigState["quickSwitch"]>(
		async (input) => {
			if (!token) return;
			const preferences = await modelConfigApi.quickSwitch(token, {
				model_ref: input.model_ref ?? undefined,
				thinking_level: input.thinking_level ?? undefined,
			});
			setConfig((previous) =>
				previous ? { ...previous, preferences } : previous,
			);
		},
		[token],
	);

	const value = useMemo<ModelConfigState>(
		() => ({
			config,
			catalog,
			catalogError,
			options,
			isLoading,
			loadError,
			needsSetup,
			refresh,
			setConfig,
			quickSwitch,
		}),
		[
			config,
			catalog,
			catalogError,
			options,
			isLoading,
			loadError,
			needsSetup,
			refresh,
			quickSwitch,
		],
	);

	return (
		<ModelConfigContext.Provider value={value}>
			{children}
		</ModelConfigContext.Provider>
	);
}

export function useModelConfig(): ModelConfigState {
	return useContext(ModelConfigContext);
}
