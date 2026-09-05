import { Check, PackageOpen, ScanLine, Warehouse } from 'lucide-react';
import { useState } from 'react';
import StatusBadge from '../components/StatusBadge.jsx';
import { receipt } from '../mock-data/data.js';

const steps = [
  { id: 1, label: 'Create receipt', icon: PackageOpen },
  { id: 2, label: 'Select items', icon: ScanLine },
  { id: 3, label: 'Accept delivery', icon: Warehouse },
];

export default function ReceivingDemo() {
  const [step, setStep] = useState(1);
  const [accepted, setAccepted] = useState(false);
  const [message, setMessage] = useState('Draft receipt ready.');

  function advance() {
    if (step < 3) { setStep(step + 1); setMessage(`Step ${step + 1} ready.`); return; }
    setAccepted(true);
    setMessage('Delivery accepted. 560 units and stock movement rows added to the simulation.');
  }

  return (
    <section className="demo-view receiving-demo" aria-labelledby="receiving-title">
      <header className="demo-heading"><div><span>Inbound operations</span><h3 id="receiving-title">Inbound inventory without chaos</h3><p>Preview every line, accept the delivery, and record the stock impact.</p></div><StatusBadge tone={accepted ? 'success' : 'neutral'}>{accepted ? 'Received' : 'Draft receipt'}</StatusBadge></header>
      <div className="receipt-stepper" aria-label="Receiving steps">{steps.map(({ id, label, icon: Icon }, index) => <div key={id}><button type="button" className={step === id ? 'active' : id < step || accepted ? 'complete' : ''} aria-current={step === id ? 'step' : undefined} onClick={() => { if (!accepted) setStep(id); }}><span>{id < step || accepted ? <Check size={15} /> : <Icon size={15} />}</span><b>{id}. {label}</b></button>{index < steps.length - 1 && <i aria-hidden="true" />}</div>)}</div>
      <div className="receiving-layout">
        <article className="demo-card receipt-summary"><span className="drawer-kicker">Incoming shipment</span><h4>{receipt.id}</h4><p>{receipt.supplier}</p><dl><div><dt>SKUs</dt><dd>{receipt.skuCount}</dd></div><div><dt>Units</dt><dd className={accepted ? 'value-pulse' : ''}>{accepted ? '560 received' : receipt.units}</dd></div><div><dt>Destination</dt><dd>{receipt.warehouse}</dd></div></dl><div className="stock-impact"><span>Atlas stock total</span><strong>{accepted ? '18,980' : '18,420'}</strong><small>{accepted ? '+560 units posted' : 'Preview: +560 units'}</small></div></article>
        <article className="demo-card receipt-content">
          {step === 1 && <div className="receipt-step-content"><PackageOpen size={32} /><span className="drawer-kicker">Receipt details</span><h4>Create a traceable inbound record</h4><p>Reference, supplier, destination, and operator notes travel with every stock movement.</p><div className="receipt-fields"><span>{receipt.id}</span><span>{receipt.supplier}</span><span>{receipt.warehouse}</span></div></div>}
          {step === 2 && <div className="receipt-step-content"><ScanLine size={32} /><span className="drawer-kicker">Line preview</span><h4>Confirm every expected item</h4><div className="receipt-lines">{receipt.lines.map((line) => <div key={line.sku}><span><strong>{line.product}</strong><small>{line.sku}</small></span><span>Expected {line.expected}</span><b className={line.expected === line.received ? '' : 'warning-text'}>{line.received} received</b></div>)}</div></div>}
          {step === 3 && <div className="receipt-step-content"><Warehouse size={32} /><span className="drawer-kicker">Stock impact</span><h4>{accepted ? 'Delivery accepted' : 'Ready to accept delivery'}</h4><p>{accepted ? 'The local simulation now includes the new quantities and an auditable receipt record.' : '560 units will be added to Atlas Warehouse. The discrepancy remains visible for review.'}</p><div className="impact-grid"><span><b>+558</b> accepted</span><span><b>−2</b> discrepancy</span><span><b>24</b> movement groups</span></div></div>}
          <button className="button button--primary" type="button" onClick={advance} disabled={accepted}>{accepted ? 'Delivery accepted' : step < 3 ? 'Continue' : 'Accept delivery'}</button>
        </article>
      </div>
      <div className="demo-status" role="status" aria-live="polite"><span>Stock changes create audit records</span><span>{message}</span></div>
    </section>
  );
}
