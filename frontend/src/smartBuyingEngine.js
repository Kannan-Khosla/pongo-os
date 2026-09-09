// Pure demo calculations. The JSON fixture is the only inventory/deal input;
// no request, clock, random value, or live operational write occurs here.
export const defaults = { horizon: 60, strategy: 'balanced', safety: 'standard', growth: 0, budget: 40000, optimize: false, budgetMode: false };
export const strategies = [
  { id: 'balanced', label: 'Balanced', description: 'Balance availability, cash, and supplier savings.' },
  { id: 'conservative', label: 'Cash Conservative', description: 'Buy a shorter organic demand window and preserve known renewals.' },
  { id: 'growth', label: 'Growth', description: 'Carry more organic demand and a larger safety reserve.' },
  { id: 'deals', label: 'Deal Maximizer', description: 'Capture offers where extra inventory sells within 90 days.' },
  { id: 'subscription', label: 'Subscription First', description: 'Protect known renewals before discretionary organic demand.' },
];

const currency = new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', maximumFractionDigits: 0 });
const preciseCurrency = new Intl.NumberFormat('en-CA', { style: 'currency', currency: 'CAD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const quantity = new Intl.NumberFormat('en-CA', { maximumFractionDigits: 1 });
export const money = (value, decimals = 0) => Number.isFinite(value) ? (decimals === 2 ? preciseCurrency : currency).format(value) : '—';
export const number = (value) => Number.isFinite(value) ? quantity.format(value) : '—';
const round = (value) => Math.round((value + Number.EPSILON * Math.max(1, Math.abs(value))) * 100) / 100;
const sum = (rows, key) => rows.reduce((total, row) => total + row[key], 0);
const percent = (part, whole) => whole > 0 ? round(part / whole * 100) : 0;
const dateAfter = (date, days) => new Date(Date.parse(`${date}T12:00:00Z`) + Math.floor(days) * 86400000).toISOString().slice(0, 10);
const isActive = (deal, date) => deal && deal.start <= date && deal.expiry >= date;

function checkedOptions(options) {
  const value = { ...defaults, ...options };
  if (![30, 60, 90].includes(value.horizon)) throw new Error('Choose a 30, 60, or 90 day forecast.');
  if (!strategies.some((strategy) => strategy.id === value.strategy)) throw new Error('Choose a valid buying strategy.');
  if (!['low', 'standard', 'high'].includes(value.safety)) throw new Error('Choose a valid safety stock level.');
  if (!Number.isFinite(value.growth) || value.growth < -20 || value.growth > 30) throw new Error('Demand growth must be between -20% and +30%.');
  if (!Number.isFinite(value.budget) || value.budget < 0 || value.budget > 1000000) throw new Error('Enter a budget between $0 and $1,000,000.');
  return value;
}

function priceLines(lines, data, options) {
  const grossBySupplier = Object.fromEntries(data.suppliers.map((supplier) => [supplier.id, round(lines.filter((line) => line.supplierId === supplier.id).reduce((total, line) => total + line.cases * line.casePack * line.cost, 0))]));
  return lines.map((line) => {
    const units = line.cases * line.casePack;
    const deal = data.deals.find((offer) => offer.id === line.dealId);
    const eligible = units > 0 && isActive(deal, data.asOf) && deal.supplierId === line.supplierId && deal.productIds.includes(line.id) && units >= deal.minUnits && grossBySupplier[line.supplierId] >= deal.minSpend;
    const discount = eligible ? deal.type === 'buy_x_get_y' ? Math.floor(line.cases / (deal.buyCases + deal.freeCases)) * deal.freeCases / line.cases : deal.discount : 0;
    const subtotal = round(units * line.cost);
    const savings = round(subtotal * discount);
    const lineTotal = round(subtotal - savings);
    const retailValue = round(units * line.retail);
    return { ...line, units, discount, effectiveCost: units ? Math.round(lineTotal / units * 1e6) / 1e6 : line.cost, subtotal, savings, lineTotal, retailValue, grossProfit: round(retailValue - lineTotal), coverageAfter: line.dailyDemand ? round((line.sellable + line.inbound + units) / line.dailyDemand) : 365, deal: deal || null, dealCaptured: discount > 0 };
  });
}

function groupLines(lines, data) {
  return data.suppliers.map((supplier) => {
    const selected = lines.filter((line) => line.supplierId === supplier.id && line.units > 0);
    const subtotal = round(sum(selected, 'subtotal'));
    const savings = round(sum(selected, 'savings'));
    const freight = selected.length && round(subtotal - savings) < supplier.freeFreight ? supplier.freight : 0;
    const tax = round((subtotal - savings + freight) * data.taxRate);
    const total = round(subtotal - savings + freight + tax);
    const retailValue = round(sum(selected, 'retailValue'));
    const grossProfit = round(retailValue - (subtotal - savings + freight));
    const units = sum(selected, 'units');
    const coverage = sum(selected, 'dailyDemand') ? round(selected.reduce((value, line) => value + line.coverageAfter * line.dailyDemand, 0) / sum(selected, 'dailyDemand')) : 0;
    return { ...supplier, supplier, lines: selected, subtotal, savings, freight, tax, total, units, retailValue, grossProfit, margin: percent(grossProfit, retailValue), coverage };
  }).filter((supplier) => supplier.lines.length);
}

const totalCash = (lines, data, options) => round(sum(groupLines(priceLines(lines, data, options), data), 'total'));

function allocateBudget(lines, data, options) {
  const selected = lines.map((line) => ({ ...line, cases: line.pinned ? line.cases : 0 }));
  if (totalCash(selected, data, options) > options.budget) return selected;
  const desired = new Map(lines.map((line) => [line.id, line.cases]));
  // ponytail: greedy case allocation suits this 20-SKU demo; use a constrained
  // optimizer when real catalogs need global rebate/freight optimality.
  let changed = true;
  while (changed) {
    changed = false;
    const ranked = selected.filter((line) => !line.pinned && line.cases < desired.get(line.id)).sort((a, b) => {
      const cover = (line) => (line.sellable + line.inbound + line.cases * line.casePack) / (options.strategy === 'subscription' && line.subscription30 ? line.subscription30 / 30 * 1.8 : line.dailyDemand || 1);
      return cover(a) - cover(b) || b.subscription30 - a.subscription30 || a.id.localeCompare(b.id);
    });
    for (const line of ranked) {
      const previous = line.cases;
      const next = previous ? previous + 1 : Math.max(1, Math.ceil(line.moq / line.casePack));
      if (next > desired.get(line.id)) continue;
      line.cases = next;
      if (totalCash(selected, data, options) <= options.budget) changed = true;
      else line.cases = previous;
    }
  }
  return selected;
}

export function calculatePlan(data, options = {}, adjustments = {}) {
  const settings = checkedOptions(options);
  const organicFactor = { balanced: 1, conservative: .75, growth: 1.15, deals: 1, subscription: .85 }[settings.strategy];
  const safetyFactor = { low: .6, standard: 1, high: 1.5 }[settings.safety] * (settings.strategy === 'growth' ? 1.2 : 1);
  const proposed = data.products.map((product) => {
    const supplier = data.suppliers.find((row) => row.id === product.supplierId);
    if (!supplier || ['stock', 'allocated', 'inbound', 'sales30', 'sales60', 'sales90', 'subscription30', 'cost', 'retail', 'casePack', 'moq', 'safety'].some((field) => !Number.isFinite(product[field]) || product[field] < 0) || product.casePack < 1 || product.sales60 < product.sales30 || product.sales90 < product.sales60) throw new Error(`Missing or invalid buying evidence for ${product.sku}.`);
    // Historical sales exclude subscriptions; the known renewals are added once.
    const dailyOrganic = (product.sales30 * .5 + (product.sales60 - product.sales30) * .3 + (product.sales90 - product.sales60) * .2) / 30 * (1 + settings.growth / 100);
    const dailyDemand = dailyOrganic + product.subscription30 / 30;
    const forecast = (days) => Math.ceil(dailyDemand * days);
    const organicDemand = Math.ceil(dailyOrganic * settings.horizon);
    const targetOrganicUnits = Math.ceil(dailyOrganic * settings.horizon * organicFactor);
    const subscriptionDemand = Math.ceil(product.subscription30 * settings.horizon / 30);
    const safetyUnits = Math.ceil(product.safety * safetyFactor);
    const sellable = Math.max(0, product.stock - product.allocated);
    const rawRequirement = Math.max(0, targetOrganicUnits + subscriptionDemand + safetyUnits - sellable - product.inbound);
    const baseCases = rawRequirement ? Math.max(Math.ceil(rawRequirement / product.casePack), Math.ceil(product.moq / product.casePack)) : 0;
    const deal = data.deals.find((offer) => offer.id === product.dealId);
    const promotionWindow = settings.strategy === 'deals' ? 28 : settings.strategy === 'conservative' ? 0 : 10;
    const targetDays = Math.min(90, settings.horizon + promotionWindow);
    const maxUsefulCases = Math.max(0, Math.floor((forecast(targetDays) + safetyUnits - sellable - product.inbound) / product.casePack));
    let recommendedCases = baseCases;
    if ((settings.optimize || settings.strategy === 'deals') && baseCases && isActive(deal, data.asOf) && deal.discount >= .08 && product.velocityClass !== 'C') {
      const minCases = Math.ceil(deal.minUnits / product.casePack);
      if (minCases <= maxUsefulCases) recommendedCases = Math.max(baseCases, minCases);
      if (deal.type === 'buy_x_get_y') {
        const cycle = deal.buyCases + deal.freeCases;
        const completeCases = Math.ceil(recommendedCases / cycle) * cycle;
        if (completeCases <= maxUsefulCases) recommendedCases = Math.max(recommendedCases, completeCases);
      } else if (settings.strategy === 'deals' || (deal.expiry <= dateAfter(data.asOf, 7) && settings.strategy === 'balanced')) {
        recommendedCases = Math.max(recommendedCases, maxUsefulCases);
      }
    }
    const adjustment = adjustments[product.id] || {};
    if (adjustment.cases !== undefined && (!Number.isInteger(adjustment.cases) || adjustment.cases < 0 || adjustment.cases > 10000)) throw new Error('Cases must be a whole number between 0 and 10,000.');
    let cases = adjustment.cases ?? recommendedCases;
    if (cases > 0) cases = Math.max(cases, Math.ceil(product.moq / product.casePack));
    if (adjustment.excluded) cases = 0;
    const daysCover = dailyDemand > 0 ? round(sellable / dailyDemand) : 365;
    const priority = daysCover < product.leadDays + 3 ? 'Critical' : daysCover < 30 ? 'High' : daysCover < settings.horizon ? 'Medium' : 'Low';
    return { ...product, supplier, dailyOrganic, dailyDemand, sellable, organicDemand, targetOrganicUnits, subscriptionDemand, forecast30: forecast(30), forecast60: forecast(60), forecast90: forecast(90), safetyUnits, rawRequirement, baseCases, promotionCases: recommendedCases - baseCases, recommendedCases, cases, daysCover, stockoutDate: dailyDemand > 0 ? dateAfter(data.asOf, daysCover) : null, priority, excluded: Boolean(adjustment.excluded), pinned: Boolean(adjustment.pinned), leadTimeRisk: sellable < dailyDemand * product.leadDays };
  });
  const optimalSpend = totalCash(proposed, data, settings);
  const lines = priceLines(settings.budgetMode ? allocateBudget(proposed, data, settings) : proposed, data, settings);
  const groups = groupLines(lines, data);
  const subtotal = round(sum(groups, 'subtotal'));
  const savings = round(sum(groups, 'savings'));
  const freight = round(sum(groups, 'freight'));
  const tax = round(sum(groups, 'tax'));
  const spend = round(sum(groups, 'total'));
  const retailValue = round(sum(groups, 'retailValue'));
  const grossProfit = round(sum(groups, 'grossProfit'));
  const margin = percent(grossProfit, retailValue);
  const baselineFreight = round(groups.reduce((total, group) => total + (group.subtotal < group.freeFreight ? group.supplier.freight : 0), 0));
  const baselineTax = round(groups.reduce((total, group) => total + round((group.subtotal + (group.subtotal < group.freeFreight ? group.supplier.freight : 0)) * data.taxRate), 0));
  const baselineSpend = round(subtotal + baselineFreight + baselineTax);
  const baselineMargin = percent(retailValue - subtotal - baselineFreight, retailValue);
  const stockoutsBefore = lines.filter((line) => line.sellable + line.inbound < line.dailyDemand * settings.horizon).length;
  const stockoutsAfter = lines.filter((line) => line.sellable + line.inbound + line.units < line.dailyDemand * settings.horizon).length;
  const subscriptionUnits = sum(lines, 'subscriptionDemand');
  const inventoryBefore = round(lines.reduce((total, line) => total + line.stock * line.cost, 0));
  const overstockValue = round(lines.reduce((total, line) => total + Math.max(0, line.sellable + line.inbound + line.units - line.forecast90 - line.safetyUnits) * line.effectiveCost, 0));
  const naiveOverstock = lines.reduce((total, line) => total + Math.max(0, line.sellable + line.inbound + Math.ceil(line.forecast90 / line.casePack) * line.casePack - line.forecast90 - line.safetyUnits) * line.cost, 0);
  const revenueSupported = round(lines.reduce((total, line) => total + Math.min(line.forecast90, line.sellable + line.inbound + line.units) * line.retail, 0));
  const cogs = round(lines.reduce((total, line) => {
    const existing = line.sellable + line.inbound;
    return total + Math.min(line.forecast90, existing) * line.cost + Math.min(line.units, Math.max(0, line.forecast90 - existing)) * line.effectiveCost;
  }, 0) + freight);
  const metrics = {
    spend, subtotal, savings, freight, tax, retailValue, grossProfit, margin, baselineMargin, baselineSpend, baselineFreight, baselineTax, marginLift: round(margin - baselineMargin),
    coverage: sum(lines, 'dailyDemand') ? round(lines.reduce((total, line) => total + line.sellable + line.inbound + line.units, 0) / sum(lines, 'dailyDemand')) : 0,
    stockoutsBefore, stockoutsAfter, stockoutsPrevented: Math.max(0, stockoutsBefore - stockoutsAfter),
    subscriptionCoverage: subscriptionUnits ? percent(lines.reduce((total, line) => total + Math.min(line.subscriptionDemand, line.sellable + line.inbound + line.units), 0), subscriptionUnits) : 100,
    subscriptionUnits, organicUnits: sum(lines, 'organicDemand'), targetOrganicUnits: sum(lines, 'targetOrganicUnits'), safetyUnits: sum(lines, 'safetyUnits'),
    inventoryBefore, inventoryAfter: round(inventoryBefore + subtotal - savings + freight), revenueSupported, cogs,
    forecastGrossProfit: round(revenueSupported - cogs), forecastMargin: percent(revenueSupported - cogs, revenueSupported),
    overstockValue, overstockAvoided: round(Math.max(0, naiveOverstock - overstockValue)), cashEfficiency: percent(savings, subtotal + freight),
    confidence: sum(lines, 'dailyDemand') ? round(lines.reduce((total, line) => total + line.confidence * line.dailyDemand, 0) / sum(lines, 'dailyDemand')) : 0,
    cashUtilization: settings.budget > 0 ? percent(spend, settings.budget) : 0,
    activeDeals: data.deals.filter((deal) => isActive(deal, data.asOf)).length,
    highVelocityShare: percent(lines.filter((line) => ['A', 'B'].includes(line.velocityClass)).reduce((total, line) => total + line.lineTotal, 0), subtotal - savings),
    budgetExceeded: round(Math.max(0, spend - settings.budget)), deferredSpend: round(Math.max(0, optimalSpend - spend)), optimalSpend,
    leadTimeRisk: lines.filter((line) => line.leadTimeRisk).length,
  };
  const expiring = lines.filter((line) => line.deal && isActive(line.deal, data.asOf) && line.deal.expiry <= dateAfter(data.asOf, 7));
  const expiringSavings = round(sum(expiring, 'savings'));
  const slow = lines.filter((line) => line.coverageAfter > 120);
  const renewalRisk = lines.filter((line) => line.subscription30 > 0 && line.daysCover < 14);
  const concentration = groups.length ? percent(Math.max(...groups.map((group) => group.total)), spend) : 0;
  const risks = [
    { id: 'stockouts', title: 'Stockout exposure', severity: stockoutsAfter ? 'High' : 'Low', description: `${stockoutsBefore} SKUs fall short of ${settings.horizon}-day demand before this plan; ${stockoutsAfter} remain exposed after replenishment.` },
    { id: 'lead-time', title: 'Delivery window', severity: metrics.leadTimeRisk ? 'Critical' : 'Low', description: metrics.leadTimeRisk ? `${metrics.leadTimeRisk} SKUs may run out before the expected supplier delivery. Expedite or transfer stock; a new order cannot erase this gap.` : 'Current sellable stock covers the expected supplier lead time for every SKU.' },
    { id: 'overstock', title: 'Excess coverage', severity: slow.length ? 'Medium' : 'Low', description: `${slow.length} SKUs exceed 120 days of cover. ${money(overstockValue)} would sit beyond 90-day demand and safety stock.` },
    { id: 'expiry', title: 'Promotion window', severity: expiringSavings ? 'Medium' : 'Low', description: `${money(expiringSavings)} in planned savings is attached to offers expiring within 7 days. Recheck the offer before placing the order.` },
    { id: 'cash', title: 'Cash concentration', severity: metrics.budgetExceeded ? 'High' : 'Low', description: metrics.budgetExceeded ? `The plan exceeds the selected cash budget by ${money(metrics.budgetExceeded)}${settings.budgetMode ? ' because pinned quantities are retained' : '; use Optimize to Budget to prioritize replenishment'}.` : `${number(concentration)}% of cash is allocated to the largest supplier. Freight and GST are included in the buying budget.` },
    { id: 'subscriptions', title: 'Upcoming renewals', severity: renewalRisk.length ? 'High' : 'Low', description: `${renewalRisk.length} subscription SKUs have fewer than 14 days of current stock. The plan covers ${number(metrics.subscriptionCoverage)}% of known ${settings.horizon}-day renewals.` },
  ];
  return { lines, groups, metrics, risks, options: settings };
}

export function copilotAnswer(query, plan, data, options = {}) {
  const text = query.toLowerCase();
  const { metrics, lines, groups } = plan;
  const settings = { ...defaults, ...plan.options, ...options };
  if (/20%|reduce|budget/.test(text)) {
    const budget = round(metrics.spend * .8);
    const currentQuantities = Object.fromEntries(lines.map((line) => [line.id, { cases: line.cases, pinned: line.pinned, excluded: line.excluded }]));
    const smaller = calculatePlan(data, { ...settings, budget, budgetMode: true, optimize: true }, currentQuantities);
    return `At a ${money(budget)} cash cap, the scenario buys ${money(smaller.metrics.spend)}, captures ${money(smaller.metrics.savings)} in offers, and covers ${number(smaller.metrics.subscriptionCoverage)}% of confirmed renewals. ${smaller.metrics.stockoutsAfter} SKUs remain below the demand horizon.${smaller.metrics.budgetExceeded ? ` Pinned quantities exceed that cap by ${money(smaller.metrics.budgetExceeded)}; unpin or reduce them to fit.` : ''} Open Scenarios to apply and inspect the tradeoff.`;
  }
  if (/stock.?out|run out/.test(text)) {
    const urgent = [...lines].sort((a, b) => a.daysCover - b.daysCover).slice(0, 3);
    return `${urgent.map((line) => `${line.name} (${number(line.daysCover)} days)`).join('; ')} have the shortest current cover. The plan reduces horizon shortages from ${metrics.stockoutsBefore} to ${metrics.stockoutsAfter} SKUs. ${metrics.leadTimeRisk} SKUs also need delivery-window attention.`;
  }
  if (/margin|profit/.test(text)) return `Eligible supplier offers save ${money(metrics.savings)} on the current purchase. At listed retail prices, purchase gross margin is ${number(metrics.margin)}%, compared with ${number(metrics.baselineMargin)}% at regular cost: ${number(metrics.marginLift)} percentage points of lift. Freight is included in cost; recoverable GST is excluded from gross margin.`;
  if (/acana/.test(text)) {
    const acana = lines.filter((line) => line.brand === 'ACANA');
    return `ACANA represents ${sum(acana, 'units')} recommended units and ${money(sum(acana, 'lineTotal'))} of merchandise. ${sum(acana, 'subscriptionDemand')} units are confirmed renewals in the selected horizon. Organic velocity, sellable stock, case packs, and eligible September offers explain the rest; each SKU drawer shows the calculation.`;
  }
  if (/save|saving|deal|supplier/.test(text)) {
    const best = [...groups].sort((a, b) => b.savings - a.savings)[0];
    return best ? `${best.name} contributes ${money(best.savings)} of the plan's ${money(metrics.savings)} supplier savings across ${best.lines.length} SKUs. ${metrics.activeDeals} dated offers are available in the fixture. The plan includes qualifying discounts; optimization tests whether extra cases justify the cash. Check expiry dates and minimum quantities in Supplier Deals.` : 'No supplier order is selected. Include a SKU or increase the cash budget to compare eligible offers.';
  }
  if (/subscription|renewal/.test(text)) return `Confirmed renewals account for ${number(metrics.subscriptionUnits)} units over ${settings.horizon} days, separate from ${number(metrics.organicUnits)} organic demand units. Available and proposed stock covers ${number(metrics.subscriptionCoverage)}% of those renewals. Subscription First prioritizes that known demand when cash is limited.`;
  return `Buy ${money(metrics.spend)} across ${groups.length} suppliers for the selected ${settings.horizon}-day window. The plan captures ${money(metrics.savings)} in supplier offers, supports ${number(metrics.coverage)} days of coverage, and protects ${metrics.stockoutsPrevented} horizon shortages. Review ${metrics.stockoutsAfter} remaining shortages and delivery timing before approving a local draft.`;
}
