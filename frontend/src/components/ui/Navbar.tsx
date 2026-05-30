import { useEffect, useId, useRef, useState } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion, type Variants } from 'framer-motion';
import { LogOut, Settings, User } from 'lucide-react';
import styles from './Navbar.module.css';

const NAVBAR_BLUR_SCROLL_Y = 100;

/** Navigation tabs — plant-growth learning journey */
interface NavTab {
  label: string;
  path: string;
  hint: string;
}

const NAV_TABS: NavTab[] = [
  { label: '萌芽', path: '/sprout', hint: '用户画像采集' },
  { label: '繁枝', path: '/branch', hint: '课程学习总览' },
  { label: '叶茂', path: '/leaf', hint: '知识图谱入口' },
  { label: '成林', path: '/forest', hint: '学习资源生成' },
  { label: '成森', path: '/canopy', hint: '测验与巩固' },
];

const dropdownVariants: Variants = {
  hidden: { opacity: 0, y: -12, scale: 0.96 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.42,
      ease: [0.25, 1, 0.5, 1] as const,
    },
  },
  exit: {
    opacity: 0,
    y: -8,
    scale: 0.98,
    transition: {
      duration: 0.12,
      ease: [0.33, 1, 0.68, 1] as const,
    },
  },
};

export function Navbar() {
  const reduceMotion = useReducedMotion();
  const dropdownId = useId();
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [isScrolled, setIsScrolled] = useState(false);
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      const shouldBlur = window.scrollY > NAVBAR_BLUR_SCROLL_Y;
      setIsScrolled((wasScrolled) => (wasScrolled === shouldBlur ? wasScrolled : shouldBlur));
    };

    handleScroll();
    window.addEventListener('scroll', handleScroll, { passive: true });

    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  useEffect(() => {
    if (!isDropdownOpen) {
      return undefined;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target;

      if (target instanceof Node && dropdownRef.current && !dropdownRef.current.contains(target)) {
        setIsDropdownOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handlePointerDown);
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      document.removeEventListener('mousedown', handlePointerDown);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [isDropdownOpen]);

  const closeDropdown = () => setIsDropdownOpen(false);

  return (
    <header className={`${styles.navbarWrapper} ${isScrolled ? styles.scrolled : ''}`}>
      <nav className={styles.navContent} aria-label="主导航">
        <Link className={styles.logoArea} to="/home" aria-label="回到主页">
          <span className={styles.logoPebble} aria-hidden="true">
            <img src="/logo.png" alt="" className={styles.logoImg} />
          </span>
          <span className={styles.logoBrand}>one-tree</span>
        </Link>

        <div className={styles.tabBar} role="navigation" aria-label="学习阶段">
          {NAV_TABS.map((tab) => (
            <NavLink
              key={tab.path}
              to={tab.path}
              className={({ isActive }) =>
                `${styles.tabItem} ${isActive ? styles.tabActive : ''}`
              }
              title={tab.hint}
            >
              <span className={styles.tabLabel}>{tab.label}</span>
              <span className={styles.tabHint}>{tab.hint}</span>
            </NavLink>
          ))}
        </div>

        <div className={styles.menuArea} ref={dropdownRef}>
          <button
            className={styles.avatarButton}
            type="button"
            onClick={() => setIsDropdownOpen((isOpen) => !isOpen)}
            aria-expanded={isDropdownOpen}
            aria-controls={isDropdownOpen ? dropdownId : undefined}
            aria-label="切换个人菜单"
            aria-haspopup="menu"
          >
            <span aria-hidden="true">访</span>
          </button>

          <AnimatePresence>
            {isDropdownOpen && (
              <motion.div
                id={dropdownId}
                className={styles.dropdownMenu}
                role="menu"
                aria-label="个人菜单"
                variants={reduceMotion ? undefined : dropdownVariants}
                initial={reduceMotion ? { opacity: 0 } : 'hidden'}
                animate={reduceMotion ? { opacity: 1 } : 'visible'}
                exit={reduceMotion ? { opacity: 0 } : 'exit'}
                transition={reduceMotion ? { duration: 0.12 } : undefined}
              >
                <div className={styles.dropdownHeader}>
                  <span className={styles.dropdownName}>个人空间</span>
                  <span className={styles.dropdownMeta}>本地会话</span>
                </div>

                <button className={styles.dropdownItem} type="button" role="menuitem" onClick={closeDropdown}>
                  <User strokeWidth={1.5} aria-hidden="true" />
                  <span>个人资料</span>
                </button>
                <button className={styles.dropdownItem} type="button" role="menuitem" onClick={closeDropdown}>
                  <Settings strokeWidth={1.5} aria-hidden="true" />
                  <span>偏好设置</span>
                </button>
                <button className={styles.dropdownItem} type="button" role="menuitem" onClick={closeDropdown}>
                  <LogOut strokeWidth={1.5} aria-hidden="true" />
                  <span>退出登录</span>
                </button>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </nav>
    </header>
  );
}
