import { ArrowRight, Menu, X } from 'lucide-react';
import { useState } from 'react';
import Brand from './Brand.jsx';

const links = [
  ['Platform', '#platform'],
  ['Inventory', '#inventory'],
  ['Operations', '#operations'],
  ['Intelligence', '#intelligence'],
  ['Integrations', '#integrations'],
];

export default function Navigation({ onExplore, onRequest }) {
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

  return (
    <header className="floating-nav glass-panel">
      <a href="#top" aria-label="The-OS home" onClick={close}><Brand /></a>
      <nav className="floating-nav__links" aria-label="Primary navigation">
        {links.map(([label, href]) => <a href={href} key={href}>{label}</a>)}
      </nav>
      <div className="floating-nav__actions">
        <button className="nav-text-button" type="button" onClick={onExplore}>Explore demo</button>
        <button className="button button--primary button--small" type="button" onClick={onRequest}>Request access <ArrowRight size={15} /></button>
      </div>
      <button className="nav-menu-button" type="button" aria-expanded={open} aria-controls="mobile-navigation" aria-label={open ? 'Close navigation' : 'Open navigation'} onClick={() => setOpen((value) => !value)}>{open ? <X /> : <Menu />}</button>
      <nav className="mobile-navigation" id="mobile-navigation" aria-label="Mobile navigation" hidden={!open}>
        {links.map(([label, href]) => <a href={href} key={href} onClick={close}>{label}</a>)}
        <button type="button" onClick={() => { close(); onExplore(); }}>Explore demo</button>
        <button type="button" onClick={() => { close(); onRequest(); }}>Request access</button>
      </nav>
    </header>
  );
}
