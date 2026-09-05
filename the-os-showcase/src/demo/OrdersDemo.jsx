import { ArrowRight, Download, X } from 'lucide-react';
import { useMemo, useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { orders } from '../mock-data/data.js';

const filters = ['All', 'Ready', 'Allocation required', 'Picking', 'Completed'];

function OrderDetail({ order, onClose }) {
  return (
    <aside className="order-detail glass-panel" role="dialog" aria-modal="true" aria-labelledby="order-detail-title">
      <button className="icon-button order-detail__close" type="button" aria-label="Close order detail" onClick={onClose}><X size={17} /></button>
      <span className="drawer-kicker">Operational order</span><h4 id="order-detail-title">Order #{order.id}</h4><p>{order.customer} · {order.items} items · ${order.total.toFixed(2)}</p>
      <div className="order-progress"><div><span>Fulfillment progress</span><strong>{order.progress}%</strong></div><div><i style={{ width: `${order.progress}%` }} /></div></div>
      <section><h5>Order lines</h5>{order.lines.map((line) => <div className="order-line" key={line.sku}><span><strong>{line.product}</strong><small>{line.sku} · Qty {line.quantity}</small></span><StatusBadge tone={line.allocated === line.quantity ? 'success' : 'warning'}>{line.allocated}/{line.quantity} allocated</StatusBadge></div>)}</section>
      <section><h5>Timeline</h5>{order.timeline.map((entry) => <div className="movement-row" key={entry}><i aria-hidden="true" /><span>{entry}</span></div>)}</section>
    </aside>
  );
}

export default function OrdersDemo() {
  const [filter, setFilter] = useState('All');
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState('Orders are ready for operational review.');
  const filtered = useMemo(() => orders.filter((order) => filter === 'All' || order.status === filter), [filter]);

  return (
    <section className="demo-view orders-demo" aria-labelledby="orders-title">
      <header className="demo-heading"><div><span>Order operations</span><h3 id="orders-title">Every order. Every stage. Visible.</h3><p>Allocation, pick status, fulfillment progress, and history in one flow.</p></div><button className="soft-button" type="button" onClick={() => setMessage(`${filtered.length} sample order rows prepared for fulfillment export.`)}><Download size={15} />Export sample</button></header>
      <div className="order-filters" role="group" aria-label="Filter orders">{filters.map((item) => <button type="button" className={filter === item ? 'active' : ''} aria-pressed={filter === item} onClick={() => setFilter(item)} key={item}>{item}<b>{item === 'All' ? 186 : orders.filter((order) => order.status === item).length}</b></button>)}</div>
      <div className="orders-stage">
        <div className="table-scroll">
          <table className="demo-table orders-table"><thead><tr><th>Order</th><th>Customer</th><th>Items</th><th>Allocation</th><th>Pick</th><th>Total</th><th>Age</th><th /></tr></thead><tbody>{filtered.map((order) => <tr key={order.id}><td><strong>#{order.id}</strong></td><td>{order.customer}</td><td>{order.items}</td><td><StatusBadge tone={order.allocation === 'Allocated' ? 'success' : 'warning'}>{order.allocation}</StatusBadge></td><td>{order.pick}</td><td>${order.total.toFixed(2)}</td><td>{order.age}</td><td><button className="row-action" type="button" aria-label={`Open order ${order.id}`} onClick={() => setSelected(order)}><ArrowRight size={15} /></button></td></tr>)}</tbody></table>
        </div>
        {selected && <OrderDetail order={selected} onClose={() => setSelected(null)} />}
      </div>
      <div className="demo-status" role="status" aria-live="polite"><span>{filtered.length} sample orders shown</span><span>{message}</span></div>
    </section>
  );
}
