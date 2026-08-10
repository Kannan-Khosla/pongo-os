import { useEffect, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  Download,
  FileSpreadsheet,
  History,
  PackagePlus,
  Pencil,
  RefreshCw,
  RotateCcw,
  Search,
  ShieldCheck,
  UploadCloud,
  Warehouse,
  X,
} from 'lucide-react';
import { API_BASE_URL, apiFetch } from './api';
import './ItemImportWorkspace.css';

const STEPS = ['Choose outcome', 'Upload', 'Match columns', 'Review & fix', 'Confirm', 'Results'];
const OUTCOME_ICONS = { add_items: PackagePlus, update_items: Pencil, update_stock: RefreshCw, starting_inventory: Warehouse };
const PREVIEW_KEY = 'pongo.item-import.preview';

function newIdempotencyKey() {
  return globalThis.crypto?.randomUUID?.() || `item-import-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function apiMessage(body, fallback) {
  const detail = body?.detail;
  if (typeof detail === 'string') return detail;
  return detail?.message || body?.message || fallback;
}

async function requestJson(path, init, fallback = 'The request could not be completed.') {
  const response = await apiFetch(`${API_BASE_URL}${path}`, init);
  const body = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(apiMessage(body, fallback));
    error.status = response.status;
    error.detail = body?.detail;
    throw error;
  }
  return body;
}

function formatNumber(value) {
  return new Intl.NumberFormat('en-CA', { maximumFractionDigits: 3 }).format(Number(value || 0));
}

function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('en-CA', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}

function outcomeSchema(schema, outcome) {
  return schema?.outcomes?.find((candidate) => candidate.key === outcome);
}

function hasBlockingIssues(summary) {
  return ['needs_attention_count', 'duplicate_count', 'unmatched_count', 'blocked_count'].some((key) => Number(summary?.[key] || 0) > 0);
}

function stockImportBlocked(summary) {
  return hasBlockingIssues(summary) || Number(summary?.excluded_count || 0) > 0;
}

function downloadHref(outcome, includeExisting = false) {
  return `${API_BASE_URL}/api/items/import/templates/${outcome}${includeExisting ? '?include_existing=true' : ''}`;
}

function StatusPill({ state }) {
  const labels = {
    will_create: 'Will create',
    will_update: 'Will update',
    no_changes: 'No changes',
    needs_attention: 'Needs attention',
    duplicate: 'Duplicate',
    unmatched: 'SKU not found',
    blocked: 'Blocked',
    excluded: 'Excluded',
    completed: 'Completed',
    completed_with_errors: 'Completed with errors',
    failed: 'Failed',
  };
  return <span className={`import-status import-status-${state}`}>{labels[state] || state}</span>;
}

function Stepper({ current, maxStep, onChange }) {
  return (
    <nav className="import-stepper" aria-label="Import progress">
      {STEPS.map((label, index) => {
        const step = index + 1;
        const complete = step < current;
        const enabled = step <= maxStep && step !== 6;
        return (
          <button className={`${step === current ? 'active' : ''} ${complete ? 'complete' : ''}`} disabled={!enabled} key={label} onClick={() => onChange(step)} type="button" aria-current={step === current ? 'step' : undefined}>
            <span>{complete ? <Check size={15} /> : step}</span>
            <strong>{label}</strong>
          </button>
        );
      })}
    </nav>
  );
}

function PageIntro({ title, description, onCancel }) {
  return (
    <div className="import-page-intro">
      <div>
        <a href="#items" className="import-back-link"><ArrowLeft size={16} /> Items</a>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      {onCancel && <button className="import-quiet-button" onClick={onCancel} type="button"><X size={17} /> Cancel import</button>}
    </div>
  );
}

function SummaryCards({ summary, outcome }) {
  const cards = outcome === 'starting_inventory'
    ? [
      ['Ready', summary?.ready_count],
      ['Needs attention', (summary?.needs_attention_count || 0) + (summary?.blocked_count || 0) + (summary?.unmatched_count || 0)],
      ['Starting units', summary?.starting_units],
      ['Estimated value', `$${formatNumber(summary?.estimated_valuation)}`],
    ] : outcome === 'update_stock'
      ? [
        ['Ready', summary?.ready_count],
        ['No changes', summary?.no_changes_count],
        ['Needs attention', (summary?.needs_attention_count || 0) + (summary?.duplicate_count || 0) + (summary?.unmatched_count || 0) + (summary?.blocked_count || 0) + (summary?.excluded_count || 0)],
        ['Net stock change', summary?.stock_units_delta],
      ]
    : [
      ['Will create', summary?.create_count],
      ['Will update', summary?.update_count],
      ['No changes', summary?.no_changes_count],
      ['Needs attention', (summary?.needs_attention_count || 0) + (summary?.duplicate_count || 0) + (summary?.unmatched_count || 0) + (summary?.blocked_count || 0)],
    ];
  return <div className="import-summary-grid">{cards.map(([label, value]) => <div key={label}><span>{label}</span><strong>{typeof value === 'string' ? value : formatNumber(value)}</strong></div>)}</div>;
}

function OutcomeStep({ schema, outcome, setOutcome, onContinue }) {
  return (
    <section className="import-stage" aria-labelledby="outcome-title">
      <div className="import-stage-heading"><span>Step 1</span><h3 id="outcome-title">What do you want this file to do?</h3><p>Choose one outcome. Each workflow has its own safe template and validation rules.</p></div>
      <div className="outcome-grid">
        {(schema?.outcomes || []).map((candidate) => {
          const Icon = OUTCOME_ICONS[candidate.key];
          return (
            <button className={`outcome-card ${outcome === candidate.key ? 'selected' : ''}`} key={candidate.key} onClick={() => setOutcome(candidate.key)} type="button" aria-pressed={outcome === candidate.key}>
              <span className="outcome-icon"><Icon size={24} /></span>
              <span><strong>{candidate.label}</strong><small>{candidate.description}</small></span>
              <span className="outcome-check">{outcome === candidate.key && <Check size={16} />}</span>
              <dl><div><dt>Changes</dt><dd>{candidate.changes}</dd></div><div><dt>Protected</dt><dd>{candidate.does_not_change}</dd></div></dl>
            </button>
          );
        })}
      </div>
      <div className="import-assurance"><ShieldCheck size={19} /><span><strong>Inventory-safe by design.</strong> Stock overrides show exact before-and-after quantities and create audit movements. Item-detail files cannot change stock.</span></div>
      <div className="import-stage-actions"><a className="import-secondary-button" href="#/items/imports"><History size={17} /> View import history</a><button className="import-primary-button" disabled={!outcome} onClick={onContinue} type="button">Continue <ArrowRight size={17} /></button></div>
    </section>
  );
}

function UploadStep({ schema, outcome, file, setFile, onUpload, busy, onBack }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);
  const outcomeData = outcomeSchema(schema, outcome);
  function choose(candidate) {
    if (candidate) setFile(candidate);
  }
  return (
    <section className="import-stage" aria-labelledby="upload-title">
      <div className="import-stage-heading"><span>Step 2</span><h3 id="upload-title">Upload your CSV</h3><p>We will read the file, suggest column matches, and save an immutable preview before anything changes.</p></div>
      <div className="template-banner">
        <div><FileSpreadsheet size={21} /><span><strong>Start with the {outcomeData?.label} template</strong><small>Generated by the same schema that validates your upload.</small></span></div>
        <div><a className="import-secondary-button" href={downloadHref(outcome)}><Download size={17} /> Download template</a>{outcome === 'update_items' && <a className="import-text-link" href={downloadHref(outcome, true)}>Export editable existing items</a>}{outcome === 'update_stock' && <a className="import-text-link" href={downloadHref(outcome, true)}>Export editable current stock</a>}</div>
      </div>
      <label className={`import-dropzone ${dragging ? 'dragging' : ''} ${file ? 'has-file' : ''}`} onDragEnter={() => setDragging(true)} onDragLeave={() => setDragging(false)} onDragOver={(event) => event.preventDefault()} onDrop={(event) => { event.preventDefault(); setDragging(false); choose(event.dataTransfer.files?.[0]); }}>
        <input accept=".csv,text/csv" ref={inputRef} onChange={(event) => choose(event.target.files?.[0])} type="file" />
        {file ? <><CheckCircle2 size={32} /><strong>{file.name}</strong><span>{formatNumber(file.size / 1024)} KB · Ready to inspect</span><button className="import-text-button" onClick={(event) => { event.preventDefault(); setFile(null); inputRef.current.value = ''; }} type="button">Choose a different file</button></> : <><UploadCloud size={34} /><strong>Drop your CSV here</strong><span>or click to browse · UTF-8 · up to {formatNumber((schema?.max_file_bytes || 0) / 1048576)} MB</span></>}
      </label>
      <div className="import-stage-actions"><button className="import-quiet-button" onClick={onBack} type="button"><ArrowLeft size={17} /> Back</button><button className="import-primary-button" disabled={!file || busy} onClick={onUpload} type="button">{busy ? 'Reading and checking…' : outcome === 'update_stock' ? 'Upload and review stock' : 'Upload and match columns'} <ArrowRight size={17} /></button></div>
    </section>
  );
}

function MappingStep({ schema, preview, setPreview, onContinue, onBack, busy, setBusy, setError }) {
  const [mapping, setMapping] = useState(preview.mapping || {});
  const [allowBlankClears, setAllowBlankClears] = useState(Boolean(preview.options?.allow_blank_clears));
  const [profileName, setProfileName] = useState('');
  const [profileSaved, setProfileSaved] = useState(false);
  const destination = outcomeSchema(schema, preview.outcome);
  const missing = destination?.required_fields?.filter((field) => !Object.values(mapping).includes(field)) || [];

  async function saveMapping(advance = false) {
    setBusy(true);
    setError('');
    try {
      const next = await requestJson(`/api/items/import/previews/${preview.preview_id}/mapping`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mapping, allow_blank_clears: allowBlankClears }) }, 'Column matches could not be saved.');
      setPreview(next);
      if (advance) onContinue();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function saveProfile() {
    if (!profileName.trim()) return;
    setBusy(true);
    setError('');
    try {
      await requestJson('/api/items/import/profiles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: profileName, outcome: preview.outcome, source_headers: preview.source_columns.map((column) => column.source), mapping }) });
      setProfileSaved(true);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="import-stage" aria-labelledby="mapping-title">
      <div className="import-stage-heading"><span>Step 3</span><h3 id="mapping-title">Match your columns</h3><p>Confirm where each source column belongs. Unneeded columns can stay ignored.</p></div>
      {preview.suggested_profile && <div className="import-notice info"><RefreshCw size={18} /><span><strong>Reusable match found: {preview.suggested_profile.name}</strong><small>Apply the saved matches, then review them before continuing.</small></span><button className="import-secondary-button" onClick={() => setMapping(preview.suggested_profile.mapping)} type="button">Apply profile</button></div>}
      <div className="mapping-table-wrap"><table className="mapping-table"><thead><tr><th>Your CSV column</th><th>Example values</th><th>Pongo OS field</th><th>Match</th></tr></thead><tbody>{preview.source_columns.map((column) => <tr key={column.source}><td><strong>{column.source}</strong></td><td><span className="mapping-samples">{column.samples?.join(' · ') || 'Blank'}</span></td><td><select aria-label={`Map ${column.source}`} value={mapping[column.source] || ''} onChange={(event) => setMapping((current) => ({ ...current, [column.source]: event.target.value || null }))}><option value="">Ignore this column</option>{destination?.fields?.map((field) => <option key={field.key} value={field.key}>{field.label}{field.required_for?.includes(preview.outcome) ? ' (required)' : ''}</option>)}</select></td><td><span className={`mapping-confidence ${mapping[column.source] ? 'matched' : ''}`}>{mapping[column.source] ? <><Check size={14} /> Matched</> : 'Ignored'}</span></td></tr>)}</tbody></table></div>
      {missing.length > 0 && <div className="import-notice warning"><AlertTriangle size={18} /><span><strong>Required matches are missing</strong><small>Match {missing.map((key) => destination.fields.find((field) => field.key === key)?.label || key).join(', ')} to continue.</small></span></div>}
      {preview.outcome === 'update_items' && <label className="import-checkbox-card"><input checked={allowBlankClears} onChange={(event) => setAllowBlankClears(event.target.checked)} type="checkbox" /><span><strong>Clear existing values when the CSV cell is blank</strong><small>Leave this off to preserve existing data. This never applies to inventory quantities.</small></span></label>}
      <div className="mapping-profile-row"><label><span>Save these matches for next time</span><input maxLength={160} placeholder="Example: Supplier weekly export" value={profileName} onChange={(event) => { setProfileName(event.target.value); setProfileSaved(false); }} /></label><button className="import-secondary-button" disabled={!profileName.trim() || busy || profileSaved} onClick={saveProfile} type="button">{profileSaved ? 'Profile saved' : 'Save profile'}</button></div>
      <div className="import-stage-actions"><button className="import-quiet-button" onClick={onBack} type="button"><ArrowLeft size={17} /> Back</button><button className="import-primary-button" disabled={missing.length > 0 || busy} onClick={() => saveMapping(true)} type="button">Validate rows <ArrowRight size={17} /></button></div>
    </section>
  );
}

function RowEditor({ row, fields, onClose, onSave, busy }) {
  const [values, setValues] = useState(() => Object.fromEntries(fields.map((field) => [field.key, row.normalized_data?.[field.key] ?? ''])));
  const dialogRef = useRef(null);
  const previousFocusRef = useRef(document.activeElement);
  useEffect(() => {
    const dialog = dialogRef.current;
    const focusable = () => [...dialog.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])')];
    function handleKeyDown(event) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;
      const candidates = focusable();
      const first = candidates[0];
      const last = candidates.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    dialog.addEventListener('keydown', handleKeyDown);
    return () => {
      dialog.removeEventListener('keydown', handleKeyDown);
      previousFocusRef.current?.focus();
    };
  }, []);
  return (
    <div className="import-drawer-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="import-row-drawer" ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="row-editor-title" aria-describedby={row.issues?.length ? 'row-editor-issues' : undefined}>
        <header><div><span>CSV row {row.row_number}</span><h3 id="row-editor-title">Fix item data</h3></div><button aria-label="Close row editor" onClick={onClose} type="button"><X size={19} /></button></header>
        {row.issues?.length > 0 && <div className="row-issue-list" id="row-editor-issues">{row.issues.map((candidate, index) => <div key={`${candidate.code}-${index}`}><AlertTriangle size={16} /><span><strong>{candidate.message}</strong>{candidate.suggested_action && <small>{candidate.suggested_action}</small>}</span></div>)}</div>}
        <div className="row-editor-fields">{fields.map((field, index) => <label key={field.key}><span>{field.label}</span><input autoFocus={index === 0} type={['decimal', 'integer'].includes(field.type) ? 'number' : 'text'} value={values[field.key]} onChange={(event) => setValues((current) => ({ ...current, [field.key]: event.target.value }))} /></label>)}</div>
        <footer><button className="import-quiet-button" onClick={onClose} type="button">Cancel</button><button className="import-primary-button" disabled={busy} onClick={() => onSave(values)} type="button">Save and revalidate</button></footer>
      </aside>
    </div>
  );
}

function ReviewStep({ schema, preview, setPreview, onContinue, onBack, busy, setBusy, setError }) {
  const [rowsData, setRowsData] = useState({ rows: [], total: 0, page: 1, total_pages: 0 });
  const [state, setState] = useState('');
  const [search, setSearch] = useState('');
  const [searchDraft, setSearchDraft] = useState('');
  const [editing, setEditing] = useState(null);
  const fields = outcomeSchema(schema, preview.outcome)?.fields || [];
  const isStockImport = preview.outcome === 'update_stock';

  async function loadRows(nextPage = 1) {
    setBusy(true);
    try {
      const params = new URLSearchParams({ page: String(nextPage), page_size: '50' });
      if (state) params.set('state', state);
      if (search) params.set('search', search);
      setRowsData(await requestJson(`/api/items/import/previews/${preview.preview_id}/rows?${params}`));
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => { loadRows(1); }, [state, search, preview.preview_id]);

  async function updateRow(row, payload) {
    setBusy(true);
    setError('');
    try {
      await requestJson(`/api/items/import/previews/${preview.preview_id}/rows/${row.row_number}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const refreshed = await requestJson(`/api/items/import/previews/${preview.preview_id}`);
      setPreview(refreshed);
      setEditing(null);
      await loadRows(rowsData.page);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  const issueCount = (preview.summary?.needs_attention_count || 0) + (preview.summary?.duplicate_count || 0) + (preview.summary?.unmatched_count || 0) + (preview.summary?.blocked_count || 0);
  const stockBlocked = isStockImport && stockImportBlocked(preview.summary);
  const rowFilters = [['', 'All'], ['needs_attention', 'Needs attention'], ['duplicate', 'Duplicates'], ['unmatched', 'Not found'], ['blocked', 'Blocked'], ['will_create', 'Will create'], ['will_update', 'Will update'], ...(!isStockImport || preview.summary?.excluded_count ? [['excluded', 'Excluded']] : [])];
  return (
    <section className="import-stage wide" aria-labelledby="review-title">
      <div className="import-stage-heading"><span>Step 4</span><h3 id="review-title">Review and fix issues</h3><p>{isStockImport ? 'Nothing has changed yet. Every row must be valid before the entire stock file can be applied.' : 'Nothing has been imported. Correct rows here or exclude them from this run.'}</p></div>
      <SummaryCards summary={preview.summary} outcome={preview.outcome} />
      <div className={`import-notice ${stockBlocked || issueCount ? 'warning' : 'success'}`}>{stockBlocked || issueCount ? <AlertTriangle size={18} /> : <CheckCircle2 size={18} />}<span><strong>{stockBlocked ? 'This stock import is blocked' : issueCount ? `${formatNumber(issueCount)} row(s) need a decision` : 'Every row is ready'}</strong><small>{stockBlocked ? 'Fix every row. No stock will change unless the whole file can be applied in one transaction.' : issueCount ? 'Fix the values, exclude those rows, or continue with the valid rows.' : isStockImport ? 'Matching quantities will be skipped; every difference will be applied together in one transaction.' : 'Review the proposed changes before confirming.'}</small></span></div>
      <div className="review-toolbar"><div className="import-segmented" aria-label="Row status filter">{rowFilters.map(([value, label]) => <button className={state === value ? 'active' : ''} key={label} onClick={() => setState(value)} type="button">{label}</button>)}</div><form onSubmit={(event) => { event.preventDefault(); setSearch(searchDraft); }}><Search size={16} /><input aria-label="Search preview rows" placeholder="Search SKU, barcode, name" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} /></form></div>
      <div className="review-table-wrap"><table className="review-table"><thead><tr><th>Row</th><th>SKU / barcode</th><th>Product</th><th>Result</th><th>Issue or proposed change</th><th><span className="sr-only">Actions</span></th></tr></thead><tbody>{rowsData.rows.map((row) => <tr key={row.id} className={row.excluded ? 'excluded' : ''}><td>{row.row_number}</td><td><strong>{row.sku || '—'}</strong><small>{row.barcode || ''}</small></td><td>{row.product_name || '—'}</td><td><StatusPill state={row.state} /></td><td>{row.issues?.[0] ? <span className="row-message issue">{row.issues[0].message}</span> : <span className="row-change-summary">{Object.values(row.proposed_changes || {}).slice(0, 2).map((change) => change.label).join(', ') || 'No data changes'}{Object.keys(row.proposed_changes || {}).length > 2 && ` +${Object.keys(row.proposed_changes).length - 2}`}</span>}</td><td><div className="row-actions"><button aria-label={`Edit row ${row.row_number}`} onClick={() => setEditing(row)} type="button"><Pencil size={16} /></button>{(!isStockImport || row.excluded) && <button aria-label={`${row.excluded ? 'Include' : 'Exclude'} row ${row.row_number}`} onClick={() => updateRow(row, { excluded: !row.excluded })} type="button">{row.excluded ? <RotateCcw size={16} /> : <X size={16} />}</button>}</div></td></tr>)}</tbody></table>{!rowsData.rows.length && <div className="review-empty">No rows match this filter.</div>}</div>
      <div className="review-pagination"><span>{formatNumber(rowsData.total)} row(s)</span><div><button disabled={rowsData.page <= 1 || busy} onClick={() => loadRows(rowsData.page - 1)} type="button">Previous</button><span>Page {rowsData.page} of {Math.max(rowsData.total_pages, 1)}</span><button disabled={rowsData.page >= rowsData.total_pages || busy} onClick={() => loadRows(rowsData.page + 1)} type="button">Next</button></div></div>
      <div className="import-stage-actions"><button className="import-quiet-button" onClick={onBack} type="button"><ArrowLeft size={17} /> Back</button><button className="import-primary-button" disabled={busy || stockBlocked || (!isStockImport && !preview.summary?.ready_count)} onClick={onContinue} type="button">Review import <ArrowRight size={17} /></button></div>
      {editing && <RowEditor busy={busy} fields={fields} row={editing} onClose={() => setEditing(null)} onSave={(values) => updateRow(editing, { values })} />}
    </section>
  );
}

function ConfirmStep({ preview, rowsData, onLoadPage, onBack, onCommit, busy }) {
  const [confirmed, setConfirmed] = useState(false);
  const [typed, setTyped] = useState('');
  const isStockImport = preview.outcome === 'update_stock';
  const readyCount = preview.summary?.ready_count || 0;
  const noStockChanges = isStockImport && readyCount === 0;
  const confirmationWord = preview.outcome === 'starting_inventory' ? 'START' : isStockImport && !noStockChanges ? 'STOCK' : '';
  const stockBlocked = isStockImport && stockImportBlocked(preview.summary);
  const enabled = confirmed && (!confirmationWord || typed === confirmationWord) && !stockBlocked;
  const rows = rowsData.rows || [];
  const proposedChanges = rows.flatMap((row) => Object.values(row.proposed_changes || {}).map((change) => ({ ...change, row_id: row.id, sku: row.sku })));
  return (
    <section className="import-stage wide" aria-labelledby="confirm-title">
      <div className="import-stage-heading"><span>Step 5</span><h3 id="confirm-title">Review changes before import</h3><p>{preview.outcome === 'update_stock' ? 'The entire CSV is one transaction. Matching stock stays unchanged, every difference is applied together, and any issue stops the whole file—there is no partial import.' : 'The preview is saved. Every source row is available page by page; if an item changed since validation, commit will stop and ask you to refresh.'}</p></div>
      <SummaryCards summary={preview.summary} outcome={preview.outcome} />
      <div className="confirm-protection"><ShieldCheck size={22} /><div><strong>{preview.outcome_content?.changes}</strong><p>{preview.outcome_content?.does_not_change}</p></div></div>
      <div className="change-table-wrap"><table className="change-table"><thead><tr><th>SKU</th><th>Field</th><th>Current value</th><th>New value</th></tr></thead><tbody>{proposedChanges.map((change) => <tr key={`${change.row_id}-${change.field}`}><td>{change.sku}</td><td>{change.label}</td><td>{String(change.before ?? 'Blank')}</td><td>{String(change.after ?? 'Blank')}</td></tr>)}</tbody></table>{!proposedChanges.length && <div className="review-empty">No field-level changes on this page.</div>}</div>
      <div className="review-pagination"><span>{formatNumber(rowsData.total || 0)} source row(s) available for review</span><div><button disabled={rowsData.page <= 1 || busy} onClick={() => onLoadPage(rowsData.page - 1)} type="button">Previous</button><span>Page {rowsData.page} of {Math.max(rowsData.total_pages, 1)}</span><button disabled={rowsData.page >= rowsData.total_pages || busy} onClick={() => onLoadPage(rowsData.page + 1)} type="button">Next</button></div></div>
      {noStockChanges && <div className="import-notice success"><CheckCircle2 size={18} /><span><strong>No stock changes needed</strong><small>Every quantity already matches this CSV. Finishing records the completed check without creating a stock adjustment.</small></span></div>}
      {stockBlocked && <div className="import-notice warning"><AlertTriangle size={18} /><span><strong>Import blocked</strong><small>Return to review and fix every row. No stock rows will import separately.</small></span></div>}
      {preview.outcome !== 'update_stock' && hasBlockingIssues(preview.summary) && <div className="import-notice warning"><AlertTriangle size={18} /><span><strong>Only valid rows will import</strong><small>Rows needing attention stay unchanged and will be available as a correction file in the results.</small></span></div>}
      {confirmationWord && <label className="typed-confirm"><span>Type <strong>{confirmationWord}</strong> to confirm this audited stock change</span><input aria-label={`Type ${confirmationWord} to confirm`} autoComplete="off" value={typed} onChange={(event) => setTyped(event.target.value.toUpperCase())} /></label>}
      <label className="import-checkbox-card confirmation"><input checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} type="checkbox" /><span><strong>{preview.outcome === 'update_stock' ? 'I reviewed every row and understand the whole file is applied as one transaction' : 'I reviewed the outcome, valid row count, and applicable change pages'}</strong><small>{preview.outcome === 'update_stock' ? 'Matching quantities are skipped; any validation or stale-data issue stops all stock changes.' : 'I understand this action creates an audit record and cannot silently overwrite newer data.'}</small></span></label>
      <div className="import-stage-actions"><button className="import-quiet-button" onClick={onBack} type="button"><ArrowLeft size={17} /> Back</button><button className="import-primary-button" disabled={!enabled || busy} onClick={onCommit} type="button">{busy ? 'Importing safely…' : preview.outcome === 'starting_inventory' ? 'Record starting inventory' : noStockChanges ? 'Finish — no stock changes' : isStockImport ? `Apply ${formatNumber(readyCount)} stock change${readyCount === 1 ? '' : 's'}` : `Import ${formatNumber(readyCount)} ready item${readyCount === 1 ? '' : 's'}`} <Check size={17} /></button></div>
    </section>
  );
}

function ResultsStep({ preview, onNewImport }) {
  const result = preview.result || {};
  const success = result.status === 'completed';
  return (
    <section className="import-stage result-stage" aria-labelledby="result-title">
      <div className={`result-icon ${success ? 'success' : 'warning'}`}>{success ? <CheckCircle2 size={34} /> : <AlertTriangle size={34} />}</div>
      <div className="import-stage-heading"><span>Step 6</span><h3 id="result-title">{success ? 'Import completed' : 'Import completed with attention needed'}</h3><p>The job is recorded in import history with its file, user, result, field changes, and errors.</p></div>
      <div className="result-metrics"><div><span>Created</span><strong>{formatNumber(result.created_count)}</strong></div><div><span>Updated</span><strong>{formatNumber(result.updated_count)}</strong></div><div><span>Unchanged</span><strong>{formatNumber(result.unchanged_count)}</strong></div><div><span>Excluded</span><strong>{formatNumber(result.excluded_count)}</strong></div><div><span>Failed</span><strong>{formatNumber(result.failed_count)}</strong></div></div>
      <div className="result-reference"><span>Import job #{result.import_job_id}</span><span>{formatNumber(result.duration_ms)} ms</span>{result.starting_units > 0 && <span>{formatNumber(result.starting_units)} starting units</span>}{result.stock_adjustment_id && <span>Stock adjustment #{result.stock_adjustment_id}</span>}{result.woo_stock_sync_job_id && <span>Woo stock sync #{result.woo_stock_sync_job_id} queued</span>}{result.outcome === 'update_stock' && <span>{formatNumber(result.stock_units_delta)} net stock change</span>}</div>
      <div className="result-actions"><a className="import-primary-button" href="#items">Return to items</a><a className="import-secondary-button" href="#/items/imports"><History size={17} /> View history</a>{result.failed_count > 0 && <a className="import-secondary-button" href={`${API_BASE_URL}/api/import-jobs/${result.import_job_id}/failed-rows`}><Download size={17} /> Download rows to fix</a>}<button className="import-quiet-button" onClick={onNewImport} type="button">Start another import</button></div>
    </section>
  );
}

export function ItemImportWorkspace({ initialPreviewId = '', initialOutcome = '', onCommitted = null }) {
  const workspaceRef = useRef(null);
  const [schema, setSchema] = useState(null);
  const [outcome, setOutcome] = useState(initialOutcome);
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [step, setStep] = useState(initialOutcome ? 2 : 1);
  const [maxStep, setMaxStep] = useState(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [confirmRows, setConfirmRows] = useState({ rows: [], total: 0, page: 1, page_size: 25, total_pages: 0 });

  useEffect(() => {
    requestJson('/api/items/import/schema').then(setSchema).catch((requestError) => setError(requestError.message));
  }, []);

  useEffect(() => {
    const resumeId = initialPreviewId || (!initialOutcome && sessionStorage.getItem(PREVIEW_KEY));
    if (!resumeId) return;
    setBusy(true);
    requestJson(`/api/items/import/previews/${resumeId}`).then((saved) => {
      setPreview(saved);
      setOutcome(saved.outcome);
      const nextStep = saved.status === 'committed' ? 6 : (saved.status === 'draft' ? 3 : 4);
      setStep(nextStep);
      setMaxStep(Math.max(nextStep, saved.status === 'ready' ? 5 : nextStep));
    }).catch(() => sessionStorage.removeItem(PREVIEW_KEY)).finally(() => setBusy(false));
  }, [initialOutcome, initialPreviewId]);

  useEffect(() => {
    const heading = workspaceRef.current?.querySelector('.import-stage-heading h3');
    if (heading) {
      heading.tabIndex = -1;
      heading.focus();
    }
  }, [step]);

  function remember(saved) {
    setPreview(saved);
    sessionStorage.setItem(PREVIEW_KEY, saved.preview_id);
    window.history.replaceState(null, '', `#/items/import?preview=${saved.preview_id}`);
  }

  async function upload() {
    setBusy(true);
    setError('');
    const form = new FormData();
    form.append('outcome', outcome);
    form.append('file', file);
    try {
      const saved = await requestJson('/api/items/import/previews', { method: 'POST', body: form }, 'The CSV could not be uploaded.');
      remember(saved);
      setStep(3);
      setMaxStep(3);
      const requiredFields = outcomeSchema(schema, outcome)?.required_fields || [];
      const mappedFields = new Set(Object.values(saved.mapping || {}).filter(Boolean));
      if (outcome === 'update_stock' && requiredFields.every((field) => mappedFields.has(field))) {
        const validated = await requestJson(`/api/items/import/previews/${saved.preview_id}/mapping`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ mapping: saved.mapping, allow_blank_clears: false }) }, 'Stock rows could not be validated.');
        remember(validated);
        setStep(4);
        setMaxStep(4);
      }
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function loadConfirmRows(page = 1) {
    setBusy(true);
    setError('');
    try {
      const rows = await requestJson(`/api/items/import/previews/${preview.preview_id}/rows?page=${page}&page_size=25`);
      setConfirmRows(rows);
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function prepareConfirm() {
    if (await loadConfirmRows(1)) {
      setStep(5);
      setMaxStep(5);
    }
  }

  async function commit() {
    setBusy(true);
    setError('');
    try {
      await requestJson(`/api/items/import/previews/${preview.preview_id}/commit`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ idempotency_key: newIdempotencyKey() }) }, 'The import could not be committed.');
      const saved = await requestJson(`/api/items/import/previews/${preview.preview_id}`);
      remember(saved);
      await onCommitted?.();
      setStep(6);
      setMaxStep(6);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (preview && !['committed', 'cancelled'].includes(preview.status)) {
      await requestJson(`/api/items/import/previews/${preview.preview_id}/cancel`, { method: 'POST' }).catch(() => null);
    }
    sessionStorage.removeItem(PREVIEW_KEY);
    window.location.hash = '#items';
  }

  function reset() {
    sessionStorage.removeItem(PREVIEW_KEY);
    window.history.replaceState(null, '', '#/items/import');
    setOutcome(''); setFile(null); setPreview(null); setConfirmRows([]); setStep(1); setMaxStep(2); setError('');
  }

  const intro = outcomeSchema(schema, outcome);
  return (
    <section className="item-import-workspace" ref={workspaceRef}>
      <PageIntro title="Import items" description={intro ? `${intro.label}: ${intro.description}` : 'A guided workspace for adding items, updating details, overriding stock, or recording starting inventory.'} onCancel={preview || step > 1 ? cancel : null} />
      <Stepper current={step} maxStep={maxStep} onChange={setStep} />
      {error && <div className="import-error" role="alert"><AlertTriangle size={18} /><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')} type="button"><X size={16} /></button></div>}
      {!schema && !error && <div className="import-loading"><RefreshCw size={20} /> Loading import rules…</div>}
      {schema && step === 1 && <OutcomeStep schema={schema} outcome={outcome} setOutcome={setOutcome} onContinue={() => { setStep(2); setMaxStep(2); }} />}
      {schema && step === 2 && <UploadStep schema={schema} outcome={outcome} file={file} setFile={setFile} onUpload={upload} busy={busy} onBack={() => setStep(1)} />}
      {schema && preview && step === 3 && <MappingStep schema={schema} preview={preview} setPreview={(saved) => { remember(saved); setMaxStep(saved.status === 'ready' ? 4 : 3); }} onContinue={() => { setStep(4); setMaxStep(4); }} onBack={() => setStep(2)} busy={busy} setBusy={setBusy} setError={setError} />}
      {schema && preview && step === 4 && <ReviewStep schema={schema} preview={preview} setPreview={remember} onContinue={prepareConfirm} onBack={() => setStep(3)} busy={busy} setBusy={setBusy} setError={setError} />}
      {preview && step === 5 && <ConfirmStep preview={preview} rowsData={confirmRows} onLoadPage={loadConfirmRows} onBack={() => setStep(4)} onCommit={commit} busy={busy} />}
      {preview && step === 6 && <ResultsStep preview={preview} onNewImport={reset} />}
    </section>
  );
}

export function ItemImportHistory({ onRolledBack = null }) {
  const [jobs, setJobs] = useState([]);
  const [jobsPagination, setJobsPagination] = useState({ page: 1, page_size: 50, total: 0, total_pages: 0, has_previous: false, has_next: false });
  const [outcome, setOutcome] = useState('');
  const [status, setStatus] = useState('');
  const [expanded, setExpanded] = useState(null);
  const [changes, setChanges] = useState([]);
  const [changesPagination, setChangesPagination] = useState({ page: 1, page_size: 50, total: 0, total_pages: 0, has_previous: false, has_next: false });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function load(page = 1, pageSize = jobsPagination.page_size || 50) {
    setBusy(true);
    try {
      const params = new URLSearchParams({ item_imports_only: 'true', page: String(page), page_size: String(pageSize) });
      if (outcome) params.set('outcome', outcome);
      if (status) params.set('status', status);
      const body = await requestJson(`/api/import-jobs?${params}`);
      setJobs(body.jobs || []);
      setJobsPagination({
        page: body.page || 1,
        page_size: body.page_size || pageSize,
        total: body.total || 0,
        total_pages: body.total_pages || 0,
        has_previous: Boolean(body.has_previous),
        has_next: Boolean(body.has_next),
      });
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => { load(1); }, [outcome, status]);

  async function loadChanges(jobId, page = 1, pageSize = changesPagination.page_size || 50) {
    const body = await requestJson(`/api/import-jobs/${jobId}/changes?page=${page}&page_size=${pageSize}`);
    setChanges(body.changes || []);
    setChangesPagination({
      page: body.page || 1,
      page_size: body.page_size || pageSize,
      total: body.total || 0,
      total_pages: body.total_pages || 0,
      has_previous: Boolean(body.has_previous),
      has_next: Boolean(body.has_next),
    });
  }

  async function toggle(job) {
    if (expanded === job.id) { setExpanded(null); return; }
    setExpanded(job.id);
    setChanges([]);
    setChangesPagination({ page: 1, page_size: 50, total: 0, total_pages: 0, has_previous: false, has_next: false });
    if (job.outcome !== 'starting_inventory') await loadChanges(job.id, 1, 50).catch(() => setChanges([]));
  }

  async function rollback(job) {
    if (!window.confirm('Restore only the metadata fields changed by this import? This will stop if any of those fields has changed since the import. Inventory quantities will not change.')) return;
    setBusy(true);
    try {
      await requestJson(`/api/import-jobs/${job.id}/rollback`, { method: 'POST' });
      await load(jobsPagination.page, jobsPagination.page_size);
      await onRolledBack?.();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="item-import-workspace history-page">
      <PageIntro title="Item import history" description="Every item import, who ran it, what changed, and which rows need attention." />
      {error && <div className="import-error" role="alert"><AlertTriangle size={18} /><span>{error}</span></div>}
      <div className="history-toolbar"><a className="import-primary-button" href="#/items/import" onClick={() => sessionStorage.removeItem(PREVIEW_KEY)}><PackagePlus size={17} /> New import</a><label><span>Outcome</span><select value={outcome} onChange={(event) => setOutcome(event.target.value)}><option value="">All outcomes</option><option value="add_items">Add new items</option><option value="update_items">Update item details</option><option value="update_stock">Override stock levels</option><option value="starting_inventory">Set starting inventory</option></select></label><label><span>Status</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="">All statuses</option><option value="completed">Completed</option><option value="completed_with_errors">Completed with errors</option><option value="failed">Failed</option></select></label><button className="import-secondary-button" disabled={busy} onClick={() => load(jobsPagination.page, jobsPagination.page_size)} type="button"><RefreshCw size={16} /> Refresh</button></div>
      <div className="history-table-wrap">
        <table className="history-table">
          <thead><tr><th>Import</th><th>Outcome</th><th>File</th><th>Result</th><th>Rows</th><th>Run by</th><th>Completed</th><th></th></tr></thead>
          {jobs.map((job) => (
            <tbody key={job.id} className="history-job-group">
              <tr>
                <td><strong>#{job.id}</strong></td>
                <td>{job.outcome?.replaceAll('_', ' ')}</td>
                <td>{job.file_name || '—'}</td>
                <td><StatusPill state={job.status} /></td>
                <td>{formatNumber(job.successful_rows)} successful · {formatNumber(job.failed_rows)} failed</td>
                <td>{job.created_by || 'System'}</td>
                <td>{formatDate(job.completed_at || job.created_at)}</td>
                <td><button className="history-expand" onClick={() => toggle(job)} type="button" aria-expanded={expanded === job.id}><ChevronDown size={17} /></button></td>
              </tr>
              {expanded === job.id && (
                <tr className="history-detail-row"><td colSpan="8"><div className="history-detail">
                  <div><strong>Job summary</strong><p>{formatNumber(job.created_rows)} created · {formatNumber(job.updated_rows)} updated · {formatNumber(job.unchanged_rows)} unchanged · {formatNumber(job.excluded_rows)} excluded</p><p>{job.outcome?.replaceAll('_', ' ')} · run by {job.created_by || 'System'} · completed {formatDate(job.completed_at || job.created_at)}</p>{job.starting_units > 0 && <p>{formatNumber(job.starting_units)} starting units recorded</p>}</div>
                  <div className="history-detail-actions"><a className="import-secondary-button" href={`${API_BASE_URL}/api/import-jobs/${job.id}/source-file`}><FileSpreadsheet size={16} /> Original CSV</a>{job.failed_rows > 0 && <a className="import-secondary-button" href={`${API_BASE_URL}/api/import-jobs/${job.id}/failed-rows`}><Download size={16} /> Rows to fix</a>}{job.outcome === 'update_items' && !(job.result_json?.rollback?.status === 'completed') && <button className="import-secondary-button" disabled={busy} onClick={() => rollback(job)} type="button"><RotateCcw size={16} /> Safe metadata rollback</button>}</div>
                  {changesPagination.total > 0 && <div className="history-change-list"><strong>Field changes · {changesPagination.total} total</strong>{changes.map((change) => <p key={change.id}><span>{change.sku} · {change.field.replaceAll('_', ' ')}</span><small>{String(change.before ?? 'Blank')} → {String(change.after ?? 'Blank')}</small></p>)}<div className="history-pagination" aria-label="Import field changes pages"><button className="import-secondary-button" disabled={!changesPagination.has_previous || busy} onClick={() => loadChanges(job.id, changesPagination.page - 1, changesPagination.page_size)} type="button">Previous changes</button><span>Page {changesPagination.page} of {Math.max(1, changesPagination.total_pages)}</span><button className="import-secondary-button" disabled={!changesPagination.has_next || busy} onClick={() => loadChanges(job.id, changesPagination.page + 1, changesPagination.page_size)} type="button">Next changes</button></div></div>}
                </div></td></tr>
              )}
            </tbody>
          ))}
        </table>
        {!jobs.length && !busy && <div className="review-empty">No item imports match these filters.</div>}
      </div>
      <div className="history-pagination" aria-label="Item import history pages"><button className="import-secondary-button" disabled={!jobsPagination.has_previous || busy} onClick={() => load(jobsPagination.page - 1, jobsPagination.page_size)} type="button">Previous imports</button><span>{jobsPagination.total} imports · Page {jobsPagination.page} of {Math.max(1, jobsPagination.total_pages)}</span><button className="import-secondary-button" disabled={!jobsPagination.has_next || busy} onClick={() => load(jobsPagination.page + 1, jobsPagination.page_size)} type="button">Next imports</button></div>
    </section>
  );
}
