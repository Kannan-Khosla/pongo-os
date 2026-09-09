import { describe, expect, it } from 'vitest';
import data from './smartBuyingData.json';
import { calculatePlan, copilotAnswer, defaults, money, strategies } from './smartBuyingEngine.js';

const total = (rows, key) => rows.reduce((value, row) => value + row[key], 0);

describe('Smart Buying deterministic engine', () => {
  it('reconciles SKU, supplier, and cash metrics including freight and recoverable tax', () => {
    const plan = calculatePlan(data);
    expect(calculatePlan(data)).toEqual(plan);
    expect(plan.lines).toHaveLength(20);
    expect(plan.groups).toHaveLength(4);
    expect(plan.metrics.spend).toBeCloseTo(total(plan.groups, 'total'), 2);
    expect(plan.metrics.spend).toBeCloseTo(plan.metrics.subtotal - plan.metrics.savings + plan.metrics.freight + plan.metrics.tax, 2);
    expect(plan.metrics.savings).toBeCloseTo(total(plan.lines, 'savings'), 2);
    expect(plan.metrics.grossProfit).toBeCloseTo(plan.metrics.retailValue - (plan.metrics.spend - plan.metrics.tax), 2);
    expect(plan.metrics.marginLift).toBeCloseTo(plan.metrics.savings / plan.metrics.retailValue * 100, 1);
    expect(plan.metrics.spend).toBeGreaterThan(40000);
    expect(plan.metrics.spend).toBeLessThan(45000);
    expect(plan.metrics.savings).toBeGreaterThan(3000);
    expect(plan.metrics.inventoryAfter).toBeCloseTo(plan.metrics.inventoryBefore + plan.metrics.subtotal - plan.metrics.savings + plan.metrics.freight, 2);
    expect(plan.metrics.baselineSpend).toBeCloseTo(plan.metrics.subtotal + plan.metrics.baselineFreight + plan.metrics.baselineTax, 2);
    expect(plan.metrics.baselineSpend - plan.metrics.spend).toBeGreaterThan(plan.metrics.savings);
    expect(money(13.47, 2)).toBe('$13.47');
  });

  it('separates organic history from confirmed renewals and respects growth only for organic demand', () => {
    expect(data.subscriptionSchedule.activeSubscriptions * data.subscriptionSchedule.unitsPerRenewal).toBe(total(data.products, 'subscription30'));
    expect(data.subscriptionSchedule.cadenceDays).toBe(30);
    const product = data.products[0];
    const line = calculatePlan(data).lines[0];
    const daily = (product.sales30 * .5 + (product.sales60 - product.sales30) * .3 + (product.sales90 - product.sales60) * .2) / 30;
    expect(line.organicDemand).toBe(Math.ceil(daily * 60));
    expect(line.subscriptionDemand).toBe(product.subscription30 * 2);
    expect(line.forecast60).toBe(Math.ceil((daily + product.subscription30 / 30) * 60));
    expect(line.rawRequirement).toBe(Math.max(0, line.organicDemand + line.subscriptionDemand + line.safetyUnits - line.sellable - line.inbound));
    const growing = calculatePlan(data, { growth: 30 }).lines[0];
    expect(growing.subscriptionDemand).toBe(line.subscriptionDemand);
    expect(growing.organicDemand).toBeGreaterThan(line.organicDemand);
    expect(calculatePlan(data, { horizon: 90 }).metrics.subscriptionUnits).toBe(calculatePlan(data, { horizon: 30 }).metrics.subscriptionUnits * 3);
  });

  it('recalculates all five strategies and honors pack sizes, MOQs, exclusions, and zero quantity', () => {
    const spend = strategies.map((strategy) => calculatePlan(data, { strategy: strategy.id }).metrics.spend);
    expect(new Set(spend).size).toBe(5);
    const id = data.products[0].id;
    const changed = calculatePlan(data, {}, { [id]: { cases: 1 }, 'rc-wet': { excluded: true }, 'now-wet': { cases: 0 } });
    const first = changed.lines.find((line) => line.id === id);
    expect(first.units).toBeGreaterThanOrEqual(first.moq);
    expect(changed.lines.find((line) => line.id === 'rc-wet').units).toBe(0);
    expect(changed.lines.find((line) => line.id === 'now-wet').units).toBe(0);
    changed.lines.forEach((line) => {
      expect(line.units % line.casePack).toBe(0);
      if (line.units) expect(line.units).toBeGreaterThanOrEqual(line.moq);
    });
  });

  it('changes buying targets without changing expected customer demand when strategy changes', () => {
    const balanced = calculatePlan(data);
    const conservative = calculatePlan(data, { strategy: 'conservative' });
    const growth = calculatePlan(data, { strategy: 'growth' });
    expect(conservative.metrics.organicUnits).toBe(balanced.metrics.organicUnits);
    expect(growth.metrics.organicUnits).toBe(balanced.metrics.organicUnits);
    expect(conservative.lines[0].forecast60).toBe(balanced.lines[0].forecast60);
    expect(conservative.lines[0].targetOrganicUnits).toBeLessThan(balanced.lines[0].organicDemand);
    expect(growth.lines[0].targetOrganicUnits).toBeGreaterThan(balanced.lines[0].organicDemand);
    const first = conservative.lines[0];
    expect(first.rawRequirement).toBe(Math.max(0, first.targetOrganicUnits + first.subscriptionDemand + first.safetyUnits - first.sellable - first.inbound));
    const pinned = calculatePlan(data, { horizon: 90, strategy: 'growth', optimize: true }, { [first.id]: { cases: first.cases, pinned: true } });
    expect(pinned.lines[0].cases).toBe(first.cases);
  });

  it('recomputes regular-price freight thresholds and GST for the comparison basket', () => {
    const onlyAcana = { ...data, products: [data.products[0]], suppliers: [{ ...data.suppliers[0], freeFreight: 1300 }] };
    const plan = calculatePlan(onlyAcana, {}, { 'acana-pacifica': { cases: 10 } });
    expect(plan.metrics.subtotal).toBe(1390);
    expect(plan.metrics.freight).toBe(95);
    expect(plan.metrics.baselineFreight).toBe(0);
    expect(plan.metrics.baselineTax).toBe(69.50);
    expect(plan.metrics.baselineSpend).toBe(1459.50);
    expect(plan.metrics.baselineMargin).toBeCloseTo((plan.metrics.retailValue - 1390) / plan.metrics.retailValue * 100, 2);
  });

  it('applies ordinary discounts immediately and only adds promotion cases within useful demand', () => {
    const regular = calculatePlan(data);
    const optimized = calculatePlan(data, { optimize: true });
    expect(regular.metrics.savings).toBeGreaterThan(0);
    expect(optimized.metrics.savings).toBeGreaterThan(regular.metrics.savings);
    expect(optimized.lines.some((line) => line.promotionCases > 0)).toBe(true);
    optimized.lines.filter((line) => line.promotionCases > 0).forEach((line) => {
      expect(line.sellable + line.inbound + line.units).toBeLessThanOrEqual(line.forecast90 + line.safetyUnits);
      expect(line.velocityClass).not.toBe('C');
    });
    expect(optimized.lines.find((line) => line.id === 'kong-classic').units).toBe(0);
  });

  it('prices free cases exactly and removes expired or unmet offers', () => {
    const eleven = calculatePlan(data, {}, { 'go-salmon': { cases: 11 } }).lines.find((line) => line.id === 'go-salmon');
    expect(eleven.units).toBe(22);
    expect(eleven.savings).toBeCloseTo(2 * eleven.cost, 2);
    expect(eleven.lineTotal).toBeCloseTo(20 * eleven.cost, 2);
    const twelve = calculatePlan(data, {}, { 'go-salmon': { cases: 12 } }).lines.find((line) => line.id === 'go-salmon');
    expect(twelve.savings).toBe(eleven.savings);
    const ten = calculatePlan(data, {}, { 'go-salmon': { cases: 10 } }).lines.find((line) => line.id === 'go-salmon');
    expect(ten.discount).toBe(0);
    expect(calculatePlan({ ...data, asOf: '2026-10-01' }).metrics.savings).toBe(0);
    const small = Object.fromEntries(data.products.filter((product) => product.supplierId === 'royal').map((product) => [product.id, { cases: Math.ceil(product.moq / product.casePack) }]));
    expect(calculatePlan(data, {}, small).lines.find((line) => line.id === 'rc-medium').discount).toBe(0);
  });

  it('never exceeds a cash budget including freight, GST, and threshold changes', () => {
    for (const budget of [0, 50, 200, 1200, 7500, 25000, 40000]) {
      const plan = calculatePlan(data, { optimize: true, budgetMode: true, budget });
      expect(plan.metrics.spend).toBeLessThanOrEqual(budget);
      expect(plan.metrics.budgetExceeded).toBe(0);
      plan.lines.filter((line) => line.units > 0).forEach((line) => expect(line.units).toBeGreaterThanOrEqual(line.moq));
      expect(plan.metrics.deferredSpend).toBeCloseTo(plan.metrics.optimalSpend - plan.metrics.spend, 2);
    }
  });

  it('keeps pinned quantities visible when they exceed the budget and defers other products', () => {
    const plan = calculatePlan(data, { budget: 200, budgetMode: true, optimize: true }, { 'acana-pacifica': { cases: 20, pinned: true } });
    expect(plan.lines.find((line) => line.id === 'acana-pacifica').cases).toBe(20);
    expect(plan.groups).toHaveLength(1);
    expect(plan.metrics.budgetExceeded).toBeCloseTo(plan.metrics.spend - 200, 2);
    expect(plan.risks.find((risk) => risk.id === 'cash').description).toContain('pinned');
  });

  it('rounds half-cent GST consistently with backend financial validation', () => {
    const plan = calculatePlan(data, { horizon: 90, strategy: 'subscription', optimize: true });
    const group = plan.groups.find((row) => row.id === 'anipet');
    expect(group.subtotal - group.savings + group.freight).toBeCloseTo(5141.90, 2);
    expect(group.tax).toBe(257.10);
  });

  it('rejects unknown evidence instead of treating missing costs or inventory as zero', () => {
    expect(() => calculatePlan({ ...data, products: [{ ...data.products[0], stock: null }] })).toThrow('Missing or invalid');
    expect(() => calculatePlan(data, { growth: Number.NaN })).toThrow('Demand growth');
    expect(() => calculatePlan(data, { budget: -1 })).toThrow('budget');
    expect(() => calculatePlan(data, {}, { 'acana-pacifica': { cases: 1.5 } })).toThrow('whole number');
    expect(data.products.find((line) => line.id === 'now-wet').supplierUnitLabel).toBe('24/85g');
    expect(data.products.every((line) => typeof line.barcode === 'string' && line.barcode.startsWith('0'))).toBe(true);
  });

  it('handles zero demand and an empty catalog without phantom purchases or NaN metrics', () => {
    const quiet = calculatePlan({ ...data, products: [{ ...data.products[0], sales30: 0, sales60: 0, sales90: 0, subscription30: 0, safety: 0 }] });
    expect(quiet.lines[0].units).toBe(0);
    expect(quiet.lines[0].stockoutDate).toBeNull();
    expect(quiet.metrics.stockoutsBefore).toBe(0);
    const empty = calculatePlan({ ...data, products: [] });
    expect(empty.metrics.spend).toBe(0);
    expect(Object.values(empty.metrics).every(Number.isFinite)).toBe(true);
  });

  it('answers the buyer from the active plan without changing it', () => {
    const plan = calculatePlan(data);
    const before = structuredClone(plan);
    expect(copilotAnswer('Where can I save the most money?', plan, data, defaults)).toContain('Pacific Pet');
    expect(copilotAnswer('What is driving the margin improvement?', plan, data, defaults)).toContain('40.8%');
    expect(copilotAnswer('What if I reduce by 20%?', plan, data, defaults)).toContain('cash cap');
    expect(copilotAnswer('Subscription demand?', calculatePlan(data, { horizon: 90 }), data)).toContain('over 90 days');
    const pinned = calculatePlan(data, { budget: 200, budgetMode: true }, { 'acana-pacifica': { cases: 20, pinned: true } });
    expect(copilotAnswer('Reduce by 20%', pinned, data)).toContain('Pinned quantities exceed that cap');
    expect(plan).toEqual(before);
  });
});
