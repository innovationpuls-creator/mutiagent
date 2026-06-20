import {
	AnimatePresence,
	motion,
	useReducedMotion,
	type Variants,
} from "framer-motion";
import { LogOut } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link, NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../../contexts/AuthContext";
import { DURATION_INSTANT, motionTokens } from "../../styles/motion-tokens";
import styles from "./Navbar.module.css";

const NAVBAR_BLUR_SCROLL_Y = 100;

interface NavTab {
	label: string;
	path: string;
	hint: string;
}

const NAV_TABS: NavTab[] = [
	{ label: "萌芽", path: "/sprout", hint: "用户画像采集" },
	{ label: "繁枝", path: "/branch", hint: "课程学习总览" },
	{ label: "叶茂", path: "/leaf", hint: "知识图谱入口" },
	{ label: "成林", path: "/forest", hint: "学习资源生成" },
	{ label: "成森", path: "/canopy", hint: "测验与巩固" },
];

const navContentVariants: Variants = {
	hidden: {},
	visible: {
		transition: {
			staggerChildren: 0.18,
			delayChildren: 0.06,
		},
	},
};

const navItemVariants: Variants = {
	hidden: { opacity: 0, y: -12 },
	visible: {
		opacity: 1,
		y: 0,
		transition: motionTokens.editorial,
	},
};

const dropdownContainerVariants: Variants = {
	hidden: { opacity: 0 },
	visible: {
		opacity: 1,
		transition: {
			duration: 0.3,
			ease: motionTokens.lazy.ease,
			staggerChildren: 0.06,
			delayChildren: 0.08,
		},
	},
	exit: {
		opacity: 0,
		transition: { duration: DURATION_INSTANT },
	},
};

const dropdownItemVariants: Variants = {
	hidden: { opacity: 0, y: -8 },
	visible: {
		opacity: 1,
		y: 0,
		transition: motionTokens.lazy,
	},
	exit: {
		opacity: 0,
		y: -4,
		transition: { duration: DURATION_INSTANT },
	},
};

export function Navbar() {
	const navigate = useNavigate();
	const auth = useAuth();
	const reduceMotion = useReducedMotion();
	const dropdownId = useId();
	const dropdownRef = useRef<HTMLDivElement>(null);
	const [isScrolled, setIsScrolled] = useState(false);
	const [isDropdownOpen, setIsDropdownOpen] = useState(false);
	const [hasEntered, setHasEntered] = useState(false);
	const [isLoggingOut, setIsLoggingOut] = useState(false);

	const isLoggedIn = Boolean(auth.user);

	useEffect(() => {
		const frame = requestAnimationFrame(() => setHasEntered(true));
		return () => cancelAnimationFrame(frame);
	}, []);

	useEffect(() => {
		const handleScroll = () => {
			const shouldBlur = window.scrollY > NAVBAR_BLUR_SCROLL_Y;
			setIsScrolled((wasScrolled) =>
				wasScrolled === shouldBlur ? wasScrolled : shouldBlur,
			);
		};

		handleScroll();
		window.addEventListener("scroll", handleScroll, { passive: true });
		return () => window.removeEventListener("scroll", handleScroll);
	}, []);

	useEffect(() => {
		if (!isDropdownOpen) return undefined;

		const handlePointerDown = (event: MouseEvent) => {
			const target = event.target;
			if (
				target instanceof Node &&
				dropdownRef.current &&
				!dropdownRef.current.contains(target)
			) {
				setIsDropdownOpen(false);
			}
		};

		const handleKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") setIsDropdownOpen(false);
		};

		document.addEventListener("mousedown", handlePointerDown);
		document.addEventListener("keydown", handleKeyDown);
		return () => {
			document.removeEventListener("mousedown", handlePointerDown);
			document.removeEventListener("keydown", handleKeyDown);
		};
	}, [isDropdownOpen]);

	const closeDropdown = () => setIsDropdownOpen(false);

	const handleLogout = () => {
		closeDropdown();
		setIsLoggingOut(true);
		setTimeout(() => {
			auth.logout();
			navigate("/login");
		}, 1500);
	};

	const avatarLabel = isLoggedIn ? auth.user!.username.charAt(0) : "访";

	return (
		<>
			<header
				className={`${styles.navbarWrapper} ${isScrolled ? styles.scrolled : ""}`}
			>
				<motion.nav
					className={styles.navContent}
					aria-label="主导航"
					variants={reduceMotion ? undefined : navContentVariants}
					initial="hidden"
					animate={hasEntered ? "visible" : "hidden"}
				>
					<motion.div variants={reduceMotion ? undefined : navItemVariants}>
						<Link
							className={styles.logoArea}
							to="/sprout"
							aria-label="回到主页"
						>
							<span className={styles.logoPebble} aria-hidden="true">
								<img src="/logo.png" alt="" className={styles.logoImg} />
							</span>
							<span className={styles.logoBrand}>one-tree</span>
						</Link>
					</motion.div>

					<motion.div
						className={styles.tabBar}
						role="navigation"
						aria-label="学习阶段"
						variants={reduceMotion ? undefined : navItemVariants}
					>
						{NAV_TABS.map((tab) => (
							<NavLink
								key={tab.path}
								to={tab.path}
								className={({ isActive }) =>
									`${styles.tabItem} ${isActive ? styles.tabActive : ""}`
								}
								title={tab.hint}
							>
								{({ isActive }) => (
									<>
										{isActive &&
											(reduceMotion ? (
												<span className={styles.tabIndicator} />
											) : (
												<motion.span
													className={styles.tabIndicator}
													layoutId="navbar-tab-indicator"
													transition={motionTokens.lazy}
												/>
											))}
										<span className={styles.tabLabel}>{tab.label}</span>
										<span className={styles.tabHint}>{tab.hint}</span>
									</>
								)}
							</NavLink>
						))}
					</motion.div>

					<motion.div
						className={styles.menuArea}
						ref={dropdownRef}
						variants={reduceMotion ? undefined : navItemVariants}
					>
						<button
							className={styles.avatarButton}
							type="button"
							onClick={() => setIsDropdownOpen((isOpen) => !isOpen)}
							aria-expanded={isDropdownOpen}
							aria-controls={isDropdownOpen ? dropdownId : undefined}
							aria-label="切换个人菜单"
							aria-haspopup="menu"
						>
							<span aria-hidden="true">{avatarLabel}</span>
						</button>

						<AnimatePresence>
							{isDropdownOpen && (
								<motion.div
									id={dropdownId}
									className={styles.dropdownMenu}
									role="menu"
									aria-label="个人菜单"
									variants={
										reduceMotion ? undefined : dropdownContainerVariants
									}
									initial={reduceMotion ? { opacity: 0 } : "hidden"}
									animate={reduceMotion ? { opacity: 1 } : "visible"}
									exit={reduceMotion ? { opacity: 0 } : "exit"}
									transition={
										reduceMotion ? { duration: DURATION_INSTANT } : undefined
									}
								>
									<div className={styles.dropdownHeader}>
										<span className={styles.dropdownName}>
											{isLoggedIn ? auth.user!.username : "个人空间"}
										</span>
										<span className={styles.dropdownMeta}>
											{isLoggedIn ? auth.user!.identifier : "本地会话"}
										</span>
									</div>

									<motion.button
										className={styles.dropdownItem}
										type="button"
										role="menuitem"
										onClick={closeDropdown}
										variants={reduceMotion ? undefined : dropdownItemVariants}
										initial={reduceMotion ? { opacity: 0 } : "hidden"}
										animate={reduceMotion ? { opacity: 1 } : "visible"}
									>
										<span className={styles.dropdownSymbol} aria-hidden="true">
											·
										</span>
										<span className={styles.dropdownText}>个人资料</span>
									</motion.button>
									<motion.button
										className={styles.dropdownItem}
										type="button"
										role="menuitem"
										onClick={closeDropdown}
										variants={reduceMotion ? undefined : dropdownItemVariants}
										initial={reduceMotion ? { opacity: 0 } : "hidden"}
										animate={reduceMotion ? { opacity: 1 } : "visible"}
									>
										<span className={styles.dropdownSymbol} aria-hidden="true">
											·
										</span>
										<span className={styles.dropdownText}>偏好设置</span>
									</motion.button>
									<motion.button
										className={styles.dropdownItem}
										type="button"
										role="menuitem"
										onClick={handleLogout}
										variants={reduceMotion ? undefined : dropdownItemVariants}
										initial={reduceMotion ? { opacity: 0 } : "hidden"}
										animate={reduceMotion ? { opacity: 1 } : "visible"}
									>
										<span className={styles.dropdownSymbol} aria-hidden="true">
											—
										</span>
										<span className={styles.dropdownText}>退出登录</span>
									</motion.button>
								</motion.div>
							)}
						</AnimatePresence>
					</motion.div>
				</motion.nav>
			</header>

			{isLoggingOut && createPortal(<LogoutOverlay />, document.body)}
		</>
	);
}

function LogoutOverlay() {
	const reduceMotion = useReducedMotion();
	const auth = useAuth();

	return (
		<motion.div
			className={styles.logoutOverlay}
			initial={reduceMotion ? false : { opacity: 0 }}
			animate={reduceMotion ? undefined : { opacity: 1 }}
			transition={
				reduceMotion ? undefined : { duration: 0.6, ease: [0.25, 1, 0.5, 1] }
			}
		>
			<motion.div
				className={styles.logoutCard}
				initial={reduceMotion ? false : { opacity: 0, scale: 0.96 }}
				animate={reduceMotion ? undefined : { opacity: 1, scale: 1 }}
				transition={
					reduceMotion ? undefined : { duration: 0.6, ease: [0.25, 1, 0.5, 1] }
				}
			>
				<LogOut aria-hidden="true" className={styles.logoutIcon} />
				<h2>期待再见</h2>
				<p>
					{auth.user?.username ?? "你"}
					，思绪已经安放，随时回来继续你的学习旅程。
				</p>
			</motion.div>
		</motion.div>
	);
}
