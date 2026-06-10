import { describe, expect, it, vi } from 'vitest';

describe('API_BASE_URL', () => {
  it('uses the local backend port when the browser hostname is localhost', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.resetModules();
    vi.stubGlobal('window', {
      location: {
        hostname: 'localhost',
        origin: 'http://localhost:5173',
        protocol: 'http:',
      },
    });

    const module = await import('./http');

    expect(module.API_BASE_URL).toBe('http://localhost:8000');

    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('uses the current origin for non-local public deployments', async () => {
    vi.stubEnv('NODE_ENV', 'development');
    vi.resetModules();
    vi.stubGlobal('window', {
      location: {
        hostname: 'app.example.com',
        origin: 'https://app.example.com',
        protocol: 'https:',
      },
    });

    const module = await import('./http');

    expect(module.API_BASE_URL).toBe('https://app.example.com');

    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });
});
