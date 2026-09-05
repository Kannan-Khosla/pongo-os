import { Download, Search, SlidersHorizontal, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { inventory, locations } from '../mock-data/data.js';

const statuses = ['All', 'Healthy', 'Low stock', 'Out of stock'];

function ProductDrawer({ product, onClose }) {
  const closeRef = useRef(null);
  useEffect(() => {
    closeRef.current?.focus();
    const closeOnEscape = (event) => { if (event.key === 'Escape') onClose(); };
    document.addEventListener('keydown', closeOnEscape);
    return () => document.removeEventListener('keydown', closeOnEscape);
  }, [onClose]);

  return (
    <aside className="product-drawer glass-panel" role="dialog" aria-modal="true" aria-labelledby="product-drawer-title">
      <button className="icon-button product-drawer__close" type="button" aria-label="Close product details" onClick={onClose} ref={closeRef}><X size={17} /></button>
      <span className="drawer-kicker">Inventory detail</span>
      <div className="product-identity"><span className={`product-swatch product-swatch--${product.id}`} aria-hidden="true" /><div><h4 id="product-drawer-title">{product.product}</h4><p>{product.sku} · {product.category}</p></div></div>
      <p className="drawer-description">{product.description}</p>
      <div className="drawer-metrics"><div><span>Available</span><strong>{product.available}</strong></div><div><span>Unit cost</span><strong>${product.cost.toFixed(2)}</strong></div><div><span>Valuation</span><strong>${product.valuation.toLocaleString()}</strong></div></div>
      <section><h5>Inventory by location</h5>{product.byLocation.map((row) => <div className="drawer-row" key={row.name}><span>{row.name}</span><strong>{row.units} units</strong></div>)}</section>
      <section><h5>Recent movements</h5>{product.movements.map((movement) => <div className="movement-row" key={movement}><i aria-hidden="true" /><span>{movement}</span></div>)}</section>
    </aside>
  );
}

export default function InventoryDemo() {
  const [query, setQuery] = useState('');
  const [warehouse, setWarehouse] = useState('all');
  const [status, setStatus] = useState('All');
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState('Showing synthetic inventory across three warehouses.');

  const filtered = useMemo(() => inventory.filter((product) => {
    const searchMatch = [product.product, product.sku, product.barcode, product.category].join(' ').toLowerCase().includes(query.toLowerCase());
    const locationMatch = warehouse === 'all' || product.warehouse === warehouse;
    const statusMatch = status === 'All' || product.status === status;
    return searchMatch && locationMatch && statusMatch;
  }), [query, warehouse, status]);

  return (
    <section className="demo-view inventory-demo" aria-labelledby="inventory-title">
      <header className="demo-heading">
        <div><span>Inventory control</span><h3 id="inventory-title">One source of truth for every unit</h3><p>Search, filter, and inspect stock without leaving the workspace.</p></div>
        <button className="soft-button" type="button" onClick={() => setMessage(`${filtered.length} sample inventory rows prepared for CSV export.`)}><Download size={15} />Export sample</button>
      </header>
      <div className="inventory-controls">
        <label className="search-control" htmlFor="inventory-query"><Search size={16} /><span className="sr-only">Search inventory</span><input id="inventory-query" type="search" value={query} placeholder="Product, SKU or barcode" onChange={(event) => setQuery(event.target.value)} /></label>
        <label className="select-control" htmlFor="warehouse-select"><span>Location</span><select id="warehouse-select" value={warehouse} onChange={(event) => setWarehouse(event.target.value)}>{locations.map((location) => <option value={location.id} key={location.id}>{location.name}</option>)}</select></label>
        <div className="segment-control" role="group" aria-label="Inventory status"><SlidersHorizontal size={15} aria-hidden="true" />{statuses.map((item) => <button type="button" className={status === item ? 'active' : ''} aria-pressed={status === item} key={item} onClick={() => setStatus(item)}>{item}</button>)}</div>
      </div>
      <div className="inventory-stage">
        <div className="table-scroll">
          <table className="demo-table">
            <thead><tr><th>Product</th><th>SKU / barcode</th><th>Location</th><th>On hand</th><th>Allocated</th><th>Available</th><th>Status</th></tr></thead>
            <tbody>
              {filtered.map((product) => (
                <tr key={product.id}>
                  <td><button className="table-product" type="button" onClick={() => setSelected(product)}><span className={`product-swatch product-swatch--${product.id}`} aria-hidden="true" /><span><strong>{product.product}</strong><small>{product.category}</small></span></button></td>
                  <td><strong>{product.sku}</strong><small>{product.barcode}</small></td><td>{product.location}</td><td>{product.onHand}</td><td>{product.allocated}</td><td><strong>{product.available}</strong></td><td><StatusBadge tone={product.status === 'Healthy' ? 'success' : product.status === 'Low stock' ? 'warning' : 'danger'}>{product.status}</StatusBadge></td>
                </tr>
              ))}
            </tbody>
          </table>
          {!filtered.length && <div className="empty-state">No products match those filters.</div>}
        </div>
        {selected && <ProductDrawer product={selected} onClose={() => setSelected(null)} />}
      </div>
      <div className="demo-status" role="status" aria-live="polite"><span>{filtered.length} products shown</span><span>{message}</span></div>
    </section>
  );
}
