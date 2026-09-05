import { Check, ChevronDown, ChevronUp, Navigation, RotateCcw } from 'lucide-react';
import { useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { initialRoute } from '../mock-data/data.js';

export default function RoutesDemo() {
  const [stops, setStops] = useState(initialRoute);
  const [finalized, setFinalized] = useState(false);
  const [message, setMessage] = useState('Draft route ready for review.');

  function move(index, direction) {
    const nextIndex = index + direction;
    if (nextIndex < 0 || nextIndex >= stops.length || finalized) return;
    const next = [...stops];
    [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
    setStops(next);
    setMessage(`${stops[index].name} moved ${direction < 0 ? 'up' : 'down'} in the route.`);
  }

  function reset() { setStops(initialRoute); setFinalized(false); setMessage('Route reset to the initial sequence.'); }

  return (
    <section className="demo-view routes-demo" aria-labelledby="routes-title">
      <header className="demo-heading"><div><span>Last-mile operations</span><h3 id="routes-title">From warehouse to final stop</h3><p>Sequence ready orders, balance the route, and finalize an auditable plan.</p></div><StatusBadge tone={finalized ? 'success' : 'neutral'}>{finalized ? 'Finalized' : 'Draft'}</StatusBadge></header>
      <div className="route-layout">
        <article className={`demo-card route-visual${finalized ? ' finalized' : ''}`} aria-label="Route R-204 visual sequence"><div className="route-visual__grid" aria-hidden="true" /><svg viewBox="0 0 700 430" aria-hidden="true"><path className="route-road" d="M0 80c90 33 147-31 238 4s114 70 208 22S606 37 700 61M90 0c-7 107 23 139 49 207s19 147 5 223M323 0c-33 104-11 141 15 202s-3 136 4 228M552 0c-14 93-12 131 17 189s8 151-17 241M0 319c111-49 168 10 257-10s124-75 228-31 146 5 215-17" /><path className="route-line" d="M112 346C164 312 172 254 245 272S312 145 404 174s81 122 148 69 77-84 112-118" /></svg><span className="route-depot"><Navigation size={17} /></span>{stops.map((stop, index) => <span className="route-pin" style={{ '--x': `${18 + index * 20}%`, '--y': `${75 - (index % 2) * 31 - index * 6}%` }} key={stop.id}><i>{index + 1}</i></span>)}<div className="route-facts glass-panel"><span><b>R-204</b> · Driver 2</span><span>4 stops · 31.6 km</span><span>Est. 2h 18m</span></div></article>
        <article className="demo-card route-list"><div className="card-heading"><div><span>Route R-204</span><h4>Delivery sequence</h4></div><span className="quiet-label">32 orders</span></div><ol>{stops.map((stop, index) => <li key={stop.id}><i>{index + 1}</i><span><strong>{stop.name}</strong><small>{stop.orders} orders · ETA {stop.eta}</small></span><div><button type="button" aria-label={`Move ${stop.name} up`} disabled={index === 0 || finalized} onClick={() => move(index, -1)}><ChevronUp size={14} /></button><button type="button" aria-label={`Move ${stop.name} down`} disabled={index === stops.length - 1 || finalized} onClick={() => move(index, 1)}><ChevronDown size={14} /></button></div></li>)}</ol><div className="route-actions"><button className="soft-button" type="button" onClick={reset}><RotateCcw size={14} />Reset</button><button className="button button--primary" type="button" disabled={finalized} onClick={() => { setFinalized(true); setMessage('Route R-204 finalized and controls locked in the simulation.'); }}>{finalized ? <><Check size={15} />Finalized</> : 'Finalize route'}</button></div></article>
      </div>
      <div className="demo-status" role="status" aria-live="polite"><span>Fictional zones only · no real addresses</span><span>{message}</span></div>
    </section>
  );
}
