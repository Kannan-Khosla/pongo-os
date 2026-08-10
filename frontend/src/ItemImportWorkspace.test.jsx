import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { ItemImportHistory, ItemImportWorkspace } from './ItemImportWorkspace';

const schema = {
  schema_version: 'test.1',
  max_file_bytes: 10485760,
  outcomes: [
    {
      key: 'add_items', label: 'Add new items', description: 'Create products.', changes: 'Creates item records.', does_not_change: 'Inventory quantities and stock history will not change.', required_fields: ['sku'],
      fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['add_items'] }, { key: 'product_name', label: 'Product name', type: 'text', required_for: [] }],
    },
    {
      key: 'update_items', label: 'Update item details', description: 'Update products.', changes: 'Updates approved metadata.', does_not_change: 'On hand, allocated, available, and stock history will not change.', required_fields: ['sku'],
      fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['update_items'] }],
    },
    {
      key: 'update_stock', label: 'Override stock levels', description: 'Set exact stock.', changes: 'Creates one audited stock adjustment.', does_not_change: 'Allocated and sellable remain system-managed.', required_fields: ['sku', 'warehouse', 'inventory_location', 'stock_quantity'],
      fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['update_stock'] }, { key: 'warehouse', label: 'Warehouse', type: 'text', required_for: ['update_stock'] }, { key: 'inventory_location', label: 'Inventory location', type: 'text', required_for: ['update_stock'] }, { key: 'stock_quantity', label: 'In stock', type: 'decimal', required_for: ['update_stock'] }],
    },
    {
      key: 'starting_inventory', label: 'Set starting inventory', description: 'Record onboarding stock.', changes: 'Creates audited starting-inventory movements.', does_not_change: 'Existing operational inventory is never overwritten.', required_fields: ['sku', 'starting_quantity', 'starting_warehouse', 'starting_location'],
      fields: [{ key: 'sku', label: 'SKU', type: 'text', required_for: ['starting_inventory'] }, { key: 'starting_quantity', label: 'Starting quantity', type: 'decimal', required_for: ['starting_inventory'] }, { key: 'starting_warehouse', label: 'Warehouse', type: 'text', required_for: ['starting_inventory'] }, { key: 'starting_location', label: 'Inventory location', type: 'text', required_for: ['starting_inventory'] }],
    },
  ],
};

function response(body, { ok = true, status = 200 } = {}) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) });
}

function preview(summary) {
  return {
    preview_id: 'preview-qa', outcome: 'add_items', outcome_content: schema.outcomes[0],
    file: { name: 'items.csv', size: 30, row_count: 1, header_count: 2 }, status: 'ready',
    source_columns: [{ source: 'SKU', destination: 'sku', confidence: 'exact', samples: ['DUP'] }, { source: 'Product name', destination: 'product_name', confidence: 'exact', samples: ['Food'] }],
    mapping: { SKU: 'sku', 'Product name': 'product_name' }, options: { allow_blank_clears: false }, summary,
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
  window.location.hash = '';
});

it('offers an audited stock override with a current-stock export', async () => {
  const user = userEvent.setup();
  vi.stubGlobal('fetch', vi.fn((url) => String(url).endsWith('/schema') ? response(schema) : response({})));
  render(<ItemImportWorkspace />);

  await user.click(await screen.findByRole('button', { name: /Override stock levels/i }));
  await user.click(screen.getByRole('button', { name: /^Continue/i }));

  expect(screen.getByRole('heading', { name: 'Upload your CSV' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /Download template/i })).toHaveAttribute('href', expect.stringContaining('/templates/update_stock'));
  expect(screen.getByRole('link', { name: /Export editable current stock/i })).toHaveAttribute('href', expect.stringContaining('/templates/update_stock?include_existing=true'));
});

it('keeps a rejected upload in the upload step with a human-readable error', async () => {
  const user = userEvent.setup();
  vi.stubGlobal('fetch', vi.fn((url, init = {}) => {
    if (String(url).endsWith('/schema')) return response(schema);
    if (String(url).endsWith('/previews') && init.method === 'POST') return response({ detail: { code: 'invalid_encoding', message: 'CSV files must use UTF-8 encoding.' } }, { ok: false, status: 400 });
    return response({});
  }));
  render(<ItemImportWorkspace />);

  await user.click(await screen.findByRole('button', { name: /Add new items/i }));
  await user.click(screen.getByRole('button', { name: /^Continue/i }));
  await user.upload(document.querySelector('.import-dropzone input'), new File(['bad'], 'items.csv', { type: 'text/csv' }));
  await user.click(screen.getByRole('button', { name: /Upload and match columns/i }));

  expect(await screen.findByRole('alert')).toHaveTextContent('CSV files must use UTF-8 encoding.');
  expect(screen.getByRole('heading', { name: 'Upload your CSV' })).toBeInTheDocument();
});

it('fixes a duplicate row inline and carries the corrected diff into confirmation', async () => {
  const user = userEvent.setup();
  let corrected = false;
  const duplicateSummary = { total_rows: 1, ready_count: 0, create_count: 0, update_count: 0, no_changes_count: 0, needs_attention_count: 0, duplicate_count: 1, unmatched_count: 0, blocked_count: 0, excluded_count: 0 };
  const readySummary = { ...duplicateSummary, ready_count: 1, create_count: 1, duplicate_count: 0 };
  const duplicateRow = { id: 1, row_number: 2, sku: 'DUP', barcode: null, product_name: 'Food', normalized_data: { sku: 'DUP', product_name: 'Food' }, proposed_changes: {}, issues: [{ code: 'duplicate_sku_in_file', message: 'SKU DUP appears more than once.', suggested_action: 'Enter a unique SKU.' }], state: 'duplicate', excluded: false };
  const readyRow = { ...duplicateRow, sku: 'UNIQUE', normalized_data: { sku: 'UNIQUE', product_name: 'Food' }, proposed_changes: { sku: { field: 'sku', label: 'SKU', before: null, after: 'UNIQUE' } }, issues: [], state: 'will_create' };
  vi.stubGlobal('fetch', vi.fn((url, init = {}) => {
    const target = String(url);
    if (target.endsWith('/schema')) return response(schema);
    if (target.endsWith('/previews') && init.method === 'POST') return response(preview(duplicateSummary));
    if (target.endsWith('/mapping') && init.method === 'PATCH') return response(preview(duplicateSummary));
    if (target.includes('/rows/2') && init.method === 'PATCH') { corrected = true; return response(readyRow); }
    if (target.includes('/rows?')) return response({ rows: [corrected ? readyRow : duplicateRow], total: 1, page: 1, page_size: 50, total_pages: 1 });
    if (target.endsWith('/preview-qa')) return response(preview(corrected ? readySummary : duplicateSummary));
    return response({});
  }));
  render(<ItemImportWorkspace />);

  await user.click(await screen.findByRole('button', { name: /Add new items/i }));
  await user.click(screen.getByRole('button', { name: /^Continue/i }));
  await user.upload(document.querySelector('.import-dropzone input'), new File(['SKU,Product name\nDUP,Food'], 'items.csv', { type: 'text/csv' }));
  await user.click(screen.getByRole('button', { name: /Upload and match columns/i }));
  await user.click(await screen.findByRole('button', { name: /Validate rows/i }));
  const reviewTable = await screen.findByRole('table');
  await user.click(within(reviewTable).getByRole('button', { name: 'Edit row 2' }));
  let drawer = screen.getByRole('dialog', { name: 'Fix item data' });
  await waitFor(() => expect(within(drawer).getByRole('textbox', { name: 'SKU' })).toHaveFocus());
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog', { name: 'Fix item data' })).not.toBeInTheDocument();
  expect(within(reviewTable).getByRole('button', { name: 'Edit row 2' })).toHaveFocus();
  await user.click(within(reviewTable).getByRole('button', { name: 'Edit row 2' }));
  drawer = screen.getByRole('dialog', { name: 'Fix item data' });
  await user.clear(within(drawer).getByRole('textbox', { name: 'SKU' }));
  await user.type(within(drawer).getByRole('textbox', { name: 'SKU' }), 'UNIQUE');
  await user.click(within(drawer).getByRole('button', { name: 'Save and revalidate' }));

  await waitFor(() => expect(screen.getAllByText('Will create').length).toBeGreaterThan(0));
  await user.click(screen.getByRole('button', { name: /Review import/i }));
  expect(await screen.findByRole('heading', { name: 'Review changes before import' })).toBeInTheDocument();
  expect(screen.getAllByRole('cell', { name: 'UNIQUE' }).length).toBeGreaterThan(0);
});

it('reconciles excluded rows in the completed import totals', async () => {
  const completed = {
    ...preview({}),
    status: 'committed',
    result: { status: 'completed', import_job_id: 9, created_count: 2, updated_count: 0, unchanged_count: 0, excluded_count: 1, failed_count: 0, duration_ms: 24, starting_units: 0 },
  };
  vi.stubGlobal('fetch', vi.fn((url) => String(url).endsWith('/schema') ? response(schema) : response(completed)));

  render(<ItemImportWorkspace initialPreviewId="preview-qa" />);

  expect(await screen.findByRole('heading', { name: 'Import completed' })).toBeInTheDocument();
  expect(screen.getByText('Excluded').nextElementSibling).toHaveTextContent('1');
});

it('makes every confirmation row reachable instead of showing a capped sample', async () => {
  const user = userEvent.setup();
  const rows = Array.from({ length: 26 }, (_, index) => ({
    id: index + 1,
    row_number: index + 2,
    sku: `SKU-${String(index + 1).padStart(2, '0')}`,
    barcode: null,
    product_name: `Product ${index + 1}`,
    proposed_changes: { brand: { field: 'brand', label: 'Brand', before: 'Old', after: 'New' } },
    issues: [],
    state: 'will_update',
    excluded: false,
  }));
  const savedPreview = preview({ total_rows: 26, ready_count: 26, create_count: 0, update_count: 26, no_changes_count: 0, needs_attention_count: 0, duplicate_count: 0, unmatched_count: 0, blocked_count: 0, excluded_count: 0 });
  vi.stubGlobal('fetch', vi.fn((url) => {
    const target = String(url);
    if (target.endsWith('/schema')) return response(schema);
    if (target.includes('/rows?')) {
      const request = new URL(target);
      const page = Number(request.searchParams.get('page') || 1);
      const pageSize = Number(request.searchParams.get('page_size') || 50);
      const pageRows = rows.slice((page - 1) * pageSize, page * pageSize);
      return response({ rows: pageRows, total: rows.length, page, page_size: pageSize, total_pages: Math.ceil(rows.length / pageSize) });
    }
    if (target.endsWith('/preview-qa')) return response(savedPreview);
    return response({});
  }));

  render(<ItemImportWorkspace initialPreviewId="preview-qa" />);

  await user.click(await screen.findByRole('button', { name: /Review import/i }));
  expect(await screen.findByRole('heading', { name: 'Review changes before import' })).toBeInTheDocument();
  expect(screen.getByText('SKU-25')).toBeInTheDocument();
  expect(screen.queryByText('SKU-26')).not.toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next' }));
  expect(await screen.findByText('SKU-26')).toBeInTheDocument();
  expect(screen.getByText('Page 2 of 2')).toBeInTheDocument();
});

it('labels completed import jobs as completed in history', async () => {
  const user = userEvent.setup();
  sessionStorage.setItem('pongo.item-import.preview', 'completed-preview');
  vi.stubGlobal('fetch', vi.fn(() => response({
    jobs: [{
      id: 9, outcome: 'add_items', status: 'completed', file_name: 'items.csv', successful_rows: 2, failed_rows: 0, created_by: 'qa@example.com', created_at: '2026-08-06T12:00:00Z',
    }],
    total: 1, page: 1, page_size: 50, total_pages: 1, has_previous: false, has_next: false,
  })));

  render(<ItemImportHistory />);

  expect(within(await screen.findByRole('cell', { name: 'Completed' })).getByText('Completed')).toHaveClass('import-status-completed');
  expect(screen.queryByText('Will update')).not.toBeInTheDocument();
  await user.click(screen.getByRole('link', { name: 'New import' }));
  expect(sessionStorage.getItem('pongo.item-import.preview')).toBeNull();
});

it('notifies the item collection after a metadata import rollback', async () => {
  const user = userEvent.setup();
  const onRolledBack = vi.fn();
  const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  const job = {
    id: 12,
    outcome: 'update_items',
    status: 'completed',
    file_name: 'metadata.csv',
    successful_rows: 1,
    failed_rows: 0,
    created_by: 'qa@example.com',
    created_at: '2026-08-06T12:00:00Z',
  };
  vi.stubGlobal('fetch', vi.fn((url, init = {}) => {
    const target = String(url);
    if (target.endsWith('/rollback') && init.method === 'POST') return response({ status: 'completed' });
    if (target.includes('/changes?')) return response({ changes: [], total: 0, page: 1, page_size: 50, total_pages: 0, has_previous: false, has_next: false });
    return response({ jobs: [job], total: 1, page: 1, page_size: 50, total_pages: 1, has_previous: false, has_next: false });
  }));

  render(<ItemImportHistory onRolledBack={onRolledBack} />);

  await screen.findByRole('cell', { name: 'metadata.csv' });
  await user.click(document.querySelector('.history-expand'));
  await user.click(await screen.findByRole('button', { name: /Safe metadata rollback/i }));

  await waitFor(() => expect(onRolledBack).toHaveBeenCalledTimes(1));
  confirmSpy.mockRestore();
});

it('pages import jobs and field changes without hiding older records', async () => {
  const user = userEvent.setup();
  const fetchMock = vi.fn((url) => {
    const target = String(url);
    if (target.includes('/api/import-jobs/22/changes?page=2')) {
      return response({ changes: [{ id: 202, item_id: 2, sku: 'SECOND', field: 'brand', before: 'Old', after: 'New', created_by: 'qa', created_at: '2026-08-06T12:00:00Z' }], total: 51, page: 2, page_size: 50, total_pages: 2, has_previous: true, has_next: false });
    }
    if (target.includes('/api/import-jobs/22/changes?')) {
      return response({ changes: [{ id: 201, item_id: 1, sku: 'FIRST', field: 'brand', before: 'A', after: 'B', created_by: 'qa', created_at: '2026-08-06T12:00:00Z' }], total: 51, page: 1, page_size: 50, total_pages: 2, has_previous: false, has_next: true });
    }
    if (target.includes('page=2')) {
      return response({ jobs: [{ id: 21, outcome: 'add_items', status: 'completed', file_name: 'older.csv', successful_rows: 1, failed_rows: 0, created_by: 'qa', created_at: '2026-08-05T12:00:00Z' }], total: 51, page: 2, page_size: 50, total_pages: 2, has_previous: true, has_next: false });
    }
    return response({ jobs: [{ id: 22, outcome: 'update_items', status: 'completed', file_name: 'latest.csv', successful_rows: 1, failed_rows: 0, created_by: 'qa', created_at: '2026-08-06T12:00:00Z' }], total: 51, page: 1, page_size: 50, total_pages: 2, has_previous: false, has_next: true });
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<ItemImportHistory />);

  await screen.findByRole('cell', { name: 'latest.csv' });
  expect(fetchMock.mock.calls[0][0]).toContain('page=1');
  expect(fetchMock.mock.calls[0][0]).toContain('page_size=50');
  await user.click(document.querySelector('.history-expand'));
  expect(await screen.findByText('FIRST · brand')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next changes' }));
  expect(await screen.findByText('SECOND · brand')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Next imports' }));
  expect(await screen.findByRole('cell', { name: 'older.csv' })).toBeInTheDocument();
});
