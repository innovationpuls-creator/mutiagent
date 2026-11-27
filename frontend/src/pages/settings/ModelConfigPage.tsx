import { useSearchParams } from "react-router-dom";
import { ModelQuickSwitcher } from "../../components/models/ModelQuickSwitcher";
import { useAuth } from "../../contexts/AuthContext";
import { useModelConfig } from "../../contexts/ModelConfigContext";
import "./model-config.css";
import { ProviderSection } from "./ProviderSection";
import { SlotSection } from "./SlotSection";
import { UsageSection } from "./UsageSection";

export function ModelConfigPage() {
	const { user } = useAuth();
	const { config, isLoading, loadError, needsSetup, refresh } =
		useModelConfig();
	const [params] = useSearchParams();
	const isAdmin = user?.role === "admin";

	return (
		<div className={`mc-page ${isAdmin ? "mc-page-admin" : "mc-page-student"}`}>
			<header className="mc-hero">
				<p className="mc-kicker">个人设置</p>
				<h1>模型配置</h1>
				<p className="mc-hint">
					配置只属于你自己：你的 Key、你的模型、你的思考深度。
					{isAdmin ? "管理员可额外配置教材翻译与公开教材搜书。" : ""}
				</p>
				{config && <ModelQuickSwitcher />}
			</header>
			{isLoading && !config && <p role="status">正在加载模型配置…</p>}
			{loadError && !config && (
				<div className="mc-warn" role="alert">
					<p>{loadError}</p>
					<button
						type="button"
						className="mc-btn"
						onClick={() => void refresh()}
					>
						重试
					</button>
				</div>
			)}
			{config && needsSetup && (
				<p className="mc-warn" role="status">
					你还没有可用的默认模型。先在下方添加
					Provider，再到「场景槽位」选择主力模型。
				</p>
			)}
			{config && (
				<>
					<ProviderSection reauthProvider={params.get("reauth")} />
					<SlotSection />
					<UsageSection />
				</>
			)}
		</div>
	);
}
