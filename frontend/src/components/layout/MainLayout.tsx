import React from 'react';
import { useLocation, useOutlet } from 'react-router-dom';
import { Navbar } from '../ui/Navbar';
import { AnimatePresence } from 'framer-motion';

export function MainLayout() {
  const location = useLocation();
  const outlet = useOutlet();

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Navbar />
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', position: 'relative' }}>
        <AnimatePresence mode="wait">
          {outlet && React.cloneElement(outlet as React.ReactElement, { key: location.pathname })}
        </AnimatePresence>
      </main>
    </div>
  );
}
