import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BuyingCopilot, dealAdjustment, Opportunities, SupplierDeals, SupplierIntelligence } from './SmartBuyingSuppliers';
import data from './smartBuyingData.json';
import { calculatePlan, money } from './smartBuyingEngine';

afterEach(() => vi.unstubAllGlobals());

describe('Smart Buying supplier workflows', () => {
  it('filters offers, recovers from empty results, and reviews evidence without external requests', async () => {
    const user = userEvent.setup();
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const onApplyDeal = vi.fn();
    const onInspectSku = vi.fn();
    const calculated = calculatePlan(data);
    const plan = { ...calculated, lines: calculated.lines.map((line) => ({ ...line, discount: 0, savings: 0 })) };
    render(<SupplierDeals data={data} plan={plan} onApplyDeal={onApplyDeal} onInspectSku={onInspectSku} />);

    await user.selectOptions(screen.getByLabelText('Supplier'), 'pacific');
    const pacificDeals = data.deals.filter((deal) => deal.supplierId === 'pacific');
    expect(screen.getByRole('status')).toHaveTextContent(`${pacificDeals.length} of ${data.deals.length} offers`);
    await user.selectOptions(screen.getByLabelText('Source'), 'pdf');
    expect(screen.getAllByRole('article')).toHaveLength(pacificDeals.filter((deal) => deal.source === 'pdf').length);
    await user.click(screen.getAllByText('Review source & matching')[0]);
    expect(screen.getAllByText(/Prices are normalized to one sellable unit/)[0]).toBeVisible();
    await user.click(screen.getAllByRole('button', { name: 'Use offer' })[0]);
    expect(onApplyDeal).toHaveBeenCalledWith('acana-september');
    await user.click(screen.getByRole('button', { name: /471421 · ACANA Pacifica/ }));
    expect(onInspectSku).toHaveBeenCalledWith('acana-pacifica');
    await user.type(screen.getByLabelText('Search supplier deals'), 'nonexistent promotion');
    expect(screen.getByRole('heading', { name: 'No offers match these filters' })).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Reset deal filters' }));
    expect(screen.getAllByRole('article')).toHaveLength(data.deals.length);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('shows supplier scorecards and source evidence including captured time', async () => {
    const user = userEvent.setup();
    render(<SupplierIntelligence data={data} plan={calculatePlan(data)} />);
    expect(screen.getAllByRole('meter')).toHaveLength(data.suppliers.length);
    await user.click(screen.getByRole('button', { name: /Promotion PDFs/ }));
    const evidence = screen.getByRole('region', { name: 'Promotion PDFs evidence' });
    expect(within(evidence).getByText('Sep 9')).toBeVisible();
    expect(within(evidence).getByText(/uncertain matches require review/)).toBeVisible();
    expect(screen.queryByText('Invalid Date')).not.toBeInTheDocument();
  });

  it('answers from the current plan, offers a budget action, and handles unsupported questions locally', async () => {
    const user = userEvent.setup();
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    const plan = calculatePlan(data);
    const onReduceBudget = vi.fn();
    const onNavigate = vi.fn();
    render(<BuyingCopilot data={data} plan={plan} options={{ horizon: 60 }} onReduceBudget={onReduceBudget} onNavigate={onNavigate} />);
    expect(screen.getByText((text) => text.startsWith(`Buy ${money(plan.metrics.spend)} across`))).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'What happens if I reduce this purchase by 20%?' }));
    await user.click(screen.getByRole('button', { name: 'Compare a 20% lower budget' }));
    expect(onReduceBudget).toHaveBeenCalledOnce();
    await user.type(screen.getByLabelText('Ask Buying Copilot', { selector: 'input' }), 'Is it raining?');
    await user.click(screen.getByRole('button', { name: 'Ask Buying Copilot' }));
    expect(screen.getByText('I can explain the buying decisions in this plan.')).toBeVisible();
    await user.click(screen.getByRole('button', { name: 'Explore the purchase plan' }));
    expect(onNavigate).toHaveBeenCalledWith('purchase-plan');
    expect(fetch).not.toHaveBeenCalled();
  });

  it('applies the actual forecast quantity from a stockout opportunity', async () => {
    const user = userEvent.setup();
    const plan = calculatePlan(data);
    const urgent = [...plan.lines].sort((a, b) => a.daysCover - b.daysCover)[0];
    const onAdjust = vi.fn();
    render(<Opportunities data={data} plan={plan} onAdjust={onAdjust} onNavigate={vi.fn()} />);
    await user.click(screen.getByRole('button', { name: 'Accept recommended quantity' }));
    expect(onAdjust).toHaveBeenCalledWith(urgent.id, { cases: urgent.recommendedCases, excluded: false });
    expect(screen.getByRole('status')).toHaveTextContent(`${urgent.recommendedCases} cases`);
  });

  it('compares complete baskets when free-case and freight thresholds change', () => {
    const product = data.products.find((item) => item.dealId === 'go-case-bonus');
    const sourceSupplier = data.suppliers.find((item) => item.id === product.supplierId);
    const supplier = { ...sourceSupplier, freeFreight: product.cost * product.casePack * 20, freight: 200 };
    const fixture = { ...data, products: [product], suppliers: [supplier], deals: data.deals.filter((deal) => deal.id === product.dealId) };
    const plan = calculatePlan(fixture, {}, { [product.id]: { cases: 21 } });
    const increased = calculatePlan(fixture, {}, { [product.id]: { cases: 22 } });
    const reduced = calculatePlan(fixture, {}, { [product.id]: { cases: 20 } });
    expect(increased.metrics.spend).toBe(plan.metrics.spend);
    expect(reduced.metrics.spend).toBeGreaterThan(plan.metrics.spend);
    render(<Opportunities data={fixture} plan={plan} onAdjust={vi.fn()} onNavigate={vi.fn()} />);
    const promotion = screen.getByRole('button', { name: 'Add one promotional case' }).closest('article');
    expect(within(promotion).getByText(money(increased.metrics.savings - plan.metrics.savings, 2))).toBeVisible();
    expect(within(promotion).getByText(/adds \$0\.00 in purchase cash/)).toBeVisible();
    const reduction = screen.getByRole('button', { name: 'Reduce by one case' }).closest('article');
    expect(within(reduction).getByText(money(reduced.metrics.spend - plan.metrics.spend, 2))).toBeVisible();
    expect(within(reduction).getByText('additional cash after supplier thresholds change')).toBeVisible();
  });

  it('labels a below-threshold rebate estimate separately from captured savings', async () => {
    const user = userEvent.setup();
    const product = data.products.find((item) => item.dealId === 'royal-volume');
    const supplier = data.suppliers.find((item) => item.id === product.supplierId);
    const deal = data.deals.find((item) => item.id === product.dealId);
    const fixture = { ...data, products: [product], suppliers: [supplier], deals: [deal] };
    const plan = calculatePlan(fixture, {}, { [product.id]: { cases: 2 } });
    render(<SupplierDeals data={fixture} plan={plan} onApplyDeal={vi.fn()} onInspectSku={vi.fn()} />);
    expect(screen.getByText('merchandise savings estimate · order minimum not met')).toBeVisible();
    expect(screen.getByText(/below the \$7,500 merchandise minimum/)).toBeVisible();
    expect(plan.metrics.savings).toBe(0);
    expect(screen.queryByText('Already captured')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Use offer' }));
  });

  it('adds only the chosen offer’s qualifying cases and refuses to override protected products', () => {
    const plan = calculatePlan(data);
    const deal = data.deals.find((item) => item.id === 'orijen-treats');
    const result = dealAdjustment(deal, plan, data);
    expect(result.qualified).toBe(true);
    expect(result.changes).toEqual({ 'orijen-freeze': { cases: 4 } });
    const snapshot = Object.fromEntries(plan.lines.map((line) => [line.id, { cases: line.cases, excluded: line.excluded, pinned: line.pinned, ...result.changes[line.id] }]));
    const applied = calculatePlan(data, plan.options, snapshot);
    expect(applied.lines.find((line) => line.id === 'orijen-freeze').discount).toBe(.15);
    expect(applied.lines.filter((line) => line.id !== 'orijen-freeze').map((line) => line.cases)).toEqual(plan.lines.filter((line) => line.id !== 'orijen-freeze').map((line) => line.cases));
    const protectedPlan = calculatePlan(data, {}, { 'orijen-freeze': { cases: 2, pinned: true } });
    expect(dealAdjustment(deal, protectedPlan, data)).toMatchObject({ changes: {}, qualified: false });
  });

  it('does not chase an unreachable supplier rebate into excess stock', () => {
    const deal = { ...data.deals.find((item) => item.id === 'royal-volume'), minSpend: 1000000 };
    const fixture = { ...data, deals: data.deals.map((item) => item.id === deal.id ? deal : item) };
    const result = dealAdjustment(deal, calculatePlan(fixture), fixture);
    expect(result.qualified).toBe(false);
    expect(result.changes).toEqual({});
    expect(result.reason).toContain('90-day demand');
  });
});
