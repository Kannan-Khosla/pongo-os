import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App.jsx';
import './App.css';

const item = {
  id: 1,
  SKU: 'SMOKE-001',
  Barcode: 'SMOKE001',
  Description: 'Smoke Test Item',
  Category: 'Test Category',
  Brand: 'Smoke Brand',
  Warehouse: 'Main Warehouse',
  'Inventory Location': 'Smoke Rack',
  'Default Location': 'Smoke Rack',
  'In Stock': 9,
  Allocated: 2,
  'Unit Cost': 4.25,
  active: true,
};

function json(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
}

function mockFetch(url) {
  const target = String(url);
  if (target.includes('/api/dashboard')) return json({ inventory_health: {}, order_operations: {}, routes: {}, warnings: [], activity: [] });
  if (target.match(/\/api\/items\/1$/)) return json({ item, stock_by_location: [], recent_activity: [] });
  if (target.includes('/api/items')) return json({ items: [item], total: 1 });
  if (target.includes('/api/locations')) return json({ locations: [{ id: 1, warehouse: 'Main Warehouse', code: 'Smoke Rack', name: 'Smoke Rack', isActive: true }] });
  if (target.includes('/api/inventory/summary/by-location')) return json({ total_items: 1, total_in_stock: 9, total_sellable: 7, groups: [] });
  if (target.includes('/api/inventory/locations')) return json({ rows: [] });
  if (target.includes('/api/cycle-counts')) return json({ cycle_counts: [] });
  if (target.includes('/api/orders/open')) return json({ orders: [], total: 0 });
  if (target.includes('/api/orders/completed')) return json({ orders: [], total: 0 });
  if (target.includes('/api/allocations')) return json({ allocations: [] });
  if (target.includes('/api/picks')) return json({ picks: [] });
  if (target.includes('/api/fulfillments')) return json({ fulfillments: [] });
  if (target.includes('/api/routes/candidates')) return json({ total_candidates: 0, candidates: [] });
  if (target.includes('/api/routes')) return json({ routes: [], total: 0 });
  if (target.includes('/api/integrations/woocommerce/status')) return json({ configured: false, message: 'WooCommerce credentials are not configured.', base_url_present: false, consumer_key_present: false, consumer_secret_present: false });
  if (target.includes('/api/integrations/woocommerce/sync-runs')) return json({ sync_runs: [] });
  if (target.includes('/api/integrations/woocommerce/remap')) return json({ candidates: [], mappings: [] });
  if (target.includes('/api/reports/inventory-valuation/summary')) return json({ total_skus: 1, total_units: 9 });
  if (target.includes('/api/reports/inventory-valuation')) return json([{ sku: 'SMOKE-001', description: 'Smoke Test Item', in_stock: 9 }]);
  if (target.includes('/api/reports/received-inventory/summary')) return json({ total_receipts: 0, total_lines: 0, by_location: [] });
  if (target.includes('/api/reports/received-inventory')) return json([]);
  if (target.includes('/api/reports/fulfillments/summary')) return json({ total_fulfillments: 0, by_location: [], by_sku: [] });
  if (target.includes('/api/reports/fulfillments')) return json([]);
  if (target.includes('/api/reports/sku-orders/summary')) return json({ total_skus: 0 });
  if (target.includes('/api/reports/sku-orders')) return json([]);
  if (target.includes('/api/scanner/inventory/lookup')) return json({ matched: false, message: 'No item matched that scan.' });
  return json({});
}

describe('App shell and workflows', () => {
  beforeEach(() => {
    window.location.hash = '';
    vi.stubGlobal('fetch', vi.fn(mockFetch));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('renders the app command center without crashing', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Command Center', level: 1 })).toBeInTheDocument();
  });

  it('renders sidebar navigation and keeps one active nav item', async () => {
    const user = userEvent.setup();
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(nav).toBeInTheDocument();
    expect(document.querySelectorAll('.nav-link.active')).toHaveLength(1);

    await user.click(within(nav).getByRole('link', { name: /Items/i }));
    await screen.findByRole('heading', { name: 'Items' });
    expect(document.querySelectorAll('.nav-link.active')).toHaveLength(1);
  });

  it('renders items table and opens item detail from the SKU cell', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('button', { name: /SMOKE-001/i }));

    expect(await screen.findByRole('dialog', { name: 'Item detail' })).toBeInTheDocument();
  });

  it('runs item search when a barcode scanner sends Enter in the search box', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    const searchInput = screen.getByPlaceholderText('Search SKU, barcode, description, brand');

    await user.type(searchInput, 'SMOKE001');
    expect(searchInput).toHaveValue('SMOKE001');
    fetch.mockClear();

    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/items') && String(url).includes('search=SMOKE001'))).toBe(true);
    });
  });

  it('switches scanner modes and shows a no-match result cleanly', async () => {
    const user = userEvent.setup();
    window.location.hash = '#scanner';
    render(<App />);

    await screen.findByRole('heading', { name: 'Scanner Console' });
    await user.click(screen.getByRole('button', { name: 'Location Lookup' }));
    expect(screen.getByPlaceholderText('Scan location code or name')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Inventory Lookup' }));
    await user.type(screen.getByPlaceholderText('Scan SKU, barcode, or item ID'), 'missing');
    await user.click(screen.getByRole('button', { name: 'Scan' }));
    expect(await screen.findByText('No item matched that scan.')).toBeInTheDocument();
  });

  it('renders only the selected report panel and switches reports', async () => {
    const user = userEvent.setup();
    window.location.hash = '#reports';
    render(<App />);

    await screen.findByRole('heading', { name: 'Inventory Valuation' });
    expect(screen.queryByRole('heading', { name: 'Received Inventory Report' })).not.toBeInTheDocument();

    const nav = screen.getByLabelText('Report list');
    await user.click(within(nav).getByRole('button', { name: 'Received Inventory' }));
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Received Inventory Report' })).toBeInTheDocument());
    expect(screen.queryByRole('heading', { name: 'Inventory Valuation' })).not.toBeInTheDocument();
  });

  it.each([
    ['#items', 'Items'],
    ['#inventory', 'Inventory'],
    ['#reports', 'Reports'],
    ['#scanner', 'Scanner'],
    ['#cycle-count', 'Cycle Count'],
  ])('renders the %s page', async (hash, heading) => {
    window.location.hash = hash;
    render(<App />);

    expect(await screen.findByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
  });

  it('styles dashboard quick actions as action rows, not default links', async () => {
    render(<App />);

    const quickAction = await screen.findByRole('link', { name: /Import Items/i });
    expect(quickAction).toHaveClass('widget-row');
    expect(quickAction).not.toHaveClass('nav-link');
  });

  it('keeps data tables inside scrollable table cards', async () => {
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    expect(document.querySelector('.table-wrap.table-card, .table-wrap')).toBeInTheDocument();
    expect(document.querySelector('.table-scroll')).toBeInTheDocument();
  });

  it('disables placeholder future buttons with an explanatory title', async () => {
    window.location.hash = '#/items/categories';
    render(<App />);

    await screen.findByRole('heading', { name: 'Categories' });
    const unavailableButtons = screen.getAllByTitle('Not available yet');
    expect(unavailableButtons.length).toBeGreaterThan(0);
    unavailableButtons.forEach((button) => expect(button).toBeDisabled());
  });

  it('renders Orders parent navigation and expands Orders sub-navigation when active', async () => {
    window.location.hash = '#/orders/open';
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('button', { name: /Orders/i })).toHaveAttribute('aria-expanded', 'true');
    expect(within(nav).getByRole('link', { name: 'Open Orders' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Allocate Orders' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Pick Orders' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Fulfillment' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Completed Orders' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Order History' })).toBeInTheDocument();
  });

  it('shows Open Orders only and removes the old Orders header tabs', async () => {
    window.location.hash = '#/orders/open';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Open Orders', level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Pick Scanner' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Completed Orders' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Allocation History' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Pick History' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Fulfillment History' })).not.toBeInTheDocument();
    expect(document.querySelectorAll('.page-tabs .tab')).toHaveLength(0);
    expect(screen.queryByRole('button', { name: /Preview Pick/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Preview Fulfillment/i })).not.toBeInTheDocument();
  });

  it('runs open order search when a barcode scanner sends Enter in the search box', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    const searchInput = screen.getByPlaceholderText('Order, customer, SKU, barcode');

    await user.type(searchInput, 'SMOKE001');
    expect(searchInput).toHaveValue('SMOKE001');
    fetch.mockClear();

    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/orders/open') && String(url).includes('search=SMOKE001'))).toBe(true);
    });
  });

  it.each([
    ['Allocate Orders', '#/orders/allocate', 'Allocation workflow'],
    ['Pick Orders', '#/orders/pick', 'Pick Scanner'],
    ['Fulfillment', '#/orders/fulfillment', 'Fulfillment workflow'],
    ['Completed Orders', '#/orders/completed', 'No completed orders match'],
    ['Order History', '#/orders/history', 'Allocation History'],
  ])('shows the %s Orders subpage', async (heading, hash, expectedText) => {
    window.location.hash = hash;
    render(<App />);

    expect(await screen.findByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
    expect(await screen.findByText(expectedText, { exact: false })).toBeInTheDocument();
  });

  it('navigates between Orders subpages from the sidebar', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    await user.click(within(nav).getByRole('link', { name: 'Pick Orders' }));

    expect(await screen.findByRole('heading', { name: 'Pick Orders', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pick Scanner' })).toBeInTheDocument();
  });
});
