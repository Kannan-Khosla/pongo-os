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
const CANONICAL_LOCATION_COLUMNS = ['Warehouse', 'Location Code', 'Location Name', 'Description', 'Zone', 'Aisle', 'Rack', 'Shelf', 'Bin', 'Default', 'Active'];
const emptyInventorySummary = {
  groups: [],
  total_items: 0,
  total_in_stock: 0,
  total_allocated: 0,
  total_sellable: 0,
  total_on_order: 0,
  total_inventory_value: 0,
  under_par_count: 0,
};
const emptyReceivedInventorySummary = {
  total_receipts: 0,
  total_lines: 0,
  total_quantity_received: 0,
  total_received_value: 0,
  unique_skus: 0,
  unique_locations: 0,
  date_from: null,
  date_to: null,
  by_warehouse: [],
  by_location: [],
  by_sku: [],
};
const emptyWooStatus = {
  configured: false,
  base_url_present: false,
  consumer_key_present: false,
  consumer_secret_present: false,
  message: 'WooCommerce status has not been checked.',
};

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
    tabs: [
      { label: 'Add Location', href: '#/locations/new' },
      { label: 'All Locations', href: '#locations' },
      { label: 'Location Stock', href: '#/locations/stock' },
    ],
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
    tabs: ['Received Inventory', 'Inventory', 'Orders', 'SKU / Barcode'],
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

const emptyLocation = normalizeLocation({
  id: null,
  warehouse: 'Main Warehouse',
  code: '',
  name: '',
  description: '',
  zone: '',
  aisle: '',
  rack: '',
  shelf: '',
  bin: '',
  isDefault: false,
  isActive: true,
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
  if (hash === 'locations/new') {
    return { pageId: 'locations', locationView: 'new' };
  }
  if (hash === 'locations/stock') {
    return { pageId: 'locations', locationView: 'stock' };
  }
  if (hash.startsWith('locations/')) {
    return { pageId: 'locations', locationView: 'detail', locationId: hash.split('/')[1] };
  }
  return navItems.some((item) => item.id === hash) ? { pageId: hash } : { pageId: 'dashboard' };
}

export default function App() {
  const [route, setRoute] = useState(parseHashRoute);
  const [items, setItems] = useState([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState('');
  const [locations, setLocations] = useState([]);
  const [locationsLoading, setLocationsLoading] = useState(false);
  const [locationsError, setLocationsError] = useState('');
  const [inventorySummary, setInventorySummary] = useState(emptyInventorySummary);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState('');
  const [receipts, setReceipts] = useState([]);
  const [receiptsLoading, setReceiptsLoading] = useState(false);
  const [receiptsError, setReceiptsError] = useState('');
  const [stockMovements, setStockMovements] = useState([]);
  const [stockMovementsLoading, setStockMovementsLoading] = useState(false);
  const [stockMovementsError, setStockMovementsError] = useState('');
  const [receivedInventoryRows, setReceivedInventoryRows] = useState([]);
  const [receivedInventorySummary, setReceivedInventorySummary] = useState(emptyReceivedInventorySummary);
  const [receivedInventoryLoading, setReceivedInventoryLoading] = useState(false);
  const [receivedInventoryError, setReceivedInventoryError] = useState('');
  const [cycleCounts, setCycleCounts] = useState([]);
  const [cycleCountsLoading, setCycleCountsLoading] = useState(false);
  const [cycleCountsError, setCycleCountsError] = useState('');
  const [wooStatus, setWooStatus] = useState(emptyWooStatus);
  const [wooPreview, setWooPreview] = useState(null);
  const [wooCommitSummary, setWooCommitSummary] = useState(null);
  const [wooSyncRuns, setWooSyncRuns] = useState([]);
  const [wooLoading, setWooLoading] = useState(false);
  const [wooError, setWooError] = useState('');

  useEffect(() => {
    const handleHashChange = () => setRoute(parseHashRoute());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (route.pageId === 'items' || route.pageId === 'inventory') {
      loadItems();
    }
    if (route.pageId === 'receiving') {
      loadItems();
      loadLocations({ status: 'active' });
      loadReceipts();
      loadStockMovements({ movement_type: 'receive_direct' });
    }
    if (route.pageId === 'locations') {
      loadLocations();
    }
    if (route.pageId === 'reports') {
      loadReceivedInventoryReport();
    }
    if (route.pageId === 'cycle-count') {
      loadItems();
      loadLocations({ status: 'active' });
      loadCycleCounts();
    }
    if (route.pageId === 'settings') {
      loadWooStatus();
      loadWooSyncRuns();
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

  async function loadLocations(filters = {}) {
    setLocationsLoading(true);
    setLocationsError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/locations${locationsFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Locations API returned ${response.status}`);
      }
      const body = await response.json();
      setLocations((body.locations || []).map(normalizeLocation));
    } catch (error) {
      setLocationsError('Unable to load locations from the backend. Start the FastAPI server and try again.');
    } finally {
      setLocationsLoading(false);
    }
  }

  async function saveLocation(nextLocation) {
    const normalized = normalizeLocation(nextLocation);
    const isNew = normalized.id == null;
    const url = isNew ? `${API_BASE_URL}/api/locations` : `${API_BASE_URL}/api/locations/${normalized.id}`;
    const response = await fetch(url, {
      method: isNew ? 'POST' : 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(locationToApiPayload(normalized)),
    });
    if (!response.ok) {
      const detail = await safeResponseText(response);
      throw new Error(detail || `Locations API returned ${response.status}`);
    }
    const saved = normalizeLocation(await response.json());
    setLocations((current) => {
      const existing = current.some((location) => location.id === saved.id);
      return existing ? current.map((location) => (location.id === saved.id ? saved : location)) : [...current, saved];
    });
    navigate(`/locations/${saved.id}`);
  }

  async function loadInventorySummary(filters = {}) {
    setInventoryLoading(true);
    setInventoryError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/inventory/summary/by-location${inventoryFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Inventory API returned ${response.status}`);
      }
      setInventorySummary(await response.json());
    } catch (error) {
      setInventoryError('Unable to load inventory summary from the backend. Start the FastAPI server and try again.');
    } finally {
      setInventoryLoading(false);
    }
  }

  async function loadReceipts(filters = {}) {
    setReceiptsLoading(true);
    setReceiptsError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/receipts${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Receipts API returned ${response.status}`);
      }
      const body = await response.json();
      setReceipts(body.receipts || []);
    } catch (error) {
      setReceiptsError('Unable to load receipt history from the backend.');
    } finally {
      setReceiptsLoading(false);
    }
  }

  async function loadStockMovements(filters = {}) {
    setStockMovementsLoading(true);
    setStockMovementsError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/stock-movements${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Stock movements API returned ${response.status}`);
      }
      const body = await response.json();
      setStockMovements(body.movements || []);
    } catch (error) {
      setStockMovementsError('Unable to load stock movement history from the backend.');
    } finally {
      setStockMovementsLoading(false);
    }
  }

  async function loadReceivedInventoryReport(filters = {}) {
    setReceivedInventoryLoading(true);
    setReceivedInventoryError('');
    try {
      const queryString = plainFiltersToQueryString(receivedInventoryFiltersToApi(filters));
      const [rowsResponse, summaryResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/reports/received-inventory${queryString}`),
        fetch(`${API_BASE_URL}/api/reports/received-inventory/summary${queryString}`),
      ]);
      if (!rowsResponse.ok || !summaryResponse.ok) {
        throw new Error('Reports API returned an error.');
      }
      setReceivedInventoryRows(await rowsResponse.json());
      setReceivedInventorySummary(await summaryResponse.json());
    } catch (error) {
      setReceivedInventoryError('Unable to load received inventory report from the backend.');
    } finally {
      setReceivedInventoryLoading(false);
    }
  }

  async function loadCycleCounts(filters = {}) {
    setCycleCountsLoading(true);
    setCycleCountsError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/cycle-counts${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Cycle Counts API returned ${response.status}`);
      }
      const body = await response.json();
      setCycleCounts(body.cycle_counts || []);
    } catch (error) {
      setCycleCountsError('Unable to load cycle count history from the backend.');
    } finally {
      setCycleCountsLoading(false);
    }
  }

  async function loadWooStatus(check = false) {
    setWooLoading(true);
    setWooError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/integrations/woocommerce/status${check ? '?check=true' : ''}`);
      if (!response.ok) {
        throw new Error(`WooCommerce status returned ${response.status}`);
      }
      setWooStatus(await response.json());
    } catch (error) {
      setWooError('Unable to load WooCommerce integration status from the backend.');
    } finally {
      setWooLoading(false);
    }
  }

  async function loadWooSyncRuns() {
    setWooError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/integrations/woocommerce/sync-runs`);
      if (!response.ok) {
        throw new Error(`WooCommerce sync runs returned ${response.status}`);
      }
      const body = await response.json();
      setWooSyncRuns(body.sync_runs || []);
    } catch (error) {
      setWooError('Unable to load WooCommerce sync run history.');
    }
  }

  async function previewWooProductSync() {
    setWooLoading(true);
    setWooError('');
    setWooCommitSummary(null);
    try {
      setWooPreview(await postJson('/api/integrations/woocommerce/products/preview', { include_statuses: ['publish'], limit: 500, created_by: 'system' }));
    } catch (error) {
      setWooError(error.message || 'Unable to preview WooCommerce product sync.');
    } finally {
      setWooLoading(false);
    }
  }

  async function commitWooProductSync() {
    const confirmed = window.confirm('This only creates or updates local Pongo OS items. It never writes WooCommerce products, orders, or stock.');
    if (!confirmed) {
      return;
    }
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/products/commit', { include_statuses: ['publish'], limit: 500, created_by: 'system' });
      setWooCommitSummary(result);
      await loadWooSyncRuns();
      await loadItems();
    } catch (error) {
      setWooError(error.message || 'Unable to commit WooCommerce product sync.');
    } finally {
      setWooLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={route.pageId} onNavigate={(pageId) => setRoute({ pageId })} />
      <div className="workspace">
        <TopHeader />
        <main className="main-content">
          <PageHeader meta={activeMeta} route={route} />
          <PageBody
            route={route}
            items={items}
            itemsLoading={itemsLoading}
            itemsError={itemsError}
            onLoadItems={loadItems}
            onSaveItem={saveItem}
            onCloneItem={cloneItem}
            locations={locations}
            locationsLoading={locationsLoading}
            locationsError={locationsError}
            onLoadLocations={loadLocations}
            onSaveLocation={saveLocation}
            inventorySummary={inventorySummary}
            inventoryLoading={inventoryLoading}
            inventoryError={inventoryError}
            onLoadInventorySummary={loadInventorySummary}
            receipts={receipts}
            receiptsLoading={receiptsLoading}
            receiptsError={receiptsError}
            onLoadReceipts={loadReceipts}
            stockMovements={stockMovements}
            stockMovementsLoading={stockMovementsLoading}
            stockMovementsError={stockMovementsError}
            onLoadStockMovements={loadStockMovements}
            receivedInventoryRows={receivedInventoryRows}
            receivedInventorySummary={receivedInventorySummary}
            receivedInventoryLoading={receivedInventoryLoading}
            receivedInventoryError={receivedInventoryError}
            onLoadReceivedInventoryReport={loadReceivedInventoryReport}
            cycleCounts={cycleCounts}
            cycleCountsLoading={cycleCountsLoading}
            cycleCountsError={cycleCountsError}
            onLoadCycleCounts={loadCycleCounts}
            wooStatus={wooStatus}
            wooPreview={wooPreview}
            wooCommitSummary={wooCommitSummary}
            wooSyncRuns={wooSyncRuns}
            wooLoading={wooLoading}
            wooError={wooError}
            onLoadWooStatus={loadWooStatus}
            onPreviewWooProductSync={previewWooProductSync}
            onCommitWooProductSync={commitWooProductSync}
          />
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

function PageBody({
  route,
  items,
  itemsLoading,
  itemsError,
  onLoadItems,
  onSaveItem,
  onCloneItem,
  locations,
  locationsLoading,
  locationsError,
  onLoadLocations,
  onSaveLocation,
  inventorySummary,
  inventoryLoading,
  inventoryError,
  onLoadInventorySummary,
  receipts,
  receiptsLoading,
  receiptsError,
  onLoadReceipts,
  stockMovements,
  stockMovementsLoading,
  stockMovementsError,
  onLoadStockMovements,
  receivedInventoryRows,
  receivedInventorySummary,
  receivedInventoryLoading,
  receivedInventoryError,
  onLoadReceivedInventoryReport,
  cycleCounts,
  cycleCountsLoading,
  cycleCountsError,
  onLoadCycleCounts,
  wooStatus,
  wooPreview,
  wooCommitSummary,
  wooSyncRuns,
  wooLoading,
  wooError,
  onLoadWooStatus,
  onPreviewWooProductSync,
  onCommitWooProductSync,
}) {
  if (route.pageId === 'items') {
    return <ItemsPage route={route} items={items} itemsLoading={itemsLoading} itemsError={itemsError} onLoadItems={onLoadItems} onSaveItem={onSaveItem} onCloneItem={onCloneItem} />;
  }

  if (route.pageId === 'locations') {
    return <LocationsPage route={route} locations={locations} loading={locationsLoading} error={locationsError} onLoadLocations={onLoadLocations} onSaveLocation={onSaveLocation} />;
  }

  if (route.pageId === 'inventory') {
    return <InventoryPage items={items} summary={inventorySummary} loading={inventoryLoading} error={inventoryError || itemsError} onLoadSummary={onLoadInventorySummary} />;
  }

  if (route.pageId === 'receiving') {
    return (
      <DirectReceivingPage
        items={items}
        locations={locations}
        receipts={receipts}
        receiptsLoading={receiptsLoading}
        receiptsError={receiptsError}
        onLoadReceipts={onLoadReceipts}
        stockMovements={stockMovements}
        stockMovementsLoading={stockMovementsLoading}
        stockMovementsError={stockMovementsError}
        onLoadStockMovements={onLoadStockMovements}
        onLoadInventorySummary={onLoadInventorySummary}
      />
    );
  }

  if (route.pageId === 'reports') {
    return (
      <ReceivedInventoryReportPage
        rows={receivedInventoryRows}
        summary={receivedInventorySummary}
        loading={receivedInventoryLoading}
        error={receivedInventoryError}
        onLoadReport={onLoadReceivedInventoryReport}
      />
    );
  }

  if (route.pageId === 'cycle-count') {
    return (
      <CycleCountPage
        items={items}
        locations={locations}
        cycleCounts={cycleCounts}
        cycleCountsLoading={cycleCountsLoading}
        cycleCountsError={cycleCountsError}
        onLoadCycleCounts={onLoadCycleCounts}
        onLoadItems={onLoadItems}
        onLoadInventorySummary={onLoadInventorySummary}
      />
    );
  }

  if (route.pageId === 'settings') {
    return (
      <WooCommerceSettingsPage
        status={wooStatus}
        preview={wooPreview}
        commitSummary={wooCommitSummary}
        syncRuns={wooSyncRuns}
        loading={wooLoading}
        error={wooError}
        onCheckConnection={() => onLoadWooStatus(true)}
        onPreview={onPreviewWooProductSync}
        onCommit={onCommitWooProductSync}
      />
    );
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

function InventoryPage({ items, summary, loading, error, onLoadSummary }) {
  const [filters, setFilters] = useState({
    warehouse: '',
    inventoryLocation: '',
    defaultLocation: '',
    category: '',
    brand: '',
    underPar: '',
  });

  const options = useMemo(
    () => ({
      warehouses: uniqueOptions(items, 'Warehouse'),
      locations: uniqueOptions(items, 'Inventory Location'),
      defaultLocations: uniqueOptions(items, 'Default Location'),
      categories: uniqueOptions(items, 'Category'),
      brands: uniqueOptions(items, 'Brand'),
    }),
    [items],
  );

  useEffect(() => {
    onLoadSummary(filters);
  }, [filters]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function clearFilters() {
    setFilters({
      warehouse: '',
      inventoryLocation: '',
      defaultLocation: '',
      category: '',
      brand: '',
      underPar: '',
    });
  }

  return (
    <section className="content-panel inventory-page">
      <div className="summary-strip">
        <Metric label="Total Items" value={summary.total_items || 0} />
        <Metric label="In Stock" value={formatNumber(summary.total_in_stock || 0)} />
        <Metric label="Sellable" value={formatNumber(summary.total_sellable || 0)} />
        <Metric label="Inventory Value" value={formatCurrency(summary.total_inventory_value || 0)} />
        <Metric label="Under Par" value={summary.under_par_count || 0} />
      </div>
      <div className="toolbar items-toolbar">
        <div className="filter-grid inventory-filter-grid">
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Inventory Location" value={filters.inventoryLocation} options={options.locations} onChange={(value) => updateFilter('inventoryLocation', value)} />
          <FilterSelect label="Default Location" value={filters.defaultLocation} options={options.defaultLocations} onChange={(value) => updateFilter('defaultLocation', value)} />
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <label className="field">
            <span>Under Par</span>
            <div className="select-shell">
              <select value={filters.underPar} onChange={(event) => updateFilter('underPar', event.target.value)}>
                <option value="">All</option>
                <option value="true">Under Par</option>
                <option value="false">Not Under Par</option>
              </select>
              <Filter size={18} />
            </div>
          </label>
        </div>
        <div className="button-row items-actions">
          <button className="primary-button" onClick={() => onLoadSummary(filters)} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
          <button className="muted-button" onClick={clearFilters} type="button">
            Clear
          </button>
          <button className="action-button" onClick={() => exportInventoryByLocationCsv(filters)} type="button">
            <Download size={17} />
            Export CSV
          </button>
        </div>
      </div>
      <div className="csv-note">Inventory by location currently uses item Warehouse, Inventory Location, and Default Location text fields.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading inventory summary...</div>}
      <InventorySummaryTable groups={summary.groups || []} />
    </section>
  );
}

function InventorySummaryTable({ groups }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>
          Showing records 1-{groups.length} out of {groups.length}
        </span>
        <div className="table-pager">
          <span>{groups.length} Results</span>
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
        <table className="inventory-summary-table">
          <thead>
            <tr>
              <th>Warehouse</th>
              <th>Inventory Location</th>
              <th>Item Count</th>
              <th>In Stock</th>
              <th>Allocated</th>
              <th>Sellable</th>
              <th>On Order</th>
              <th>Inventory Value</th>
              <th>Under Par Count</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((group) => (
              <tr key={`${group.warehouse}-${group.inventory_location}`}>
                <td>{group.warehouse || 'Unassigned'}</td>
                <td>{group.inventory_location || 'Unassigned'}</td>
                <td>{group.item_count}</td>
                <td>{formatNumber(group.total_in_stock)}</td>
                <td>{formatNumber(group.total_allocated)}</td>
                <td>{formatNumber(group.total_sellable)}</td>
                <td>{formatNumber(group.total_on_order)}</td>
                <td>{formatCurrency(group.total_inventory_value)}</td>
                <td>{group.under_par_count}</td>
              </tr>
            ))}
            {groups.length === 0 && (
              <tr>
                <td colSpan={9}>
                  <div className="empty-table-row">No inventory groups match the current filters.</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LocationsPage({ route, locations, loading, error, onLoadLocations, onSaveLocation }) {
  if (route.locationView === 'new') {
    return <LocationDetail location={emptyLocation} onSave={onSaveLocation} isNew />;
  }

  if (route.locationView === 'detail') {
    const location = locations.find((candidate) => String(candidate.id) === String(route.locationId));
    if (!location) {
      return (
        <section className="content-panel">
          <div className="empty-state">
            <h2>Location not found</h2>
            <p>{loading ? 'Loading location from the backend.' : 'The selected location is not available from the backend.'}</p>
            <a className="primary-button" href="#locations">
              Return to Locations
            </a>
          </div>
        </section>
      );
    }
    return <LocationDetail location={location} onSave={onSaveLocation} />;
  }

  if (route.locationView === 'stock') {
    return (
      <StandardPage
        icon={MapPin}
        title="Location Stock"
        description="Placeholder for future item-location stock splits. Item stock logic is not connected yet."
        columns={['Area', 'Status', 'Type', 'Notes']}
      />
    );
  }

  return <LocationsList locations={locations} loading={loading} error={error} onLoadLocations={onLoadLocations} />;
}

function LocationsList({ locations, loading, error, onLoadLocations }) {
  const [importOpen, setImportOpen] = useState(false);
  const [filters, setFilters] = useState({
    search: '',
    warehouse: '',
    zone: '',
    aisle: '',
    status: 'active',
  });

  const options = useMemo(
    () => ({
      warehouses: uniqueOptions(locations, 'warehouse'),
      zones: uniqueOptions(locations, 'zone'),
      aisles: uniqueOptions(locations, 'aisle'),
    }),
    [locations],
  );

  useEffect(() => {
    onLoadLocations(filters);
  }, [filters]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function clearFilters() {
    setFilters({
      search: '',
      warehouse: '',
      zone: '',
      aisle: '',
      status: 'active',
    });
  }

  return (
    <section className="content-panel">
      <div className="toolbar items-toolbar">
        <div className="filter-grid locations-filter-grid">
          <label className="field">
            <span>Search</span>
            <div className="input-with-icon">
              <input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} placeholder="Warehouse, code, name, zone, aisle" type="search" />
              <Search size={18} />
            </div>
          </label>
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Zone" value={filters.zone} options={options.zones} onChange={(value) => updateFilter('zone', value)} />
          <FilterSelect label="Aisle" value={filters.aisle} options={options.aisles} onChange={(value) => updateFilter('aisle', value)} />
          <div className="field status-field">
            <span>Show</span>
            <div className="radio-row">
              <label>
                <input checked={filters.status === 'active'} name="location-status" onChange={() => updateFilter('status', 'active')} type="radio" />
                Active
              </label>
              <label>
                <input checked={filters.status === 'inactive'} name="location-status" onChange={() => updateFilter('status', 'inactive')} type="radio" />
                Inactive
              </label>
            </div>
          </div>
        </div>
        <div className="button-row items-actions">
          <a className="primary-button" href="#/locations/new">
            <Plus size={17} />
            Add Location
          </a>
          <button className="muted-button" onClick={clearFilters} type="button">
            Clear
          </button>
          <button className="action-button" onClick={() => setImportOpen(true)} type="button">
            <Upload size={17} />
            Import
          </button>
          <button className="action-button" onClick={() => exportLocationsCsv(filters)} type="button">
            <Download size={17} />
            Export
          </button>
        </div>
      </div>
      <div className="csv-note">Location import/export uses the canonical Warehouse, Location Code, and Location Name CSV foundation.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading backend locations...</div>}
      <LocationsTable locations={locations} />
      {importOpen && <LocationImportModal onClose={() => setImportOpen(false)} onImported={() => onLoadLocations(filters)} />}
    </section>
  );
}

function LocationsTable({ locations }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>
          Showing records 1-{locations.length} out of {locations.length}
        </span>
        <div className="table-pager">
          <span>{locations.length} Results</span>
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
        <table className="locations-data-table">
          <thead>
            <tr>
              <th>Edit</th>
              {CANONICAL_LOCATION_COLUMNS.map((column) => (
                <th key={column}>{column}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {locations.map((location) => (
              <tr key={location.id}>
                <td>
                  <a className="round-action" href={`#/locations/${location.id}`} aria-label={`Edit ${location.code}`}>
                    <Edit3 size={17} />
                  </a>
                </td>
                <td>{location.warehouse}</td>
                <td className="mono">{location.code}</td>
                <td>{location.name}</td>
                <td className="description-cell">{location.description}</td>
                <td>{location.zone}</td>
                <td>{location.aisle}</td>
                <td>{location.rack}</td>
                <td>{location.shelf}</td>
                <td>{location.bin}</td>
                <td>
                  <BooleanBadge value={location.isDefault} />
                </td>
                <td>
                  <StatusBadge active={location.isActive} />
                </td>
              </tr>
            ))}
            {locations.length === 0 && (
              <tr>
                <td colSpan={CANONICAL_LOCATION_COLUMNS.length + 1}>
                  <div className="empty-table-row">No locations match the current filters.</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LocationDetail({ location, onSave, isNew = false }) {
  const [formLocation, setFormLocation] = useState(() => normalizeLocation(location));
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);

  function updateField(field, value) {
    setFormLocation((current) => normalizeLocation({ ...current, [field]: value }));
  }

  async function saveChanges() {
    setSaveError('');
    setSaving(true);
    try {
      await onSave(formLocation);
    } catch (error) {
      setSaveError('Unable to save location to the backend. Check that FastAPI is running and warehouse/code/name are valid.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="content-panel">
      <div className="detail-layout single-detail-layout">
        <div className="detail-main">
          <FormSection title="Location Identity">
            {renderLocationTextField('warehouse', 'Warehouse', formLocation, updateField, { required: true })}
            {renderLocationTextField('code', 'Location Code', formLocation, updateField, { required: true })}
            {renderLocationTextField('name', 'Location Name', formLocation, updateField, { required: true })}
            {renderLocationTextField('description', 'Description', formLocation, updateField, { wide: true })}
          </FormSection>
          <FormSection title="Physical Position">
            {renderLocationTextField('zone', 'Zone', formLocation, updateField)}
            {renderLocationTextField('aisle', 'Aisle', formLocation, updateField)}
            {renderLocationTextField('rack', 'Rack', formLocation, updateField)}
            {renderLocationTextField('shelf', 'Shelf', formLocation, updateField)}
            {renderLocationTextField('bin', 'Bin', formLocation, updateField)}
          </FormSection>
          <FormSection title="Status">
            <label className="toggle-card">
              <input checked={Boolean(formLocation.isDefault)} onChange={(event) => updateField('isDefault', event.target.checked)} type="checkbox" />
              <span>Default</span>
            </label>
            <label className="toggle-card">
              <input checked={Boolean(formLocation.isActive)} onChange={(event) => updateField('isActive', event.target.checked)} type="checkbox" />
              <span>Active</span>
            </label>
          </FormSection>
        </div>
      </div>
      <div className="detail-actions">
        {saveError && <div className="api-error detail-error">{saveError}</div>}
        <button className="primary-button" disabled={saving} onClick={saveChanges} type="button">
          <Save size={17} />
          {saving ? 'Saving' : 'Save Changes'}
        </button>
        <a className="action-button" href="#locations">
          <ArrowLeft size={17} />
          Return to Locations
        </a>
      </div>
    </section>
  );
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
      {summary.warnings?.length > 0 && (
        <div className="warning-list">
          {summary.warnings.slice(0, 8).map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}
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
        <div className="import-error-row" key={`${error.row_number}-${error.sku || error.code}-${error.error_message}`}>
          <span>Row {error.row_number}</span>
          <span>{error.sku || error.code || 'No Code'}</span>
          <span>{error.barcode || error.warehouse || 'No Warehouse'}</span>
          <strong>{error.error_message}</strong>
        </div>
      ))}
    </div>
  );
}

function LocationImportModal({ onClose, onImported }) {
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
      const result = await uploadImportFile('/api/locations/import/preview', file);
      setPreview(result);
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview locations CSV import.');
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
      const result = await uploadImportFile('/api/locations/import/commit', file);
      setSummary(result);
      await onImported();
    } catch (apiError) {
      setError(apiError.message || 'Unable to import locations CSV.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Import locations CSV">
        <div className="modal-header">
          <div>
            <h2>Import Locations CSV</h2>
            <p>Warehouse, Location Code, and Location Name are required.</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close import modal" type="button">
            <MoreVertical size={20} />
          </button>
        </div>
        <div className="import-steps">
          <section className="import-step">
            <h3>1. Upload CSV</h3>
            <p>Expected columns: {CANONICAL_LOCATION_COLUMNS.join(', ')}. Extra columns are ignored and reported as warnings.</p>
            <input type="file" accept=".csv,text/csv" onChange={(event) => setFile(event.target.files?.[0] || null)} />
            <button className="muted-button" onClick={downloadSampleLocationsCsv} type="button">
              <Download size={17} />
              Download Sample CSV
            </button>
          </section>
          <section className="import-step">
            <h3>2. Preview</h3>
            <button className="primary-button" disabled={loading || !file} onClick={previewImport} type="button">
              Preview CSV
            </button>
            {preview && <LocationImportPreview preview={preview} />}
          </section>
          <section className="import-step">
            <h3>3. Commit Import</h3>
            <button className="primary-button" disabled={loading || !file || !preview} onClick={commitImport} type="button">
              Import Valid Rows
            </button>
            {summary && <ImportSummary summary={summary} />}
          </section>
        </div>
        {loading && <div className="loading-strip">Working on locations CSV import...</div>}
        {error && <div className="api-error">{error}</div>}
      </section>
    </div>
  );
}

function LocationImportPreview({ preview }) {
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
              <th>Warehouse</th>
              <th>Code</th>
              <th>Name</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {preview.preview_rows.map((row) => (
              <tr key={row.row_number}>
                <td>{row.row_number}</td>
                <td>{row.action}</td>
                <td>{row.warehouse}</td>
                <td>{row.code}</td>
                <td>{row.name}</td>
                <td>{row.row.Active ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

function renderLocationTextField(field, label, location, updateField, options = {}) {
  return (
    <label className={options.wide ? 'field form-field wide-field' : 'field form-field'} key={field}>
      <span>{label}</span>
      <input required={options.required} value={location[field] ?? ''} onChange={(event) => updateField(field, event.target.value)} />
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

function CycleCountPage({ items, locations, cycleCounts, cycleCountsLoading, cycleCountsError, onLoadCycleCounts, onLoadItems, onLoadInventorySummary }) {
  const [form, setForm] = useState({
    warehouse: 'Main Warehouse',
    inventory_location: '',
    count_type: 'selected_items',
    notes: '',
    lines: [emptyCycleCountLine()],
  });
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);

  const activeLocations = locations.filter((location) => location.isActive);
  const locationOptions = activeLocations.filter((location) => !form.warehouse || location.warehouse === form.warehouse);

  function updateHeader(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setPreview(null);
    setSummary(null);
  }

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => (lineIndex === index ? { ...line, [field]: value } : line)),
    }));
    setPreview(null);
    setSummary(null);
  }

  function addLine() {
    setForm((current) => ({ ...current, lines: [...current.lines, emptyCycleCountLine()] }));
  }

  function removeLine(index) {
    setForm((current) => ({ ...current, lines: current.lines.filter((_, lineIndex) => lineIndex !== index) }));
  }

  function resetForm() {
    setForm({ warehouse: 'Main Warehouse', inventory_location: '', count_type: 'selected_items', notes: '', lines: [emptyCycleCountLine()] });
    setPreview(null);
    setSummary(null);
    setError('');
  }

  async function previewCount() {
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      setPreview(await postJson('/api/cycle-counts/preview', cycleCountPayload(form, items)));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview cycle count.');
    } finally {
      setLoading(false);
    }
  }

  async function postCount() {
    setLoading(true);
    setError('');
    try {
      const result = await postJson('/api/cycle-counts/commit', cycleCountPayload(form, items));
      setSummary(result);
      await onLoadCycleCounts();
      await onLoadItems();
      await onLoadInventorySummary();
      setForm({ warehouse: 'Main Warehouse', inventory_location: '', count_type: 'selected_items', notes: '', lines: [emptyCycleCountLine()] });
      setPreview(null);
    } catch (apiError) {
      setError(apiError.message || 'Unable to post cycle count.');
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(cycleCountId) {
    setDetailLoading(true);
    setError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/cycle-counts/${cycleCountId}`);
      if (!response.ok) {
        throw new Error(`Cycle Count detail returned ${response.status}`);
      }
      setDetail(await response.json());
    } catch (apiError) {
      setError('Unable to load cycle count detail.');
    } finally {
      setDetailLoading(false);
    }
  }

  return (
    <section className="content-panel receiving-page cycle-count-page">
      <div className="receiving-form">
        <div className="section-heading">
          <div>
            <h2>New Cycle Count</h2>
            <p>Count physical stock and post audited adjustments</p>
          </div>
          <button className="muted-button" onClick={resetForm} type="button">
            Reset Form
          </button>
        </div>
        <div className="receiving-header-fields cycle-count-header-fields">
          <FilterSelect label="Warehouse" value={form.warehouse} options={uniqueOptions(activeLocations, 'warehouse')} onChange={(value) => updateHeader('warehouse', value || 'Main Warehouse')} />
          <label className="field">
            <span>Inventory Location</span>
            <div className="select-shell">
              <select value={form.inventory_location} onChange={(event) => updateHeader('inventory_location', event.target.value)}>
                <option value="">Optional for selected items</option>
                {locationOptions.map((location) => (
                  <option key={location.id} value={location.code}>
                    {location.warehouse} / {location.code}
                  </option>
                ))}
              </select>
              <Filter size={18} />
            </div>
          </label>
          <label className="field">
            <span>Count Type</span>
            <div className="select-shell">
              <select value={form.count_type} onChange={(event) => updateHeader('count_type', event.target.value)}>
                <option value="selected_items">Selected Items</option>
                <option value="full_location">Full Location</option>
              </select>
              <Filter size={18} />
            </div>
          </label>
          <label className="field wide-field">
            <span>Notes</span>
            <input value={form.notes} onChange={(event) => updateHeader('notes', event.target.value)} placeholder="Optional count notes" />
          </label>
        </div>
        <div className="table-scroll receiving-line-scroll">
          <table className="receiving-line-table cycle-count-line-table">
            <thead>
              <tr>
                <th>SKU / Barcode</th>
                <th>Description</th>
                <th>System Qty</th>
                <th>Counted Quantity</th>
                <th>Notes</th>
                <th>Remove</th>
              </tr>
            </thead>
            <tbody>
              {form.lines.map((line, index) => {
                const item = findReceivingItem(items, line.query);
                return (
                  <tr key={line.localId}>
                    <td>
                      <input value={line.query} onChange={(event) => updateLine(index, 'query', event.target.value)} placeholder="Scan or type SKU/barcode" />
                    </td>
                    <td className="description-cell">{item?.Description || ''}</td>
                    <td>{item ? formatNumber(item['In Stock']) : ''}</td>
                    <td>
                      <input value={line.counted_quantity} onChange={(event) => updateLine(index, 'counted_quantity', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input value={line.notes} onChange={(event) => updateLine(index, 'notes', event.target.value)} />
                    </td>
                    <td>
                      <button className="pager-button" onClick={() => removeLine(index)} disabled={form.lines.length === 1} type="button">
                        <MoreVertical size={17} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="detail-actions">
          <button className="muted-button" onClick={addLine} type="button">
            <Plus size={17} />
            Add Line
          </button>
          <button className="primary-button" disabled={loading} onClick={previewCount} type="button">
            Preview Count
          </button>
          <button className="primary-button" disabled={loading || !preview || preview.invalid_lines > 0} onClick={postCount} type="button">
            Post Count
          </button>
        </div>
        {loading && <div className="loading-strip">Working on cycle count...</div>}
        {error && <div className="api-error">{error}</div>}
        {summary && (
          <div className="success-strip">
            Cycle count {summary.count_number} posted. {summary.adjustment_lines} adjustment line(s), {summary.created_movements} movement(s) created.
          </div>
        )}
        {preview && <CycleCountPreview preview={preview} />}
      </div>
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Cycle Count History</h2>
            <p>Posted physical inventory counts.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadCycleCounts()} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
        </div>
        {cycleCountsError && <div className="api-error">{cycleCountsError}</div>}
        {cycleCountsLoading && <div className="loading-strip">Loading cycle count history...</div>}
        <CycleCountHistoryTable counts={cycleCounts} onLoadDetail={loadDetail} />
      </div>
      {detailLoading && <div className="loading-strip">Loading cycle count detail...</div>}
      {detail && <CycleCountDetailPanel detail={detail} onClose={() => setDetail(null)} />}
    </section>
  );
}

function CycleCountPreview({ preview }) {
  return (
    <div className="import-results receiving-preview">
      <div className="import-metrics cycle-count-metrics">
        <Metric label="Lines" value={preview.total_lines} />
        <Metric label="Adjustments" value={preview.adjustment_lines} />
        <Metric label="Positive Var" value={formatNumber(preview.total_positive_variance)} />
        <Metric label="Negative Var" value={formatNumber(preview.total_negative_variance)} />
        <Metric label="Absolute Var" value={formatNumber(preview.total_absolute_variance)} />
        <Metric label="Variance Value" value={formatCurrency(preview.total_variance_value)} />
      </div>
      {preview.errors?.length > 0 && (
        <div className="import-errors">
          <h4>Validation Errors</h4>
          {preview.errors.map((previewError) => (
            <div key={previewError}>{previewError}</div>
          ))}
        </div>
      )}
      <div className="table-scroll">
        <table className="preview-table cycle-count-preview-table">
          <thead>
            <tr>
              <th>Line</th>
              <th>Status</th>
              <th>SKU</th>
              <th>Description</th>
              <th>Location</th>
              <th>System Qty</th>
              <th>Counted Qty</th>
              <th>Variance</th>
              <th>Variance Value</th>
            </tr>
          </thead>
          <tbody>
            {preview.preview_lines.map((line) => (
              <tr key={line.line_number}>
                <td>{line.line_number}</td>
                <td>{line.status}</td>
                <td>{line.sku}</td>
                <td>{line.description}</td>
                <td>{line.inventory_location}</td>
                <td>{formatNumber(line.system_quantity)}</td>
                <td>{formatNumber(line.counted_quantity)}</td>
                <td>{formatNumber(line.variance_quantity)}</td>
                <td>{formatCurrency(line.variance_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CycleCountHistoryTable({ counts, onLoadDetail }) {
  return (
    <TableShell caption={`${counts.length} cycle count(s)`} columns={['Count Number', 'Status', 'Warehouse', 'Inventory Location', 'Count Type', 'Total Lines', 'Adjustment Lines', 'Created At', 'Posted At', 'Created By', 'Export']}>
      {counts.map((count) => (
        <tr key={count.id}>
          <td>
            <button className="link-button mono" onClick={() => onLoadDetail(count.id)} type="button">
              {count.count_number}
            </button>
          </td>
          <td>{count.status}</td>
          <td>{count.warehouse}</td>
          <td>{count.inventory_location}</td>
          <td>{formatCountType(count.count_type)}</td>
          <td>{count.total_lines}</td>
          <td>{count.adjustment_lines}</td>
          <td>{formatDateTime(count.created_at)}</td>
          <td>{formatDateTime(count.posted_at)}</td>
          <td>{count.created_by}</td>
          <td>
            <button className="action-button" onClick={() => exportCycleCountCsv(count.id, count.count_number)} type="button">
              <Download size={17} />
              Export
            </button>
          </td>
        </tr>
      ))}
      {counts.length === 0 && (
        <tr>
          <td colSpan={11}>
            <div className="empty-table-row">No cycle counts posted yet.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function CycleCountDetailPanel({ detail, onClose }) {
  return (
    <div className="wide-panel">
      <div className="panel-title">
        <div>
          <h2>{detail.count_number}</h2>
          <p>
            {formatCountType(detail.count_type)} / {detail.status}
          </p>
        </div>
        <div className="button-row compact">
          <button className="action-button" onClick={() => exportCycleCountCsv(detail.id, detail.count_number)} type="button">
            <Download size={17} />
            Export CSV
          </button>
          <button className="muted-button" onClick={onClose} type="button">
            Close
          </button>
        </div>
      </div>
      <TableShell caption={`${detail.lines.length} counted line(s)`} columns={['SKU', 'Barcode', 'Description', 'Warehouse', 'Inventory Location', 'System Quantity', 'Counted Quantity', 'Variance Quantity', 'Unit Cost', 'Variance Value', 'Notes']}>
        {detail.lines.map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.description}</td>
            <td>{line.warehouse}</td>
            <td>{line.inventory_location}</td>
            <td>{formatNumber(line.system_quantity)}</td>
            <td>{formatNumber(line.counted_quantity)}</td>
            <td>{formatNumber(line.variance_quantity)}</td>
            <td>{formatCurrency(line.unit_cost)}</td>
            <td>{formatCurrency(line.variance_value)}</td>
            <td>{line.notes}</td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function DirectReceivingPage({ items, locations, receipts, receiptsLoading, receiptsError, onLoadReceipts, stockMovements, stockMovementsLoading, stockMovementsError, onLoadStockMovements, onLoadInventorySummary }) {
  const [form, setForm] = useState({
    warehouse: 'Main Warehouse',
    reference_number: '',
    notes: '',
    lines: [emptyReceivingLine()],
  });
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const activeLocations = locations.filter((location) => location.isActive);
  const locationOptions = activeLocations.filter((location) => !form.warehouse || location.warehouse === form.warehouse);

  function updateHeader(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setPreview(null);
    setSummary(null);
  }

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => (lineIndex === index ? { ...line, [field]: value } : line)),
    }));
    setPreview(null);
    setSummary(null);
  }

  function addLine() {
    setForm((current) => ({ ...current, lines: [...current.lines, emptyReceivingLine()] }));
  }

  function removeLine(index) {
    setForm((current) => ({ ...current, lines: current.lines.filter((_, lineIndex) => lineIndex !== index) }));
  }

  function resetForm() {
    setForm({ warehouse: 'Main Warehouse', reference_number: '', notes: '', lines: [emptyReceivingLine()] });
    setPreview(null);
    setSummary(null);
    setError('');
  }

  async function previewReceiving() {
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      setPreview(await postJson('/api/receipts/direct/preview', receivingPayload(form, items)));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview receiving.');
    } finally {
      setLoading(false);
    }
  }

  async function commitReceiving() {
    setLoading(true);
    setError('');
    try {
      const result = await postJson('/api/receipts/direct/commit', receivingPayload(form, items));
      setSummary(result);
      await onLoadReceipts();
      await onLoadStockMovements({ movement_type: 'receive_direct' });
      await onLoadInventorySummary();
      setForm({ warehouse: 'Main Warehouse', reference_number: '', notes: '', lines: [emptyReceivingLine()] });
      setPreview(null);
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit receiving.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="content-panel receiving-page">
      <div className="receiving-form">
        <div className="section-heading">
          <div>
            <h2>Direct Receiving</h2>
            <p>Receive stock without a purchase order</p>
          </div>
          <button className="muted-button" onClick={resetForm} type="button">
            Reset Form
          </button>
        </div>
        <div className="receiving-header-fields">
          <FilterSelect label="Warehouse" value={form.warehouse} options={uniqueOptions(activeLocations, 'warehouse')} onChange={(value) => updateHeader('warehouse', value || 'Main Warehouse')} />
          <label className="field">
            <span>Reference Number</span>
            <input value={form.reference_number} onChange={(event) => updateHeader('reference_number', event.target.value)} placeholder="Invoice, delivery note, or manual reference" />
          </label>
          <label className="field wide-field">
            <span>Notes</span>
            <input value={form.notes} onChange={(event) => updateHeader('notes', event.target.value)} placeholder="Optional receiving notes" />
          </label>
        </div>
        <div className="table-scroll receiving-line-scroll">
          <table className="receiving-line-table">
            <thead>
              <tr>
                <th>SKU / Barcode</th>
                <th>Description</th>
                <th>Inventory Location</th>
                <th>Quantity Received</th>
                <th>Unit Cost</th>
                <th>Notes</th>
                <th>Remove</th>
              </tr>
            </thead>
            <tbody>
              {form.lines.map((line, index) => {
                const item = findReceivingItem(items, line.query);
                return (
                  <tr key={line.localId}>
                    <td>
                      <input value={line.query} onChange={(event) => updateLine(index, 'query', event.target.value)} placeholder="Scan or type SKU/barcode" />
                    </td>
                    <td className="description-cell">{item?.Description || ''}</td>
                    <td>
                      <select value={line.inventory_location} onChange={(event) => updateLine(index, 'inventory_location', event.target.value)}>
                        <option value="">Select location</option>
                        {locationOptions.map((location) => (
                          <option key={location.id} value={location.code}>
                            {location.warehouse} / {location.code}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input value={line.quantity_received} onChange={(event) => updateLine(index, 'quantity_received', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input value={line.unit_cost} onChange={(event) => updateLine(index, 'unit_cost', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input value={line.notes} onChange={(event) => updateLine(index, 'notes', event.target.value)} />
                    </td>
                    <td>
                      <button className="pager-button" onClick={() => removeLine(index)} disabled={form.lines.length === 1} type="button">
                        <MoreVertical size={17} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <div className="detail-actions">
          <button className="muted-button" onClick={addLine} type="button">
            <Plus size={17} />
            Add Line
          </button>
          <button className="primary-button" disabled={loading} onClick={previewReceiving} type="button">
            Preview Receiving
          </button>
          <button className="primary-button" disabled={loading || !preview || preview.invalid_lines > 0} onClick={commitReceiving} type="button">
            Commit Receiving
          </button>
        </div>
        {loading && <div className="loading-strip">Working on receiving...</div>}
        {error && <div className="api-error">{error}</div>}
        {summary && (
          <div className="success-strip">
            Receipt {summary.receipt_number} posted. {summary.total_quantity_received} units received across {summary.total_lines} line(s).
          </div>
        )}
        {preview && <ReceivingPreview preview={preview} />}
      </div>
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Receipt History</h2>
            <p>Posted direct receiving sessions.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadReceipts()} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
        </div>
        {receiptsError && <div className="api-error">{receiptsError}</div>}
        {receiptsLoading && <div className="loading-strip">Loading receipt history...</div>}
        <ReceiptHistoryTable receipts={receipts} />
      </div>
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Recent Stock Movements</h2>
            <p>Audit trail for direct receiving.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadStockMovements({ movement_type: 'receive_direct' })} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
        </div>
        {stockMovementsError && <div className="api-error">{stockMovementsError}</div>}
        {stockMovementsLoading && <div className="loading-strip">Loading stock movements...</div>}
        <StockMovementsTable movements={stockMovements} />
      </div>
    </section>
  );
}

function ReceivingPreview({ preview }) {
  return (
    <div className="import-results receiving-preview">
      <div className="import-metrics">
        <Metric label="Lines" value={preview.total_lines} />
        <Metric label="Valid" value={preview.valid_lines} />
        <Metric label="Invalid" value={preview.invalid_lines} />
        <Metric label="Quantity" value={formatNumber(preview.total_quantity)} />
        <Metric label="Value" value={formatCurrency(preview.estimated_inventory_value)} />
      </div>
      {preview.errors?.length > 0 && (
        <div className="import-errors">
          <h4>Validation Errors</h4>
          {preview.errors.map((previewError) => (
            <div key={previewError}>{previewError}</div>
          ))}
        </div>
      )}
      <div className="table-scroll">
        <table className="preview-table">
          <thead>
            <tr>
              <th>Line</th>
              <th>Status</th>
              <th>SKU</th>
              <th>Description</th>
              <th>Location</th>
              <th>Qty</th>
              <th>Previous</th>
              <th>New</th>
              <th>Line Value</th>
            </tr>
          </thead>
          <tbody>
            {preview.preview_lines.map((line) => (
              <tr key={line.line_number}>
                <td>{line.line_number}</td>
                <td>{line.status}</td>
                <td>{line.sku}</td>
                <td>{line.description}</td>
                <td>{line.inventory_location}</td>
                <td>{formatNumber(line.quantity_received)}</td>
                <td>{formatNumber(line.previous_in_stock)}</td>
                <td>{formatNumber(line.new_in_stock)}</td>
                <td>{formatCurrency(line.line_value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReceiptHistoryTable({ receipts }) {
  return (
    <TableShell caption={`${receipts.length} receipt(s)`} columns={['Receipt Number', 'Warehouse', 'Reference Number', 'Status', 'Total Lines', 'Total Quantity', 'Received At', 'Created By']}>
      {receipts.map((receipt) => (
        <tr key={receipt.id}>
          <td className="mono">{receipt.receipt_number}</td>
          <td>{receipt.warehouse}</td>
          <td>{receipt.reference_number}</td>
          <td>{receipt.status}</td>
          <td>{receipt.total_lines}</td>
          <td>{formatNumber(receipt.total_quantity)}</td>
          <td>{formatDateTime(receipt.received_at || receipt.created_at)}</td>
          <td>{receipt.created_by}</td>
        </tr>
      ))}
      {receipts.length === 0 && (
        <tr>
          <td colSpan={8}>
            <div className="empty-table-row">No receipts posted yet.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function StockMovementsTable({ movements }) {
  return (
    <TableShell caption={`${movements.length} movement(s)`} columns={['Created At', 'SKU', 'Barcode', 'Movement Type', 'Quantity Delta', 'Previous In Stock', 'New In Stock', 'Warehouse', 'Inventory Location', 'Reference Number']}>
      {movements.map((movement) => (
        <tr key={movement.id}>
          <td>{formatDateTime(movement.created_at)}</td>
          <td className="mono">{movement.sku}</td>
          <td className="mono">{movement.barcode}</td>
          <td>{movement.movement_type}</td>
          <td>{formatNumber(movement.quantity_delta)}</td>
          <td>{formatNumber(movement.previous_in_stock)}</td>
          <td>{formatNumber(movement.new_in_stock)}</td>
          <td>{movement.warehouse}</td>
          <td>{movement.inventory_location}</td>
          <td className="mono">{movement.reference_number}</td>
        </tr>
      ))}
      {movements.length === 0 && (
        <tr>
          <td colSpan={10}>
            <div className="empty-table-row">No stock movements yet.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function ReceivedInventoryReportPage({ rows, summary, loading, error, onLoadReport }) {
  const [filters, setFilters] = useState(emptyReceivedInventoryFilters);
  const [activeFilters, setActiveFilters] = useState(emptyReceivedInventoryFilters);
  const options = useMemo(
    () => ({
      warehouses: uniqueOptions(rows, 'warehouse'),
      locations: uniqueOptions(rows, 'inventory_location'),
      categories: uniqueOptions(rows, 'category'),
      brands: uniqueOptions(rows, 'brand'),
    }),
    [rows],
  );

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function applyFilters() {
    setActiveFilters(filters);
    onLoadReport(filters);
  }

  function clearFilters() {
    const cleared = emptyReceivedInventoryFilters();
    setFilters(cleared);
    setActiveFilters(cleared);
    onLoadReport(cleared);
  }

  return (
    <section className="content-panel report-page">
      <div className="summary-strip report-summary-strip">
        <Metric label="Total Receipts" value={summary.total_receipts || 0} />
        <Metric label="Total Lines" value={summary.total_lines || 0} />
        <Metric label="Quantity Received" value={formatNumber(summary.total_quantity_received || 0)} />
        <Metric label="Received Value" value={formatCurrency(summary.total_received_value || 0)} />
        <Metric label="Unique SKUs" value={summary.unique_skus || 0} />
        <Metric label="Unique Locations" value={summary.unique_locations || 0} />
      </div>
      <div className="toolbar report-toolbar">
        <div className="filter-grid report-filter-grid">
          <label className="field">
            <span>Date From</span>
            <div className="input-with-icon">
              <input value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <label className="field">
            <span>Date To</span>
            <div className="input-with-icon">
              <input value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Inventory Location" value={filters.inventoryLocation} options={options.locations} onChange={(value) => updateFilter('inventoryLocation', value)} />
          <label className="field">
            <span>SKU</span>
            <div className="input-with-icon">
              <input value={filters.sku} onChange={(event) => updateFilter('sku', event.target.value)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Barcode</span>
            <div className="input-with-icon">
              <input value={filters.barcode} onChange={(event) => updateFilter('barcode', event.target.value)} />
              <Search size={18} />
            </div>
          </label>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <label className="field">
            <span>Receipt Number</span>
            <div className="input-with-icon">
              <input value={filters.receiptNumber} onChange={(event) => updateFilter('receiptNumber', event.target.value)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Reference Number</span>
            <div className="input-with-icon">
              <input value={filters.referenceNumber} onChange={(event) => updateFilter('referenceNumber', event.target.value)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Created By</span>
            <div className="input-with-icon">
              <input value={filters.createdBy} onChange={(event) => updateFilter('createdBy', event.target.value)} />
              <UserCircle size={18} />
            </div>
          </label>
        </div>
        <div className="button-row items-actions">
          <button className="primary-button" onClick={applyFilters} type="button">
            <Filter size={17} />
            Apply Filters
          </button>
          <button className="muted-button" onClick={clearFilters} type="button">
            Clear Filters
          </button>
          <button className="action-button" onClick={() => onLoadReport(activeFilters)} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
          <button className="action-button" onClick={() => exportReceivedInventoryCsv(activeFilters)} type="button">
            <Download size={17} />
            Export CSV
          </button>
        </div>
      </div>
      <div className="csv-note">Received Inventory is read-only and based on direct receiving receipt lines. Purchase order receiving is not built yet.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading received inventory report...</div>}
      <ReceivedInventoryTable rows={rows} />
      <div className="wide-panel grouped-report-panel">
        <div className="panel-title">
          <div>
            <h2>Grouped by Location</h2>
            <p>Quantity and value received by warehouse location.</p>
          </div>
        </div>
        <ReceivedInventoryLocationSummaryTable groups={summary.by_location || []} />
      </div>
    </section>
  );
}

function ReceivedInventoryTable({ rows }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>
          Showing records 1-{rows.length} out of {rows.length}
        </span>
        <div className="table-pager">
          <span>{rows.length} Results</span>
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
        <table className="received-inventory-table">
          <thead>
            <tr>
              <th>Receipt Number</th>
              <th>Received At</th>
              <th>Warehouse</th>
              <th>Inventory Location</th>
              <th>SKU</th>
              <th>Barcode</th>
              <th>Description</th>
              <th>Category</th>
              <th>Brand</th>
              <th>Quantity Received</th>
              <th>Unit Cost</th>
              <th>Total Received Value</th>
              <th>Reference Number</th>
              <th>Created By</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.receipt_id}-${row.sku}-${row.inventory_location}`}>
                <td className="mono">{row.receipt_number}</td>
                <td>{formatDateTime(row.received_at || row.created_at)}</td>
                <td>{row.warehouse}</td>
                <td>{row.inventory_location}</td>
                <td className="mono">{row.sku}</td>
                <td className="mono">{row.barcode}</td>
                <td className="description-cell">{row.description}</td>
                <td>{row.category}</td>
                <td>{row.brand}</td>
                <td>{formatNumber(row.quantity_received)}</td>
                <td>{formatCurrency(row.unit_cost)}</td>
                <td>{formatCurrency(row.total_received_value)}</td>
                <td className="mono">{row.reference_number}</td>
                <td>{row.created_by}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={14}>
                  <div className="empty-table-row">No received inventory rows match the current filters.</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ReceivedInventoryLocationSummaryTable({ groups }) {
  return (
    <TableShell caption={`${groups.length} location group(s)`} columns={['Warehouse', 'Inventory Location', 'Total Lines', 'Total Quantity Received', 'Total Received Value']}>
      {groups.map((group) => (
        <tr key={`${group.warehouse}-${group.inventory_location}`}>
          <td>{group.warehouse || 'Unassigned'}</td>
          <td>{group.inventory_location || 'Unassigned'}</td>
          <td>{group.total_lines}</td>
          <td>{formatNumber(group.total_quantity_received)}</td>
          <td>{formatCurrency(group.total_received_value)}</td>
        </tr>
      ))}
      {groups.length === 0 && (
        <tr>
          <td colSpan={5}>
            <div className="empty-table-row">No location groups match the current filters.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function WooCommerceSettingsPage({ status, preview, commitSummary, syncRuns, loading, error, onCheckConnection, onPreview, onCommit }) {
  const latestRun = syncRuns[0];
  const commitDisabled = !status.configured || !preview || preview.conflict_count > 0 || preview.error_count > 0;
  return (
    <section className="content-panel settings-page">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>WooCommerce Product Sync</h2>
            <p>This sync is read-only against WooCommerce. It only creates or updates local Pongo OS items. It does not change WooCommerce products, orders, or stock.</p>
          </div>
          <div className="button-row compact">
            <button className="muted-button" onClick={onCheckConnection} type="button">
              <CheckCircle2 size={17} />
              Check Connection
            </button>
            <button className="primary-button" disabled={loading || !status.configured} onClick={onPreview} type="button">
              <Search size={17} />
              Preview Product Sync
            </button>
            <button className="action-button" disabled={loading || commitDisabled} onClick={onCommit} type="button">
              <RefreshCw size={17} />
              Commit Product Sync
            </button>
          </div>
        </div>
        <div className="summary-strip report-summary-strip">
          <Metric label="Configured" value={status.configured ? 'Yes' : 'No'} />
          <Metric label="Base URL" value={status.base_url_present ? 'Present' : 'Missing'} />
          <Metric label="Consumer Key" value={status.consumer_key_present ? 'Present' : 'Missing'} />
          <Metric label="Consumer Secret" value={status.consumer_secret_present ? 'Present' : 'Missing'} />
          <Metric label="Last Sync" value={latestRun ? latestRun.status : 'None'} />
          <Metric label="Last Records" value={latestRun ? latestRun.total_remote_records : 0} />
        </div>
        <div className="csv-note">{status.message}</div>
        {loading && <div className="loading-strip">Working with the Pongo backend...</div>}
        {error && <div className="api-error">{error}</div>}
        {preview && <WooPreviewSummary preview={preview} />}
        {commitSummary && (
          <div className="success-strip">
            Sync run {commitSummary.sync_run_id || 'not created'} finished with status {commitSummary.status}. Created {commitSummary.created_count}, updated {commitSummary.updated_count}, skipped {commitSummary.skipped_count}.
          </div>
        )}
      </div>
      {preview && <WooPreviewTable rows={preview.preview_rows || []} />}
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Sync Run History</h2>
            <p>Local product sync attempts and outcomes.</p>
          </div>
        </div>
        <WooSyncRunsTable runs={syncRuns} />
      </div>
    </section>
  );
}

function WooPreviewSummary({ preview }) {
  return (
    <div className="summary-strip woo-summary-strip">
      <Metric label="Remote Records" value={preview.total_remote_records} />
      <Metric label="Create" value={preview.create_count} />
      <Metric label="Update" value={preview.update_count} />
      <Metric label="Matched" value={preview.matched_count} />
      <Metric label="Skipped" value={preview.skipped_count} />
      <Metric label="Conflicts" value={preview.conflict_count} />
      <Metric label="Errors" value={preview.error_count} />
    </div>
  );
}

function WooPreviewTable({ rows }) {
  return (
    <TableShell caption={`${rows.length} preview row(s)`} columns={['Action', 'Remote Type', 'Woo Product ID', 'Woo Variation ID', 'SKU', 'Barcode', 'Description', 'Category', 'Brand', 'Price', 'Stock Status', 'Woo Stock Snapshot', 'Local Item ID', 'Warnings', 'Errors']}>
      {rows.map((row) => (
        <tr key={`${row.woo_product_id}-${row.woo_variation_id || 'simple'}-${row.sku}`}>
          <td>{row.action}</td>
          <td>{row.remote_type}</td>
          <td>{row.woo_product_id}</td>
          <td>{row.woo_variation_id}</td>
          <td className="mono">{row.sku}</td>
          <td className="mono">{row.barcode}</td>
          <td className="description-cell">{row.description}</td>
          <td>{row.category}</td>
          <td>{row.brand}</td>
          <td>{formatCurrency(row.price)}</td>
          <td>{row.stock_status}</td>
          <td>{formatNumber(row.stock_quantity_snapshot)}</td>
          <td>{row.local_item_id}</td>
          <td className="description-cell">{(row.warnings || []).join(' ')}</td>
          <td className="description-cell">{(row.errors || []).join(' ')}</td>
        </tr>
      ))}
      {rows.length === 0 && (
        <tr>
          <td colSpan={15}>
            <div className="empty-table-row">No WooCommerce preview rows loaded.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function WooSyncRunsTable({ runs }) {
  return (
    <TableShell caption={`${runs.length} sync run(s)`} columns={['Started At', 'Completed At', 'Sync Type', 'Status', 'Total Records', 'Created', 'Updated', 'Matched', 'Skipped', 'Conflicts', 'Errors', 'Created By']}>
      {runs.map((run) => (
        <tr key={run.id}>
          <td>{formatDateTime(run.started_at)}</td>
          <td>{formatDateTime(run.completed_at)}</td>
          <td>{run.sync_type}</td>
          <td>{run.status}</td>
          <td>{run.total_remote_records}</td>
          <td>{run.created_count}</td>
          <td>{run.updated_count}</td>
          <td>{run.matched_count}</td>
          <td>{run.skipped_count}</td>
          <td>{run.conflict_count}</td>
          <td>{run.error_count}</td>
          <td>{run.created_by}</td>
        </tr>
      ))}
      {runs.length === 0 && (
        <tr>
          <td colSpan={12}>
            <div className="empty-table-row">No WooCommerce sync runs yet.</div>
          </td>
        </tr>
      )}
    </TableShell>
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
  if (route.pageId === 'items') {
    if (route.itemView === 'new') {
      return { title: 'New Item', kicker: 'CSV field entry', tabs: detailTabs };
    }
    if (route.itemView === 'detail') {
      const item = items.find((candidate) => String(candidate.id) === String(route.itemId));
      return { title: item ? `Edit ${item.SKU}` : 'Edit Item', kicker: 'CSV field entry', tabs: detailTabs };
    }
    return pageMeta.items;
  }
  if (route.pageId === 'locations' && route.locationView === 'new') {
    return { title: 'Add Location', kicker: 'Warehouse and bin setup', tabs: pageMeta.locations.tabs };
  }
  if (route.pageId === 'locations' && route.locationView === 'detail') {
    return { title: 'Edit Location', kicker: 'Warehouse and bin setup', tabs: pageMeta.locations.tabs };
  }
  return pageMeta[route.pageId];
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
  if (route.pageId === 'locations' && tab.href) {
    if (tab.href === '#locations') {
      return !route.locationView;
    }
    if (tab.href === '#/locations/new') {
      return route.locationView === 'new';
    }
    if (tab.href === '#/locations/stock') {
      return route.locationView === 'stock';
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

function normalizeLocation(location) {
  return {
    id: null,
    warehouse: '',
    code: '',
    name: '',
    description: '',
    zone: '',
    aisle: '',
    rack: '',
    shelf: '',
    bin: '',
    isDefault: false,
    isActive: true,
    ...location,
  };
}

function emptyReceivingLine() {
  return {
    localId: globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : String(Date.now()),
    query: '',
    inventory_location: '',
    quantity_received: 1,
    unit_cost: '',
    notes: '',
  };
}

function emptyCycleCountLine() {
  return {
    localId: globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : String(Date.now()),
    query: '',
    counted_quantity: '',
    notes: '',
  };
}

function emptyReceivedInventoryFilters() {
  return {
    dateFrom: '',
    dateTo: '',
    warehouse: '',
    inventoryLocation: '',
    sku: '',
    barcode: '',
    category: '',
    brand: '',
    receiptNumber: '',
    referenceNumber: '',
    createdBy: '',
  };
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

function formatDateTime(value) {
  if (!value) {
    return '';
  }
  return new Intl.DateTimeFormat('en-US', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}

function formatCountType(value) {
  return value === 'full_location' ? 'Full Location' : 'Selected Items';
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

async function exportLocationsCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/locations/export${locationsFiltersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder('Unable to export locations CSV from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-locations-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportInventoryByLocationCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/inventory/export/by-location${inventoryFiltersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder('Unable to export inventory by location from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-inventory-by-location-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportReceivedInventoryCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/reports/received-inventory/export${plainFiltersToQueryString(receivedInventoryFiltersToApi(filters))}`);
  if (!response.ok) {
    showPlaceholder('Unable to export received inventory report from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-received-inventory-report.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportCycleCountCsv(cycleCountId, countNumber) {
  const response = await fetch(`${API_BASE_URL}/api/cycle-counts/${cycleCountId}/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export cycle count CSV from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-cycle-count-${countNumber || cycleCountId}.csv`;
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

async function postJson(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = body.detail?.errors?.join(' ') || JSON.stringify(body.detail || body);
    } catch {
      detail = await safeResponseText(response);
    }
    throw new Error(detail || `API returned ${response.status}`);
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

function downloadSampleLocationsCsv() {
  const sampleRows = [
    {
      Warehouse: 'Main Warehouse',
      'Location Code': 'REC-01',
      'Location Name': 'Receiving Bay',
      Description: 'Sample inbound staging area',
      Zone: 'Receiving',
      Aisle: 'A',
      Rack: '01',
      Shelf: '01',
      Bin: '01',
      Default: 'Yes',
      Active: 'Yes',
    },
    {
      Warehouse: 'Main Warehouse',
      'Location Code': 'RACK-A-01',
      'Location Name': 'Rack A 01',
      Description: 'Sample storage rack',
      Zone: 'Dry Storage',
      Aisle: 'A',
      Rack: '01',
      Shelf: '02',
      Bin: '01',
      Default: 'No',
      Active: 'Yes',
    },
  ];
  const header = CANONICAL_LOCATION_COLUMNS.join(',');
  const rows = sampleRows.map((row) => CANONICAL_LOCATION_COLUMNS.map((column) => escapeCsvValue(row[column], column)).join(','));
  const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'sample-locations-import.csv';
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

function locationsFiltersToQueryString(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.warehouse) params.set('warehouse', filters.warehouse);
  if (filters.zone) params.set('zone', filters.zone);
  if (filters.aisle) params.set('aisle', filters.aisle);
  if (filters.status === 'active') params.set('active', 'true');
  if (filters.status === 'inactive') params.set('active', 'false');
  const query = params.toString();
  return query ? `?${query}` : '';
}

function plainFiltersToQueryString(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, value);
    }
  });
  const query = params.toString();
  return query ? `?${query}` : '';
}

function inventoryFiltersToQueryString(filters = {}) {
  const params = new URLSearchParams();
  if (filters.warehouse) params.set('warehouse', filters.warehouse);
  if (filters.inventoryLocation) params.set('inventory_location', filters.inventoryLocation);
  if (filters.defaultLocation) params.set('default_location', filters.defaultLocation);
  if (filters.category) params.set('category', filters.category);
  if (filters.brand) params.set('brand', filters.brand);
  if (filters.underPar) params.set('under_par', filters.underPar);
  const query = params.toString();
  return query ? `?${query}` : '';
}

function receivedInventoryFiltersToApi(filters = {}) {
  return {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    warehouse: filters.warehouse,
    inventory_location: filters.inventoryLocation,
    sku: filters.sku,
    barcode: filters.barcode,
    category: filters.category,
    brand: filters.brand,
    receipt_number: filters.receiptNumber,
    reference_number: filters.referenceNumber,
    created_by: filters.createdBy,
  };
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

function locationToApiPayload(location) {
  return {
    warehouse: location.warehouse,
    code: location.code,
    name: location.name,
    description: location.description || '',
    zone: location.zone || '',
    aisle: location.aisle || '',
    rack: location.rack || '',
    shelf: location.shelf || '',
    bin: location.bin || '',
    isDefault: Boolean(location.isDefault),
    isActive: Boolean(location.isActive),
  };
}

function findReceivingItem(items, query) {
  const normalizedQuery = String(query || '').trim().toLowerCase();
  if (!normalizedQuery) {
    return null;
  }
  return items.find((item) => String(item.SKU || '').toLowerCase() === normalizedQuery || String(item.Barcode || '').toLowerCase() === normalizedQuery) || null;
}

function receivingPayload(form, items) {
  return {
    warehouse: form.warehouse,
    reference_number: form.reference_number,
    notes: form.notes,
    created_by: 'system',
    lines: form.lines.map((line) => {
      const item = findReceivingItem(items, line.query);
      const query = String(line.query || '').trim();
      return {
        item_id: item?.id || null,
        sku: item?.SKU || query || null,
        barcode: item?.Barcode || null,
        inventory_location: line.inventory_location,
        default_location: line.inventory_location,
        quantity_received: toNumber(line.quantity_received),
        unit_cost: line.unit_cost === '' ? null : toNumber(line.unit_cost),
        notes: line.notes,
      };
    }),
  };
}

function cycleCountPayload(form, items) {
  return {
    warehouse: form.warehouse,
    inventory_location: form.inventory_location || null,
    count_type: form.count_type,
    notes: form.notes,
    created_by: 'system',
    lines: form.lines.map((line) => {
      const item = findReceivingItem(items, line.query);
      const query = String(line.query || '').trim();
      return {
        item_id: item?.id || null,
        sku: item?.SKU || query || null,
        barcode: item?.Barcode || null,
        counted_quantity: toNumber(line.counted_quantity),
        notes: line.notes,
      };
    }),
  };
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
