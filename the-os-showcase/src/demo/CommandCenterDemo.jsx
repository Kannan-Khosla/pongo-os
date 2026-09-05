import { AlertTriangle, ArrowUpRight, Boxes, CheckCircle2, PackageCheck, ShoppingBag, Truck } from 'lucide-react';
import { useState } from 'react';
import MetricCard from '../components/MetricCard.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import { attentionItems, commandMetrics, pipeline } from '../mock-data/data.js';

const metricIcons = [ShoppingBag, PackageCheck, AlertTriangle, Truck, Boxes, CheckCircle2];

export default function CommandCenterDemo() {
  const [stage, setStage] = useState('ready');
  const [issue, setIssue] = useState('low-stock');
  const activeStage = pipeline.find((item) => item.id === stage);
  const activeIssue = attentionItems.find((item) => item.id === issue);

  return (
    <section className="demo-view" aria-labelledby="command-title">
      <header className="demo-heading">
        <div><span>Thursday · August 13</span><h3 id="command-title">Command center</h3><p>One operational picture, from storefront to final stop.</p></div>
        <StatusBadge tone="success">Live workspace</StatusBadge>
      </header>
      <div className="command-metrics">
        {commandMetrics.map((metric, index) => {
          const Icon = metricIcons[index];
          return <div className="command-metric" key={metric.label}><Icon size={16} aria-hidden="true" /><MetricCard {...metric} compact /></div>;
        })}
      </div>
      <div className="command-layout">
        <article className="demo-card pipeline-card">
          <div className="card-heading"><div><span>Order pipeline</span><h4>Today’s flow</h4></div><span className="quiet-label">Updated just now</span></div>
          <div className="pipeline" role="group" aria-label="Order pipeline stages">
            {pipeline.map((item, index) => (
              <div className="pipeline__step" key={item.id}>
                <button type="button" className={stage === item.id ? 'active' : ''} aria-pressed={stage === item.id} onClick={() => setStage(item.id)}>
                  <span>{item.label}</span><strong>{item.value}</strong>
                </button>
                {index < pipeline.length - 1 && <i aria-hidden="true" />}
              </div>
            ))}
          </div>
          <div className="pipeline-detail" aria-live="polite"><span>{activeStage.label}</span><strong>{activeStage.value} records</strong><p>{activeStage.detail}</p></div>
          <svg className="command-chart" viewBox="0 0 680 190" role="img" aria-label="Order throughput increased over the last seven days">
            <defs><linearGradient id="commandFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#7267e7" stopOpacity=".24" /><stop offset="1" stopColor="#7267e7" stopOpacity="0" /></linearGradient></defs>
            <path className="chart-grid" d="M10 35H670M10 90H670M10 145H670" />
            <path className="chart-fill" d="M10 151C63 143 83 103 135 115s75-40 123-21 81 22 127-15 74-11 124-31 92-18 161-8v145H10Z" />
            <path className="chart-line" d="M10 151C63 143 83 103 135 115s75-40 123-21 81 22 127-15 74-11 124-31 92-18 161-8" />
          </svg>
          <div className="chart-axis" aria-hidden="true"><span>Fri</span><span>Sat</span><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span></div>
        </article>
        <article className="demo-card attention-card">
          <div className="card-heading"><div><span>Attention center</span><h4>What needs you</h4></div><b>31</b></div>
          <div className="attention-list">
            {attentionItems.map((item) => <button type="button" className={issue === item.id ? 'active' : ''} aria-pressed={issue === item.id} key={item.id} onClick={() => setIssue(item.id)}><i className={`tone-${item.tone}`} aria-hidden="true" /><span><strong>{item.label}</strong><small>{item.meta}</small></span><ArrowUpRight size={14} /></button>)}
          </div>
          <div className="attention-detail" aria-live="polite"><strong>{activeIssue.label}</strong>{activeIssue.rows.map((row) => <span key={row}>{row}</span>)}</div>
        </article>
      </div>
    </section>
  );
}
