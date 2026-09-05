import { BarChart3, Boxes, CheckCircle2, PackageOpen, Route, ShieldCheck, ShoppingCart, Warehouse } from 'lucide-react';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';

const features = [
  [Boxes, 'Catalog + inventory', 'Items, imports, locations, availability, valuation, and movement history.'],
  [ShoppingCart, 'Order operations', 'Open orders, allocation state, exceptions, completed orders, and history.'],
  [PackageOpen, 'Warehouse execution', 'Receiving, scanning, cycle counts, adjustments, and picking.'],
  [Warehouse, 'Location control', 'Warehouse and location-level quantities, capacity context, and transfers.'],
  [BarChart3, 'Reports + insights', 'Operational reports, executive metrics, demand signals, and stock risk.'],
  [Route, 'Route planning', 'Candidate orders, sequenced stops, estimated completion, and route history.'],
  [ShieldCheck, 'Commerce safety', 'Preview, remap, queued approvals, writeback protection, and sync health.'],
  [CheckCircle2, 'Auditability', 'Every stock-changing action belongs to a traceable movement record.'],
];

export default function PlatformOverview() {
  return (
    <section className="section platform-overview" aria-labelledby="overview-heading">
      <Reveal><SectionHeading eyebrow="Platform overview" title="Not another disconnected inventory screen." body="The-OS is presented as an operating layer: each module carries enough context for the next team and the next decision." /></Reveal>
      <div className="overview-grid">{features.map(([Icon, title, body], index) => <Reveal as="article" className="overview-card" delay={(index % 4) * 50} key={title}><span><Icon /></span><h3>{title}</h3><p>{body}</p></Reveal>)}</div>
    </section>
  );
}
