import { render, screen, fireEvent } from '@testing-library/react';
import React, { useContext } from 'react';
import { expect, test } from 'vitest';
import { AiWidgetProvider, useAiWidget } from '../AiWidgetContext';

function TestComponent() {
  const { widgetState, setWidgetState } = useAiWidget();
  return (
    <div>
      <span data-testid="state">{widgetState}</span>
      <button onClick={() => setWidgetState('EXPANDED')}>Expand</button>
    </div>
  );
}

test('provides default state and allows state updates', () => {
  render(
    <AiWidgetProvider>
      <TestComponent />
    </AiWidgetProvider>
  );
  expect(screen.getByTestId('state').textContent).toBe('HIDDEN');
  fireEvent.click(screen.getByText('Expand'));
  expect(screen.getByTestId('state').textContent).toBe('EXPANDED');
});
