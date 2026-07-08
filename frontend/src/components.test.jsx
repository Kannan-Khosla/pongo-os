import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { Button, DataTable, FilterBar } from './components.jsx';
import './App.css';

describe('design system components', () => {
  it('fires primary button clicks and blocks disabled clicks', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    const disabledClick = vi.fn();

    render(
      <>
        <Button variant="primary" onClick={onClick}>Save</Button>
        <Button disabled onClick={disabledClick}>Disabled</Button>
      </>,
    );

    await user.click(screen.getByRole('button', { name: 'Save' }));
    await user.click(screen.getByRole('button', { name: 'Disabled' }));

    expect(onClick).toHaveBeenCalledTimes(1);
    expect(disabledClick).not.toHaveBeenCalled();
  });

  it('renders rows, empty state, loading state, and a scroll container', () => {
    const { rerender } = render(<DataTable columns={['SKU', 'Description']} rows={[{ SKU: 'SMOKE-001', Description: 'Smoke Test Item' }]} />);
    expect(screen.getByText('SMOKE-001')).toBeInTheDocument();
    expect(screen.getByTestId('table-scroll-container')).toHaveClass('table-scroll');

    rerender(<DataTable columns={['SKU']} rows={[]} emptyMessage="Nothing here." />);
    expect(screen.getByText('Nothing here.')).toBeInTheDocument();

    rerender(<DataTable columns={['SKU']} rows={[]} loading />);
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('updates and clears filter search input', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const onClear = vi.fn();
    render(<FilterBar value="" onChange={onChange} onClear={onClear} />);

    await user.type(screen.getByLabelText('Search'), 'smoke');
    await user.click(screen.getByRole('button', { name: 'Clear' }));

    expect(onChange).toHaveBeenCalled();
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});
