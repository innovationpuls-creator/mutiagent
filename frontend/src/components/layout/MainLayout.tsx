import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import React from "react";
import { useLocation, useOutlet } from "react-router-dom";
import { Navbar } from "../ui/Navbar";

export function MainLayout() {
	const location = useLocation();
	const outlet = useOutlet();
	const reduceMotion = useReducedMotion();

	return (
		<div
			style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}
		>
			<Navbar />
			<main
				style={{
					flex: 1,
					display: "flex",
					flexDirection: "column",
					position: "relative",
				}}
			>
				<AnimatePresence mode="wait" initial={false}>
					{outlet && (
						<motion.div
							key={location.pathname}
							initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 10 }}
							animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
							exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -10 }}
							transition={
								reduceMotion
									? { duration: 0.12 }
									: { duration: 0.42, ease: [0.25, 1, 0.5, 1] }
							}
							style={{ display: "flex", flex: 1, flexDirection: "column" }}
						>
							{React.cloneElement(outlet as React.ReactElement)}
						</motion.div>
					)}
				</AnimatePresence>
			</main>
		</div>
	);
}
