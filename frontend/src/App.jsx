import { useEffect, useMemo, useState } from 'react';
import {
  ArrowLeft,
  BarChart3,
  Bell,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Copy,
  Download,
  Edit3,
  Filter,
  LayoutDashboard,
  Link2,
  MapPin,
  Menu,
  MoreVertical,
  PackagePlus,
  PackageSearch,
  Plus,
  RefreshCw,
  Route,
  Save,
  Search,
  Settings,
  ShoppingCart,
  SlidersHorizontal,
  TriangleAlert,
  Truck,
  Upload,
  UserCircle,
  Warehouse,
} from 'lucide-react';

const CANONICAL_ITEM_COLUMNS = [
  'Client',
  'SKU',
  'Description',
  'Category',
  'Unit of Measurement',
  'Warehouse',
  'Inventory Location',
  'Default Location',
  'In Stock',
  'Allocated',
  'Sellable',
  'Under Par',
  'On Order',
  'Barcode',
  'Manufacturer',
  'Manufacturer Website',
  'Recommended Retail Price',
  'Sales Price',
  'Unit Cost',
  'Weight',
  'Default Econ Order',
  'Default Lead Time Days',
  'Par Level',
  'Assembly',
  'Serializable',
  'Track Lot',
  'Perishable',
  'Re-Order',
  'Storage Length',
  'Storage Width',
  'Storage Height',
  'Storage Volume',
  'Brand',
];

const SEARCH_FIELDS = ['SKU', 'Barcode', 'Description', 'Category', 'Brand', 'Manufacturer', 'Warehouse', 'Inventory Location'];
const BOOLEAN_FIELDS = new Set(['Under Par', 'Assembly', 'Serializable', 'Track Lot', 'Perishable', 'Re-Order']);
const CURRENCY_FIELDS = new Set(['Recommended Retail Price', 'Sales Price', 'Unit Cost']);
const NUMERIC_FIELDS = new Set([
  'In Stock',
  'Allocated',
  'Sellable',
  'On Order',
  'Weight',
  'Default Econ Order',
  'Default Lead Time Days',
  'Par Level',
  'Storage Length',
  'Storage Width',
  'Storage Height',
  'Storage Volume',
]);
const CALCULATED_FIELDS = new Set(['Sellable', 'Under Par', 'Storage Volume']);
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'items', label: 'Items', icon: PackageSearch },
  { id: 'inventory', label: 'Inventory', icon: Boxes },
  { id: 'locations', label: 'Locations', icon: MapPin },
  { id: 'receiving', label: 'Receiving', icon: Truck },
  { id: 'orders', label: 'Orders', icon: ShoppingCart },
  { id: 'cycle-count', label: 'Cycle Count', icon: ClipboardCheck },
  { id: 'reports', label: 'Reports', icon: BarChart3 },
  { id: 'routes', label: 'Routes', icon: Route },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const pageMeta = {
  dashboard: {
    title: 'Dashboard',
    kicker: 'Operational snapshot',
    tabs: ['Today', 'Work Queues', 'Exceptions'],
  },
  items: {
    title: 'Items',
    kicker: 'Zenventory-compatible item master',
    tabs: [
      { label: 'New Item', href: '#/items/new' },
      { label: 'All Items', href: '#items' },
      { label: 'Categories', href: '#/items/categories' },
      { label: 'Commodities', href: '#/items/commodities' },
    ],
  },
  inventory: {
    title: 'Inventory',
    kicker: 'Main Warehouse Inventory',
    tabs: ['List Inventory', 'All Inventory', 'Location View', 'Low Stock', 'Expiring Stock', 'Par Level'],
  },
  locations: {
    title: 'Locations',
    kicker: 'Warehouse and bin setup',
    tabs: ['Warehouses', 'Inventory Locations', 'Location Stock'],
  },
  receiving: {
    title: 'Receiving',
    kicker: 'Direct receiving without PO',
    tabs: ['Create Receipt', 'Select Items', 'Accept Delivery'],
  },
  orders: {
    title: 'Orders',
    kicker: 'Order workflow',
    tabs: ['Open Orders', 'Allocate Orders', 'Pick Orders'],
  },
  'cycle-count': {
    title: 'Cycle Count',
    kicker: 'Scan, count, and reconcile',
    tabs: ['Count Entry', 'Variances', 'History'],
  },
  reports: {
    title: 'Reports',
    kicker: 'Export-ready operational views',
    tabs: ['Inventory', 'Receiving', 'Orders', 'SKU / Barcode'],
  },
  routes: {
    title: 'Routes',
    kicker: 'Route planning',
    tabs: ['Route Date', 'Stops', 'Optimization'],
  },
  settings: {
    title: 'Settings',
    kicker: 'Internal administration',
    tabs: ['Company', 'Users', 'Warehouses', 'System'],
  },
};

const detailTabs = ['Basic', 'Units', 'Warehouse', 'Variants', 'Integration Mappings', 'Timeline'];

const genericRows = [
  ['Work queue', 'Awaiting setup', 'Planning', 'Main Warehouse'],
  ['Exceptions', 'Needs review', 'Operations', 'Main Warehouse'],
  ['Exports', 'Ready later', 'Reporting', 'Main Warehouse'],
];

const dashboardCards = [
  ['Orders', '0', 'Open order queue', ShoppingCart],
  ['Items', '0', 'Item master records', PackageSearch],
  ['Low Stock', '0', 'Needs review', TriangleAlert],
  ['Received Today', '0', 'Receipt sessions', PackagePlus],
];

const widgetRows = [
  ['Receiving', 'No sessions pending', 'Main Warehouse'],
  ['Cycle Count', 'No counts assigned', 'Operations'],
  ['Routes', 'No routes scheduled', 'Dispatch'],
];

const mockItems = [
  normalizeItem({
    id: 1,
    imageUrl: '',
    active: true,
    nonInventory: false,
    wooProductId: '',
    wooVariationId: '',
    Client: 'Pongo',
    SKU: '000437',
    Description: 'Utility Classic Collar Black, Small',
    Category: 'Dog Harness, Lead & Collar',
    'Unit of Measurement': 'Each',
    Warehouse: 'Main Warehouse',
    'Inventory Location': 'Aisle 01 / Collar Wall',
    'Default Location': 'Aisle 01 / Collar Wall',
    'In Stock': 24,
    Allocated: 3,
    'On Order': 0,
    Barcode: '649510004377',
    Manufacturer: 'RC Pets',
    'Manufacturer Website': 'https://example.invalid/rc-pets',
    'Recommended Retail Price': 11.99,
    'Sales Price': 9.49,
    'Unit Cost': 4.75,
    Weight: 0.18,
    'Default Econ Order': 12,
    'Default Lead Time Days': 7,
    'Par Level': 8,
    Assembly: false,
    Serializable: false,
    'Track Lot': false,
    Perishable: false,
    'Re-Order': true,
    'Storage Length': 8,
    'Storage Width': 2,
    'Storage Height': 1,
    Brand: 'Utility',
  }),
  normalizeItem({
    id: 2,
    imageUrl: '',
    active: true,
    nonInventory: false,
    wooProductId: '',
    wooVariationId: '',
    Client: 'Pongo',
    SKU: '00101',
    Description: 'Weruva Outback Grill Canned Cat Food - 3oz',
    Category: 'Cats',
    'Unit of Measurement': 'Each',
    Warehouse: 'Main Warehouse',
    'Inventory Location': 'Receiving',
    'Default Location': 'Cat Food Rack 03',
    'In Stock': 7,
    Allocated: 2,
    'On Order': 0,
    Barcode: '878408001017',
    Manufacturer: 'Weruva',
    'Manufacturer Website': 'https://example.invalid/weruva',
    'Recommended Retail Price': 2.35,
    'Sales Price': 2.35,
    'Unit Cost': 0,
    Weight: 0.2,
    'Default Econ Order': 24,
    'Default Lead Time Days': 5,
    'Par Level': 12,
    Assembly: false,
    Serializable: false,
    'Track Lot': true,
    Perishable: true,
    'Re-Order': true,
    'Storage Length': 3,
    'Storage Width': 3,
    'Storage Height': 1.5,
    Brand: 'Weruva',
  }),
  normalizeItem({
    id: 3,
    imageUrl: '',
    active: true,
    nonInventory: false,
    wooProductId: '',
    wooVariationId: '',
    Client: 'Pongo',
    SKU: '00109',
    Description: "World's Best Multiple Cat Scented Clumping Litter - 7Lb",
    Category: 'Cat Litter & Litter Supplies',
    'Unit of Measurement': 'Bag',
    Warehouse: 'Main Warehouse',
    'Inventory Location': 'Rack 11 Level 1',
    'Default Location': 'Rack 11 Level 1',
    'In Stock': 1,
    Allocated: 0,
    'On Order': 0,
    Barcode: '322591001090',
    Manufacturer: "World's Best Cat Litter",
    'Manufacturer Website': 'https://example.invalid/worlds-best',
    'Recommended Retail Price': 18.99,
    'Sales Price': 18.99,
    'Unit Cost': 14,
    Weight: 7,
    'Default Econ Order': 6,
    'Default Lead Time Days': 10,
    'Par Level': 4,
    Assembly: false,
    Serializable: false,
    'Track Lot': false,
    Perishable: false,
    'Re-Order': true,
    'Storage Length': 14,
    'Storage Width': 9,
    'Storage Height': 4,
    Brand: "World's Best",
  }),
  normalizeItem({
    id: 4,
    imageUrl: '',
    active: true,
    nonInventory: false,
    wooProductId: '',
    wooVariationId: '',
    Client: 'Pongo',
    SKU: '00160',
    Description: "Bullymake Toss N'Treat Dog Toy - Popcorn",
    Category: 'Dog Toys',
    'Unit of Measurement': 'Each',
    Warehouse: 'Main Warehouse',
    'Inventory Location': 'Receiving',
    'Default Location': 'Toy Wall 02',
    'In Stock': 1,
    Allocated: 0,
    'On Order': 0,
    Barcode: '669125001608',
    Manufacturer: 'Bullymake',
    'Manufacturer Website': 'https://example.invalid/bullymake',
    'Recommended Retail Price': 24.99,
    'Sales Price': 24.99,
    'Unit Cost': 0,
    Weight: 0.45,
    'Default Econ Order': 8,
    'Default Lead Time Days': 14,
    'Par Level': 2,
    Assembly: false,
    Serializable: false,
    'Track Lot': false,
    Perishable: false,
    'Re-Order': true,
    'Storage Length': 5,
    'Storage Width': 5,
    'Storage Height': 5,
    Brand: 'Bullymake',
  }),
  normalizeItem({
    id: 5,
    imageUrl: '',
    active: false,
    nonInventory: true,
    wooProductId: '',
    wooVariationId: '',
    Client: 'Pongo',
    SKU: 'SERV-GROOM',
    Description: 'Grooming service placeholder',
    Category: 'Services',
    'Unit of Measurement': 'Service',
    Warehouse: 'Main Warehouse',
    'Inventory Location': 'Front Desk',
    'Default Location': 'Front Desk',
    'In Stock': 0,
    Allocated: 0,
    'On Order': 0,
    Barcode: 'SERVGROOM',
    Manufacturer: 'Pongo Pet Supplies',
    'Manufacturer Website': '',
    'Recommended Retail Price': 0,
    'Sales Price': 0,
    'Unit Cost': 0,
    Weight: 0,
    'Default Econ Order': 0,
    'Default Lead Time Days': 0,
    'Par Level': 0,
    Assembly: false,
    Serializable: false,
    'Track Lot': false,
    Perishable: false,
    'Re-Order': false,
    'Storage Length': 0,
    'Storage Width': 0,
    'Storage Height': 0,
    Brand: 'Pongo',
  }),
];

const emptyItem = normalizeItem({
  id: null,
  imageUrl: '',
  active: true,
  nonInventory: false,
  wooProductId: '',
  wooVariationId: '',
  Client: 'Pongo',
  SKU: '',
  Description: '',
  Category: '',
  'Unit of Measurement': 'Each',
  Warehouse: 'Main Warehouse',
  'Inventory Location': '',
  'Default Location': '',
  'In Stock': 0,
  Allocated: 0,
  'On Order': 0,
  Barcode: '',
  Manufacturer: '',
  'Manufacturer Website': '',
  'Recommended Retail Price': 0,
  'Sales Price': 0,
  'Unit Cost': 0,
  Weight: 0,
  'Default Econ Order': 0,
  'Default Lead Time Days': 0,
  'Par Level': 0,
  Assembly: false,
  Serializable: false,
  'Track Lot': false,
  Perishable: false,
  'Re-Order': false,
  'Storage Length': 0,
  'Storage Width': 0,
  'Storage Height': 0,
  Brand: '',
});

function parseHashRoute() {
  let hash = window.location.hash.replace(/^#/, '');
  if (!hash) {
    return { pageId: 'dashboard' };
  }
  if (hash.startsWith('/')) {
    hash = hash.slice(1);
  }
  if (hash === 'items/categories') {
    return { pageId: 'items', itemView: 'categories' };
  }
  if (hash === 'items/commodities') {
    return { pageId: 'items', itemView: 'commodities' };
  }
  if (hash === 'items/new') {
    return { pageId: 'items', itemView: 'new' };
  }
  if (hash.startsWith('items/')) {
    return { pageId: 'items', itemView: 'detail', itemId: hash.split('/')[1] };
  }
  return navItems.some((item) => item.id === hash) ? { pageId: hash } : { pageId: 'dashboard' };
}

export default function App() {
  const [route, setRoute] = useState(parseHashRoute);
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState('');

  useEffect(() => {
    const handleHashChange = () => setRoute(parseHashRoute());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (route.pageId === 'items') {
      loadItems();
    }
  }, [route.pageId]);

  const activeMeta = getHeaderMeta(route, items);

  function navigate(hash) {
    window.location.hash = hash;
    setRoute(parseHashRoute());
  }

  async function loadItems(filters = {}) {
    setItemsLoading(true);
    setItemsError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/items${filtersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Items API returned ${response.status}`);
      }
      const body = await response.json();
      setItems((body.items || []).map(normalizeItem));
    } catch (error) {
      setItemsError('Unable to load items from the backend. Start the FastAPI server and try again.');
    } finally {
      setItemsLoading(false);
    }
  }

  async function saveItem(nextItem) {
    const normalized = normalizeItem(nextItem);
    const isNew = normalized.id == null;
    const url = isNew ? `${API_BASE_URL}/api/items` : `${API_BASE_URL}/api/items/${normalized.id}`;
    const response = await fetch(url, {
      method: isNew ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(itemToApiPayload(normalized)),
    });
    if (!response.ok) {
      const detail = await safeResponseText(response);
      throw new Error(detail || `Items API returned ${response.status}`);
    }
    const saved = normalizeItem(await response.json());
    setItems((current) => {
      const existing = current.some((item) => item.id === saved.id);
      return existing ? current.map((item) => (item.id === saved.id ? saved : item)) : [...current, saved];
    });
    navigate(`/items/${saved.id}`);
  }

  async function cloneItem(sourceItem) {
    const cloned = normalizeItem({
      ...sourceItem,
      id: null,
      SKU: `${sourceItem.SKU || 'ITEM'}-COPY`,
      wooProductId: '',
      wooVariationId: '',
    });
    await saveItem(cloned);
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={route.pageId} onNavigate={(pageId) => setRoute({ pageId })} />
      <div className="workspace">
        <TopHeader />
        <main className="main-content">
          <PageHeader meta={activeMeta} route={route} />
          <PageBody route={route} items={items} itemsLoading={itemsLoading} itemsError={itemsError} onLoadItems={loadItems} onSaveItem={saveItem} onCloneItem={cloneItem} />
        </main>
      </div>
    </div>
  );
}

function Sidebar({ activePage, onNavigate }) {
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">
          PI
        </div>
        <div>
          <div className="brand-name">Pongo</div>
          <div className="brand-subtitle">Inventory OS</div>
        </div>
      </div>
      <nav className="nav-list">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === activePage;
          return (
            <a className={`nav-link ${isActive ? 'active' : ''}`} href={`#${item.id}`} key={item.id} onClick={() => onNavigate(item.id)}>
              <Icon size={24} strokeWidth={1.8} />
              <span>{item.label}</span>
            </a>
          );
        })}
      </nav>
      <div className="sidebar-footer">
        <Warehouse size={20} />
        <span>Main Warehouse</span>
      </div>
    </aside>
  );
}

function TopHeader() {
  return (
    <header className="top-header">
      <div className="warehouse-control">
        <button className="icon-button header-icon" aria-label="Open navigation">
          <Menu size={23} />
        </button>
        <span>Main Warehouse</span>
        <ChevronDown size={18} />
      </div>
      <div className="header-actions">
        <button className="icon-button header-icon" aria-label="Notifications">
          <Bell size={20} />
        </button>
        <div className="user-chip" aria-label="Signed in user">
          <div className="avatar">
            <UserCircle size={26} />
          </div>
          <span>Kannan</span>
        </div>
        <button className="icon-button header-icon" aria-label="More options">
          <MoreVertical size={22} />
        </button>
      </div>
    </header>
  );
}

function PageHeader({ meta, route }) {
  return (
    <section className="page-heading">
      <div>
        <p>{meta.kicker}</p>
        <h1>{meta.title}</h1>
      </div>
      <div className="page-tabs" role="tablist" aria-label={`${meta.title} sections`}>
        {meta.tabs.map((tab, index) => {
          const tabObject = typeof tab === 'string' ? { label: tab } : tab;
          const isActive = isTabActive(tabObject, index, route);
          const className = isActive ? 'tab active' : 'tab';
          return tabObject.href ? (
            <a className={className} href={tabObject.href} key={tabObject.label} role="tab" aria-selected={isActive}>
              {tabObject.label}
            </a>
          ) : (
            <button className={className} key={tabObject.label} type="button" role="tab" aria-selected={isActive}>
              {tabObject.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}

function PageBody({ route, items, itemsLoading, itemsError, onLoadItems, onSaveItem, onCloneItem }) {
  if (route.pageId === 'items') {
    return <ItemsPage route={route} items={items} itemsLoading={itemsLoading} itemsError={itemsError} onLoadItems={onLoadItems} onSaveItem={onSaveItem} onCloneItem={onCloneItem} />;
  }

  if (route.pageId === 'inventory') {
    return (
      <StandardPage
        icon={Boxes}
        title="Inventory list"
        description="Stock-by-location table layout for Main Warehouse."
        columns={['SKU', 'Category', 'Description', 'UOM', 'In Stock', 'Allocated', 'Sellable', 'Location']}
      />
    );
  }

  if (route.pageId === 'receiving') {
    return <ReceivingPlaceholder />;
  }

  if (route.pageId === 'dashboard') {
    return <DashboardPlaceholder />;
  }

  return <StandardPage icon={pageIcon(route.pageId)} title={pageMeta[route.pageId].title} description="Main Warehouse workspace." columns={['Area', 'Status', 'Type', 'Notes']} />;
}

function ItemsPage({ route, items, itemsLoading, itemsError, onLoadItems, onSaveItem, onCloneItem }) {
  if (route.itemView === 'new') {
    return <ItemDetail item={emptyItem} onSave={onSaveItem} onClone={onCloneItem} isNew />;
  }

  if (route.itemView === 'detail') {
    const item = items.find((candidate) => String(candidate.id) === String(route.itemId));
    if (!item) {
      return (
        <section className="content-panel">
          <div className="empty-state">
            <h2>Item not found</h2>
            <p>{itemsLoading ? 'Loading item from the backend.' : 'The selected item is not available from the backend.'}</p>
            <a className="primary-button" href="#items">
              Return to Items
            </a>
          </div>
        </section>
      );
    }
    return <ItemDetail item={item} onSave={onSaveItem} onClone={onCloneItem} />;
  }

  if (route.itemView === 'categories' || route.itemView === 'commodities') {
    return (
      <StandardPage
        icon={PackageSearch}
        title={route.itemView === 'categories' ? 'Categories' : 'Commodities'}
        description="Placeholder view for later item taxonomy management."
        columns={['Area', 'Status', 'Type', 'Notes']}
      />
    );
  }

  return <ItemsList items={items} loading={itemsLoading} error={itemsError} onLoadItems={onLoadItems} />;
}

function ItemsList({ items, loading, error, onLoadItems }) {
  const [importOpen, setImportOpen] = useState(false);
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    warehouse: '',
    inventoryLocation: '',
    brand: '',
    status: 'active',
    includeNonInventory: true,
  });

  const options = useMemo(
    () => ({
      categories: uniqueOptions(items, 'Category'),
      warehouses: uniqueOptions(items, 'Warehouse'),
      locations: uniqueOptions(items, 'Inventory Location'),
      brands: uniqueOptions(items, 'Brand'),
    }),
    [items],
  );

  useEffect(() => {
    onLoadItems(filters);
  }, [filters]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function clearFilters() {
    setFilters({
      search: '',
      category: '',
      warehouse: '',
      inventoryLocation: '',
      brand: '',
      status: 'active',
      includeNonInventory: true,
    });
  }

  return (
    <section className="content-panel">
      <div className="toolbar items-toolbar">
        <div className="filter-grid items-filter-grid">
          <label className="field">
            <span>Search</span>
            <div className="input-with-icon">
              <input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} placeholder="SKU, barcode, description, brand, location" type="search" />
              <Search size={18} />
            </div>
          </label>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Inventory Location" value={filters.inventoryLocation} options={options.locations} onChange={(value) => updateFilter('inventoryLocation', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <div className="field status-field">
            <span>Show</span>
            <div className="radio-row">
              <label>
                <input checked={filters.status === 'active'} name="item-status" onChange={() => updateFilter('status', 'active')} type="radio" />
                Active
              </label>
              <label>
                <input checked={filters.status === 'inactive'} name="item-status" onChange={() => updateFilter('status', 'inactive')} type="radio" />
                Inactive
              </label>
            </div>
          </div>
          <label className="check-field">
            <input checked={filters.includeNonInventory} onChange={(event) => updateFilter('includeNonInventory', event.target.checked)} type="checkbox" />
            Include Non-Inventory
          </label>
        </div>
        <div className="button-row items-actions">
          <button className="primary-button" onClick={() => onLoadItems(filters)} type="button">
            <Search size={17} />
            Search
          </button>
          <button className="muted-button" onClick={clearFilters} type="button">
            Clear
          </button>
          <button className="action-button" onClick={() => showPlaceholder('Refresh will sync WooCommerce products and variations in a later phase.')} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
          <button className="action-button" onClick={() => showPlaceholder('Remap will link local items to WooCommerce products/variations in a later phase.')} type="button">
            <Link2 size={17} />
            Remap
          </button>
          <button className="action-button" onClick={() => setImportOpen(true)} type="button">
            <Upload size={17} />
            Import
          </button>
          <button className="action-button" onClick={() => exportItemsCsv(filters)} type="button">
            <Download size={17} />
            Export
          </button>
        </div>
      </div>
      <div className="csv-note">CSV import/export uses the canonical Zenventory-compatible inventory column order.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading backend items...</div>}
      <ItemsTable items={items} />
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onImported={() => onLoadItems(filters)} />}
    </section>
  );
}

function ImportModal({ onClose, onImported }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function previewImport() {
    if (!file) {
      setError('Choose a CSV file first.');
      return;
    }
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      const result = await uploadImportFile('/api/items/import/preview', file);
      setPreview(result);
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview CSV import.');
    } finally {
      setLoading(false);
    }
  }

  async function commitImport() {
    if (!file) {
      setError('Choose a CSV file first.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await uploadImportFile('/api/items/import/commit', file);
      setSummary(result);
      await onImported();
    } catch (apiError) {
      setError(apiError.message || 'Unable to import CSV.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Import CSV">
        <div className="modal-header">
          <div>
            <h2>Import Items CSV</h2>
            <p>Zenventory-compatible inventory columns are required.</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close import modal" type="button">
            <MoreVertical size={20} />
          </button>
        </div>
        <div className="import-steps">
          <section className="import-step">
            <h3>1. Upload CSV</h3>
            <p>Import expects the canonical item CSV header. Extra columns are ignored and reported as warnings.</p>
            <input type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <button className="muted-button" onClick={downloadSampleCsv} type="button">
              <Download size={17} />
              Download Sample CSV
            </button>
          </section>
          <section className="import-step">
            <h3>2. Preview</h3>
            <button className="primary-button" disabled={loading || !file} onClick={previewImport} type="button">
              Preview CSV
            </button>
            {preview && <ImportPreview preview={preview} />}
          </section>
          <section className="import-step">
            <h3>3. Commit Import</h3>
            <button className="primary-button" disabled={loading || !file || !preview} onClick={commitImport} type="button">
              Import Valid Rows
            </button>
            {summary && <ImportSummary summary={summary} />}
          </section>
        </div>
        {loading && <div className="loading-strip">Working on CSV import...</div>}
        {error && <div className="api-error">{error}</div>}
      </section>
    </div>
  );
}

function ImportPreview({ preview }) {
  return (
    <div className="import-results">
      <div className="import-metrics">
        <Metric label="Total" value={preview.total_rows} />
        <Metric label="Valid" value={preview.valid_rows} />
        <Metric label="Invalid" value={preview.invalid_rows} />
        <Metric label="Create" value={preview.create_count} />
        <Metric label="Update" value={preview.update_count} />
      </div>
      {preview.warnings?.length > 0 && (
        <div className="warning-list">
          {preview.warnings.slice(0, 8).map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}
      <ImportErrors errors={preview.errors} />
      <div className="preview-table-wrap">
        <table className="preview-table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Action</th>
              <th>SKU</th>
              <th>Barcode</th>
              <th>Description</th>
              <th>Warnings</th>
            </tr>
          </thead>
          <tbody>
            {preview.preview_rows.map((row) => (
              <tr key={row.row_number}>
                <td>{row.row_number}</td>
                <td>{row.action}</td>
                <td>{row.sku}</td>
                <td>{row.barcode}</td>
                <td>{row.row.Description}</td>
                <td>{row.warnings.join(' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ImportSummary({ summary }) {
  return (
    <div className="import-results">
      <div className="import-metrics">
        <Metric label="Created" value={summary.created_count} />
        <Metric label="Updated" value={summary.updated_count} />
        <Metric label="Skipped" value={summary.skipped_count} />
        <Metric label="Failed" value={summary.failed_count} />
      </div>
      <ImportErrors errors={summary.errors} />
      {summary.import_job_id && (
        <a className="action-button failed-download" href={`${API_BASE_URL}/api/import-jobs/${summary.import_job_id}/failed-rows`}>
          <Download size={17} />
          Download Failed Rows
        </a>
      )}
    </div>
  );
}

function ImportErrors({ errors = [] }) {
  if (!errors.length) {
    return null;
  }
  return (
    <div className="import-errors">
      <h4>Errors</h4>
      {errors.slice(0, 12).map((error) => (
        <div className="import-error-row" key={`${error.row_number}-${error.sku}-${error.error_message}`}>
          <span>Row {error.row_number}</span>
          <span>{error.sku || 'No SKU'}</span>
          <span>{error.barcode || 'No Barcode'}</span>
          <strong>{error.error_message}</strong>
        </div>
      ))}
    </div>
  );
}

function Metric({ label, value }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function FilterSelect({ label, value, options, onChange }) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="select-shell">
        <select value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">All {label}</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        <Filter size={18} />
      </div>
    </label>
  );
}

function ItemsTable({ items }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>
          Showing records 1-{items.length} out of {items.length}
        </span>
        <div className="table-pager">
          <span>{items.length} Results</span>
          <button className="pager-button" aria-label="Previous page" type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" type="button">
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      <div className="table-action-band">
        <span>Actions</span>
        <ChevronDown size={18} />
      </div>
      <div className="table-scroll items-table-scroll">
        <table className="items-data-table">
          <thead>
            <tr>
              <th className="sticky-col sticky-action-col">Edit</th>
              <th className="sticky-col sticky-image-col">Image</th>
              {CANONICAL_ITEM_COLUMNS.map((column) => (
                <th key={column}>{column}</th>
              ))}
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td className="sticky-col sticky-action-col">
                  <a className="round-action" href={`#/items/${item.id}`} aria-label={`Edit ${item.SKU}`}>
                    <Edit3 size={17} />
                  </a>
                </td>
                <td className="sticky-col sticky-image-col">
                  <div className="image-cell">{item.imageUrl ? 'Image' : 'Add Image'}</div>
                </td>
                {CANONICAL_ITEM_COLUMNS.map((column) => (
                  <td key={`${item.id}-${column}`} className={column === 'Description' ? 'description-cell' : ''}>
                    {formatCell(item[column], column)}
                  </td>
                ))}
                <td>
                  <StatusBadge active={item.active} />
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={CANONICAL_ITEM_COLUMNS.length + 3}>
                  <div className="empty-table-row">No items match the current filters.</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ItemDetail({ item, onSave, onClone, isNew = false }) {
  const [formItem, setFormItem] = useState(() => normalizeItem(item));
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const calculatedItem = normalizeItem(formItem);

  function updateField(field, value) {
    setFormItem((current) => normalizeItem({ ...current, [field]: value }));
  }

  function updateInternalField(field, value) {
    setFormItem((current) => ({ ...current, [field]: value }));
  }

  async function saveChanges() {
    setSaveError('');
    setSaving(true);
    try {
      await onSave(calculatedItem);
    } catch (error) {
      setSaveError('Unable to save item to the backend. Check that FastAPI is running and SKU is valid.');
    } finally {
      setSaving(false);
    }
  }

  async function cloneChanges() {
    setSaveError('');
    setSaving(true);
    try {
      await onClone(calculatedItem);
    } catch (error) {
      setSaveError('Unable to clone item through the backend. Check that FastAPI is running.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="content-panel">
      <div className="detail-layout">
        <div className="detail-main">
          <FormSection title="Core Identity">
            {renderTextField('Client', calculatedItem, updateField)}
            {renderTextField('SKU', calculatedItem, updateField, { required: true })}
            {renderTextField('Barcode', calculatedItem, updateField)}
            {renderTextField('Description', calculatedItem, updateField, { wide: true })}
            {renderTextField('Category', calculatedItem, updateField)}
            {renderTextField('Brand', calculatedItem, updateField)}
            {renderTextField('Manufacturer', calculatedItem, updateField)}
            {renderTextField('Manufacturer Website', calculatedItem, updateField, { wide: true })}
          </FormSection>
          <FormSection title="Stock and Location">
            {renderTextField('Warehouse', calculatedItem, updateField)}
            {renderTextField('Inventory Location', calculatedItem, updateField)}
            {renderTextField('Default Location', calculatedItem, updateField)}
            {renderNumberField('In Stock', calculatedItem, updateField)}
            {renderNumberField('Allocated', calculatedItem, updateField)}
            {renderNumberField('Sellable', calculatedItem, updateField, { readOnly: true })}
            {renderBooleanField('Under Par', calculatedItem, updateField, { readOnly: true })}
            {renderNumberField('On Order', calculatedItem, updateField)}
            {renderNumberField('Par Level', calculatedItem, updateField)}
            {renderBooleanField('Re-Order', calculatedItem, updateField)}
          </FormSection>
          <FormSection title="Pricing and Cost">
            {renderNumberField('Recommended Retail Price', calculatedItem, updateField)}
            {renderNumberField('Sales Price', calculatedItem, updateField)}
            {renderNumberField('Unit Cost', calculatedItem, updateField)}
            {renderNumberField('Default Econ Order', calculatedItem, updateField)}
            {renderNumberField('Default Lead Time Days', calculatedItem, updateField)}
          </FormSection>
          <FormSection title="Units and Physical Attributes">
            {renderTextField('Unit of Measurement', calculatedItem, updateField)}
            {renderNumberField('Weight', calculatedItem, updateField)}
            {renderNumberField('Storage Length', calculatedItem, updateField)}
            {renderNumberField('Storage Width', calculatedItem, updateField)}
            {renderNumberField('Storage Height', calculatedItem, updateField)}
            {renderNumberField('Storage Volume', calculatedItem, updateField, { readOnly: true })}
          </FormSection>
          <FormSection title="Flags">
            {renderBooleanField('Assembly', calculatedItem, updateField)}
            {renderBooleanField('Serializable', calculatedItem, updateField)}
            {renderBooleanField('Track Lot', calculatedItem, updateField)}
            {renderBooleanField('Perishable', calculatedItem, updateField)}
            <label className="toggle-card">
              <input checked={Boolean(formItem.active)} onChange={(event) => updateInternalField('active', event.target.checked)} type="checkbox" />
              <span>Active</span>
            </label>
            <label className="toggle-card">
              <input checked={Boolean(formItem.nonInventory)} onChange={(event) => updateInternalField('nonInventory', event.target.checked)} type="checkbox" />
              <span>Non-Inventory</span>
            </label>
          </FormSection>
        </div>
        <aside className="detail-side">
          <div className="image-dropzone">Add Image</div>
          <div className="mapping-card">
            <h2>Integration Mappings</h2>
            <p>WooCommerce fields are local placeholders only in this phase.</p>
            <label className="field">
              <span>Woo Product ID</span>
              <input value={formItem.wooProductId || ''} onChange={(event) => updateInternalField('wooProductId', event.target.value)} />
            </label>
            <label className="field">
              <span>Woo Variation ID</span>
              <input value={formItem.wooVariationId || ''} onChange={(event) => updateInternalField('wooVariationId', event.target.value)} />
            </label>
          </div>
        </aside>
      </div>
      <div className="detail-actions">
        {saveError && <div className="api-error detail-error">{saveError}</div>}
        <button className="primary-button" disabled={saving} onClick={saveChanges} type="button">
          <Save size={17} />
          {saving ? 'Saving' : 'Save Changes'}
        </button>
        <button className="muted-button" disabled={isNew || saving} onClick={cloneChanges} type="button">
          <Copy size={17} />
          Clone
        </button>
        <a className="action-button" href="#items">
          <ArrowLeft size={17} />
          Return to Items
        </a>
      </div>
    </section>
  );
}

function FormSection({ title, children }) {
  return (
    <section className="form-section">
      <h2>{title}</h2>
      <div className="form-grid">{children}</div>
    </section>
  );
}

function renderTextField(field, item, updateField, options = {}) {
  return (
    <label className={options.wide ? 'field form-field wide-field' : 'field form-field'} key={field}>
      <span>{field}</span>
      <input required={options.required} value={item[field] ?? ''} onChange={(event) => updateField(field, event.target.value)} />
    </label>
  );
}

function renderNumberField(field, item, updateField, options = {}) {
  return (
    <label className="field form-field" key={field}>
      <span>{field}</span>
      <input readOnly={options.readOnly} value={item[field] ?? ''} onChange={(event) => updateField(field, event.target.value)} inputMode="decimal" />
    </label>
  );
}

function renderBooleanField(field, item, updateField, options = {}) {
  return (
    <label className={options.readOnly ? 'toggle-card read-only-toggle' : 'toggle-card'} key={field}>
      <input checked={Boolean(item[field])} disabled={options.readOnly} onChange={(event) => updateField(field, event.target.checked)} type="checkbox" />
      <span>{field}</span>
    </label>
  );
}

function DashboardPlaceholder() {
  return (
    <section className="dashboard-grid">
      {dashboardCards.map(([label, value, caption, Icon]) => (
        <article className="summary-card" key={label}>
          <div className="summary-icon">
            <Icon size={24} />
          </div>
          <div>
            <span>{label}</span>
            <strong>{value}</strong>
            <small>{caption}</small>
          </div>
        </article>
      ))}
      <div className="dashboard-chart">
        <div className="section-heading">
          <div>
            <h2>Warehouse Activity</h2>
            <p>Activity by week</p>
          </div>
          <button className="muted-button" type="button">
            <SlidersHorizontal size={17} />
            View
          </button>
        </div>
        <div className="chart-placeholder" aria-label="Placeholder warehouse activity chart">
          <div className="chart-axis">
            <span></span>
            <span></span>
            <span></span>
            <span></span>
          </div>
          <div className="chart-bars">
            <i style={{ '--bar-height': '42%' }}></i>
            <i style={{ '--bar-height': '68%' }}></i>
            <i style={{ '--bar-height': '54%' }}></i>
            <i style={{ '--bar-height': '78%' }}></i>
            <i style={{ '--bar-height': '47%' }}></i>
            <i style={{ '--bar-height': '62%' }}></i>
          </div>
        </div>
      </div>
      <aside className="dashboard-widgets">
        <div className="section-heading compact-heading">
          <div>
            <h2>Widgets</h2>
            <p>Operations</p>
          </div>
        </div>
        <div className="widget-list">
          {widgetRows.map(([title, status, owner]) => (
            <article className="widget-row" key={title}>
              <div>
                <strong>{title}</strong>
                <span>{status}</span>
              </div>
              <em>{owner}</em>
            </article>
          ))}
        </div>
      </aside>
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Work queues</h2>
            <p>Main Warehouse activity overview.</p>
          </div>
          <button className="muted-button" type="button">
            <SlidersHorizontal size={17} />
            View
          </button>
        </div>
        <TableShell caption="Main Warehouse queues" columns={['Queue', 'Status', 'Owner', 'Updated']}>
          {genericRows.map((row) => (
            <tr key={row[0]}>
              {row.map((cell) => (
                <td key={cell}>{cell}</td>
              ))}
            </tr>
          ))}
        </TableShell>
      </div>
    </section>
  );
}

function ReceivingPlaceholder() {
  return (
    <section className="content-panel">
      <div className="receiving-strip">
        <label className="field scan-field">
          <span>Add New Item</span>
          <div className="input-with-icon">
            <input placeholder="Scan SKU or barcode" />
            <Search size={18} />
          </div>
        </label>
        <button className="add-button" aria-label="Add receiving row" type="button">
          <Plus size={22} />
        </button>
        <label className="toggle-label">
          <span>Enable One to One Scanning</span>
          <input type="checkbox" />
        </label>
      </div>
      <TableShell
        caption="Receiving rows"
        columns={['Image', 'SKU', 'PKG #', 'Item #', 'Unit Cost', 'UOM', 'Expires', 'Lot No', 'Delivered', 'Destination', 'Total']}
      >
        <tr>
          <td>
            <div className="image-cell">No Image</div>
          </td>
          <td className="mono">100107</td>
          <td></td>
          <td></td>
          <td>48.25</td>
          <td>Each</td>
          <td></td>
          <td></td>
          <td>1</td>
          <td>Receiving</td>
          <td>48.25</td>
        </tr>
      </TableShell>
      <div className="footer-actions">
        <span>Delivered: 1</span>
        <button className="primary-button" type="button">
          Next
        </button>
        <span>Total: 48.25</span>
      </div>
    </section>
  );
}

function StandardPage({ icon: Icon, title, description, columns }) {
  const rows = columns.length === 4 ? genericRows : mockItems.map((row) => [row.SKU, row.Category, row.Description, row['Unit of Measurement'], row['In Stock'], row.Allocated, row.Sellable, row['Inventory Location']]);

  return (
    <section className="content-panel">
      <div className="panel-title">
        <div className="title-with-icon">
          <span className="large-icon">
            <Icon size={26} />
          </span>
          <div>
            <h2>{title}</h2>
            <p>{description}</p>
          </div>
        </div>
        <div className="button-row compact">
          <button className="muted-button" type="button">
            <Filter size={17} />
            Filter
          </button>
          <button className="action-button" type="button">
            <Download size={17} />
            Export
          </button>
        </div>
      </div>
      <TableShell caption="Records" columns={columns}>
        {rows.map((row) => (
          <tr key={row.join('-')}>
            {row.map((cell) => (
              <td key={cell}>{cell}</td>
            ))}
          </tr>
        ))}
      </TableShell>
    </section>
  );
}

function TableShell({ caption, columns, children }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>{caption}</span>
        <div className="table-pager">
          <span>20 Results</span>
          <button className="pager-button" aria-label="Previous page" type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" type="button">
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      <div className="table-action-band">
        <span>Actions</span>
        <ChevronDown size={18} />
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

function getHeaderMeta(route, items) {
  if (route.pageId !== 'items') {
    return pageMeta[route.pageId];
  }
  if (route.itemView === 'new') {
    return { title: 'New Item', kicker: 'CSV field entry', tabs: detailTabs };
  }
  if (route.itemView === 'detail') {
    const item = items.find((candidate) => String(candidate.id) === String(route.itemId));
    return { title: item ? `Edit ${item.SKU}` : 'Edit Item', kicker: 'CSV field entry', tabs: detailTabs };
  }
  return pageMeta.items;
}

function isTabActive(tab, index, route) {
  if (route.pageId === 'items' && tab.href) {
    if (tab.href === '#items') {
      return !route.itemView;
    }
    if (tab.href === '#/items/new') {
      return route.itemView === 'new';
    }
    if (tab.href === '#/items/categories') {
      return route.itemView === 'categories';
    }
    if (tab.href === '#/items/commodities') {
      return route.itemView === 'commodities';
    }
  }
  return index === 0;
}

function uniqueOptions(items, field) {
  return [...new Set(items.map((item) => item[field]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function filterItems(items, filters) {
  const query = filters.search.trim().toLowerCase();
  return items.filter((item) => {
    const matchesSearch = !query || SEARCH_FIELDS.some((field) => String(item[field] ?? '').toLowerCase().includes(query));
    const matchesCategory = !filters.category || item.Category === filters.category;
    const matchesWarehouse = !filters.warehouse || item.Warehouse === filters.warehouse;
    const matchesLocation = !filters.inventoryLocation || item['Inventory Location'] === filters.inventoryLocation;
    const matchesBrand = !filters.brand || item.Brand === filters.brand;
    const matchesStatus = filters.status === 'inactive' ? !item.active : item.active;
    const matchesInventoryType = filters.includeNonInventory || !item.nonInventory;
    return matchesSearch && matchesCategory && matchesWarehouse && matchesLocation && matchesBrand && matchesStatus && matchesInventoryType;
  });
}

function normalizeItem(item) {
  const normalized = {
    imageUrl: '',
    active: true,
    nonInventory: false,
    wooProductId: '',
    wooVariationId: '',
    ...item,
  };
  CANONICAL_ITEM_COLUMNS.forEach((column) => {
    if (!(column in normalized)) {
      normalized[column] = BOOLEAN_FIELDS.has(column) ? false : '';
    }
  });
  normalized['In Stock'] = toNumber(normalized['In Stock']);
  normalized.Allocated = toNumber(normalized.Allocated);
  normalized['On Order'] = toNumber(normalized['On Order']);
  normalized['Par Level'] = toNumber(normalized['Par Level']);
  normalized['Storage Length'] = toNumber(normalized['Storage Length']);
  normalized['Storage Width'] = toNumber(normalized['Storage Width']);
  normalized['Storage Height'] = toNumber(normalized['Storage Height']);
  normalized.Sellable = calculateSellable(normalized['In Stock'], normalized.Allocated);
  normalized['Under Par'] = calculateUnderPar(normalized['In Stock'], normalized['Par Level']);
  normalized['Storage Volume'] = calculateStorageVolume(normalized['Storage Length'], normalized['Storage Width'], normalized['Storage Height']);
  ['Assembly', 'Serializable', 'Track Lot', 'Perishable', 'Re-Order'].forEach((field) => {
    normalized[field] = toBoolean(normalized[field]);
  });
  return normalized;
}

function toNumber(value) {
  if (value === null || value === undefined || value === '') {
    return 0;
  }
  const parsed = Number(String(value).replace(/,/g, ''));
  return Number.isFinite(parsed) ? parsed : 0;
}

function toBoolean(value) {
  if (typeof value === 'boolean') {
    return value;
  }
  return ['true', 'yes', 'y', '1'].includes(String(value).trim().toLowerCase());
}

function calculateSellable(inStock, allocated) {
  return roundNumber(toNumber(inStock) - toNumber(allocated));
}

function calculateUnderPar(inStock, parLevel) {
  return toNumber(inStock) <= toNumber(parLevel);
}

function calculateStorageVolume(length, width, height) {
  return roundNumber(toNumber(length) * toNumber(width) * toNumber(height));
}

function roundNumber(value) {
  return Math.round(value * 1000) / 1000;
}

function formatCell(value, column) {
  if (BOOLEAN_FIELDS.has(column)) {
    return <BooleanBadge value={Boolean(value)} />;
  }
  if (CURRENCY_FIELDS.has(column)) {
    return formatCurrency(value);
  }
  if (NUMERIC_FIELDS.has(column)) {
    return formatNumber(value);
  }
  if (column === 'Manufacturer Website' && value) {
    return (
      <a href={value} onClick={(event) => event.preventDefault()} className="table-link">
        {value}
      </a>
    );
  }
  return value || '';
}

function formatCurrency(value) {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(toNumber(value));
}

function formatNumber(value) {
  const number = toNumber(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(3).replace(/0+$/, '').replace(/\.$/, '');
}

function BooleanBadge({ value }) {
  return <span className={value ? 'boolean-badge yes' : 'boolean-badge no'}>{value ? 'Yes' : 'No'}</span>;
}

function StatusBadge({ active }) {
  return <span className={active ? 'status-pill' : 'status-pill inactive'}>{active ? 'Active' : 'Inactive'}</span>;
}

async function exportItemsCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/items/export${filtersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder('Unable to export CSV from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-inventory-items-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function uploadImportFile(path, file) {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await safeResponseText(response);
    throw new Error(detail || `Import API returned ${response.status}`);
  }
  return response.json();
}

function downloadSampleCsv() {
  const sampleRows = [
    {
      Client: 'Pongo',
      SKU: 'SAMPLE-DOG-001',
      Description: 'Sample Dog Treats',
      Category: 'Dog Treats',
      'Unit of Measurement': 'Bag',
      Warehouse: 'Main Warehouse',
      'Inventory Location': 'Sample Rack A',
      'Default Location': 'Sample Rack A',
      'In Stock': 12,
      Allocated: 2,
      Sellable: 10,
      'Under Par': 'No',
      'On Order': 0,
      Barcode: 'SAMPLE001',
      Manufacturer: 'Sample Maker',
      'Manufacturer Website': '',
      'Recommended Retail Price': 14.99,
      'Sales Price': 12.99,
      'Unit Cost': 6.5,
      Weight: 1.2,
      'Default Econ Order': 6,
      'Default Lead Time Days': 7,
      'Par Level': 5,
      Assembly: 'No',
      Serializable: 'No',
      'Track Lot': 'Yes',
      Perishable: 'No',
      'Re-Order': 'Yes',
      'Storage Length': 8,
      'Storage Width': 5,
      'Storage Height': 3,
      'Storage Volume': 120,
      Brand: 'Sample Brand',
    },
  ];
  const header = CANONICAL_ITEM_COLUMNS.join(',');
  const rows = sampleRows.map((row) => CANONICAL_ITEM_COLUMNS.map((column) => escapeCsvValue(row[column], column)).join(','));
  const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sample-items-import.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function filtersToQueryString(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.category) params.set('category', filters.category);
  if (filters.warehouse) params.set('warehouse', filters.warehouse);
  if (filters.inventoryLocation) params.set('inventory_location', filters.inventoryLocation);
  if (filters.brand) params.set('brand', filters.brand);
  if (filters.status === 'active') params.set('active', 'true');
  if (filters.status === 'inactive') params.set('active', 'false');
  params.set('include_non_inventory', String(Boolean(filters.includeNonInventory)));
  const query = params.toString();
  return query ? `?${query}` : '';
}

function itemToApiPayload(item) {
  const payload = {};
  CANONICAL_ITEM_COLUMNS.forEach((column) => {
    payload[column] = item[column];
  });
  payload.imageUrl = item.imageUrl || '';
  payload.active = Boolean(item.active);
  payload.nonInventory = Boolean(item.nonInventory);
  payload.wooProductId = item.wooProductId || null;
  payload.wooVariationId = item.wooVariationId || null;
  return payload;
}

async function safeResponseText(response) {
  try {
    return await response.text();
  } catch {
    return '';
  }
}

function escapeCsvValue(value, column) {
  let output = value;
  if (BOOLEAN_FIELDS.has(column)) {
    output = value ? 'Yes' : 'No';
  } else if (NUMERIC_FIELDS.has(column) || CURRENCY_FIELDS.has(column)) {
    output = toNumber(value);
  }
  const stringValue = String(output ?? '');
  return /[",\n\r]/.test(stringValue) ? `"${stringValue.replace(/"/g, '""')}"` : stringValue;
}

function showPlaceholder(message) {
  window.alert(message);
}

function pageIcon(pageId) {
  const icons = {
    locations: MapPin,
    orders: ShoppingCart,
    'cycle-count': ClipboardList,
    reports: BarChart3,
    routes: CalendarDays,
    settings: CheckCircle2,
  };
  return icons[pageId] || PackageSearch;
}
