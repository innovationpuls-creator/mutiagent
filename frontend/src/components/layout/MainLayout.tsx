import React from 'react';
import { Outlet } from 'react-router-dom';
import { Navbar } from '../ui/Navbar';

export function MainLayout() {
  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <main style={{ flex: 1 }}>
        <Outlet />
      </main>
    </div>
  );
}
