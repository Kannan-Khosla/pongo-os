import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import App, {
  browserNavigation,
  formatCurrency,
  formatDateTime,
  formatInsightValue,
  formatNumber,
  formatPercent,
  resetMutationIdempotency,
  withMutationIdempotency,
} from './App.jsx';
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

describe('shared display formatters', () => {
  it('distinguishes positive, negative, zero, and missing values', () => {
    expect(formatCurrency(79047.64)).toBe('$79,047.64');
    expect(formatCurrency(-12.5)).toBe('-$12.50');
    expect(formatCurrency(0)).toBe('$0.00');
    expect(formatCurrency(null)).toBe('—');
    expect(formatNumber(1294)).toBe('1,294');
    expect(formatNumber(null)).toBe('—');
    expect(formatPercent(-12.5)).toBe('-12.5%');
    expect(formatDateTime(null)).toBe('—');
    expect(formatInsightValue('valued_sku_count', 1)).toBe('1');
    expect(formatInsightValue('missing_cost_count', 0)).toBe('0');
    expect(formatInsightValue('total_inventory_value', 40)).toBe('$40.00');
  });
});

describe('stock mutation idempotency', () => {
  it('reuses a key for an identical retry and replaces it for changed or completed work', () => {
    const ref = { current: null };
    const first = withMutationIdempotency(ref, 'receipt', { quantity: 2 });
    const retry = withMutationIdempotency(ref, 'receipt', { quantity: 2 });
    const changed = withMutationIdempotency(ref, 'receipt', { quantity: 3 });

    expect(retry.idempotency_key).toBe(first.idempotency_key);
    expect(changed.idempotency_key).not.toBe(first.idempotency_key);

    resetMutationIdempotency(ref);
    const nextAction = withMutationIdempotency(ref, 'receipt', { quantity: 3 });
    expect(nextAction.idempotency_key).not.toBe(changed.idempotency_key);
  });
});

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
  customer_id: 501,
  billing_summary: { first_name: 'Avery', last_name: 'Stone', company: 'Pongo Test Co.', address_1: '100 Billing Ave', city: 'Edmonton', state: 'AB', postcode: 'T5J 0N3', country: 'CA', email: 'avery@example.invalid', phone: '555-0100' },
  shipping_summary: { first_name: 'Avery', last_name: 'Stone', address_1: '200 Delivery Way', city: 'Edmonton', state: 'AB', postcode: 'T5J 0N3', country: 'CA' },
  payment_method: 'cod',
  payment_method_title: 'Cash on delivery',
  subtotal: 58,
  discount_total: 3,
  shipping_total: 2,
  tax_total: 3,
  customer_note: 'Leave at the receiving desk.',
  workflow_notes: 'Woo reconciliation: Line 18058 quantity changed from 0 to 1.',
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
    unit_price: 29,
    line_tax: 3,
    line_total: 58,
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
  event_type: 'order_created',
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

let mockWebhookFeed;
let mockWooHealth;
let mockWooLastError;
let mockWooEnvironment;
let mockItemsFeed;
let mockItemFacets;
let mockOpenOrdersFeed;
let mockPickOrdersFeed;
let mockAllocationExceptionsFeed;
let mockInsightOverview;

function pagedItemsFeed(rows) {
  return (target) => {
    const url = new URL(target);
    const search = (url.searchParams.get('search') || '').toLowerCase();
    const filtered = search ? rows.filter((row) => [row.SKU, row.Barcode, row.Description].some((value) => String(value || '').toLowerCase().includes(search))) : rows;
    const page = Math.max(1, Number(url.searchParams.get('page') || 1));
    const pageSize = Math.max(1, Number(url.searchParams.get('page_size') || 20));
    const start = (page - 1) * pageSize;
    const items = filtered.slice(start, start + pageSize);
    return { items, page, page_size: pageSize, total: filtered.length, total_pages: Math.max(1, Math.ceil(filtered.length / pageSize)), returned_count: items.length };
  };
}

function pagedOrdersFeed(rows) {
  return (target) => {
    const url = new URL(target);
    const includes = (value, query) => !query || String(value || '').toLowerCase().includes(query.toLowerCase());
    const filtered = rows.filter((order) => {
      const itemText = [...(order.skus || []), ...(order.item_names || [])].join(' ');
      const searchText = [order.woo_order_number, order.woo_order_id, order.customer_name, itemText].join(' ');
      return includes(searchText, url.searchParams.get('search'))
        && includes(order.woo_order_number || order.woo_order_id, url.searchParams.get('order_number'))
        && includes(order.customer_name, url.searchParams.get('customer'))
        && includes(itemText, url.searchParams.get('containing_item'))
        && includes(order.ship_from || 'Main Warehouse', url.searchParams.get('warehouse'));
    });
    const page = Math.max(1, Number(url.searchParams.get('page') || 1));
    const pageSize = Math.max(1, Number(url.searchParams.get('page_size') || 20));
    const start = (page - 1) * pageSize;
    const orders = filtered.slice(start, start + pageSize);
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    return {
      orders,
      total: filtered.length,
      available_count: filtered.filter((order) => order.availability_status === 'available').length,
      partial_count: filtered.filter((order) => order.availability_status === 'partial').length,
      unavailable_count: filtered.filter((order) => order.availability_status === 'unavailable').length,
      unknown_count: filtered.filter((order) => order.availability_status === 'unknown').length,
      page,
      page_size: pageSize,
      total_pages: totalPages,
      returned_count: orders.length,
      has_previous: page > 1,
      has_next: page < totalPages,
    };
  };
}

function pagedAllocationExceptionsFeed(rows) {
  return (target) => {
    const url = new URL(target);
    const view = url.searchParams.get('view') === 'orders' ? 'orders' : 'items';
    const search = (url.searchParams.get('search') || '').toLowerCase();
    const warehouse = url.searchParams.get('warehouse') || '';
    const filteredBySearch = rows.filter((line) => {
      const searchable = [line.woo_order_number, line.woo_order_id, line.customer_name, line.sku, line.barcode, line.description].join(' ').toLowerCase();
      return (!search || searchable.includes(search)) && (!warehouse || line.warehouse === warehouse);
    });
    const selectedItemId = Number(url.searchParams.get('item_id') || 0);
    const selectedUnmatchedLineId = Number(url.searchParams.get('unmatched_line_id') || 0);
    const filtered = filteredBySearch.filter((line) => (
      (!selectedItemId || Number(line.item_id) === selectedItemId)
      && (!selectedUnmatchedLineId || (!line.item_id && Number(line.order_line_id) === selectedUnmatchedLineId))
    ));
    const pageSize = Math.max(1, Number(url.searchParams.get('page_size') || 20));
    const itemKey = (line) => line.item_id ? `item:${line.item_id}` : `unmatched:${line.sku || ''}:${line.barcode || ''}:${line.description || ''}`;
    const grouped = new Map();
    filtered.forEach((line) => {
      const key = itemKey(line);
      grouped.set(key, [...(grouped.get(key) || []), line]);
    });
    const itemGroups = [...grouped.values()];
    const groupSummary = (lines) => {
      const representative = lines[0];
      return {
        key: itemKey(representative),
        item_id: representative.item_id,
        unmatched_line_id: representative.item_id ? null : representative.order_line_id,
        representative_order_line_id: representative.order_line_id,
        sku: representative.sku,
        barcode: representative.barcode,
        description: representative.description,
        warehouse: representative.warehouse,
        inventory_location: representative.inventory_location,
        affected_order_count: new Set(lines.map((line) => line.order_id)).size,
        quantity_ordered: lines.reduce((sum, line) => sum + Number(line.quantity_ordered || 0), 0),
        quantity_allocated: lines.reduce((sum, line) => sum + Number(line.quantity_allocated || 0), 0),
        quantity_unallocated: lines.reduce((sum, line) => sum + Number(line.quantity_unallocated || 0), 0),
        quantity_picked: lines.reduce((sum, line) => sum + Number(line.quantity_picked || 0), 0),
        quantity_available: Math.max(...lines.map((line) => Number(line.quantity_available || 0))),
        exception_reason: representative.exception_reason,
      };
    };
    const totalResults = view === 'items' ? itemGroups.length : filtered.length;
    const totalPages = Math.max(1, Math.ceil(totalResults / pageSize));
    const page = Math.min(totalPages, Math.max(1, Number(url.searchParams.get('page') || 1)));
    const start = (page - 1) * pageSize;
    const pageGroups = view === 'items' ? itemGroups.slice(start, start + pageSize) : [];
    const pageLines = view === 'items' ? [] : filtered.slice(start, start + pageSize);
    return {
      lines: pageLines,
      item_groups: pageGroups.map(groupSummary),
      total_orders: new Set(filtered.map((line) => line.order_id)).size,
      total_lines: filtered.length,
      total_quantity_unallocated: filtered.reduce((sum, line) => sum + Number(line.quantity_unallocated || 0), 0),
      lines_with_available_stock: filtered.filter((line) => Number(line.quantity_available || 0) > 0).length,
      lines_out_of_stock: filtered.filter((line) => Number(line.quantity_available || 0) <= 0).length,
      view,
      total_item_groups: itemGroups.length,
      returned_item_groups: pageGroups.length,
      page,
      page_size: pageSize,
      total_pages: totalPages,
      returned_count: view === 'items' ? pageGroups.length : pageLines.length,
      has_previous: page > 1,
      has_next: page < totalPages,
      warehouses: [...new Set(filteredBySearch.map((line) => line.warehouse).filter(Boolean))].sort(),
    };
  };
}

function json(body) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
}

function csvResponse(text) {
  return Promise.resolve({ ok: true, blob: () => Promise.resolve(new Blob([text], { type: 'text/csv' })), text: () => Promise.resolve(text) });
}

const mockImportSchema = {
  schema_version: 'test.1',
  max_file_bytes: 10485760,
  outcomes: [
    { key: 'add_items', label: 'Add new items', description: 'Create products that do not yet exist.', changes: 'Creates item records and metadata.', does_not_change: 'Inventory quantities and movement history will not change.', required_fields: ['sku'], fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['add_items'] }, { key: 'product_name', label: 'Product name', type: 'text', required_for: [] }] },
    { key: 'update_items', label: 'Update item details', description: 'Update existing products by SKU.', changes: 'Updates approved metadata.', does_not_change: 'On hand, allocated, available, and movement history will not change.', required_fields: ['sku'], fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['update_items'] }, { key: 'product_name', label: 'Product name', type: 'text', required_for: [] }] },
    { key: 'update_stock', label: 'Override stock levels', description: 'Set exact stock by location.', changes: 'Creates one audited stock adjustment.', does_not_change: 'Allocated and sellable remain system-managed.', required_fields: ['sku', 'stock_quantity'], fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['update_stock'] }, { key: 'warehouse', label: 'Warehouse', type: 'text', required_for: [] }, { key: 'inventory_location', label: 'Inventory location', type: 'text', required_for: [] }, { key: 'stock_quantity', label: 'In stock', type: 'decimal', required_for: ['update_stock'] }] },
    { key: 'starting_inventory', label: 'Set starting inventory', description: 'Record physical stock at onboarding.', changes: 'Creates audited starting-inventory movements.', does_not_change: 'Existing operational inventory is never overwritten.', required_fields: ['sku', 'starting_quantity', 'starting_warehouse', 'starting_location'], fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['starting_inventory'] }, { key: 'starting_quantity', label: 'Starting quantity', type: 'decimal', required_for: ['starting_inventory'] }, { key: 'starting_warehouse', label: 'Warehouse', type: 'text', required_for: ['starting_inventory'] }, { key: 'starting_location', label: 'Inventory location', type: 'text', required_for: ['starting_inventory'] }] },
  ],
};

const mockDataQuality = { total_items: 1, complete_items: 0, items_needing_attention: 1, completion_percent: 0, issues: [{ key: 'missing_cost', label: 'Missing unit cost', description: 'Add the landed unit cost.', count: 1, severity: 'attention' }, { key: 'missing_image', label: 'Missing image', description: 'Add an image.', count: 1, severity: 'attention' }] };

function mockFetch(url, options = {}) {
  const target = String(url);
  if (target.includes('/api/reports/google-sheets/oauth/start')) {
    return json({
      authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?state=encrypted-state',
      redirect_uri: 'https://inventory.pongo.ca/api/reports/google-sheets/oauth/callback',
    });
  }
  if (target.includes('/api/reports/google-sheets/configuration')) {
    const saved = String(options.method || 'GET').toUpperCase() === 'POST';
    return json({
      configured: saved,
      client_id_present: saved,
      client_secret_present: saved,
      refresh_token_present: saved,
      folder_id: saved ? 'pongo-folder' : '',
      folder_configured: saved,
      configuration_source: saved ? 'pongo_database' : 'not_configured',
      configuration_updated_by: saved ? 'pytest@example.com' : null,
      configuration_updated_at: saved ? '2026-08-07T06:00:00Z' : null,
      oauth_redirect_uri: 'https://inventory.pongo.ca/api/reports/google-sheets/oauth/callback',
      message: saved ? 'Google Sheets is connected and saved securely in Pongo.' : undefined,
    });
  }
  if (target.includes('/api/integrations/woocommerce/webhooks/events')) return json(typeof mockWebhookFeed === 'function' ? mockWebhookFeed(target) : mockWebhookFeed);
  if (target.includes('/api/business-dashboard')) return json({
    generated_at: '2026-07-08T16:30:00Z',
    today: { summary: { today_orders_count: 2, today_revenue: 90, today_new_customers: 1, today_returning_customers: 1, today_subscription_orders: 0, average_order_value_today: 45 }, data_quality: [] },
    open_orders: { summary: { open_orders_count: 1 }, rows: [{ order_number: '0802', woo_order_id: 802, customer_name: 'Avery Stone', customer_email: 'avery@example.invalid', status: 'open', placed_on: '2026-07-08T10:00:00Z', order_total: 60, city: 'Edmonton' }], data_quality: [] },
    subscriptions: { summary: { subscription_data_available: false, upcoming_7_days_count: 0, upcoming_30_days_count: 0 }, rows: [], empty_state: 'Subscription data is not synced yet.', data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'Subscription data is not synced yet. This section will populate after subscription sync is connected.' }] },
    revenue_comparison: { summary: { current_period_label: 'July 1-8', previous_period_label: 'June 1-8', current_period_revenue: 90, previous_period_revenue: 120, delta_percent: -25 }, daily_series: [{ day_index: 1, current_revenue: 20, previous_revenue: 40 }, { day_index: 2, current_revenue: 70, previous_revenue: 80 }], data_quality: [] },
    order_map: { summary: { total_orders_today: 2, total_orders_plotted: 2, total_orders_unplotted: 0 }, city_breakdown: [{ city: 'Edmonton', order_count: 1, revenue: 60, customer_count: 1 }, { city: 'Sherwood Park', order_count: 1, revenue: 30, customer_count: 1 }], markers: [{ marker_label: '0802', latitude: 53.5461, longitude: -113.4938, approximate: true }, { marker_label: '0803', latitude: 53.5412, longitude: -113.2957, approximate: true }], data_quality: [{ code: 'approximate_coordinates', severity: 'info', message: 'Map uses city-level approximate markers until address geocoding is configured.' }] },
    data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'Subscription data is not synced yet. This section will populate after subscription sync is connected.' }],
  });
  if (target.includes('/api/insights/subscriptions')) return json({ dashboard: 'subscriptions', summary: { data_available: false, active_subscriptions: null, subscription_revenue: null, monthly_recurring_revenue: null }, rows: [], data_quality: [{ code: 'missing_subscription_data', severity: 'info', message: 'No WooCommerce Subscriptions snapshots are synced locally yet.' }], empty_state: 'No subscription data synced yet' });
  if (target.includes('/api/insights/customer-metrics')) return json({ dashboard: 'customer-metrics', summary: { total_customers: 2, returning_customers: 1 }, rows: [{ customer_name: 'Avery Stone', email: 'avery@example.invalid', order_count: 2, lifetime_spend: 90, last_order_date: '2026-06-20T12:00:00Z' }], data_quality: [] });
  if (target.includes('/api/insights/product-sku')) return json({ dashboard: 'product-sku', summary: { sku_count: 1, units_sold: 4, revenue: 90 }, rows: [{ sku: 'DOG-FOOD', description: 'Dog Food', brand: 'Acana', category: 'Dog Food', units_sold: 4, revenue: 90, estimated_margin: 50, current_sellable: 10 }], data_quality: [] });
  if (target.includes('/api/insights/orders-revenue')) return json({ dashboard: 'orders-revenue', summary: { total_orders: 2, average_order_value: 45, net_sales: 90 }, trends: { daily_revenue: [{ date: '2026-06-20', order_count: 2, gross_sales: 90, net_sales: 90, units_sold: 4 }] }, rows: [{ date: '2026-06-20', order_count: 2, gross_sales: 90, net_sales: 90, units_sold: 4 }], data_quality: [] });
  if (target.includes('/api/insights/overview')) return json(mockInsightOverview);
  if (target.includes('/api/insights/')) return json({ dashboard: 'generic', summary: { total: 0 }, rows: [], data_quality: [] });
  if (target.includes('/api/dashboard')) return json({ inventory_health: {}, order_operations: {}, routes: {}, warnings: [], activity: [] });
  if (target.includes('/api/items/import/schema')) return json(mockImportSchema);
  if (target.includes('/api/items/facets')) return json(typeof mockItemFacets === 'function' ? mockItemFacets(target) : mockItemFacets);
  if (target.includes('/api/items/data-quality')) return json(mockDataQuality);
  if (target.includes('/api/items/export')) return csvResponse('SKU,Unit cost\nSMOKE-001,\n');
  if (target.includes('/api/import-jobs')) return json([]);
  if (target.includes('/api/items/enrichment/export')) return csvResponse('Pongo Item ID,Woo Product ID,Woo Variation ID,Woo Mapping Type,Woo Mapping Status,SKU\n1,101,,simple,synced,SMOKE-001\n');
  if (target.includes('/api/items/enrichment/preview')) return json({ total_rows: 1, valid_rows: 1, invalid_rows: 0, create_count: 0, update_count: 1, unchanged_count: 0, conflict_count: 0, unmatched_count: 0, warnings: [], errors: [], preview_rows: [{ row_number: 2, action: 'update', sku: 'SMOKE-001', barcode: 'SMOKE001', match_method: 'pongo_item_id', fields_changing: ['Brand'], warnings: [], errors: [], raw_row: { SKU: 'SMOKE-001' } }] });
  if (target.match(/\/api\/items\/1$/)) return json({ item, stock_by_location: [], recent_activity: [] });
  if (target.includes('/api/items')) return json(typeof mockItemsFeed === 'function' ? mockItemsFeed(target) : mockItemsFeed);
  if (target.includes('/api/locations')) return json({ locations: [{ id: 1, warehouse: 'Main Warehouse', code: 'Smoke Rack', name: 'Smoke Rack', isActive: true }] });
  if (target.includes('/api/inventory/summary/by-location')) return json({ total_items: 1, total_in_stock: 9, total_sellable: 7, groups: [] });
  if (target.includes('/api/inventory/adjustments')) return json({ status: 'committed', adjustment_number: 'ADJ-0001' });
  if (target.includes('/api/inventory/locations')) return json({ rows: [] });
  if (target.includes('/api/cycle-counts')) return json({ cycle_counts: [] });
  if (target.includes('/api/receipts/direct/preview')) return json({ total_lines: 1, valid_lines: 1, invalid_lines: 0, total_quantity: 1, estimated_inventory_value: 4.25, errors: [], preview_lines: [{ line_number: 1, status: 'valid', sku: 'SMOKE-001', description: 'Smoke Test Item', inventory_location: 'Smoke Rack', quantity_received: 1, previous_in_stock: 9, new_in_stock: 10, line_value: 4.25 }] });
  if (target.includes('/api/receipts/direct/commit')) return json({ status: 'committed', id: 11, receipt_number: 'REC-0011' });
  if (target.includes('/api/receipts/bulk/preview')) return json({ can_commit: true, line_count: 1, valid_line_count: 1, error_line_count: 0, total_quantity: 1, total_cost: 4.25, lines: [{ line_number: 1, status: 'valid', item: { sku: 'SMOKE-001' }, inventory_location: 'Smoke Rack', quantity: 1, old_location_stock: 9, new_location_stock: 10, errors: [] }] });
  if (target.includes('/api/receipts/bulk/commit')) return json({ status: 'committed', id: 12, receipt_number: 'REC-0012' });
  if (target.includes('/api/receipts')) return json({ receipts: [] });
  if (target.includes('/api/stock-movements')) return json({ movements: [] });
  if (target.includes('/api/orders/701/complete/commit')) return json({ status: 'completed_without_picking', message: 'Order completed without picking. Stock was not reduced.', woo_sync_status: 'sent', woo_writeback_queue_id: 41 });
  if (target.includes('/api/orders/bulk/complete')) return json({ status: 'completed', requested_count: 1, succeeded_count: 1, failed_count: 0, results: [{ order_id: 701, status: 'completed', message: 'Completed.', woo_sync_status: 'sent', woo_writeback_queue_id: 41 }], errors: [] });
  if (target.includes('/api/orders/bulk/unpick')) return json({ status: 'completed', requested_count: 1, succeeded_count: 1, failed_count: 0, total_quantity_restored: 1, results: [], errors: [] });
  if (target.match(/\/api\/orders\/701$/)) return json(mockOrderDetail);
  if (target.includes('/api/orders/allocate')) return json({ orders: [], total: 0 });
  if (target.includes('/api/orders/pick')) return json(typeof mockPickOrdersFeed === 'function' ? mockPickOrdersFeed(target) : mockPickOrdersFeed);
  if (target.includes('/api/orders/open')) return json(typeof mockOpenOrdersFeed === 'function' ? mockOpenOrdersFeed(target) : mockOpenOrdersFeed);
  if (target.includes('/api/orders/completed')) return json({ orders: [], total: 0 });
  if (target.includes('/api/allocations/exceptions/export')) return csvResponse('Order Number,SKU\n0803,SMOKE-001\n');
  if (target.includes('/api/allocations/exceptions')) return json(typeof mockAllocationExceptionsFeed === 'function' ? mockAllocationExceptionsFeed(target) : mockAllocationExceptionsFeed);
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
  if (target.includes('/api/routes/open-orders/plan')) return json({
    start_address: '5855 99 Street NW, Edmonton, AB',
    requested_driver_count: 1,
    effective_driver_count: 1,
    total_open_orders: 2,
    routable_order_count: 2,
    excluded_order_count: 0,
    return_to_start: false,
    assignment_method: 'balanced_by_postal_area',
    warnings: [],
    excluded_orders: [],
    drivers: [{
      driver_number: 1,
      driver_label: 'Driver 1',
      stop_count: 2,
      stops: [
        { stop_sequence: 1, order_id: 701, woo_order_number: '0802', customer_name: 'Avery Stone', address: '200 Delivery Way, Edmonton, AB, T5J 0N3, CA', postal_area: 'T5J' },
        { stop_sequence: 2, order_id: 702, woo_order_number: '0803', customer_name: 'Morgan Lee', address: '300 Delivery Way, Edmonton, AB, T5K 1A1, CA', postal_area: 'T5K' },
      ],
      google_maps_links: [{ part_number: 1, label: 'Stops 1–2', url: 'https://www.google.com/maps/dir/?api=1&origin=5855+99+Street&destination=300+Delivery+Way', stop_sequence_from: 1, stop_sequence_to: 2, stop_count: 2, returns_to_start: false }],
    }],
  });
  if (target.includes('/api/routes/candidates')) return json({ total_candidates: 0, candidates: [] });
  if (target.includes('/api/routes')) return json({ routes: [], total: 0 });
  if (target.includes('/api/integrations/woocommerce/status')) return json({
    configured: true,
    message: 'WooCommerce sync is configured.',
    base_url_present: true,
    consumer_key_present: true,
    consumer_secret_present: true,
    base_url: 'https://staging32.pongo.ca',
    base_url_host: 'staging32.pongo.ca',
    environment: mockWooEnvironment,
    access_mode: 'read_write',
    access_mode_updated_by: 'Pytest',
    access_mode_updated_at: '2026-07-31T18:00:00Z',
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
    order_reconciliation: mockWooHealth,
    last_error: mockWooLastError,
  });
  if (target.includes('/api/integrations/woocommerce/access-mode')) return json({
    access_mode: 'read_only',
    changed_by: 'Pytest',
    changed_at: '2026-07-31T18:00:00Z',
    message: 'WooCommerce access changed to Read only.',
  });
  if (target.includes('/api/integrations/woocommerce/configuration')) return json({
    connected: true,
    base_url: 'https://staging32.pongo.ca',
    base_url_host: 'staging32.pongo.ca',
    consumer_key_present: true,
    consumer_secret_present: true,
    message: 'WooCommerce credentials were verified and saved in the backend environment.',
  });
  if (target.includes('/api/integrations/woocommerce/products/preview')) return json({
    configured: true,
    total_remote_records: 4,
    create_count: 3,
    update_count: 0,
    unchanged_count: 0,
    matched_count: 0,
    skipped_count: 1,
    conflict_count: 0,
    error_count: 0,
    simple_products_examined: 0,
    variable_parents_examined: 1,
    purchasable_variations_examined: 3,
    new_simple_count: 0,
    new_variation_count: 3,
    skipped_parent_count: 1,
    warnings: [],
    errors: [],
    has_more: false,
    preview_rows: [
      { remote_type: 'variable', product_name: 'Nutram Dog Food', parent_product_name: null, variation_attributes: [], sku: '', woo_product_id: 7000, woo_variation_id: null, action: 'skip', status: 'skipped', warnings: ['Variable parent container is informational and will not become a stock item.'], errors: [] },
      ...['2 kg', '5 kg', '11.4 kg'].map((size, index) => ({ remote_type: 'variation', product_name: `Nutram Dog Food - ${size}`, parent_product_name: 'Nutram Dog Food', variation_attributes: [{ name: 'Size', option: size }], sku: `NUTRAM-${index}`, woo_product_id: 7000, woo_variation_id: 7001 + index, proposed_item: { description: `Nutram Dog Food - ${size}` }, action: 'create', status: 'valid', warnings: [], errors: [] })),
    ],
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
  if (target.endsWith('/api/reports')) return json({
    reports: [{
      key: 'inventory-export',
      title: 'Inventory Export',
      description: 'Verified inventory export.',
      category: 'inventory',
      date_mode: 'snapshot',
      filters: ['warehouse', 'inventory_location', 'brand', 'category', 'sku'],
      formats: ['csv'],
    }],
  });
  if (target.includes('/api/reports/inventory-valuation/summary')) return json({ total_skus: 1, total_units: 9 });
  if (target.includes('/api/reports/inventory-valuation')) return json([{ sku: 'SMOKE-001', description: 'Smoke Test Item', in_stock: 9 }]);
  if (target.includes('/api/reports/low-stock/summary')) return json({ total_skus: 1, total_units: 9 });
  if (target.includes('/api/reports/low-stock')) return json([{ sku: 'SMOKE-001', description: 'Smoke Test Item', in_stock: 9 }]);
  if (target.includes('/api/reports/receiving-cost/summary')) return json({ total_receipts: 0, total_received_value: 0 });
  if (target.includes('/api/reports/receiving-cost')) return json([]);
  if (target.includes('/api/reports/received-inventory/summary')) return json({ total_receipts: 0, total_lines: 0, by_location: [] });
  if (target.includes('/api/reports/received-inventory')) return json([]);
  if (target.includes('/api/reports/fulfillments/summary')) return json({ total_fulfillments: 0, by_location: [], by_sku: [] });
  if (target.includes('/api/reports/fulfillments')) return json([]);
  if (target.includes('/api/reports/sku-orders/summary')) return json({ total_skus: 0 });
  if (target.includes('/api/reports/sku-orders')) return json([]);
  if (target.includes('/api/scanner/inventory/lookup')) return json({ matched: false, message: 'No item matched that scan.' });
  if (target.includes('/api/scanner/receiving/scan/commit')) return json({ matched: true, status: 'committed', message: 'Received.' });
  if (target.includes('/api/scanner/adjustments/commit')) return json({ matched: true, status: 'committed', message: 'Adjusted.' });
  return json({});
}

function webhookEventPollCalls() {
  return fetch.mock.calls.filter(([url]) => String(url).includes('/api/integrations/woocommerce/webhooks/events'));
}

function wooStatusCalls() {
  return fetch.mock.calls.filter(([url]) => String(url).includes('/api/integrations/woocommerce/status'));
}

async function settleInitialOrderPolling() {
  await waitFor(() => {
    expect(webhookEventPollCalls().some(([url]) => String(url).includes('initialize=true'))).toBe(true);
    expect(wooStatusCalls().length).toBeGreaterThan(0);
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
    mockWooHealth = {
      enabled: true,
      running: true,
      healthy: true,
      degraded: false,
      stale: false,
      interval_seconds: 60,
      stale_after_seconds: 300,
      statuses: ['processing', 'completed', 'failed', 'cancelled', 'refunded'],
      last_status: 'completed',
      error_count: 0,
      last_attempt_at: '2026-07-10T17:00:00Z',
      last_success_at: '2026-07-10T17:00:00Z',
      last_failure_at: null,
      last_error: null,
      message: 'Server order reconciliation is healthy.',
    };
    mockWooLastError = null;
    mockWooEnvironment = 'staging';
    mockItemsFeed = { items: [item], page: 1, page_size: 20, total: 1, total_pages: 1, returned_count: 1 };
    mockItemFacets = { categories: ['Test Category'], brands: ['Smoke Brand'] };
    mockOpenOrdersFeed = pagedOrdersFeed([mockOrder]);
    mockPickOrdersFeed = pagedOrdersFeed([mockOrder]);
    mockAllocationExceptionsFeed = pagedAllocationExceptionsFeed([mockAllocationException]);
    mockInsightOverview = {
      dashboard: 'overview',
      summary: { gross_sales: 100, discount_amount: 10, refund_amount: null, net_sales: 90, total_orders: 2, units_sold: 4, average_order_value: 45 },
      trends: { daily_revenue: [{ date: '2026-06-20', order_count: 2, net_sales: 90 }] },
      tables: { stockout_risk: [{ sku: 'DOG-FOOD', product_name: 'Dog Food', risk_level: 'low', current_sellable: 10, daily_velocity: 1, days_of_stock_left: 10 }] },
      data_quality: [{ code: 'missing_refund_data', severity: 'info', message: 'Refund detail is not synced yet.' }],
    };
    vi.stubGlobal('fetch', vi.fn(mockFetch));
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    window.location.hash = '';
    window.sessionStorage.clear();
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
    await screen.findByRole('heading', { name: 'Items', level: 1 });
    expect(document.querySelectorAll('.nav-link.active')).toHaveLength(1);
  });

  it('opens the report intelligence workspace from every default report entry point', async () => {
    const user = userEvent.setup();
    render(<App />);

    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    const reportsLink = within(nav).getByRole('link', { name: 'Reports' });
    expect(reportsLink).toHaveAttribute('href', '#/reports/inventory/inventory-export');
    await user.click(reportsLink);
    expect(await screen.findByRole('heading', { name: 'Inventory Export', level: 1 })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/reports/inventory/inventory-export');

    await user.click(within(nav).getByRole('link', { name: /Items/i }));
    await screen.findByRole('heading', { name: 'Items', level: 1 });
    window.location.hash = '#/reports/inventory/inventory-valuation';
    window.dispatchEvent(new HashChangeEvent('hashchange'));
    expect(await screen.findByRole('heading', { name: 'Inventory Export', level: 1 })).toBeInTheDocument();
  });

  it('exposes the production shell landmarks and closes mobile navigation with Escape', async () => {
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByRole('link', { name: 'Skip to workspace' })).toHaveAttribute('href', '#main-content');
    expect(screen.getByRole('main')).toHaveAttribute('id', 'main-content');
    expect(screen.getByRole('navigation', { name: 'Module navigation' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main navigation' })).toBeInTheDocument();
    const warehouseContexts = screen.getAllByLabelText('Current warehouse: Main Warehouse');
    expect(warehouseContexts).toHaveLength(1);
    expect(warehouseContexts[0].tagName).toBe('DIV');
    expect(document.querySelector('.warehouse-control')).not.toBeInTheDocument();

    const navigationToggle = screen.getByRole('button', { name: 'Open navigation' });
    await user.click(navigationToggle);
    expect(navigationToggle).toHaveAttribute('aria-expanded', 'true');
    expect(document.getElementById('application-navigation')).toHaveClass('is-open');
    expect(document.querySelector('.navigation-close')).toHaveFocus();

    await user.keyboard('{Escape}');
    await waitFor(() => expect(navigationToggle).toHaveFocus());
    expect(navigationToggle).toHaveAttribute('aria-expanded', 'false');
    expect(document.getElementById('application-navigation')).not.toHaveClass('is-open');
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
    const searchInput = screen.getByPlaceholderText('Search SKU, barcode, product title, or brand');

    await user.type(searchInput, 'SMOKE001');
    expect(searchInput).toHaveValue('SMOKE001');
    fetch.mockClear();

    await user.keyboard('{Enter}');

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/items') && String(url).includes('search=SMOKE001'))).toBe(true);
    });
  });

  it('searches Items from the mobile camera scanner manual fallback', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('button', { name: 'Scan QR code or barcode with camera' }));

    const scanner = screen.getByRole('dialog', { name: 'Scan an item code' });
    await user.type(within(scanner).getByLabelText('Enter barcode or SKU instead'), 'SMOKE001');
    await user.click(within(scanner).getByRole('button', { name: 'Search item' }));

    expect(screen.getByPlaceholderText('Search SKU, barcode, product title, or brand')).toHaveValue('SMOKE001');
    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => {
        const request = new URL(String(url));
        return request.pathname === '/api/items' && request.searchParams.get('search') === 'SMOKE001';
      })).toBe(true);
    });
  });

  it('aborts an obsolete item-list request when moving to Scanner', async () => {
    let itemRequestSignal;
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/items') {
        itemRequestSignal = options.signal;
        return new Promise((resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#items';
    render(<App />);

    await waitFor(() => expect(itemRequestSignal).toBeTruthy());
    act(() => { window.location.hash = '#scanner'; });
    await screen.findByRole('heading', { name: 'Scanner Console', level: 2 });
    expect(itemRequestSignal.aborted).toBe(true);
  });

  it('aborts superseded inventory summary and location-stock requests', async () => {
    const summarySignals = [];
    const locationSignals = [];
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/inventory/summary/by-location') {
        summarySignals.push(options.signal);
        if (summarySignals.length === 1) {
          return new Promise((resolve, reject) => {
            options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
          });
        }
      }
      if (request.pathname === '/api/inventory/locations') {
        locationSignals.push(options.signal);
        if (locationSignals.length === 1) {
          return new Promise((resolve, reject) => {
            options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
          });
        }
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    await waitFor(() => {
      expect(summarySignals).toHaveLength(1);
      expect(locationSignals).toHaveLength(1);
    });
    act(() => { window.location.hash = '#/inventory/all?page=1&page_size=20&category=Test%20Category'; });

    await waitFor(() => {
      expect(summarySignals.length).toBeGreaterThan(1);
      expect(locationSignals.length).toBeGreaterThan(1);
    });
    expect(summarySignals[0].aborted).toBe(true);
    expect(locationSignals[0].aborted).toBe(true);
  });

  it('shows live inventory suggestions and applies keyword searches while typing', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation((url) => {
      const target = String(url);
      if (target.includes('/api/items/search')) {
        const suggestions = [
          { id: 11, sku: '70001', barcode: '11170001', product_name: 'Duck Food Adult', brand: 'North Paw', category: 'Dog Food' },
          { id: 12, sku: '70002', barcode: '11170002', product_name: 'Duck Food Puppy', brand: 'South Paw', category: 'Dog Food' },
        ];
        return json({ items: suggestions, total: suggestions.length });
      }
      return mockFetch(url);
    });
    window.location.hash = '#/inventory/all';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    const searchInput = screen.getByRole('combobox', { name: 'Scan or search inventory' });
    await user.type(searchInput, 'duck');

    expect(await screen.findByRole('option', { name: /Duck Food Adult.*North Paw.*70001/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /Duck Food Puppy.*South Paw.*70002/i })).toBeInTheDocument();
    await waitFor(() => expect(window.location.hash).toContain('search=duck'));

    await user.clear(searchInput);
    await user.type(searchInput, '700');
    const skuSuggestion = await screen.findByRole('option', { name: /Duck Food Puppy.*70002/i });
    await user.click(skuSuggestion);

    await waitFor(() => expect(window.location.hash).toContain('search=70002'));
    expect(searchInput).toHaveValue('70002');
  });

  it('turns a data-quality filter into an export and re-import workflow', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    expect(screen.getByRole('link', { name: 'Add item' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Import items' })).toHaveAttribute('href', '#/items/import');
    expect(screen.getByRole('link', { name: 'Update stock CSV' })).toHaveAttribute('href', '#/items/import?outcome=update_stock');
    expect(screen.getByText('Export')).toBeInTheDocument();
    expect(screen.getByText('More')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Item data quality' })).toHaveTextContent('Missing image');

    await user.click(screen.getByRole('button', { name: /Missing unit cost/i }));
    const actions = await screen.findByRole('region', { name: 'Missing unit cost actions' });
    expect(within(actions).getByRole('button', { name: 'Export CSV' })).toBeInTheDocument();
    expect(within(actions).getByRole('link', { name: 'Import completed CSV' })).toHaveAttribute('href', '#/items/import?outcome=update_items');
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('data_quality=missing_cost'))).toBe(true));
  });

  it('opens the stock CSV override directly from the item catalog', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('link', { name: 'Update stock CSV' }));

    expect(await screen.findByRole('heading', { name: 'Upload your CSV' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Export editable current stock/i })).toHaveAttribute('href', expect.stringContaining('/templates/update_stock?include_existing=true'));
  });

  it('keeps sign out in the top-right account menu', async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();
    render(<App currentUser={{ display_name: 'Kannan', email: 'kannan@example.com' }} onLogout={onLogout} />);

    await user.click(screen.getByLabelText('Account: Kannan'));
    expect(screen.getByText('kannan@example.com')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign out' }));

    expect(onLogout).toHaveBeenCalledOnce();
    expect(document.querySelector('.auth-account')).not.toBeInTheDocument();
  });

  it('loads the item master once with server pagination', async () => {
    const rows = Array.from({ length: 120 }, (_, index) => ({
      ...item,
      id: index + 1,
      SKU: `ITEM-${String(index + 1).padStart(3, '0')}`,
      Description: `Item master row ${index + 1}`,
    }));
    mockItemsFeed = pagedItemsFeed(rows);
    window.location.hash = '#items';
    render(<App />);

    expect(await screen.findByText('ITEM-001')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–50 of 120 items')).toBeInTheDocument();
    const itemRequests = fetch.mock.calls.map(([url]) => new URL(String(url))).filter((url) => url.pathname === '/api/items');
    expect(itemRequests.length).toBeGreaterThan(0);
    expect(itemRequests.every((url) => url.searchParams.get('page') === '1' && url.searchParams.get('page_size') === '50')).toBe(true);
    expect(itemRequests.some((url) => !url.searchParams.has('page'))).toBe(false);
  });

  it('removes hidden item selections after a successful same-page Items refresh', async () => {
    const user = userEvent.setup();
    let rows = [item];
    mockItemsFeed = (target) => pagedItemsFeed(rows)(target);
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('checkbox', { name: 'Select SMOKE-001' }));
    expect(screen.getByRole('button', { name: 'Bulk edit 1' })).toBeInTheDocument();

    rows = [{ ...item, id: 2, SKU: 'REPLACED-002', Description: 'Replacement Item' }];
    await user.click(screen.getByText('More'));
    await user.click(screen.getByRole('button', { name: /Refresh items/i }));

    expect(await screen.findByText('Replacement Item')).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Bulk edit 1' })).not.toBeInTheDocument());
  });

  it('opens the dedicated item import workspace and persists a server preview', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation((url, init = {}) => {
      const target = String(url);
      if (target.includes('/api/items/import/schema')) return json(mockImportSchema);
      if (target.endsWith('/api/items/import/previews') && init.method === 'POST') return json({
        preview_id: 'preview-1', outcome: 'add_items', outcome_content: mockImportSchema.outcomes[0],
        file: { name: 'items.csv', size: 20, row_count: 1, header_count: 2 }, status: 'ready',
        source_columns: [{ source: 'SKU', destination: 'sku', confidence: 'exact', samples: ['A'] }, { source: 'Product name', destination: 'product_name', confidence: 'exact', samples: ['Food'] }],
        mapping: { SKU: 'sku', 'Product name': 'product_name' }, options: { allow_blank_clears: false },
        summary: { total_rows: 1, ready_count: 1, create_count: 1, update_count: 0, no_changes_count: 0 },
      });
      return mockFetch(url);
    });
    window.location.hash = '#/items/import';
    render(<App />);

    await screen.findByRole('heading', { name: 'What do you want this file to do?' });
    await user.click(screen.getByRole('button', { name: /Add new items/i }));
    await user.click(screen.getByRole('button', { name: /^Continue/i }));
    const input = document.querySelector('.import-dropzone input[type="file"]');
    await user.upload(input, new File(['SKU,Product name\nA,Food'], 'items.csv', { type: 'text/csv' }));
    await user.click(screen.getByRole('button', { name: /Upload and match columns/i }));
    expect(await screen.findByRole('heading', { name: 'Match your columns' })).toBeInTheDocument();
    expect(window.sessionStorage.getItem('pongo.item-import.preview')).toBe('preview-1');
  });

  it('invalidates a location import preview when the selected CSV changes', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation((url) => {
      if (String(url).includes('/api/locations/import/preview')) return json({ total_rows: 1, valid_rows: 1, invalid_rows: 0, create_count: 1, update_count: 0, warnings: [], errors: [], preview_rows: [] });
      return mockFetch(url);
    });
    window.location.hash = '#locations';
    render(<App />);

    await screen.findAllByText('Smoke Rack');
    await user.click(screen.getByRole('button', { name: 'Import' }));
    const dialog = screen.getByRole('dialog', { name: 'Import locations CSV' });
    const input = dialog.querySelector('input[type="file"]');
    await user.upload(input, new File(['Warehouse,Location Code,Location Name\nMain,A,A'], 'a.csv', { type: 'text/csv' }));
    await user.click(within(dialog).getByRole('button', { name: 'Preview CSV' }));
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Import Valid Rows' })).toBeEnabled());

    await user.upload(input, new File(['Warehouse,Location Code,Location Name\nMain,B,B'], 'b.csv', { type: 'text/csv' }));
    expect(within(dialog).getByRole('button', { name: 'Import Valid Rows' })).toBeDisabled();
  });

  it('invalidates a bulk-edit preview when any field changes', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation((url) => {
      if (String(url).includes('/api/items/bulk/preview')) return json({ can_commit: true, affected_count: 1, fields_to_update: ['brand'], warnings: [] });
      return mockFetch(url);
    });
    window.location.hash = '#items';
    render(<App />);

    const itemRow = (await screen.findByText('Smoke Test Item')).closest('tr');
    await user.click(within(itemRow).getByRole('checkbox'));
    await user.click(screen.getByRole('button', { name: 'Bulk edit 1' }));
    const dialog = screen.getByRole('dialog', { name: 'Bulk edit inventory items' });
    const brand = within(dialog).getByRole('textbox', { name: 'Brand' });
    await user.type(brand, 'Acana');
    await user.click(within(dialog).getByRole('button', { name: 'Preview changes' }));
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Apply to 1 item(s)' })).toBeEnabled());

    await user.type(brand, ' Updated');
    expect(within(dialog).getByRole('button', { name: 'Apply to 1 item(s)' })).toBeDisabled();
  });

  it('shows product titles without a long-description column', async () => {
    window.location.hash = '#items';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    expect(screen.getByRole('columnheader', { name: 'Product Title' })).toBeInTheDocument();
    expect(screen.queryByRole('columnheader', { name: 'Description' })).not.toBeInTheDocument();
  });

  it('uses server pagination for Inventory and resets the page when size or search changes', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 45 }, (_, index) => ({
      ...item,
      id: index + 1,
      SKU: `PAGE-${String(index + 1).padStart(3, '0')}`,
      Barcode: `PAGE${String(index + 1).padStart(3, '0')}`,
      Description: `Paged item ${index + 1}`,
    }));
    mockItemsFeed = pagedItemsFeed(rows);
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    expect(await screen.findByText('PAGE-001')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–20 of 45 inventory records')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(window.location.hash).toContain('page=2'));
    await waitFor(() => expect(screen.getByText('PAGE-021')).toBeInTheDocument());
    expect(screen.getByText('Showing 21–40 of 45 inventory records')).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Current page' }), '3');
    await waitFor(() => expect(window.location.hash).toContain('page=3'));
    await waitFor(() => expect(screen.getByText('PAGE-041')).toBeInTheDocument());
    expect(screen.getByText('Showing 41–45 of 45 inventory records')).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Rows per page' }), '50');
    await waitFor(() => expect(window.location.hash).toContain('page=1&page_size=50'));
    await waitFor(() => expect(screen.getByText('PAGE-001')).toBeInTheDocument());
    expect(screen.getByText('Showing 1–45 of 45 inventory records')).toBeInTheDocument();

    const search = screen.getByRole('combobox', { name: 'Scan or search inventory' });
    await user.type(search, 'PAGE-045');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(window.location.hash).toContain('search=PAGE-045'));
    expect(window.location.hash).toContain('page=1');
    await waitFor(() => expect(screen.getByText('PAGE-045')).toBeInTheDocument());
    expect(screen.getByText('Showing 1–1 of 1 inventory records')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Reset' }));
    await waitFor(() => expect(window.location.hash).not.toContain('search='));
    expect(window.location.hash).toContain('page=1');
    await waitFor(() => expect(screen.getByText('PAGE-001')).toBeInTheDocument());
    expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/items' && request.searchParams.get('page') === '1' && request.searchParams.get('page_size') === '50';
    })).toBe(true);
    expect(fetch.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/locations')).toHaveLength(1);
  });

  it('opens the phone camera scanner from Inventory and searches the detected code immediately', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('button', { name: 'Scan QR code or barcode with camera' }));
    const scanner = screen.getByRole('dialog', { name: 'Scan an item code' });
    await user.type(within(scanner).getByRole('textbox', { name: /Enter barcode or SKU instead/i }), 'SMOKE001');
    await user.click(within(scanner).getByRole('button', { name: 'Search item' }));

    await waitFor(() => expect(window.location.hash).toContain('search=SMOKE001'));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/items' && request.searchParams.get('search') === 'SMOKE001';
    })).toBe(true));
    expect(screen.queryByRole('dialog', { name: 'Scan an item code' })).not.toBeInTheDocument();
  });

  it('clears and disables Inventory selection while the next page is loading', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 21 }, (_, index) => ({
      ...item,
      id: index + 1,
      SKU: `SAFE-${String(index + 1).padStart(3, '0')}`,
      Description: `Safe paged item ${index + 1}`,
    }));
    mockItemsFeed = pagedItemsFeed(rows);
    let resolvePageTwo;
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/items' && request.searchParams.get('page') === '2') {
        return new Promise((resolve) => {
          resolvePageTwo = () => resolve(mockFetch(url, options));
        });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    const firstCheckbox = await screen.findByRole('checkbox', { name: 'Select SAFE-001' });
    await waitFor(() => expect(firstCheckbox).toBeEnabled());
    await user.click(firstCheckbox);
    expect(screen.getByRole('button', { name: 'Bulk Edit' })).toBeEnabled();

    await user.click(screen.getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(resolvePageTwo).toBeTypeOf('function'));
    expect(screen.getByRole('checkbox', { name: 'Select SAFE-001' })).not.toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Select SAFE-001' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Bulk Edit' })).toBeDisabled();

    await act(async () => { resolvePageTwo(); });
    expect(await screen.findByText('SAFE-021')).toBeInTheDocument();
  });

  it('removes hidden inventory selections after a successful same-page refresh', async () => {
    const user = userEvent.setup();
    let rows = [item];
    mockItemsFeed = (target) => pagedItemsFeed(rows)(target);
    fetch.mockImplementation((url, options = {}) => {
      if (String(url).includes('/api/integrations/woocommerce/writeback/stock/sync')) {
        return json({ status: 'no_changes', skipped_unmapped_count: 0 });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('checkbox', { name: 'Select SMOKE-001' }));
    expect(screen.getByRole('button', { name: 'Bulk Edit' })).toBeEnabled();

    rows = [{ ...item, id: 2, SKU: 'CURRENT-002', Description: 'Current Item' }];
    await user.click(screen.getByRole('button', { name: 'Update Stock' }));

    expect(await screen.findByText('Current Item')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: 'Bulk Edit' })).toBeDisabled());
    expect(screen.getByText('Select items to bulk edit')).toBeInTheDocument();
  });

  it('offers the shared safe bulk editor from the inventory table', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    await user.click(screen.getByRole('checkbox', { name: 'Select SMOKE-001' }));
    await user.click(screen.getByRole('button', { name: 'Bulk Edit' }));
    const dialog = screen.getByRole('dialog', { name: 'Bulk edit inventory items' });

    expect(within(dialog).getByRole('textbox', { name: 'Brand' })).toBeInTheDocument();
    expect(within(dialog).getByRole('spinbutton', { name: 'Unit cost' })).toBeInTheDocument();
    expect(within(dialog).getByRole('combobox', { name: 'Inventory location' })).toBeInTheDocument();
    expect(within(dialog).queryByRole('textbox', { name: 'SKU' })).not.toBeInTheDocument();
  });

  it('uses full-catalog raw facets while presenting decoded filter labels', async () => {
    const user = userEvent.setup();
    const rows = [
      { ...item, id: 1, SKU: 'FACET-1', Category: 'Dogs', Brand: 'Alpha' },
      { ...item, id: 2, SKU: 'FACET-2', Category: 'Dog &amp; Cat', Brand: 'Zeta &amp; Co' },
    ];
    mockItemFacets = { categories: ['Dog &amp; Cat', 'Dogs'], brands: ['Alpha', 'Zeta &amp; Co'] };
    mockItemsFeed = (target) => {
      const url = new URL(target);
      const category = url.searchParams.get('category');
      const filtered = category ? rows.filter((row) => row.Category === category) : rows;
      return {
        items: filtered.slice(0, 1),
        page: 1,
        page_size: 1,
        total: filtered.length,
        total_pages: filtered.length,
        returned_count: Math.min(filtered.length, 1),
      };
    };
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    await screen.findByText('FACET-1');
    const category = screen.getByRole('combobox', { name: 'Category' });
    expect(within(category).getByRole('option', { name: 'Dog & Cat' })).toHaveValue('Dog &amp; Cat');
    await user.selectOptions(category, 'Dog &amp; Cat');

    await screen.findByText('FACET-2');
    expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/items' && request.searchParams.get('category') === 'Dog &amp; Cat';
    })).toBe(true);
    const itemListCalls = fetch.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/items');
    expect(itemListCalls.length).toBeGreaterThan(1);
    expect(itemListCalls.every(([url]) => new URL(String(url)).searchParams.get('include_facets') === 'false')).toBe(true);
    expect(fetch.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/items/facets')).toHaveLength(1);
  });

  it('force-refreshes cached item facets after a metadata bulk edit', async () => {
    const user = userEvent.setup();
    let facetRequests = 0;
    mockItemFacets = () => {
      facetRequests += 1;
      return facetRequests === 1
        ? { categories: ['Test Category'], brands: ['Before Brand'] }
        : { categories: ['Test Category'], brands: ['After Brand'] };
    };
    fetch.mockImplementation((url, options) => {
      const target = String(url);
      if (target.includes('/api/items/bulk/preview')) return json({ can_commit: true, affected_count: 1, fields_to_update: ['brand'], warnings: [] });
      if (target.includes('/api/items/bulk/commit')) return json({ status: 'committed', updated_count: 1 });
      return mockFetch(url, options);
    });
    window.location.hash = '#items';
    render(<App />);

    await screen.findByRole('option', { name: 'Before Brand' });
    await user.click(screen.getByRole('checkbox', { name: 'Select SMOKE-001' }));
    await user.click(screen.getByRole('button', { name: 'Bulk edit 1' }));
    const dialog = screen.getByRole('dialog', { name: 'Bulk edit inventory items' });
    await user.type(within(dialog).getByRole('textbox', { name: 'Brand' }), 'After Brand');
    await user.click(within(dialog).getByRole('button', { name: 'Preview changes' }));
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Apply to 1 item(s)' })).toBeEnabled());
    await user.click(within(dialog).getByRole('button', { name: 'Apply to 1 item(s)' }));

    expect(await screen.findByRole('option', { name: 'After Brand' })).toBeInTheDocument();
    expect(facetRequests).toBe(2);
  });

  it('keeps inventory KPI summary filters aligned with search and data quality', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    const search = await screen.findByRole('combobox', { name: 'Scan or search inventory' });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Data Quality' }), 'missing_cost');
    await user.type(search, 'needle');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/inventory/summary/by-location'
        && request.searchParams.get('search') === 'needle'
        && request.searchParams.get('data_quality') === 'missing_cost';
    })).toBe(true));
  });

  it('shows zero-safe empty pagination metadata', async () => {
    mockItemsFeed = { items: [], page: 1, page_size: 20, total: 0, total_pages: 1, returned_count: 0 };
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    const pager = await screen.findByLabelText('Inventory Records pagination');
    expect(within(pager).getByText('Showing 0–0 of 0 inventory records')).toBeInTheDocument();
    expect(within(pager).getByRole('button', { name: 'Previous page' })).toBeDisabled();
    expect(within(pager).getByRole('button', { name: 'Next page' })).toBeDisabled();
  });

  it('decodes encoded product titles as clamped plain text without injecting markup', async () => {
    const encodedTitle = `Dog &amp; Coat ${'long product title '.repeat(8)}&lt;img data-xss-probe=&quot;true&quot; src=x&gt;`;
    const decodedTitle = `Dog & Coat ${'long product title '.repeat(8)}<img data-xss-probe="true" src=x>`;
    mockItemsFeed = { items: [{ ...item, woo_name: encodedTitle }], page: 1, page_size: 20, total: 1, total_pages: 1, returned_count: 1 };
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    const title = await screen.findByTitle(decodedTitle);
    expect(title).toHaveTextContent(decodedTitle);
    expect(title).toHaveClass('clamped-text');
    expect(title).toHaveAttribute('aria-label', decodedTitle);
    expect(title).toHaveAttribute('tabindex', '0');
    expect(title.closest('td')).toHaveClass('description-cell');
    expect(document.querySelector('[data-xss-probe]')).not.toBeInTheDocument();
  });

  it('distinguishes missing inventory fields from real numeric zero', async () => {
    mockItemsFeed = {
      items: [
        { ...item, id: 11, SKU: 'NULL-COST', Barcode: '', Brand: '', Category: '', 'Unit Cost': null, 'Default Location': 'RECEIVING', 'Inventory Location': 'RECEIVING' },
        { ...item, id: 12, SKU: 'ZERO-COST', Barcode: 'ZERO12', Brand: 'Zero Brand', Category: 'Zero Category', 'Unit Cost': 0, 'In Stock': 0, Allocated: 0 },
      ],
      page: 1,
      page_size: 20,
      total: 2,
      total_pages: 1,
      returned_count: 2,
    };
    window.location.hash = '#/inventory/all?page=1&page_size=20';
    render(<App />);

    const missingRow = (await screen.findByText('NULL-COST')).closest('tr');
    expect(within(missingRow).getByText('Barcode missing')).toBeInTheDocument();
    expect(within(missingRow).getByText('Brand missing')).toBeInTheDocument();
    expect(within(missingRow).getByText('Category missing')).toBeInTheDocument();
    expect(within(missingRow).getByText('Cost missing')).toBeInTheDocument();
    expect(within(missingRow).getByText('Receiving staging')).toBeInTheDocument();
    expect(within(missingRow).getByText('Not available')).toBeInTheDocument();

    const zeroRow = screen.getByText('ZERO-COST').closest('tr');
    expect(within(zeroRow).queryByText('Cost missing')).not.toBeInTheDocument();
    expect(within(zeroRow).getAllByText('$0.00')).toHaveLength(2);
  });

  it('previews variable parents as skipped and three variations as separate proposed items', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);
    await screen.findByText('Smoke Test Item');

    await user.click(screen.getByText('More'));
    await user.click(screen.getByRole('button', { name: /Sync WooCommerce catalog/i }));
    const dialog = screen.getByRole('dialog', { name: 'Import WooCommerce mappings' });
    await user.click(within(dialog).getByRole('button', { name: /Start Import Preview/i }));

    expect(await within(dialog).findByText('Catalog mapping preview')).toBeInTheDocument();
    expect(within(dialog).getByText('Parents skipped')).toBeInTheDocument();
    expect(within(dialog).getAllByText('Nutram Dog Food - 2 kg').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('Nutram Dog Food - 5 kg').length).toBeGreaterThan(0);
    expect(within(dialog).getAllByText('Nutram Dog Food - 11.4 kg').length).toBeGreaterThan(0);
    expect(within(dialog).getByText('Variable parent container is informational and will not become a stock item.')).toBeInTheDocument();
  });

  it('separates metadata updates from explicitly audited starting inventory', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/items/import';
    render(<App />);
    await screen.findByRole('heading', { name: 'What do you want this file to do?' });

    const update = screen.getByRole('button', { name: /Update item details/i });
    expect(update).toHaveTextContent('On hand, allocated, available, and movement history will not change.');
    const starting = screen.getByRole('button', { name: /Set starting inventory/i });
    expect(starting).toHaveTextContent('Creates audited starting-inventory movements.');
    const stock = screen.getByRole('button', { name: /Override stock levels/i });
    expect(stock).toHaveTextContent('Allocated and sellable remain system-managed.');
    expect(screen.queryByText(/closing stock/i)).not.toBeInTheDocument();
  });

  it('opens searchable remap selection without raw local database ID inputs', async () => {
    const user = userEvent.setup();
    window.location.hash = '#items';
    render(<App />);
    await screen.findByText('Smoke Test Item');

    await user.click(screen.getByText('More'));
    await user.click(screen.getByRole('button', { name: /Fix connection exceptions/i }));
    const dialog = screen.getByRole('dialog', { name: 'Remap WooCommerce exceptions' });
    expect(within(dialog).getByPlaceholderText('Search product, variation, SKU, or Woo ID')).toBeInTheDocument();
    expect(within(dialog).getByPlaceholderText('Search SKU, barcode, product name, or brand')).toBeInTheDocument();
    expect(within(dialog).queryByText('Local Item ID')).not.toBeInTheDocument();
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

  it('adds idempotency keys to scanner receiving and adjustment commits', async () => {
    const user = userEvent.setup();
    window.location.hash = '#scanner';
    render(<App />);

    await screen.findByRole('heading', { name: 'Scanner Console' });
    await user.click(screen.getByRole('button', { name: 'Receiving' }));
    await user.type(screen.getByPlaceholderText('Scan SKU, barcode, or item ID'), 'SMOKE-001');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Location' }), 'Smoke Rack');
    await user.click(screen.getByRole('button', { name: 'Commit' }));

    let receivingKey;
    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/scanner/receiving/scan/commit'));
      receivingKey = JSON.parse(commitCall[1].body).idempotency_key;
      expect(receivingKey).toEqual(expect.any(String));
    });

    await user.click(screen.getByRole('button', { name: 'Adjustment' }));
    await user.type(screen.getByRole('textbox', { name: 'Qty Change' }), '1');
    await user.type(screen.getByRole('textbox', { name: 'Reason' }), 'Count correction');
    await user.click(screen.getByRole('button', { name: 'Commit' }));

    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/scanner/adjustments/commit'));
      const adjustmentKey = JSON.parse(commitCall[1].body).idempotency_key;
      expect(adjustmentKey).toEqual(expect.any(String));
      expect(adjustmentKey).not.toBe(receivingKey);
    });
  });

  it('uses semantic receiving modes, an accessible stepper, disabled reasons, and named remove actions', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/receiving/direct';
    render(<App />);

    const modes = await screen.findByRole('navigation', { name: 'Receiving modes' });
    const itemRequests = fetch.mock.calls
      .map(([url]) => new URL(String(url)))
      .filter((url) => url.pathname === '/api/items');
    expect(itemRequests).toHaveLength(0);
    expect(within(modes).getByRole('link', { name: 'Direct Receiving' })).toHaveAttribute('aria-current', 'page');
    expect(within(modes).getByRole('link', { name: 'Bulk Receiving Session' })).not.toHaveAttribute('aria-current');
    expect(within(modes).getByRole('link', { name: 'Receipt History' })).not.toHaveAttribute('aria-current');

    const progress = screen.getByRole('list', { name: 'Direct receiving progress' });
    const steps = within(progress).getAllByRole('listitem');
    expect(steps).toHaveLength(3);
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    expect(steps[0]).toHaveAttribute('data-state', 'current');

    const commit = screen.getByRole('button', { name: 'Commit Receiving' });
    expect(commit).toBeDisabled();
    expect(commit).toHaveAttribute('aria-describedby', 'receiving-commit-reason');
    expect(screen.getByText('Commit unavailable: add at least one SKU or barcode.')).toHaveAttribute('role', 'status');

    expect(screen.getByRole('button', { name: 'Remove receiving line 1' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Add Line' }));
    const removeSecondLine = screen.getByRole('button', { name: 'Remove receiving line 2' });
    expect(removeSecondLine).toBeEnabled();
    await user.click(removeSecondLine);
    expect(screen.queryByRole('button', { name: 'Remove receiving line 2' })).not.toBeInTheDocument();

    await user.type(screen.getByRole('combobox', { name: 'Line 1 SKU or barcode' }), 'SMOKE-001');
    expect(steps[1]).toHaveAttribute('aria-current', 'step');
    expect(screen.getByText(/choose a destination location for every selected item/)).toHaveAttribute('role', 'status');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Line 1 inventory location' }), 'Smoke Rack');
    expect(screen.getByText(/preview the receipt after completing the required fields/)).toHaveAttribute('role', 'status');

    await user.click(screen.getByRole('button', { name: 'Preview Receiving' }));
    await waitFor(() => expect(commit).toBeEnabled());
    expect(steps[2]).toHaveAttribute('aria-current', 'step');
    expect(steps[2]).toHaveAttribute('data-state', 'current');
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/receipts/direct/preview'))).toBe(true);

    await user.click(commit);
    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/receipts/direct/commit'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ idempotency_key: expect.any(String) });
    });

    await user.click(within(modes).getByRole('link', { name: 'Receipt History' }));
    expect(await screen.findByRole('heading', { name: 'Receipt History', level: 2 })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/receiving/history');
    expect(screen.getByRole('link', { name: 'Receipt History' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('heading', { name: 'Direct Receiving', level: 2 })).not.toBeInTheDocument();
  });

  it('finds a later catalog item for direct receiving without preloading the catalog', async () => {
    const user = userEvent.setup();
    const laterItem = { id: 160, sku: 'LATE-160', barcode: '9916000', product_name: 'Later Catalog Product', description: 'Later Catalog Product', brand: 'Archive Brand', category: 'Test Category', in_stock: 37 };
    mockItemsFeed = pagedItemsFeed(Array.from({ length: 160 }, (_, index) => ({ ...item, id: index + 1, SKU: `PAGE-${String(index + 1).padStart(3, '0')}` })));
    fetch.mockImplementation((url, options) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/items/search') return json({ items: [laterItem], total: 1 });
      return mockFetch(url, options);
    });
    window.location.hash = '#/receiving/direct';
    render(<App />);

    await screen.findByRole('heading', { name: 'Direct Receiving', level: 2 });
    expect(fetch.mock.calls.map(([url]) => new URL(String(url))).filter((url) => url.pathname === '/api/items')).toHaveLength(0);

    const lookup = screen.getByRole('combobox', { name: 'Line 1 SKU or barcode' });
    await user.type(lookup, 'later');
    await user.click(await screen.findByRole('option', { name: /Later Catalog Product.*LATE-160/i }));
    expect(lookup).toHaveValue('LATE-160');
    expect(screen.getByText('Later Catalog Product')).toBeInTheDocument();

    await user.selectOptions(screen.getByRole('combobox', { name: 'Line 1 inventory location' }), 'Smoke Rack');
    await user.click(screen.getByRole('button', { name: 'Preview Receiving' }));
    await waitFor(() => {
      const previewCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/receipts/direct/preview'));
      expect(JSON.parse(previewCall[1].body).lines[0]).toMatchObject({ item_id: 160, sku: 'LATE-160', barcode: '9916000' });
    });
    expect(fetch.mock.calls.map(([url]) => new URL(String(url))).filter((url) => url.pathname === '/api/items')).toHaveLength(0);
  });

  it('finds a later catalog item for cycle counting without preloading the catalog', async () => {
    const user = userEvent.setup();
    const laterItem = { id: 161, sku: 'LATE-161', barcode: '9916100', product_name: 'Cycle Count Catalog Product', description: 'Cycle Count Catalog Product', brand: 'Archive Brand', category: 'Test Category', in_stock: 42 };
    fetch.mockImplementation((url, options) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/items/search') return json({ items: [laterItem], total: 1 });
      return mockFetch(url, options);
    });
    window.location.hash = '#cycle-count';
    render(<App />);

    await screen.findByRole('heading', { name: 'New Cycle Count' });
    expect(fetch.mock.calls.map(([url]) => new URL(String(url))).filter((url) => url.pathname === '/api/items')).toHaveLength(0);

    const lookup = screen.getByRole('combobox', { name: 'Cycle count line 1 SKU, barcode, or product' });
    await user.type(lookup, '99161');
    await user.click(await screen.findByRole('option', { name: /Cycle Count Catalog Product.*LATE-161/i }));
    expect(lookup).toHaveValue('LATE-161');
    expect(screen.getByText('Cycle Count Catalog Product')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: 'Cycle count line 1 counted quantity' }), '40');
    await user.click(screen.getByRole('button', { name: 'Preview Count' }));
    await waitFor(() => {
      const previewCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/cycle-counts/preview'));
      expect(JSON.parse(previewCall[1].body).lines[0]).toMatchObject({ item_id: 161, sku: 'LATE-161', barcode: '9916100', counted_quantity: 40 });
    });
    expect(fetch.mock.calls.map(([url]) => new URL(String(url))).filter((url) => url.pathname === '/api/items')).toHaveLength(0);
  });

  it('adds an idempotency key to bulk receiving commits', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/receiving/bulk';
    render(<App />);

    await screen.findByRole('heading', { name: 'Bulk Receiving Session' });
    await user.type(screen.getByPlaceholderText('Scan or type SKU/barcode'), 'SMOKE-001');
    await user.selectOptions(document.querySelector('.bulk-session .scanner-input-row select'), 'Smoke Rack');
    await user.click(screen.getByRole('button', { name: 'Add Line' }));
    await user.click(screen.getByRole('button', { name: 'Preview Session' }));
    const commit = screen.getByRole('button', { name: 'Commit Session' });
    await waitFor(() => expect(commit).toBeEnabled());
    await user.click(commit);

    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/receipts/bulk/commit'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ idempotency_key: expect.any(String) });
    });
  });

  it('uses route-backed report categories, scoped secondary navigation, and contextual filters', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/reports/inventory/low-stock';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Low Stock / Reorder', level: 1 })).toBeInTheDocument();
    expect(await screen.findByText('SMOKE-001')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Received Inventory Report' })).not.toBeInTheDocument();

    const categoryNav = screen.getByRole('navigation', { name: 'Low Stock / Reorder sections' });
    expect(within(categoryNav).getByRole('link', { name: 'Inventory' })).toHaveAttribute('aria-current', 'page');
    const inventoryNav = screen.getByRole('navigation', { name: 'Inventory reports' });
    expect(within(inventoryNav).getByRole('link', { name: 'Low Stock / Reorder' })).toHaveAttribute('aria-current', 'page');
    expect(within(inventoryNav).queryByRole('link', { name: 'Received Inventory' })).not.toBeInTheDocument();

    const inventoryFilters = document.querySelector('.report-filter-grid');
    expect(within(inventoryFilters).getByLabelText('Warehouse')).toBeInTheDocument();
    expect(within(inventoryFilters).getByLabelText('Inventory Location')).toBeInTheDocument();
    expect(within(inventoryFilters).getByLabelText('Brand')).toBeInTheDocument();
    expect(within(inventoryFilters).getByLabelText('Category')).toBeInTheDocument();
    expect(within(inventoryFilters).getByLabelText(/sku/i)).toBeInTheDocument();
    expect(within(inventoryFilters).queryByLabelText('Start Date')).not.toBeInTheDocument();
    expect(within(inventoryFilters).queryByLabelText('Barcode')).not.toBeInTheDocument();

    fetch.mockClear();
    await user.type(within(inventoryFilters).getByLabelText('Brand'), 'Acana');
    await user.click(screen.getByRole('button', { name: 'Refresh' }));
    await waitFor(() => {
      const reportCalls = fetch.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/api/reports/low-stock'));
      expect(reportCalls).toHaveLength(2);
      expect(reportCalls.every((url) => new URL(url).searchParams.get('brand') === 'Acana')).toBe(true);
      expect(reportCalls.every((url) => !new URL(url).searchParams.has('start_date') && !new URL(url).searchParams.has('barcode'))).toBe(true);
    });

    await user.click(within(categoryNav).getByRole('link', { name: 'Receiving' }));
    expect(await screen.findByRole('heading', { name: 'Receiving Cost', level: 1 })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/reports/receiving/receiving-cost');
    const receivingNav = screen.getByRole('navigation', { name: 'Receiving reports' });
    expect(within(receivingNav).getByRole('link', { name: 'Receiving Cost' })).toHaveAttribute('aria-current', 'page');
    expect(within(receivingNav).getByRole('link', { name: 'Received Inventory' })).toBeInTheDocument();
    expect(within(receivingNav).queryByRole('link', { name: 'Fulfillment' })).not.toBeInTheDocument();

    const receivingFilters = document.querySelector('.report-filter-grid');
    expect(within(receivingFilters).getByLabelText('Start Date')).toBeInTheDocument();
    expect(within(receivingFilters).getByLabelText('End Date')).toBeInTheDocument();
    expect(within(receivingFilters).getByLabelText('Warehouse')).toBeInTheDocument();
    expect(within(receivingFilters).getByLabelText('Inventory Location')).toBeInTheDocument();
    expect(within(receivingFilters).getByLabelText(/sku/i)).toBeInTheDocument();
    expect(within(receivingFilters).queryByLabelText('Barcode')).not.toBeInTheDocument();
    expect(within(receivingFilters).queryByLabelText('Brand')).not.toBeInTheDocument();
    expect(within(receivingFilters).queryByLabelText('Category')).not.toBeInTheDocument();

    await user.click(within(receivingNav).getByRole('link', { name: 'Received Inventory' }));
    expect(await screen.findByRole('heading', { name: 'Received Inventory', level: 1 })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Received Inventory Report', level: 2 })).toBeInTheDocument();
    expect(window.location.hash).toBe('#/reports/receiving/received-inventory');
    expect(screen.queryByRole('heading', { name: 'Receiving Cost', level: 2 })).not.toBeInTheDocument();
  });

  it.each([
    ['#items', 'Items'],
    ['#inventory', 'All Inventory'],
    ['#/reports/inventory/inventory-export', 'Inventory Export'],
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
    await settleInitialOrderPolling();

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
    await settleInitialOrderPolling();

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

  it('does not overlap WooCommerce status requests', async () => {
    let releaseStatus;
    const pendingStatus = new Promise((resolve) => {
      releaseStatus = () => resolve({
        ok: true,
        json: () => Promise.resolve({ configured: true, order_reconciliation: mockWooHealth }),
      });
    });
    fetch.mockImplementation((url) => (
      String(url).includes('/api/integrations/woocommerce/status') ? pendingStatus : mockFetch(url)
    ));
    render(<App />);

    await waitFor(() => expect(wooStatusCalls()).toHaveLength(1));
    await focusWindow();
    await focusWindow();
    expect(wooStatusCalls()).toHaveLength(1);

    await act(async () => {
      releaseStatus();
      await pendingStatus;
    });
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

  it('refreshes local order views without posting the Woo quick-sync endpoint', async () => {
    render(<App />);
    await settleInitialOrderPolling();
    fetch.mockClear();

    await focusWindow();

    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/business-dashboard'))).toBe(true));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/integrations/woocommerce/orders/quick-sync'))).toBe(false);
  });

  it('does not announce order update events as new customer orders', async () => {
    render(<App />);
    await settleInitialOrderPolling();
    mockWebhookFeed = {
      events: [{ ...mockWebhookEvent, id: 42, topic: 'order.updated', event_type: 'order_updated', created_order: false }],
      latest_event_id: 42,
      next_after_id: 42,
      has_more: false,
    };

    await focusWindow();
    await waitFor(() => expect(webhookEventPollCalls().some(([url]) => String(url).includes('after_id=0'))).toBe(true));

    expect(screen.queryByLabelText('New order notification')).not.toBeInTheDocument();
  });

  it('shows a global accessible warning when server reconciliation is stale', async () => {
    mockWooHealth = {
      ...mockWooHealth,
      healthy: false,
      stale: true,
      last_error: 'WooCommerce credentials expired.',
      message: 'Server order reconciliation is stale.',
    };
    render(<App />);

    const warning = await screen.findByRole('alert', { name: 'WooCommerce order sync warning' });
    expect(within(warning).getByText('Automatic order sync is not healthy')).toBeInTheDocument();
    expect(within(warning).getByText('WooCommerce credentials expired.')).toBeInTheDocument();
    expect(within(warning).getByRole('link', { name: 'Review WooCommerce Settings' })).toHaveAttribute('href', '#/settings/sync');
  });

  it('hides WooCommerce health warnings from the local development environment', async () => {
    mockWooEnvironment = 'development';
    mockWooHealth = {
      ...mockWooHealth,
      healthy: false,
      stale: true,
      last_error: 'Local WooCommerce sync is unavailable.',
    };
    render(<App />);

    await settleInitialOrderPolling();
    expect(screen.queryByRole('alert', { name: 'WooCommerce order sync warning' })).not.toBeInTheDocument();
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

  it('renders canonical overview metrics, unavailable refunds, and only contextual filters', async () => {
    window.location.hash = '#/insights/overview';
    render(<App />);

    expect(await screen.findByRole('tab', { name: 'Executive Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Orders & Revenue' })).toBeInTheDocument();
    expect(await screen.findByText('Refund detail is not synced yet.')).toBeInTheDocument();

    const metricLabels = [...document.querySelectorAll('.insights-summary-strip .metric > span')].map((node) => node.textContent);
    expect(metricLabels).toEqual(['Gross Sales', 'Discount Amount', 'Refund Amount', 'Net Sales', 'Total Orders', 'Units Sold', 'Average Order Value']);
    const refundMetric = screen.getByText('Refund Amount').closest('.metric');
    expect(within(refundMetric).getByText('Not available')).toBeInTheDocument();
    expect(within(refundMetric).getByText('Refund value reported by WooCommerce Analytics for the selected unfiltered range.')).toBeInTheDocument();
    expect(screen.getByText('Low risk')).toBeInTheDocument();
    expect(screen.queryByText('Total Revenue')).not.toBeInTheDocument();

    const filters = document.querySelector('.insights-filter-card');
    for (const label of ['Start Date', 'End Date', 'Brand', 'Category', 'SKU']) {
      expect(within(filters).getByLabelText(label)).toBeInTheDocument();
    }
    for (const label of ['Customer Email', 'Payment Method', 'Order Status', 'City']) {
      expect(within(filters).queryByLabelText(label)).not.toBeInTheDocument();
    }
  });

  it('gives data-quality warnings a real remediation route and affected scope', async () => {
    mockInsightOverview = {
      ...mockInsightOverview,
      data_quality: [{ code: 'missing_unit_cost', severity: 'warning', count: 3, message: 'Some products have no unit cost.' }],
    };
    window.location.hash = '#/insights/overview';
    render(<App />);

    expect(await screen.findByText('Some products have no unit cost.')).toBeInTheDocument();
    expect(screen.getByText('3 affected record(s)')).toBeInTheDocument();
    expect(screen.getByText('Margin and inventory-value metrics exclude items without cost.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review missing costs' })).toHaveAttribute('href', '#/inventory/all?data_quality=missing_cost');
  });

  it('deep-links Insights tabs, scopes filter requests, and supports arrow-key navigation', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/insights/orders-revenue';
    render(<App />);

    const ordersTab = await screen.findByRole('tab', { name: 'Orders & Revenue' });
    expect(ordersTab).toHaveAttribute('aria-selected', 'true');
    expect(ordersTab).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'insight-tab-orders-revenue');

    let filters = document.querySelector('.insights-filter-card');
    expect(within(filters).getByLabelText('Payment Method')).toBeInTheDocument();
    expect(within(filters).getByLabelText('Order Status')).toBeInTheDocument();
    expect(within(filters).queryByLabelText('Brand')).not.toBeInTheDocument();
    expect(within(filters).queryByLabelText('SKU')).not.toBeInTheDocument();

    await user.type(within(filters).getByLabelText('Payment Method'), 'stripe');
    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }));
    await waitFor(() => {
      const request = fetch.mock.calls.map(([url]) => String(url)).find((url) => url.includes('/api/insights/orders-revenue'));
      expect(request).toBeDefined();
      expect(new URL(request).searchParams.get('payment_method')).toBe('stripe');
      expect(new URL(request).searchParams.has('brand')).toBe(false);
      expect(new URL(request).searchParams.has('customer_email')).toBe(false);
    });

    ordersTab.focus();
    await user.keyboard('{ArrowRight}');
    const customerTab = await screen.findByRole('tab', { name: 'Customer Metrics', selected: true });
    await waitFor(() => expect(customerTab).toHaveFocus());
    expect(window.location.hash).toBe('#/insights/customer-metrics');
    expect(customerTab).toHaveAttribute('tabindex', '0');
    expect(screen.getByRole('tabpanel')).toHaveAttribute('aria-labelledby', 'insight-tab-customer-metrics');
    filters = document.querySelector('.insights-filter-card');
    expect(within(filters).getByLabelText('Customer Email')).toBeInTheDocument();
    expect(within(filters).queryByLabelText('Payment Method')).not.toBeInTheDocument();
  });

  it('keeps the verified Insights result visible while draft filters are edited', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/insights/overview';
    render(<App />);

    expect(await screen.findByText('DOG-FOOD')).toBeInTheDocument();
    const filters = document.querySelector('.insights-filter-card');
    await user.type(within(filters).getByLabelText('Brand'), 'Acana');

    expect(screen.getByText('DOG-FOOD')).toBeInTheDocument();
  });

  it('loads selected Insights tabs on demand without rendering every dashboard table', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/insights/overview';
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
    window.location.hash = '#/insights/overview';
    render(<App />);

    await user.click(await screen.findByRole('tab', { name: 'Customer Metrics' }));
    expect(await screen.findByText('Avery Stone')).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Product & SKU Metrics' }));
    expect(await screen.findByText('DOG-FOOD')).toBeInTheDocument();
  });

  it('shows subscription empty state and keeps export buttons real only', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/insights/overview';
    render(<App />);

    await user.click(await screen.findByRole('tab', { name: 'Subscriptions' }));

    expect((await screen.findAllByText('No subscription data synced yet')).length).toBeGreaterThan(0);
    const activeSubscriptions = screen.getByText('Active Subscriptions').closest('.metric');
    expect(within(activeSubscriptions).getByText('Not available')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /Export CSV/i })).not.toBeInTheDocument();
  });

  it('has a refresh button for Insights and reloads the selected dashboard', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/insights/overview';
    render(<App />);

    await screen.findByRole('tab', { name: 'Executive Overview' });
    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: /Refresh/i }));

    await waitFor(() => {
      expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/insights/overview'))).toBe(true);
    });
  });

  it('shows an Insights error without a contradictory empty table and retries successfully', async () => {
    const user = userEvent.setup();
    let overviewAttempts = 0;
    fetch.mockImplementation((url, options) => {
      if (String(url).includes('/api/insights/overview') && overviewAttempts++ === 0) {
        return Promise.resolve({ ok: false, status: 503, json: () => Promise.resolve({}), text: () => Promise.resolve('Unavailable') });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/insights/overview';
    render(<App />);

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Unable to load Pongo Insights from the backend.')).toBeInTheDocument();
    expect(screen.queryByText('Not enough data yet for this dashboard.')).not.toBeInTheDocument();
    await user.click(within(alert).getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('DOG-FOOD')).toBeInTheDocument();
  });

  it('shows staging WooCommerce Settings without exposing secrets', async () => {
    window.location.hash = '#/settings/connection';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'WooCommerce Connection', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Store connection & operations' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Catalog import, orders, remapping/i })).toHaveAttribute('href', '#/settings/sync');
    expect(screen.getByRole('link', { name: /Stock updates, order status/i })).toHaveAttribute('href', '#/settings/writeback');
    expect(await screen.findByText(/staging environment/i)).toBeInTheDocument();
    expect(await screen.findByText('staging32.pongo.ca')).toBeInTheDocument();
    expect(screen.getByText(/Keys never return to the browser after saving/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'WooCommerce Catalog Mapping & Import' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'WooCommerce write policy' })).not.toBeInTheDocument();
    expect(screen.queryByText(/ck_test/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cs_test/i)).not.toBeInTheDocument();
  });

  it('starts one-click Google sign-in without exposing a refresh token', async () => {
    const user = userEvent.setup();
    const navigate = vi.spyOn(browserNavigation, 'assign').mockImplementation(() => {});
    window.location.hash = '#/settings/google-sheets';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Google Sheets', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Connect report sharing' })).toBeInTheDocument();
    expect(screen.getByText(/not in Heroku or any hosting provider/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://inventory.pongo.ca/api/reports/google-sheets/oauth/callback')).toHaveAttribute('readonly');
    await user.type(screen.getByLabelText('OAuth client ID'), 'google-client-id');
    await user.type(screen.getByLabelText('OAuth client secret'), 'google-client-secret');
    await user.type(screen.getByLabelText(/Google Drive folder ID/i), 'pongo-folder');
    expect(screen.queryByLabelText(/refresh token/i)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Sign in with Google' }));

    await waitFor(() => {
      const call = fetch.mock.calls.find(([url, options]) => (
        String(url).includes('/api/reports/google-sheets/oauth/start') && options?.method === 'POST'
      ));
      expect(JSON.parse(call[1].body)).toEqual({
        client_id: 'google-client-id',
        client_secret: 'google-client-secret',
        folder_id: 'pongo-folder',
      });
    });
    expect(navigate).toHaveBeenCalledWith('https://accounts.google.com/o/oauth2/v2/auth?state=encrypted-state');
  });

  it('shows a safe message when Google access is denied', async () => {
    window.location.hash = '#/settings/google-sheets?google=denied';
    render(<App />);

    expect(await screen.findByText('Google access was not approved. Nothing was changed.')).toBeInTheDocument();
  });

  it('does not present a historical sync error as a current connection failure', async () => {
    mockWooLastError = 'Historical WooCommerce sync failed.';
    window.location.hash = '#/settings/connection';
    render(<App />);

    await screen.findByRole('heading', { name: 'Store connection & operations' });
    expect(screen.getByText('Configured', { selector: '.integration-health strong' })).toBeInTheDocument();
    expect(screen.queryByText('Historical WooCommerce sync failed.')).not.toBeInTheDocument();
  });

  it('keeps catalog, order, remap, and history workflows on Sync & Mapping only', async () => {
    window.location.hash = '#/settings/sync';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Sync & Mapping', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'WooCommerce Catalog Mapping & Import' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'WooCommerce Order Sync' })).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'WooCommerce Remap' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Sync Run History' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Store connection & operations' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'WooCommerce write policy' })).not.toBeInTheDocument();
  });

  it('paginates long Settings history tables instead of rendering every row', async () => {
    const user = userEvent.setup();
    const runs = Array.from({ length: 55 }, (_, index) => ({
      id: index + 1,
      started_at: '2026-07-28T12:00:00Z',
      completed_at: '2026-07-28T12:01:00Z',
      sync_type: 'products',
      status: 'completed',
      total_remote_records: 1,
      created_count: 0,
      updated_count: 1,
      matched_count: 1,
      skipped_count: 0,
      conflict_count: 0,
      error_count: 0,
      created_by: `Worker ${index + 1}`,
    }));
    fetch.mockImplementation((url, options) => {
      if (!String(url).includes('/api/integrations/woocommerce/sync-runs')) return mockFetch(url, options);
      const requestUrl = new URL(String(url));
      const page = Number(requestUrl.searchParams.get('page') || 1);
      const pageSize = Number(requestUrl.searchParams.get('page_size') || 50);
      const syncRuns = runs.slice((page - 1) * pageSize, page * pageSize);
      return json({ sync_runs: syncRuns, total: runs.length, page, page_size: pageSize, total_pages: Math.ceil(runs.length / pageSize), returned_count: syncRuns.length, has_previous: page > 1, has_next: page * pageSize < runs.length });
    });
    window.location.hash = '#/settings/sync';
    render(<App />);

    const history = (await screen.findByText('55 sync run(s)')).closest('.table-wrap');
    expect(within(history).getAllByRole('row')).toHaveLength(51);
    expect(within(history).getByText(/Showing 1–50 of 55 sync runs/)).toBeInTheDocument();

    await user.click(within(history).getByRole('button', { name: 'Next page' }));

    expect(within(history).getAllByRole('row')).toHaveLength(6);
    expect(within(history).getByText(/Showing 51–55 of 55 sync runs/)).toBeInTheDocument();
    expect(within(history).getByText('Worker 55')).toBeInTheDocument();
  });

  it('ignores an older sync-history response after a newer page-size request completes', async () => {
    const user = userEvent.setup();
    const runs = Array.from({ length: 55 }, (_, index) => ({
      id: index + 1,
      started_at: '2026-07-28T12:00:00Z',
      completed_at: '2026-07-28T12:01:00Z',
      sync_type: 'products',
      status: 'completed',
      total_remote_records: 1,
      created_count: 0,
      updated_count: 1,
      matched_count: 1,
      skipped_count: 0,
      conflict_count: 0,
      error_count: 0,
      created_by: `Worker ${index + 1}`,
    }));
    let resolveSlowPage;
    fetch.mockImplementation((url, options) => {
      if (!String(url).includes('/api/integrations/woocommerce/sync-runs')) return mockFetch(url, options);
      const requestUrl = new URL(String(url));
      const page = Number(requestUrl.searchParams.get('page') || 1);
      const pageSize = Number(requestUrl.searchParams.get('page_size') || 50);
      const syncRuns = runs.slice((page - 1) * pageSize, page * pageSize);
      const body = { sync_runs: syncRuns, total: runs.length, page, page_size: pageSize, total_pages: Math.ceil(runs.length / pageSize), returned_count: syncRuns.length, has_previous: page > 1, has_next: page * pageSize < runs.length };
      if (page === 2 && pageSize === 50) {
        return new Promise((resolve) => {
          resolveSlowPage = () => resolve({ ok: true, json: () => Promise.resolve(body), text: () => Promise.resolve(JSON.stringify(body)) });
        });
      }
      return json(body);
    });
    window.location.hash = '#/settings/sync';
    render(<App />);

    const history = (await screen.findByText('55 sync run(s)')).closest('.table-wrap');
    await user.click(within(history).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(resolveSlowPage).toBeTypeOf('function'));
    await user.selectOptions(within(history).getByRole('combobox', { name: 'Rows per page' }), '20');
    await waitFor(() => expect(within(history).getByText(/Showing 1–20 of 55 sync runs/)).toBeInTheDocument());
    expect(within(history).getByText('Worker 20')).toBeInTheDocument();

    await act(async () => {
      resolveSlowPage();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(within(history).getByText(/Showing 1–20 of 55 sync runs/)).toBeInTheDocument();
    expect(within(history).getByText('Worker 20')).toBeInTheDocument();
    expect(within(history).queryByText('Worker 55')).not.toBeInTheDocument();
  });

  it('keeps the selected sync-history page during historical-import polling', async () => {
    const user = userEvent.setup();
    const intervalCallbacks = [];
    vi.spyOn(window, 'setInterval').mockImplementation((callback, delay) => {
      intervalCallbacks.push({ callback, delay });
      return intervalCallbacks.length;
    });
    const runs = Array.from({ length: 55 }, (_, index) => ({
      id: index + 1,
      started_at: '2026-07-28T12:00:00Z',
      completed_at: null,
      sync_type: 'orders_history',
      status: index === 54 ? 'running' : 'completed',
      total_remote_records: 1,
      created_count: 0,
      updated_count: 1,
      matched_count: 1,
      skipped_count: 0,
      conflict_count: 0,
      error_count: 0,
      created_by: `History Worker ${index + 1}`,
    }));
    fetch.mockImplementation((url, options) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/integrations/woocommerce/status') {
        return json({
          configured: true,
          environment: 'staging',
          order_history_import: { id: 55, status: 'running', total_remote_records: 10, progress: { current_status: 'any', next_page: 2 } },
          order_history_coverage: { verified_complete: false, local_order_count: 10, source_absent_snapshot_count: 0, distinct_order_dates: 2 },
        });
      }
      if (request.pathname !== '/api/integrations/woocommerce/sync-runs') return mockFetch(url, options);
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 50);
      const syncRuns = runs.slice((page - 1) * pageSize, page * pageSize);
      return json({ sync_runs: syncRuns, total: runs.length, page, page_size: pageSize, total_pages: Math.ceil(runs.length / pageSize), returned_count: syncRuns.length, has_previous: page > 1, has_next: page * pageSize < runs.length });
    });
    window.location.hash = '#/settings/sync';
    render(<App />);

    const history = (await screen.findByText('55 sync run(s)')).closest('.table-wrap');
    await user.click(within(history).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(within(history).getByText(/Showing 51–55 of 55 sync runs/)).toBeInTheDocument());
    await waitFor(() => expect(intervalCallbacks.some(({ delay }) => delay === 3000)).toBe(true));
    const callsBeforePoll = fetch.mock.calls.length;

    await act(async () => {
      intervalCallbacks.find(({ delay }) => delay === 3000).callback();
      await Promise.resolve();
      await Promise.resolve();
    });

    await waitFor(() => expect(fetch.mock.calls.slice(callsBeforePoll).some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/integrations/woocommerce/sync-runs'
        && request.searchParams.get('page') === '2'
        && request.searchParams.get('page_size') === '50';
    })).toBe(true));
    expect(within(history).getByText(/Showing 51–55 of 55 sync runs/)).toBeInTheDocument();
  });

  it('sends changed WooCommerce credentials only to the backend configuration endpoint', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/settings/connection';
    render(<App />);

    await screen.findByRole('heading', { name: 'Store connection & operations' });
    await user.type(screen.getByLabelText('Consumer key'), 'ck_replacement');
    await user.type(screen.getByLabelText('Consumer secret'), 'cs_replacement');
    await user.click(screen.getByRole('button', { name: 'Save & verify connection' }));

    await waitFor(() => {
      const call = fetch.mock.calls.find(([url]) => String(url).includes('/api/integrations/woocommerce/configuration'));
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).toEqual({
        base_url: 'https://staging32.pongo.ca',
        consumer_key: 'ck_replacement',
        consumer_secret: 'cs_replacement',
      });
    });
    expect(await screen.findByText(/verified and saved in the backend environment/i)).toBeInTheDocument();
  });

  it('changes WooCommerce access mode from the connection page', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/settings/connection';
    render(<App />);

    await screen.findByRole('heading', { name: 'Store connection & operations' });
    expect(screen.getByRole('button', { name: /Read & writeEnable Pongo/i })).toHaveAttribute('aria-pressed', 'true');
    await user.click(screen.getByRole('button', { name: /Read onlyGET requests only/i }));

    await waitFor(() => {
      const call = fetch.mock.calls.find(([url]) => String(url).includes('/api/integrations/woocommerce/access-mode'));
      expect(call).toBeTruthy();
      expect(JSON.parse(call[1].body)).toEqual({ access_mode: 'read_only' });
    });
  });

  it('blocks a WooCommerce host replacement until it is explicitly authorized', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/settings/connection';
    render(<App />);

    await screen.findByRole('heading', { name: 'Store connection & operations' });
    const storeUrl = screen.getByLabelText('Store URL');
    const saveButton = screen.getByRole('button', { name: 'Save & verify connection' });
    await user.clear(storeUrl);
    await user.type(storeUrl, 'https://staging23.pongo.ca/');

    expect(screen.getByText('staging32.pongo.ca', { selector: '.integration-host-comparison strong' })).toBeInTheDocument();
    expect(screen.getByText('staging23.pongo.ca', { selector: '.integration-host-comparison strong' })).toBeInTheDocument();
    expect(screen.getByText('Host review required')).toBeInTheDocument();
    expect(saveButton).toBeDisabled();
    await user.keyboard('{Enter}');
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/integrations/woocommerce/configuration'))).toBe(false);

    await user.click(screen.getByRole('checkbox', { name: /Authorize replacing the WooCommerce host/i }));
    expect(saveButton).toBeEnabled();
    await user.click(saveButton);

    await waitFor(() => {
      const call = fetch.mock.calls.find(([url]) => String(url).includes('/api/integrations/woocommerce/configuration'));
      expect(JSON.parse(call[1].body)).toEqual({
        base_url: 'https://staging23.pongo.ca/',
        consumer_key: '',
        consumer_secret: '',
        allow_host_change: true,
      });
    });
  });

  it('renders a WooCommerce API detail string without JSON quotes', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation((url, options) => (
      String(url).includes('/api/integrations/woocommerce/configuration')
        ? Promise.resolve({
          ok: false,
          status: 400,
          json: () => Promise.resolve({ detail: 'WooCommerce connection failed: host replacement was not authorized.' }),
          text: () => Promise.resolve(''),
        })
        : mockFetch(url, options)
    ));
    window.location.hash = '#/settings/connection';
    render(<App />);

    await screen.findByRole('heading', { name: 'Store connection & operations' });
    await user.click(screen.getByRole('button', { name: 'Save & verify connection' }));

    const message = await screen.findByText('WooCommerce connection failed: host replacement was not authorized.');
    expect(message).toHaveTextContent(/^WooCommerce connection failed: host replacement was not authorized\.$/);
  });

  it('renders dry-run staging writeback controls in Settings', async () => {
    window.location.hash = '#/settings/writeback';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Writeback Control', level: 1 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'WooCommerce write policy' })).toBeInTheDocument();
    expect(screen.getByText(/Live Staging Writes On/i)).toBeInTheDocument();
    expect(screen.getByText('Hard-blocked operations')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview stock writeback/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Preview order writeback/i })).toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /Send to Staging/i })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Store connection & operations' })).not.toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'WooCommerce Catalog Mapping & Import' })).not.toBeInTheDocument();
  });

  it('paginates and searches the WooCommerce writeback queue on the server', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 55 }, (_, index) => ({
      id: index + 1,
      operation_type: 'update_product_stock',
      entity_type: 'inventory_item',
      entity_id: index + 1,
      woo_entity_id: 1000 + index,
      status: 'pending',
      environment: 'staging',
      dry_run: false,
      preview_json: { sku: `QUEUE-${String(index + 1).padStart(3, '0')}`, woo_stock_snapshot: 1, proposed_woo_stock: 2 },
      created_at: '2026-07-09T12:00:00Z',
    }));
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname !== '/api/integrations/woocommerce/writeback/queue' || options.method) return mockFetch(url, options);
      const search = (request.searchParams.get('search') || '').toLowerCase();
      const matching = search
        ? rows.filter((row) => [row.operation_type, row.entity_type, row.entity_id, row.woo_entity_id, row.status].some((value) => String(value).toLowerCase().includes(search)))
        : rows;
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 50);
      const queue = matching.slice((page - 1) * pageSize, page * pageSize);
      return json({ queue, total: matching.length, page, page_size: pageSize, total_pages: Math.ceil(matching.length / pageSize), returned_count: queue.length, has_previous: page > 1, has_next: page * pageSize < matching.length });
    });
    window.location.hash = '#/settings/writeback';
    render(<App />);

    const caption = await screen.findByText('55 matching queue item(s)', { selector: '.table-meta > span' });
    const table = caption.closest('.table-wrap');
    expect(within(table).getByText(/Showing 1–50 of 55 queue items/)).toBeInTheDocument();
    await user.click(within(table).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(within(table).getByText(/Showing 51–55 of 55 queue items/)).toBeInTheDocument());
    expect(within(table).getByText(/QUEUE-055/)).toBeInTheDocument();

    await user.type(screen.getByRole('textbox', { name: 'Search writeback queue' }), '1054');
    await waitFor(() => expect(within(table).getByText(/Showing 1–1 of 1 queue items/)).toBeInTheDocument());
    expect(fetch.mock.calls.some(([url]) => new URL(String(url)).searchParams.get('search') === '1054')).toBe(true);
  });

  it('keeps the active writeback queue filter, search, and page after a queue mutation', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 55 }, (_, index) => ({
      id: index + 1,
      operation_type: 'update_product_stock',
      entity_type: 'keep_item',
      entity_id: index + 1,
      woo_entity_id: 2000 + index,
      status: 'pending',
      environment: 'staging',
      dry_run: false,
      preview_json: { sku: `KEEP-${String(index + 1).padStart(3, '0')}`, woo_stock_snapshot: 1, proposed_woo_stock: 2 },
      created_at: '2026-07-09T12:00:00Z',
    }));
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname.match(/\/api\/integrations\/woocommerce\/writeback\/queue\/\d+\/approve$/) && options.method === 'POST') {
        return json({ status: 'approved' });
      }
      if (request.pathname !== '/api/integrations/woocommerce/writeback/queue' || options.method) return mockFetch(url, options);
      const status = request.searchParams.get('status');
      const search = (request.searchParams.get('search') || '').toLowerCase();
      const matching = rows.filter((row) => (
        (!status || row.status === status)
        && (!search || [row.operation_type, row.entity_type, row.entity_id, row.woo_entity_id, row.status].some((value) => String(value).toLowerCase().includes(search)))
      ));
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 50);
      const queue = matching.slice((page - 1) * pageSize, page * pageSize);
      return json({ queue, total: matching.length, page, page_size: pageSize, total_pages: Math.ceil(matching.length / pageSize), returned_count: queue.length, has_previous: page > 1, has_next: page * pageSize < matching.length });
    });
    window.location.hash = '#/settings/writeback';
    render(<App />);

    const caption = await screen.findByText('55 matching queue item(s)', { selector: '.table-meta > span' });
    const table = caption.closest('.table-wrap');
    await user.click(within(screen.getByLabelText('Filter writeback queue')).getByRole('button', { name: 'Pending' }));
    await user.type(screen.getByRole('textbox', { name: 'Search writeback queue' }), 'keep');
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/integrations/woocommerce/writeback/queue'
        && request.searchParams.get('status') === 'pending'
        && request.searchParams.get('search') === 'keep';
    })).toBe(true));
    await user.click(within(table).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(within(table).getByText(/Showing 51–55 of 55 queue items/)).toBeInTheDocument());

    const callsBeforeMutation = fetch.mock.calls.length;
    await user.click(within(table).getAllByRole('button', { name: 'Approve' })[0]);
    await waitFor(() => expect(fetch.mock.calls.slice(callsBeforeMutation).some(([url, options = {}]) => {
      const request = new URL(String(url));
      return !options.method
        && request.pathname === '/api/integrations/woocommerce/writeback/queue'
        && request.searchParams.get('status') === 'pending'
        && request.searchParams.get('search') === 'keep'
        && request.searchParams.get('page') === '2'
        && request.searchParams.get('page_size') === '50';
    })).toBe(true));
  });

  it('keeps every route candidate reachable through server pagination', async () => {
    const user = userEvent.setup();
    const candidates = Array.from({ length: 55 }, (_, index) => ({
      order_id: index + 1,
      woo_order_id: 9000 + index,
      woo_order_number: `ROUTE-${String(index + 1).padStart(3, '0')}`,
      local_status: 'fulfilled',
      customer_name: `Customer ${index + 1}`,
      customer_email: `customer-${index + 1}@example.invalid`,
      customer_phone: '',
      shipping_summary: { city: 'Edmonton' },
      order_total: 10,
      fulfilled_line_count: 1,
      total_quantity_fulfilled: 1,
      date_created: '2026-08-01T12:00:00Z',
    }));
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname !== '/api/routes/candidates' || options.method) return mockFetch(url, options);
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 50);
      const rows = candidates.slice((page - 1) * pageSize, page * pageSize);
      return json({ total_candidates: candidates.length, candidates: rows, page, page_size: pageSize, total_pages: Math.ceil(candidates.length / pageSize), returned_count: rows.length, has_previous: page > 1, has_next: page * pageSize < candidates.length });
    });
    window.location.hash = '#routes';
    render(<App />);

    const caption = await screen.findByText('55 candidate order(s)', { selector: '.table-meta > span' });
    const table = caption.closest('.table-wrap');
    expect(within(table).getByText(/Showing 1–50 of 55 route candidates/)).toBeInTheDocument();
    await user.click(within(table).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(within(table).getByText(/Showing 51–55 of 55 route candidates/)).toBeInTheDocument());
    expect(within(table).getByText('ROUTE-055')).toBeInTheDocument();

    const candidateToolbar = screen.getByLabelText('Order Date').closest('.toolbar');
    await user.type(within(candidateToolbar).getByLabelText('Order Date'), '2026-08-01');
    await user.click(within(candidateToolbar).getByRole('button', { name: /^Apply$/i }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => new URL(String(url)).searchParams.get('route_date') === '2026-08-01')).toBe(true));
  });

  it('plans every open order from the warehouse and generates shareable Google Maps routes for any driver count', async () => {
    const user = userEvent.setup();
    window.location.hash = '#routes';
    render(<App />);

    expect(await screen.findByRole('heading', { name: 'Route all open orders' })).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Starting location' })).toHaveValue('5855 99 Street NW, Edmonton, AB');
    expect(await screen.findByRole('heading', { name: 'Driver 1' })).toBeInTheDocument();
    expect(screen.getByText('Order #0802')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open Maps' })).toHaveAttribute('href', expect.stringContaining('https://www.google.com/maps/dir/'));

    const driverCount = screen.getByRole('spinbutton', { name: 'Number of drivers' });
    await user.clear(driverCount);
    await user.type(driverCount, '3');
    await user.click(screen.getByRole('button', { name: 'Plan all open orders' }));

    await waitFor(() => expect(fetch.mock.calls.some(([url, options = {}]) => (
      String(url).includes('/api/routes/open-orders/plan')
      && JSON.parse(options.body || '{}').driver_count === 3
      && JSON.parse(options.body || '{}').start_address === '5855 99 Street NW, Edmonton, AB'
    ))).toBe(true));
  });

  it('shows all Update All errors and wires resume and cancel actions after refresh', async () => {
    const user = userEvent.setup();
    const jobs = [
      { id: 81, status: 'completed_with_errors', force: true, chunk_size: 20, total_items: 2, processed_items: 2, sent_count: 1, dry_run_count: 0, failed_count: 1, skipped_unmapped_count: 0, unchanged_count: 0, progress_percent: 100, errors: ['SKU-A: timeout', 'SKU-B: mapping failed'], last_error: 'SKU-B: mapping failed', created_at: '2026-07-31T12:00:00Z' },
      { id: 82, status: 'running', force: true, chunk_size: 20, total_items: 10, processed_items: 2, sent_count: 2, dry_run_count: 0, failed_count: 0, skipped_unmapped_count: 0, unchanged_count: 0, progress_percent: 20, errors: [], last_error: null, created_at: '2026-07-31T12:01:00Z' },
    ];
    fetch.mockImplementation((url) => {
      const target = String(url);
      if (target.includes('/api/integrations/woocommerce/writeback/stock/jobs?')) return json({ jobs, total: jobs.length, page: 1, page_size: 25, total_pages: 1, returned_count: jobs.length, has_previous: false, has_next: false });
      if (target.includes('/api/integrations/woocommerce/writeback/stock/jobs/81/resume')) return json({ ...jobs[0], status: 'queued' });
      if (target.includes('/api/integrations/woocommerce/writeback/stock/jobs/82/cancel')) return json({ ...jobs[1], status: 'cancelling' });
      return mockFetch(url);
    });
    window.location.hash = '#/settings/writeback';
    render(<App />);

    await screen.findByRole('heading', { name: 'Update All history' });
    await user.click(screen.getByText('SKU-B: mapping failed', { selector: 'summary' }));
    expect(screen.getByText('SKU-A: timeout')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Download error report' })).toHaveAttribute('download', 'pongo-stock-sync-job-81-errors.txt');
    await user.click(screen.getAllByRole('button', { name: 'Resume' }).find((button) => !button.disabled));
    await user.click(screen.getAllByRole('button', { name: 'Cancel' }).find((button) => !button.disabled));
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/stock/jobs/81/resume'))).toBe(true);
    expect(fetch.mock.calls.some(([url]) => String(url).includes('/stock/jobs/82/cancel'))).toBe(true);
  });

  it('keeps the current Update All history page after a stock-job action', async () => {
    const user = userEvent.setup();
    const jobs = Array.from({ length: 30 }, (_, index) => ({
      id: index + 1,
      status: 'completed_with_errors',
      force: true,
      chunk_size: 20,
      total_items: 2,
      processed_items: 2,
      sent_count: 1,
      dry_run_count: 0,
      failed_count: 1,
      skipped_unmapped_count: 0,
      unchanged_count: 0,
      progress_percent: 100,
      errors: [],
      last_error: `Job ${index + 1} failed`,
      created_at: '2026-07-31T12:00:00Z',
    }));
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname.match(/\/api\/integrations\/woocommerce\/writeback\/stock\/jobs\/\d+\/resume$/) && options.method === 'POST') {
        return json({ status: 'queued' });
      }
      if (request.pathname !== '/api/integrations/woocommerce/writeback/stock/jobs' || options.method) return mockFetch(url, options);
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 25);
      const pageJobs = jobs.slice((page - 1) * pageSize, page * pageSize);
      return json({ jobs: pageJobs, total: jobs.length, page, page_size: pageSize, total_pages: Math.ceil(jobs.length / pageSize), returned_count: pageJobs.length, has_previous: page > 1, has_next: page * pageSize < jobs.length });
    });
    window.location.hash = '#/settings/writeback';
    render(<App />);

    const caption = await screen.findByText('30 stock sync job(s)', { selector: '.table-meta > span' });
    const table = caption.closest('.table-wrap');
    await user.click(within(table).getByRole('button', { name: 'Next page' }));
    await waitFor(() => expect(within(table).getByText(/Showing 26–30 of 30 stock sync jobs/)).toBeInTheDocument());

    const callsBeforeMutation = fetch.mock.calls.length;
    await user.click(within(table).getAllByRole('button', { name: 'Resume' })[0]);
    await waitFor(() => expect(fetch.mock.calls.slice(callsBeforeMutation).some(([url, options = {}]) => {
      const request = new URL(String(url));
      return !options.method
        && request.pathname === '/api/integrations/woocommerce/writeback/stock/jobs'
        && request.searchParams.get('page') === '2'
        && request.searchParams.get('page_size') === '25';
    })).toBe(true));
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
    expect(await screen.findByText('No open customer orders match the current filters.')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/orders/open' && request.searchParams.get('order_number') === '9999' && request.searchParams.get('page') === '1';
    })).toBe(true);

    await user.click(screen.getByRole('button', { name: 'Clear' }));
    expect(await screen.findByText('0802')).toBeInTheDocument();
  });

  it('resets Open filters when returning from another order workspace', async () => {
    const user = userEvent.setup();
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    const customerInput = screen.getByRole('textbox', { name: 'Customer' });
    await user.type(customerInput, 'Avery');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => new URL(String(url)).searchParams.get('customer') === 'Avery')).toBe(true));

    act(() => { window.location.hash = '#/orders/pick'; });
    await screen.findByRole('heading', { name: 'Pick Orders', level: 1 });
    act(() => { window.location.hash = '#/orders/open'; });

    expect(await screen.findByRole('textbox', { name: 'Customer' })).toHaveValue('');
    await waitFor(() => {
      const openCalls = fetch.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/orders/open');
      expect(new URL(String(openCalls.at(-1)[0])).searchParams.has('customer')).toBe(false);
    });
  });

  it('preserves the active Open filter when a single order is completed', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    window.location.hash = '#/orders/open';
    render(<App />);

    await screen.findByRole('heading', { name: 'Open Orders', level: 1 });
    await user.type(screen.getByRole('textbox', { name: 'Customer' }), 'Avery');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => new URL(String(url)).searchParams.get('customer') === 'Avery')).toBe(true));
    fetch.mockClear();

    await user.click(screen.getByRole('button', { name: 'Open actions for order 0802' }));
    await user.click(screen.getByRole('menuitem', { name: 'Complete order' }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/orders/701/complete/commit'))).toBe(true));
    await waitFor(() => {
      const refreshes = fetch.mock.calls.filter(([url]) => new URL(String(url)).pathname === '/api/orders/open');
      expect(refreshes.length).toBeGreaterThan(0);
      expect(refreshes.every(([url]) => new URL(String(url)).searchParams.get('customer') === 'Avery')).toBe(true);
    });
    expect(screen.getByRole('textbox', { name: 'Customer' })).toHaveValue('Avery');
    confirmSpy.mockRestore();
  });

  it('requests Open and Pick order pages from the backend', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 21 }, (_, index) => ({
      ...mockOrder,
      id: 800 + index,
      woo_order_id: 1800 + index,
      woo_order_number: `P-${String(index + 1).padStart(2, '0')}`,
    }));
    mockOpenOrdersFeed = pagedOrdersFeed(rows);
    mockPickOrdersFeed = pagedOrdersFeed(rows);
    window.location.hash = '#/orders/open';
    render(<App />);

    expect((await screen.findAllByText('Showing 1–20 of 21 orders'))[0]).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Next orders page' })[0]);
    expect(await screen.findByText('P-21')).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/orders/open' && request.searchParams.get('page') === '2' && request.searchParams.get('page_size') === '20';
    })).toBe(true));

    act(() => { window.location.hash = '#/orders/pick'; });
    expect(await screen.findByText('21 order(s) ready to pick')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next orders page' }));
    expect(await screen.findByText('P-21')).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/orders/pick' && request.searchParams.get('page') === '2' && request.searchParams.get('page_size') === '20';
    })).toBe(true));
  });

  it('disables stale Open rows and aborts their request when leaving Orders', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 21 }, (_, index) => ({
      ...mockOrder,
      id: 900 + index,
      woo_order_id: 1900 + index,
      woo_order_number: `WAIT-${String(index + 1).padStart(2, '0')}`,
    }));
    mockOpenOrdersFeed = pagedOrdersFeed(rows);
    let pageTwoSignal;
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/orders/open' && request.searchParams.get('page') === '2') {
        pageTwoSignal = options.signal;
        return new Promise((resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/orders/open';
    render(<App />);

    expect(await screen.findByText('WAIT-01')).toBeInTheDocument();
    await user.click(screen.getAllByRole('button', { name: 'Next orders page' })[0]);
    await waitFor(() => expect(pageTwoSignal).toBeTruthy());
    expect(screen.getByRole('checkbox', { name: 'Select order WAIT-01' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Actions' })).toBeDisabled();

    act(() => { window.location.hash = '#/orders/completed'; });
    await screen.findByRole('heading', { name: 'Completed Orders', level: 1 });
    expect(pageTwoSignal.aborted).toBe(true);
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
    const invoice = screen.getByLabelText('Invoice for order 0802');
    expect(invoice.parentElement).toBe(document.body);
    expect(within(invoice).getByRole('img', { name: 'Pongo Pet Supplies' })).toHaveAttribute('src', '/pongo-logo.png');
    expect(within(invoice).getByText('Billing details')).toBeInTheDocument();
    expect(within(invoice).getByText('100 Billing Ave')).toBeInTheDocument();
    expect(within(invoice).getByText('Shipping details')).toBeInTheDocument();
    expect(within(invoice).getByText('200 Delivery Way')).toBeInTheDocument();
    expect(within(invoice).getByText('Cash on delivery')).toBeInTheDocument();
    expect(within(invoice).getByText('Completed')).toBeInTheDocument();
    expect(within(invoice).getByText('Leave at the receiving desk.')).toBeInTheDocument();
    expect(within(invoice).queryByText(/Woo reconciliation/)).not.toBeInTheDocument();
    expect(within(invoice).queryByText(/WooCommerce|CAD|Local order ID|Printed/)).not.toBeInTheDocument();
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
    expect(screen.queryByRole('button', { name: /preview allocation|commit allocation|allocate selected/i })).not.toBeInTheDocument();

    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: 'Run FIFO Allocation' }));
    await waitFor(() => {
      const allocationCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/allocations/auto/commit'));
      expect(allocationCall?.[1]).toMatchObject({ method: 'POST', body: '{}' });
    });
    expect(await screen.findByText('0 unit(s) reserved in first-come-first-served order. 0 order(s) became fully allocated.')).toBeInTheDocument();

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
    const newStock = screen.getByRole('spinbutton', { name: 'New Stock Quantity' });
    await user.clear(newStock);
    await user.type(newStock, '1');
    await user.click(screen.getByRole('button', { name: 'Update and Auto-Allocate' }));
    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/scanner/adjustments/commit'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ idempotency_key: expect.any(String) });
    });
  });

  it('paginates allocation exceptions on the server and exports the full applied filter', async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: 21 }, (_, index) => ({
      ...mockAllocationException,
      order_id: 900 + index,
      order_line_id: 1900 + index,
      woo_order_id: 2900 + index,
      woo_order_number: `A-${String(index + 1).padStart(2, '0')}`,
      sku: `ALLOC-${String(index + 1).padStart(2, '0')}`,
      item_id: 3900 + index,
      description: `Allocation item ${index + 1}`,
      warehouse: index === 20 ? 'Secondary Warehouse' : 'Main Warehouse',
    }));
    mockAllocationExceptionsFeed = pagedAllocationExceptionsFeed(rows);
    window.location.hash = '#/orders/allocate';
    render(<App />);

    expect(await screen.findByText('Showing 1–20 of 21 item shortages')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Secondary Warehouse' })).toBeInTheDocument();
    expect(screen.queryByText('ALLOC-21')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next item shortages page' }));
    expect(await screen.findByText('ALLOC-21')).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions' && request.searchParams.get('view') === 'items' && request.searchParams.get('page') === '2' && request.searchParams.get('page_size') === '20';
    })).toBe(true));

    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: 'Run FIFO Allocation' }));
    await waitFor(() => {
      const refreshes = fetch.mock.calls.filter(([url]) => new URL(String(url), window.location.href).pathname === '/api/allocations/exceptions');
      expect(refreshes.length).toBeGreaterThan(0);
      expect(refreshes.every(([url]) => new URL(String(url)).searchParams.get('view') === 'items' && new URL(String(url)).searchParams.get('page') === '2')).toBe(true);
    });

    fetch.mockClear();
    await user.click(screen.getByRole('tab', { name: /Orders/ }));
    expect(await screen.findByText('Showing 1–20 of 21 allocation lines')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions' && request.searchParams.get('view') === 'orders' && request.searchParams.get('page') === '1';
    })).toBe(true);
    await user.click(screen.getByRole('tab', { name: /Items/ }));
    expect(await screen.findByText('Showing 1–20 of 21 item shortages')).toBeInTheDocument();

    fetch.mockClear();
    const searchInput = screen.getByRole('textbox', { name: 'Item, order, SKU or barcode' });
    await user.clear(searchInput);
    await user.type(searchInput, 'ALLOC-01');
    await user.click(screen.getByRole('button', { name: 'Filter' }));
    expect(await screen.findByText('Showing 1–1 of 1 item shortages')).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions' && request.searchParams.get('search') === 'ALLOC-01' && request.searchParams.get('page') === '1';
    })).toBe(true));

    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    fetch.mockClear();
    await user.click(screen.getByRole('button', { name: 'Export Results' }));
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions/export'
        && request.searchParams.get('search') === 'ALLOC-01'
        && !request.searchParams.has('page')
        && !request.searchParams.has('page_size');
    })).toBe(true));
  });

  it('loads every affected order through the bounded item-group drill-down', async () => {
    const user = userEvent.setup();
    mockAllocationExceptionsFeed = pagedAllocationExceptionsFeed(Array.from({ length: 21 }, (_, index) => ({
        ...mockAllocationException,
        order_id: 702 + index,
        order_line_id: 9002 + index,
        woo_order_id: 803 + index,
        woo_order_number: String(803 + index).padStart(4, '0'),
        customer_name: `Customer ${index + 1}`,
      })));
    window.location.hash = '#/orders/allocate';
    render(<App />);

    expect(await screen.findByText('Showing 1–1 of 1 item shortages')).toBeInTheDocument();
    const itemTable = screen.getByText('SMOKE-001').closest('table');
    expect(within(screen.getByText('SMOKE-001').closest('tr')).getAllByRole('cell')[3]).toHaveTextContent('21');
    fetch.mockClear();
    await user.click(within(itemTable).getByRole('button', { name: 'Open allocation actions for SMOKE-001' }));
    await user.click(screen.getByRole('menuitem', { name: 'View affected orders' }));

    expect(await screen.findByText('Showing affected orders for one item.')).toBeInTheDocument();
    expect(screen.getByText('0803')).toBeInTheDocument();
    expect(screen.queryByText('0823')).not.toBeInTheDocument();
    expect(screen.queryByText('Showing 1–1 of 1 item shortages')).not.toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions'
        && request.searchParams.get('view') === 'orders'
        && request.searchParams.get('item_id') === '1'
        && request.searchParams.get('page_size') === '20';
    })).toBe(true));

    await user.click(screen.getByRole('button', { name: 'Next allocation lines page' }));
    expect(await screen.findByText('0823')).toBeInTheDocument();
    expect(screen.getByText('Showing 21–21 of 21 allocation lines')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show all orders' }));
    expect(await screen.findByText('Showing 1–20 of 21 allocation lines')).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => {
      const request = new URL(String(url));
      return request.pathname === '/api/allocations/exceptions' && request.searchParams.get('view') === 'orders' && request.searchParams.get('page') === '1';
    })).toBe(true));
  });

  it('disables allocation actions and aborts the page request when leaving Allocate', async () => {
    let requestSignal;
    fetch.mockImplementation((url, options = {}) => {
      const request = new URL(String(url));
      if (request.pathname === '/api/allocations/exceptions') {
        requestSignal = options.signal;
        return new Promise((resolve, reject) => {
          options.signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), { once: true });
        });
      }
      return mockFetch(url, options);
    });
    window.location.hash = '#/orders/allocate';
    render(<App />);

    await waitFor(() => expect(requestSignal).toBeTruthy());
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Run FIFO Allocation' })).toBeDisabled();
    expect(screen.getByRole('textbox', { name: 'Item, order, SKU or barcode' })).toBeDisabled();

    act(() => { window.location.hash = '#/orders/pick'; });
    await screen.findByRole('heading', { name: 'Pick Orders', level: 1 });
    expect(requestSignal.aborted).toBe(true);
  });

  it('adds an idempotency key to the inventory stock adjustment modal', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    fetch.mockImplementation((url) => {
      if (String(url).includes('/api/inventory/locations')) {
        return json({
          rows: [{
            id: 91,
            item_id: 1,
            sku: 'SMOKE-001',
            barcode: 'SMOKE001',
            description: 'Smoke Test Item',
            warehouse: 'Main Warehouse',
            inventory_location: 'Smoke Rack',
            in_stock: 9,
            allocated: 2,
            sellable: 7,
          }],
        });
      }
      return mockFetch(url);
    });
    window.location.hash = '#/inventory/all';
    render(<App />);

    await screen.findByText('Smoke Test Item');
    const inventoryTable = screen.getByText('SMOKE-001').closest('table');
    await user.click(within(inventoryTable).getByRole('button', { name: 'Open inventory actions' }));
    const inventoryMenu = screen.getByRole('menu');
    expect(inventoryMenu).toHaveClass('floating-menu');
    expect(inventoryMenu.parentElement).toBe(document.body);
    await user.click(screen.getByRole('menuitem', { name: 'Edit Current Stock' }));
    const dialog = await screen.findByRole('dialog', { name: 'Edit current stock' });
    expect(dialog.closest('.app-overlay-root')?.parentElement).toBe(document.body);
    const newQuantity = within(dialog).getByRole('spinbutton', { name: 'New Stock Quantity' });
    await user.clear(newQuantity);
    await user.type(newQuantity, '10');
    await user.type(within(dialog).getByPlaceholderText('Required'), 'Physical count correction');
    await user.click(within(dialog).getByRole('button', { name: 'Commit Adjustment' }));

    await waitFor(() => {
      const commitCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/inventory/adjustments'));
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ idempotency_key: expect.any(String) });
    });
    confirmSpy.mockRestore();
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
        idempotency_key: expect.any(String),
      });
    });
    await waitFor(() => {
      const commitIndex = fetch.mock.calls.findIndex(([url]) => String(url).includes('/api/picks/commit'));
      const pickRefreshes = fetch.mock.calls.slice(commitIndex + 1).filter(([url]) => new URL(String(url)).pathname === '/api/orders/pick');
      expect(pickRefreshes).toHaveLength(1);
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
      expect(JSON.parse(commitCall[1].body)).toMatchObject({ order_ids: [701], allow_partial: false, idempotency_key: expect.any(String) });
    });
    confirmSpy.mockRestore();
  });

  it('selects Open Orders and exposes complete, print, and unpick-all bulk actions', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const printSpy = vi.spyOn(window, 'print').mockImplementation(() => {});
    window.location.hash = '#/orders/open';
    render(<App />);

    await user.click(await screen.findByRole('checkbox', { name: 'Select all open orders' }));
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    expect(screen.getByRole('menuitem', { name: 'Mark as completed' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Print' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Unpick all' })).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Print' }));
    await waitFor(() => expect(printSpy).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('Selected customer invoices').parentElement).toBe(document.body);
    expect(document.body).not.toHaveClass('bulk-order-printing');

    await user.click(screen.getByRole('button', { name: 'Actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Mark as completed' }));
    await waitFor(() => {
      const bulkCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/orders/bulk/complete'));
      expect(JSON.parse(bulkCall[1].body)).toMatchObject({ order_ids: [701] });
    });
    printSpy.mockRestore();
    confirmSpy.mockRestore();
  });

  it('adds an idempotency key to bulk unpick requests', async () => {
    const user = userEvent.setup();
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    window.location.hash = '#/orders/open';
    render(<App />);

    await user.click(await screen.findByRole('checkbox', { name: 'Select order 0802' }));
    await user.click(screen.getByRole('button', { name: 'Actions' }));
    await user.click(screen.getByRole('menuitem', { name: 'Unpick all' }));

    await waitFor(() => {
      const unpickCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/orders/bulk/unpick'));
      expect(JSON.parse(unpickCall[1].body)).toMatchObject({
        order_ids: [701],
        idempotency_key: expect.any(String),
      });
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
