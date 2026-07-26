import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { lazy, Suspense } from "react";
import {
	BrowserRouter,
	Navigate,
	Outlet,
	Route,
	Routes,
	useLocation,
} from "react-router-dom";
import { IcpFilingLink } from "./components/layout/IcpFilingLink";
import { AiWidgetProvider } from "./context/AiWidgetContext";
import { useAuth } from "./contexts/AuthContext";
import type { AuthRole } from "./types/auth";

const AuthPage = lazy(() =>
	import("./components/auth/AuthPage").then(({ AuthPage: Component }) => ({
		default: Component,
	})),
);
const BlankPage = lazy(() =>
	import("./components/home/BlankPage").then(({ BlankPage: Component }) => ({
		default: Component,
	})),
);
const AdminLayout = lazy(() =>
	import("./components/layout/AdminLayout").then(
		({ AdminLayout: Component }) => ({
			default: Component,
		}),
	),
);
const MainLayout = lazy(() =>
	import("./components/layout/MainLayout").then(
		({ MainLayout: Component }) => ({
			default: Component,
		}),
	),
);
const IcebreakerFlow = lazy(() =>
	import("./components/learning/IcebreakerFlow").then(
		({ IcebreakerFlow: Component }) => ({ default: Component }),
	),
);
const AdminAccountsPage = lazy(() =>
	import("./pages/admin/AdminAccountsPage").then(
		({ AdminAccountsPage: Component }) => ({ default: Component }),
	),
);
const AdminDataPage = lazy(() =>
	import("./pages/admin/AdminDataPage").then(
		({ AdminDataPage: Component }) => ({
			default: Component,
		}),
	),
);
const AdminKnowledgeBasePage = lazy(() =>
	import("./pages/admin/AdminKnowledgeBasePage").then(
		({ AdminKnowledgeBasePage: Component }) => ({ default: Component }),
	),
);
const AdminProgramsPage = lazy(() =>
	import("./pages/admin/AdminProgramsPage").then(
		({ AdminProgramsPage: Component }) => ({ default: Component }),
	),
);
const BranchPage = lazy(() =>
	import("./pages/branch/BranchPage").then(({ BranchPage: Component }) => ({
		default: Component,
	})),
);
const CanopyPage = lazy(() =>
	import("./pages/canopy/CanopyPage").then(({ CanopyPage: Component }) => ({
		default: Component,
	})),
);
const ScratchpadCanvas = lazy(() =>
	import("./pages/canvas/ScratchpadCanvas").then(
		({ ScratchpadCanvas: Component }) => ({ default: Component }),
	),
);
const ForestQuizPage = lazy(() =>
	import("./pages/forest/ForestQuizPage").then(
		({ ForestQuizPage: Component }) => ({ default: Component }),
	),
);
const LeafPage = lazy(() =>
	import("./pages/leaf/LeafPage").then(({ LeafPage: Component }) => ({
		default: Component,
	})),
);
const SproutPage = lazy(() =>
	import("./pages/SproutPage").then(({ SproutPage: Component }) => ({
		default: Component,
	})),
);
const GlobalAiWidget = lazy(() =>
	import("./components/onboarding/GlobalAiWidget").then(
		({ GlobalAiWidget: Component }) => ({ default: Component }),
	),
);

function RouteLoadingFallback() {
	return (
		<div aria-live="polite" className="app-route-loading" role="status">
			正在加载学习空间…
		</div>
	);
}

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
				<Suspense fallback={<RouteLoadingFallback />}>
					<Routes location={location}>
						<Route path="/login" element={<AuthPage />} />
						<Route path="/onboarding" element={<IcebreakerFlow />} />

						<Route element={<ProtectedRoute />}>
							<Route element={<RoleRoute allowedRoles={["admin"]} />}>
								<Route element={<AdminLayout />}>
									<Route
										path="/admin/programs"
										element={<AdminProgramsPage />}
									/>
									<Route
										path="/admin/accounts"
										element={<AdminAccountsPage />}
									/>
									<Route path="/admin/data" element={<AdminDataPage />} />
									<Route
										path="/admin/knowledge-base"
										element={<AdminKnowledgeBasePage />}
									/>
								</Route>
								<Route
									path="/teacher"
									element={<Navigate replace to="/admin/programs" />}
								/>
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
				</Suspense>
			</motion.div>
		</AnimatePresence>
	);
}

function AppGlobalAiWidget() {
	const location = useLocation();
	const isHiddenPath =
		location.pathname === "/login" ||
		location.pathname === "/forest" ||
		location.pathname.startsWith("/forest/") ||
		location.pathname.startsWith("/admin");
	if (isHiddenPath) {
		return null;
	}
	return (
		<Suspense fallback={null}>
			<GlobalAiWidget />
		</Suspense>
	);
}

export function App() {
	return (
		<BrowserRouter
			future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
		>
			<AiWidgetProvider>
				<AnimatedRoutes />
				<AppGlobalAiWidget />
				<IcpFilingLink />
			</AiWidgetProvider>
		</BrowserRouter>
	);
}
