import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ScratchpadCanvas } from './ScratchpadCanvas';
import { AuthProvider } from '../../contexts/AuthContext';

function stubAuth() {
  const store: Record<string, string> = {
    'mutiagent-auth': JSON.stringify({
      token: 'token-1',
      user: {
        uid: 'user-1',
        username: '测试用户',
        identifier: 'user@example.com',
        provider: 'password',
        is_active: true,
      },
    }),
  };
  vi.stubGlobal('localStorage', {
    getItem: vi.fn((key: string) => store[key] ?? null),
  });
}

describe('ScratchpadCanvas', () => {
  it('should render canvas whiteboard and react to tool changes', () => {
    stubAuth();
    
    // Stub canvas for crop method
    HTMLCanvasElement.prototype.getContext = vi.fn().mockReturnValue({
      fillRect: vi.fn(),
      translate: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      strokeRect: vi.fn(),
      fillText: vi.fn(),
    });
    HTMLCanvasElement.prototype.toDataURL = vi.fn().mockReturnValue('data:image/png;base64,drawing');

    render(
      <AuthProvider>
        <ScratchpadCanvas />
      </AuthProvider>
    );

    // Verify toolbar items exist
    expect(screen.getByTitle('画笔')).toBeDefined();
    expect(screen.getByTitle('套索工具 (框选追问)')).toBeDefined();
    expect(screen.getByTitle('移动画布')).toBeDefined();
    expect(screen.getByTitle('新建便签')).toBeDefined();
    expect(screen.getByTitle('代码容器')).toBeDefined();

    // Verify initial sticky notes are rendered
    expect(screen.getByText(/多模态 AI 交互脑图/)).toBeDefined();

    // Switch tool to lasso
    const lassoBtn = screen.getByTitle('套索工具 (框选追问)');
    fireEvent.click(lassoBtn);
    expect(lassoBtn.className).toContain('is-active');
  });
});
