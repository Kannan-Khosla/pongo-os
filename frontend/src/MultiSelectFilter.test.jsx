import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import MultiSelectFilter from './MultiSelectFilter';

it('lets staff select and clear multiple brands', async () => {
  const user = userEvent.setup();
  const onChange = vi.fn();
  const { rerender } = render(
    <MultiSelectFilter label="Brand" options={['Acana', 'Kong', 'Orijen']} value={[]} onChange={onChange} />,
  );

  await user.click(screen.getByText('All brands'));
  await user.click(screen.getByLabelText('Acana'));
  expect(onChange).toHaveBeenLastCalledWith(['Acana']);

  rerender(<MultiSelectFilter label="Brand" options={['Acana', 'Kong', 'Orijen']} value={['Acana']} onChange={onChange} />);
  await user.click(screen.getByLabelText('Kong'));
  expect(onChange).toHaveBeenLastCalledWith(['Acana', 'Kong']);

  rerender(<MultiSelectFilter label="Brand" options={['Acana', 'Kong', 'Orijen']} value={['Acana', 'Kong']} onChange={onChange} />);
  expect(screen.getByText('2 brands selected')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Clear' }));
  expect(onChange).toHaveBeenLastCalledWith([]);
});
