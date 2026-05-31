import { render } from '@testing-library/react';
import React from 'react';
import { expect, test } from 'vitest';
import { AiGreetingInput } from '../AiGreetingInput';
import { AiWidgetProvider } from '../../../context/AiWidgetContext';

test('renders AiGreetingInput cleanly without CSS areas', () => {
  const { container } = render(
    <AiWidgetProvider>
      <AiGreetingInput />
    </AiWidgetProvider>
  );
  // Ensure the 15 css-hover grid areas are removed
  expect(container.querySelectorAll('.area').length).toBe(0);
});
