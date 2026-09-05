import { BarChart3, Bell, Boxes, Command, FileBarChart, HeartPulse, Map, PackageCheck, PackageOpen, Search, ShoppingCart, Warehouse } from 'lucide-react';
import { useRef, useState } from 'react';
import Brand from '../components/Brand.jsx';
import StatusBadge from '../components/StatusBadge.jsx';
import { company, showcaseModules } from '../mock-data/data.js';
import CommandCenterDemo from './CommandCenterDemo.jsx';
import InsightsDemo from './InsightsDemo.jsx';
import IntegrationsDemo from './IntegrationsDemo.jsx';
import InventoryDemo from './InventoryDemo.jsx';
import OrdersDemo from './OrdersDemo.jsx';
import PickingDemo from './PickingDemo.jsx';
import ReceivingDemo from './ReceivingDemo.jsx';
import ReportsDemo from './ReportsDemo.jsx';
import RoutesDemo from './RoutesDemo.jsx';
import WarehouseDemo from './WarehouseDemo.jsx';

const iconMap = { command: Command, inventory: Boxes, orders: ShoppingCart, picking: PackageCheck, receiving: PackageOpen, warehouse: Warehouse, reports: FileBarChart, insights: BarChart3, routes: Map, integrations: HeartPulse };
const componentMap = { command: CommandCenterDemo, inventory: InventoryDemo, orders: OrdersDemo, picking: PickingDemo, receiving: ReceivingDemo, warehouse: WarehouseDemo, reports: ReportsDemo, insights: InsightsDemo, routes: RoutesDemo, integrations: IntegrationsDemo };

export default function InteractiveOSWindow({ activeModule, onModuleChange }) {
  const [query, setQuery] = useState('');
  const [announcement, setAnnouncement] = useState('Command center loaded.');
  const tabRefs = useRef([]);
  const ActiveDemo = componentMap[activeModule] || CommandCenterDemo;

  function activate(id) {
    onModuleChange(id);
    setAnnouncement(`${showcaseModules.find((module) => module.id === id)?.label} demo loaded.`);
  }

  function submitSearch(event) {
    event.preventDefault();
    const normalized = query.trim().toLowerCase();
    const match = showcaseModules.find((module) => module.id.includes(normalized) || module.label.toLowerCase().includes(normalized));
    if (match) { activate(match.id); setQuery(''); }
    else setAnnouncement(`No demo module matches “${query}”. Try inventory, orders, reports, or routes.`);
  }

  function handleTabKey(event, index) {
    let next = index;
    if (['ArrowDown', 'ArrowRight'].includes(event.key)) next = (index + 1) % showcaseModules.length;
    else if (['ArrowUp', 'ArrowLeft'].includes(event.key)) next = (index - 1 + showcaseModules.length) % showcaseModules.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = showcaseModules.length - 1;
    else return;
    event.preventDefault();
    activate(showcaseModules[next].id);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="os-window glass-panel" id="product-demo">
      <div className="os-window__topbar">
        <div className="os-workspace"><Brand compact /><i aria-hidden="true" /><span><strong>{company.name}</strong><small>{company.subtitle}</small></span></div>
        <form className="os-search" role="search" onSubmit={submitSearch}><Search size={15} /><label className="sr-only" htmlFor="os-search-input">Search demo modules</label><input id="os-search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search a module" /><kbd>Enter</kbd></form>
        <div className="os-health"><button type="button" aria-label="Open system health" onClick={() => activate('integrations')}><i aria-hidden="true" />Healthy</button><button type="button" aria-label="Open attention center" onClick={() => activate('command')}><Bell size={16} /><b>4</b></button></div>
      </div>
      <div className="os-window__layout">
        <nav className="demo-sidebar" role="tablist" aria-label="The-OS product modules" aria-orientation="vertical">
          <span className="demo-sidebar__label">Workspace</span>
          {showcaseModules.map((module, index) => {
            const Icon = iconMap[module.id];
            return <button type="button" role="tab" aria-label={module.label} aria-selected={activeModule === module.id} aria-controls="active-demo-panel" tabIndex={activeModule === module.id ? 0 : -1} className={activeModule === module.id ? 'active' : ''} key={module.id} onClick={() => activate(module.id)} onKeyDown={(event) => handleTabKey(event, index)} ref={(node) => { tabRefs.current[index] = node; }}><Icon size={17} aria-hidden="true" /><span>{module.label}</span>{module.id === 'orders' && <b>186</b>}</button>;
          })}
          <div className="demo-sidebar__foot"><StatusBadge tone="success">Local demo</StatusBadge><small>Synthetic data only</small></div>
        </nav>
        <div className="demo-surface" id="active-demo-panel" role="tabpanel" aria-label={`${showcaseModules.find((module) => module.id === activeModule)?.label} demonstration`} tabIndex={0} key={activeModule}><ActiveDemo /></div>
      </div>
      <div className="sr-only" role="status" aria-live="polite">{announcement}</div>
    </div>
  );
}
