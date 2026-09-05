import { Check, RotateCcw, ScanLine } from 'lucide-react';
import { useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { pickItems } from '../mock-data/data.js';

export default function PickingDemo() {
  const [picked, setPicked] = useState(2);
  const [scan, setScan] = useState('');
  const [state, setState] = useState('Waiting for next scan');
  const complete = picked === pickItems.length;
  const nextItem = pickItems[Math.min(picked, pickItems.length - 1)];

  function verifyScan(value = scan) {
    if (complete) return;
    if (!value.trim()) { setState(`Enter ${nextItem.barcode} or use the demo scan.`); return; }
    const valid = [nextItem.barcode, nextItem.sku].includes(value.trim());
    if (!valid) { setState('Code does not match the next pick item.'); return; }
    setState('Scanned · Verified · Picked');
    setPicked((current) => current + 1);
    setScan('');
  }

  function reset() { setPicked(2); setScan(''); setState('Waiting for next scan'); }

  return (
    <section className={`demo-view picking-demo${complete ? ' is-complete' : ''}`} aria-labelledby="picking-title">
      <header className="demo-heading"><div><span>Warehouse floor</span><h3 id="picking-title">Pick order #10428</h3><p>Scan verification keeps the operator moving and the audit trail clean.</p></div><StatusBadge tone={complete ? 'success' : 'info'}>{complete ? 'Pick complete' : 'In progress'}</StatusBadge></header>
      <div className="pick-overview">
        <article className="pick-progress-card demo-card"><div className="pick-progress-card__top"><div><span>Order progress</span><strong>{picked} / {pickItems.length}</strong></div><b>{Math.round((picked / pickItems.length) * 100)}%</b></div><div className="progress-track"><i style={{ width: `${(picked / pickItems.length) * 100}%` }} /></div><div className="pick-progress-card__meta"><span>Cart 06</span><span>Atlas Warehouse</span><span>{Math.max(0, pickItems.length - picked)} remaining</span></div></article>
        <article className="scanner-card demo-card">
          <div className="scanner-orb" aria-hidden="true">{complete ? <Check /> : <ScanLine />}</div>
          <div><span className="drawer-kicker">{complete ? 'Order verified' : 'Next item'}</span><h4>{complete ? 'All items picked' : nextItem.product}</h4><p>{complete ? 'The pick can now be committed.' : `${nextItem.sku} · Aisle ${nextItem.location} · Qty ${nextItem.quantity}`}</p></div>
          {!complete && <label className="scanner-input" htmlFor="pick-scan"><span>Scan SKU or barcode</span><div><input id="pick-scan" value={scan} onChange={(event) => setScan(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter') verifyScan(); }} placeholder={nextItem.barcode} inputMode="numeric" /><button type="button" onClick={() => verifyScan(nextItem.barcode)}>Demo scan</button></div></label>}
          {complete && <button className="button button--primary" type="button" onClick={() => setState('Pick committed. Four local stock movement rows recorded in the simulation.')}>Commit pick</button>}
          <div className="scanner-state" role="status" aria-live="polite"><i className={complete ? 'success' : ''} aria-hidden="true" />{state}</div>
        </article>
      </div>
      <div className="pick-items">
        {pickItems.map((item, index) => <article className={index < picked ? 'picked' : index === picked ? 'active' : ''} key={item.id}><span>{index < picked ? <Check size={16} /> : index + 1}</span><div><strong>{item.product}</strong><small>{item.sku} · {item.location}</small></div><b>{index < picked ? 'Picked' : index === picked ? 'Next' : 'Waiting'}</b></article>)}
      </div>
      <button className="reset-button" type="button" onClick={reset}><RotateCcw size={14} />Reset demo</button>
    </section>
  );
}
