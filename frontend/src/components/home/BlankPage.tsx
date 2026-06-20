import { motion, useReducedMotion } from "framer-motion";
import "./BlankPage.css";

interface BlankPageProps {
	title: string;
}

export function BlankPage({ title }: BlankPageProps) {
	const reduceMotion = useReducedMotion();

	return (
		<motion.main
			className="home-page"
			initial={reduceMotion ? false : { opacity: 0 }}
			animate={reduceMotion ? undefined : { opacity: 1 }}
			exit={
				reduceMotion
					? { opacity: 0 }
					: { opacity: 0, filter: "blur(10px)", transition: { duration: 0.4 } }
			}
		>
			<div className="home-ambient-sun" aria-hidden="true" />
			<div className="home-paper-canvas" aria-hidden="true" />

			<section className="home-content">
				<h2 style={{ opacity: 0, pointerEvents: "none" }}>{title}</h2>
			</section>
		</motion.main>
	);
}
