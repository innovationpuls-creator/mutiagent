import { useSearchParams } from "react-router-dom";
import { ModelQuickSwitcher } from "../../components/models/ModelQuickSwitcher";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import "./model-config.css";
import { Button } from "../../components/ui/Button";
import { ProviderSection } from "./ProviderSection";
import { SlotSection } from "./SlotSection";
import { UsageSection } from "./UsageSection";

export function ModelConfigPage() {
	const { user } = useAuth();
	const { config, isLoading, loadError, needsSetup, refresh } =
		useModelConfig();
	const [params] = useSearchParams();
	const isAdmin = user?.role === "admin";
	const hasService = Boolean(
		config?.providers.some((p) => p.enabled && (p.has_secret || !p.is_builtin)),
	);

	return (
		<div className={`mc-page ${isAdmin ? "mc-page-admin" : "mc-page-student"}`}>
			<header className="page-header mc-hero">
				<div className="page-header-title">
					<h1>模型配置</h1>
					<p>
						配置只属于你自己：你的密钥、你的模型、你的思考深度。
						{isAdmin ? "管理员可额外配置教材翻译与公开教材搜书。" : ""}
					</p>
				</div>
				{config && (
					<div className="page-header-actions">
						<ModelQuickSwitcher />
					</div>
				)}
			</header>
			{isLoading && !config && <p role="status">正在加载模型配置…</p>}
			{loadError && !config && (
				<div className="mc-warn" role="alert">
					<p>{loadError}</p>
					<Button variant="secondary" size="sm" onClick={() => void refresh()}>
						重试
					</Button>
				</div>
			)}
			{config && needsSetup && (
				<p className="mc-warn" role="status">
					{hasService
						? "还差一步：在第 2 步选择默认使用的模型。"
						: "还没有可用的模型。先完成第 1 步添加模型服务，再在第 2 步选择默认模型。"}
				</p>
			)}
			{config && (
				<ol className="mc-steps">
					<li className="mc-step" data-state={hasService ? "done" : "current"}>
						<ProviderSection reauthProvider={params.get("reauth")} />
					</li>
					<li
						className="mc-step"
						data-state={
							!needsSetup ? "done" : hasService ? "current" : "pending"
						}
					>
						<SlotSection />
					</li>
					<li className="mc-step" data-state="info">
						<UsageSection />
					</li>
				</ol>
			)}
		</div>
	);
}
