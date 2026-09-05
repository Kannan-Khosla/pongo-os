import { Check, RefreshCw, ShieldCheck, ShoppingBag } from 'lucide-react';
import { useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { integrationCapabilities, systemHealth } from '../mock-data/data.js';

export default function IntegrationsDemo() {
  const [previewed, setPreviewed] = useState(false);
  const [message, setMessage] = useState('No network calls are made by this showcase.');
  function preview() {
    setPreviewed(true);
    setMessage('Safe preview complete: 2,482 matched · 3 new · 2 need review · nothing written remotely.');
  }
  return (
    <section className="demo-view integrations-demo" aria-labelledby="integrations-title">
      <header className="demo-heading"><div><span>Commerce infrastructure</span><h3 id="integrations-title">Connected, controlled, observable</h3><p>Commerce data flows in; guarded approvals protect what flows back.</p></div><StatusBadge tone="success">Systems healthy</StatusBadge></header>
      <div className="integrations-layout">
        <article className="demo-card commerce-card"><div className="commerce-card__top"><span className="commerce-icon"><ShoppingBag /></span><div><span className="drawer-kicker">Commerce integration</span><h4>WooCommerce</h4></div><StatusBadge tone="success">Connected</StatusBadge></div><div className="capability-list">{integrationCapabilities.map((item) => <span key={item}><Check size={14} />{item}</span>)}</div><div className={`sync-preview${previewed ? ' active' : ''}`}><div><span>Read-only sync preview</span><strong>{previewed ? '2,482 matched' : 'Ready to compare'}</strong><small>{previewed ? '3 new · 2 review · 0 remote writes' : 'Product and variation identifiers'}</small></div><i aria-hidden="true"><RefreshCw /></i></div><button className="button button--primary" type="button" onClick={preview} disabled={previewed}>{previewed ? 'Preview complete' : 'Run safe preview'}</button></article>
        <article className="demo-card health-card"><div className="card-heading"><div><span>System health</span><h4>Operational safeguards</h4></div><ShieldCheck size={21} /></div><div className="health-list">{systemHealth.map((item) => <div key={item.label}><i aria-hidden="true" /><span><strong>{item.label}</strong><small>{item.meta}</small></span><b>{item.value}</b></div>)}</div></article>
      </div>
      <aside className="expandable-note"><span>Expandable integration architecture</span><p>Additional providers are intentionally described as architectural possibilities—not advertised as connected capabilities.</p></aside>
      <div className="demo-status" role="status" aria-live="polite"><span>No credentials · no API calls</span><span>{message}</span></div>
    </section>
  );
}
