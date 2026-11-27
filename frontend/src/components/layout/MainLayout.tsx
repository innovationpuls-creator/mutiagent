import "../../pages/student-workspace.css";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import React from "react";
import { useLocation, useOutlet } from "react-router-dom";
import { Navbar } from "../ui/Navbar";
import { IcpFilingLink } from "./IcpFilingLink";

import { useStudentViewport } from "./useStudentViewport";

export function MainLayout() {
	useStudentViewport();
	const location = useLocation();
	const outlet = useOutlet();
	const reduceMotion = useReducedMotion();

	return (
		<div
			className="student-app-layout"
			style={{ display: "flex", flexDirection: "column" }}
		>
			<Navbar />
			<main
				className="student-content-viewport"
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
				<IcpFilingLink />
			</main>
		</div>
	);
}
