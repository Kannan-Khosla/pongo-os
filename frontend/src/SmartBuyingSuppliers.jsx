import { useState } from 'react';
import { ArrowDownRight, ArrowRight, ArrowUpRight, BadgePercent, Check, CheckCheck, ChevronRight, CircleHelp, Clock3, FileText, Globe2, Layers3, Mail, PackageCheck, Search, Send, ShieldCheck, Sparkles, TrendingUp, Truck, Wallet } from 'lucide-react';
import { calculatePlan, copilotAnswer as explainPlan, money, number } from './smartBuyingEngine';

const sourceIcons = { website: Globe2, email: Mail, pdf: FileText, portal: Layers3, manual: FileText, newsletter: Mail };
const daysBetween = (start, end) => Math.ceil((new Date(end).getTime() - new Date(String(start).slice(0, 10)).getTime()) / 86400000);
const dateLabel = (value) => /^\d{4}-\d{2}-\d{2}/.test(String(value)) ? new Date(`${String(value).slice(0, 10)}T12:00:00`).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' }) : String(value);
const titleCase = (value) => String(value).replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
const activeLines = (plan) => plan.lines.filter((line) => !line.excluded && line.units > 0);
const sum = (rows, field) => rows.reduce((total, row) => total + Number(row[field] || 0), 0);

export function dealAdjustment(deal, plan, data) {
  if (!deal || daysBetween(data.asOf, deal.start) > 0 || daysBetween(data.asOf, deal.expiry) < 0) return { changes: {}, qualified: false, reason: 'This offer is outside its valid purchasing window.' };
  const snapshot = Object.fromEntries(plan.lines.map((line) => [line.id, { cases: line.cases, excluded: line.excluded, pinned: line.pinned }]));
  const candidates = plan.lines.filter((line) => line.dealId === deal.id && !line.excluded && !line.pinned);
  const ceiling = (line) => Math.max(0, Math.floor((line.forecast90 + line.safetyUnits - line.sellable - line.inbound) / line.casePack));
  const evaluate = () => calculatePlan(data, { ...plan.options, budgetMode: false }, snapshot);
  let proposed = evaluate();
  const qualifies = () => proposed.lines.some((line) => line.dealId === deal.id && line.discount > 0);
  for (const line of candidates) {
    if (qualifies()) break;
    const minimum = Math.max(line.cases, Math.ceil(line.moq / line.casePack), Math.ceil(deal.minUnits / line.casePack));
    const target = deal.type === 'buy_x_get_y' ? Math.ceil(minimum / (deal.buyCases + deal.freeCases)) * (deal.buyCases + deal.freeCases) : minimum;
    if (target <= ceiling(line)) snapshot[line.id].cases = target;
    proposed = evaluate();
  }
  // ponytail: bounded case increments are sufficient for this 20-SKU fixture;
  // use the purchasing optimizer for a large live supplier catalog.
  while (!qualifies()) {
    const next = candidates.filter((line) => Math.max(snapshot[line.id].cases + 1, Math.ceil(line.moq / line.casePack)) <= ceiling(line)).sort((a, b) => a.cost * a.casePack - b.cost * b.casePack)[0];
    if (!next) break;
    snapshot[next.id].cases = Math.max(snapshot[next.id].cases + 1, Math.ceil(next.moq / next.casePack));
    proposed = evaluate();
  }
  if (!qualifies()) return { changes: {}, qualified: false, reason: 'This offer cannot qualify within 90-day demand plus safety stock while retaining pinned and excluded products. Keep the demand-led purchase instead.' };
  const changes = Object.fromEntries(plan.lines.filter((line) => snapshot[line.id].cases !== line.cases).map((line) => [line.id, { cases: snapshot[line.id].cases }]));
  return { changes, qualified: true, reason: `${deal.title} qualifies. ${money(sum(proposed.lines.filter((line) => line.dealId === deal.id), 'savings'))} in supplier savings is included in the updated plan.` };
}

function SupplierMark({ supplier }) {
  return <span className="sb-supplier-mark" style={{ '--supplier-color': supplier.color }}>{supplier.initials}</span>;
}

function DealEvidence({ deal, data, lines, onInspectSku }) {
  return <details className="sb-evidence">
    <summary><ShieldCheck size={15} aria-hidden="true" /> Review source &amp; matching <ChevronRight size={15} aria-hidden="true" /></summary>
    <div className="sb-evidence-body">
      <strong>{deal.sourceLabel}</strong>
      <p>{deal.description}</p>
      <dl className="sb-mini-stats">
        <div><dt>Captured</dt><dd>{dateLabel(data.asOf)}</dd></div>
        <div><dt>Match confidence</dt><dd>{deal.confidence}%</dd></div>
        <div><dt>Eligible products</dt><dd>{deal.productIds.length}</dd></div>
      </dl>
      <p className="sb-muted">Prices are normalized to one sellable unit. Case packs stay explicit; barcode, recipe, and size must match before an offer enters the plan.</p>
      <div className="sb-evidence-products">{lines.map((line) => <button className="sb-text-button" type="button" key={line.id} onClick={() => onInspectSku(line.id)}>{line.sku} · {line.name}<ArrowUpRight size={13} aria-hidden="true" /></button>)}</div>
      <small>Demonstration evidence · no supplier connection is opened.</small>
    </div>
  </details>;
}

export function SupplierDeals({ data, plan, onApplyDeal, onInspectSku }) {
  const [search, setSearch] = useState('');
  const [supplierId, setSupplierId] = useState('all');
  const [source, setSource] = useState('all');
  const [type, setType] = useState('all');
  const selectedLines = activeLines(plan);
  const expiring = data.deals.filter((deal) => daysBetween(data.asOf, deal.expiry) >= 0 && daysBetween(data.asOf, deal.expiry) <= 7);
  const deals = data.deals.filter((deal) => {
    const supplier = data.suppliers.find((item) => item.id === deal.supplierId);
    return (supplierId === 'all' || deal.supplierId === supplierId) && (source === 'all' || deal.source === source) && (type === 'all' || deal.type === type) && `${supplier.name} ${deal.brand} ${deal.title} ${deal.sourceLabel}`.toLowerCase().includes(search.toLowerCase());
  });
  const reset = () => { setSearch(''); setSupplierId('all'); setSource('all'); setType('all'); };

  return <div className="sb-stack">
    <section className="sb-section-intro"><div><span className="sb-eyebrow">The right offer. At the right time.</span><h2>Offers matched to your buying plan</h2><p>Promotions matched to real buying needs, with the terms behind every recommendation.</p></div><span className="sb-badge sb-badge-blue"><BadgePercent size={15} aria-hidden="true" />{data.deals.length} offers evaluated</span></section>
    <div className="sb-summary-strip">
      <div><span>Supplier savings in your plan</span><strong>{money(plan.metrics.savings)}</strong></div>
      <div><span>Offers closing within 7 days</span><strong>{expiring.length}</strong></div>
      <div><span>Matched supplier sources</span><strong>{data.sources.length}</strong></div>
      <div><span>Your purchasing window</span><strong>{dateLabel(data.asOf)}</strong></div>
    </div>
    <div className="sb-filter-bar">
      <label className="sb-search"><Search size={17} aria-hidden="true" /><span className="sr-only">Search supplier deals</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search offers, brands, sources…" /></label>
      <label><span>Supplier</span><select value={supplierId} onChange={(event) => setSupplierId(event.target.value)}><option value="all">All suppliers</option>{data.suppliers.map((supplier) => <option value={supplier.id} key={supplier.id}>{supplier.name}</option>)}</select></label>
      <label><span>Source</span><select value={source} onChange={(event) => setSource(event.target.value)}><option value="all">All sources</option>{[...new Set(data.deals.map((deal) => deal.source))].map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
      <label><span>Offer type</span><select value={type} onChange={(event) => setType(event.target.value)}><option value="all">All offer types</option>{[...new Set(data.deals.map((deal) => deal.type))].map((value) => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label>
    </div>
    <p className="sb-result-count" role="status">{deals.length} of {data.deals.length} offers</p>
    {deals.length ? <div className="sb-deal-grid">{deals.map((deal) => {
      const supplier = data.suppliers.find((item) => item.id === deal.supplierId);
      const eligible = plan.lines.filter((line) => deal.productIds.includes(line.id));
      const applied = selectedLines.filter((line) => line.dealId === deal.id && line.discount > 0);
      const captured = sum(applied, 'savings');
      const remainingDays = daysBetween(data.asOf, deal.expiry);
      const upcoming = daysBetween(data.asOf, deal.start) > 0;
      const expired = remainingDays < 0;
      const potential = sum(eligible.map((line) => {
        const cases = Math.max(line.recommendedCases, Math.ceil(deal.minUnits / line.casePack));
        const discount = deal.type === 'buy_x_get_y' && cases ? Math.floor(cases / (deal.buyCases + deal.freeCases)) * deal.freeCases / cases : deal.discount;
        return { amount: cases * line.casePack * line.cost * discount };
      }), 'amount');
      const thresholdGap = Math.max(0, deal.minSpend - sum(selectedLines.filter((line) => line.supplierId === deal.supplierId), 'subtotal'));
      const effectiveDiscount = captured > 0 ? captured / sum(applied, 'subtotal') : deal.discount;
      const SourceIcon = sourceIcons[deal.source.toLowerCase()] || FileText;
      const status = expired ? 'Expired' : upcoming ? 'Upcoming' : captured > 0 ? 'Already captured' : remainingDays <= 7 ? 'Expiring soon' : potential > 0 ? 'Recommended' : 'Consider';
      return <article className="sb-deal-card" key={deal.id}>
        <div className="sb-card-heading"><div className="sb-supplier-heading"><SupplierMark supplier={supplier} /><div><strong>{supplier.name}</strong><span>{deal.brand}</span></div></div><span className={`sb-badge ${captured > 0 ? 'sb-badge-green' : remainingDays <= 7 ? 'sb-badge-peach' : ''}`}>{status}</span></div>
        <h3>{deal.title}</h3>
        <div className="sb-deal-value"><strong>{money(captured || potential)}</strong><span>{captured > 0 ? 'savings captured in this plan' : thresholdGap > 0 ? 'merchandise savings estimate · order minimum not met' : 'potential savings at qualifying quantities'}</span></div>
        {thresholdGap > 0 && <p className="sb-muted">This supplier basket is {money(thresholdGap)} below the {money(deal.minSpend)} merchandise minimum. The estimate is not included in plan savings.</p>}
        <dl className="sb-deal-terms">
          <div><dt>{captured ? 'Effective plan discount' : 'Advertised discount'}</dt><dd>{number(effectiveDiscount * 100, 1)}%</dd></div>
          <div><dt>Minimum order</dt><dd>{deal.minSpend ? money(deal.minSpend) : deal.minUnits ? `${number(deal.minUnits)} units` : 'No minimum'}</dd></div>
          <div><dt>Eligible SKUs</dt><dd>{deal.productIds.length}</dd></div>
          <div><dt>Valid dates</dt><dd>{dateLabel(deal.start)} – {dateLabel(deal.expiry)}</dd></div>
        </dl>
        <div className="sb-deal-source"><span><SourceIcon size={14} aria-hidden="true" />{titleCase(deal.source)}</span><span>{deal.confidence}% confidence</span></div>
        <DealEvidence deal={deal} data={data} lines={eligible} onInspectSku={onInspectSku} />
        <div className="sb-card-footer"><span><Clock3 size={14} aria-hidden="true" />{expired ? 'Offer has ended' : upcoming ? `Opens ${dateLabel(deal.start)}` : remainingDays === 0 ? 'Expires today' : `${remainingDays} days remaining`}</span><button type="button" className={captured ? 'secondary-button' : 'primary-button'} onClick={() => onApplyDeal(deal.id)} disabled={expired || upcoming || captured > 0}>{captured > 0 ? <><Check size={15} aria-hidden="true" /> In purchase plan</> : <>Use offer <ArrowRight size={15} aria-hidden="true" /></>}</button></div>
      </article>;
    })}</div> : <div className="sb-empty"><Search size={28} aria-hidden="true" /><h3>No offers match these filters</h3><p>Broaden your supplier, source, or offer selection to find another buying window.</p><button className="secondary-button" type="button" onClick={reset}>Reset deal filters</button></div>}
  </div>;
}

export function SupplierIntelligence({ data, plan }) {
  const [sourceId, setSourceId] = useState(null);
  const selectedSource = data.sources.find((source) => source.id === sourceId);
  return <div className="sb-stack">
    <section className="sb-section-intro"><div><span className="sb-eyebrow">From supplier signals to buying decisions</span><h2>The partners behind your next purchase</h2><p>A clear view of who delivers, where value comes from, and the evidence behind it.</p></div><span className="sb-badge sb-badge-blue"><ShieldCheck size={15} aria-hidden="true" />Source evidence available</span></section>
    <section className="sb-panel"><div className="sb-panel-heading"><div><h3>Every offer has a path to your plan</h3><p>Traceable promotions, matched to the products you sell.</p></div></div><ol className="sb-pipeline">{['Source captured', 'Offer normalized', 'SKU matched', 'Terms validated', 'Plan optimized'].map((step, index) => <li key={step}><span>{index + 1}</span><strong>{step}</strong>{index < 4 && <ChevronRight size={18} aria-hidden="true" />}</li>)}</ol></section>
    <div className="sb-supplier-grid">{data.suppliers.map((supplier) => {
      const group = plan.groups.find((item) => (item.supplier?.id || item.id) === supplier.id);
      return <article key={supplier.id} className="sb-supplier-card">
        <div className="sb-card-heading"><div className="sb-supplier-heading"><SupplierMark supplier={supplier} /><div><h3>{supplier.name}</h3><span>{data.products.filter((product) => product.supplierId === supplier.id).length} active SKUs in analysis</span></div></div><div className="sb-score"><strong>{supplier.score}</strong><span>/ 100</span></div></div>
        <div className="sb-score-track" role="meter" aria-label={`${supplier.name} supplier score`} aria-valuemin="0" aria-valuemax="100" aria-valuenow={supplier.score}><span style={{ width: `${supplier.score}%` }} /></div>
        <dl className="sb-score-details"><div><dt>Average lead time</dt><dd>{supplier.leadDays} days</dd></div><div><dt>Fill rate</dt><dd>{supplier.fillRate}%</dd></div><div><dt>Average discount</dt><dd>{supplier.avgDiscount}%</dd></div><div><dt>Deal frequency</dt><dd>{supplier.dealFrequency}</dd></div><div><dt>Promotion reliability</dt><dd>{supplier.promotionReliability}%</dd></div><div><dt>Average order</dt><dd>{money(supplier.avgOrderValue)}</dd></div><div><dt>Spend year to date</dt><dd>{money(supplier.spendYtd)}</dd></div><div><dt>Savings year to date</dt><dd>{money(supplier.savingsYtd)}</dd></div></dl>
        <div className="sb-supplier-current"><span>In this purchase plan</span><strong>{money(group?.total || 0)}</strong><span>{money(group?.savings || 0)} saved</span></div>
        <div className="sb-recommendation-note"><Sparkles size={16} aria-hidden="true" /><p>{supplier.strategy}</p></div>
      </article>;
    })}</div>
    <div className="sb-two-columns">
      <section className="sb-panel"><div className="sb-panel-heading"><div><h3>Supplier sources</h3><p>Inspect the evidence and matching rules for each input.</p></div><span className="sb-badge">{data.sources.length} sources</span></div><div className="sb-source-list">{data.sources.map((source) => {
        const Icon = sourceIcons[source.type.toLowerCase()] || FileText;
        return <button className={`sb-source-row ${sourceId === source.id ? 'is-selected' : ''}`} key={source.id} type="button" aria-expanded={sourceId === source.id} onClick={() => setSourceId(sourceId === source.id ? null : source.id)}><span className="sb-source-icon"><Icon size={19} aria-hidden="true" /></span><span><strong>{source.label}</strong><small>{source.offers} offers · {source.confidence}% confidence · {source.status}</small></span><ChevronRight size={16} aria-hidden="true" /></button>;
      })}</div>{selectedSource && <section className="sb-source-evidence" aria-label={`${selectedSource.label} evidence`}><h4>{selectedSource.label}</h4><p>{selectedSource.notes}</p><dl><div><dt>Last captured</dt><dd>{dateLabel(selectedSource.lastUpdated)}</dd></div><div><dt>Source type</dt><dd>{titleCase(selectedSource.type)}</dd></div><div><dt>Confidence</dt><dd>{selectedSource.confidence}%</dd></div></dl><p>Supplier pack prices are converted to sellable-unit costs. Pongo SKU, barcode, recipe, and size are preserved; uncertain matches require review.</p><small>Local demonstration record. Reviewing this source does not access a website, inbox, or attachment.</small></section>}</section>
      <section className="sb-panel"><div className="sb-panel-heading"><div><h3>Intelligence feed</h3><p>The signals influencing this buying cycle.</p></div><span className="sb-live-dot" aria-hidden="true" /></div><ol className="sb-activity-list">{data.activity.map((event) => <li key={event.id}><span className="sb-activity-dot" /><div><p>{event.text}</p><time>{event.time}</time></div></li>)}</ol></section>
    </div>
  </div>;
}

const copilotQuestions = ['What should I buy this week?', 'Where can I save the most money?', 'Which products will stock out next month?', 'Which supplier deal should I use?', 'What happens if I reduce this purchase by 20%?', 'Why are we buying so much ACANA?', 'What is driving the margin improvement?'];

function copilotAnswer(question, data, plan, options) {
  const query = question.toLowerCase();
  const topics = [
    [/20|reduce|budget|less cash/, 'A smaller buy needs a different priority order.', 'Compare a 20% lower budget', 'budget'],
    [/margin|profit/, 'Better purchase costs support healthier margins.', 'Review the financial impact', 'draft-pos'],
    [/acana/, 'ACANA is backed by forecast demand.', 'See SKU-level forecasts', 'forecast'],
    [/stock ?out|run out/, 'Protect the products with the shortest cover.', 'Inspect stockout risks', 'forecast'],
    [/deal|promotion|offer/, 'Compare the offers your forecast can absorb.', 'Compare supplier deals', 'supplier-deals'],
    [/sav|money|cheapest/, 'Concentrate on the offers your demand can absorb.', 'Review buying opportunities', 'opportunities'],
    [/buy|week|purchase|order|subscription|renewal/, 'Your purchasing plan is ready to review.', 'Open purchase plan', 'purchase-plan'],
  ];
  const topic = topics.find(([pattern]) => pattern.test(query));
  return topic ? { title: topic[1], text: explainPlan(question, plan, data, options), action: topic[2], destination: topic[3] } : { title: 'I can explain the buying decisions in this plan.', text: 'Ask about this week’s purchase, supplier savings, stockouts, promotions, a 20% budget reduction, ACANA demand, or gross margin. My answers use this local scenario; I do not search supplier sites or send orders.', action: 'Explore the purchase plan', destination: 'purchase-plan' };
}

export function BuyingCopilot({ data, plan, options = {}, onNavigate, onReduceBudget }) {
  const [question, setQuestion] = useState(copilotQuestions[0]);
  const [input, setInput] = useState('');
  const answer = copilotAnswer(question, data, plan, options);
  const ask = (event) => { event.preventDefault(); if (input.trim()) { setQuestion(input.trim()); setInput(''); } };
  return <section className="sb-copilot sb-panel" aria-labelledby="sb-copilot-title">
    <div className="sb-panel-heading"><div className="sb-copilot-heading"><span className="sb-copilot-icon"><Sparkles size={21} aria-hidden="true" /></span><div><h3 id="sb-copilot-title">Buying Copilot</h3><p>Your plan, explained in plain language.</p></div></div><span className="sb-badge">Scenario-aware</span></div>
    <div className="sb-copilot-layout"><div className="sb-copilot-questions" aria-label="Suggested buying questions">{copilotQuestions.map((prompt) => <button type="button" className={question === prompt ? 'is-selected' : ''} key={prompt} aria-pressed={question === prompt} onClick={() => setQuestion(prompt)}>{prompt}<ArrowUpRight size={14} aria-hidden="true" /></button>)}</div><div className="sb-copilot-conversation"><p className="sb-copilot-question">{question}</p><div className="sb-copilot-answer" aria-live="polite"><span className="sb-eyebrow"><Sparkles size={13} aria-hidden="true" />Pongo intelligence</span><h4>{answer.title}</h4><p>{answer.text}</p><button className="sb-text-button" type="button" onClick={() => answer.destination === 'budget' ? onReduceBudget() : onNavigate(answer.destination)}>{answer.action}<ArrowRight size={15} aria-hidden="true" /></button></div></div></div>
    <form className="sb-copilot-form" onSubmit={ask}><label className="sr-only" htmlFor="sb-copilot-input">Ask Buying Copilot</label><input id="sb-copilot-input" value={input} maxLength={300} onChange={(event) => setInput(event.target.value)} placeholder="Ask about demand, cash, savings, or your next purchase…" /><button className="primary-button" type="submit" disabled={!input.trim()} aria-label="Ask Buying Copilot"><Send size={17} aria-hidden="true" /></button></form>
    <small className="sb-muted">Answers reflect your current plan. Verify supplier terms before placing an order.</small>
  </section>;
}

export function Opportunities({ data, plan, onAdjust, onNavigate }) {
  const [notice, setNotice] = useState('');
  const lines = activeLines(plan);
  const urgent = [...plan.lines].sort((a, b) => a.daysCover - b.daysCover)[0];
  const promoted = [...lines].filter((line) => line.discount > 0).sort((a, b) => b.savings - a.savings)[0];
  const accelerating = [...lines].sort((a, b) => b.trend - a.trend)[0];
  const subscribed = [...plan.lines].sort((a, b) => b.subscriptionDemand - a.subscriptionDemand)[0];
  const overstock = [...lines].filter((line) => line.cases > 1).sort((a, b) => b.coverageAfter - a.coverageAfter)[0];
  const freightGroup = plan.groups.find((group) => group.freight > 0);
  const cards = [];
  const addCase = (line) => ({ cases: Math.max(1, line.cases + 1), excluded: false });
  const compare = (line, patch) => calculatePlan(data, { ...plan.options, budgetMode: false }, Object.fromEntries(plan.lines.map((item) => [item.id, { cases: item.cases, pinned: item.pinned, excluded: item.excluded, ...(item.id === line.id ? patch : {}) }])));
  if (urgent) cards.push({ id: 'stockout', Icon: PackageCheck, label: 'Stockout prevention', tone: 'peach', title: `Protect ${urgent.name}`, text: `${number(urgent.daysCover)} days of current cover with a ${urgent.leadDays}-day supplier lead time. Confirm this SKU before less urgent purchases.`, value: `${number(urgent.recommendedCases)} cases`, detail: 'forecast recommendation', action: urgent.excluded ? 'Restore recommended quantity' : 'Accept recommended quantity', line: urgent, adjustment: { cases: urgent.recommendedCases, excluded: false } });
  if (promoted) {
    const deal = data.deals.find((item) => item.id === promoted.dealId);
    const next = compare(promoted, addCase(promoted));
    const cash = next.metrics.spend - plan.metrics.spend;
    const savings = next.metrics.savings - plan.metrics.savings;
    cards.push({ id: 'promotion', Icon: BadgePercent, label: 'Promotion window', tone: 'blue', title: `Capture another case of ${promoted.brand}`, text: `${deal?.title || 'Supplier discount'}${deal ? ` closes ${dateLabel(deal.expiry)}` : ''}. The adjustment ${cash >= 0 ? 'adds' : 'releases'} ${money(Math.abs(cash), 2)} in purchase cash, including freight, tax, and supplier thresholds. Check forecast coverage before increasing.`, value: money(savings, 2), detail: 'change in total supplier savings', action: 'Add one promotional case', line: promoted, adjustment: addCase(promoted) });
  }
  if (accelerating) cards.push({ id: 'velocity', Icon: TrendingUp, label: 'Demand acceleration', tone: 'blue', title: `${accelerating.brand} is moving faster`, text: `${accelerating.name} is trending ${number(accelerating.trend, 1)}% against its prior velocity. One additional ${accelerating.casePack}-unit case adds a buffer for demand above forecast.`, value: `+${number(accelerating.trend, 1)}%`, detail: 'recent demand trend', action: 'Add a demand buffer', line: accelerating, adjustment: addCase(accelerating) });
  if (subscribed) cards.push({ id: 'subscriptions', Icon: CheckCheck, label: 'Subscription priority', tone: 'green', title: `Protect known demand for ${subscribed.brand}`, text: `${number(subscribed.subscriptionDemand)} renewal units are expected for ${subscribed.name}. Keep its recommended purchase included to cover recurring customers.`, value: `${number(subscribed.subscriptionDemand)} units`, detail: 'subscription demand in this horizon', action: 'Prioritize renewal coverage', line: subscribed, adjustment: { cases: Math.max(subscribed.cases, subscribed.recommendedCases), excluded: false } });
  if (overstock) {
    const adjustment = { cases: Math.max(0, overstock.cases - 1), excluded: false };
    const next = compare(overstock, adjustment);
    const cash = plan.metrics.spend - next.metrics.spend;
    cards.push({ id: 'overstock', Icon: ArrowDownRight, label: 'Coverage adjustment', tone: 'peach', title: `Revisit ${overstock.brand} coverage`, text: `${overstock.name} reaches ${number(overstock.coverageAfter)} days of cover after this purchase. After removing one case, free-case, rebate, freight, and tax terms are recalculated with the rest of your basket.`, value: money(Math.abs(cash), 2), detail: cash >= 0 ? 'cash released by removing one case' : 'additional cash after supplier thresholds change', action: 'Reduce by one case', line: overstock, adjustment });
  }
  cards.push(freightGroup ? { id: 'freight', Icon: Truck, label: 'Supplier consolidation', tone: 'blue', title: `Review ${freightGroup.name || freightGroup.supplier?.name || 'supplier'} freight`, text: `This supplier order carries ${money(freightGroup.freight)} freight. Compare its ${money(freightGroup.freeFreight || freightGroup.supplier?.freeFreight || 0)} free-freight threshold with eligible forecast purchases before adding stock.`, value: money(freightGroup.freight), detail: 'freight cost to evaluate', action: 'Review supplier allocation', destination: 'purchase-plan' } : { id: 'budget', Icon: Wallet, label: 'Cash optimization', tone: 'green', title: 'Put every buying dollar to work', text: `Your proposed buy is ${money(plan.metrics.spend)}. Compare a smaller cash budget with subscription protection and stockout risk before committing.`, value: money(plan.metrics.savings), detail: 'discounts captured in the current plan', action: 'Compare a buying scenario', destination: 'scenarios' });
  const apply = (card) => { if (card.line) { onAdjust(card.line.id, card.adjustment); setNotice(`${card.line.name}: purchase plan updated to ${card.adjustment.cases} cases.`); } else onNavigate(card.destination); };
  return <div className="sb-stack"><section className="sb-section-intro"><div><span className="sb-eyebrow">Small decisions. Measurable impact.</span><h2>Buying opportunities</h2><p>Prioritized actions grounded in your forecast, supplier offers, and current plan.</p></div><span className="sb-badge sb-badge-blue"><Sparkles size={15} aria-hidden="true" />{cards.length} opportunities</span></section>{notice && <p className="sb-notice" role="status"><Check size={16} aria-hidden="true" />{notice}</p>}<div className="sb-opportunity-grid">{cards.map((card) => <article className="sb-opportunity-card" key={card.id}><span className={`sb-opportunity-icon sb-tone-${card.tone}`}><card.Icon size={21} aria-hidden="true" /></span><span className="sb-eyebrow">{card.label}</span><h3>{card.title}</h3><p>{card.text}</p><div className="sb-opportunity-impact"><strong>{card.value}</strong><span>{card.detail}</span></div><button className="secondary-button" type="button" onClick={() => apply(card)}>{card.action}<ArrowRight size={15} aria-hidden="true" /></button></article>)}</div><div className="sb-method-note"><CircleHelp size={17} aria-hidden="true" /><p>Each action updates the same purchase plan. Cash, margin, and coverage recalculate together; a supplier discount alone never guarantees a better buy.</p></div></div>;
}
