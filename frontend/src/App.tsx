import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthPage } from './components/auth/AuthPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="*" element={<Navigate replace to="/login" />} />
      </Routes>
    </BrowserRouter>
  );
}
