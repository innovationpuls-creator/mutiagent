import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { AuthPage } from './components/auth/AuthPage';
import { IcebreakerFlow } from './components/learning/IcebreakerFlow';
import { BlankPage } from './components/home/BlankPage';
import { MainLayout } from './components/layout/MainLayout';
import { SproutPage } from './pages/SproutPage';

function AnimatedRoutes() {
  const location = useLocation();
  const isAppRoute = ['/sprout', '/branch', '/leaf', '/forest', '/canopy', '/canvas'].includes(location.pathname);
  const routeKey = isAppRoute ? 'app' : location.pathname;

  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={routeKey}>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/onboarding" element={<IcebreakerFlow />} />
        
        <Route element={<MainLayout />}>
          <Route path="/sprout" element={<SproutPage />} />
          <Route path="/branch" element={<BlankPage title="繁枝" />} />
          <Route path="/leaf" element={<BlankPage title="叶茂" />} />
          <Route path="/forest" element={<BlankPage title="成林" />} />
          <Route path="/canopy" element={<BlankPage title="成森" />} />
          <Route path="/canvas" element={<div style={{ padding: 'var(--space-32)', color: 'var(--color-text-primary)' }}>Welcome to the Canvas!</div>} />
        </Route>
        
        <Route path="*" element={<Navigate replace to="/login" />} />
      </Routes>
    </AnimatePresence>
  );
}

import { AiWidgetProvider } from './context/AiWidgetContext';
import { GlobalAiWidget } from './components/onboarding/GlobalAiWidget';

export function App() {
  return (
    <BrowserRouter>
      <AiWidgetProvider>
        <AnimatedRoutes />
        <GlobalAiWidget />
      </AiWidgetProvider>
    </BrowserRouter>
  );
}
