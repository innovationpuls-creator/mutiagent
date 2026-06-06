import { BrowserRouter, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion';
import { AuthPage } from './components/auth/AuthPage';
import { IcebreakerFlow } from './components/learning/IcebreakerFlow';
import { BlankPage } from './components/home/BlankPage';
import { MainLayout } from './components/layout/MainLayout';
import { SproutPage } from './pages/SproutPage';
import { BranchPage } from './pages/branch/BranchPage';
import { useAuth } from './contexts/AuthContext';

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

function AnimatedRoutes() {
  const location = useLocation();
  const reduceMotion = useReducedMotion();
  const isAppRoute = ['/sprout', '/branch', '/leaf', '/forest', '/canopy', '/canvas'].includes(location.pathname);
  const routeKey = isAppRoute ? 'app' : location.pathname;

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={routeKey}
        initial={reduceMotion ? { opacity: 0 } : { opacity: 0, y: 12 }}
        animate={reduceMotion ? { opacity: 1 } : { opacity: 1, y: 0 }}
        exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -12 }}
        transition={reduceMotion ? { duration: 0.12 } : { duration: 0.42, ease: [0.25, 1, 0.5, 1] }}
        style={{ minHeight: '100%' }}
      >
        <Routes location={location}>
          <Route path="/login" element={<AuthPage />} />
          <Route path="/onboarding" element={<IcebreakerFlow />} />

          <Route element={<ProtectedRoute />}>
            <Route element={<MainLayout />}>
              <Route path="/sprout" element={<SproutPage />} />
              <Route path="/branch" element={<BranchPage />} />
              <Route path="/leaf" element={<BlankPage title="叶茂" />} />
              <Route path="/forest" element={<BlankPage title="成林" />} />
              <Route path="/canopy" element={<BlankPage title="成森" />} />
              <Route path="/canvas" element={<div style={{ padding: 'var(--space-32)', color: 'var(--color-text-primary)' }}>Welcome to the Canvas!</div>} />
            </Route>
          </Route>

          <Route path="*" element={<Navigate replace to="/login" />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

import { AiWidgetProvider } from './context/AiWidgetContext';
import { GlobalAiWidget } from './components/onboarding/GlobalAiWidget';

export function App() {
  return (
    <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AiWidgetProvider>
        <AnimatedRoutes />
        <GlobalAiWidget />
      </AiWidgetProvider>
    </BrowserRouter>
  );
}
