import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarRange,
  Check,
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileSpreadsheet,
  LoaderCircle,
  Mail,
  RefreshCw,
  Send,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import * as echarts from 'echarts/core';
import { BarChart, LineChart } from 'echarts/charts';
import {
  AriaComponent,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { apiFetch } from './api';
import DocumentActions from './DocumentActions';
import MultiSelectFilter from './MultiSelectFilter';

echarts.use([
  AriaComponent,
  BarChart,
  CanvasRenderer,
  DataZoomComponent,
  GridComponent,
  LegendComponent,
  LineChart,
  TooltipComponent,
]);

const CATEGORY_ORDER = ['executive', 'inventory', 'orders', 'operations', 'intelligence'];
const CATEGORY_LABELS = {
  executive: 'Executive',
  inventory: 'Inventory',
  orders: 'Orders',
  operations: 'Operations',
  intelligence: 'Intelligence',
};
const FILTER_LABELS = {
  start_date: 'Start date',
  end_date: 'End date',
  warehouse: 'Warehouse',
  inventory_location: 'Location',
  brand: 'Brand',
  category: 'Category',
  sku: 'SKU',
  status: 'Order status',
  customer_email: 'Customer email',
};
const ALL_OPTION_LABELS = {
  warehouse: 'All warehouses',
  inventory_location: 'All locations',
  brand: 'All brands',
  category: 'All categories',
  status: 'All order statuses',
};
const EMPTY_SCOPE_OPTIONS = { warehouses: [], locations: [], brands: [], categories: [] };
const REPORT_PREVIEW_PAGE_SIZE = 50;
const REPORT_PREVIEW_PAGE_SIZES = [20, 50, 100];
const ORDER_STATUS_OPTIONS = [
  ['open', 'Open'],
  ['processing', 'Processing'],
  ['on-hold', 'On hold'],
  ['pending', 'Pending'],
  ['partially_allocated', 'Partially allocated'],
  ['allocated', 'Allocated'],
  ['picked', 'Picked'],
  ['partially_fulfilled', 'Partially fulfilled'],
  ['fulfilled', 'Fulfilled'],
  ['completed', 'Completed'],
  ['cancelled', 'Cancelled'],
  ['failed', 'Failed'],
  ['refunded', 'Refunded'],
];

function localIsoDate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function defaultFilters(report, scopeOptions = EMPTY_SCOPE_OPTIONS) {
  const defaults = {};
  if (report?.date_mode === 'range') {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (report.key === 'executive-weekly' ? 6 : 29));
    defaults.start_date = localIsoDate(start);
    defaults.end_date = localIsoDate(end);
  }
  if (report?.filters?.includes('warehouse') && scopeOptions.warehouses.length === 1) {
    [defaults.warehouse] = scopeOptions.warehouses;
  }
  return defaults;
}

function uniqueSorted(values) {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))]
    .sort((left, right) => left.localeCompare(right, 'en-CA', { sensitivity: 'base' }));
}

function buildScopeOptions(itemBody, locationBody) {
  const locations = (locationBody?.locations || []).filter((location) => location?.isActive !== false);
  return {
    warehouses: uniqueSorted(locations.map((location) => location.warehouse)),
    locations,
    brands: uniqueSorted(itemBody?.facets?.brands || []),
    categories: uniqueSorted(itemBody?.facets?.categories || []),
  };
}

function reportPreviewPagination(run) {
  const rows = Array.isArray(run?.rows) ? run.rows : [];
  const total = Math.max(0, Number(run?.row_pagination?.total ?? run?.row_count ?? rows.length) || 0);
  const pageSize = Math.max(1, Number(run?.row_pagination?.page_size ?? REPORT_PREVIEW_PAGE_SIZE) || REPORT_PREVIEW_PAGE_SIZE);
  const totalPages = total ? Math.max(1, Number(run?.row_pagination?.total_pages) || Math.ceil(total / pageSize)) : 0;
  const page = totalPages ? Math.min(totalPages, Math.max(1, Number(run?.row_pagination?.page) || 1)) : 1;
  const returnedCount = Math.max(0, Number(run?.row_pagination?.returned_count ?? rows.length) || 0);
  const rangeStart = total && returnedCount ? ((page - 1) * pageSize) + 1 : 0;
  const rangeEnd = total && returnedCount ? Math.min(total, rangeStart + returnedCount - 1) : 0;
  return { page, pageSize, total, totalPages, returnedCount, rangeStart, rangeEnd };
}

function reportRunPreviewUrl(apiBaseUrl, runId, page, pageSize) {
  return `${apiBaseUrl}/api/reports/runs/${runId}?row_page=${page}&row_page_size=${pageSize}`;
}

async function optionalJson(url) {
  try {
    const response = await apiFetch(url);
    return response.ok ? response.json() : {};
  } catch {
    return {};
  }
}

function completedMonthRange(months) {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth(), 0);
  const start = new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
  return { start_date: localIsoDate(start), end_date: localIsoDate(end) };
}

function responseError(body, fallback) {
  if (typeof body?.detail === 'string') return body.detail;
  if (Array.isArray(body?.detail)) return body.detail.map((item) => item.msg).join(', ');
  return fallback;
}

async function readResponse(response, fallback) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(responseError(body, fallback));
  return body;
}

function formatMetric(metric) {
  if (metric?.type === 'currency') {
    return new Intl.NumberFormat('en-CA', {
      style: 'currency',
      currency: 'CAD',
      maximumFractionDigits: 2,
    }).format(Number(metric.value || 0));
  }
  if (metric?.type === 'quantity' || metric?.type === 'number') {
    return new Intl.NumberFormat('en-CA', { maximumFractionDigits: 3 }).format(Number(metric.value || 0));
  }
  return metric?.value ?? '—';
}

function formatCell(value, kind) {
  if (value === null || value === undefined || value === '') return '—';
  if (kind === 'currency') {
    return new Intl.NumberFormat('en-CA', {
      style: 'currency',
      currency: 'CAD',
      maximumFractionDigits: 2,
    }).format(Number(value));
  }
  if (['quantity', 'number', 'integer', 'percent'].includes(kind)) {
    return new Intl.NumberFormat('en-CA', { maximumFractionDigits: 3 }).format(Number(value));
  }
  if (kind === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function ReportChart({ chart }) {
  const elementRef = useRef(null);

  useEffect(() => {
    if (!elementRef.current) return undefined;
    const instance = echarts.init(elementRef.current, null, { renderer: 'canvas' });
    const rows = chart.rows || [];
    const categories = rows.map((row) => String(row[chart.category_key] || 'Unspecified'));
    const values = rows.map((row) => Number(row[chart.value_key] || 0));
    instance.setOption({
      animationDuration: 380,
      aria: {
        enabled: true,
        decal: { show: true },
        description: `${chart.title}. ${categories.length} categories.`,
      },
      color: ['#ff6433'],
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        valueFormatter: (value) => new Intl.NumberFormat('en-CA', { maximumFractionDigits: 2 }).format(value),
      },
      grid: { top: 18, right: 18, bottom: categories.length > 7 ? 76 : 44, left: 66 },
      xAxis: {
        type: 'category',
        data: categories,
        axisLabel: { color: '#66677d', rotate: categories.length > 7 ? 28 : 0, hideOverlap: true },
        axisLine: { lineStyle: { color: '#d9dae5' } },
        axisTick: { show: false },
      },
      yAxis: {
        type: 'value',
        axisLabel: { color: '#66677d' },
        splitLine: { lineStyle: { color: '#e8e8ef' } },
      },
      dataZoom: categories.length > 15
        ? [{ type: 'inside', start: 0, end: Math.max(20, 1500 / categories.length) }]
        : [],
      series: [{
        type: chart.type === 'line' ? 'line' : 'bar',
        data: values,
        barMaxWidth: 34,
        smooth: true,
        showSymbol: values.length < 20,
        itemStyle: { borderRadius: [5, 5, 0, 0] },
        lineStyle: { width: 3 },
        areaStyle: chart.type === 'line' ? { color: 'rgba(38, 39, 184, .08)' } : undefined,
      }],
    });
    const resize = () => instance.resize();
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('resize', resize);
      instance.dispose();
    };
  }, [chart]);

  return <div className="ri-chart-canvas" ref={elementRef} role="img" aria-label={chart.title} />;
}

function FilterFields({ report, filters, scopeOptions, onChange }) {
  function optionsFor(key) {
    if (key === 'warehouse') return scopeOptions.warehouses.map((value) => [value, value]);
    if (key === 'brand') return scopeOptions.brands.map((value) => [value, value]);
    if (key === 'category') return scopeOptions.categories.map((value) => [value, value]);
    if (key === 'status') return ORDER_STATUS_OPTIONS;
    if (key === 'inventory_location') {
      return uniqueSorted(
        scopeOptions.locations
          .filter((location) => !filters.warehouse || location.warehouse === filters.warehouse)
          .map((location) => location.name || location.code),
      ).map((value) => [value, value]);
    }
    return null;
  }

  return (
    <div className="ri-filter-grid">
      {(report.filters || []).map((key) => {
        const label = FILTER_LABELS[key] || key.replaceAll('_', ' ');
        const options = optionsFor(key);
        const inputId = `report-filter-${key}`;
        if (key === 'brand') {
          return (
            <MultiSelectFilter
              allLabel={ALL_OPTION_LABELS.brand}
              className="ri-field"
              key={key}
              label={label}
              onChange={(value) => onChange(key, value)}
              options={options.map(([value]) => value)}
              value={filters[key] || []}
            />
          );
        }
        return (
          <label className="ri-field" htmlFor={inputId} key={key}>
            <span>{label}</span>
            {options ? (
              <select id={inputId} value={filters[key] || ''} onChange={(event) => onChange(key, event.target.value)}>
                <option value="">{ALL_OPTION_LABELS[key]}</option>
                {options.map(([value, optionLabel]) => <option key={value} value={value}>{optionLabel}</option>)}
              </select>
            ) : (
              <input
                id={inputId}
                type={key.includes('date') ? 'date' : key === 'customer_email' ? 'email' : 'text'}
                value={filters[key] || ''}
                onChange={(event) => onChange(key, event.target.value)}
                placeholder={key === 'sku' ? 'Exact or partial SKU' : ''}
              />
            )}
          </label>
        );
      })}
    </div>
  );
}

function ReportNavigation({ reports, activeKey }) {
  const grouped = useMemo(
    () => CATEGORY_ORDER.map((category) => ({
      category,
      reports: reports.filter((report) => report.category === category),
    })).filter((group) => group.reports.length),
    [reports],
  );

  return (
    <aside className="ri-nav" aria-label="Intelligent reports">
      <div className="ri-nav-heading">
        <span>REPORT LIBRARY</span>
        <strong>{String(reports.length).padStart(2, '0')}</strong>
      </div>
      {grouped.map((group) => (
        <div className="ri-nav-group" key={group.category}>
          <p>{CATEGORY_LABELS[group.category]}</p>
          {group.reports.map((report) => (
            <a
              href={`#/reports/${report.category}/${report.key === 'received-inventory' ? 'received-inventory-intelligence' : report.key}`}
              className={report.key === activeKey ? 'active' : ''}
              aria-current={report.key === activeKey ? 'page' : undefined}
              key={report.key}
            >
              <span>{report.short_title || report.title}</span>
              <ChevronRight size={15} aria-hidden="true" />
            </a>
          ))}
        </div>
      ))}
    </aside>
  );
}

function SharePanel({ run, catalog, apiBaseUrl, onNotice }) {
  const [sheetRecipients, setSheetRecipients] = useState('');
  const [emailRecipients, setEmailRecipients] = useState('');
  const [formats, setFormats] = useState({ csv: true, pdf: true });
  const [sheetUrl, setSheetUrl] = useState('');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const recipients = (value) => value
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);

  async function createSheet() {
    const sheetWindow = window.open('about:blank', '_blank');
    if (sheetWindow) sheetWindow.opener = null;
    setBusy('sheet');
    setError('');
    try {
      const response = await apiFetch(`${apiBaseUrl}/api/reports/runs/${run.run_id}/google-sheets`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ share_with: recipients(sheetRecipients) }),
      });
      const body = await readResponse(response, 'Google Sheet could not be created.');
      setSheetUrl(body.url);
      onNotice('Google Sheet created from this verified snapshot.');
      if (sheetWindow) sheetWindow.location.replace(body.url);
    } catch (requestError) {
      if (sheetWindow) sheetWindow.close();
      setError(requestError.message);
    } finally {
      setBusy('');
    }
  }

  async function sendEmail() {
    setBusy('email');
    setError('');
    try {
      const selectedFormats = Object.entries(formats).filter(([, enabled]) => enabled).map(([format]) => format);
      const response = await apiFetch(`${apiBaseUrl}/api/reports/runs/${run.run_id}/email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recipients: recipients(emailRecipients),
          formats: selectedFormats,
          google_sheet_url: sheetUrl || null,
        }),
      });
      await readResponse(response, 'Report email could not be sent.');
      onNotice('Report email sent with the selected verified attachments.');
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy('');
    }
  }

  return (
    <div className="ri-share-row">
      <details className="ri-share-panel" open>
        <summary>
          <span className="ri-share-icon sheet"><FileSpreadsheet size={20} /></span>
          <span><strong>Open in Google Sheets</strong><small>Create a live spreadsheet from this frozen run</small></span>
          <ChevronRight size={18} />
        </summary>
        <div className="ri-share-body">
          {!catalog.google_sheets_configured && (
            <div className="ri-config-note">
              <AlertTriangle aria-hidden="true" size={16} />
              <span>Google Sheets is not connected.</span>
              <a href="#/settings/google-sheets">Sign in with Google</a>
            </div>
          )}
          <label className="ri-field">
            <span>Share with (optional)</span>
            <textarea value={sheetRecipients} onChange={(event) => setSheetRecipients(event.target.value)} placeholder="owner@example.com, bookkeeper@example.com" rows="2" />
          </label>
          <button className="ri-primary-button" type="button" disabled={!catalog.google_sheets_configured || busy === 'sheet'} onClick={createSheet}>
            {busy === 'sheet' ? <LoaderCircle className="ri-spin" size={17} /> : <ExternalLink size={17} />}
            Create and open Sheet
          </button>
          {sheetUrl && <a className="ri-created-link" href={sheetUrl} target="_blank" rel="noreferrer">Open created Sheet <ExternalLink size={14} /></a>}
        </div>
      </details>
      <details className="ri-share-panel">
        <summary>
          <span className="ri-share-icon email"><Mail size={20} /></span>
          <span><strong>Email report</strong><small>Send PDF, CSV, and the Sheet link directly</small></span>
          <ChevronRight size={18} />
        </summary>
        <div className="ri-share-body">
          {!catalog.email_configured && (
            <div className="ri-config-note"><AlertTriangle size={16} />Email delivery must be configured in the backend environment first.</div>
          )}
          <label className="ri-field">
            <span>Recipients</span>
            <textarea value={emailRecipients} onChange={(event) => setEmailRecipients(event.target.value)} placeholder="bookkeeper@example.com" rows="2" />
          </label>
          <div className="ri-checks">
            {['pdf', 'csv'].map((format) => (
              <label key={format}>
                <input type="checkbox" checked={formats[format]} onChange={(event) => setFormats((current) => ({ ...current, [format]: event.target.checked }))} />
                {format.toUpperCase()}
              </label>
            ))}
            {sheetUrl && <span><Check size={14} />Sheet link included</span>}
          </div>
          <button className="ri-primary-button" type="button" disabled={!catalog.email_configured || !emailRecipients.trim() || busy === 'email'} onClick={sendEmail}>
            {busy === 'email' ? <LoaderCircle className="ri-spin" size={17} /> : <Send size={17} />}
            Send report
          </button>
        </div>
      </details>
      {error && <div className="ri-inline-error" role="alert">{error}</div>}
    </div>
  );
}

export default function ReportIntelligencePage({ apiBaseUrl, reportKey }) {
  const [catalog, setCatalog] = useState({ reports: [] });
  const [scopeOptions, setScopeOptions] = useState(EMPTY_SCOPE_OPTIONS);
  const [filters, setFilters] = useState({});
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [job, setJob] = useState(null);
  const [previewPageSize, setPreviewPageSize] = useState(REPORT_PREVIEW_PAGE_SIZE);
  const [previewLoading, setPreviewLoading] = useState(false);
  const requestRef = useRef(0);
  const previewRequestRef = useRef(0);
  const pollTimerRef = useRef(null);
  const pollFailuresRef = useRef(0);
  const report = catalog.reports.find((candidate) => candidate.key === reportKey);
  const previewPagination = reportPreviewPagination(run);

  useEffect(() => {
    let active = true;
    Promise.all([
      apiFetch(`${apiBaseUrl}/api/reports`).then((response) => readResponse(response, 'Report library could not be loaded.')),
      optionalJson(`${apiBaseUrl}/api/items?page=1&page_size=1`),
      optionalJson(`${apiBaseUrl}/api/locations?active=true`),
    ])
      .then(([body, itemBody, locationBody]) => {
        if (active) {
          setScopeOptions(buildScopeOptions(itemBody, locationBody));
          setCatalog({
            ...body,
            reports: Array.isArray(body?.reports) ? body.reports : [],
          });
        }
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message);
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [apiBaseUrl]);

  useEffect(() => {
    if (!report) return;
    const nextFilters = defaultFilters(report, scopeOptions);
    setFilters(nextFilters);
    setRun(null);
    setJob(null);
    setNotice('');
    previewRequestRef.current += 1;
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    loadLatest(report.key, nextFilters, requestId);
    return () => {
      requestRef.current += 1;
      window.clearTimeout(pollTimerRef.current);
    };
  }, [report?.key]);

  async function loadLatest(key, selectedFilters, requestId = requestRef.current) {
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${apiBaseUrl}/api/reports/jobs/latest/${key}?row_page=1&row_page_size=${previewPageSize}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filters: selectedFilters, generated_by: 'reporting-ui' }),
      });
      if (response.status === 404) {
        if (requestId === requestRef.current) setRun(null);
        return;
      }
      const body = await readResponse(response, 'The latest report snapshot could not be loaded.');
      if (requestId === requestRef.current) setRun(body?.run_id ? body : null);
    } catch (requestError) {
      if (requestId === requestRef.current) setError(requestError.message);
    } finally {
      if (requestId === requestRef.current) setLoading(false);
    }
  }

  async function loadRun(runId, requestId, page = 1, pageSize = previewPageSize) {
    const response = await apiFetch(reportRunPreviewUrl(apiBaseUrl, runId, page, pageSize));
    const body = await readResponse(response, 'Completed report snapshot could not be loaded.');
    if (requestId === requestRef.current) setRun(body);
    return body;
  }

  function scheduleJobPoll(jobId, requestId, delay = 1500) {
    window.clearTimeout(pollTimerRef.current);
    pollTimerRef.current = window.setTimeout(() => pollJob(jobId, requestId), delay);
  }

  async function pollJob(jobId, requestId) {
    if (requestId !== requestRef.current) return;
    try {
      const response = await apiFetch(`${apiBaseUrl}/api/reports/jobs/${jobId}`);
      const body = await readResponse(response, 'Report progress could not be checked.');
      if (requestId !== requestRef.current) return;
      pollFailuresRef.current = 0;
      setJob(body);
      if (body.status === 'completed' && body.run_id) {
        await loadRun(body.run_id, requestId);
        setLoading(false);
      } else if (body.status === 'failed') {
        setError(body.error || 'Report generation failed.');
        setLoading(false);
      } else {
        scheduleJobPoll(jobId, requestId);
      }
    } catch (requestError) {
      if (requestId === requestRef.current) {
        pollFailuresRef.current += 1;
        if (pollFailuresRef.current <= 3) {
          scheduleJobPoll(jobId, requestId, 1500 * (2 ** pollFailuresRef.current));
        } else {
          setError(requestError.message);
          setLoading(false);
        }
      }
    }
  }

  async function generateSynchronously(key, selectedFilters, requestId) {
    const response = await apiFetch(`${apiBaseUrl}/api/reports/runs/${key}?row_page=1&row_page_size=${previewPageSize}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filters: selectedFilters, generated_by: 'reporting-ui' }),
    });
    const body = await readResponse(response, 'Report could not be generated.');
    if (!body?.run_id) throw new Error('Report generation returned no verified run.');
    if (requestId === requestRef.current) setRun(body);
  }

  async function generate(key = report?.key, selectedFilters = filters) {
    if (!key) return;
    let keepPolling = false;
    window.clearTimeout(pollTimerRef.current);
    const requestId = requestRef.current + 1;
    requestRef.current = requestId;
    pollFailuresRef.current = 0;
    previewRequestRef.current += 1;
    setLoading(true);
    setError('');
    setJob(null);
    if (JSON.stringify(run?.filters || {}) !== JSON.stringify(selectedFilters || {})) setRun(null);
    try {
      const response = await apiFetch(`${apiBaseUrl}/api/reports/jobs/${key}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filters: selectedFilters, generated_by: 'reporting-ui' }),
      });
      if ([404, 405].includes(response.status)) {
        await generateSynchronously(key, selectedFilters, requestId);
        return;
      }
      const body = await readResponse(response, 'Report could not be queued.');
      if (body.columns && body.run_id && !body.job_id) {
        setRun(body);
        return;
      }
      if (!body.job_id) {
        await generateSynchronously(key, selectedFilters, requestId);
        return;
      }
      setJob(body);
      if (body.previous_run_id) await loadRun(body.previous_run_id, requestId);
      else if (requestId === requestRef.current) setRun(null);
      if (body.status === 'completed' && body.run_id) {
        await loadRun(body.run_id, requestId);
      } else if (body.status === 'failed') {
        throw new Error(body.error || 'Report generation failed.');
      } else {
        keepPolling = true;
        scheduleJobPoll(body.job_id, requestId);
        return;
      }
    } catch (requestError) {
      if (requestId === requestRef.current) setError(requestError.message);
    } finally {
      if (requestId === requestRef.current && !keepPolling) setLoading(false);
    }
  }

  async function loadPreviewPage(page, pageSize = previewPageSize) {
    if (!run?.run_id) return;
    const requestId = previewRequestRef.current + 1;
    previewRequestRef.current = requestId;
    setPreviewLoading(true);
    setError('');
    try {
      const response = await apiFetch(reportRunPreviewUrl(apiBaseUrl, run.run_id, page, pageSize));
      const body = await readResponse(response, 'Report detail page could not be loaded.');
      if (requestId === previewRequestRef.current && body?.run_id === run.run_id) setRun(body);
    } catch (requestError) {
      if (requestId === previewRequestRef.current) setError(requestError.message);
    } finally {
      if (requestId === previewRequestRef.current) setPreviewLoading(false);
    }
  }

  function changePreviewPageSize(pageSize) {
    setPreviewPageSize(pageSize);
    loadPreviewPage(1, pageSize);
  }

  function applyPreset(days) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (days - 1));
    const nextFilters = { ...filters, start_date: localIsoDate(start), end_date: localIsoDate(end) };
    setFilters(nextFilters);
    generate(report.key, nextFilters);
  }

  function applyCompletedMonths(months) {
    const nextFilters = { ...filters, ...completedMonthRange(months) };
    setFilters(nextFilters);
    generate(report.key, nextFilters);
  }

  function applyYearToDate() {
    const now = new Date();
    const nextFilters = {
      ...filters,
      start_date: `${now.getFullYear()}-01-01`,
      end_date: localIsoDate(now),
    };
    setFilters(nextFilters);
    generate(report.key, nextFilters);
  }

  if (!report && !error) {
    return (
      <section className="ri-shell ri-loading-page" aria-busy="true">
        <LoaderCircle className="ri-spin" size={28} />
        Loading report library…
      </section>
    );
  }

  return (
    <section className="ri-shell">
      <ReportNavigation reports={catalog.reports} activeKey={reportKey} />
      <main className="ri-main">
        {error && <div className="ri-error-banner" role="alert"><AlertTriangle size={18} />{error}</div>}
        {notice && <div className="ri-success-banner" role="status"><Check size={18} />{notice}</div>}
        {report && (
          <>
            <header className="ri-header">
              <div>
                <p className="ri-eyebrow">{CATEGORY_LABELS[report.category]} / REPORT INTELLIGENCE</p>
                <h1>{report.title}</h1>
                <p>{report.description}</p>
              </div>
              <div className="ri-verified-mark">
                <ShieldCheck size={21} />
                <span><strong>Audited snapshot</strong><small>Repeatable + hash verified</small></span>
              </div>
            </header>

            <section className="ri-filter-card" aria-label="Report filters">
              <div className="ri-section-heading">
                <div><CalendarRange size={19} /><span><strong>Reporting scope</strong><small>All dates use America/Edmonton</small></span></div>
                {report.date_mode === 'range' && (
                  <div className="ri-presets" aria-label="Date presets">
                    <button type="button" onClick={() => applyPreset(7)}>7 days</button>
                    <button type="button" onClick={() => applyCompletedMonths(1)}>Last month</button>
                    <button type="button" onClick={() => applyCompletedMonths(2)}>Last 2 months</button>
                    <button type="button" onClick={() => applyCompletedMonths(3)}>Last 3 months</button>
                    <button type="button" onClick={() => applyCompletedMonths(12)}>Last year</button>
                    <button type="button" onClick={applyYearToDate}>Calendar YTD</button>
                  </div>
                )}
              </div>
              <FilterFields
                report={report}
                filters={filters}
                scopeOptions={scopeOptions}
                onChange={(key, value) => setFilters((current) => (
                  key === 'warehouse'
                    ? { ...current, warehouse: value, inventory_location: '' }
                    : { ...current, [key]: value }
                ))}
              />
              <div className="ri-filter-actions">
                <p>Exports are generated from one immutable report run, so PDF, CSV, Sheets, and email agree.</p>
                <button className="ri-primary-button" type="button" onClick={() => generate()} disabled={loading}>
                  {loading ? <LoaderCircle className="ri-spin" size={17} /> : <RefreshCw size={17} />}
                  Generate verified report
                </button>
              </div>
            </section>

            {loading && !run && (
              <div className="ri-report-loading" aria-live="polite">
                <LoaderCircle className="ri-spin" size={25} />
                {job ? `Generating report… ${Math.round(Number(job.progress || 0))}%` : 'Loading the latest verified snapshot…'}
              </div>
            )}

            {loading && run && job && (
              <div className="ri-report-loading" aria-live="polite">
                <LoaderCircle className="ri-spin" size={20} />
                Showing the previous verified run while the new report generates… {Math.round(Number(job.progress || 0))}%
              </div>
            )}

            {run && (
              <>
                <div className="ri-action-bar">
                  <div>
                    <span className="ri-live-dot" />
                    <strong>Run ready</strong>
                    <small>{previewPagination.total.toLocaleString()} rows • generated {new Date(run.generated_at).toLocaleString('en-CA')}</small>
                  </div>
                  <div>
                    {report.formats.includes('pdf') ? (
                      <DocumentActions
                        compact
                        csvUrl={report.formats.includes('csv') ? `${apiBaseUrl}/api/reports/runs/${run.run_id}/csv` : undefined}
                        pdfUrl={`${apiBaseUrl}/api/reports/runs/${run.run_id}/pdf`}
                        title={`${report.title} · run ${run.run_id}`}
                      />
                    ) : report.formats.includes('csv') && (
                      <a href={`${apiBaseUrl}/api/reports/runs/${run.run_id}/csv`} className="ri-action-button">
                        <Download size={16} />CSV
                      </a>
                    )}
                  </div>
                </div>

                <SharePanel key={run.run_id} run={run} catalog={catalog} apiBaseUrl={apiBaseUrl} onNotice={setNotice} />

                <section className="ri-kpis" aria-label="Report summary">
                  {(run.kpis || []).map((metric, index) => (
                    <article className={index === 0 ? 'featured' : ''} key={metric.key}>
                      <span>{metric.label}</span>
                      <strong>{formatMetric(metric)}</strong>
                      <small>{index === 0 ? 'Primary measure' : 'Verified at generation'}</small>
                    </article>
                  ))}
                </section>

                {(run.charts || []).length > 0 && (
                  <section className="ri-chart-grid">
                    {run.charts.map((chart) => (
                      <article className="ri-chart-card" key={`${chart.title}-${chart.category_key}`}>
                        <div>
                          <p>INTERACTIVE VIEW</p>
                          <h2>{chart.title}</h2>
                        </div>
                        <ReportChart chart={chart} />
                      </article>
                    ))}
                  </section>
                )}

                {(run.insights || []).length > 0 && (
                  <section className="ri-insights">
                    <div className="ri-block-title">
                      <span><Sparkles size={18} /></span>
                      <div><p>EMBEDDED INTELLIGENCE</p><h2>Evidence, finding, next action</h2></div>
                    </div>
                    <div className="ri-insight-grid">
                      {run.insights.map((item, index) => (
                        <article className={`ri-insight ${item.severity || 'info'}`} key={`${item.title}-${index}`}>
                          <span>{String(index + 1).padStart(2, '0')}</span>
                          <div>
                            <h3>{item.title}</h3>
                            <p>{item.evidence}</p>
                            <strong>Recommended action</strong>
                            {item.href ? <a href={item.href}>{item.action}<ArrowRight size={14} /></a> : <small>{item.action}</small>}
                          </div>
                        </article>
                      ))}
                    </div>
                  </section>
                )}

                <section className="ri-table-card">
                  <div className="ri-table-heading">
                    <div><p>SUPPORTING LEDGER</p><h2>Report detail</h2></div>
                    <span>{previewPagination.total.toLocaleString()} records</span>
                  </div>
                  <div className="ri-table-scroll" aria-busy={previewLoading}>
                    <table>
                      <thead>
                        <tr>{run.columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr>
                      </thead>
                      <tbody>
                        {run.rows.length ? run.rows.map((row, rowIndex) => (
                          <tr className={row.is_subscription_product ? 'ri-subscription-row' : ''} key={`${run.run_id}-${previewPagination.page}-${rowIndex}`}>
                            {run.columns.map((column) => (
                              <td className={['currency', 'quantity', 'number', 'integer', 'percent'].includes(column.type) ? 'numeric' : ''} key={column.key}>
                                {formatCell(row[column.key], column.type)}
                                {column.key === 'name' && row.is_subscription_product && <span className="ri-subscription-badge">Subscription</span>}
                              </td>
                            ))}
                          </tr>
                        )) : (
                          <tr><td className="ri-empty-cell" colSpan={Math.max(1, run.columns.length)}>No records matched this reporting scope.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                  <div className="ri-table-pager" aria-label="Report detail pagination">
                    <span>
                      Showing {previewPagination.rangeStart.toLocaleString()}–{previewPagination.rangeEnd.toLocaleString()} of {previewPagination.total.toLocaleString()} records
                    </span>
                    <label>
                      <span>Rows per page</span>
                      <select
                        aria-label="Report rows per page"
                        value={previewPagination.pageSize}
                        onChange={(event) => changePreviewPageSize(Number(event.target.value))}
                        disabled={previewLoading}
                      >
                        {REPORT_PREVIEW_PAGE_SIZES.map((size) => <option value={size} key={size}>{size}</option>)}
                      </select>
                    </label>
                    <button
                      type="button"
                      aria-label="Previous report page"
                      onClick={() => loadPreviewPage(previewPagination.page - 1)}
                      disabled={previewLoading || previewPagination.page <= 1}
                    >
                      <ChevronLeft size={17} />
                    </button>
                    <strong>Page {previewPagination.totalPages ? previewPagination.page : 0} of {previewPagination.totalPages}</strong>
                    <button
                      type="button"
                      aria-label="Next report page"
                      onClick={() => loadPreviewPage(previewPagination.page + 1)}
                      disabled={previewLoading || previewPagination.page >= previewPagination.totalPages || previewPagination.total === 0}
                    >
                      <ChevronRight size={17} />
                    </button>
                  </div>
                </section>

                <section className="ri-assurance">
                  <div className="ri-assurance-heading">
                    <ShieldCheck size={20} />
                    <div><p>REPORT ASSURANCE</p><h2>Definitions and data-quality disclosures</h2></div>
                  </div>
                  <div className="ri-assurance-columns">
                    <div>
                      <h3>Calculation definitions</h3>
                      <ol>{(run.definitions || []).map((definition) => <li key={definition}>{definition}</li>)}</ol>
                    </div>
                    <div>
                      <h3>Data quality</h3>
                      {run.data_quality?.length ? run.data_quality.map((warning) => (
                        <article className="ri-quality-warning" key={warning.code}>
                          <AlertTriangle size={16} />
                          <span><strong>{warning.title}</strong><small>{warning.message}</small></span>
                        </article>
                      )) : <div className="ri-quality-clear"><Check size={16} />No report-specific exceptions were detected.</div>}
                    </div>
                  </div>
                </section>

                <footer className="ri-audit-footer">
                  <BarChart3 size={17} />
                  <span><strong>Run ID</strong>{run.run_id}</span>
                  <span><strong>Definition</strong>v{run.definition_version}</span>
                  <span className="ri-hash"><strong>SHA-256 evidence hash</strong>{run.data_hash}</span>
                </footer>
              </>
            )}
          </>
        )}
      </main>
    </section>
  );
}
