import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import { AnimatePresence } from 'framer-motion';
import { AuthPage } from './components/auth/AuthPage';
import { IcebreakerFlow } from './components/learning/IcebreakerFlow';
import { HomePage } from './components/home/HomePage';
import { MainLayout } from './components/layout/MainLayout';

function AnimatedRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <Routes location={location} key={location.pathname}>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/onboarding" element={<IcebreakerFlow />} />
        
        <Route element={<MainLayout />}>
          <Route path="/home" element={<HomePage />} />
          <Route path="/canvas" element={<div style={{ padding: 'var(--space-32)', color: 'var(--color-text-primary)' }}>Welcome to the Canvas!</div>} />
        </Route>
        
        <Route path="*" element={<Navigate replace to="/login" />} />
      </Routes>
    </AnimatePresence>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AnimatedRoutes />
    </BrowserRouter>
  );
}
