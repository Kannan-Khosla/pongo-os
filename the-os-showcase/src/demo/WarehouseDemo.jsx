import { Boxes, MapPin, Warehouse as WarehouseIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { warehouses } from '../mock-data/data.js';

export default function WarehouseDemo() {
  const [warehouseId, setWarehouseId] = useState('atlas');
  const [zoneName, setZoneName] = useState('A-01');
  const warehouse = useMemo(() => warehouses.find((item) => item.id === warehouseId), [warehouseId]);
  const zone = warehouse.zones.find((item) => item.name === zoneName) || warehouse.zones[0];

  function selectWarehouse(id) {
    const next = warehouses.find((item) => item.id === id);
    setWarehouseId(id);
    setZoneName(next.zones[0].name);
  }

  return (
    <section className="demo-view warehouse-demo" aria-labelledby="warehouse-title">
      <header className="demo-heading"><div><span>Location control</span><h3 id="warehouse-title">Know exactly where every unit lives</h3><p>Warehouse and location cards replace guesswork with precise operational context.</p></div><StatusBadge tone="success">3 active warehouses</StatusBadge></header>
      <div className="warehouse-tabs" role="tablist" aria-label="Warehouses">{warehouses.map((item) => <button role="tab" aria-selected={warehouseId === item.id} type="button" className={warehouseId === item.id ? 'active' : ''} key={item.id} onClick={() => selectWarehouse(item.id)}><WarehouseIcon size={17} /><span><strong>{item.name}</strong><small>{item.subtitle}</small></span></button>)}</div>
      <div className="warehouse-layout">
        <article className="demo-card warehouse-overview">
          <div className="warehouse-overview__top"><div><span className="drawer-kicker">Selected facility</span><h4>{warehouse.name}</h4></div><span className="capacity-ring" style={{ '--capacity': `${warehouse.capacity * 3.6}deg` }}><strong>{warehouse.capacity}%</strong><small>capacity</small></span></div>
          <div className="warehouse-metrics"><div><Boxes size={17} /><span>SKUs<strong>{warehouse.skus.toLocaleString()}</strong></span></div><div><WarehouseIcon size={17} /><span>Units<strong>{warehouse.units.toLocaleString()}</strong></span></div><div><MapPin size={17} /><span>Value<strong>{warehouse.value}</strong></span></div></div>
          <div className="location-diagram" aria-label={`${warehouse.name} locations`}>{warehouse.zones.map((item) => <button type="button" aria-pressed={zone.name === item.name} className={zone.name === item.name ? 'active' : ''} key={item.name} onClick={() => setZoneName(item.name)}><span>{item.name}</span><small>{item.units.toLocaleString()} units</small></button>)}</div>
        </article>
        <article className="demo-card zone-detail" aria-live="polite"><span className="drawer-kicker">Location detail</span><div className="zone-detail__name"><span><MapPin size={22} /></span><div><h4>{zone.name}</h4><p>{warehouse.name}</p></div></div><dl><div><dt>SKU count</dt><dd>{zone.skus}</dd></div><div><dt>Units</dt><dd>{zone.units.toLocaleString()}</dd></div><div><dt>Inventory value</dt><dd>{zone.value}</dd></div></dl><div className="zone-capacity"><div><span>Capacity</span><strong>{zone.capacity}%</strong></div><div><i style={{ width: `${zone.capacity}%` }} /></div></div><p>Location cards show operational capacity without pretending to be a physical map.</p></article>
      </div>
    </section>
  );
}
