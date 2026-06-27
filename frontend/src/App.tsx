import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
	BrowserRouter,
	Navigate,
	Outlet,
	Route,
	Routes,
	useLocation,
} from "react-router-dom";
import { AuthPage } from "./components/auth/AuthPage";
import { BlankPage } from "./components/home/BlankPage";
import { MainLayout } from "./components/layout/MainLayout";
import { IcebreakerFlow } from "./components/learning/IcebreakerFlow";
import { useAuth } from "./contexts/AuthContext";
import { AdminAccountsPage } from "./pages/admin/AdminAccountsPage";
import { AdminDataPage } from "./pages/admin/AdminDataPage";
import { BranchPage } from "./pages/branch/BranchPage";
import { CanopyPage } from "./pages/canopy/CanopyPage";
import { ScratchpadCanvas } from "./pages/canvas/ScratchpadCanvas";
import { ForestQuizPage } from "./pages/forest/ForestQuizPage";
import { LeafPage } from "./pages/leaf/LeafPage";
import { SproutPage } from "./pages/SproutPage";
import { TeacherPage } from "./pages/teacher/TeacherPage";
import type { AuthRole } from "./types/auth";

function homeForRole(role: AuthRole): string {
	if (role === "admin") return "/admin/programs";
	return "/sprout";
}

function ProtectedRoute() {
	const { user, isAuthReady } = useAuth();

	if (!isAuthReady) {
		return null;
	}

	if (!user) {
		return <Navigate replace to="/login" />;
	}

	return <Outlet />;
}

function RoleRoute({ allowedRoles }: { allowedRoles: AuthRole[] }) {
	const { user, isAuthReady } = useAuth();

	if (!isAuthReady) {
		return null;
	}

	if (!user) {
		return <Navigate replace to="/login" />;
	}

	if (!allowedRoles.includes(user.role)) {
		return <Navigate replace to={homeForRole(user.role)} />;
	}

	return <Outlet />;
}

function AnimatedRoutes() {
	const location = useLocation();
	const reduceMotion = useReducedMotion();
	const isAppRoute = [
		"/sprout",
		"/branch",
		"/leaf",
		"/forest",
		"/canopy",
		"/canvas",
		"/teacher",
		"/admin",
	].some(
		(path) =>
			location.pathname === path || location.pathname.startsWith(`${path}/`),
	);
	const routeKey = isAppRoute ? "app" : location.pathname;

	return (
		<AnimatePresence mode="wait" initial={false}>
			<motion.div
				key={routeKey}
				initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
				animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
				exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
				transition={
					reduceMotion
						? { duration: 0.12 }
						: { duration: 0.42, ease: [0.25, 1, 0.5, 1] }
				}
				style={{ minHeight: "100%" }}
			>
				<Routes location={location}>
					<Route path="/login" element={<AuthPage />} />
					<Route path="/onboarding" element={<IcebreakerFlow />} />

					<Route element={<ProtectedRoute />}>
						<Route element={<RoleRoute allowedRoles={["admin"]} />}>
							<Route path="/admin/programs" element={<TeacherPage />} />
							<Route
								path="/teacher"
								element={<Navigate replace to="/admin/programs" />}
							/>
							<Route path="/admin/accounts" element={<AdminAccountsPage />} />
							<Route path="/admin/data" element={<AdminDataPage />} />
						</Route>

						<Route element={<RoleRoute allowedRoles={["student"]} />}>
							<Route element={<MainLayout />}>
								<Route path="/sprout" element={<SproutPage />} />
								<Route path="/branch" element={<BranchPage />} />
								<Route path="/leaf" element={<BranchPage />} />
								<Route path="/leaf/:courseNodeId" element={<LeafPage />} />
								<Route path="/forest" element={<BlankPage title="成林" />} />
								<Route
									path="/forest/:courseNodeId"
									element={<ForestQuizPage />}
								/>
								<Route path="/canopy" element={<CanopyPage />} />
								<Route path="/canvas" element={<ScratchpadCanvas />} />
							</Route>
						</Route>
					</Route>

					<Route path="*" element={<Navigate replace to="/login" />} />
				</Routes>
			</motion.div>
		</AnimatePresence>
	);
}

import { GlobalAiWidget } from "./components/onboarding/GlobalAiWidget";
import { AiWidgetProvider } from "./context/AiWidgetContext";

function AppGlobalAiWidget() {
	const location = useLocation();
	if (
		location.pathname === "/forest" ||
		location.pathname.startsWith("/forest/")
	) {
		return null;
	}
	return <GlobalAiWidget />;
}

export function App() {
	return (
		<BrowserRouter
			future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
		>
			<AiWidgetProvider>
				<AnimatedRoutes />
				<AppGlobalAiWidget />
			</AiWidgetProvider>
		</BrowserRouter>
	);
}
