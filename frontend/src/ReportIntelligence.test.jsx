import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ReportIntelligencePage from './ReportIntelligence.jsx';

const report = {
  key: 'inventory-cost-sku',
  short_title: 'Cost by SKU',
  title: 'Current Cost of Inventory by SKU',
  description: 'Verified inventory value by item.',
  category: 'inventory',
  date_mode: 'none',
  filters: ['sku'],
  formats: ['csv', 'pdf'],
};

const run = {
  run_id: 7,
  row_count: 1,
  generated_at: '2026-08-05T18:00:00Z',
  kpis: [],
  charts: [],
  insights: [],
  columns: [{ key: 'sku', label: 'SKU', type: 'text' }],
  rows: [{ sku: 'SMOKE-001' }],
  definitions: [],
  data_quality: [],
  definition_version: 1,
  data_hash: 'abc123',
};

const scopedReport = {
  ...report,
  key: 'inventory-export',
  title: 'Inventory Export',
  date_mode: 'snapshot',
  filters: ['warehouse', 'inventory_location', 'brand', 'category', 'sku'],
  formats: ['csv', 'google_sheets', 'email'],
};

function response(body, { ok = true, status = 200 } = {}) {
  return Promise.resolve({ ok, status, json: () => Promise.resolve(body) });
}

describe('Report Intelligence performance flow', () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('loads the latest snapshot without generating a report on mount', async () => {
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [report] });
      if (target.includes('/api/reports/jobs/latest/')) return response({}, { ok: false, status: 404 });
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={report.key} />);

    expect(await screen.findByRole('heading', { name: report.title })).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).includes('/api/reports/jobs/latest/'))).toBe(true));
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith(`/api/reports/jobs/${report.key}`))).toBe(false);
  });

  it('prefills the sole warehouse and renders catalog-backed scope dropdowns', async () => {
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [scopedReport] });
      if (target.includes('/api/items?')) return response({ facets: { brands: ['Acana', 'Weruva'], categories: ['Cats', 'Dogs'] } });
      if (target.includes('/api/locations?')) {
        return response({
          locations: [
            { id: 1, warehouse: 'Main Warehouse', code: 'A-01', name: 'Aisle 1', isActive: true },
            { id: 2, warehouse: 'Main Warehouse', code: 'B-01', name: 'Aisle 2', isActive: true },
          ],
        });
      }
      if (target.includes('/api/reports/jobs/latest/')) return response({}, { ok: false, status: 404 });
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={scopedReport.key} />);

    expect(await screen.findByRole('heading', { name: scopedReport.title })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText('Warehouse')).toHaveValue('Main Warehouse'));
    expect(screen.getByLabelText('Location')).toHaveValue('');
    expect(screen.getByLabelText('Brand')).toHaveTextContent('All brands');
    expect(screen.getByLabelText('Category')).toHaveValue('');
    expect(screen.getByLabelText('SKU')).toHaveAttribute('placeholder', 'Exact or partial SKU');
    expect(screen.getByRole('option', { name: 'All locations' })).toBeInTheDocument();
    expect(screen.getByText('All brands')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'All categories' })).toBeInTheDocument();
    await waitFor(() => {
      const latestCall = fetch.mock.calls.find(([url]) => String(url).includes('/api/reports/jobs/latest/'));
      expect(JSON.parse(latestCall[1].body).filters).toEqual({ warehouse: 'Main Warehouse' });
    });
  });

  it('creates and opens a Google Sheet directly from a ready report', async () => {
    const user = userEvent.setup();
    const replace = vi.fn();
    vi.spyOn(window, 'open').mockReturnValue({ opener: null, location: { replace }, close: vi.fn() });
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [scopedReport], google_sheets_configured: true });
      if (target.includes('/api/reports/jobs/latest/')) return response({ ...run, filters: {}, run_id: 77 });
      if (target.endsWith('/api/reports/runs/77/google-sheets')) return response({ url: 'https://docs.google.com/spreadsheets/d/pongo-report' });
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={scopedReport.key} />);

    await user.click(await screen.findByRole('button', { name: 'Create and open Sheet' }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith('https://docs.google.com/spreadsheets/d/pongo-report'));
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/api/reports/runs/77/google-sheets'))).toBe(true);
  });

  it('links directly to Google sign-in when report sharing is not connected', async () => {
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [scopedReport], google_sheets_configured: false });
      if (target.includes('/api/reports/jobs/latest/')) return response(run);
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={scopedReport.key} />);

    const signIn = await screen.findByRole('link', { name: 'Sign in with Google' });
    expect(signIn).toHaveAttribute('href', '#/settings/google-sheets');
    expect(screen.getByRole('button', { name: 'Create and open Sheet' })).toBeDisabled();
  });

  it('queues generation and shows the previous verified run while polling', async () => {
    const user = userEvent.setup();
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [report] });
      if (target.includes('/api/reports/jobs/latest/')) return response({}, { ok: false, status: 404 });
      if (target.endsWith(`/api/reports/jobs/${report.key}`)) return response({ job_id: 91, report_key: report.key, status: 'queued', progress: 0, previous_run_id: 7 }, { status: 202 });
      if (target.endsWith('/api/reports/jobs/91')) return response({ job_id: 91, report_key: report.key, status: 'completed', progress: 100, run_id: 8 });
      if (target.includes('/api/reports/runs/7?')) return response(run);
      if (target.includes('/api/reports/runs/8?')) return response({ ...run, run_id: 8, generated_at: '2026-08-05T18:01:00Z' });
      return response({});
    }));
    render(<ReportIntelligencePage apiBaseUrl="" reportKey={report.key} />);
    await screen.findByRole('heading', { name: report.title });

    await user.click(screen.getByRole('button', { name: /Generate verified report/i }));

    expect(await screen.findByText('SMOKE-001')).toBeInTheDocument();
    expect(screen.getByText(/Showing the previous verified run/)).toBeInTheDocument();
    await waitFor(() => expect(fetch.mock.calls.some(([url]) => String(url).endsWith('/api/reports/jobs/91'))).toBe(true), { timeout: 3000 });
    await waitFor(() => expect(screen.queryByText(/Showing the previous verified run/)).not.toBeInTheDocument());
    expect(fetch.mock.calls.some(([url]) => String(url).includes(`/api/reports/runs/${report.key}?`))).toBe(false);
  });

  it('clears a report from a different filter scope before exposing exports', async () => {
    const user = userEvent.setup();
    const previous = { ...run, filters: { sku: 'OLD' }, rows: [{ sku: 'OLD' }] };
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [report] });
      if (target.includes('/api/reports/jobs/latest/')) return response(previous);
      if (target.endsWith(`/api/reports/jobs/${report.key}`)) return response({ job_id: 92, report_key: report.key, status: 'queued', progress: 0, previous_run_id: null }, { status: 202 });
      if (target.endsWith('/api/reports/jobs/92')) return response({ job_id: 92, report_key: report.key, status: 'queued', progress: 10 });
      return response({});
    }));
    render(<ReportIntelligencePage apiBaseUrl="" reportKey={report.key} />);

    expect(await screen.findByText('OLD')).toBeInTheDocument();
    await user.clear(screen.getByLabelText('SKU'));
    await user.type(screen.getByLabelText('SKU'), 'NEW');
    await user.click(screen.getByRole('button', { name: /Generate verified report/i }));

    await waitFor(() => expect(screen.queryByText('OLD')).not.toBeInTheDocument());
    expect(screen.queryByRole('link', { name: /Download CSV/i })).not.toBeInTheDocument();
  });

  it('retries a transient progress error and continues to the completed run', async () => {
    let statusAttempts = 0;
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [report] });
      if (target.includes('/api/reports/jobs/latest/')) return response({}, { ok: false, status: 404 });
      if (target.endsWith(`/api/reports/jobs/${report.key}`)) return response({ job_id: 93, report_key: report.key, status: 'queued', progress: 0, previous_run_id: null }, { status: 202 });
      if (target.endsWith('/api/reports/jobs/93')) {
        statusAttempts += 1;
        if (statusAttempts === 1) return Promise.reject(new Error('temporary network error'));
        return response({ job_id: 93, report_key: report.key, status: 'completed', progress: 100, run_id: 9 });
      }
      if (target.includes('/api/reports/runs/9?')) return response({ ...run, run_id: 9 });
      return response({});
    }));
    render(<ReportIntelligencePage apiBaseUrl="" reportKey={report.key} />);
    expect(await screen.findByRole('heading', { name: report.title })).toBeInTheDocument();
    const generateButton = screen.getByRole('button', { name: /Generate verified report/i });
    await waitFor(() => expect(generateButton).toBeEnabled());
    vi.useFakeTimers();

    fireEvent.click(generateButton);
    await act(async () => Promise.resolve());
    await act(async () => vi.advanceTimersByTimeAsync(1500));
    expect(screen.queryByText('temporary network error')).not.toBeInTheDocument();
    await act(async () => vi.advanceTimersByTimeAsync(3000));
    await act(async () => Promise.resolve());

    expect(screen.getByText('SMOKE-001')).toBeInTheDocument();
    expect(statusAttempts).toBe(2);
  });

  it('pages a large immutable report preview on the server and reaches rows after 100', async () => {
    const user = userEvent.setup();
    const pageBody = (page) => {
      const start = ((page - 1) * 50) + 1;
      const end = Math.min(125, start + 49);
      const rows = Array.from(
        { length: Math.max(0, end - start + 1) },
        (_, index) => ({ sku: `SKU-${String(start + index).padStart(3, '0')}` }),
      );
      return {
        ...run,
        run_id: 125,
        row_count: 125,
        rows,
        row_pagination: {
          page,
          page_size: 50,
          total: 125,
          total_pages: 3,
          returned_count: rows.length,
          has_previous: page > 1,
          has_next: page < 3,
        },
      };
    };
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [report] });
      if (target.includes('/api/reports/jobs/latest/')) return response(pageBody(1));
      if (target.includes('/api/reports/runs/125?')) {
        const page = Number(new URL(target, 'http://localhost').searchParams.get('row_page'));
        return response(pageBody(page));
      }
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={report.key} />);

    expect(await screen.findByText('SKU-001')).toBeInTheDocument();
    expect(screen.getByText('Showing 1–50 of 125 records')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next report page' }));
    expect(await screen.findByText('SKU-051')).toBeInTheDocument();
    expect(screen.getByText('Showing 51–100 of 125 records')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Next report page' }));
    expect(await screen.findByText('SKU-101')).toBeInTheDocument();
    expect(screen.getByText('Showing 101–125 of 125 records')).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).includes('row_page=3&row_page_size=50'))).toBe(true);
  });

  it('visibly highlights subscription products in the sales report', async () => {
    const salesReport = { ...report, key: 'sales-by-sku', title: 'Sales by SKU' };
    const salesRun = {
      ...run,
      columns: [
        { key: 'name', label: 'Item', type: 'text' },
        { key: 'subscription_status', label: 'Subscription', type: 'text' },
      ],
      rows: [
        { name: 'Renewal Food', subscription_status: 'Active', is_subscription_product: true },
        { name: 'Regular Food', subscription_status: 'Not active', is_subscription_product: false },
      ],
    };
    vi.stubGlobal('fetch', vi.fn((url) => {
      const target = String(url);
      if (target.endsWith('/api/reports')) return response({ reports: [salesReport] });
      if (target.includes('/api/reports/jobs/latest/')) return response(salesRun);
      return response({});
    }));

    render(<ReportIntelligencePage apiBaseUrl="" reportKey={salesReport.key} />);

    expect(await screen.findByText('Renewal Food')).toBeInTheDocument();
    expect(screen.getByText('Subscription', { selector: '.ri-subscription-badge' })).toBeInTheDocument();
    expect(screen.getByText('Renewal Food').closest('tr')).toHaveClass('ri-subscription-row');
    expect(screen.getByText('Regular Food').closest('tr')).not.toHaveClass('ri-subscription-row');
  });
});
