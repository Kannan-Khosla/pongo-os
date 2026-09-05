import { ArrowRight, Check } from 'lucide-react';
import Brand from '../components/Brand.jsx';
import GlassPanel from '../components/GlassPanel.jsx';
import Reveal from '../components/Reveal.jsx';

export default function FinalCTA({ onExplore, onRequest }) {
  return (
    <section className="section final-cta" id="request-access" aria-labelledby="cta-heading">
      <Reveal><GlassPanel className="final-cta__panel"><div className="final-cta__glow" aria-hidden="true" /><Brand /><span className="eyebrow">The operation, composed</span><h2 id="cta-heading">Your operation deserves more than inventory software.</h2><p>The-OS connects inventory, orders, warehouse execution, fulfillment, routes, and intelligence into one operating layer.</p><div className="final-cta__actions"><button className="button button--primary" type="button" onClick={onExplore}>Explore The-OS <ArrowRight size={16} /></button><button className="button button--ghost" type="button" onClick={onRequest}>Request a walkthrough</button></div><div className="final-cta__proof"><span><Check />Runs locally</span><span><Check />No production data</span><span><Check />No authentication</span><span><Check />Nothing deployed</span></div></GlassPanel></Reveal>
    </section>
  );
}
