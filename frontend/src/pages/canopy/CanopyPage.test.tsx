import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { CanopyPage } from './CanopyPage';

describe('CanopyPage', () => {
  it('should render knowledge graph page with correct header and statistics', () => {
    render(<CanopyPage />);
    expect(screen.getByRole('heading', { name: '知识雨林图谱', level: 2 })).toBeDefined();
    expect(screen.getByText('已点亮叶片数')).toBeDefined();
    expect(screen.getByText('测验平均得分')).toBeDefined();
    expect(screen.getByText('专注学习时长')).toBeDefined();
  });
});
