import { ArrowRight, Check, PackageOpen, ScanLine, ShoppingCart, Warehouse } from 'lucide-react';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';

const chapters = [
  { id: 'orders', eyebrow: 'Orders', title: 'From order to fulfillment without losing visibility.', body: 'Allocation state, shortages, warehouse progress, and completion history stay connected.', icon: ShoppingCart, meta: '186 open · 158 allocated' },
  { id: 'picking', eyebrow: 'Picking', title: 'Built for the warehouse floor.', body: 'Scan verification advances line-by-line progress with a clear completion state.', icon: ScanLine, meta: '42 ready · 11 active' },
  { id: 'receiving', eyebrow: 'Receiving', title: 'Inbound inventory without chaos.', body: 'Create the receipt, validate items, preview the impact, and accept delivery.', icon: PackageOpen, meta: '6 receipts · 1,260 units' },
  { id: 'warehouse', eyebrow: 'Locations', title: 'Capacity and stock context at every location.', body: 'Location cards show SKU count, units, value, and practical capacity without a fake map.', icon: Warehouse, meta: '3 warehouses · 8 zones' },
];

export default function OperationsStories({ onOpenModule }) {
  return (
    <section className="section operations-stories" id="operations" aria-labelledby="operations-heading">
      <Reveal><SectionHeading eyebrow="Warehouse operations" title="The floor moves faster when the software stays clear." body="Four workflows, one interaction language: explicit state, scanner-ready inputs, visible stock impact, and a dependable audit trail." /></Reveal>
      <div className="story-grid">
        {chapters.map(({ id, eyebrow, title, body, icon: Icon, meta }, index) => <Reveal delay={index * 60} key={id}><GlassPanel as="article" className={`story-card story-card--${id}`}><div className="story-card__icon"><Icon /></div><span className="eyebrow">{eyebrow}</span><h3>{title}</h3><p>{body}</p><div className="story-card__meta"><Check size={14} />{meta}</div><button type="button" onClick={() => onOpenModule(id)}>Explore {eyebrow.toLowerCase()} <ArrowRight size={14} /></button></GlassPanel></Reveal>)}
      </div>
    </section>
  );
}
