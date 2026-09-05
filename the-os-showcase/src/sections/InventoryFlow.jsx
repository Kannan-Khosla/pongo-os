import { ArrowRight, Box, Boxes, MapPin, PackageCheck } from 'lucide-react';
import { useState } from 'react';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';
import { warehouses } from '../mock-data/data.js';

export default function InventoryFlow({ onOpenModule }) {
  const [warehouseId, setWarehouseId] = useState('atlas');
  const warehouse = warehouses.find((item) => item.id === warehouseId);
  return (
    <section className="section inventory-flow" aria-labelledby="flow-heading">
      <Reveal><SectionHeading eyebrow="Inventory" title="Know exactly what you have and where it is." body="A product becomes operational context: warehouse, location, on-hand quantity, allocations, available stock, cost, and movement history." /></Reveal>
      <Reveal className="inventory-flow__grid" delay={80}>
        <GlassPanel className="inventory-path">
          <div className="inventory-path__product"><span><Box /></span><div><small>PRODUCT</small><strong>AeroCharge Dock</strong><p>ACD-440 · Electronics</p></div></div>
          <div className="inventory-path__rail" aria-hidden="true"><i /><ArrowRight /><i /><ArrowRight /><i /></div>
          <div className="inventory-path__stages"><span><Boxes size={18} /><b>{warehouse.name}</b></span><span><MapPin size={18} /><b>{warehouse.zones[0].name}</b></span><span><PackageCheck size={18} /><b>{warehouse.units.toLocaleString()} units</b></span></div>
          <button className="text-button" type="button" onClick={() => onOpenModule('inventory')}>Open inventory control <ArrowRight size={14} /></button>
        </GlassPanel>
        <div className="warehouse-selector" role="group" aria-label="Update inventory flow warehouse">{warehouses.map((item) => <button type="button" aria-pressed={warehouseId === item.id} className={warehouseId === item.id ? 'active glass-panel' : 'glass-panel'} key={item.id} onClick={() => setWarehouseId(item.id)}><span><strong>{item.name}</strong><small>{item.subtitle}</small></span><b>{item.units.toLocaleString()}<small>units</small></b><i><em style={{ width: `${item.capacity}%` }} /></i></button>)}</div>
      </Reveal>
    </section>
  );
}
