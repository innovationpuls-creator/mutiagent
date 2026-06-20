import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { SproutHero } from "../components/home/SproutHero";
import { SproutInitOverlay } from "../components/onboarding/SproutInitOverlay";
import { useAiWidget } from "../context/AiWidgetContext";
import "../components/home/BlankPage.css";

const SPROUT_INIT_OVERLAY_KEY = "mutiagent-sprout-init-overlay";

export function SproutPage() {
	const location = useLocation();
	const reduceMotion = useReducedMotion();
	const { pendingMessage, widgetState } = useAiWidget();
	const isFirstLogin = location.state?.isFirstLogin === true;
	const [showOverlay, setShowOverlay] = useState(() => {
		if (isFirstLogin) return true;
		if (typeof window === "undefined") return false;
		return window.sessionStorage.getItem(SPROUT_INIT_OVERLAY_KEY) === "1";
	});

	const handleOverlayComplete = () => {
		if (typeof window !== "undefined") {
			window.sessionStorage.removeItem(SPROUT_INIT_OVERLAY_KEY);
		}
		setShowOverlay(false);
	};

	useEffect(() => {
		if (!showOverlay) {
			return;
		}
		if (widgetState === "WIDGET") {
			handleOverlayComplete();
			return;
		}
		if (widgetState === "EXPANDED" && pendingMessage !== null) {
			handleOverlayComplete();
		}
	}, [pendingMessage, showOverlay, widgetState]);

	return (
		<>
			<motion.main
				className="home-page"
				initial={reduceMotion ? false : { opacity: 0 }}
				animate={reduceMotion ? undefined : { opacity: 1 }}
				exit={
					reduceMotion
						? { opacity: 0 }
						: { opacity: 0, transition: { duration: 0.4 } }
				}
			>
				{/* 背景层 — 保留 BlankPage 的暖色环境 */}
				<div className="home-ambient-sun" aria-hidden="true" />
				<div className="home-paper-canvas" aria-hidden="true" />

				{/* Hero 内容 */}
				<SproutHero />
			</motion.main>

			<AnimatePresence>
				{showOverlay && (
					<SproutInitOverlay onComplete={handleOverlayComplete} />
				)}
			</AnimatePresence>
		</>
	);
}
