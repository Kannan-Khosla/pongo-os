import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SmartBuying from './SmartBuying';
import data from './smartBuyingData.json';
import { calculatePlan, copilotAnswer, defaults, money } from './smartBuyingEngine';

vi.mock('echarts', () => ({ init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), on: vi.fn(), off: vi.fn() }) }));
vi.mock('echarts/core', () => ({ use: vi.fn(), init: () => ({ setOption: vi.fn(), resize: vi.fn(), dispose: vi.fn(), on: vi.fn(), off: vi.fn() }) }));

const product = data.products[0];
const metric = (label) => screen.getByText(label, { exact: true }).parentElement;
const caseInput = (name = product.name) => screen.getByRole('spinbutton', { name: `Cases for ${name}` });
const inspectButton = () => screen.getByRole('button', { name: new RegExp(`^${product.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`) });

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new Error('Unexpected request in local Smart Buying flow'))));
  vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:smart-buying-document'), revokeObjectURL: vi.fn() }));
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.sessionStorage.clear();
});

describe('Smart Buying investor workflows', () => {
  it('uses planning language across every view while retaining reference-data provenance', () => {
    const { rerender } = render(<SmartBuying />);
    for (const view of ['overview', 'purchase-plan', 'forecast', 'supplier-deals', 'opportunities', 'draft-pos', 'suppliers', 'scenarios']) {
      rerender(<SmartBuying view={view} />);
      expect(document.body.textContent).not.toMatch(/\b(demo|mock|prototype|demonstration)\b/i);
      expect(screen.getByText('Planning intelligence · September reference snapshot · session drafts')).toBeVisible();
    }
    expect(data.mode).toBe('snapshot');
    expect(data.metadata.disclosure).toContain('Supplier accounts and live operational records are not connected');
    expect(data.sources.every((source) => source.notes.includes('Supplier connections are not enabled'))).toBe(true);
  });

  it('renders the deterministic executive KPIs and all eight navigation destinations', () => {
    const plan = calculatePlan(data);
    render(<SmartBuying />);
    expect(screen.getByRole('heading', { level: 1, name: 'Smart Buying Intelligence' })).toBeVisible();
    expect(metric('Recommended purchase')).toHaveTextContent(money(plan.metrics.spend));
    expect(metric('Inventory coverage')).toHaveTextContent(`${Math.round(plan.metrics.coverage)} days`);
    expect(metric('Subscription coverage')).toHaveTextContent(`${plan.metrics.subscriptionCoverage.toFixed(1)}%`);
    const tabs = screen.getByRole('navigation', { name: 'Smart Buying views' });
    expect(within(tabs).getAllByRole('link')).toHaveLength(8);
    expect(within(tabs).getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');
    expect(within(tabs).getByRole('link', { name: 'Purchase Plan' })).toHaveAttribute('href', '#/smart-buying/purchase-plan');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('recalculates forecast horizon and exposes a complete SKU explanation with focus restoration', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="forecast" />);
    await user.click(screen.getByRole('button', { name: '90 days' }));
    expect(screen.getByRole('heading', { name: '90-day demand forecast' })).toBeVisible();
    const expected = calculatePlan(data, { horizon: 90 }).lines[0];
    const trigger = inspectButton();
    await user.click(trigger);
    const dialog = screen.getByRole('dialog', { name: 'Why this purchase quantity?' });
    expect(within(dialog).getByText('Upcoming subscription demand').parentElement).toHaveTextContent(`+ ${expected.subscriptionDemand}`);
    expect(within(dialog).getByText('Final purchase').parentElement).toHaveTextContent(`${expected.units} units / ${expected.cases} cases`);
    expect(within(dialog).getByRole('button', { name: 'Close dialog' })).toHaveFocus();
    await user.tab({ shift: true });
    expect(within(dialog).getByRole('button', { name: 'Review in purchase plan' })).toHaveFocus();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(document.body.style.overflow).not.toBe('hidden');
  });

  it('updates strategy metrics and retains pinned quantities through optimization', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="purchase-plan" />);
    await user.click(screen.getByRole('button', { name: /^Cash Conservative/ }));
    expect(screen.getByRole('button', { name: /^Cash Conservative/ })).toHaveAttribute('aria-pressed', 'true');
    const conservative = calculatePlan(data, { strategy: 'conservative' });
    expect(metric('Proposed spend')).toHaveTextContent(money(conservative.metrics.spend));
    fireEvent.change(caseInput(), { target: { value: '8' } });
    await user.click(screen.getByRole('button', { name: `Pin ${product.name}` }));
    await user.click(screen.getByRole('button', { name: 'Optimize Purchase Plan' }));
    expect(caseInput()).toHaveValue(8);
    expect(screen.getByRole('button', { name: `Pin ${product.name}` })).toHaveAttribute('aria-pressed', 'true');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('edits and excludes a line, updates the spend, and invalidates local approval', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="purchase-plan" />);
    await user.click(screen.getByRole('button', { name: 'Accept recommendation' }));
    expect(screen.getByRole('button', { name: 'Plan accepted' })).toBeDisabled();
    fireEvent.change(caseInput(), { target: { value: '12' } });
    const edited = calculatePlan(data, defaults, { [product.id]: { cases: 12 } });
    expect(caseInput()).toHaveValue(12);
    expect(metric('Proposed spend')).toHaveTextContent(money(edited.metrics.spend));
    expect(screen.getByRole('button', { name: 'Accept recommendation' })).toBeEnabled();
    await user.click(screen.getByRole('checkbox', { name: `Include ${product.name}` }));
    expect(caseInput()).toBeDisabled();
    const excluded = calculatePlan(data, defaults, { [product.id]: { cases: 12, excluded: true } });
    expect(metric('Proposed spend')).toHaveTextContent(money(excluded.metrics.spend));
    await user.click(screen.getByRole('checkbox', { name: `Include ${product.name}` }));
    expect(caseInput()).toHaveValue(12);
  });

  it('optimizes to a cash budget including freight and tax', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="purchase-plan" />);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Available buying budget' }), { target: { value: '25000' } });
    await user.click(screen.getByRole('button', { name: 'Optimize to Budget' }));
    const expected = calculatePlan(data, { budget: 25000, budgetMode: true, optimize: true });
    expect(expected.metrics.spend).toBeLessThanOrEqual(25000);
    expect(metric('Proposed spend')).toHaveTextContent(money(expected.metrics.spend));
    expect(screen.getByRole('status')).toHaveTextContent('Plan optimized to your cash budget');
    expect(screen.getByText(/remains in your buying budget/)).toBeVisible();
  });

  it('recalculates a scenario and applies it to the purchase plan', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SmartBuying view="scenarios" />);
    fireEvent.change(screen.getByRole('slider', { name: /Demand growth/ }), { target: { value: '20' } });
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Cash budget (CAD)' }), { target: { value: '30000' } });
    await user.selectOptions(screen.getByRole('combobox', { name: 'Safety stock' }), 'high');
    const expected = calculatePlan(data, { ...defaults, growth: 20, budget: 30000, safety: 'high', budgetMode: true, optimize: true });
    expect(screen.getByRole('heading', { level: 2, name: money(expected.metrics.spend) })).toBeVisible();
    expect(metric('Projected margin')).toHaveTextContent(`${expected.metrics.margin.toFixed(1)}%`);
    await user.click(screen.getByRole('button', { name: 'Use this scenario' }));
    expect(window.location.hash).toBe('#/smart-buying/purchase-plan');
    rerender(<SmartBuying view="purchase-plan" />);
    expect(metric('Proposed spend')).toHaveTextContent(money(expected.metrics.spend));
    expect(screen.getByRole('spinbutton', { name: 'Available buying budget' })).toHaveValue(30000);
    expect(screen.getByRole('status')).toHaveTextContent('Scenario applied to the purchase plan');
  });

  it('keeps other budgeted lines unchanged when manually adjusting one product', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="purchase-plan" />);
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Available buying budget' }), { target: { value: '25000' } });
    await user.click(screen.getByRole('button', { name: 'Optimize to Budget' }));
    const budgeted = calculatePlan(data, { budget: 25000, budgetMode: true, optimize: true });
    const cases = budgeted.lines[0].cases + 1;
    fireEvent.change(caseInput(), { target: { value: String(cases) } });
    const adjustments = Object.fromEntries(budgeted.lines.map((line) => [line.id, { cases: line.id === product.id ? cases : line.cases, pinned: line.pinned, excluded: line.excluded }]));
    const expected = calculatePlan(data, { ...budgeted.options, budgetMode: false }, adjustments);
    expect(caseInput()).toHaveValue(cases);
    for (const line of budgeted.lines.slice(1)) expect(caseInput(line.name)).toHaveValue(line.cases);
    expect(metric('Proposed spend')).toHaveTextContent(money(expected.metrics.spend));
  });

  it('recalculates unpinned quantities after a policy change while preserving pins and exclusions', async () => {
    const user = userEvent.setup();
    const pinned = data.products[1];
    const excluded = data.products[2];
    render(<SmartBuying view="purchase-plan" />);
    fireEvent.change(caseInput(), { target: { value: '8' } });
    fireEvent.change(caseInput(pinned.name), { target: { value: '10' } });
    await user.click(screen.getByRole('button', { name: `Pin ${pinned.name}` }));
    await user.click(screen.getByRole('checkbox', { name: `Include ${excluded.name}` }));
    await user.click(screen.getByRole('button', { name: '90 days' }));
    const protectedRows = { [pinned.id]: { cases: 10, pinned: true }, [excluded.id]: { excluded: true } };
    const extended = calculatePlan(data, { horizon: 90 }, protectedRows);
    expect(caseInput()).toHaveValue(extended.lines[0].cases);
    expect(caseInput(pinned.name)).toHaveValue(10);
    expect(screen.getByRole('checkbox', { name: `Include ${excluded.name}` })).not.toBeChecked();
    expect(metric('Proposed spend')).toHaveTextContent(money(extended.metrics.spend));
    await user.click(screen.getByRole('button', { name: /^Cash Conservative/ }));
    const conservative = calculatePlan(data, { horizon: 90, strategy: 'conservative' }, protectedRows);
    expect(caseInput()).toHaveValue(conservative.lines[0].cases);
    expect(metric('Proposed spend')).toHaveTextContent(money(conservative.metrics.spend));
  });

  it('applies the exact 20% reduction quoted by the copilot for the current edited basket', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<SmartBuying view="purchase-plan" />);
    fireEvent.change(caseInput(), { target: { value: '100' } });
    const edited = calculatePlan(data, {}, { [product.id]: { cases: 100 } });
    const snapshot = Object.fromEntries(edited.lines.map((line) => [line.id, { cases: line.cases, pinned: line.pinned, excluded: line.excluded }]));
    const budget = Math.round((edited.metrics.spend * .8 + Number.EPSILON) * 100) / 100;
    const expected = calculatePlan(data, { ...defaults, budget, budgetMode: true, optimize: true }, snapshot);
    rerender(<SmartBuying view="overview" />);
    const question = 'What happens if I reduce this purchase by 20%?';
    await user.click(screen.getByRole('button', { name: question }));
    expect(screen.getByText(copilotAnswer(question, edited, data, defaults))).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Compare a 20% lower budget' }));
    rerender(<SmartBuying view="purchase-plan" />);
    expect(screen.getByRole('spinbutton', { name: 'Available buying budget' })).toHaveValue(budget);
    expect(metric('Proposed spend')).toHaveTextContent(money(expected.metrics.spend));
    for (const line of expected.lines) expect(caseInput(line.name)).toHaveValue(line.cases);
  });

  it('removes a minimum-sized purchase when the minus control would otherwise be a no-op', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="purchase-plan" />);
    fireEvent.change(caseInput(), { target: { value: String(Math.ceil(product.moq / product.casePack)) } });
    await user.click(screen.getByRole('button', { name: `Reduce ${product.name}` }));
    expect(caseInput()).toHaveValue(0);
    expect(screen.getByRole('button', { name: `Reduce ${product.name}` })).toBeDisabled();
  });

  it('previews and approves a draft without sending any supplier request', async () => {
    const user = userEvent.setup();
    render(<SmartBuying view="draft-pos" />);
    await user.click(screen.getAllByRole('button', { name: 'Preview PO' })[0]);
    const dialog = screen.getByRole('dialog', { name: 'DRAFT-20260909-01' });
    expect(within(dialog).getByRole('region', { name: 'Draft order lines' })).toBeVisible();
    expect(within(dialog).getByText('Final purchase cost').parentElement).toHaveTextContent(money(calculatePlan(data).groups[0].total));
    await user.click(within(dialog).getByRole('button', { name: 'Preview Send' }));
    expect(within(dialog).getByText('Preview only. Nothing has been sent, and no supplier order exists.')).toBeVisible();
    await user.click(within(dialog).getByRole('button', { name: 'Approve purchase plan' }));
    expect(within(dialog).getByRole('button', { name: 'Plan approved locally' })).toBeDisabled();
    expect(fetch).not.toHaveBeenCalled();
  });

  it('reports export failure, retries the PDF download, and releases its object URL', async () => {
    const user = userEvent.setup();
    const downloads = [];
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () { downloads.push({ href: this.href, filename: this.download }); });
    fetch.mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'Export unavailable' }) }).mockResolvedValueOnce({ ok: true, blob: async () => new Blob(['%PDF-local-draft'], { type: 'application/pdf' }) });
    render(<SmartBuying view="draft-pos" />);
    await user.click(screen.getAllByRole('button', { name: 'Preview PO' })[0]);
    await user.click(screen.getByRole('button', { name: 'Export PDF' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Export unavailable');
    await user.click(screen.getByRole('button', { name: 'Export PDF' }));
    await waitFor(() => expect(downloads).toEqual([{ href: 'blob:smart-buying-document', filename: 'DRAFT-20260909-01.pdf' }]));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('PDF exported. Your draft remains local.');
    expect(fetch).toHaveBeenCalledTimes(2);
    const [url, request] = fetch.mock.calls[1];
    expect(String(url)).toMatch(/\/api\/smart-buying\/export\/pdf$/);
    expect(request.method).toBe('POST');
    const payload = JSON.parse(request.body);
    expect(payload.supplier_id).toBe('pacific');
    expect(payload.lines[0].product_id).toBe(product.id);
    await user.keyboard('{Escape}');
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:smart-buying-document');
  });

  it('finishes the deterministic analysis and presents the recalculated plan', async () => {
    const user = userEvent.setup();
    render(<SmartBuying />);
    await user.click(screen.getByRole('button', { name: 'Run buying analysis' }));
    expect(screen.getByRole('dialog', { name: 'Running Smart Buying analysis' })).toBeVisible();
    const dialog = await screen.findByRole('dialog', { name: 'Optimization complete' }, { timeout: 4000 });
    const expected = calculatePlan(data, { optimize: true });
    await waitFor(() => expect(within(dialog).getByRole('status')).toHaveTextContent(`${money(expected.metrics.spend)} recommended`));
    await user.click(within(dialog).getByRole('button', { name: 'Review optimized plan' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(window.location.hash).toBe('#/smart-buying/purchase-plan');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('loads from the existing sidebar, preserves Smart Buying state between views, and keeps Items navigation working', async () => {
    const user = userEvent.setup();
    fetch.mockImplementation(async () => ({ ok: true, json: async () => ({ items: [], locations: [], events: [], total: 0, page: 1, page_size: 20, total_pages: 0, categories: [], brands: [] }) }));
    window.location.hash = '#/smart-buying/overview';
    const { default: App } = await import('./App');
    render(<App currentUser={{ display_name: 'Buying Demo', email: 'demo@example.invalid', access_level: 'demo' }} />);
    await screen.findByRole('heading', { level: 1, name: 'Smart Buying Intelligence' });
    const nav = screen.getByRole('navigation', { name: 'Main navigation' });
    expect(within(nav).getByRole('button', { name: 'Smart Buying' })).toHaveAttribute('aria-expanded', 'true');
    await user.click(within(screen.getByRole('navigation', { name: 'Smart Buying views' })).getByRole('link', { name: 'Purchase Plan' }));
    await screen.findByRole('heading', { level: 1, name: 'Your purchase plan' });
    fireEvent.change(caseInput(), { target: { value: '9' } });
    await user.click(within(screen.getByRole('navigation', { name: 'Smart Buying views' })).getByRole('link', { name: 'Forecast' }));
    await screen.findByRole('heading', { level: 1, name: 'Demand forecast' });
    await user.click(inspectButton());
    expect(within(screen.getByRole('dialog')).getByText('Recommended buy').parentElement).toHaveTextContent('9 cases');
    await user.keyboard('{Escape}');
    await user.click(within(nav).getByRole('link', { name: 'Items' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Items' })).toBeVisible();
    expect(fetch.mock.calls.every(([, options]) => !options?.method || options.method === 'GET')).toBe(true);
  });
});
