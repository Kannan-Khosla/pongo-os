import { ArrowDown, ArrowRight, Boxes, Check, PackageCheck, ShoppingCart, Sparkles } from 'lucide-react';
import Brand from '../components/Brand.jsx';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import { company, pipeline } from '../mock-data/data.js';

export default function Hero({ onExplore, onOpenModule }) {
  return (
    <section className="hero" id="top" aria-labelledby="hero-title">
      <div className="hero__ambient hero__ambient--one" aria-hidden="true" /><div className="hero__ambient hero__ambient--two" aria-hidden="true" />
      <Reveal className="hero__copy">
        <span className="hero__eyebrow"><Sparkles size={14} />The operating layer for modern commerce</span>
        <h1 id="hero-title">Run your entire operation from one OS.</h1>
        <p>Manage inventory, orders, receiving, picking, fulfillment, analytics, and commerce operations from one intelligent workspace.</p>
        <div className="hero__actions"><button className="button button--primary" type="button" onClick={onExplore}>Explore The-OS <ArrowRight size={16} /></button><a className="button button--ghost" href="#platform">See how it works <ArrowDown size={16} /></a></div>
        <div className="hero__proof"><span><Check size={14} />Local interactive demo</span><span><Check size={14} />Synthetic data</span><span><Check size={14} />No account required</span></div>
      </Reveal>
      <Reveal className="hero__product" delay={120}>
        <div className="hero-orbit" aria-hidden="true" />
        <GlassPanel className="hero-window">
          <div className="hero-window__bar"><Brand compact /><span>{company.name}</span><div><i aria-hidden="true" />System healthy</div></div>
          <div className="hero-window__body">
            <nav aria-label="Hero preview modules"><button type="button" aria-label="Open command center demo" onClick={() => onOpenModule('command')}><Sparkles size={16} /></button><button type="button" aria-label="Open inventory demo" onClick={() => onOpenModule('inventory')}><Boxes size={16} /></button><button type="button" aria-label="Open orders demo" onClick={() => onOpenModule('orders')}><ShoppingCart size={16} /></button><button type="button" aria-label="Open picking demo" onClick={() => onOpenModule('picking')}><PackageCheck size={16} /></button></nav>
            <div className="hero-dashboard">
              <header><div><span>THURSDAY · AUGUST 13</span><h2>Operational command</h2></div><StatusBadge tone="success">Live sample</StatusBadge></header>
              <div className="hero-dashboard__metrics">{company.stats.slice(0, 3).map((metric) => <article key={metric.label}><span>{metric.label}</span><strong>{metric.value}</strong><small>{metric.detail}</small></article>)}</div>
              <div className="hero-dashboard__content">
                <article><div className="mini-heading"><div><span>THROUGHPUT</span><strong>Orders moving today</strong></div><b>+14.2%</b></div><svg viewBox="0 0 480 170" role="img" aria-label="Order throughput trending upward"><defs><linearGradient id="heroFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#6571e9" stopOpacity=".28" /><stop offset="1" stopColor="#6571e9" stopOpacity="0" /></linearGradient></defs><path className="chart-grid" d="M10 36H470M10 88H470M10 140H470" /><path className="hero-chart-fill" d="M10 137C53 127 76 95 111 108s69-34 108-10 70 4 109-22 72-34 142-15v99H10Z" /><path className="hero-chart-line" d="M10 137C53 127 76 95 111 108s69-34 108-10 70 4 109-22 72-34 142-15" /></svg></article>
                <aside><div className="mini-heading"><div><span>PIPELINE</span><strong>Order flow</strong></div></div>{pipeline.slice(0, 4).map((item, index) => <button type="button" key={item.id} onClick={() => onOpenModule('command')}><i className={index < 3 ? 'complete' : ''} aria-hidden="true" /><span>{item.label}</span><strong>{item.value}</strong></button>)}</aside>
              </div>
            </div>
          </div>
        </GlassPanel>
        <GlassPanel className="hero-float hero-float--stock"><span><Boxes size={16} /></span><div><small>Inventory synchronized</small><strong>2,482 records matched</strong></div><b>Safe</b></GlassPanel>
        <GlassPanel className="hero-float hero-float--pick"><span><PackageCheck size={16} /></span><div><small>Order #10428</small><strong>Ready for next scan</strong></div></GlassPanel>
      </Reveal>
    </section>
  );
}
