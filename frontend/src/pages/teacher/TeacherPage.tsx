import { motion, useReducedMotion } from 'framer-motion';
import { useAuth } from '../../contexts/AuthContext';
import './teacher.css';

export function TeacherPage() {
  const { user } = useAuth();
  const reduceMotion = useReducedMotion();

  return (
    <motion.main
      className="teacher-page"
      initial={reduceMotion ? false : { opacity: 0, y: 16 }}
      animate={reduceMotion ? undefined : { opacity: 1, y: 0 }}
      transition={reduceMotion ? undefined : { duration: 0.76, ease: [0.25, 1, 0.5, 1] }}
    >
      <section className="teacher-shell" aria-labelledby="teacher-title">
        <p className="teacher-kicker">teacher route</p>
        <h1 id="teacher-title">教师界面</h1>
        <p>{user?.username ?? '教师'}，路由已进入教师工作台。</p>
      </section>
    </motion.main>
  );
}
