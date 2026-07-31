import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CalendarRange,
  Check,
  ChevronRight,
  Download,
  ExternalLink,
  FileSpreadsheet,
  FileText,
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

function localIsoDate(value = new Date()) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function defaultFilters(report) {
  if (report?.date_mode !== 'range') return {};
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (report.key === 'executive-weekly' ? 6 : 29));
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

function FilterFields({ report, filters, onChange }) {
  return (
    <div className="ri-filter-grid">
      {(report.filters || []).map((key) => (
        <label className="ri-field" key={key}>
          <span>{FILTER_LABELS[key] || key.replaceAll('_', ' ')}</span>
          <input
            type={key.includes('date') ? 'date' : key === 'customer_email' ? 'email' : 'text'}
            value={filters[key] || ''}
            onChange={(event) => onChange(key, event.target.value)}
            placeholder={key === 'sku' ? 'Exact or partial SKU' : ''}
          />
        </label>
      ))}
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
      <details className="ri-share-panel">
        <summary>
          <span className="ri-share-icon sheet"><FileSpreadsheet size={20} /></span>
          <span><strong>Open in Google Sheets</strong><small>Create a live spreadsheet from this frozen run</small></span>
          <ChevronRight size={18} />
        </summary>
        <div className="ri-share-body">
          {!catalog.google_sheets_configured && (
            <div className="ri-config-note"><AlertTriangle size={16} />Google Sheets credentials must be configured in the backend environment first.</div>
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
  const [filters, setFilters] = useState({});
  const [run, setRun] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const report = catalog.reports.find((candidate) => candidate.key === reportKey);

  useEffect(() => {
    let active = true;
    apiFetch(`${apiBaseUrl}/api/reports`)
      .then((response) => readResponse(response, 'Report library could not be loaded.'))
      .then((body) => {
        if (active) {
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
    const nextFilters = defaultFilters(report);
    setFilters(nextFilters);
    setRun(null);
    setNotice('');
    generate(report.key, nextFilters);
  }, [report?.key]);

  async function generate(key = report?.key, selectedFilters = filters) {
    if (!key) return;
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${apiBaseUrl}/api/reports/runs/${key}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filters: selectedFilters, generated_by: 'reporting-ui' }),
      });
      const body = await readResponse(response, 'Report could not be generated.');
      setRun(body);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setLoading(false);
    }
  }

  function applyPreset(days) {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - (days - 1));
    setFilters((current) => ({ ...current, start_date: localIsoDate(start), end_date: localIsoDate(end) }));
  }

  function applyYearToDate() {
    const now = new Date();
    setFilters((current) => ({
      ...current,
      start_date: `${now.getFullYear()}-01-01`,
      end_date: localIsoDate(now),
    }));
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
                    <button type="button" onClick={() => applyPreset(30)}>30 days</button>
                    <button type="button" onClick={applyYearToDate}>Calendar YTD</button>
                  </div>
                )}
              </div>
              <FilterFields report={report} filters={filters} onChange={(key, value) => setFilters((current) => ({ ...current, [key]: value }))} />
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
                Reconciling the report snapshot…
              </div>
            )}

            {run && (
              <>
                <div className="ri-action-bar">
                  <div>
                    <span className="ri-live-dot" />
                    <strong>Run ready</strong>
                    <small>{run.row_count.toLocaleString()} rows • generated {new Date(run.generated_at).toLocaleString('en-CA')}</small>
                  </div>
                  <div>
                    {report.formats.includes('csv') && (
                      <a href={`${apiBaseUrl}/api/reports/runs/${run.run_id}/csv`} className="ri-action-button">
                        <Download size={16} />CSV
                      </a>
                    )}
                    {report.formats.includes('pdf') && (
                      <a href={`${apiBaseUrl}/api/reports/runs/${run.run_id}/pdf`} className="ri-action-button">
                        <FileText size={16} />PDF
                      </a>
                    )}
                  </div>
                </div>

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
                    <span>{run.row_count.toLocaleString()} records</span>
                  </div>
                  <div className="ri-table-scroll">
                    <table>
                      <thead>
                        <tr>{run.columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr>
                      </thead>
                      <tbody>
                        {run.rows.length ? run.rows.map((row, rowIndex) => (
                          <tr key={`${run.run_id}-${rowIndex}`}>
                            {run.columns.map((column) => (
                              <td className={['currency', 'quantity', 'number', 'integer', 'percent'].includes(column.type) ? 'numeric' : ''} key={column.key}>
                                {formatCell(row[column.key], column.type)}
                              </td>
                            ))}
                          </tr>
                        )) : (
                          <tr><td className="ri-empty-cell" colSpan={Math.max(1, run.columns.length)}>No records matched this reporting scope.</td></tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </section>

                <SharePanel key={run.run_id} run={run} catalog={catalog} apiBaseUrl={apiBaseUrl} onNotice={setNotice} />

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
