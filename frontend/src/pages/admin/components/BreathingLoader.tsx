import { useEffect } from "react";

interface BreathingLoaderProps {
	onFinished: () => void;
}

export function BreathingLoader({ onFinished }: BreathingLoaderProps) {
	useEffect(() => {
		const timer = setTimeout(() => {
			onFinished();
		}, 3000);
		return () => clearTimeout(timer);
	}, [onFinished]);

	return (
		<div className="loader-container">
			<div className="pulse-halo-container">
				<div className="pulse-halo breathing" />
			</div>
			<div className="loader-content">
				<h3 className="loader-title">正在读取培养方案并由AI对齐大纲...</h3>
				<p className="loader-subtitle">
					解析人培体系、智能提取核心知识节点，这需要几秒钟的宁静时刻
				</p>
			</div>
		</div>
	);
}
