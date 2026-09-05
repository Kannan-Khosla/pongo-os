import { ArrowRight, BarChart3, Boxes, PackageCheck, ScanLine, ShoppingCart, Truck } from 'lucide-react';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';

const layers = [
  { id: 'inventory', label: 'Inventory', detail: 'Every unit and location', icon: Boxes },
  { id: 'orders', label: 'Orders', detail: 'Demand enters the flow', icon: ShoppingCart },
  { id: 'receiving', label: 'Warehouse', detail: 'Receive, count, move', icon: ScanLine },
  { id: 'picking', label: 'Fulfillment', detail: 'Allocate, pick, complete', icon: PackageCheck },
  { id: 'routes', label: 'Routes', detail: 'Sequence the last mile', icon: Truck },
  { id: 'insights', label: 'Intelligence', detail: 'Turn activity into signal', icon: BarChart3 },
];

export default function OperatingLayer({ onOpenModule }) {
  return (
    <section className="section operating-layer" id="platform" aria-labelledby="platform-heading">
      <Reveal><SectionHeading eyebrow="The operating layer" title="One continuous record. Every operational handoff." body="The-OS connects inventory, order demand, warehouse execution, fulfillment, and intelligence without hiding the audit trail between them." /></Reveal>
      <Reveal className="layer-rail" delay={80}>
        {layers.map(({ id, label, detail, icon: Icon }, index) => <div className="layer-node" key={id}><button type="button" onClick={() => onOpenModule(id)}><span><Icon size={20} /></span><strong>{label}</strong><small>{detail}</small></button>{index < layers.length - 1 && <i aria-hidden="true"><ArrowRight size={15} /></i>}</div>)}
      </Reveal>
    </section>
  );
}
