import { ArrowDownRight, ArrowUpRight, Sparkles } from 'lucide-react';
import { useState } from 'react';
import { insightCards, insightRanges } from '../mock-data/data.js';

export default function InsightsDemo() {
  const [range, setRange] = useState('30D');
  const data = insightRanges[range];
  const points = data.chart.map((value, index) => `${index * 105 + 18},${178 - value * 1.72}`).join(' ');
  return (
    <section className="demo-view insights-demo" aria-labelledby="insights-title">
      <header className="demo-heading"><div><span>Business intelligence</span><h3 id="insights-title">Turn operations into decisions</h3><p>Demand, stock risk, and performance signals stay connected to the underlying ledger.</p></div><div className="range-selector" role="group" aria-label="Insights date range">{Object.keys(insightRanges).map((item) => <button type="button" className={range === item ? 'active' : ''} aria-pressed={range === item} key={item} onClick={() => setRange(item)}>{item}</button>)}</div></header>
      <div className="insight-metrics" aria-live="polite"><div><span>Revenue</span><strong>{data.revenue}</strong><small><ArrowUpRight size={12} /> +12.4%</small></div><div><span>Orders</span><strong>{data.orders}</strong><small><ArrowUpRight size={12} /> +8.1%</small></div><div><span>Units</span><strong>{data.units}</strong><small><ArrowUpRight size={12} /> +6.8%</small></div><div><span>Sell-through</span><strong>{data.sellThrough}</strong><small><ArrowUpRight size={12} /> +3.2 pts</small></div><div><span>Days of supply</span><strong>{data.daysSupply}</strong><small className="down"><ArrowDownRight size={12} /> 2 days leaner</small></div></div>
      <div className="insights-layout">
        <article className="demo-card insight-chart-card"><div className="card-heading"><div><span>Executive overview</span><h4>Revenue and demand signal</h4></div><span className="quiet-label">{range}</span></div><svg viewBox="0 0 660 200" role="img" aria-label={`${range} demand trend: ${data.chart.join(', ')}`}><path className="chart-grid" d="M15 40H645M15 95H645M15 150H645" /><polyline className="insight-fill" points={`${points} 648,190 18,190`} /><polyline className="insight-line" points={points} /></svg><div className="chart-axis" aria-hidden="true"><span>Start</span><span>Range midpoint</span><span>Today</span></div></article>
        <aside className="insight-cards">{insightCards.map((card) => <article className={`demo-card insight-signal insight-signal--${card.tone}`} key={card.title}><span><Sparkles size={15} />{card.title}</span><strong>{card.value}</strong><small>{card.meta}</small></article>)}</aside>
      </div>
    </section>
  );
}
