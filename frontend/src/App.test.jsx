import { act, render, screen, waitFor, within } from '@testing-library/react';
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

const mockOrder = {
  id: 701,
  woo_order_id: 802,
  woo_order_number: '0802',
  woo_status: 'processing',
  local_status: 'open',
  allocation_status: 'auto_allocated',
  pick_status: 'ready_to_pick',
  completion_status: 'open',
  matched_status: 'matched',
  availability_status: 'available',
  can_pick: true,
  customer_name: 'Avery Stone',
  customer_email: 'avery@example.invalid',
  order_source: 'WooCommerce',
  shipping_city: 'Edmonton',
  shipping_state: 'AB',
  shipping_zip: 'T5J 0N3',
  shipping_via: 'Free shipping',
  company: 'Pongo Test Co.',
  ship_from: 'Main Warehouse',
  skus: ['SMOKE-001'],
  item_names: ['Smoke Test Item'],
  total_quantity_ordered: 2,
  total_quantity_allocated: 2,
  total_quantity_picked: 0,
  total_quantity_fulfilled: 0,
  total: 60,
  line_count: 1,
  date_created: '2026-07-08T10:00:00Z',
  last_synced_at: '2026-07-08T10:05:00Z',
};

const mockOrderDetail = {
  ...mockOrder,
  customer_phone: '555-0100',
  shipping_summary: { city: 'Edmonton', state: 'AB', postcode: 'T5J 0N3' },
  lines: [{
    id: 9001,
    sku: 'SMOKE-001',
    barcode: 'SMOKE001',
    name: 'Smoke Test Item',
    quantity_ordered: 2,
    quantity_allocated: 2,
    quantity_picked: 0,
    quantity_stock_reduced: 0,
    quantity_fulfilled: 0,
    remaining_to_pick: 2,
    remaining_to_fulfill: 2,
    remaining_to_allocate: 0,
    matched_status: 'matched',
    allocation_status: 'auto_allocated',
    pick_status: 'ready_to_pick',
    shortage_quantity: 0,
    local_sellable: 7,
    woo_product_id: 101,
    woo_variation_id: null,
  }],
};

const mockAllocationException = {
  order_id: 702,
  order_line_id: 9002,
  woo_order_id: 803,
  woo_order_number: '0803',
  ordered_at: '2026-07-08T11:00:00Z',
  customer_name: 'Morgan Lee',
  item_id: 1,
  sku: 'SMOKE-001',
  barcode: 'SMOKE001',
  description: 'Smoke Test Item',
  warehouse: 'Main Warehouse',
  inventory_location: 'Smoke Rack',
  quantity_ordered: 4,
  quantity_allocated: 1,
  quantity_unallocated: 3,
  quantity_picked: 0,
  quantity_available: 0,
  allocation_status: 'partially_allocated',
  exception_reason: 'out_of_stock',
};

const mockWebhookEvent = {
  id: 41,
  topic: 'order.created',
  woo_order_id: 1601,
  local_order_id: 702,
  woo_order_number: '1601',
  woo_status: 'processing',
  local_status: 'allocated',
  customer_name: 'Morgan Lee',
  currency: 'CAD',
  total: 84.5,
  created_order: true,
  received_at: '2026-07-10T17:00:00Z',
};

function emptyQuickSyncResult(overrides = {}) {
  return {
    sync_run_id: 91,
    status: 'completed',
    total_remote_records: 0,
    created_count: 0,
    updated_count: 0,
    matched_count: 0,
    skipped_count: 0,
    conflict_count: 0,
    error_count: 0,
    available_count: 0,
    partial_count: 0,
    unavailable_count: 0,
    unknown_count: 0,
    auto_allocated_count: 0,
    allocation_exception_count: 0,
    unmatched_line_count: 0,
    conflict_line_count: 0,
    pick_ready_count: 0,
    warnings: [],
    errors: [],
    ...overrides,
  };
}

let mockWebhookFeed;
let mockQuickSyncResult;

function json(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
}

function mockFetch(url) {
  const target = String(url);
  if (target.includes('/api/integrations/woocommerce/webhooks/events')) return json(typeof mockWebhookFeed === 'function' ? mockWebhookFeed(target) : mockWebhookFeed);
  if (target.includes('/api/integrations/woocommerce/orders/quick-sync')) return json(mockQuickSyncResult);
  if (target.includes('/api/business-dashboard')) return json({
    generated_at: '2026-07-08T16:30:00Z',
    today: { summary: { today_orders_count: 2, today_revenue: 90, today_new_customers: 1, today_returning_customers: 1, today_subscription_orders: 0, average_order_value_today: 45 }, data_quality: [] },
    open_orders: { summary: { open_orders_count: 1 }, rows: [{ order_number: '0802', woo_order_id: 802, customer_name: 'Avery Stone', customer_email: 'avery@example.invalid', status: 'open', placed_on: '2026-07-08T10:00:00Z', order_total: 60, city: 'Edmonton' }], data_quality: [] },
    subscriptions: { summary: { subscription_data_available: false, upcoming_7_days_count: 0, upcoming_30_days_count: 0 }, rows: [], empty_state: 'Subscription data is not synced yet.', data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'Subscription data is not synced yet. This section will populate after subscription sync is connected.' }] },
    revenue_comparison: { summary: { current_period_label: 'July 1-8', previous_period_label: 'June 1-8', current_period_revenue: 90, previous_period_revenue: 120, delta_percent: -25 }, daily_series: [{ day_index: 1, current_revenue: 20, previous_revenue: 40 }, { day_index: 2, current_revenue: 70, previous_revenue: 80 }], data_quality: [] },
    order_map: { summary: { total_orders_today: 2, total_orders_plotted: 2, total_orders_unplotted: 0 }, city_breakdown: [{ city: 'Edmonton', order_count: 1, revenue: 60, customer_count: 1 }, { city: 'Sherwood Park', order_count: 1, revenue: 30, customer_count: 1 }], markers: [{ marker_label: '0802', latitude: 53.5461, longitude: -113.4938, approximate: true }, { marker_label: '0803', latitude: 53.5412, longitude: -113.2957, approximate: true }], data_quality: [{ code: 'approximate_coordinates', severity: 'info', message: 'Map uses city-level approximate markers until address geocoding is configured.' }] },
    data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'Subscription data is not synced yet. This section will populate after subscription sync is connected.' }],
  });
  if (target.includes('/api/insights/subscriptions')) return json({ dashboard: 'subscriptions', summary: { active_subscriptions: 0 }, rows: [], data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'No WooCommerce Subscriptions snapshots are synced locally yet.' }], empty_state: 'No subscription data synced yet' });
  if (target.includes('/api/insights/customer-metrics')) return json({ dashboard: 'customer-metrics', summary: { total_customers: 2, returning_customers: 1 }, rows: [{ customer_name: 'Avery Stone', email: 'avery@example.invalid', order_count: 2, lifetime_spend: 90, last_order_date: '2026-06-20T12:00:00Z' }], data_quality: [] });
  if (target.includes('/api/insights/product-sku')) return json({ dashboard: 'product-sku', summary: { sku_count: 1, units_sold: 4, revenue: 90 }, rows: [{ sku: 'DOG-FOOD', description: 'Dog Food', brand: 'Acana', category: 'Dog Food', units_sold: 4, revenue: 90, estimated_margin: 50, current_sellable: 10 }], data_quality: [] });
  if (target.includes('/api/insights/orders-revenue')) return json({ dashboard: 'orders-revenue', summary: { total_orders: 2, average_order_value: 45, net_sales: 90 }, trends: { daily_revenue: [{ date: '2026-06-20', order_count: 2, gross_sales: 90, net_sales: 90, units_sold: 4 }] }, rows: [{ date: '2026-06-20', order_count: 2, gross_sales: 90, net_sales: 90, units_sold: 4 }], data_quality: [] });
  if (target.includes('/api/insights/overview')) return json({ dashboard: 'overview', summary: { total_revenue: 90, total_orders: 2, total_customers: 1, stockout_risk_count: 1 }, trends: { daily_revenue: [{ date: '2026-06-20', order_count: 2, net_sales: 90 }] }, tables: { stockout_risk: [{ sku: 'DOG-FOOD', description: 'Dog Food', risk_level: 'low', current_sellable: 10, daily_velocity: 1, days_of_stock_left: 10 }] }, data_quality: [{ code: 'missing_refund_data', severity: 'info', message: 'Refund detail is not synced yet.' }] });
  if (target.includes('/api/insights/')) return json({ dashboard: 'generic', summary: { total: 0 }, rows: [], data_quality: [] });
  if (target.includes('/api/dashboard')) return json({ inventory_health: {}, order_operations: {}, routes: {}, warnings: [], activity: [] });
  if (target.match(/\/api\/items\/1$/)) return json({ item, stock_by_location: [], recent_activity: [] });
  if (target.includes('/api/items')) return json({ items: [item], total: 1 });
  if (target.includes('/api/locations')) return json({ locations: [{ id: 1, warehouse: 'Main Warehouse', code: 'Smoke Rack', name: 'Smoke Rack', isActive: true }] });
  if (target.includes('/api/inventory/summary/by-location')) return json({ total_items: 1, total_in_stock: 9, total_sellable: 7, groups: [] });
  if (target.includes('/api/inventory/locations')) return json({ rows: [] });
  if (target.includes('/api/cycle-counts')) return json({ cycle_counts: [] });
  if (target.includes('/api/orders/701/complete/commit')) return json({ status: 'completed_without_picking', message: 'Order completed without picking. Stock was not reduced.', woo_sync_status: 'sent', woo_writeback_queue_id: 41 });
  if (target.includes('/api/orders/bulk/complete')) return json({ status: 'completed', requested_count: 1, succeeded_count: 1, failed_count: 0, results: [{ order_id: 701, status: 'completed', message: 'Completed.', woo_sync_status: 'sent', woo_writeback_queue_id: 41 }], errors: [] });
  if (target.includes('/api/orders/bulk/unpick')) return json({ status: 'completed', requested_count: 1, succeeded_count: 1, failed_count: 0, total_quantity_restored: 1, results: [], errors: [] });
  if (target.match(/\/api\/orders\/701$/)) return json(mockOrderDetail);
  if (target.includes('/api/orders/allocate')) return json({ orders: [], total: 0 });
  if (target.includes('/api/orders/pick')) return json({ orders: [mockOrder], total: 1, available_count: 1, partial_count: 0, unavailable_count: 0, unknown_count: 0 });
  if (target.includes('/api/orders/open')) return json({ orders: [mockOrder], total: 1, available_count: 1, partial_count: 0, unavailable_count: 0, unknown_count: 0 });
  if (target.includes('/api/orders/completed')) return json({ orders: [], total: 0 });
  if (target.includes('/api/allocations/exceptions')) return json({
    lines: [mockAllocationException],
    total_orders: 1,
    total_lines: 1,
    total_quantity_unallocated: 3,
    lines_with_available_stock: 0,
    lines_out_of_stock: 1,
  });
  if (target.includes('/api/allocations/auto/commit')) return json({
    status: 'completed',
    attempted_orders: 1,
    allocated_orders: 0,
    partially_allocated_orders: 1,
    exception_orders: 1,
    total_quantity_allocated: 0,
    allocation_ids: [],
    errors: [],
  });
  if (target.includes('/api/allocations')) return json({ allocations: [] });
  if (target.includes('/api/picks/preview')) return json({
    total_orders: 1,
    total_lines: 1,
    pickable_lines: 1,
    partial_lines: 0,
    skipped_lines: 0,
    total_quantity_to_pick: 2,
    preview_orders: [{
      order_id: 701,
      woo_order_number: '0802',
      lines: [{
        order_id: 701,
        order_line_id: 9001,
        sku: 'SMOKE-001',
        description: 'Smoke Test Item',
        warehouse: 'Main Warehouse',
        inventory_location: 'Smoke Rack',
        quantity_ordered: 2,
        quantity_allocated: 2,
        quantity_previously_picked: 0,
        remaining_to_pick: 2,
        recommended_pick_quantity: 2,
      }],
    }],
  });
  if (target.includes('/api/picks/commit')) return json({ status: 'posted', pick_id: 44, pick_number: 'PICK-0044', total_quantity_picked: 1 });
  if (target.includes('/api/picks')) return json({ picks: [] });
  if (target.includes('/api/fulfillments')) return json({ fulfillments: [] });
  if (target.includes('/api/routes/candidates')) return json({ total_candidates: 0, candidates: [] });
  if (target.includes('/api/routes')) return json({ routes: [], total: 0 });
  if (target.includes('/api/integrations/woocommerce/status')) return json({
    configured: true,
    message: 'WooCommerce sync is configured.',
    base_url_present: true,
    consumer_key_present: true,
    consumer_secret_present: true,
    base_url_host: 'staging32.pongo.ca',
    environment: 'staging',
    read_only: false,
    writeback_enabled: true,
    dry_run: false,
    staging_live_test_mode: true,
    stock_write_allowed: true,
    order_status_write_allowed: true,
    product_metadata_write_allowed: false,
    customer_write_allowed: false,
    coupon_write_allowed: false,
    refund_write_allowed: false,
    delete_allowed: false,
    allowed_host: 'staging32.pongo.ca',
    host_allowed: true,
    webhook_enabled: true,
    webhook_configured: true,
    webhook_secret_present: true,
    last_webhook_delivery: { id: 41, topic: 'order.created', status: 'processed', woo_order_id: 1601, created_order: true, received_at: '2026-07-10T17:00:00Z' },
    last_product_sync: { status: 'completed', total_remote_records: 12 },
    last_order_sync: { status: 'completed', total_remote_records: 8 },
    last_error: null,
  });
  if (target.includes('/api/integrations/woocommerce/sync-runs')) return json({ sync_runs: [] });
  if (target.includes('/api/integrations/woocommerce/writeback/queue')) return json({
    total: 1,
    queue: [{
      id: 7,
      operation_type: 'update_product_stock',
      entity_type: 'inventory_item',
      entity_id: 1,
      woo_entity_id: 101,
      payload_json: { method: 'PATCH', path: '/wp-json/wc/v3/products/101', body: { stock_quantity: 9 } },
      status: 'approved',
      environment: 'staging',
      dry_run: false,
      preview_json: { sku: 'SMOKE-001', woo_stock_snapshot: 4, proposed_woo_stock: 9 },
      response_json: null,
      error_message: null,
      created_at: '2026-07-09T12:00:00Z',
      approved_at: null,
      sent_at: null,
    }],
  });
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

function webhookEventPollCalls() {
  return fetch.mock.calls.filter(([url]) => String(url).includes('/api/integrations/woocommerce/webhooks/events'));
}

function quickSyncCalls() {
  return fetch.mock.calls.filter(([url]) => String(url).includes('/api/integrations/woocommerce/orders/quick-sync'));
}

async function settleInitialOrderPolling() {
  await waitFor(() => {
    expect(webhookEventPollCalls().some(([url]) => String(url).includes('initialize=true'))).toBe(true);
    expect(quickSyncCalls().length).toBeGreaterThan(0);
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

async function focusWindow() {
  await act(async () => {
    window.dispatchEvent(new Event('focus'));
    await Promise.resolve();
  });
}

describe('App shell and workflows', () => {
  beforeEach(() => {
    window.location.hash = '';
    mockWebhookFeed = { events: [], latest_event_id: 0, next_after_id: 0, has_more: false };
    mockQuickSyncResult = emptyQuickSyncResult();
    vi.stubGlobal('fetch', vi.fn(mockFetch));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.location.hash = '';
  });

  it('renders the new business Dashboard as the default landing page', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Dashboard', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('Live business snapshot for orders, customers, revenue, subscriptions, and delivery geography.')).toBeInTheDocument();
    expect(screen.getByText("Today's Orders")).toBeInTheDocument();
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
    ['#inventory', 'All Inventory'],
    ['#reports', 'Reports'],
    ['#scanner', 'Scanner'],
    ['#cycle-count', 'Cycle Count'],
  ])('renders the %s page', async (hash, heading) => {
    window.location.hash = hash;
    render(<App />);

    expect(await screen.findByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
  });

  it('styles inventory overview quick actions as action rows, not default links', async () => {
    window.location.hash = '#inventory-overview';
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
    expect(within(nav).getByRole('link', { name: 'Allocate' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Pick Orders' })).toBeInTheDocument();
    expect(within(nav).queryByRole('link', { name: 'Fulfillment' })).not.toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Completed Orders' })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: 'Order History' })).toBeInTheDocument();
  });

  it('shows Dashboard and Inventory Overview in the sidebar', async () => {
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('link', { name: /^Dashboard$/i })).toBeInTheDocument();
    expect(within(nav).getByRole('link', { name: /Inventory Overview/i })).toBeInTheDocument();
  });

  it('opens the renamed Inventory Overview command center', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(within(screen.getByRole('navigation', { name: 'Main navigation' })).getByRole('link', { name: /Inventory Overview/i }));

    expect(await screen.findByRole('heading', { name: 'Inventory Overview', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Inventory Health' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Command Center' })).not.toBeInTheDocument();
  });

  it('renders business Dashboard sections', async () => {
    render(<App />);

    expect(await screen.findByText("Today's Orders")).toBeInTheDocument();
    expect(screen.getByText("Today's Revenue")).toBeInTheDocument();
    expect(screen.getByText('New Customers')).toBeInTheDocument();
    expect(screen.getByText('Returning Customers')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Open Orders' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Upcoming Subscriptions' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: "Today's Orders Map" })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Revenue per day/i })).toBeInTheDocument();
    expect(screen.getByText('Subscription data is not synced yet.')).toBeInTheDocument();
  });

  it('has a refresh button for the business Dashboard', async () => {
    const user = userEvent.setup();
    render(<App />);

    await screen.findByRole('heading', { name: 'Dashboard', level: 1 });
    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: /Refresh/i }));

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/business-dashboard'))).toBe(true);
    });
  });

  it('seeds the webhook cursor without announcing historical orders', async () => {
    mockWebhookFeed = { events: [mockWebhookEvent], latest_event_id: 41, next_after_id: 41, has_more: false };
    render(<App />);

    await settleInitialOrderPolling();

    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveAttribute('aria-live', 'polite');
    expect(liveRegion).toHaveAttribute('aria-atomic', 'true');
    expect(screen.queryByLabelText('New order notification')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Order notifications, no unread orders' })).toBeInTheDocument();
  });

  it('announces a subsequent webhook order and exposes persistent view and history actions', async () => {
    const user = userEvent.setup();
    render(<App />);
    await settleInitialOrderPolling();
    mockWebhookFeed = { events: [mockWebhookEvent], latest_event_id: 41, next_after_id: 41, has_more: false };

    await focusWindow();

    const toast = await screen.findByLabelText('New order notification');
    expect(within(toast).getByText('New WooCommerce order #1601 imported')).toBeInTheDocument();
    expect(within(toast).getByText(/Morgan Lee/)).toBeInTheDocument();
    expect(webhookEventPollCalls().some(([url]) => String(url).includes('after_id=0'))).toBe(true);
    const bell = screen.getByRole('button', { name: 'Order notifications, 1 unread' });
    await user.click(bell);
    const history = screen.getByLabelText('Order notification history');
    expect(within(history).getByText('WooCommerce order #1601')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Order notifications, no unread orders' })).toHaveAttribute('aria-expanded', 'true');
    await user.click(within(history).getByRole('button', { name: 'Close order notification history' }));
    await user.click(within(toast).getByRole('link', { name: 'View Open Orders' }));

    expect(window.location.hash).toBe('#/orders/open');
    expect(screen.queryByLabelText('New order notification')).not.toBeInTheDocument();
  });

  it('does not replay a dismissed webhook notification with the same event id', async () => {
    const user = userEvent.setup();
    render(<App />);
    await settleInitialOrderPolling();
    mockWebhookFeed = { events: [mockWebhookEvent], latest_event_id: 41, next_after_id: 41, has_more: false };
    await focusWindow();
    const toast = await screen.findByLabelText('New order notification');
    await user.click(within(toast).getByRole('button', { name: 'Dismiss new order notification' }));
    const callsBeforeReplay = webhookEventPollCalls().length;

    await focusWindow();
    await waitFor(() => expect(webhookEventPollCalls().length).toBeGreaterThan(callsBeforeReplay));

    expect(screen.queryByLabelText('New order notification')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Order notifications, no unread orders' })).toBeInTheDocument();
  });

  it('advances by the page cursor and promptly drains additional webhook event pages', async () => {
    const secondEvent = { ...mockWebhookEvent, id: 42, woo_order_id: 1602, local_order_id: 703, woo_order_number: '1602', customer_name: 'Taylor Park' };
    mockWebhookFeed = (target) => {
      if (target.includes('initialize=true')) return { events: [], latest_event_id: 10, next_after_id: 10, has_more: false };
      if (target.includes('after_id=10')) return { events: [mockWebhookEvent], latest_event_id: 42, next_after_id: 41, has_more: true };
      return { events: [secondEvent], latest_event_id: 42, next_after_id: 42, has_more: false };
    };
    render(<App />);
    await settleInitialOrderPolling();

    await focusWindow();

    const toast = await screen.findByLabelText('New order notification');
    expect(await within(toast).findByText('2 new WooCommerce orders imported')).toBeInTheDocument();
    expect(webhookEventPollCalls().some(([url]) => String(url).includes('after_id=41'))).toBe(true);
    expect(screen.getByRole('button', { name: 'Order notifications, 2 unread' })).toBeInTheDocument();
  });

  it('uses quick-sync creation counts as a deduplicated fallback notification', async () => {
    const user = userEvent.setup();
    render(<App />);
    await settleInitialOrderPolling();
    mockQuickSyncResult = emptyQuickSyncResult({ sync_run_id: 92, total_remote_records: 2, created_count: 2, auto_allocated_count: 2 });

    await focusWindow();

    const toast = await screen.findByLabelText('New order notification');
    expect(within(toast).getByText('2 new WooCommerce orders imported')).toBeInTheDocument();
    await user.click(within(toast).getByRole('button', { name: 'Dismiss new order notification' }));
    const callsBeforeReplay = quickSyncCalls().length;
    await focusWindow();
    await waitFor(() => expect(quickSyncCalls().length).toBeGreaterThan(callsBeforeReplay));
    expect(screen.queryByLabelText('New order notification')).not.toBeInTheDocument();
  });

  it('shows Insights in the sidebar and opens Pongo Insights', async () => {
    const user = userEvent.setup();
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('link', { name: /Insights/i })).toBeInTheDocument();

    await user.click(within(nav).getByRole('link', { name: /Insights/i }));

    expect(await screen.findByRole('heading', { name: 'Pongo Insights', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('Business intelligence, customer behavior, revenue, product demand, and forecasting.')).toBeInTheDocument();
  });

  it('renders Insights tab navigation and Executive Overview by default', async () => {
    window.location.hash = '#insights';
    render(<App />);

    expect(await screen.findByRole('tab', { name: 'Executive Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Orders & Revenue' })).toBeInTheDocument();
    expect(await screen.findByText('Refund detail is not synced yet.')).toBeInTheDocument();
  });

  it('loads selected Insights tabs on demand without rendering every dashboard table', async () => {
    const user = userEvent.setup();
    window.location.hash = '#insights';
    render(<App />);

    await screen.findByRole('tab', { name: 'Executive Overview' });
    expect(screen.queryByText('DOG-FOOD')).toBeInTheDocument();
    expect(screen.queryByText('Avery Stone')).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Orders & Revenue' }));
    expect(await screen.findByRole('heading', { name: 'Orders & Revenue' })).toBeInTheDocument();
    expect((await screen.findAllByText('2026-06-20')).length).toBeGreaterThan(0);
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/insights/orders-revenue'))).toBe(true);
  });

  it('renders Customer Metrics and Product & SKU Insights tabs', async () => {
    const user = userEvent.setup();
    window.location.hash = '#insights';
    render(<App />);

    await user.click(await screen.findByRole('tab', { name: 'Customer Metrics' }));
    expect(await screen.findByText('Avery Stone')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Product & SKU Metrics' }));
    expect(await screen.findByText('DOG-FOOD')).toBeInTheDocument();
  });

  it('shows subscription empty state and keeps export buttons real only', async () => {
    const user = userEvent.setup();
    window.location.hash = '#insights';
    render(<App />);

    await user.click(await screen.findByRole('tab', { name: 'Subscriptions' }));

    expect((await screen.findAllByText('No subscription data synced yet')).length).toBeGreaterThan(0);
    expect(screen.queryByRole('link', { name: /Export CSV/i })).not.toBeInTheDocument();
  });

  it('has a refresh button for Insights and reloads the selected dashboard', async () => {
    const user = userEvent.setup();
    window.location.hash = '#insights';
    render(<App />);

    await screen.findByRole('tab', { name: 'Executive Overview' });
    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: /Refresh/i }));

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/insights/overview'))).toBe(true);
    });
  });

  it('shows staging WooCommerce Settings without exposing secrets', async () => {
    window.location.hash = '#settings';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'WooCommerce Catalog Mapping & Import' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview Catalog Mapping/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Import & Map Catalog/i })).toBeInTheDocument();
    expect(screen.getAllByText('staging').length).toBeGreaterThan(0);
    expect(screen.getAllByText('staging32.pongo.ca').length).toBeGreaterThan(0);
    expect(screen.getByText(/Credentials stay in backend environment variables/i)).toBeInTheDocument();
    expect(screen.getByText('Webhook Receiver')).toBeInTheDocument();
    expect(screen.getByText('Webhook Secret')).toBeInTheDocument();
    expect(screen.getByText(/Last webhook delivery processed/i)).toBeInTheDocument();
    expect(screen.getByText(/may safely auto-allocate active local orders/i)).toBeInTheDocument();
    expect(screen.queryByText(/ck_test/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cs_test/i)).not.toBeInTheDocument();
  });

  it('renders dry-run staging writeback controls in Settings', async () => {
    window.location.hash = '#settings';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Staging Writeback Testing' })).toBeInTheDocument();
    expect(screen.getByText('Live Staging Writes On')).toBeInTheDocument();
    expect(screen.getByText(/Live staging write testing is enabled/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview Stock Writeback/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview Order Status Writeback/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Send to Staging/i })).toBeInTheDocument();
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

  it('filters open orders when Enter is pressed in the order number field', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    const searchInput = screen.getByRole('textbox', { name: 'Order Number' });

    await user.type(searchInput, '9999');
    expect(searchInput).toHaveValue('9999');

    await user.keyboard('{Enter}');
    expect(screen.getByText('No open customer orders match the current filters.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(await screen.findByText('0802')).toBeInTheDocument();
  });

  it('shows the Zenventory-style Open Orders columns, row actions, and detail dialog', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    const orderTable = screen.getByText('0802').closest('table');
    expect(within(orderTable).getByRole('columnheader', { name: 'Order actions' })).toBeInTheDocument();
    expect(within(orderTable).getByRole('columnheader', { name: 'Order Number' })).toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Order Source' })).not.toBeInTheDocument();
    expect(within(orderTable).getByRole('columnheader', { name: 'Placed On' })).toBeInTheDocument();
    expect(within(orderTable).getByRole('columnheader', { name: 'Customer' })).toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Company' })).not.toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'State' })).not.toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Zip' })).not.toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Ship From' })).not.toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Shipped' })).not.toBeInTheDocument();
    expect(within(orderTable).queryByRole('columnheader', { name: 'Woo Status' })).not.toBeInTheDocument();
    expect(orderTable.parentElement).not.toHaveClass('zen-orders-table-scroll');

    await user.click(within(orderTable).getByRole('button', { name: 'Open actions for order 0802' }));
    expect(screen.getByRole('menu').parentElement).toBe(document.body);
    expect(screen.getByRole('menuitem', { name: 'View order' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Edit order' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Print order' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Complete order' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Unpick' })).toBeDisabled();
    expect(screen.getByRole('menuitem', { name: 'View timeline' })).toBeInTheDocument();

    fetch.mockClear();
    await user.click(screen.getByRole('menuitem', { name: 'View order' }));
    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/api/orders/701'))).toBe(true);
    });
    expect(await screen.findByRole('dialog', { name: 'View Customer Order' })).toBeInTheDocument();
    expect(screen.getByText('Ship/Bill To')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close' }));

    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});
    await user.click(within(orderTable).getByRole('button', { name: 'Open actions for order 0802' }));
    await user.click(screen.getByRole('menuitem', { name: 'Print order' }));
    await waitFor(() => expect(printSpy).toHaveBeenCalled());
    printSpy.mockRestore();
  });

  it.each([
    ['Allocate', '#/orders/allocate', 'Available stock is reserved automatically'],
    ['Pick Orders', '#/orders/pick', '1 order(s) ready to pick'],
    ['Completed Orders', '#/orders/completed', 'No completed orders match'],
    ['Order History', '#/orders/history', 'Allocation History'],
  ])('shows the %s Orders subpage', async (heading, hash, expectedText) => {
    window.location.hash = hash;
    render(<App />);

    expect(await screen.findByRole('heading', { name: heading, level: 1 })).toBeInTheDocument();
    expect(await screen.findByText(expectedText, { exact: false })).toBeInTheDocument();
  });

  it('switches to Pick Orders immediately from the Orders sidebar', async () => {
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const pickOrdersLink = within(nav).getByRole('link', { name: 'Pick Orders' });
    fetch.mockClear();

    act(() => pickOrdersLink.click());

    expect(window.location.hash).toBe('#/orders/pick');
    expect(screen.getByRole('heading', { name: 'Pick Orders', level: 1 })).toBeInTheDocument();
    expect(pickOrdersLink).toHaveClass('active');
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/orders/pick'))).toBe(true));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/orders/open'))).toBe(false);
  });

  it('shows allocation shortages by item and opens the stock correction workflow', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/allocate';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Allocate', level: 1 })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Allocate Orders', level: 2 })).toBeInTheDocument();
    expect(screen.getByText('1 order(s) could not be fully auto-allocated')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Items/ })).toHaveAttribute('aria-selected', 'true');

    const itemTable = screen.getByText('SMOKE-001').closest('table');
    expect(within(itemTable).getByRole('columnheader', { name: 'Ordered' })).toBeInTheDocument();
    expect(within(itemTable).getByRole('columnheader', { name: 'Allocated' })).toBeInTheDocument();
    expect(within(itemTable).getByRole('columnheader', { name: 'Unallocated' })).toBeInTheDocument();
    expect(within(itemTable).getByRole('columnheader', { name: 'Picked' })).toBeInTheDocument();
    expect(within(itemTable).getByRole('columnheader', { name: 'Available' })).toBeInTheDocument();

    await user.click(within(itemTable).getByRole('button', { name: 'Open allocation actions for SMOKE-001' }));
    expect(screen.getByRole('menuitem', { name: 'View affected orders' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Update stock levels' })).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Update stock levels' }));
    expect(await screen.findByRole('dialog', { name: 'Update stock levels' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Update and Auto-Allocate' })).toBeInTheDocument();
  });

  it('navigates between Orders subpages from the sidebar', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    await user.click(within(nav).getByRole('link', { name: 'Pick Orders' }));

    expect(await screen.findByRole('heading', { name: 'Pick Orders', level: 1 })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Pick Scanner' })).not.toBeInTheDocument();
    expect(await screen.findByText('0802')).toBeInTheDocument();
    const pickTable = screen.getByText('0802').closest('table');
    expect(within(pickTable).queryByRole('columnheader', { name: 'Order source' })).not.toBeInTheDocument();
    expect(within(pickTable).queryByRole('columnheader', { name: 'State' })).not.toBeInTheDocument();
    expect(within(pickTable).queryByRole('columnheader', { name: 'SKU' })).not.toBeInTheDocument();
    expect(within(pickTable).queryByRole('columnheader', { name: 'Allocated' })).not.toBeInTheDocument();
    expect(screen.queryByText('Fully allocated WooCommerce orders for picking and audited unpick corrections.')).not.toBeInTheDocument();
    expect(screen.queryByText('Active fully allocated orders stay here for pick management.', { exact: false })).not.toBeInTheDocument();
    expect(document.querySelector('.pick-list-panel.wide-panel')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Open order 0802 for picking' }));

    expect(screen.queryByRole('heading', { name: 'Pick Scanner' })).not.toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Order 0802' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Location' })).toBeInTheDocument();
    expect(screen.getByRole('spinbutton', { name: 'Picked quantity for Smoke Test Item' })).toHaveValue(0);
    expect(screen.getByRole('button', { name: 'Confirm Pick' })).toBeDisabled();

    await user.clear(screen.getByRole('spinbutton', { name: 'Picked quantity for Smoke Test Item' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Picked quantity for Smoke Test Item' }), '1');
    expect(screen.getByRole('button', { name: 'Confirm Pick' })).toBeEnabled();

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    await user.click(screen.getByRole('button', { name: 'Confirm Pick' }));
    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/picks/commit'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({
        order_ids: [],
        lines: [{ order_line_id: 9001, quantity_to_pick: 1 }],
        allow_partial: true,
      });
    });
    confirmSpy.mockRestore();
  });

  it('selects Pick Orders and exposes Pick Selected and Unpick Selected bulk actions', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    window.location.hash = '#/orders/pick';
    render(<App />);

    await user.click(await screen.findByRole('checkbox', { name: 'Select order 0802' }));
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menuitem', { name: 'Pick Selected' })).toBeEnabled();
    expect(screen.getByRole('menuitem', { name: 'Unpick Selected' })).toBeDisabled();

    await user.click(screen.getByRole('menuitem', { name: 'Pick Selected' }));
    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/picks/commit'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ order_ids: [701], allow_partial: false });
    });
    confirmSpy.mockRestore();
  });

  it('selects Open Orders and exposes complete, print, and unpick-all bulk actions', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    window.location.hash = '#/orders/open';
    render(<App />);

    await user.click(await screen.findByRole('checkbox', { name: 'Select order 0802' }));
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menuitem', { name: 'Mark as completed' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Print' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Unpick all' })).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Mark as completed' }));
    await waitFor(() => {
      const bulkCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/orders/bulk/complete'));
      expect(JSON.parse(bulkCall[1].body)).toMatchObject({ order_ids: [701] });
    });
    confirmSpy.mockRestore();
  });

  it('warns before the single Complete order action closes an unpicked order', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    window.location.hash = '#/orders/open';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Open Orders', level: 1 })).toBeInTheDocument();
    await user.click(await screen.findByRole('button', { name: 'Open actions for order 0802' }));
    await user.click(screen.getByRole('menuitem', { name: 'Complete order' }));

    expect(confirmSpy).toHaveBeenCalledWith(expect.stringContaining('has not been fully picked'));
    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/orders/701/complete/commit'))).toBe(true);
    });
    const completionCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/orders/701/complete/commit'));
    expect(JSON.parse(completionCall[1].body)).toMatchObject({ completion_mode: 'complete', queue_woo_status_update: true });
    expect(await screen.findByText('Order completed without picking. Stock was not reduced.')).toBeInTheDocument();
  });
});
