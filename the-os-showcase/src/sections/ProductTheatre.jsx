import Reveal from '../components/Reveal.jsx';
import SectionHeading from '../components/SectionHeading.jsx';
import InteractiveOSWindow from '../demo/InteractiveOSWindow.jsx';

export default function ProductTheatre({ activeModule, onModuleChange }) {
  return (
    <section className="section product-theatre" id="inventory" aria-labelledby="theatre-heading">
      <Reveal><SectionHeading eyebrow="Interactive product theatre" title="Explore the system, not a slideshow." body="Every tab, filter, drawer, scanner, stepper, range selector, route control, and safety preview below runs entirely in local state." /></Reveal>
      <Reveal delay={90}><InteractiveOSWindow activeModule={activeModule} onModuleChange={onModuleChange} /></Reveal>
    </section>
  );
}
