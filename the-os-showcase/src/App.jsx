import { useCallback, useState } from 'react';
import Brand from './components/Brand.jsx';
import LocalModal from './components/LocalModal.jsx';
import Navigation from './components/Navigation.jsx';
import FinalCTA from './sections/FinalCTA.jsx';
import Hero from './sections/Hero.jsx';
import IntelligenceStory from './sections/IntelligenceStory.jsx';
import InventoryFlow from './sections/InventoryFlow.jsx';
import OperatingLayer from './sections/OperatingLayer.jsx';
import OperationsStories from './sections/OperationsStories.jsx';
import PlatformOverview from './sections/PlatformOverview.jsx';
import ProductTheatre from './sections/ProductTheatre.jsx';
import ReliabilityStory from './sections/ReliabilityStory.jsx';

export default function App() {
  const [activeModule, setActiveModule] = useState('command');
  const [modalOpen, setModalOpen] = useState(false);

  const scrollToDemo = useCallback(() => {
    document.getElementById('inventory')?.scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'start' });
  }, []);

  const openModule = useCallback((module) => {
    setActiveModule(module);
    scrollToDemo();
  }, [scrollToDemo]);

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to main content</a>
      <div className="page-ambient page-ambient--one" aria-hidden="true" />
      <div className="page-ambient page-ambient--two" aria-hidden="true" />
      <Navigation onExplore={scrollToDemo} onRequest={() => setModalOpen(true)} />
      <main id="main-content">
        <Hero onExplore={scrollToDemo} onOpenModule={openModule} />
        <OperatingLayer onOpenModule={openModule} />
        <ProductTheatre activeModule={activeModule} onModuleChange={setActiveModule} />
        <InventoryFlow onOpenModule={openModule} />
        <OperationsStories onOpenModule={openModule} />
        <IntelligenceStory onOpenModule={openModule} />
        <ReliabilityStory onOpenModule={openModule} />
        <PlatformOverview />
        <FinalCTA onExplore={scrollToDemo} onRequest={() => setModalOpen(true)} />
      </main>
      <footer className="site-footer"><a href="#top" aria-label="Back to The-OS home"><Brand /></a><p>Standalone interactive product showcase · Synthetic data only</p><a href="#top">Back to top ↑</a></footer>
      <LocalModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </>
  );
}
