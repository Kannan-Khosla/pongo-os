import { ArrowRight, Check, HeartPulse, Map, RefreshCw, ShieldCheck, ShoppingBag } from 'lucide-react';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import { systemHealth } from '../mock-data/data.js';

export default function ReliabilityStory({ onOpenModule }) {
  return (
    <section className="section reliability-story" id="integrations" aria-labelledby="integrations-heading">
      <Reveal><SectionHeading eyebrow="Routes + integrations" title="Execution outside the warehouse, control inside the system." body="Plan the final stop sequence and keep commerce synchronization observable, previewable, and protected." /></Reveal>
      <div className="reliability-grid">
        <Reveal delay={40}><GlassPanel as="article" className="route-story-card"><div className="route-story-card__top"><span><Map /></span><StatusBadge tone="info">Draft route</StatusBadge></div><span className="eyebrow">Route R-204</span><h3>Four fictional districts. One ordered run.</h3><div className="district-list"><span><i>1</i>Downtown</span><span><i>2</i>West End</span><span><i>3</i>North Industrial</span><span><i>4</i>South Business District</span></div><button type="button" onClick={() => onOpenModule('routes')}>Open route studio <ArrowRight size={14} /></button></GlassPanel></Reveal>
        <Reveal delay={90}><GlassPanel as="article" className="integration-story-card"><div className="integration-story-card__top"><span><ShoppingBag /></span><div><small>COMMERCE INTEGRATION</small><h3>WooCommerce</h3></div><StatusBadge tone="success">Connected</StatusBadge></div><div className="integration-capabilities"><span><Check />Products + variations</span><span><Check />Order synchronization</span><span><Check />Inventory synchronization</span><span><ShieldCheck />Controlled writeback</span></div><button type="button" onClick={() => onOpenModule('integrations')}>Inspect safe sync <ArrowRight size={14} /></button></GlassPanel></Reveal>
        <Reveal delay={140}><GlassPanel as="article" className="health-story-card"><div className="card-heading"><div><span>System health</span><h3>Reliability made visible</h3></div><HeartPulse /></div>{systemHealth.slice(0, 4).map((item) => <div className="health-story-row" key={item.label}><i aria-hidden="true" /><span><strong>{item.label}</strong><small>{item.meta}</small></span><b>{item.value}</b></div>)}<div className="health-story-footer"><RefreshCw size={13} />Status values are simulated locally.</div></GlassPanel></Reveal>
      </div>
    </section>
  );
}
