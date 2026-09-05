import { ArrowRight, BarChart3, FileBarChart, Sparkles } from 'lucide-react';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';

export default function IntelligenceStory({ onOpenModule }) {
  return (
    <section className="section intelligence-story" id="intelligence" aria-labelledby="intelligence-heading">
      <Reveal><SectionHeading eyebrow="Intelligence" title="Turn operational activity into the next decision." body="Reports explain what moved. Insights surface what deserves attention next. Both remain tied to transparent source rows." /></Reveal>
      <Reveal className="intelligence-composition" delay={80}>
        <GlassPanel className="executive-panel">
          <div className="executive-panel__heading"><div><span className="eyebrow">Executive overview</span><h3>Signal, with the evidence close by.</h3></div><span className="signal-orb"><Sparkles /></span></div>
          <div className="executive-metrics"><div><span>Revenue</span><strong>$742k</strong><small>+12.4% · 30D</small></div><div><span>Orders</span><strong>2,486</strong><small>+8.1%</small></div><div><span>Sell-through</span><strong>72%</strong><small>+3.2 pts</small></div><div><span>Days of supply</span><strong>38</strong><small>2 days leaner</small></div></div>
          <svg viewBox="0 0 760 250" role="img" aria-label="Synthetic revenue and demand trend rising over 30 days"><defs><linearGradient id="intelligenceFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#706ae7" stopOpacity=".25" /><stop offset="1" stopColor="#706ae7" stopOpacity="0" /></linearGradient></defs><path className="chart-grid" d="M15 45H745M15 115H745M15 185H745" /><path className="intelligence-fill" d="M15 188C76 161 92 178 149 132s102 23 160-19 96-21 156-52 96 19 147-4 75-25 133-13v180H15Z" /><path className="intelligence-line" d="M15 188C76 161 92 178 149 132s102 23 160-19 96-21 156-52 96 19 147-4 75-25 133-13" /></svg>
          <button type="button" onClick={() => onOpenModule('insights')}>Explore insights <ArrowRight size={14} /></button>
        </GlassPanel>
        <div className="intelligence-side">
          <GlassPanel as="article"><span><BarChart3 /></span><div><small>INVENTORY INTELLIGENCE</small><h3>12 reorder candidates</h3><p>$14,280 suggested replenishment value.</p></div><button type="button" aria-label="Open insights demo" onClick={() => onOpenModule('insights')}><ArrowRight /></button></GlassPanel>
          <GlassPanel as="article"><span><FileBarChart /></span><div><small>REPORT WORKSPACE</small><h3>6 report families</h3><p>Valuation, low stock, movements, SKU orders, receiving, fulfillment.</p></div><button type="button" aria-label="Open reports demo" onClick={() => onOpenModule('reports')}><ArrowRight /></button></GlassPanel>
        </div>
      </Reveal>
    </section>
  );
}
