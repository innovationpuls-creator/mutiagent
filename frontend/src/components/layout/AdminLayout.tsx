import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import "../../pages/admin/admin.css";

const adminRoutes = [
	{ label: "账号管理", path: "/admin/accounts", hint: "用户账号管理" },
	{ label: "人培方案", path: "/admin/programs", hint: "上传与发布人培方案" },
	{ label: "数据管理", path: "/admin/data", hint: "学习数据与人培方案管理" },
	{
		label: "知识库",
		path: "/admin/knowledge-base",
		hint: "教材来源与未覆盖待办",
	},
];

export function AdminLayout() {
	const location = useLocation();
	const reduceMotion = useReducedMotion();
	const { user } = useAuth();

	return (
		<motion.main
			className="admin-page"
			initial={reduceMotion ? false : { opacity: 0, y: 16 }}
			animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
			transition={
				reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }
			}
		>
			<div className="admin-ambient-sun" aria-hidden="true" />
			<div className="admin-paper-canvas" aria-hidden="true" />

			<nav className="admin-menu" aria-label="管理员菜单">
				<NavLink
					className="admin-logo-area"
					to="/admin/accounts"
					aria-label="回到后台首页"
				>
					<span className="admin-logo-pebble" aria-hidden="true">
						<img src="/logo.png" alt="" className="admin-logo-img" />
					</span>
					<span className="admin-logo-brand">one-tree</span>
				</NavLink>
				<span className="admin-menu-links">
					{adminRoutes.map((route) => (
						<NavLink
							key={route.path}
							to={route.path}
							className={({ isActive }) =>
								`admin-menu-link ${isActive ? "active" : ""}`
							}
							title={route.hint}
						>
							{route.label}
						</NavLink>
					))}
				</span>
				<span className="admin-user-chip">{user?.username ?? "管理员"}</span>
			</nav>

			<section className="admin-shell">
				<AnimatePresence mode="wait" initial={false}>
					<motion.div
						key={location.pathname}
						initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
						animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
						exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
						transition={
							reduceMotion
								? { duration: 0.12 }
								: { duration: 0.42, ease: [0.25, 1, 0.5, 1] }
						}
						style={{
							minHeight: "100%",
							display: "grid",
							gap: "var(--gap-md)",
						}}
					>
						<Outlet />
					</motion.div>
				</AnimatePresence>
			</section>
		</motion.main>
	);
}
