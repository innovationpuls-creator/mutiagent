import { render } from '@testing-library/react';
import React from 'react';
import { expect, test } from 'vitest';
import { AiEyes } from '../AiEyes';

test('renders the AiEyes component', () => {
  const { container } = render(<AiEyes layoutId="test-eyes" />);
  expect(container.querySelector('.eyes')).toBeDefined();
});
