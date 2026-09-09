import { useState } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import MultiSelectFilter from './MultiSelectFilter';

it('keeps the option order and focused checkbox stable while selecting the last two options', async () => {
  const user = userEvent.setup();
  const options = Array.from({ length: 30 }, (_, index) => `Brand ${index + 1}`);
  function Filter() {
    const [value, setValue] = useState([]);
    return <MultiSelectFilter label="Brand" options={options} value={value} onChange={setValue} />;
  }
  render(<Filter />);
  await user.click(screen.getByText('All brands'));
  const menu = screen.getByRole('group', { name: 'Brand options' });
  const secondLast = screen.getByRole('checkbox', { name: 'Brand 29' });
  await user.click(secondLast);
  expect(within(menu).getAllByRole('checkbox').map((input) => input.labels[0].textContent)).toEqual(options);
  expect(secondLast).toHaveFocus();
  await user.click(screen.getByRole('checkbox', { name: 'Brand 30' }));
  expect(secondLast).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'Brand 30' })).toBeChecked();
  expect(within(menu).getAllByRole('checkbox').map((input) => input.labels[0].textContent)).toEqual(options);
});

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

it('uses the supplied category wording for multiple selections', () => {
  render(
    <MultiSelectFilter
      allLabel="All categories"
      label="Category"
      onChange={() => {}}
      options={Array.from({ length: 11 }, (_, index) => `Category ${index + 1}`)}
      value={['Cats', 'Dogs']}
    />,
  );

  expect(screen.getByLabelText('Category')).toHaveTextContent('2 categories selected');
  expect(screen.getByLabelText('Search categories')).toBeInTheDocument();
});
