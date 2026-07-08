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
const ITEM_DEFAULT_VISIBLE_COLUMNS = ['SKU / Barcode', 'Description', 'Brand', 'Category', 'In Stock', 'Sellable', 'Unit Cost'];

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
const emptyFulfillmentSummary = {
  total_fulfillments: 0,
  total_orders: 0,
  total_lines: 0,
  total_quantity_fulfilled: 0,
  total_fulfilled_value: 0,
  unique_skus: 0,
  unique_locations: 0,
  date_from: null,
  date_to: null,
  by_warehouse: [],
  by_location: [],
  by_sku: [],
  by_order: [],
};
const emptySkuOrdersSummary = {
  total_skus: 0,
  total_quantity_ordered: 0,
  total_quantity_fulfilled: 0,
  total_unfulfilled_quantity: 0,
  unmatched_lines_count: 0,
  top_sku_by_quantity: null,
};
const emptyDashboard = {
  generated_at: null,
  inventory_health: {},
  order_operations: {},
  routes: {},
  warnings: [],
  activity: [],
};
const emptyCompletedOrders = {
  orders: [],
  total: 0,
};
const emptyWooStatus = {
  configured: false,
  base_url_present: false,
  consumer_key_present: false,
  consumer_secret_present: false,
  message: 'WooCommerce status has not been checked.',
};
const emptyOpenOrders = {
  orders: [],
  total: 0,
  available_count: 0,
  partial_count: 0,
  unavailable_count: 0,
  unknown_count: 0,
};

const orderSubpages = [
  { id: 'open', label: 'Open Orders', href: '#/orders/open' },
  { id: 'allocate', label: 'Allocate Orders', href: '#/orders/allocate' },
  { id: 'pick', label: 'Pick Orders', href: '#/orders/pick' },
  { id: 'fulfillment', label: 'Fulfillment', href: '#/orders/fulfillment' },
  { id: 'completed', label: 'Completed Orders', href: '#/orders/completed' },
  { id: 'history', label: 'Order History', href: '#/orders/history' },
];

const orderSubpageMeta = {
  open: { title: 'Open Orders', kicker: 'Orders / Open' },
  allocate: { title: 'Allocate Orders', kicker: 'Orders / Allocation' },
  pick: { title: 'Pick Orders', kicker: 'Orders / Picking' },
  fulfillment: { title: 'Fulfillment', kicker: 'Orders / Fulfillment' },
  completed: { title: 'Completed Orders', kicker: 'Orders / Completed' },
  history: { title: 'Order History', kicker: 'Orders / History' },
};

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'items', label: 'Items', icon: PackageSearch },
  { id: 'inventory', label: 'Inventory', icon: Boxes },
  { id: 'locations', label: 'Locations', icon: MapPin },
  { id: 'receiving', label: 'Receiving', icon: Truck },
  { id: 'scanner', label: 'Scanner', icon: PackageSearch },
  { id: 'orders', label: 'Orders', icon: ShoppingCart },
  { id: 'cycle-count', label: 'Cycle Count', icon: ClipboardCheck },
  { id: 'reports', label: 'Reports', icon: BarChart3 },
  { id: 'routes', label: 'Routes', icon: Route },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const pageMeta = {
  dashboard: {
    title: 'Command Center',
    kicker: 'Operational snapshot',
    tabs: ['Today', 'Work Queues', 'Exceptions'],
  },
  items: {
    title: 'Items',
    kicker: 'Item master',
    tabs: [
      { label: 'New Item', href: '#/items/new' },
      { label: 'All Items', href: '#items' },
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
  scanner: {
    title: 'Scanner',
    kicker: 'Warehouse keyboard-scanner workflows',
    tabs: ['Lookup', 'Receiving', 'Cycle Count', 'Transfer', 'Adjustment', 'Picking'],
  },
  orders: {
    title: 'Orders',
    kicker: 'Order workflow',
    tabs: [],
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

const detailTabs = [];

function submitSearchOnEnter(event, submit) {
  if (event.key !== 'Enter') {
    return;
  }
  event.preventDefault();
  submit();
}

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
  if (hash === 'orders') {
    return { pageId: 'orders', ordersView: 'open' };
  }
  if (hash.startsWith('orders/')) {
    const ordersView = hash.split('/')[1] || 'open';
    const knownView = orderSubpages.some((page) => page.id === ordersView);
    return { pageId: 'orders', ordersView: knownView ? ordersView : 'open' };
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
  const [fulfillmentReportRows, setFulfillmentReportRows] = useState([]);
  const [fulfillmentReportSummary, setFulfillmentReportSummary] = useState(emptyFulfillmentSummary);
  const [fulfillmentReportLoading, setFulfillmentReportLoading] = useState(false);
  const [fulfillmentReportError, setFulfillmentReportError] = useState('');
  const [skuOrdersRows, setSkuOrdersRows] = useState([]);
  const [skuOrdersSummary, setSkuOrdersSummary] = useState(emptySkuOrdersSummary);
  const [skuOrdersLoading, setSkuOrdersLoading] = useState(false);
  const [skuOrdersError, setSkuOrdersError] = useState('');
  const [dashboard, setDashboard] = useState(emptyDashboard);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [dashboardError, setDashboardError] = useState('');
  const [cycleCounts, setCycleCounts] = useState([]);
  const [cycleCountsLoading, setCycleCountsLoading] = useState(false);
  const [cycleCountsError, setCycleCountsError] = useState('');
  const [wooStatus, setWooStatus] = useState(emptyWooStatus);
  const [wooPreview, setWooPreview] = useState(null);
  const [wooCommitSummary, setWooCommitSummary] = useState(null);
  const [wooOrderPreview, setWooOrderPreview] = useState(null);
  const [wooOrderCommitSummary, setWooOrderCommitSummary] = useState(null);
  const [wooSyncRuns, setWooSyncRuns] = useState([]);
  const [wooRemapCandidates, setWooRemapCandidates] = useState({ candidates: [], total: 0 });
  const [wooRemapMappings, setWooRemapMappings] = useState({ mappings: [], total: 0 });
  const [wooRemapPreview, setWooRemapPreview] = useState(null);
  const [wooRemapMessage, setWooRemapMessage] = useState('');
  const [wooLoading, setWooLoading] = useState(false);
  const [wooError, setWooError] = useState('');
  const [openOrders, setOpenOrders] = useState(emptyOpenOrders);
  const [openOrdersLoading, setOpenOrdersLoading] = useState(false);
  const [openOrdersError, setOpenOrdersError] = useState('');
  const [openOrderDetail, setOpenOrderDetail] = useState(null);
  const [completedOrders, setCompletedOrders] = useState(emptyCompletedOrders);
  const [completedOrdersLoading, setCompletedOrdersLoading] = useState(false);
  const [completedOrdersError, setCompletedOrdersError] = useState('');
  const [allocationPreview, setAllocationPreview] = useState(null);
  const [allocationCommitSummary, setAllocationCommitSummary] = useState(null);
  const [allocationHistory, setAllocationHistory] = useState([]);
  const [allocationDetail, setAllocationDetail] = useState(null);
  const [allocationLoading, setAllocationLoading] = useState(false);
  const [allocationError, setAllocationError] = useState('');
  const [pickPreview, setPickPreview] = useState(null);
  const [pickCommitSummary, setPickCommitSummary] = useState(null);
  const [pickHistory, setPickHistory] = useState([]);
  const [pickDetail, setPickDetail] = useState(null);
  const [pickScannerOrder, setPickScannerOrder] = useState(null);
  const [pickScannerMessage, setPickScannerMessage] = useState('');
  const [pickLoading, setPickLoading] = useState(false);
  const [pickError, setPickError] = useState('');
  const [fulfillmentPreview, setFulfillmentPreview] = useState(null);
  const [fulfillmentCommitSummary, setFulfillmentCommitSummary] = useState(null);
  const [fulfillmentHistory, setFulfillmentHistory] = useState([]);
  const [fulfillmentDetail, setFulfillmentDetail] = useState(null);
  const [fulfillmentLoading, setFulfillmentLoading] = useState(false);
  const [fulfillmentError, setFulfillmentError] = useState('');
  const [routeCandidates, setRouteCandidates] = useState({ total_candidates: 0, candidates: [] });
  const [routeCandidatesLoading, setRouteCandidatesLoading] = useState(false);
  const [routeCandidatesError, setRouteCandidatesError] = useState('');
  const [routePreview, setRoutePreview] = useState(null);
  const [routeCommitSummary, setRouteCommitSummary] = useState(null);
  const [routesHistory, setRoutesHistory] = useState({ routes: [], total: 0 });
  const [routeDetail, setRouteDetail] = useState(null);
  const [routeMapPayload, setRouteMapPayload] = useState(null);
  const [routeProviderMessage, setRouteProviderMessage] = useState('');
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState('');

  useEffect(() => {
    const handleHashChange = () => setRoute(parseHashRoute());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (route.pageId === 'dashboard') {
      loadDashboard();
    }
    if (route.pageId === 'items' || route.pageId === 'inventory') {
      loadItems();
    }
    if (route.pageId === 'receiving') {
      loadItems();
      loadLocations({ status: 'active' });
      loadReceipts();
      loadStockMovements({ movement_type: 'receive_direct' });
    }
    if (route.pageId === 'scanner') {
      loadItems();
      loadLocations({ status: 'active' });
    }
    if (route.pageId === 'locations') {
      loadLocations();
    }
    if (route.pageId === 'reports') {
      loadReceivedInventoryReport();
      loadFulfillmentReport();
      loadSkuOrdersReport();
    }
    if (route.pageId === 'cycle-count') {
      loadItems();
      loadLocations({ status: 'active' });
      loadCycleCounts();
    }
    if (route.pageId === 'orders') {
      loadOpenOrders();
      loadAllocations();
      loadPicks();
      loadFulfillments();
      loadCompletedOrders();
    }
    if (route.pageId === 'settings') {
      loadWooStatus();
      loadWooSyncRuns();
      loadWooRemap();
    }
    if (route.pageId === 'routes') {
      loadRouteCandidates();
      loadRoutes();
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

  async function loadFulfillmentReport(filters = {}) {
    setFulfillmentReportLoading(true);
    setFulfillmentReportError('');
    try {
      const queryString = plainFiltersToQueryString(fulfillmentReportFiltersToApi(filters));
      const [rowsResponse, summaryResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/reports/fulfillments${queryString}`),
        fetch(`${API_BASE_URL}/api/reports/fulfillments/summary${queryString}`),
      ]);
      if (!rowsResponse.ok || !summaryResponse.ok) {
        throw new Error('Fulfillment report API returned an error.');
      }
      setFulfillmentReportRows(await rowsResponse.json());
      setFulfillmentReportSummary(await summaryResponse.json());
    } catch (error) {
      setFulfillmentReportError('Unable to load fulfillment report from the backend.');
    } finally {
      setFulfillmentReportLoading(false);
    }
  }

  async function loadSkuOrdersReport(filters = {}) {
    setSkuOrdersLoading(true);
    setSkuOrdersError('');
    try {
      const queryString = plainFiltersToQueryString(skuOrdersFiltersToApi(filters));
      const [rowsResponse, summaryResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/reports/sku-orders${queryString}`),
        fetch(`${API_BASE_URL}/api/reports/sku-orders/summary${queryString}`),
      ]);
      if (!rowsResponse.ok || !summaryResponse.ok) {
        throw new Error('SKU Orders report API returned an error.');
      }
      setSkuOrdersRows(await rowsResponse.json());
      setSkuOrdersSummary(await summaryResponse.json());
    } catch (error) {
      setSkuOrdersError('Unable to load SKU Orders report from the backend.');
    } finally {
      setSkuOrdersLoading(false);
    }
  }

  async function loadDashboard() {
    setDashboardLoading(true);
    setDashboardError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/dashboard?limit=30`);
      if (!response.ok) {
        throw new Error(`Dashboard API returned ${response.status}`);
      }
      setDashboard({ ...emptyDashboard, ...(await response.json()) });
    } catch (error) {
      setDashboardError('Unable to load Command Center data from the backend.');
    } finally {
      setDashboardLoading(false);
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

  async function loadWooRemap() {
    setWooError('');
    try {
      const [candidatesResponse, mappingsResponse] = await Promise.all([
        fetch(`${API_BASE_URL}/api/integrations/woocommerce/remap/candidates`),
        fetch(`${API_BASE_URL}/api/integrations/woocommerce/remap/mappings`),
      ]);
      if (!candidatesResponse.ok || !mappingsResponse.ok) {
        throw new Error('Remap API returned an error.');
      }
      setWooRemapCandidates(await candidatesResponse.json());
      setWooRemapMappings(await mappingsResponse.json());
    } catch (error) {
      setWooError('Unable to load WooCommerce remap data.');
    }
  }

  async function loadOpenOrders(filters = {}) {
    setOpenOrdersLoading(true);
    setOpenOrdersError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/orders/open${plainFiltersToQueryString(openOrderFiltersToApi(filters))}`);
      if (!response.ok) {
        throw new Error(`Open Orders API returned ${response.status}`);
      }
      const body = await response.json();
      setOpenOrders({ ...emptyOpenOrders, ...body });
      if (body.orders?.length) {
        await loadOpenOrderDetail(body.orders[0].id);
      } else {
        setOpenOrderDetail(null);
      }
    } catch (error) {
      setOpenOrdersError('Unable to load open orders from the backend.');
    } finally {
      setOpenOrdersLoading(false);
    }
  }

  async function loadCompletedOrders(filters = {}) {
    setCompletedOrdersLoading(true);
    setCompletedOrdersError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/orders/completed${plainFiltersToQueryString(completedOrderFiltersToApi(filters))}`);
      if (!response.ok) {
        throw new Error(`Completed Orders API returned ${response.status}`);
      }
      const body = await response.json();
      setCompletedOrders({ ...emptyCompletedOrders, ...body });
    } catch (error) {
      setCompletedOrdersError('Unable to load completed orders from the backend.');
    } finally {
      setCompletedOrdersLoading(false);
    }
  }

  async function loadOpenOrderDetail(orderId) {
    if (!orderId) {
      setOpenOrderDetail(null);
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/orders/${orderId}`);
      if (!response.ok) {
        throw new Error(`Order detail API returned ${response.status}`);
      }
      setOpenOrderDetail(await response.json());
    } catch (error) {
      setOpenOrdersError('Unable to load order detail from the backend.');
    }
  }

  async function loadAllocations(filters = {}) {
    setAllocationError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/allocations${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Allocations API returned ${response.status}`);
      }
      const body = await response.json();
      setAllocationHistory(body.allocations || []);
    } catch (error) {
      setAllocationError('Unable to load allocation history from the backend.');
    }
  }

  async function loadAllocationDetail(allocationId) {
    if (!allocationId) {
      setAllocationDetail(null);
      return;
    }
    setAllocationError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/allocations/${allocationId}`);
      if (!response.ok) {
        throw new Error(`Allocation detail API returned ${response.status}`);
      }
      setAllocationDetail(await response.json());
    } catch (error) {
      setAllocationError('Unable to load allocation detail from the backend.');
    }
  }

  async function loadPicks(filters = {}) {
    setPickError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/picks${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Picks API returned ${response.status}`);
      }
      const body = await response.json();
      setPickHistory(body.picks || []);
    } catch (error) {
      setPickError('Unable to load pick history from the backend.');
    }
  }

  async function loadFulfillments(filters = {}) {
    setFulfillmentError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/fulfillments${plainFiltersToQueryString(filters)}`);
      if (!response.ok) {
        throw new Error(`Fulfillments API returned ${response.status}`);
      }
      const body = await response.json();
      setFulfillmentHistory(body.fulfillments || []);
    } catch (error) {
      setFulfillmentError('Unable to load fulfillment history from the backend.');
    }
  }

  async function loadFulfillmentDetail(fulfillmentId) {
    if (!fulfillmentId) {
      setFulfillmentDetail(null);
      return;
    }
    setFulfillmentError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/fulfillments/${fulfillmentId}`);
      if (!response.ok) {
        throw new Error(`Fulfillment detail API returned ${response.status}`);
      }
      setFulfillmentDetail(await response.json());
    } catch (error) {
      setFulfillmentError('Unable to load fulfillment detail from the backend.');
    }
  }

  async function loadRouteCandidates(filters = {}) {
    setRouteCandidatesLoading(true);
    setRouteCandidatesError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/routes/candidates${plainFiltersToQueryString(routeCandidateFiltersToApi(filters))}`);
      if (!response.ok) {
        throw new Error(`Route candidates API returned ${response.status}`);
      }
      const body = await response.json();
      setRouteCandidates({ total_candidates: body.total_candidates || 0, candidates: body.candidates || [] });
    } catch (error) {
      setRouteCandidatesError('Unable to load route candidates from the backend.');
    } finally {
      setRouteCandidatesLoading(false);
    }
  }

  async function loadRoutes(filters = {}) {
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/routes${plainFiltersToQueryString(routeFiltersToApi(filters))}`);
      if (!response.ok) {
        throw new Error(`Routes API returned ${response.status}`);
      }
      const body = await response.json();
      setRoutesHistory({ routes: body.routes || [], total: body.total || 0 });
      if (!body.routes?.length) {
        setRouteDetail(null);
      }
    } catch (error) {
      setRoutesError('Unable to load routes from the backend.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function loadRouteDetail(routeId) {
    if (!routeId) {
      setRouteDetail(null);
      return;
    }
    setRoutesError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/routes/${routeId}`);
      if (!response.ok) {
        throw new Error(`Route detail API returned ${response.status}`);
      }
      const detail = await response.json();
      setRouteDetail(detail);
      await loadRouteMap(routeId);
    } catch (error) {
      setRoutesError('Unable to load route detail from the backend.');
    }
  }

  async function loadRouteMap(routeId) {
    if (!routeId) {
      setRouteMapPayload(null);
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/routes/${routeId}/map`);
      if (response.ok) {
        setRouteMapPayload(await response.json());
      }
    } catch {
      setRouteMapPayload(null);
    }
  }

  async function previewRoute(payload) {
    setRoutesLoading(true);
    setRoutesError('');
    setRouteCommitSummary(null);
    try {
      setRoutePreview(await postJson('/api/routes/preview', payload));
    } catch (error) {
      setRoutesError(error.message || 'Unable to preview route.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function commitRoute(payload) {
    const confirmed = window.confirm('This creates a local draft route only. It does not update WooCommerce, maps, shipping labels, order status, or inventory quantities.');
    if (!confirmed) {
      return;
    }
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const result = await postJson('/api/routes/commit', payload);
      setRouteCommitSummary(result);
      if (result.route_id) {
        await loadRouteDetail(result.route_id);
      }
      await loadRouteCandidates();
      await loadRoutes();
    } catch (error) {
      setRoutesError(error.message || 'Unable to create route.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function finalizeRoute(routeId) {
    const confirmed = window.confirm('Finalize marks the local route finalized. It does not notify customers, update WooCommerce, or perform delivery tracking.');
    if (!confirmed) {
      return;
    }
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const result = await postJson(`/api/routes/${routeId}/finalize`, {});
      setRouteCommitSummary(result);
      await loadRoutes();
      await loadRouteDetail(routeId);
    } catch (error) {
      setRoutesError(error.message || 'Unable to finalize route.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function cancelRoute(routeId) {
    const confirmed = window.confirm('Cancel releases these orders for future local route planning. It does not modify inventory, WooCommerce, labels, or notifications.');
    if (!confirmed) {
      return;
    }
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const result = await postJson(`/api/routes/${routeId}/cancel`, {});
      setRouteCommitSummary(result);
      await loadRouteCandidates();
      await loadRoutes();
      await loadRouteDetail(routeId);
    } catch (error) {
      setRoutesError(error.message || 'Unable to cancel route.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function saveRouteMetadata(routeId, payload) {
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const response = await patchJson(`/api/routes/${routeId}`, payload);
      setRouteDetail(response);
      await loadRoutes();
    } catch (error) {
      setRoutesError(error.message || 'Unable to save route metadata.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function reorderRouteStops(routeId, orderedStopIds) {
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const response = await postJson(`/api/routes/${routeId}/stops/reorder`, { ordered_stop_ids: orderedStopIds });
      setRouteDetail(response);
      await loadRouteMap(routeId);
    } catch (error) {
      setRoutesError(error.message || 'Unable to reorder route stops.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function saveRouteStop(routeId, stopId, payload) {
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const response = await patchJson(`/api/routes/${routeId}/stops/${stopId}`, payload);
      setRouteDetail(response);
      await loadRouteMap(routeId);
    } catch (error) {
      setRoutesError(error.message || 'Unable to save route stop.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function routeProviderAction(routeId, action) {
    setRoutesLoading(true);
    setRouteProviderMessage('');
    setRoutesError('');
    try {
      const result = await postJson(`/api/routes/${routeId}/${action}`, {});
      setRouteProviderMessage(result.message || result.status);
      await loadRouteMap(routeId);
    } catch (error) {
      setRoutesError(error.message || 'Unable to run route provider action.');
    } finally {
      setRoutesLoading(false);
    }
  }

  async function loadPickDetail(pickId) {
    if (!pickId) {
      setPickDetail(null);
      return;
    }
    setPickError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/picks/${pickId}`);
      if (!response.ok) {
        throw new Error(`Pick detail API returned ${response.status}`);
      }
      setPickDetail(await response.json());
    } catch (error) {
      setPickError('Unable to load pick detail from the backend.');
    }
  }

  async function loadPickScanner(orderId) {
    if (!orderId) {
      setPickScannerOrder(null);
      return;
    }
    setPickError('');
    try {
      const response = await fetch(`${API_BASE_URL}/api/picks/orders/${orderId}/scanner`);
      if (!response.ok) {
        throw new Error(`Pick scanner API returned ${response.status}`);
      }
      setPickScannerOrder(await response.json());
    } catch (error) {
      setPickError('Unable to load scanner view for this order.');
    }
  }

  async function commitPickScan(orderId, skuOrBarcode, quantity) {
    if (!orderId) {
      setPickError('Select an order before scanning.');
      return;
    }
    setPickLoading(true);
    setPickScannerMessage('');
    setPickError('');
    try {
      const result = await postJson(`/api/picks/orders/${orderId}/scan/commit`, { sku_or_barcode: skuOrBarcode, quantity: toNumber(quantity) || 1, created_by: 'system', note: 'Scanner pick' });
      setPickScannerMessage(result.errors?.length ? result.errors.join(' ') : `Scan ${result.status}.`);
      await loadPickScanner(orderId);
      await loadOpenOrderDetail(orderId);
      await loadPicks();
    } catch (error) {
      setPickError(error.message || 'Unable to commit scan.');
    } finally {
      setPickLoading(false);
    }
  }

  async function previewPick(orderId) {
    if (!orderId) {
      setPickError('Select an allocated order before previewing picking.');
      return;
    }
    setPickLoading(true);
    setPickError('');
    setPickCommitSummary(null);
    try {
      setPickPreview(await postJson('/api/picks/preview', { order_ids: [orderId], pick_strategy: 'allocated_first', allow_partial: true, created_by: 'system' }));
    } catch (error) {
      setPickError(error.message || 'Unable to preview picking.');
    } finally {
      setPickLoading(false);
    }
  }

  async function commitPick(orderId) {
    if (!orderId) {
      setPickError('Select an allocated order before committing a pick.');
      return;
    }
    const confirmed = window.confirm('Picking only records operational progress against allocated quantities. It does not update WooCommerce, reduce In Stock, reduce Allocated, or fulfill the order.');
    if (!confirmed) {
      return;
    }
    setPickLoading(true);
    setPickError('');
    try {
      const result = await postJson('/api/picks/commit', { order_ids: [orderId], pick_strategy: 'allocated_first', allow_partial: true, created_by: 'system', notes: 'Picked from Open Orders' });
      setPickCommitSummary(result);
      await loadOpenOrders();
      await loadOpenOrderDetail(orderId);
      await loadPicks();
    } catch (error) {
      setPickError(error.message || 'Unable to commit pick.');
    } finally {
      setPickLoading(false);
    }
  }

  async function previewFulfillment(orderId) {
    if (!orderId) {
      setFulfillmentError('Select a picked order before previewing fulfillment.');
      return;
    }
    setFulfillmentLoading(true);
    setFulfillmentError('');
    setFulfillmentCommitSummary(null);
    try {
      setFulfillmentPreview(await postJson('/api/fulfillments/preview', { order_ids: [orderId], fulfillment_strategy: 'picked_first', allow_partial: true, created_by: 'system' }));
    } catch (error) {
      setFulfillmentError(error.message || 'Unable to preview fulfillment.');
    } finally {
      setFulfillmentLoading(false);
    }
  }

  async function commitFulfillment(orderId) {
    if (!orderId) {
      setFulfillmentError('Select a picked order before committing fulfillment.');
      return;
    }
    const confirmed = window.confirm('Fulfillment reduces local Pongo OS In Stock and Allocated quantities. It does not update WooCommerce order status, WooCommerce stock, routes, shipping labels, or notifications.');
    if (!confirmed) {
      return;
    }
    setFulfillmentLoading(true);
    setFulfillmentError('');
    try {
      const result = await postJson('/api/fulfillments/commit', { order_ids: [orderId], fulfillment_strategy: 'picked_first', allow_partial: true, created_by: 'system', notes: 'Fulfilled from Open Orders' });
      setFulfillmentCommitSummary(result);
      await loadOpenOrders();
      await loadOpenOrderDetail(orderId);
      await loadFulfillments();
      await loadItems();
      await loadInventorySummary();
    } catch (error) {
      setFulfillmentError(error.message || 'Unable to commit fulfillment.');
    } finally {
      setFulfillmentLoading(false);
    }
  }

  async function previewAllocation(orderId) {
    if (!orderId) {
      setAllocationError('Select an open order before previewing allocation.');
      return;
    }
    setAllocationLoading(true);
    setAllocationError('');
    setAllocationCommitSummary(null);
    try {
      setAllocationPreview(await postJson('/api/allocations/preview', { order_ids: [orderId], allocation_strategy: 'available_first', allow_partial: true, created_by: 'system' }));
    } catch (error) {
      setAllocationError(error.message || 'Unable to preview allocation.');
    } finally {
      setAllocationLoading(false);
    }
  }

  async function commitAllocation(orderId) {
    if (!orderId) {
      setAllocationError('Select an open order before committing allocation.');
      return;
    }
    const confirmed = window.confirm('Allocation only reserves local Pongo OS inventory. It does not update WooCommerce, does not reduce In Stock, and does not pick the order.');
    if (!confirmed) {
      return;
    }
    setAllocationLoading(true);
    setAllocationError('');
    try {
      const result = await postJson('/api/allocations/commit', { order_ids: [orderId], allocation_strategy: 'available_first', allow_partial: true, created_by: 'system', notes: 'Allocated from Open Orders' });
      setAllocationCommitSummary(result);
      await loadOpenOrders();
      await loadOpenOrderDetail(orderId);
      await loadAllocations();
      await loadItems();
      await loadInventorySummary();
    } catch (error) {
      setAllocationError(error.message || 'Unable to commit allocation.');
    } finally {
      setAllocationLoading(false);
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

  async function previewWooOrderSync() {
    setWooLoading(true);
    setWooError('');
    setWooOrderCommitSummary(null);
    try {
      setWooOrderPreview(await postJson('/api/integrations/woocommerce/orders/preview', { include_statuses: ['processing', 'on-hold'], limit: 500, created_by: 'system' }));
    } catch (error) {
      setWooError(error.message || 'Unable to preview WooCommerce order sync.');
    } finally {
      setWooLoading(false);
    }
  }

  async function commitWooOrderSync() {
    const confirmed = window.confirm('This imports WooCommerce orders into local Pongo OS only. It does not allocate stock, pick orders, update statuses, or write back to WooCommerce.');
    if (!confirmed) {
      return;
    }
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/orders/commit', { include_statuses: ['processing', 'on-hold'], limit: 500, created_by: 'system' });
      setWooOrderCommitSummary(result);
      await loadWooSyncRuns();
      await loadOpenOrders();
    } catch (error) {
      setWooError(error.message || 'Unable to commit WooCommerce order sync.');
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

  async function previewWooRemap(payload) {
    setWooLoading(true);
    setWooError('');
    setWooRemapMessage('');
    try {
      setWooRemapPreview(await postJson('/api/integrations/woocommerce/remap/preview', payload));
    } catch (error) {
      setWooError(error.message || 'Unable to preview remap.');
    } finally {
      setWooLoading(false);
    }
  }

  async function commitWooRemap(payload) {
    const confirmed = window.confirm('This only changes local WooCommerce mapping metadata. It does not update WooCommerce or inventory quantities.');
    if (!confirmed) {
      return;
    }
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/remap/commit', payload);
      setWooRemapMessage(result.safe_message || `Mapping ${result.status}.`);
      setWooRemapPreview(null);
      await loadWooRemap();
      await loadItems();
    } catch (error) {
      setWooError(error.message || 'Unable to commit remap.');
    } finally {
      setWooLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activePage={route.pageId} route={route} onNavigate={(pageId) => setRoute({ pageId })} />
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
            fulfillmentReportRows={fulfillmentReportRows}
            fulfillmentReportSummary={fulfillmentReportSummary}
            fulfillmentReportLoading={fulfillmentReportLoading}
            fulfillmentReportError={fulfillmentReportError}
            onLoadFulfillmentReport={loadFulfillmentReport}
            skuOrdersRows={skuOrdersRows}
            skuOrdersSummary={skuOrdersSummary}
            skuOrdersLoading={skuOrdersLoading}
            skuOrdersError={skuOrdersError}
            onLoadSkuOrdersReport={loadSkuOrdersReport}
            dashboard={dashboard}
            dashboardLoading={dashboardLoading}
            dashboardError={dashboardError}
            onLoadDashboard={loadDashboard}
            cycleCounts={cycleCounts}
            cycleCountsLoading={cycleCountsLoading}
            cycleCountsError={cycleCountsError}
            onLoadCycleCounts={loadCycleCounts}
            wooStatus={wooStatus}
            wooPreview={wooPreview}
            wooCommitSummary={wooCommitSummary}
            wooOrderPreview={wooOrderPreview}
            wooOrderCommitSummary={wooOrderCommitSummary}
            wooSyncRuns={wooSyncRuns}
            wooRemapCandidates={wooRemapCandidates}
            wooRemapMappings={wooRemapMappings}
            wooRemapPreview={wooRemapPreview}
            wooRemapMessage={wooRemapMessage}
            wooLoading={wooLoading}
            wooError={wooError}
            onLoadWooStatus={loadWooStatus}
            onPreviewWooProductSync={previewWooProductSync}
            onCommitWooProductSync={commitWooProductSync}
            onPreviewWooOrderSync={previewWooOrderSync}
            onCommitWooOrderSync={commitWooOrderSync}
            onPreviewWooRemap={previewWooRemap}
            onCommitWooRemap={commitWooRemap}
            onLoadWooRemap={loadWooRemap}
            openOrders={openOrders}
            openOrdersLoading={openOrdersLoading}
            openOrdersError={openOrdersError}
            openOrderDetail={openOrderDetail}
            onLoadOpenOrders={loadOpenOrders}
            onLoadOpenOrderDetail={loadOpenOrderDetail}
            completedOrders={completedOrders}
            completedOrdersLoading={completedOrdersLoading}
            completedOrdersError={completedOrdersError}
            onLoadCompletedOrders={loadCompletedOrders}
            allocationPreview={allocationPreview}
            allocationCommitSummary={allocationCommitSummary}
            allocationHistory={allocationHistory}
            allocationDetail={allocationDetail}
            allocationLoading={allocationLoading}
            allocationError={allocationError}
            onPreviewAllocation={previewAllocation}
            onCommitAllocation={commitAllocation}
            onLoadAllocationDetail={loadAllocationDetail}
            pickPreview={pickPreview}
            pickCommitSummary={pickCommitSummary}
            pickHistory={pickHistory}
            pickDetail={pickDetail}
            pickScannerOrder={pickScannerOrder}
            pickScannerMessage={pickScannerMessage}
            pickLoading={pickLoading}
            pickError={pickError}
            onPreviewPick={previewPick}
            onCommitPick={commitPick}
            onLoadPickDetail={loadPickDetail}
            onLoadPickScanner={loadPickScanner}
            onCommitPickScan={commitPickScan}
            fulfillmentPreview={fulfillmentPreview}
            fulfillmentCommitSummary={fulfillmentCommitSummary}
            fulfillmentHistory={fulfillmentHistory}
            fulfillmentDetail={fulfillmentDetail}
            fulfillmentLoading={fulfillmentLoading}
            fulfillmentError={fulfillmentError}
            onPreviewFulfillment={previewFulfillment}
            onCommitFulfillment={commitFulfillment}
            onLoadFulfillmentDetail={loadFulfillmentDetail}
            routeCandidates={routeCandidates}
            routeCandidatesLoading={routeCandidatesLoading}
            routeCandidatesError={routeCandidatesError}
            routePreview={routePreview}
            routeCommitSummary={routeCommitSummary}
            routesHistory={routesHistory}
            routeDetail={routeDetail}
            routeMapPayload={routeMapPayload}
            routeProviderMessage={routeProviderMessage}
            routesLoading={routesLoading}
            routesError={routesError}
            onLoadRouteCandidates={loadRouteCandidates}
            onPreviewRoute={previewRoute}
            onCommitRoute={commitRoute}
            onLoadRoutes={loadRoutes}
            onLoadRouteDetail={loadRouteDetail}
            onFinalizeRoute={finalizeRoute}
            onCancelRoute={cancelRoute}
            onSaveRouteMetadata={saveRouteMetadata}
            onReorderRouteStops={reorderRouteStops}
            onSaveRouteStop={saveRouteStop}
            onRouteProviderAction={routeProviderAction}
          />
        </main>
      </div>
    </div>
  );
}

function Sidebar({ activePage, route, onNavigate }) {
  const [ordersExpanded, setOrdersExpanded] = useState(activePage === 'orders');

  useEffect(() => {
    if (activePage === 'orders') {
      setOrdersExpanded(true);
    }
  }, [activePage]);

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
      <nav className="nav-list" aria-label="Main navigation">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = item.id === activePage;
          if (item.id === 'orders') {
            return (
              <div className="nav-group" key={item.id}>
                <button className={`nav-link nav-parent ${isActive ? 'active' : ''}`} aria-expanded={ordersExpanded} onClick={() => setOrdersExpanded((current) => !current)} type="button">
                  <Icon size={24} strokeWidth={1.8} />
                  <span>{item.label}</span>
                  <ChevronDown className="nav-caret" size={17} aria-hidden="true" />
                </button>
                {ordersExpanded && (
                  <div className="subnav-list" aria-label="Orders sub-navigation">
                    {orderSubpages.map((subpage) => {
                      const childActive = activePage === 'orders' && (route.ordersView || 'open') === subpage.id;
                      return (
                        <a className={`subnav-link ${childActive ? 'active' : ''}`} href={subpage.href} key={subpage.id} onClick={() => onNavigate('orders')}>
                          {subpage.label}
                        </a>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          }
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
        <Menu size={23} aria-hidden="true" />
        <span>Main Warehouse</span>
        <ChevronDown size={18} />
      </div>
      <div className="header-actions">
        <div className="user-chip" aria-label="Signed in user">
          <div className="avatar">
            <UserCircle size={26} />
          </div>
          <span>Kannan</span>
        </div>
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
            <span className={`${className} is-static`} key={tabObject.label} role="tab" aria-selected={isActive}>
              {tabObject.label}
            </span>
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
  fulfillmentReportRows,
  fulfillmentReportSummary,
  fulfillmentReportLoading,
  fulfillmentReportError,
  onLoadFulfillmentReport,
  skuOrdersRows,
  skuOrdersSummary,
  skuOrdersLoading,
  skuOrdersError,
  onLoadSkuOrdersReport,
  dashboard,
  dashboardLoading,
  dashboardError,
  onLoadDashboard,
  cycleCounts,
  cycleCountsLoading,
  cycleCountsError,
  onLoadCycleCounts,
  wooStatus,
  wooPreview,
  wooCommitSummary,
  wooOrderPreview,
  wooOrderCommitSummary,
  wooSyncRuns,
  wooRemapCandidates,
  wooRemapMappings,
  wooRemapPreview,
  wooRemapMessage,
  wooLoading,
  wooError,
  onLoadWooStatus,
  onPreviewWooProductSync,
  onCommitWooProductSync,
  onPreviewWooOrderSync,
  onCommitWooOrderSync,
  onPreviewWooRemap,
  onCommitWooRemap,
  onLoadWooRemap,
  openOrders,
  openOrdersLoading,
  openOrdersError,
  openOrderDetail,
  onLoadOpenOrders,
  onLoadOpenOrderDetail,
  completedOrders,
  completedOrdersLoading,
  completedOrdersError,
  onLoadCompletedOrders,
  allocationPreview,
  allocationCommitSummary,
  allocationHistory,
  allocationDetail,
  allocationLoading,
  allocationError,
  onPreviewAllocation,
  onCommitAllocation,
  onLoadAllocationDetail,
  pickPreview,
  pickCommitSummary,
  pickHistory,
  pickDetail,
  pickScannerOrder,
  pickScannerMessage,
  pickLoading,
  pickError,
  onPreviewPick,
  onCommitPick,
  onLoadPickDetail,
  onLoadPickScanner,
  onCommitPickScan,
  fulfillmentPreview,
  fulfillmentCommitSummary,
  fulfillmentHistory,
  fulfillmentDetail,
  fulfillmentLoading,
  fulfillmentError,
  onPreviewFulfillment,
  onCommitFulfillment,
  onLoadFulfillmentDetail,
  routeCandidates,
  routeCandidatesLoading,
  routeCandidatesError,
  routePreview,
  routeCommitSummary,
  routesHistory,
  routeDetail,
  routeMapPayload,
  routeProviderMessage,
  routesLoading,
  routesError,
  onLoadRouteCandidates,
  onPreviewRoute,
  onCommitRoute,
  onLoadRoutes,
  onLoadRouteDetail,
  onFinalizeRoute,
  onCancelRoute,
  onSaveRouteMetadata,
  onReorderRouteStops,
  onSaveRouteStop,
  onRouteProviderAction,
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

  if (route.pageId === 'scanner') {
    return <ScannerWorkflowsPage locations={locations} onLoadItems={onLoadItems} onLoadInventorySummary={onLoadInventorySummary} />;
  }

  if (route.pageId === 'reports') {
    return (
      <ReportsPage
        receivedRows={receivedInventoryRows}
        receivedSummary={receivedInventorySummary}
        receivedLoading={receivedInventoryLoading}
        receivedError={receivedInventoryError}
        onLoadReceivedReport={onLoadReceivedInventoryReport}
        fulfillmentRows={fulfillmentReportRows}
        fulfillmentSummary={fulfillmentReportSummary}
        fulfillmentLoading={fulfillmentReportLoading}
        fulfillmentError={fulfillmentReportError}
        onLoadFulfillmentReport={onLoadFulfillmentReport}
        skuOrdersRows={skuOrdersRows}
        skuOrdersSummary={skuOrdersSummary}
        skuOrdersLoading={skuOrdersLoading}
        skuOrdersError={skuOrdersError}
        onLoadSkuOrdersReport={onLoadSkuOrdersReport}
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

  if (route.pageId === 'orders') {
    return (
      <OrdersPage
        route={route}
        ordersData={openOrders}
        loading={openOrdersLoading}
        error={openOrdersError}
        detail={openOrderDetail}
        onLoadOpenOrders={onLoadOpenOrders}
        onLoadOpenOrderDetail={onLoadOpenOrderDetail}
        completedOrders={completedOrders}
        completedOrdersLoading={completedOrdersLoading}
        completedOrdersError={completedOrdersError}
        onLoadCompletedOrders={onLoadCompletedOrders}
        allocationPreview={allocationPreview}
        allocationCommitSummary={allocationCommitSummary}
        allocationHistory={allocationHistory}
        allocationDetail={allocationDetail}
        allocationLoading={allocationLoading}
        allocationError={allocationError}
        onPreviewAllocation={onPreviewAllocation}
        onCommitAllocation={onCommitAllocation}
        onLoadAllocationDetail={onLoadAllocationDetail}
        pickPreview={pickPreview}
        pickCommitSummary={pickCommitSummary}
        pickHistory={pickHistory}
        pickDetail={pickDetail}
        pickScannerOrder={pickScannerOrder}
        pickScannerMessage={pickScannerMessage}
        pickLoading={pickLoading}
        pickError={pickError}
        onPreviewPick={onPreviewPick}
        onCommitPick={onCommitPick}
        onLoadPickDetail={onLoadPickDetail}
        onLoadPickScanner={onLoadPickScanner}
        onCommitPickScan={onCommitPickScan}
        fulfillmentPreview={fulfillmentPreview}
        fulfillmentCommitSummary={fulfillmentCommitSummary}
        fulfillmentHistory={fulfillmentHistory}
        fulfillmentDetail={fulfillmentDetail}
        fulfillmentLoading={fulfillmentLoading}
        fulfillmentError={fulfillmentError}
        onPreviewFulfillment={onPreviewFulfillment}
        onCommitFulfillment={onCommitFulfillment}
        onLoadFulfillmentDetail={onLoadFulfillmentDetail}
      />
    );
  }

  if (route.pageId === 'settings') {
    return (
      <WooCommerceSettingsPage
        status={wooStatus}
        preview={wooPreview}
        commitSummary={wooCommitSummary}
        orderPreview={wooOrderPreview}
        orderCommitSummary={wooOrderCommitSummary}
        syncRuns={wooSyncRuns}
        remapCandidates={wooRemapCandidates}
        remapMappings={wooRemapMappings}
        remapPreview={wooRemapPreview}
        remapMessage={wooRemapMessage}
        loading={wooLoading}
        error={wooError}
        onCheckConnection={() => onLoadWooStatus(true)}
        onPreview={onPreviewWooProductSync}
        onCommit={onCommitWooProductSync}
        onPreviewOrders={onPreviewWooOrderSync}
        onCommitOrders={onCommitWooOrderSync}
        onPreviewRemap={onPreviewWooRemap}
        onCommitRemap={onCommitWooRemap}
        onLoadRemap={onLoadWooRemap}
      />
    );
  }

  if (route.pageId === 'routes') {
    return (
      <RoutesPage
        candidatesData={routeCandidates}
        candidatesLoading={routeCandidatesLoading}
        candidatesError={routeCandidatesError}
        preview={routePreview}
        commitSummary={routeCommitSummary}
        routesData={routesHistory}
        detail={routeDetail}
        mapPayload={routeMapPayload}
        providerMessage={routeProviderMessage}
        loading={routesLoading}
        error={routesError}
        onLoadCandidates={onLoadRouteCandidates}
        onPreview={onPreviewRoute}
        onCommit={onCommitRoute}
        onLoadRoutes={onLoadRoutes}
        onLoadDetail={onLoadRouteDetail}
        onFinalize={onFinalizeRoute}
        onCancel={onCancelRoute}
        onSaveMetadata={onSaveRouteMetadata}
        onReorderStops={onReorderRouteStops}
        onSaveStop={onSaveRouteStop}
        onProviderAction={onRouteProviderAction}
      />
    );
  }

  if (route.pageId === 'dashboard') {
    return <CommandCenterPage dashboard={dashboard} loading={dashboardLoading} error={dashboardError} onRefresh={onLoadDashboard} />;
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
  const [locationRows, setLocationRows] = useState([]);
  const [locationRowsLoading, setLocationRowsLoading] = useState(false);
  const [locationRowsError, setLocationRowsError] = useState('');
  const [operationMessage, setOperationMessage] = useState('');
  const [transferForm, setTransferForm] = useState({ itemLocationId: '', toWarehouse: '', toInventoryLocation: '', quantity: '', notes: '' });
  const [adjustmentForm, setAdjustmentForm] = useState({ itemLocationId: '', adjustmentType: 'correction', quantityChange: '', reason: '', notes: '' });

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
    loadLocationRows(filters);
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

  async function loadLocationRows(nextFilters = filters) {
    setLocationRowsLoading(true);
    setLocationRowsError('');
    try {
      const query = plainFiltersToQueryString({
        warehouse: nextFilters.warehouse || undefined,
        inventory_location: nextFilters.inventoryLocation || undefined,
        category: nextFilters.category || undefined,
        brand: nextFilters.brand || undefined,
        under_par: nextFilters.underPar || undefined,
        limit: 50,
      });
      const response = await fetch(`${API_BASE_URL}/api/inventory/locations${query}`);
      if (!response.ok) {
        throw new Error(`Location inventory API returned ${response.status}`);
      }
      const body = await response.json();
      setLocationRows(body.rows || []);
    } catch (error) {
      setLocationRowsError('Unable to load location stock rows from the backend.');
    } finally {
      setLocationRowsLoading(false);
    }
  }

  async function commitTransfer() {
    setOperationMessage('');
    const source = locationRows.find((row) => String(row.id) === String(transferForm.itemLocationId));
    if (!source) {
      setOperationMessage('Select a source location row before transferring stock.');
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/inventory/transfers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          created_by: 'frontend',
          notes: transferForm.notes || null,
          lines: [
            {
              item_id: source.item_id,
              from_inventory_item_location_id: source.id,
              to_warehouse: transferForm.toWarehouse,
              to_inventory_location: transferForm.toInventoryLocation,
              quantity: Number(transferForm.quantity || 0),
              notes: transferForm.notes || null,
            },
          ],
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Transfer API returned ${response.status}`);
      }
      const body = await response.json();
      setOperationMessage(`Transfer ${body.transfer_number} committed.`);
      setTransferForm({ itemLocationId: '', toWarehouse: '', toInventoryLocation: '', quantity: '', notes: '' });
      await onLoadSummary(filters);
      await loadLocationRows(filters);
    } catch (error) {
      setOperationMessage(error.message || 'Unable to commit transfer.');
    }
  }

  async function commitAdjustment() {
    setOperationMessage('');
    const source = locationRows.find((row) => String(row.id) === String(adjustmentForm.itemLocationId));
    if (!source) {
      setOperationMessage('Select a location row before adjusting stock.');
      return;
    }
    try {
      const response = await fetch(`${API_BASE_URL}/api/inventory/adjustments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adjustment_type: adjustmentForm.adjustmentType,
          reason: adjustmentForm.reason,
          notes: adjustmentForm.notes || null,
          created_by: 'frontend',
          lines: [
            {
              item_id: source.item_id,
              inventory_item_location_id: source.id,
              quantity_change: Number(adjustmentForm.quantityChange || 0),
              notes: adjustmentForm.notes || null,
            },
          ],
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.detail || `Adjustment API returned ${response.status}`);
      }
      const body = await response.json();
      setOperationMessage(`Adjustment ${body.adjustment_number} committed.`);
      setAdjustmentForm({ itemLocationId: '', adjustmentType: 'correction', quantityChange: '', reason: '', notes: '' });
      await onLoadSummary(filters);
      await loadLocationRows(filters);
    } catch (error) {
      setOperationMessage(error.message || 'Unable to commit adjustment.');
    }
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
      {locationRowsError && <div className="api-error">{locationRowsError}</div>}
      {operationMessage && <div className="api-success">{operationMessage}</div>}
      {loading && <div className="loading-strip">Loading inventory summary...</div>}
      <InventorySummaryTable groups={summary.groups || []} />
      <LocationInventoryOperations
        rows={locationRows}
        loading={locationRowsLoading}
        transferForm={transferForm}
        setTransferForm={setTransferForm}
        adjustmentForm={adjustmentForm}
        setAdjustmentForm={setAdjustmentForm}
        onCommitTransfer={commitTransfer}
        onCommitAdjustment={commitAdjustment}
      />
    </section>
  );
}

function LocationInventoryOperations({ rows, loading, transferForm, setTransferForm, adjustmentForm, setAdjustmentForm, onCommitTransfer, onCommitAdjustment }) {
  const rowOptions = rows.map((row) => ({
    value: row.id,
    label: `${row.sku || `Item ${row.item_id}`} · ${row.warehouse || 'Unassigned'} / ${row.inventory_location || 'Unassigned'} · ${formatNumber(row.sellable)} sellable`,
  }));
  return (
    <div className="location-operations">
      <div className="section-heading">
        <div>
          <h3>Location Stock</h3>
          <p>{loading ? 'Loading rows...' : `${rows.length} location rows`}</p>
        </div>
        <a className="muted-button" href={`${API_BASE_URL}/api/inventory/locations/export`}>
          <Download size={16} />
          Export Rows
        </a>
      </div>
      <div className="table-wrap compact-table-wrap">
        <div className="table-scroll">
          <table className="inventory-summary-table">
            <thead>
              <tr>
                <th>SKU</th>
                <th>Description</th>
                <th>Warehouse</th>
                <th>Location</th>
                <th>In Stock</th>
                <th>Allocated</th>
                <th>Sellable</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.sku || 'Unassigned'}</td>
                  <td>{row.description || ''}</td>
                  <td>{row.warehouse || 'Unassigned'}</td>
                  <td>{row.inventory_location || 'Unassigned'}</td>
                  <td>{formatNumber(row.in_stock)}</td>
                  <td>{formatNumber(row.allocated)}</td>
                  <td>{formatNumber(row.sellable)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="operation-grid">
        <div className="operation-panel">
          <h3>Transfer</h3>
          <label className="field">
            <span>Source Row</span>
            <select value={transferForm.itemLocationId} onChange={(event) => setTransferForm((current) => ({ ...current, itemLocationId: event.target.value }))}>
              <option value="">Select row</option>
              {rowOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>To Warehouse</span>
            <input value={transferForm.toWarehouse} onChange={(event) => setTransferForm((current) => ({ ...current, toWarehouse: event.target.value }))} />
          </label>
          <label className="field">
            <span>To Location</span>
            <input value={transferForm.toInventoryLocation} onChange={(event) => setTransferForm((current) => ({ ...current, toInventoryLocation: event.target.value }))} />
          </label>
          <label className="field">
            <span>Quantity</span>
            <input min="0" step="0.001" type="number" value={transferForm.quantity} onChange={(event) => setTransferForm((current) => ({ ...current, quantity: event.target.value }))} />
          </label>
          <button className="primary-button" onClick={onCommitTransfer} type="button">
            <Save size={16} />
            Commit Transfer
          </button>
        </div>
        <div className="operation-panel">
          <h3>Adjustment</h3>
          <label className="field">
            <span>Location Row</span>
            <select value={adjustmentForm.itemLocationId} onChange={(event) => setAdjustmentForm((current) => ({ ...current, itemLocationId: event.target.value }))}>
              <option value="">Select row</option>
              {rowOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Type</span>
            <select value={adjustmentForm.adjustmentType} onChange={(event) => setAdjustmentForm((current) => ({ ...current, adjustmentType: event.target.value }))}>
              <option value="correction">Correction</option>
              <option value="damage">Damage</option>
              <option value="loss">Loss</option>
              <option value="found">Found</option>
              <option value="manual_increase">Manual Increase</option>
              <option value="manual_decrease">Manual Decrease</option>
            </select>
          </label>
          <label className="field">
            <span>Quantity Change</span>
            <input step="0.001" type="number" value={adjustmentForm.quantityChange} onChange={(event) => setAdjustmentForm((current) => ({ ...current, quantityChange: event.target.value }))} />
          </label>
          <label className="field">
            <span>Reason</span>
            <input value={adjustmentForm.reason} onChange={(event) => setAdjustmentForm((current) => ({ ...current, reason: event.target.value }))} />
          </label>
          <button className="primary-button" onClick={onCommitAdjustment} type="button">
            <Save size={16} />
            Commit Adjustment
          </button>
        </div>
      </div>
    </div>
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
          <button className="pager-button" aria-label="Previous page" title="Pagination is not available yet" disabled type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" title="Pagination is not available yet" disabled type="button">
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
              <input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadLocations(filters))} placeholder="Warehouse, code, name, zone, aisle" type="search" />
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
          <button className="pager-button" aria-label="Previous page" title="Pagination is not available yet" disabled type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" title="Pagination is not available yet" disabled type="button">
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
  const [selectedIds, setSelectedIds] = useState([]);
  const [visibleColumns, setVisibleColumns] = useState(ITEM_DEFAULT_VISIBLE_COLUMNS);
  const [detailId, setDetailId] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailTab, setDetailTab] = useState('overview');
  const [savedViews, setSavedViews] = useState([]);
  const [selectedViewId, setSelectedViewId] = useState('');
  const [viewName, setViewName] = useState('');
  const [message, setMessage] = useState('');
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkUpdates, setBulkUpdates] = useState({ category: '', brand: '', manufacturer: '', unit_cost: '', sales_price: '', par_level: '', active: '' });
  const [bulkPreview, setBulkPreview] = useState(null);
  const [remapOpen, setRemapOpen] = useState(false);
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    brand: '',
    status: 'active',
    stockStatus: '',
    includeNonInventory: true,
  });

  const options = useMemo(
    () => ({
      categories: uniqueOptions(items, 'Category'),
      brands: uniqueOptions(items, 'Brand'),
    }),
    [items],
  );

  useEffect(() => {
    onLoadItems(filters);
  }, [filters]);

  useEffect(() => {
    loadSavedViews();
  }, []);

  const displayedItems = useMemo(() => filterItems(items, filters), [items, filters]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function clearFilters() {
    setFilters({
      search: '',
      category: '',
      brand: '',
      status: 'active',
      stockStatus: '',
      includeNonInventory: true,
    });
  }

  async function loadSavedViews() {
    try {
      const response = await fetch(`${API_BASE_URL}/api/ui/saved-views?page=items`);
      if (response.ok) {
        const body = await response.json();
        setSavedViews(body.views || []);
      }
    } catch {
      setSavedViews([]);
    }
  }

  async function saveCurrentView() {
    if (!viewName.trim()) {
      setMessage('Name the view before saving it.');
      return;
    }
    await postJson('/api/ui/saved-views', { page: 'items', view_key: `items:${viewName.trim()}`, name: viewName.trim(), filters, columns: visibleColumns, created_by: 'frontend' });
    setViewName('');
    setMessage('Saved item view.');
    await loadSavedViews();
  }

  function loadView(view) {
    if (!view) {
      return;
    }
    setSelectedViewId(String(view.id));
    setFilters({ ...filters, ...(view.filters || {}) });
    setVisibleColumns(view.columns?.length ? view.columns : visibleColumns);
    setMessage(`Loaded ${view.name}.`);
  }

  async function deleteView(viewId) {
    const response = await fetch(`${API_BASE_URL}/api/ui/saved-views/${viewId}`, { method: 'DELETE' });
    if (response.ok) {
      setMessage('Deleted saved view.');
      setSelectedViewId('');
      await loadSavedViews();
    }
  }

  async function openDetail(itemId) {
    setDetailId(itemId);
    setDetailData(null);
    setDetailTab('overview');
    try {
      const response = await fetch(`${API_BASE_URL}/api/items/${itemId}/detail`);
      if (!response.ok) throw new Error(`Detail API returned ${response.status}`);
      setDetailData(await response.json());
    } catch {
      setMessage('Unable to load item detail.');
    }
  }

  function toggleSelected(itemId) {
    setSelectedIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleAllDisplayed(checked) {
    setSelectedIds(checked ? displayedItems.map((item) => item.id) : []);
  }

  function toggleColumn(column) {
    setVisibleColumns((current) => (current.includes(column) ? current.filter((item) => item !== column) : [...current, column]));
  }

  function bulkPayload() {
    return Object.fromEntries(Object.entries(bulkUpdates).filter(([, value]) => value !== '' && value !== null));
  }

  async function previewBulkEdit() {
    const result = await postJson('/api/items/bulk/preview', { item_ids: selectedIds, updates: bulkPayload() });
    setBulkPreview(result);
    setMessage(result.warnings?.join(' ') || `Previewed ${result.affected_count} item(s).`);
  }

  async function commitBulkEdit() {
    const result = await postJson('/api/items/bulk/commit', { item_ids: selectedIds, updates: bulkPayload() });
    setMessage(`Updated ${result.updated_count} item(s).`);
    setBulkPreview(null);
    setBulkOpen(false);
    setSelectedIds([]);
    await onLoadItems(filters);
  }

  return (
    <section className="content-panel items-page-pro">
      <div className="items-command-bar">
        <div className="items-command-header">
          <div>
            <h2>Item Master</h2>
            <p>{displayedItems.length} visible item(s)</p>
          </div>
          <div className="button-row items-actions">
            <button className="primary-button" onClick={() => onLoadItems(filters)} type="button">
              <Search size={17} />
              Search
            </button>
            <button className="muted-button" onClick={clearFilters} type="button">
              Clear
            </button>
            <button className="action-button" onClick={() => onLoadItems(filters)} type="button">
              <RefreshCw size={17} />
              Refresh
            </button>
            <button className="action-button" onClick={() => setRemapOpen(true)} type="button">
              <Link2 size={17} />
              Remap
            </button>
            <button className="action-button" disabled={!selectedIds.length} onClick={() => setBulkOpen(true)} type="button">
              <Edit3 size={17} />
              Bulk Edit
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
        <div className="items-filter-grid-pro">
          <label className="field">
            <span>SKU / Barcode / Description</span>
            <div className="input-with-icon">
              <input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadItems(filters))} placeholder="Search SKU, barcode, description, brand" type="search" />
              <Search size={18} />
            </div>
          </label>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <FilterSelect label="Stock Status" value={filters.stockStatus} options={['in_stock', 'out_of_stock', 'under_par', 'negative_sellable']} onChange={(value) => updateFilter('stockStatus', value)} />
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
      </div>
      <div className="items-view-card">
        <div className="items-view-controls">
          <label className="field compact-field">
            <span>Saved View</span>
            <select onChange={(event) => loadView(savedViews.find((view) => String(view.id) === event.target.value))} value={selectedViewId}>
              <option value="">Default view</option>
              {savedViews.map((view) => <option key={view.id} value={view.id}>{view.name}</option>)}
            </select>
          </label>
          <label className="field compact-field">
            <span>View Name</span>
            <input value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="Save current layout" />
          </label>
          <button className="muted-button" onClick={saveCurrentView} type="button"><Save size={16} />Save View</button>
          <button className="muted-button" disabled={!selectedViewId} onClick={() => deleteView(selectedViewId)} type="button">Delete View</button>
        </div>
        <details className="items-columns-panel">
          <summary>Columns</summary>
          <div className="column-toggle-row">
            {['SKU / Barcode', ...CANONICAL_ITEM_COLUMNS.filter((column) => !['SKU', 'Barcode', 'Warehouse', 'Inventory Location', 'Default Location', 'On Order', 'Assembly', 'Serializable', 'Track Lot', 'Perishable', 'Storage Length', 'Storage Width', 'Storage Height', 'Storage Volume'].includes(column))].map((column) => (
              <label className="check-field compact-check" key={column}>
                <input checked={visibleColumns.includes(column)} onChange={() => toggleColumn(column)} type="checkbox" />
                {column}
              </label>
            ))}
          </div>
        </details>
      </div>
      {error && <div className="api-error">{error}</div>}
      {message && <div className="api-success">{message}</div>}
      {loading && <div className="loading-strip">Loading backend items...</div>}
      <ItemsTable items={displayedItems} visibleColumns={visibleColumns} selectedIds={selectedIds} onToggleSelected={toggleSelected} onToggleAll={toggleAllDisplayed} onOpenDetail={openDetail} />
      {importOpen && <ImportModal onClose={() => setImportOpen(false)} onImported={() => onLoadItems(filters)} />}
      {detailId && <ItemDetailDrawer detail={detailData} tab={detailTab} setTab={setDetailTab} onClose={() => setDetailId(null)} onRefresh={() => openDetail(detailId)} />}
      {bulkOpen && <BulkEditModal selectedCount={selectedIds.length} updates={bulkUpdates} setUpdates={setBulkUpdates} preview={bulkPreview} onPreview={previewBulkEdit} onCommit={commitBulkEdit} onClose={() => setBulkOpen(false)} />}
      {remapOpen && <LocalRemapSearchModal onClose={() => setRemapOpen(false)} />}
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

function ItemsTable({ items, visibleColumns, selectedIds, onToggleSelected, onToggleAll, onOpenDetail }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>
          Showing records 1-{items.length} out of {items.length}
        </span>
        <div className="table-pager">
          <span>{items.length} Results</span>
          <button className="pager-button" aria-label="Previous page" title="Pagination is not available yet" disabled type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" title="Pagination is not available yet" disabled type="button">
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
              <th className="sticky-col sticky-action-col"><input checked={items.length > 0 && selectedIds.length === items.length} onChange={(event) => onToggleAll(event.target.checked)} type="checkbox" /></th>
              <th className="sticky-col sticky-image-col">Image</th>
              {visibleColumns.map((column) => (
                <th key={column}>{column}</th>
              ))}
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td className="sticky-col sticky-action-col">
                  <input checked={selectedIds.includes(item.id)} onChange={() => onToggleSelected(item.id)} type="checkbox" />
                </td>
                <td className="sticky-col sticky-image-col">
                  <button className="image-cell image-button" onClick={() => onOpenDetail(item.id)} type="button">
                    {item.imageUrl ? <img alt="" src={item.imageUrl} /> : 'No Image'}
                  </button>
                </td>
                {visibleColumns.map((column) => (
                  <td key={`${item.id}-${column}`} className={column === 'Description' ? 'description-cell' : ''}>
                    {column === 'SKU / Barcode' ? (
                      <button className="table-link-button sku-barcode-cell" onClick={() => onOpenDetail(item.id)} type="button">
                        <strong>{item.SKU || 'No SKU'}</strong>
                        <span>{item.Barcode || 'No barcode'}</span>
                      </button>
                    ) : column === 'SKU' || column === 'Description' ? (
                      <button className="table-link-button" onClick={() => onOpenDetail(item.id)} type="button">{formatCell(item[column], column) || 'Open'}</button>
                    ) : (
                      formatCell(item[column], column)
                    )}
                  </td>
                ))}
                <td>
                  <StatusBadge active={item.active} />
                </td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr>
                <td colSpan={visibleColumns.length + 3}>
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

function ItemDetailDrawer({ detail, tab, setTab, onClose, onRefresh }) {
  const item = detail?.item;
  const tabs = ['overview', 'stock', 'activity', 'history', 'edit'];
  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="detail-drawer" role="dialog" aria-modal="true" aria-label="Item detail">
        <div className="modal-header">
          <div>
            <h2>{item?.sku || 'Item Detail'}</h2>
            <p>{item?.description || 'Loading item control center...'}</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close item detail" type="button"><MoreVertical size={20} /></button>
        </div>
        {!detail && <div className="loading-strip">Loading item detail...</div>}
        {detail && (
          <>
            <div className="tab-row">
              {tabs.map((name) => <button className={tab === name ? 'tab-button active' : 'tab-button'} key={name} onClick={() => setTab(name)} type="button">{name}</button>)}
            </div>
            {tab === 'overview' && <ItemOverview detail={detail} onRefresh={onRefresh} />}
            {tab === 'stock' && <ItemStockByLocation rows={detail.stock_by_location || []} item={item} />}
            {tab === 'activity' && <ItemActivityTimeline rows={detail.recent_activity || []} />}
            {tab === 'history' && <ItemHistoryPanel itemId={item.id} />}
            {tab === 'edit' && <ItemMetadataPanel item={item} onSaved={onRefresh} />}
          </>
        )}
      </aside>
    </div>
  );
}

function ItemOverview({ detail, onRefresh }) {
  const item = detail.item || {};
  const stats = detail.quick_stats || {};
  return (
    <div className="drawer-section">
      <div className="item-overview-grid">
        <div className="item-photo">{item.image_url ? <img alt="" src={item.image_url} /> : <PackageSearch size={42} />}</div>
        <div className="summary-strip">
          <Metric label="In Stock" value={formatNumber(item.in_stock)} />
          <Metric label="Allocated" value={formatNumber(item.allocated)} />
          <Metric label="Sellable" value={formatNumber(item.sellable)} />
          <Metric label="Value" value={formatCurrency(stats.inventory_value)} />
        </div>
      </div>
      <TableShell caption="Item" columns={['Field', 'Value']}>
        {[
          ['SKU', item.sku], ['Barcode', item.barcode], ['Brand', item.brand], ['Category', item.category], ['Unit Cost', formatCurrency(item.unit_cost)], ['Sales Price', formatCurrency(item.sales_price)], ['Woo Mapping', item.woo_product_id || item.woo_variation_id ? `${item.woo_product_id || ''}/${item.woo_variation_id || ''}` : 'Unmapped'], ['Last Received', formatDateTime(stats.last_received_at)], ['Last Counted', formatDateTime(stats.last_counted_at)],
        ].map(([label, value]) => <tr key={label}><td>{label}</td><td>{value || ''}</td></tr>)}
      </TableShell>
      <div className="button-row"><button className="muted-button" onClick={onRefresh} type="button"><RefreshCw size={16} />Refresh Detail</button><a className="action-button" href="#receiving">Receive</a><a className="action-button" href="#inventory">Transfer</a><a className="action-button" href="#cycle-count">Cycle Count</a></div>
    </div>
  );
}

function ItemStockByLocation({ rows }) {
  return (
    <TableShell caption={`${rows.length} stock location(s)`} columns={['Warehouse', 'Location', 'In Stock', 'Allocated', 'Sellable', 'Under Par', 'Par', 'Default', 'Updated']}>
      {rows.map((row) => <tr key={row.id}><td>{row.warehouse}</td><td>{row.inventory_location}</td><td>{formatNumber(row.in_stock)}</td><td>{formatNumber(row.allocated)}</td><td>{formatNumber(row.sellable)}</td><td>{row.under_par ? 'Yes' : 'No'}</td><td>{formatNumber(row.par_level)}</td><td>{row.is_default_location ? 'Yes' : 'No'}</td><td>{formatDateTime(row.updated_at)}</td></tr>)}
      {!rows.length && <tr><td colSpan={9}><div className="empty-table-row">No stock locations yet.</div></td></tr>}
    </TableShell>
  );
}

function ItemActivityTimeline({ rows }) {
  return (
    <div className="activity-timeline">
      {rows.map((row) => <div className={`activity-row ${row.severity}`} key={row.id}><strong>{row.title}</strong><span>{formatDateTime(row.created_at)} · {row.warehouse || ''} {row.inventory_location || ''}</span><p>{row.description || row.reference_number || ''}</p><b>{row.quantity_change == null ? '' : formatNumber(row.quantity_change)}</b></div>)}
      {!rows.length && <div className="empty-table-row">No item activity yet.</div>}
    </div>
  );
}

function ItemHistoryPanel({ itemId }) {
  const [section, setSection] = useState('receipts');
  const [history, setHistory] = useState({ rows: [], total: 0 });
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/items/${itemId}/history?section=${section}`).then((response) => response.json()).then(setHistory).catch(() => setHistory({ rows: [], total: 0 }));
  }, [itemId, section]);
  return (
    <div className="drawer-section">
      <FilterSelect label="History" value={section} options={['receipts', 'cycle-counts', 'adjustments', 'transfers', 'allocations', 'picks', 'fulfillments', 'orders', 'stock-movements']} onChange={setSection} />
      <ItemActivityTimeline rows={history.rows || []} />
    </div>
  );
}

function ItemMetadataPanel({ item, onSaved }) {
  const [form, setForm] = useState({ category: item.category || '', brand: item.brand || '', manufacturer: item.manufacturer || '', unit_cost: item.unit_cost || '', sales_price: item.sales_price || '', par_level: '', active: item.active });
  const [message, setMessage] = useState('');
  async function saveMetadata() {
    const payload = {
      Category: form.category,
      Brand: form.brand,
      Manufacturer: form.manufacturer,
      'Unit Cost': form.unit_cost,
      'Sales Price': form.sales_price,
      active: Boolean(form.active),
    };
    await patchJson(`/api/items/${item.id}`, payload);
    setMessage('Metadata saved. Stock quantities remain controlled by receiving, count, transfer, and adjustment workflows.');
    onSaved();
  }
  return (
    <div className="drawer-section operation-grid">
      {['category', 'brand', 'manufacturer', 'unit_cost', 'sales_price'].map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={form[field]} onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))} /></label>)}
      <label className="check-field"><input checked={form.active} onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))} type="checkbox" />Active</label>
      <button className="primary-button" onClick={saveMetadata} type="button"><Save size={16} />Save Metadata</button>
      {message && <div className="api-success">{message}</div>}
    </div>
  );
}

function BulkEditModal({ selectedCount, updates, setUpdates, preview, onPreview, onCommit, onClose }) {
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Bulk edit items">
        <div className="modal-header"><div><h2>Bulk Edit Metadata</h2><p>{selectedCount} selected item(s). Stock and Woo fields are blocked.</p></div><button className="icon-button modal-close" onClick={onClose} type="button"><MoreVertical size={20} /></button></div>
        <div className="operation-grid">
          {Object.keys(updates).map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={updates[field]} onChange={(event) => setUpdates((current) => ({ ...current, [field]: event.target.value }))} /></label>)}
        </div>
        <div className="button-row"><button className="muted-button" onClick={onPreview} type="button">Preview</button><button className="primary-button" disabled={!preview?.can_commit} onClick={onCommit} type="button">Commit Metadata</button></div>
        {preview && <div className="import-results"><div className="import-metrics"><Metric label="Affected" value={preview.affected_count} /><Metric label="Fields" value={(preview.fields_to_update || []).length} /></div>{preview.warnings?.map((warning) => <div className="api-error" key={warning}>{warning}</div>)}</div>}
      </section>
    </div>
  );
}

function LocalRemapSearchModal({ onClose }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  async function search() {
    const response = await fetch(`${API_BASE_URL}/api/items/search?q=${encodeURIComponent(query)}&limit=10`);
    if (response.ok) {
      const body = await response.json();
      setResults(body.items || []);
    }
  }
  return (
    <div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Local remap search">
        <div className="modal-header"><div><h2>Local Remap Search</h2><p>This only searches local item candidates. Remap commit remains in Settings and never writes to WooCommerce.</p></div><button className="icon-button modal-close" onClick={onClose} type="button"><MoreVertical size={20} /></button></div>
        <div className="scanner-input-row"><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && search()} placeholder="Search SKU, barcode, or name" /><button className="primary-button" onClick={search} type="button"><Search size={16} />Search</button></div>
        <TableShell caption={`${results.length} candidate(s)`} columns={['SKU', 'Barcode', 'Description', 'Brand', 'Woo Mapping']}>
          {results.map((item) => <tr key={item.id}><td>{item.sku}</td><td>{item.barcode}</td><td>{item.description}</td><td>{item.brand}</td><td>{item.woo_mapping_summary?.mapped ? 'Mapped' : 'Unmapped'}</td></tr>)}
          {!results.length && <tr><td colSpan={5}><div className="empty-table-row">No candidates loaded.</div></td></tr>}
        </TableShell>
      </section>
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
    <section className="content-panel item-editor-page">
      <div className="item-editor-toolbar">
        <a className="muted-button" href="#items">
          <ArrowLeft size={17} />
          All Items
        </a>
        <div>
          <h2>{isNew ? 'New Item' : calculatedItem.SKU || 'Edit Item'}</h2>
          <p>Clean item metadata entry. Stock quantities are controlled by receiving, counts, transfers, and adjustments.</p>
        </div>
      </div>
      <div className="detail-layout">
        <div className="detail-main">
          <FormSection title="Core Identity">
            {renderTextField('SKU', calculatedItem, updateField, { required: true })}
            {renderTextField('Barcode', calculatedItem, updateField)}
            {renderTextField('Description', calculatedItem, updateField, { wide: true })}
            {renderTextField('Category', calculatedItem, updateField)}
            {renderTextField('Brand', calculatedItem, updateField)}
            {renderTextField('Manufacturer', calculatedItem, updateField)}
            {renderTextField('Manufacturer Website', calculatedItem, updateField, { wide: true })}
          </FormSection>
          <FormSection title="Placement">
            {renderTextField('Warehouse', calculatedItem, updateField)}
            {renderTextField('Default Location', calculatedItem, updateField)}
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
          <FormSection title="Physical Attributes">
            {renderTextField('Unit of Measurement', calculatedItem, updateField)}
            {renderNumberField('Weight', calculatedItem, updateField)}
          </FormSection>
          <FormSection title="Flags">
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
          <div className="mapping-card item-editor-note">
            <h2>Stock Control</h2>
            <p>Do not enter stock here. Receive, count, transfer, or adjust stock from the operational workflows so every change has an audit trail.</p>
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

function CommandCenterPage({ dashboard, loading, error, onRefresh }) {
  const inventory = dashboard.inventory_health || {};
  const orders = dashboard.order_operations || {};
  const routes = dashboard.routes || {};
  const warnings = dashboard.warnings || [];
  const activity = dashboard.activity || [];
  return (
    <section className="dashboard-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Command Center</h2>
            <p>Last refreshed {dashboard.generated_at ? formatDateTime(dashboard.generated_at) : 'not yet'}.</p>
          </div>
          <button className="primary-button" onClick={onRefresh} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
        </div>
        {error && <div className="api-error">{error}</div>}
        {loading && <div className="loading-strip">Loading Command Center...</div>}
      </div>
      <DashboardCardSection title="Inventory Health" cards={[
        ['Items', inventory.total_items, 'Total records', PackageSearch],
        ['Active', inventory.active_items, 'Active items', CheckCircle2],
        ['Inventory Value', formatCurrency(inventory.total_inventory_value), 'Local value', Boxes],
        ['Reorder', inventory.reorder_count, 'Under par + reorder', TriangleAlert],
        ['Under Par', inventory.under_par_count, 'Needs review', TriangleAlert],
        ['Damage/Loss', formatCurrency(inventory.damage_loss_value_this_month), 'This month', TriangleAlert],
        ['Transfers', inventory.transfers_this_week, 'Last 7 days', Warehouse],
        ['Receiving', inventory.receiving_this_week, 'Last 7 days', PackagePlus],
        ['Adjustments', inventory.adjustment_count_this_week, 'Last 7 days', SlidersHorizontal],
        ['Negative Sellable', inventory.negative_sellable_count, 'Data warning', TriangleAlert],
        ['Missing SKU', inventory.missing_sku_count, 'Match risk', Search],
      ]} />
      <DashboardCardSection title="Order Operations" cards={[
        ['Open', orders.open_orders_count, 'Local open orders', ShoppingCart],
        ['Allocated', orders.allocated_orders_count, 'Fully allocated', ClipboardList],
        ['Part Allocated', orders.partially_allocated_orders_count, 'Partial reservations', ClipboardList],
        ['Picked', orders.picked_orders_count, 'Ready for fulfillment', ClipboardCheck],
        ['Fulfilled', orders.fulfilled_orders_count, 'Completed locally', CheckCircle2],
        ['Attention', orders.orders_needing_attention_count, 'Needs review', TriangleAlert],
      ]} />
      <DashboardCardSection title="Routes" cards={[
        ['Candidates', routes.route_candidates_count, 'Ready for routes', Route],
        ['Draft', routes.draft_routes_count, 'Editable routes', CalendarDays],
        ['Finalized', routes.finalized_routes_count, 'Locked locally', CheckCircle2],
        ['Cancelled', routes.cancelled_routes_count, 'Released orders', TriangleAlert],
      ]} />
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Data Quality Warnings</h2>
            <p>Local records that need cleanup.</p>
          </div>
        </div>
        <TableShell caption={`${warnings.length} warning group(s)`} columns={['Severity', 'Title', 'Count', 'Description', 'Samples']}>
          {warnings.map((warning) => (
            <tr key={warning.code}>
              <td>{StatusText(warning.severity)}</td>
              <td>{warning.title}</td>
              <td>{warning.count}</td>
              <td className="description-cell">{warning.description}</td>
              <td className="description-cell">{(warning.sample_records || []).map((sample) => sample.label).join(', ')}</td>
            </tr>
          ))}
          {warnings.length === 0 && <tr><td colSpan={5}><div className="empty-table-row">No data quality warnings right now.</div></td></tr>}
        </TableShell>
      </div>
      <div className="wide-panel">
        <div className="panel-title"><div><h2>Recent Activity</h2><p>Latest local operational records.</p></div></div>
        <TableShell caption={`${activity.length} activity item(s)`} columns={['When', 'Type', 'Title', 'Details', 'Severity']}>
          {activity.map((item) => (
            <tr key={item.id}><td>{formatDateTime(item.created_at)}</td><td>{item.type}</td><td>{item.title}</td><td className="description-cell">{item.subtitle}</td><td>{StatusText(item.severity)}</td></tr>
          ))}
          {activity.length === 0 && <tr><td colSpan={5}><div className="empty-table-row">No recent local activity yet.</div></td></tr>}
        </TableShell>
      </div>
      <aside className="dashboard-widgets">
        <div className="section-heading compact-heading"><div><h2>Quick Actions</h2><p>Common workflows</p></div></div>
        <div className="widget-list">
          {[
            ['Import Items', '#items'],
            ['Sync Woo Products', '#settings'],
            ['Sync Woo Orders', '#settings'],
            ['Receive Inventory', '#receiving'],
            ['Cycle Count', '#cycle-count'],
            ['Allocate Orders', '#/orders/allocate'],
            ['Pick Orders', '#/orders/pick'],
            ['Fulfill Orders', '#/orders/fulfillment'],
            ['Create Route', '#routes'],
            ['Reports', '#reports'],
          ].map(([title, href]) => <a className="widget-row" href={href} key={title}><div><strong>{title}</strong><em>Open workflow</em></div><span>Open</span></a>)}
        </div>
      </aside>
    </section>
  );
}

function DashboardCardSection({ title, cards }) {
  return (
    <div className="wide-panel dashboard-card-section">
      <div className="section-heading compact-heading"><div><h2>{title}</h2></div></div>
      <div className="summary-strip report-summary-strip">
        {cards.map(([label, value, caption, Icon]) => (
          <article className="summary-card" key={`${title}-${label}`}>
            <div className="summary-icon"><Icon size={22} /></div>
            <div><span>{label}</span><strong>{value ?? 0}</strong><small>{caption}</small></div>
          </article>
        ))}
      </div>
    </div>
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
  const [mode, setMode] = useState('direct');
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
      <div className="tab-row">
        <button className={mode === 'direct' ? 'tab-button active' : 'tab-button'} onClick={() => setMode('direct')} type="button">Direct Receiving</button>
        <button className={mode === 'bulk' ? 'tab-button active' : 'tab-button'} onClick={() => setMode('bulk')} type="button">Bulk Receiving Session</button>
        <button className={mode === 'history' ? 'tab-button active' : 'tab-button'} onClick={() => setMode('history')} type="button">Receipt History</button>
      </div>
      {mode === 'direct' && <div className="receiving-form">
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
      </div>}
      {mode === 'bulk' && <BulkReceivingSession items={items} locations={locations} onCommitted={async () => { await onLoadReceipts(); await onLoadStockMovements({ movement_type: 'receive_direct' }); await onLoadInventorySummary(); }} />}
      {(mode === 'history' || mode === 'direct') && <div className="wide-panel">
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
      </div>}
      {mode !== 'bulk' && <div className="wide-panel">
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
      </div>}
    </section>
  );
}

function BulkReceivingSession({ items, locations, onCommitted }) {
  const [header, setHeader] = useState({ warehouse: 'Main Warehouse', notes: '' });
  const [scanInput, setScanInput] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [inventoryLocation, setInventoryLocation] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [optional, setOptional] = useState({ lot_number: '', expiration_date: '', pallet_number: '', pkg_number: '', item_number: '', sales_price: '', weight: '', notes: '' });
  const [lines, setLines] = useState([]);
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const activeLocations = locations.filter((location) => location.isActive && (!header.warehouse || location.warehouse === header.warehouse));

  function addLine() {
    const item = findReceivingItem(items, scanInput);
    setLines((current) => [...current, { localId: crypto.randomUUID?.() || String(Date.now()), scan_input: scanInput, sku: item?.SKU || '', barcode: item?.Barcode || '', quantity: toNumber(quantity) || 1, warehouse: header.warehouse, inventory_location: inventoryLocation, unit_cost: unitCost, ...optional }]);
    setScanInput('');
    setQuantity(1);
    setPreview(null);
  }

  async function previewSession() {
    setError('');
    setSummary(null);
    try {
      setPreview(await postJson('/api/receipts/bulk/preview', { ...header, lines }));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview bulk receipt.');
    }
  }

  async function commitSession() {
    setError('');
    try {
      const result = await postJson('/api/receipts/bulk/commit', { ...header, source: 'manual', lines });
      setSummary(result);
      setLines([]);
      setPreview(null);
      await onCommitted();
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit bulk receipt.');
    }
  }

  return (
    <div className="receiving-form bulk-session">
      <div className="section-heading"><div><h2>Bulk Receiving Session</h2><p>Multi-row receiving cart committed as one receipt.</p></div><button className="muted-button" onClick={() => { setLines([]); setPreview(null); setSummary(null); }} type="button">Clear Session</button></div>
      <div className="receiving-header-fields">
        <FilterSelect label="Warehouse" value={header.warehouse} options={uniqueOptions(locations, 'warehouse')} onChange={(value) => setHeader((current) => ({ ...current, warehouse: value || 'Main Warehouse' }))} />
        <label className="field wide-field"><span>Notes</span><input value={header.notes} onChange={(event) => setHeader((current) => ({ ...current, notes: event.target.value }))} /></label>
      </div>
      <div className="scanner-input-row">
        <input autoFocus value={scanInput} onChange={(event) => setScanInput(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && addLine()} placeholder="Scan or type SKU/barcode" />
        <input value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" />
        <select value={inventoryLocation} onChange={(event) => setInventoryLocation(event.target.value)}><option value="">Location</option>{activeLocations.map((location) => <option key={location.id} value={location.code}>{location.warehouse} / {location.code}</option>)}</select>
        <input value={unitCost} onChange={(event) => setUnitCost(event.target.value)} placeholder="Unit cost" inputMode="decimal" />
        <button className="primary-button" onClick={addLine} type="button"><Plus size={16} />Add Line</button>
      </div>
      <details className="optional-fields"><summary>Optional receiving fields</summary><div className="operation-grid">{Object.keys(optional).map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={optional[field]} onChange={(event) => setOptional((current) => ({ ...current, [field]: event.target.value }))} type={field === 'expiration_date' ? 'date' : 'text'} /></label>)}</div></details>
      <TableShell caption={`${lines.length} cart line(s)`} columns={['Scan', 'SKU', 'Location', 'Qty', 'Unit Cost', 'Notes']}>
        {lines.map((line) => <tr key={line.localId}><td>{line.scan_input}</td><td>{line.sku}</td><td>{line.inventory_location}</td><td>{formatNumber(line.quantity)}</td><td>{formatCurrency(line.unit_cost)}</td><td>{line.notes}</td></tr>)}
        {!lines.length && <tr><td colSpan={6}><div className="empty-table-row">Scan or add lines to begin.</div></td></tr>}
      </TableShell>
      <div className="detail-actions"><button className="muted-button" onClick={previewSession} type="button">Preview Session</button><button className="primary-button" disabled={!preview?.can_commit} onClick={commitSession} type="button">Commit Session</button></div>
      {error && <div className="api-error">{error}</div>}
      {summary && <div className="success-strip">Receipt {summary.receipt_number} committed. <a href={`${API_BASE_URL}/api/receipts/${summary.id}/export`}>Export CSV</a></div>}
      {preview && <BulkReceivingPreview preview={preview} />}
    </div>
  );
}

function BulkReceivingPreview({ preview }) {
  return (
    <div className="import-results">
      <div className="import-metrics"><Metric label="Lines" value={preview.line_count} /><Metric label="Valid" value={preview.valid_line_count} /><Metric label="Errors" value={preview.error_line_count} /><Metric label="Qty" value={formatNumber(preview.total_quantity)} /><Metric label="Cost" value={formatCurrency(preview.total_cost)} /></div>
      <TableShell caption="Bulk preview" columns={['Line', 'Status', 'SKU', 'Location', 'Qty', 'Old Loc', 'New Loc', 'Errors']}>
        {preview.lines.map((line) => <tr key={line.line_number}><td>{line.line_number}</td><td>{line.status}</td><td>{line.item?.sku}</td><td>{line.inventory_location}</td><td>{formatNumber(line.quantity)}</td><td>{formatNumber(line.old_location_stock)}</td><td>{formatNumber(line.new_location_stock)}</td><td>{line.errors?.join(' ')}</td></tr>)}
      </TableShell>
    </div>
  );
}

function ScannerWorkflowsPage({ locations, onLoadItems, onLoadInventorySummary }) {
  const [mode, setMode] = useState('inventory');
  const [form, setForm] = useState({ scan_input: '', quantity: 1, warehouse: 'Main Warehouse', inventory_location: '', counted_quantity: '', from_warehouse: 'Main Warehouse', from_inventory_location: '', to_warehouse: 'Main Warehouse', to_inventory_location: '', adjustment_type: 'correction', quantity_change: '', new_quantity: '', reason: '', notes: '', order_id: '' });
  const [result, setResult] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState('');
  const activeLocations = locations.filter((location) => location.isActive);
  const modes = [
    { key: 'inventory', label: 'Inventory Lookup' },
    { key: 'location', label: 'Location Lookup' },
    { key: 'receiving', label: 'Receiving' },
    { key: 'cycle-count', label: 'Cycle Count' },
    { key: 'transfer', label: 'Transfer' },
    { key: 'adjustment', label: 'Adjustment' },
    { key: 'picking', label: 'Picking' },
  ];
  const activeMode = modes.find((candidate) => candidate.key === mode) || modes[0];

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function runScan(commit = false) {
    setError('');
    try {
      let nextResult;
      if (mode === 'inventory') {
        const response = await fetch(`${API_BASE_URL}/api/scanner/inventory/lookup?scan_input=${encodeURIComponent(form.scan_input)}`);
        nextResult = await response.json();
      } else if (mode === 'location') {
        const response = await fetch(`${API_BASE_URL}/api/scanner/location/lookup?scan_input=${encodeURIComponent(form.scan_input)}`);
        nextResult = await response.json();
      } else if (mode === 'picking') {
        window.location.hash = '#orders';
        return;
      } else {
        const endpoint = {
          receiving: `/api/scanner/receiving/scan/${commit ? 'commit' : 'preview'}`,
          'cycle-count': `/api/scanner/cycle-count/${commit ? 'commit' : 'preview'}`,
          transfer: `/api/scanner/transfers/${commit ? 'commit' : 'preview'}`,
          adjustment: `/api/scanner/adjustments/${commit ? 'commit' : 'preview'}`,
        }[mode];
        nextResult = await postJson(endpoint, { ...form, quantity: toNumber(form.quantity), counted_quantity: toNumber(form.counted_quantity), quantity_change: form.quantity_change === '' ? '' : toNumber(form.quantity_change), new_quantity: form.new_quantity === '' ? '' : toNumber(form.new_quantity) });
      }
      setResult(nextResult);
      setRecent((current) => [{ mode, scan: form.scan_input, status: nextResult.matched === false || nextResult.can_commit === false ? 'warning' : 'success', at: new Date().toISOString() }, ...current].slice(0, 12));
      if (commit) {
        await onLoadItems();
        await onLoadInventorySummary();
      }
    } catch (apiError) {
      setError(apiError.message || 'Scanner request failed.');
    }
  }

  return (
    <section className="content-panel scanner-page">
      <div className="scanner-mode-card">
        <div>
          <h2>Scanner Console</h2>
          <p>Use keyboard scanners as fast SKU, barcode, or location input.</p>
        </div>
        <div className="segmented-control" role="tablist" aria-label="Scanner modes">
          {modes.map((item) => <button className={mode === item.key ? 'segment active' : 'segment'} key={item.key} onClick={() => setMode(item.key)} type="button">{item.label}</button>)}
        </div>
      </div>
      <div className="scanner-layout">
        <div className="scanner-console-card">
          <div className="scanner-card-header">
            <div>
              <span>{activeMode.label}</span>
              <h2>{mode === 'picking' ? 'Open the order pick scanner' : 'Ready to scan'}</h2>
            </div>
            <Badge tone={result?.matched === false || result?.can_commit === false ? 'warning' : result ? 'success' : 'neutral'}>{result ? 'Result loaded' : 'Waiting'}</Badge>
          </div>
          <div className="scanner-input-row">
            <input autoFocus value={form.scan_input} onChange={(event) => update('scan_input', event.target.value)} onKeyDown={(event) => event.key === 'Enter' && runScan(false)} placeholder={mode === 'location' ? 'Scan location code or name' : 'Scan SKU, barcode, or item ID'} />
            <button className="primary-button" onClick={() => runScan(false)} type="button"><Search size={16} />Scan</button>
          </div>
          {['receiving', 'cycle-count', 'transfer', 'adjustment'].includes(mode) && (
            <div className="operation-grid">
              {mode === 'receiving' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><label className="field"><span>Quantity</span><input value={form.quantity} onChange={(event) => update('quantity', event.target.value)} /></label><label className="field"><span>Unit Cost</span><input value={form.unit_cost || ''} onChange={(event) => update('unit_cost', event.target.value)} /></label></>}
              {mode === 'cycle-count' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><label className="field"><span>Counted Quantity</span><input value={form.counted_quantity} onChange={(event) => update('counted_quantity', event.target.value)} /></label><label className="field"><span>Reason</span><input value={form.reason} onChange={(event) => update('reason', event.target.value)} /></label></>}
              {mode === 'transfer' && <><label className="field"><span>From Location</span><input value={form.from_inventory_location} onChange={(event) => update('from_inventory_location', event.target.value)} /></label><label className="field"><span>To Location</span><input value={form.to_inventory_location} onChange={(event) => update('to_inventory_location', event.target.value)} /></label><label className="field"><span>Quantity</span><input value={form.quantity} onChange={(event) => update('quantity', event.target.value)} /></label></>}
              {mode === 'adjustment' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><FilterSelect label="Adjustment Type" value={form.adjustment_type} options={['correction', 'damage', 'loss', 'found', 'manual_increase', 'manual_decrease']} onChange={(value) => update('adjustment_type', value)} /><label className="field"><span>Qty Change</span><input value={form.quantity_change} onChange={(event) => update('quantity_change', event.target.value)} /></label><label className="field"><span>New Qty</span><input value={form.new_quantity} onChange={(event) => update('new_quantity', event.target.value)} /></label><label className="field"><span>Reason</span><input value={form.reason} onChange={(event) => update('reason', event.target.value)} /></label></>}
            </div>
          )}
          {['receiving', 'cycle-count', 'transfer', 'adjustment'].includes(mode) && <div className="button-row"><button className="muted-button" onClick={() => runScan(false)} type="button">Preview</button><button className="primary-button" onClick={() => runScan(true)} type="button">Commit</button></div>}
          {mode === 'picking' && <div className="empty-state"><h2>Picking Scanner</h2><p>Picking scanner is tied to open orders so it can prevent over-pick.</p><a className="primary-button" href="#/orders/pick">Open Pick Orders</a></div>}
          {error && <div className="api-error">{error}</div>}
          <ScannerResult result={result} />
        </div>
        <div className="scanner-recent-card">
          <div className="panel-title"><div><h2>Recent Scans</h2><p>Keyboard scanner history for this screen.</p></div></div>
          {recent.map((row) => <div className={`activity-row ${row.status}`} key={`${row.at}-${row.scan}`}><strong>{row.mode}</strong><span>{row.scan}</span><p>{formatDateTime(row.at)}</p></div>)}
          {!recent.length && <div className="scanner-empty-state">No scans yet. The next scan will appear here with status and timestamp.</div>}
        </div>
      </div>
    </section>
  );
}

function ScannerLocationFields({ form, locations, update }) {
  return (
    <>
      <FilterSelect label="Warehouse" value={form.warehouse} options={uniqueOptions(locations, 'warehouse')} onChange={(value) => update('warehouse', value || 'Main Warehouse')} />
      <label className="field"><span>Location</span><select value={form.inventory_location} onChange={(event) => update('inventory_location', event.target.value)}><option value="">Select location</option>{locations.filter((location) => !form.warehouse || location.warehouse === form.warehouse).map((location) => <option key={location.id} value={location.code}>{location.warehouse} / {location.code}</option>)}</select></label>
    </>
  );
}

function ScannerResult({ result }) {
  if (!result) return null;
  const item = result.item;
  return (
    <div className="scanner-result-panel">
      <div className="panel-title compact-title"><div><h2>Scan Result</h2><p>{result.matched === false ? 'No matching item or location was found.' : 'Validated scanner response.'}</p></div></div>
      {item && <div className="scanner-match"><strong>{item.sku}</strong><span>{item.barcode}</span><p>{item.description}</p></div>}
      {result.stock_by_location && <ItemStockByLocation rows={result.stock_by_location} />}
      {result.items && <TableShell caption={`${result.items.length} location item(s)`} columns={['SKU', 'Description', 'Location', 'In Stock', 'Sellable']} >{result.items.map((row) => <tr key={row.id}><td>{row.sku}</td><td>{row.description}</td><td>{row.inventory_location}</td><td>{formatNumber(row.in_stock)}</td><td>{formatNumber(row.sellable)}</td></tr>)}</TableShell>}
      {!item && !result.stock_by_location && !result.items && <div className={result.matched === false ? 'api-error' : 'success-strip'}>{result.message || result.safe_message || 'Scan response received.'}</div>}
      <details className="raw-response-details">
        <summary>Raw response</summary>
        <pre className="json-preview">{JSON.stringify(result, null, 2)}</pre>
      </details>
    </div>
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

function ReportsPage({ receivedRows, receivedSummary, receivedLoading, receivedError, onLoadReceivedReport, fulfillmentRows, fulfillmentSummary, fulfillmentLoading, fulfillmentError, onLoadFulfillmentReport, skuOrdersRows, skuOrdersSummary, skuOrdersLoading, skuOrdersError, onLoadSkuOrdersReport }) {
  const [activeReport, setActiveReport] = useState(expandedReportDefinitions[0].key);
  const allReports = [
    ...expandedReportDefinitions,
    { key: 'received-inventory', label: 'Received Inventory' },
    { key: 'fulfillment', label: 'Fulfillment' },
    { key: 'sku-orders', label: 'SKU Orders' },
  ];
  const isExpandedReport = expandedReportDefinitions.some((report) => report.key === activeReport);

  return (
    <section className="content-panel report-page">
      <div className="reports-workspace">
        <aside className="report-nav-card" aria-label="Report list">
          <div>
            <h2>Reports</h2>
            <p>Choose one export-ready view.</p>
          </div>
          <div className="report-nav-list">
            {allReports.map((report) => (
              <button className={activeReport === report.key ? 'report-nav-button active' : 'report-nav-button'} key={report.key} onClick={() => setActiveReport(report.key)} type="button">
                {report.label}
              </button>
            ))}
          </div>
        </aside>
        <div className="report-main-panel">
          {isExpandedReport && <ExpandedReportsPanel activeReport={activeReport} />}
          {activeReport === 'received-inventory' && <ReceivedInventoryReportPage rows={receivedRows} summary={receivedSummary} loading={receivedLoading} error={receivedError} onLoadReport={onLoadReceivedReport} />}
          {activeReport === 'fulfillment' && <FulfillmentReportPage rows={fulfillmentRows} summary={fulfillmentSummary} loading={fulfillmentLoading} error={fulfillmentError} onLoadReport={onLoadFulfillmentReport} />}
          {activeReport === 'sku-orders' && <SkuOrdersReportPage rows={skuOrdersRows} summary={skuOrdersSummary} loading={skuOrdersLoading} error={skuOrdersError} onLoadReport={onLoadSkuOrdersReport} />}
        </div>
      </div>
    </section>
  );
}

const expandedReportDefinitions = [
  { key: 'inventory-valuation', label: 'Inventory Valuation' },
  { key: 'low-stock', label: 'Low Stock / Reorder' },
  { key: 'stock-movement-ledger', label: 'Stock Movement Ledger' },
  { key: 'item-activity', label: 'Item Activity' },
  { key: 'location-utilization', label: 'Location Utilization' },
  { key: 'margin-by-sku', label: 'Margin by SKU' },
  { key: 'receiving-cost', label: 'Receiving Cost' },
  { key: 'adjustments', label: 'Adjustment / Damage / Loss' },
];

function ExpandedReportsPanel({ activeReport }) {
  const active = activeReport || expandedReportDefinitions[0].key;
  const [filters, setFilters] = useState({ sku: '', barcode: '', brand: '', category: '', warehouse: '', inventory_location: '', start_date: '', end_date: '', movement_type: '', adjustment_type: '' });
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const definition = expandedReportDefinitions.find((report) => report.key === active) || expandedReportDefinitions[0];

  useEffect(() => {
    loadReport();
  }, [active]);

  function update(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  async function loadReport() {
    setLoading(true);
    setError('');
    try {
      const query = plainFiltersToQueryString(filters);
      const [rowsResponse, summaryResponse] = await Promise.all([fetch(`${API_BASE_URL}/api/reports/${active}${query}`), fetch(`${API_BASE_URL}/api/reports/${active}/summary${query}`)]);
      if (!rowsResponse.ok || !summaryResponse.ok) throw new Error('Report API returned an error.');
      setRows(await rowsResponse.json());
      setSummary(await summaryResponse.json());
    } catch (apiError) {
      setRows([]);
      setSummary({});
      setError(apiError.message || 'Unable to load report.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="wide-panel report-section">
      <div className="panel-title"><div><h2>{definition.label}</h2><p>Read-only local inventory and operations report.</p></div></div>
      <div className="summary-strip report-summary-strip">
        {Object.entries(summary).slice(0, 6).map(([key, value]) => <Metric key={key} label={key.replace(/_/g, ' ')} value={typeof value === 'number' ? formatNumber(value) : String(value ?? '')} />)}
        {Object.keys(summary).length === 0 && <Metric label="Rows" value={rows.length} />}
      </div>
      <div className="toolbar report-toolbar">
        <div className="filter-grid report-filter-grid">
          {['start_date', 'end_date'].map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={filters[field]} onChange={(event) => update(field, event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, loadReport)} type="date" /></label>)}
          {['sku', 'barcode', 'brand', 'category', 'warehouse', 'inventory_location', 'movement_type', 'adjustment_type'].map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={filters[field]} onChange={(event) => update(field, event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, loadReport)} /></label>)}
        </div>
        <div className="button-row items-actions"><button className="primary-button" onClick={loadReport} type="button"><RefreshCw size={17} />Refresh</button><button className="action-button" onClick={() => exportGenericReportCsv(active, filters, definition.label)} type="button"><Download size={17} />Export CSV</button></div>
      </div>
      {loading && <div className="loading-strip">Loading {definition.label}...</div>}
      {error && <div className="api-error">{error}</div>}
      <GenericReportTable rows={rows} />
    </section>
  );
}

function GenericReportTable({ rows }) {
  const columns = rows[0] ? Object.keys(rows[0]) : [];
  return (
    <TableShell caption={`${rows.length} row(s)`} columns={columns.length ? columns.map((column) => column.replace(/_/g, ' ')) : ['Report']}>
      {rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column}>{formatReportValue(row[column])}</td>)}</tr>)}
      {!rows.length && <tr><td colSpan={Math.max(columns.length, 1)}><div className="empty-table-row">No report rows match the current filters.</div></td></tr>}
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
    <section className="wide-panel report-section">
      <div className="panel-title">
        <div>
          <h2>Received Inventory Report</h2>
          <p>Read-only receiving rows from posted direct receipts.</p>
        </div>
      </div>
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
              <input value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <label className="field">
            <span>Date To</span>
            <div className="input-with-icon">
              <input value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Inventory Location" value={filters.inventoryLocation} options={options.locations} onChange={(value) => updateFilter('inventoryLocation', value)} />
          <label className="field">
            <span>SKU</span>
            <div className="input-with-icon">
              <input value={filters.sku} onChange={(event) => updateFilter('sku', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Barcode</span>
            <div className="input-with-icon">
              <input value={filters.barcode} onChange={(event) => updateFilter('barcode', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
              <Search size={18} />
            </div>
          </label>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <label className="field">
            <span>Receipt Number</span>
            <div className="input-with-icon">
              <input value={filters.receiptNumber} onChange={(event) => updateFilter('receiptNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Reference Number</span>
            <div className="input-with-icon">
              <input value={filters.referenceNumber} onChange={(event) => updateFilter('referenceNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Created By</span>
            <div className="input-with-icon">
              <input value={filters.createdBy} onChange={(event) => updateFilter('createdBy', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
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
          <button className="pager-button" aria-label="Previous page" title="Pagination is not available yet" disabled type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" title="Pagination is not available yet" disabled type="button">
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

function FulfillmentReportPage({ rows, summary, loading, error, onLoadReport }) {
  const [filters, setFilters] = useState(emptyFulfillmentReportFilters);
  const [activeFilters, setActiveFilters] = useState(emptyFulfillmentReportFilters);
  const options = useMemo(
    () => ({
      warehouses: uniqueOptions(rows, 'warehouse'),
      locations: uniqueOptions(rows, 'inventory_location'),
      categories: uniqueOptions(rows, 'category'),
      brands: uniqueOptions(rows, 'brand'),
      statuses: ['fulfilled', 'partially_fulfilled'],
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
    const cleared = emptyFulfillmentReportFilters();
    setFilters(cleared);
    setActiveFilters(cleared);
    onLoadReport(cleared);
  }

  return (
    <section className="wide-panel report-section">
      <div className="panel-title">
        <div>
          <h2>Fulfillment Report</h2>
          <p>Read-only audit of completed local fulfillment lines.</p>
        </div>
      </div>
      <div className="summary-strip report-summary-strip">
        <Metric label="Fulfillments" value={summary.total_fulfillments || 0} />
        <Metric label="Orders" value={summary.total_orders || 0} />
        <Metric label="Lines" value={summary.total_lines || 0} />
        <Metric label="Qty Fulfilled" value={formatNumber(summary.total_quantity_fulfilled || 0)} />
        <Metric label="Fulfilled Value" value={formatCurrency(summary.total_fulfilled_value || 0)} />
        <Metric label="Unique SKUs" value={summary.unique_skus || 0} />
        <Metric label="Locations" value={summary.unique_locations || 0} />
      </div>
      <div className="toolbar report-toolbar">
        <div className="filter-grid report-filter-grid">
          <label className="field">
            <span>Date From</span>
            <div className="input-with-icon">
              <input value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <label className="field">
            <span>Date To</span>
            <div className="input-with-icon">
              <input value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" />
              <CalendarDays size={18} />
            </div>
          </label>
          <FilterSelect label="Warehouse" value={filters.warehouse} options={options.warehouses} onChange={(value) => updateFilter('warehouse', value)} />
          <FilterSelect label="Inventory Location" value={filters.inventoryLocation} options={options.locations} onChange={(value) => updateFilter('inventoryLocation', value)} />
          <label className="field"><span>SKU</span><div className="input-with-icon"><input value={filters.sku} onChange={(event) => updateFilter('sku', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Barcode</span><div className="input-with-icon"><input value={filters.barcode} onChange={(event) => updateFilter('barcode', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <label className="field"><span>Fulfillment Number</span><div className="input-with-icon"><input value={filters.fulfillmentNumber} onChange={(event) => updateFilter('fulfillmentNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Woo Order Number</span><div className="input-with-icon"><input value={filters.wooOrderNumber} onChange={(event) => updateFilter('wooOrderNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Customer Email</span><div className="input-with-icon"><input value={filters.customerEmail} onChange={(event) => updateFilter('customerEmail', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <FilterSelect label="Local Status" value={filters.localStatus} options={options.statuses} onChange={(value) => updateFilter('localStatus', value)} />
          <label className="field"><span>Created By</span><div className="input-with-icon"><input value={filters.createdBy} onChange={(event) => updateFilter('createdBy', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><UserCircle size={18} /></div></label>
        </div>
        <div className="button-row items-actions">
          <button className="primary-button" onClick={applyFilters} type="button"><Filter size={17} />Apply Filters</button>
          <button className="muted-button" onClick={clearFilters} type="button">Clear Filters</button>
          <button className="action-button" onClick={() => onLoadReport(activeFilters)} type="button"><RefreshCw size={17} />Refresh</button>
          <button className="action-button" onClick={() => exportFulfillmentReportCsv(activeFilters)} type="button"><Download size={17} />Export CSV</button>
        </div>
      </div>
      <div className="csv-note">Fulfillment Report is read-only. It does not modify inventory, allocated quantities, WooCommerce, routes, shipping labels, or notifications.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading fulfillment report...</div>}
      <FulfillmentReportTable rows={rows} />
      <div className="orders-grid allocation-history-grid">
        <div className="wide-panel grouped-report-panel">
          <div className="panel-title"><div><h2>Grouped by Location</h2><p>Quantity and value fulfilled by warehouse location.</p></div></div>
          <FulfillmentLocationSummaryTable groups={summary.by_location || []} />
        </div>
        <div className="wide-panel grouped-report-panel">
          <div className="panel-title"><div><h2>Grouped by SKU</h2><p>Fulfilled value and count by item.</p></div></div>
          <FulfillmentSkuSummaryTable groups={summary.by_sku || []} />
        </div>
      </div>
    </section>
  );
}

function FulfillmentReportTable({ rows }) {
  return (
    <TableShell caption={`${rows.length} fulfillment row(s)`} columns={['Fulfillment', 'Posted At', 'Woo Order', 'Local Status', 'Customer', 'Warehouse', 'Location', 'SKU', 'Barcode', 'Description', 'Category', 'Brand', 'Qty Fulfilled', 'Unit Cost', 'Fulfilled Value', 'Stock Before', 'Stock After', 'Allocated Before', 'Allocated After', 'Created By']}>
      {rows.map((row) => (
        <tr key={`${row.fulfillment_id}-${row.sku}-${row.order_id}`}>
          <td className="mono">{row.fulfillment_number}</td>
          <td>{formatDateTime(row.posted_at || row.created_at)}</td>
          <td className="mono">{row.woo_order_number}</td>
          <td>{StatusText(row.local_status)}</td>
          <td>{row.customer_name}</td>
          <td>{row.warehouse}</td>
          <td>{row.inventory_location}</td>
          <td className="mono">{row.sku}</td>
          <td className="mono">{row.barcode}</td>
          <td className="description-cell">{row.description}</td>
          <td>{row.category}</td>
          <td>{row.brand}</td>
          <td>{formatNumber(row.quantity_fulfilled)}</td>
          <td>{formatCurrency(row.unit_cost)}</td>
          <td>{formatCurrency(row.fulfilled_value)}</td>
          <td>{formatNumber(row.in_stock_before)}</td>
          <td>{formatNumber(row.in_stock_after)}</td>
          <td>{formatNumber(row.allocated_before)}</td>
          <td>{formatNumber(row.allocated_after)}</td>
          <td>{row.created_by}</td>
        </tr>
      ))}
      {rows.length === 0 && (
        <tr><td colSpan={20}><div className="empty-table-row">No fulfillment rows match the current filters.</div></td></tr>
      )}
    </TableShell>
  );
}

function FulfillmentLocationSummaryTable({ groups }) {
  return (
    <TableShell caption={`${groups.length} location group(s)`} columns={['Warehouse', 'Inventory Location', 'Total Lines', 'Qty Fulfilled', 'Fulfilled Value']}>
      {groups.map((group) => (
        <tr key={`${group.warehouse}-${group.inventory_location}`}><td>{group.warehouse || 'Unassigned'}</td><td>{group.inventory_location || 'Unassigned'}</td><td>{group.total_lines}</td><td>{formatNumber(group.total_quantity_fulfilled)}</td><td>{formatCurrency(group.total_fulfilled_value)}</td></tr>
      ))}
      {groups.length === 0 && <tr><td colSpan={5}><div className="empty-table-row">No location groups match the current filters.</div></td></tr>}
    </TableShell>
  );
}

function FulfillmentSkuSummaryTable({ groups }) {
  return (
    <TableShell caption={`${groups.length} SKU group(s)`} columns={['SKU', 'Description', 'Brand', 'Category', 'Qty Fulfilled', 'Fulfilled Value', 'Fulfillments', 'Orders']}>
      {groups.map((group) => (
        <tr key={group.sku}><td className="mono">{group.sku}</td><td className="description-cell">{group.description}</td><td>{group.brand}</td><td>{group.category}</td><td>{formatNumber(group.total_quantity_fulfilled)}</td><td>{formatCurrency(group.total_fulfilled_value)}</td><td>{group.fulfillment_count}</td><td>{group.order_count}</td></tr>
      ))}
      {groups.length === 0 && <tr><td colSpan={8}><div className="empty-table-row">No SKU groups match the current filters.</div></td></tr>}
    </TableShell>
  );
}

function SkuOrdersReportPage({ rows, summary, loading, error, onLoadReport }) {
  const [filters, setFilters] = useState(emptySkuOrdersFilters);
  const [activeFilters, setActiveFilters] = useState(emptySkuOrdersFilters);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function applyFilters() {
    setActiveFilters(filters);
    onLoadReport(filters);
  }

  function clearFilters() {
    const cleared = emptySkuOrdersFilters();
    setFilters(cleared);
    setActiveFilters(cleared);
    onLoadReport(cleared);
  }

  return (
    <section className="wide-panel report-section">
      <div className="panel-title">
        <div>
          <h2>SKU Orders Report</h2>
          <p>Read-only demand report from locally synced WooCommerce order snapshots.</p>
        </div>
      </div>
      <div className="summary-strip report-summary-strip">
        <Metric label="SKUs" value={summary.total_skus || 0} />
        <Metric label="Qty Ordered" value={formatNumber(summary.total_quantity_ordered || 0)} />
        <Metric label="Qty Fulfilled" value={formatNumber(summary.total_quantity_fulfilled || 0)} />
        <Metric label="Unfulfilled" value={formatNumber(summary.total_unfulfilled_quantity || 0)} />
        <Metric label="Unmatched Lines" value={summary.unmatched_lines_count || 0} />
        <Metric label="Top SKU" value={summary.top_sku_by_quantity || 'None'} />
      </div>
      <div className="toolbar report-toolbar">
        <div className="filter-grid report-filter-grid">
          <label className="field"><span>Start Date</span><div className="input-with-icon"><input value={filters.startDate} onChange={(event) => updateFilter('startDate', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" /><CalendarDays size={18} /></div></label>
          <label className="field"><span>End Date</span><div className="input-with-icon"><input value={filters.endDate} onChange={(event) => updateFilter('endDate', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" /><CalendarDays size={18} /></div></label>
          <label className="field"><span>SKU</span><div className="input-with-icon"><input value={filters.sku} onChange={(event) => updateFilter('sku', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Brand</span><input value={filters.brand} onChange={(event) => updateFilter('brand', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /></label>
          <label className="field"><span>Category</span><input value={filters.category} onChange={(event) => updateFilter('category', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /></label>
          <FilterSelect label="Group By" value={filters.groupBy} options={['sku', 'brand', 'category', 'location']} onChange={(value) => updateFilter('groupBy', value)} />
          <label className="toggle-card"><input checked={filters.includeUnmatched} onChange={(event) => updateFilter('includeUnmatched', event.target.checked)} type="checkbox" /><span>Include Unmatched</span></label>
        </div>
        <div className="button-row items-actions">
          <button className="primary-button" onClick={applyFilters} type="button"><Filter size={17} />Apply Filters</button>
          <button className="muted-button" onClick={clearFilters} type="button">Clear Filters</button>
          <button className="action-button" onClick={() => onLoadReport(activeFilters)} type="button"><RefreshCw size={17} />Refresh</button>
          <button className="action-button" onClick={() => exportSkuOrdersCsv(activeFilters)} type="button"><Download size={17} />Export CSV</button>
        </div>
      </div>
      <div className="csv-note">SKU Orders is read-only and does not modify orders, inventory, allocation, picking, fulfillment, routes, or WooCommerce.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading SKU Orders report...</div>}
      <TableShell caption={`${rows.length} SKU order row(s)`} columns={['SKU', 'Item', 'Description', 'Brand', 'Category', 'Location', 'Orders', 'Ordered', 'Allocated', 'Picked', 'Fulfilled', 'Unfulfilled', 'Unmatched Lines', 'First Order', 'Last Order', 'In Stock', 'Sellable', 'Woo Snapshot']}>
        {rows.map((row) => (
          <tr key={`${row.sku}-${row.item_id || row.location || row.brand || row.category}`}>
            <td className="mono">{row.sku}</td>
            <td>{row.item_id || ''}</td>
            <td className="description-cell">{row.description}</td>
            <td>{row.brand}</td>
            <td>{row.category}</td>
            <td>{row.location}</td>
            <td>{row.total_orders_count}</td>
            <td>{formatNumber(row.total_quantity_ordered)}</td>
            <td>{formatNumber(row.total_quantity_allocated)}</td>
            <td>{formatNumber(row.total_quantity_picked)}</td>
            <td>{formatNumber(row.total_quantity_fulfilled)}</td>
            <td>{formatNumber(row.unfulfilled_quantity)}</td>
            <td>{row.unmatched_order_line_count}</td>
            <td>{formatDateTime(row.first_order_date)}</td>
            <td>{formatDateTime(row.last_order_date)}</td>
            <td>{row.current_in_stock == null ? '' : formatNumber(row.current_in_stock)}</td>
            <td>{row.current_sellable == null ? '' : formatNumber(row.current_sellable)}</td>
            <td>{row.woo_stock_snapshot == null ? '' : formatNumber(row.woo_stock_snapshot)}</td>
          </tr>
        ))}
        {rows.length === 0 && <tr><td colSpan={18}><div className="empty-table-row">No SKU order rows match the current filters.</div></td></tr>}
      </TableShell>
    </section>
  );
}

function OrdersPage({
  route,
  ordersData,
  loading,
  error,
  detail,
  onLoadOpenOrders,
  onLoadOpenOrderDetail,
  completedOrders,
  completedOrdersLoading,
  completedOrdersError,
  onLoadCompletedOrders,
  allocationPreview,
  allocationCommitSummary,
  allocationHistory,
  allocationDetail,
  allocationLoading,
  allocationError,
  onPreviewAllocation,
  onCommitAllocation,
  onLoadAllocationDetail,
  pickPreview,
  pickCommitSummary,
  pickHistory,
  pickDetail,
  pickScannerOrder,
  pickScannerMessage,
  pickLoading,
  pickError,
  onPreviewPick,
  onCommitPick,
  onLoadPickDetail,
  onLoadPickScanner,
  onCommitPickScan,
  fulfillmentPreview,
  fulfillmentCommitSummary,
  fulfillmentHistory,
  fulfillmentDetail,
  fulfillmentLoading,
  fulfillmentError,
  onPreviewFulfillment,
  onCommitFulfillment,
  onLoadFulfillmentDetail,
}) {
  const [filters, setFilters] = useState({ search: '', wooStatus: '', availabilityStatus: '', matchedStatus: '' });
  const orders = ordersData.orders || [];
  const selectedOrderId = detail?.id;
  const view = route.ordersView || 'open';

  useEffect(() => {
    if (view === 'pick' && selectedOrderId) {
      onLoadPickScanner(selectedOrderId);
    }
  }, [view, selectedOrderId]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function clearFilters() {
    const cleared = { search: '', wooStatus: '', availabilityStatus: '', matchedStatus: '' };
    setFilters(cleared);
    onLoadOpenOrders(cleared);
  }

  const summaryCards = (
    <div className="summary-strip order-summary-strip">
      <Metric label="Open Orders" value={ordersData.total || 0} />
      <Metric label="Available" value={ordersData.available_count || 0} />
      <Metric label="Partial" value={ordersData.partial_count || 0} />
      <Metric label="Unavailable" value={ordersData.unavailable_count || 0} />
      <Metric label="Unknown" value={ordersData.unknown_count || 0} />
    </div>
  );

  const filtersPanel = (
    <div className="filter-panel">
      <div className="filter-grid orders-filter-grid">
        <label className="field">
          <span>Search</span>
          <div className="input-with-icon">
            <Search size={18} />
            <input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadOpenOrders(filters))} placeholder="Order, customer, SKU, barcode" type="search" />
          </div>
        </label>
        <FilterSelect label="Woo Status" value={filters.wooStatus} options={['processing', 'on-hold']} onChange={(value) => updateFilter('wooStatus', value)} />
        <FilterSelect label="Availability" value={filters.availabilityStatus} options={['available', 'partial', 'unavailable', 'unknown']} onChange={(value) => updateFilter('availabilityStatus', value)} />
        <FilterSelect label="Matched" value={filters.matchedStatus} options={['matched', 'unmatched', 'conflict', 'unknown']} onChange={(value) => updateFilter('matchedStatus', value)} />
      </div>
      <div className="button-row">
        <button className="muted-button" onClick={clearFilters} type="button">
          <SlidersHorizontal size={17} />
          Clear
        </button>
        <button className="primary-button" onClick={() => onLoadOpenOrders(filters)} disabled={loading} type="button">
          <Filter size={17} />
          Apply
        </button>
      </div>
    </div>
  );

  const openStatus = (
    <>
      {loading && <div className="loading-strip">Loading open orders...</div>}
      {error && <div className="api-error">{error}</div>}
    </>
  );

  const selectedLabel = selectedOrderId ? `Order ${detail?.woo_order_number || detail?.woo_order_id || selectedOrderId}` : 'Select an order to continue.';

  if (view === 'completed') {
    return (
      <section className="content-panel orders-page">
        <CompletedOrdersPanel ordersData={completedOrders} loading={completedOrdersLoading} error={completedOrdersError} onLoadCompletedOrders={onLoadCompletedOrders} />
      </section>
    );
  }

  if (view === 'history') {
    return (
      <section className="content-panel orders-page">
        <div className="wide-panel">
          <div className="panel-title">
            <div>
              <h2>Order History</h2>
              <p>Read-only local allocation, pick, and fulfillment records.</p>
            </div>
            <div className="button-row compact">
              <button className="muted-button" onClick={() => { onLoadAllocationDetail(null); onLoadFulfillmentDetail(null); onLoadPickDetail(null); }} type="button">
                Clear Details
              </button>
            </div>
          </div>
        </div>
        {allocationError && <div className="api-error">{allocationError}</div>}
        {pickError && <div className="api-error">{pickError}</div>}
        {fulfillmentError && <div className="api-error">{fulfillmentError}</div>}
        <AllocationHistoryPanel allocations={allocationHistory} detail={allocationDetail} onSelect={onLoadAllocationDetail} />
        <PickHistoryPanel picks={pickHistory} detail={pickDetail} onSelect={onLoadPickDetail} />
        <FulfillmentHistoryPanel fulfillments={fulfillmentHistory} detail={fulfillmentDetail} onSelect={onLoadFulfillmentDetail} />
      </section>
    );
  }

  if (view === 'allocate') {
    return (
      <section className="content-panel orders-page">
        <div className="wide-panel">
          <OrdersWorkflowHeader title="Allocate Orders" description="Reserve local Pongo OS inventory for open WooCommerce order snapshots." loading={loading || allocationLoading} onRefresh={() => onLoadOpenOrders(filters)} onExport={() => exportOpenOrdersCsv(filters)} />
          {summaryCards}
          {filtersPanel}
          <div className="csv-note">Allocation reserves local inventory only. It does not update WooCommerce, reduce In Stock, or pick orders.</div>
          <div className="context-action-panel">
            <div>
              <span>Allocation workflow</span>
              <strong>{selectedLabel}</strong>
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => onPreviewAllocation(selectedOrderId)} disabled={!selectedOrderId || allocationLoading} type="button">
                <ClipboardList size={17} />
                Preview Allocation
              </button>
              <button className="action-button" onClick={() => onCommitAllocation(selectedOrderId)} disabled={!selectedOrderId || allocationLoading || !allocationPreview} type="button">
                <CheckCircle2 size={17} />
                Commit Allocation
              </button>
            </div>
          </div>
          {openStatus}
          {allocationLoading && <div className="loading-strip">Working on allocation...</div>}
          {allocationError && <div className="api-error">{allocationError}</div>}
          {allocationCommitSummary && <OrderWorkflowSummary summary={allocationCommitSummary} type="Allocation" quantityField="total_quantity_allocated" />}
        </div>
        {allocationPreview && <AllocationPreviewPanel preview={allocationPreview} />}
        <div className="orders-grid">
          <OpenOrdersTable orders={orders} selectedOrderId={detail?.id} onSelect={onLoadOpenOrderDetail} renderActions={(order) => (
            <div className="button-row compact table-button-row">
              <button className="muted-button" onClick={() => onLoadOpenOrderDetail(order.id)} type="button">View</button>
              <button className="primary-button" onClick={() => { onLoadOpenOrderDetail(order.id); onPreviewAllocation(order.id); }} disabled={allocationLoading} type="button">Preview</button>
            </div>
          )} />
          <OpenOrderDetailPanel order={detail} />
        </div>
      </section>
    );
  }

  if (view === 'pick') {
    return (
      <section className="content-panel orders-page">
        <div className="wide-panel">
          <OrdersWorkflowHeader title="Pick Orders" description="Scan allocated order lines and record local picking progress." loading={loading || pickLoading} onRefresh={() => onLoadOpenOrders(filters)} onExport={() => exportOpenOrdersCsv(filters)} />
          {summaryCards}
          {filtersPanel}
          <div className="csv-note">Picking records operational progress only. It does not update WooCommerce and does not reduce In Stock.</div>
          <div className="context-action-panel">
            <div>
              <span>Picking workflow</span>
              <strong>{selectedOrderId ? selectedLabel : 'Select an allocated order to start picking.'}</strong>
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => onPreviewPick(selectedOrderId)} disabled={!selectedOrderId || pickLoading} type="button">
                <ClipboardCheck size={17} />
                Preview Pick
              </button>
              <button className="action-button" onClick={() => onCommitPick(selectedOrderId)} disabled={!selectedOrderId || pickLoading || !pickPreview} type="button">
                <CheckCircle2 size={17} />
                Commit Pick
              </button>
            </div>
          </div>
          {openStatus}
          {pickLoading && <div className="loading-strip">Working on picking...</div>}
          {pickError && <div className="api-error">{pickError}</div>}
          {pickCommitSummary && <OrderWorkflowSummary summary={pickCommitSummary} type="Pick" quantityField="total_quantity_picked" />}
        </div>
        <div className="orders-grid">
          <OpenOrdersTable orders={orders} selectedOrderId={detail?.id} onSelect={onLoadOpenOrderDetail} renderActions={(order) => (
            <div className="button-row compact table-button-row">
              <button className="muted-button" onClick={() => onLoadOpenOrderDetail(order.id)} type="button">Select</button>
              <button className="primary-button" onClick={() => { onLoadOpenOrderDetail(order.id); onPreviewPick(order.id); }} disabled={pickLoading} type="button">Preview</button>
            </div>
          )} />
          <OpenOrderDetailPanel order={detail} />
        </div>
        <PickScannerPanel order={pickScannerOrder} message={pickScannerMessage} loading={pickLoading} onScan={(skuOrBarcode, quantity) => onCommitPickScan(selectedOrderId, skuOrBarcode, quantity)} />
        {pickPreview && <PickPreviewPanel preview={pickPreview} />}
      </section>
    );
  }

  if (view === 'fulfillment') {
    return (
      <section className="content-panel orders-page">
        <div className="wide-panel">
          <OrdersWorkflowHeader title="Fulfillment" description="Complete picked local orders and reduce local Pongo OS inventory." loading={loading || fulfillmentLoading} onRefresh={() => onLoadOpenOrders(filters)} onExport={() => exportOpenOrdersCsv(filters)} />
          {summaryCards}
          {filtersPanel}
          <div className="csv-note">Fulfillment reduces local Pongo OS inventory only. It does not update WooCommerce order status or WooCommerce stock.</div>
          <div className="context-action-panel">
            <div>
              <span>Fulfillment workflow</span>
              <strong>{selectedLabel}</strong>
            </div>
            <div className="button-row">
              <button className="primary-button" onClick={() => onPreviewFulfillment(selectedOrderId)} disabled={!selectedOrderId || fulfillmentLoading} type="button">
                <PackagePlus size={17} />
                Preview Fulfillment
              </button>
              <button className="action-button" onClick={() => onCommitFulfillment(selectedOrderId)} disabled={!selectedOrderId || fulfillmentLoading || !fulfillmentPreview} type="button">
                <CheckCircle2 size={17} />
                Commit Fulfillment
              </button>
            </div>
          </div>
          {openStatus}
          {fulfillmentLoading && <div className="loading-strip">Working on fulfillment...</div>}
          {fulfillmentError && <div className="api-error">{fulfillmentError}</div>}
          {fulfillmentCommitSummary && <OrderWorkflowSummary summary={fulfillmentCommitSummary} type="Fulfillment" quantityField="total_quantity_fulfilled" />}
        </div>
        {fulfillmentPreview && <FulfillmentPreviewPanel preview={fulfillmentPreview} />}
        <div className="orders-grid">
          <OpenOrdersTable orders={orders} selectedOrderId={detail?.id} onSelect={onLoadOpenOrderDetail} renderActions={(order) => (
            <div className="button-row compact table-button-row">
              <button className="muted-button" onClick={() => onLoadOpenOrderDetail(order.id)} type="button">View</button>
              <button className="primary-button" onClick={() => { onLoadOpenOrderDetail(order.id); onPreviewFulfillment(order.id); }} disabled={fulfillmentLoading} type="button">Preview</button>
            </div>
          )} />
          <OpenOrderDetailPanel order={detail} />
        </div>
      </section>
    );
  }

  return (
    <section className="content-panel orders-page">
      <div className="wide-panel">
        <OrdersWorkflowHeader title="Open Orders" description="Read-only local order queue imported from WooCommerce processing and on-hold orders." loading={loading} onRefresh={() => onLoadOpenOrders(filters)} onExport={() => exportOpenOrdersCsv(filters)} />
        {summaryCards}
        {filtersPanel}
        <div className="csv-note">Orders are local snapshots imported from WooCommerce. This page does not update WooCommerce.</div>
        {openStatus}
        {allocationError && <div className="api-error">{allocationError}</div>}
        {allocationCommitSummary && <OrderWorkflowSummary summary={allocationCommitSummary} type="Allocation" quantityField="total_quantity_allocated" />}
      </div>
      <div className="orders-grid">
        <OpenOrdersTable orders={orders} selectedOrderId={detail?.id} onSelect={onLoadOpenOrderDetail} renderActions={(order) => (
          <div className="button-row compact table-button-row">
            <button className="muted-button" onClick={() => onLoadOpenOrderDetail(order.id)} type="button">View Details</button>
            <button className="primary-button" onClick={() => { onLoadOpenOrderDetail(order.id); onPreviewAllocation(order.id); }} disabled={allocationLoading} type="button">Preview Allocation</button>
            <button className="action-button" onClick={() => onCommitAllocation(order.id)} disabled={allocationLoading} type="button">Allocate</button>
          </div>
        )} />
        <OpenOrderDetailPanel order={detail} />
      </div>
    </section>
  );
}

function OrdersWorkflowHeader({ title, description, loading, onRefresh, onExport }) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      <div className="button-row compact">
        <button className="muted-button" onClick={onRefresh} disabled={loading} type="button">
          <RefreshCw size={17} />
          Refresh
        </button>
        <button className="action-button" onClick={onExport} type="button">
          <Download size={17} />
          Export
        </button>
      </div>
    </div>
  );
}

function OrderWorkflowSummary({ summary, type, quantityField }) {
  return (
    <div className={summary.errors?.length ? 'api-error' : 'success-strip'}>
      {type} {summary.allocation_number || summary.pick_number || summary.fulfillment_number || ''} finished with status {summary.status}. {formatNumber(summary[quantityField])} unit(s).
      {(summary.errors || []).join(' ')}
    </div>
  );
}

function OpenOrdersTable({ orders, selectedOrderId, onSelect, renderActions }) {
  const columns = ['Order', 'Local Status', 'Woo Status', 'Customer', 'Email', 'Total', 'Availability', 'Matched', 'Lines', 'Created', 'Last Sync'];
  if (renderActions) {
    columns.push('Actions');
  }
  return (
    <TableShell caption={`${orders.length} open order(s)`} columns={columns}>
      {orders.map((order) => (
        <tr key={order.id} className={selectedOrderId === order.id ? 'selected-row' : ''} onClick={() => onSelect(order.id)}>
          <td className="mono">{order.woo_order_number || order.woo_order_id}</td>
          <td>{StatusText(order.local_status)}</td>
          <td>{StatusText(order.woo_status)}</td>
          <td>{order.customer_name}</td>
          <td>{order.customer_email}</td>
          <td>{formatCurrency(order.total)}</td>
          <td>{StatusText(order.availability_status)}</td>
          <td>{StatusText(order.matched_status)}</td>
          <td>{order.line_count}</td>
          <td>{formatDateTime(order.date_created)}</td>
          <td>{formatDateTime(order.last_synced_at)}</td>
          {renderActions && (
            <td onClick={(event) => event.stopPropagation()}>
              {renderActions(order)}
            </td>
          )}
        </tr>
      ))}
      {orders.length === 0 && (
        <tr>
          <td colSpan={columns.length}>
            <div className="empty-table-row">No local open orders match the current filters.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function OpenOrderDetailPanel({ order }) {
  if (!order) {
    return (
      <aside className="order-detail-panel">
        <div className="empty-state">
          <h2>No order selected</h2>
          <p>Preview or commit WooCommerce order sync from Settings, then select an open order here.</p>
        </div>
      </aside>
    );
  }
  return (
    <aside className="order-detail-panel">
      <div className="panel-title compact-title">
        <div>
          <h2>Order {order.woo_order_number || order.woo_order_id}</h2>
          <p>{order.customer_name || 'Customer'} · {formatCurrency(order.total)}</p>
        </div>
      </div>
      <div className="detail-kv-grid">
        <Metric label="Local Status" value={order.local_status || ''} />
        <Metric label="Woo Status" value={order.woo_status || ''} />
        <Metric label="Availability" value={order.availability_status || ''} />
        <Metric label="Matched" value={order.matched_status || ''} />
        <Metric label="Lines" value={order.line_count || 0} />
      </div>
      <div className="detail-address">
        <strong>{order.customer_email || 'No email'}</strong>
        <span>{order.customer_phone || 'No phone'}</span>
        <span>{formatAddressSummary(order.shipping_summary)}</span>
      </div>
      <TableShell caption={`${order.lines?.length || 0} line(s)`} columns={['SKU', 'Barcode', 'Name', 'Ordered', 'Allocated', 'Picked', 'Fulfilled', 'Remaining To Pick', 'Remaining To Fulfill', 'Remaining To Allocate', 'Match', 'Availability', 'Pick Status', 'Fulfillment Status', 'Short', 'Local Sellable', 'Woo Product', 'Woo Variation']}>
        {(order.lines || []).map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.name}</td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_allocated)}</td>
            <td>{formatNumber(line.quantity_picked)}</td>
            <td>{formatNumber(line.quantity_fulfilled)}</td>
            <td>{formatNumber(line.remaining_to_pick)}</td>
            <td>{formatNumber(line.remaining_to_fulfill)}</td>
            <td>{formatNumber(line.remaining_to_allocate)}</td>
            <td>{StatusText(line.matched_status)}</td>
            <td>{StatusText(line.availability_status)}</td>
            <td>{StatusText(line.picking_status)}</td>
            <td>{StatusText(line.fulfillment_status)}</td>
            <td>{formatNumber(line.shortage_quantity)}</td>
            <td>{formatNumber(line.local_sellable ?? line.sellable_snapshot)}</td>
            <td className="mono">{line.woo_product_id}</td>
            <td className="mono">{line.woo_variation_id}</td>
          </tr>
        ))}
      </TableShell>
    </aside>
  );
}

function PickScannerPanel({ order, message, loading, onScan }) {
  const [scan, setScan] = useState('');
  const [quantity, setQuantity] = useState(1);

  useEffect(() => {
    const input = document.querySelector('[data-pick-scan-input="true"]');
    if (input) input.focus();
  }, [order?.order_id, message]);

  function submit(event) {
    event.preventDefault();
    if (!scan.trim()) return;
    onScan(scan.trim(), quantity);
    setScan('');
  }

  const lines = order?.lines || [];
  return (
    <div className="wide-panel allocation-panel">
      <div className="panel-title">
        <div>
          <h2>Pick Scanner</h2>
          <p>{order ? `Order ${order.woo_order_number || order.order_id}: ${order.complete_lines}/${order.line_count} lines complete.` : 'Select an allocated order to scan picks.'}</p>
        </div>
      </div>
      <form className="receiving-form route-form" onSubmit={submit}>
        <div className="receiving-header-fields route-header-fields">
          <label className="field wide-field"><span>SKU / Barcode</span><input data-pick-scan-input="true" value={scan} onChange={(event) => setScan(event.target.value)} placeholder="Scan or type SKU/barcode" /></label>
          <label className="field"><span>Qty</span><input value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" /></label>
        </div>
        <div className="button-row"><button className="primary-button" disabled={!order || loading || !scan.trim()} type="submit"><ClipboardCheck size={17} />Commit Scan</button></div>
      </form>
      {message && <div className={message.includes('exceeds') || message.includes('not') ? 'api-error' : 'success-strip'}>{message}</div>}
      <TableShell caption={`${lines.length} scanner line(s)`} columns={['Status', 'SKU', 'Barcode', 'Description', 'Ordered', 'Allocated', 'Picked', 'Remaining', 'Location', 'Warnings']}>
        {lines.map((line) => (
          <tr key={line.order_line_id}>
            <td>{StatusText(line.status)}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.description}</td>
            <td>{formatNumber(line.ordered_quantity)}</td>
            <td>{formatNumber(line.allocated_quantity)}</td>
            <td>{formatNumber(line.picked_quantity)}</td>
            <td>{formatNumber(line.remaining_to_pick)}</td>
            <td>{line.inventory_location}</td>
            <td className="description-cell">{(line.warnings || []).join(' ')}</td>
          </tr>
        ))}
        {lines.length === 0 && <tr><td colSpan={10}><div className="empty-table-row">No scanner lines loaded for the selected order.</div></td></tr>}
      </TableShell>
    </div>
  );
}

function PickPreviewPanel({ preview }) {
  const rows = (preview.preview_orders || []).flatMap((order) => (order.lines || []).map((line) => ({ order, line })));
  return (
    <div className="wide-panel allocation-panel">
      <div className="panel-title">
        <div>
          <h2>Pick Preview</h2>
          <p>Recommended pick quantities from already allocated order lines.</p>
        </div>
      </div>
      <div className="summary-strip allocation-summary-strip">
        <Metric label="Orders" value={preview.total_orders} />
        <Metric label="Lines" value={preview.total_lines} />
        <Metric label="Pickable" value={preview.pickable_lines} />
        <Metric label="Partial" value={preview.partial_lines} />
        <Metric label="Skipped" value={preview.skipped_lines} />
        <Metric label="Qty Pick" value={formatNumber(preview.total_quantity_to_pick)} />
      </div>
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Description', 'Warehouse', 'Location', 'Ordered', 'Allocated', 'Previously Picked', 'Remaining To Pick', 'Recommended', 'Picked After', 'Status', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.description}</td>
            <td>{line.warehouse}</td>
            <td>{line.inventory_location}</td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_allocated)}</td>
            <td>{formatNumber(line.quantity_previously_picked)}</td>
            <td>{formatNumber(line.remaining_to_pick)}</td>
            <td>{formatNumber(line.recommended_pick_quantity)}</td>
            <td>{formatNumber(line.quantity_picked_after)}</td>
            <td>{StatusText(line.pick_status)}</td>
            <td className="description-cell">{(line.warnings || []).join(' ')}</td>
            <td className="description-cell">{(line.errors || []).join(' ')}</td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function FulfillmentPreviewPanel({ preview }) {
  const rows = (preview.preview_orders || []).flatMap((order) => (order.lines || []).map((line) => ({ order, line })));
  return (
    <div className="wide-panel allocation-panel">
      <div className="panel-title">
        <div>
          <h2>Fulfillment Preview</h2>
          <p>Recommended completion quantities from already picked order lines.</p>
        </div>
      </div>
      <div className="summary-strip allocation-summary-strip">
        <Metric label="Orders" value={preview.total_orders} />
        <Metric label="Lines" value={preview.total_lines} />
        <Metric label="Fulfillable" value={preview.fulfillable_lines} />
        <Metric label="Partial" value={preview.partial_lines} />
        <Metric label="Skipped" value={preview.skipped_lines} />
        <Metric label="Qty Fulfill" value={formatNumber(preview.total_quantity_to_fulfill)} />
      </div>
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Description', 'Ordered', 'Allocated', 'Picked', 'Previously Fulfilled', 'Remaining To Fulfill', 'Recommended', 'Status', 'In Stock', 'Allocated Stock', 'Sellable', 'Warehouse', 'Location', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.description}</td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_allocated)}</td>
            <td>{formatNumber(line.quantity_picked)}</td>
            <td>{formatNumber(line.quantity_previously_fulfilled)}</td>
            <td>{formatNumber(line.remaining_to_fulfill)}</td>
            <td>{formatNumber(line.recommended_fulfill_quantity)}</td>
            <td>{StatusText(line.fulfillment_status)}</td>
            <td>{formatNumber(line.in_stock)}</td>
            <td>{formatNumber(line.allocated)}</td>
            <td>{formatNumber(line.sellable)}</td>
            <td>{line.warehouse}</td>
            <td>{line.inventory_location}</td>
            <td className="description-cell">{(line.warnings || []).join(' ')}</td>
            <td className="description-cell">{(line.errors || []).join(' ')}</td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function AllocationPreviewPanel({ preview }) {
  const rows = (preview.preview_orders || []).flatMap((order) => (order.lines || []).map((line) => ({ order, line })));
  return (
    <div className="wide-panel allocation-panel">
      <div className="panel-title">
        <div>
          <h2>Allocation Preview</h2>
          <p>Recommended local reservations for the selected open order.</p>
        </div>
      </div>
      <div className="summary-strip allocation-summary-strip">
        <Metric label="Orders" value={preview.total_orders} />
        <Metric label="Lines" value={preview.total_lines} />
        <Metric label="Allocatable" value={preview.allocatable_lines} />
        <Metric label="Partial" value={preview.partial_lines} />
        <Metric label="Skipped" value={preview.skipped_lines} />
        <Metric label="Qty Allocate" value={formatNumber(preview.total_quantity_to_allocate)} />
        <Metric label="Shortage" value={formatNumber(preview.total_shortage_quantity)} />
      </div>
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Description', 'Ordered', 'Previously Allocated', 'Remaining', 'In Stock', 'Allocated', 'Sellable', 'Recommended', 'Shortage', 'Status', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell">{line.description}</td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_previously_allocated)}</td>
            <td>{formatNumber(line.remaining_to_allocate)}</td>
            <td>{formatNumber(line.in_stock)}</td>
            <td>{formatNumber(line.allocated)}</td>
            <td>{formatNumber(line.sellable)}</td>
            <td>{formatNumber(line.recommended_allocate_quantity)}</td>
            <td>{formatNumber(line.shortage_quantity)}</td>
            <td>{StatusText(line.allocation_status)}</td>
            <td className="description-cell">{(line.warnings || []).join(' ')}</td>
            <td className="description-cell">{(line.errors || []).join(' ')}</td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function AllocationHistoryPanel({ allocations, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Allocation History</h2>
            <p>Posted local allocation records. Picking is not built yet.</p>
          </div>
        </div>
        <TableShell caption={`${allocations.length} allocation(s)`} columns={['Allocation', 'Status', 'Woo Order', 'Lines', 'Qty Allocated', 'Created By', 'Created At', 'Posted At']}>
          {allocations.map((allocation) => (
            <tr key={allocation.id} className={detail?.id === allocation.id ? 'selected-row' : ''} onClick={() => onSelect(allocation.id)}>
              <td className="mono">{allocation.allocation_number}</td>
              <td>{StatusText(allocation.status)}</td>
              <td className="mono">{allocation.woo_order_number}</td>
              <td>{allocation.total_lines}</td>
              <td>{formatNumber(allocation.total_quantity_allocated)}</td>
              <td>{allocation.created_by}</td>
              <td>{formatDateTime(allocation.created_at)}</td>
              <td>{formatDateTime(allocation.posted_at)}</td>
            </tr>
          ))}
          {allocations.length === 0 && (
            <tr>
              <td colSpan={8}>
                <div className="empty-table-row">No allocations have been posted yet.</div>
              </td>
            </tr>
          )}
        </TableShell>
      </div>
      <AllocationDetailPanel allocation={detail} />
    </div>
  );
}

function AllocationDetailPanel({ allocation }) {
  if (!allocation) {
    return (
      <aside className="order-detail-panel">
        <div className="empty-state">
          <h2>No allocation selected</h2>
          <p>Select an allocation from history to review its reserved quantities.</p>
        </div>
      </aside>
    );
  }
  return (
    <aside className="order-detail-panel">
      <div className="panel-title compact-title">
        <div>
          <h2>{allocation.allocation_number}</h2>
          <p>{allocation.status} · {formatNumber(allocation.total_quantity_allocated)} reserved</p>
        </div>
        <button className="action-button" onClick={() => exportAllocationCsv(allocation.id, allocation.allocation_number)} type="button">
          <Download size={17} />
          Export
        </button>
      </div>
      <TableShell caption={`${allocation.lines?.length || 0} allocation line(s)`} columns={['SKU', 'Qty', 'Allocated After', 'Before Sellable', 'After Sellable', 'Status']}>
        {(allocation.lines || []).map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td>{formatNumber(line.quantity_to_allocate)}</td>
            <td>{formatNumber(line.quantity_allocated_after)}</td>
            <td>{formatNumber(line.sellable_before)}</td>
            <td>{formatNumber(line.sellable_after)}</td>
            <td>{StatusText(line.status)}</td>
          </tr>
        ))}
      </TableShell>
    </aside>
  );
}

function PickHistoryPanel({ picks, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Pick History</h2>
            <p>Posted local pick records. Picking does not reduce In Stock or Allocated.</p>
          </div>
        </div>
        <TableShell caption={`${picks.length} pick(s)`} columns={['Pick', 'Status', 'Woo Order', 'Lines', 'Qty Picked', 'Created By', 'Created At', 'Posted At']}>
          {picks.map((pick) => (
            <tr key={pick.id} className={detail?.id === pick.id ? 'selected-row' : ''} onClick={() => onSelect(pick.id)}>
              <td className="mono">{pick.pick_number}</td>
              <td>{StatusText(pick.status)}</td>
              <td className="mono">{pick.woo_order_number}</td>
              <td>{pick.total_lines}</td>
              <td>{formatNumber(pick.total_quantity_picked)}</td>
              <td>{pick.created_by}</td>
              <td>{formatDateTime(pick.created_at)}</td>
              <td>{formatDateTime(pick.posted_at)}</td>
            </tr>
          ))}
          {picks.length === 0 && (
            <tr>
              <td colSpan={8}>
                <div className="empty-table-row">No picks have been posted yet.</div>
              </td>
            </tr>
          )}
        </TableShell>
      </div>
      <PickDetailPanel pick={detail} />
    </div>
  );
}

function PickDetailPanel({ pick }) {
  if (!pick) {
    return (
      <aside className="order-detail-panel">
        <div className="empty-state">
          <h2>No pick selected</h2>
          <p>Select a pick from history to review picked quantities.</p>
        </div>
      </aside>
    );
  }
  return (
    <aside className="order-detail-panel">
      <div className="panel-title compact-title">
        <div>
          <h2>{pick.pick_number}</h2>
          <p>{pick.status} · {formatNumber(pick.total_quantity_picked)} picked</p>
        </div>
        <button className="action-button" onClick={() => exportPickCsv(pick.id, pick.pick_number)} type="button">
          <Download size={17} />
          Export
        </button>
      </div>
      <TableShell caption={`${pick.lines?.length || 0} pick line(s)`} columns={['SKU', 'Picked', 'Picked After', 'Remaining', 'Warehouse', 'Location', 'Status']}>
        {(pick.lines || []).map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td>{formatNumber(line.quantity_to_pick)}</td>
            <td>{formatNumber(line.quantity_picked_after)}</td>
            <td>{formatNumber(line.remaining_to_pick)}</td>
            <td>{line.warehouse}</td>
            <td>{line.inventory_location}</td>
            <td>{StatusText(line.status)}</td>
          </tr>
        ))}
      </TableShell>
    </aside>
  );
}

function FulfillmentHistoryPanel({ fulfillments, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Fulfillment History</h2>
            <p>Posted local completion records that reduce In Stock and Allocated.</p>
          </div>
        </div>
        <TableShell caption={`${fulfillments.length} fulfillment(s)`} columns={['Fulfillment', 'Status', 'Woo Order', 'Lines', 'Qty Fulfilled', 'Created By', 'Created At', 'Posted At']}>
          {fulfillments.map((fulfillment) => (
            <tr key={fulfillment.id} className={detail?.id === fulfillment.id ? 'selected-row' : ''} onClick={() => onSelect(fulfillment.id)}>
              <td className="mono">{fulfillment.fulfillment_number}</td>
              <td>{StatusText(fulfillment.status)}</td>
              <td className="mono">{fulfillment.woo_order_number}</td>
              <td>{fulfillment.total_lines}</td>
              <td>{formatNumber(fulfillment.total_quantity_fulfilled)}</td>
              <td>{fulfillment.created_by}</td>
              <td>{formatDateTime(fulfillment.created_at)}</td>
              <td>{formatDateTime(fulfillment.posted_at)}</td>
            </tr>
          ))}
          {fulfillments.length === 0 && (
            <tr>
              <td colSpan={8}>
                <div className="empty-table-row">No fulfillments have been posted yet.</div>
              </td>
            </tr>
          )}
        </TableShell>
      </div>
      <FulfillmentDetailPanel fulfillment={detail} />
    </div>
  );
}

function FulfillmentDetailPanel({ fulfillment }) {
  if (!fulfillment) {
    return (
      <aside className="order-detail-panel">
        <div className="empty-state">
          <h2>No fulfillment selected</h2>
          <p>Select a fulfillment from history to review completed quantities.</p>
        </div>
      </aside>
    );
  }
  return (
    <aside className="order-detail-panel">
      <div className="panel-title compact-title">
        <div>
          <h2>{fulfillment.fulfillment_number}</h2>
          <p>{fulfillment.status} · {formatNumber(fulfillment.total_quantity_fulfilled)} fulfilled</p>
        </div>
        <button className="action-button" onClick={() => exportFulfillmentCsv(fulfillment.id, fulfillment.fulfillment_number)} type="button">
          <Download size={17} />
          Export
        </button>
      </div>
      <TableShell caption={`${fulfillment.lines?.length || 0} fulfillment line(s)`} columns={['SKU', 'Fulfilled', 'Fulfilled After', 'Remaining', 'Before Stock', 'After Stock', 'Before Allocated', 'After Allocated', 'Status']}>
        {(fulfillment.lines || []).map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td>{formatNumber(line.quantity_to_fulfill)}</td>
            <td>{formatNumber(line.quantity_fulfilled_after)}</td>
            <td>{formatNumber(line.remaining_to_fulfill)}</td>
            <td>{formatNumber(line.in_stock_before)}</td>
            <td>{formatNumber(line.in_stock_after)}</td>
            <td>{formatNumber(line.allocated_before)}</td>
            <td>{formatNumber(line.allocated_after)}</td>
            <td>{StatusText(line.status)}</td>
          </tr>
        ))}
      </TableShell>
    </aside>
  );
}

function CompletedOrdersPanel({ ordersData, loading, error, onLoadCompletedOrders }) {
  const [filters, setFilters] = useState(emptyCompletedOrderFilters);
  const [activeFilters, setActiveFilters] = useState(emptyCompletedOrderFilters);
  const orders = ordersData.orders || [];
  const totals = orders.reduce(
    (acc, order) => ({
      quantityFulfilled: acc.quantityFulfilled + Number(order.total_quantity_fulfilled || 0),
      remaining: acc.remaining + Number(order.total_remaining_to_fulfill || 0),
      value: acc.value + Number(order.total_fulfilled_value || 0),
    }),
    { quantityFulfilled: 0, remaining: 0, value: 0 },
  );

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function applyFilters() {
    setActiveFilters(filters);
    onLoadCompletedOrders(filters);
  }

  function clearFilters() {
    const cleared = emptyCompletedOrderFilters();
    setFilters(cleared);
    setActiveFilters(cleared);
    onLoadCompletedOrders(cleared);
  }

  return (
    <div className="wide-panel">
      <div className="panel-title">
        <div>
          <h2>Completed Orders</h2>
          <p>Read-only view of fulfilled and partially fulfilled local orders.</p>
        </div>
        <div className="button-row compact">
          <button className="muted-button" onClick={() => onLoadCompletedOrders(activeFilters)} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
          <button className="action-button" onClick={() => exportCompletedOrdersCsv(activeFilters)} type="button"><Download size={17} />Export CSV</button>
        </div>
      </div>
      <div className="summary-strip report-summary-strip">
        <Metric label="Orders" value={ordersData.total || 0} />
        <Metric label="Qty Fulfilled" value={formatNumber(totals.quantityFulfilled)} />
        <Metric label="Remaining" value={formatNumber(totals.remaining)} />
        <Metric label="Fulfilled Value" value={formatCurrency(totals.value)} />
      </div>
      <div className="filter-panel">
        <div className="filter-grid orders-filter-grid">
          <FilterSelect label="Local Status" value={filters.localStatus} options={['fulfilled', 'partially_fulfilled']} onChange={(value) => updateFilter('localStatus', value)} />
          <label className="field"><span>Date From</span><div className="input-with-icon"><input value={filters.dateFrom} onChange={(event) => updateFilter('dateFrom', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" /><CalendarDays size={18} /></div></label>
          <label className="field"><span>Date To</span><div className="input-with-icon"><input value={filters.dateTo} onChange={(event) => updateFilter('dateTo', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} type="date" /><CalendarDays size={18} /></div></label>
          <label className="field"><span>Customer Email</span><div className="input-with-icon"><input value={filters.customerEmail} onChange={(event) => updateFilter('customerEmail', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Woo Order Number</span><div className="input-with-icon"><input value={filters.wooOrderNumber} onChange={(event) => updateFilter('wooOrderNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>SKU</span><div className="input-with-icon"><input value={filters.sku} onChange={(event) => updateFilter('sku', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Barcode</span><div className="input-with-icon"><input value={filters.barcode} onChange={(event) => updateFilter('barcode', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
          <label className="field"><span>Search</span><div className="input-with-icon"><input value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} /><Search size={18} /></div></label>
        </div>
        <div className="button-row">
          <button className="muted-button" onClick={clearFilters} type="button"><SlidersHorizontal size={17} />Clear</button>
          <button className="primary-button" onClick={applyFilters} disabled={loading} type="button"><Filter size={17} />Apply</button>
        </div>
      </div>
      <div className="csv-note">Completed Orders is read-only and does not modify inventory, WooCommerce, routes, shipping labels, or notifications.</div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading completed orders...</div>}
      <TableShell caption={`${orders.length} completed order(s)`} columns={['Woo Order', 'Woo Status', 'Local Status', 'Customer', 'Email', 'Order Total', 'Qty Ordered', 'Qty Allocated', 'Qty Picked', 'Qty Fulfilled', 'Remaining', 'Fulfilled Value', 'Date Created']}>
        {orders.map((order) => (
          <tr key={order.id}>
            <td className="mono">{order.woo_order_number || order.woo_order_id}</td>
            <td>{StatusText(order.woo_status)}</td>
            <td>{StatusText(order.local_status)}</td>
            <td>{order.customer_name}</td>
            <td>{order.customer_email}</td>
            <td>{formatCurrency(order.total)}</td>
            <td>{formatNumber(order.total_quantity_ordered)}</td>
            <td>{formatNumber(order.total_quantity_allocated)}</td>
            <td>{formatNumber(order.total_quantity_picked)}</td>
            <td>{formatNumber(order.total_quantity_fulfilled)}</td>
            <td>{formatNumber(order.total_remaining_to_fulfill)}</td>
            <td>{formatCurrency(order.total_fulfilled_value)}</td>
            <td>{formatDateTime(order.date_created)}</td>
          </tr>
        ))}
        {orders.length === 0 && <tr><td colSpan={13}><div className="empty-table-row">No completed orders match the current filters.</div></td></tr>}
      </TableShell>
    </div>
  );
}

function RoutesPage({
  candidatesData,
  candidatesLoading,
  candidatesError,
  preview,
  commitSummary,
  routesData,
  detail,
  mapPayload,
  providerMessage,
  loading,
  error,
  onLoadCandidates,
  onPreview,
  onCommit,
  onLoadRoutes,
  onLoadDetail,
  onFinalize,
  onCancel,
  onSaveMetadata,
  onReorderStops,
  onSaveStop,
  onProviderAction,
}) {
  const [candidateFilters, setCandidateFilters] = useState(emptyRouteCandidateFilters);
  const [routeFilters, setRouteFilters] = useState(emptyRouteFilters);
  const [selectedOrderIds, setSelectedOrderIds] = useState([]);
  const [routeForm, setRouteForm] = useState({
    routeDate: todayDateInput(),
    routeName: 'Main Warehouse Route',
    driverName: '',
    vehicleName: '',
    notes: '',
  });
  const candidates = candidatesData.candidates || [];
  const routes = routesData.routes || [];
  const selectedCount = selectedOrderIds.length;

  function updateCandidateFilter(name, value) {
    setCandidateFilters((current) => ({ ...current, [name]: value }));
  }

  function updateRouteFilter(name, value) {
    setRouteFilters((current) => ({ ...current, [name]: value }));
  }

  function updateRouteForm(name, value) {
    setRouteForm((current) => ({ ...current, [name]: value }));
  }

  function toggleOrder(orderId) {
    setSelectedOrderIds((current) => (current.includes(orderId) ? current.filter((id) => id !== orderId) : [...current, orderId]));
  }

  function clearCandidateFilters() {
    const cleared = emptyRouteCandidateFilters();
    setCandidateFilters(cleared);
    onLoadCandidates(cleared);
  }

  function clearRouteFilters() {
    const cleared = emptyRouteFilters();
    setRouteFilters(cleared);
    onLoadRoutes(cleared);
  }

  function payload() {
    return {
      route_date: routeForm.routeDate,
      route_name: routeForm.routeName,
      driver_name: routeForm.driverName,
      vehicle_name: routeForm.vehicleName,
      notes: routeForm.notes,
      created_by: 'system',
      order_ids: selectedOrderIds,
    };
  }

  function createRoute() {
    onCommit(payload());
  }

  return (
    <section className="content-panel routes-page">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Route Creation</h2>
            <p>Create local draft routes from completed local orders. No maps, optimization, WooCommerce, labels, notifications, or inventory changes are performed.</p>
          </div>
          <div className="button-row compact">
            <button className="muted-button" onClick={() => onLoadCandidates(candidateFilters)} disabled={candidatesLoading} type="button">
              <RefreshCw size={17} />
              Refresh Candidates
            </button>
            <button className="primary-button" onClick={() => onPreview(payload())} disabled={loading || selectedCount === 0} type="button">
              <Search size={17} />
              Preview Route
            </button>
            <button className="action-button" onClick={createRoute} disabled={loading || selectedCount === 0} type="button">
              <Plus size={17} />
              Create Draft
            </button>
          </div>
        </div>
        <div className="summary-strip route-summary-strip">
          <Metric label="Candidates" value={candidatesData.total_candidates || 0} />
          <Metric label="Selected Stops" value={selectedCount} />
          <Metric label="Preview Valid" value={preview?.valid_orders || 0} />
          <Metric label="Preview Invalid" value={preview?.invalid_orders || 0} />
          <Metric label="Routes" value={routesData.total || 0} />
        </div>
        <div className="toolbar report-toolbar routes-toolbar">
          <div className="filter-grid route-filter-grid">
            <label className="field">
              <span>Search</span>
              <div className="input-with-icon">
                <input value={candidateFilters.search} onChange={(event) => updateCandidateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadCandidates(candidateFilters))} />
                <Search size={18} />
              </div>
            </label>
            <FilterSelect label="Local Status" value={candidateFilters.localStatus} options={['fulfilled', 'partially_fulfilled']} onChange={(value) => updateCandidateFilter('localStatus', value)} />
            <label className="field">
              <span>Customer Email</span>
              <div className="input-with-icon">
                <input value={candidateFilters.customerEmail} onChange={(event) => updateCandidateFilter('customerEmail', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadCandidates(candidateFilters))} />
                <Search size={18} />
              </div>
            </label>
            <label className="field">
              <span>Woo Order Number</span>
              <div className="input-with-icon">
                <input value={candidateFilters.wooOrderNumber} onChange={(event) => updateCandidateFilter('wooOrderNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadCandidates(candidateFilters))} />
                <Search size={18} />
              </div>
            </label>
          </div>
          <div className="button-row items-actions">
            <button className="primary-button" onClick={() => onLoadCandidates(candidateFilters)} type="button">
              <Filter size={17} />
              Apply
            </button>
            <button className="muted-button" onClick={clearCandidateFilters} type="button">
              Clear
            </button>
          </div>
        </div>
        <div className="receiving-form route-form">
          <div className="receiving-header-fields route-header-fields">
            <label className="field">
              <span>Route Date</span>
              <input value={routeForm.routeDate} onChange={(event) => updateRouteForm('routeDate', event.target.value)} type="date" />
            </label>
            <label className="field">
              <span>Route Name</span>
              <input value={routeForm.routeName} onChange={(event) => updateRouteForm('routeName', event.target.value)} />
            </label>
            <label className="field">
              <span>Driver Name</span>
              <input value={routeForm.driverName} onChange={(event) => updateRouteForm('driverName', event.target.value)} />
            </label>
            <label className="field">
              <span>Vehicle Name</span>
              <input value={routeForm.vehicleName} onChange={(event) => updateRouteForm('vehicleName', event.target.value)} />
            </label>
            <label className="field wide-field">
              <span>Notes</span>
              <input value={routeForm.notes} onChange={(event) => updateRouteForm('notes', event.target.value)} />
            </label>
          </div>
        </div>
        <div className="csv-note">Eligible candidates are local orders in fulfilled or partially fulfilled status. Already-routed orders are hidden unless their route is cancelled.</div>
        {candidatesError && <div className="api-error">{candidatesError}</div>}
        {error && <div className="api-error">{error}</div>}
        {(candidatesLoading || loading) && <div className="loading-strip">Working with local routes...</div>}
        {commitSummary && (
          <div className={commitSummary.status === 'draft' || commitSummary.status === 'finalized' || commitSummary.status === 'cancelled' ? 'success-strip' : 'api-error'}>
            Route action finished with status {commitSummary.status}. {commitSummary.route_number ? `Route ${commitSummary.route_number}.` : ''} {(commitSummary.errors || []).join(' ')}
          </div>
        )}
        <RouteCandidatesTable candidates={candidates} selectedOrderIds={selectedOrderIds} onToggle={toggleOrder} />
      </div>
      {preview && <RoutePreviewPanel preview={preview} />}
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Route History</h2>
            <p>Local draft, finalized, and cancelled routes.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadRoutes(routeFilters)} disabled={loading} type="button">
            <RefreshCw size={17} />
            Refresh Routes
          </button>
        </div>
        <div className="filter-panel">
          <div className="filter-grid route-history-filter-grid">
            <FilterSelect label="Status" value={routeFilters.status} options={['draft', 'finalized', 'cancelled']} onChange={(value) => updateRouteFilter('status', value)} />
            <label className="field"><span>Date From</span><div className="input-with-icon"><input value={routeFilters.dateFrom} onChange={(event) => updateRouteFilter('dateFrom', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadRoutes(routeFilters))} type="date" /><CalendarDays size={18} /></div></label>
            <label className="field"><span>Date To</span><div className="input-with-icon"><input value={routeFilters.dateTo} onChange={(event) => updateRouteFilter('dateTo', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadRoutes(routeFilters))} type="date" /><CalendarDays size={18} /></div></label>
            <label className="field"><span>Search</span><div className="input-with-icon"><input value={routeFilters.search} onChange={(event) => updateRouteFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadRoutes(routeFilters))} /><Search size={18} /></div></label>
            <label className="field"><span>Driver</span><div className="input-with-icon"><input value={routeFilters.driverName} onChange={(event) => updateRouteFilter('driverName', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadRoutes(routeFilters))} /><UserCircle size={18} /></div></label>
            <label className="field"><span>Vehicle</span><div className="input-with-icon"><input value={routeFilters.vehicleName} onChange={(event) => updateRouteFilter('vehicleName', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadRoutes(routeFilters))} /><Truck size={18} /></div></label>
          </div>
          <div className="button-row">
            <button className="muted-button" onClick={clearRouteFilters} type="button"><SlidersHorizontal size={17} />Clear</button>
            <button className="primary-button" onClick={() => onLoadRoutes(routeFilters)} disabled={loading} type="button"><Filter size={17} />Apply</button>
          </div>
        </div>
        {routesErrorOrLoading(routesLoading, routesError)}
        <RouteHistoryTable routes={routes} detail={detail} onSelect={onLoadDetail} onFinalize={onFinalize} onCancel={onCancel} />
      </div>
      <RouteDetailPanel route={detail} mapPayload={mapPayload} providerMessage={providerMessage} loading={loading} onSaveMetadata={onSaveMetadata} onReorderStops={onReorderStops} onSaveStop={onSaveStop} onProviderAction={onProviderAction} />
    </section>
  );
}

function RouteCandidatesTable({ candidates, selectedOrderIds, onToggle }) {
  return (
    <TableShell caption={`${candidates.length} candidate order(s)`} columns={['Select', 'Woo Order', 'Local Status', 'Customer', 'Email', 'Phone', 'Shipping', 'Order Total', 'Fulfilled Lines', 'Qty Fulfilled', 'Date Created', 'Warning']}>
      {candidates.map((candidate) => (
        <tr key={candidate.order_id} className={selectedOrderIds.includes(candidate.order_id) ? 'selected-row' : ''}>
          <td><input checked={selectedOrderIds.includes(candidate.order_id)} onChange={() => onToggle(candidate.order_id)} type="checkbox" /></td>
          <td className="mono">{candidate.woo_order_number || candidate.woo_order_id}</td>
          <td>{StatusText(candidate.local_status)}</td>
          <td>{candidate.customer_name}</td>
          <td>{candidate.customer_email}</td>
          <td>{candidate.customer_phone}</td>
          <td className="description-cell">{formatAddressSummary(candidate.shipping_summary)}</td>
          <td>{formatCurrency(candidate.order_total)}</td>
          <td>{candidate.fulfilled_line_count}</td>
          <td>{formatNumber(candidate.total_quantity_fulfilled)}</td>
          <td>{formatDateTime(candidate.date_created)}</td>
          <td className="description-cell">{candidate.route_warning || ''}</td>
        </tr>
      ))}
      {candidates.length === 0 && <tr><td colSpan={12}><div className="empty-table-row">No completed orders are available for routing.</div></td></tr>}
    </TableShell>
  );
}

function RoutePreviewPanel({ preview }) {
  const route = preview.preview_route || {};
  const stops = route.stops || [];
  return (
    <div className="wide-panel allocation-panel">
      <div className="panel-title">
        <div>
          <h2>Route Preview</h2>
          <p>{route.route_name || 'Route'} on {route.route_date || 'selected date'} with {preview.valid_orders} valid stop(s).</p>
        </div>
      </div>
      <div className="summary-strip allocation-summary-strip">
        <Metric label="Orders" value={preview.total_orders} />
        <Metric label="Valid" value={preview.valid_orders} />
        <Metric label="Invalid" value={preview.invalid_orders} />
        <Metric label="Warnings" value={preview.warning_count} />
        <Metric label="Driver" value={route.driver_name || 'Unassigned'} />
        <Metric label="Vehicle" value={route.vehicle_name || 'Unassigned'} />
        <Metric label="Stops" value={route.estimated_stop_count || 0} />
      </div>
      {(preview.errors || []).length > 0 && <div className="api-error">{preview.errors.join(' ')}</div>}
      <TableShell caption={`${stops.length} preview stop(s)`} columns={['Seq', 'Status', 'Woo Order', 'Local Status', 'Customer', 'Email', 'Shipping', 'Fulfilled Lines', 'Qty Fulfilled', 'Warnings', 'Errors']}>
        {stops.map((stop) => (
          <tr key={`${stop.stop_sequence}-${stop.order_id}`}>
            <td>{stop.stop_sequence}</td>
            <td>{StatusText(stop.status)}</td>
            <td className="mono">{stop.woo_order_number || stop.woo_order_id || stop.order_id}</td>
            <td>{StatusText(stop.local_status)}</td>
            <td>{stop.customer_name}</td>
            <td>{stop.customer_email}</td>
            <td className="description-cell">{formatAddressSummary(stop.shipping_summary)}</td>
            <td>{stop.fulfilled_line_count}</td>
            <td>{formatNumber(stop.total_quantity_fulfilled)}</td>
            <td className="description-cell">{(stop.warnings || []).join(' ')}</td>
            <td className="description-cell">{(stop.errors || []).join(' ')}</td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function RouteHistoryTable({ routes, detail, onSelect, onFinalize, onCancel }) {
  return (
    <TableShell caption={`${routes.length} route(s)`} columns={['Route', 'Status', 'Date', 'Name', 'Driver', 'Vehicle', 'Stops', 'Created By', 'Created At', 'Actions']}>
      {routes.map((route) => (
        <tr key={route.id} className={detail?.id === route.id ? 'selected-row' : ''} onClick={() => onSelect(route.id)}>
          <td className="mono">{route.route_number}</td>
          <td>{StatusText(route.status)}</td>
          <td>{route.route_date}</td>
          <td>{route.route_name}</td>
          <td>{route.driver_name}</td>
          <td>{route.vehicle_name}</td>
          <td>{route.total_stops}</td>
          <td>{route.created_by}</td>
          <td>{formatDateTime(route.created_at)}</td>
          <td>
            <div className="button-row compact table-button-row">
              <button className="muted-button" onClick={(event) => { event.stopPropagation(); onSelect(route.id); }} type="button">View</button>
              <button className="action-button" onClick={(event) => { event.stopPropagation(); exportRouteCsv(route.id, route.route_number); }} type="button"><Download size={15} />CSV</button>
              <button className="primary-button" onClick={(event) => { event.stopPropagation(); onFinalize(route.id); }} disabled={route.status !== 'draft'} type="button">Finalize</button>
              <button className="muted-button" onClick={(event) => { event.stopPropagation(); onCancel(route.id); }} disabled={route.status === 'cancelled'} type="button">Cancel</button>
            </div>
          </td>
        </tr>
      ))}
      {routes.length === 0 && <tr><td colSpan={10}><div className="empty-table-row">No routes have been created yet.</div></td></tr>}
    </TableShell>
  );
}

function RouteDetailPanel({ route, mapPayload, providerMessage, loading, onSaveMetadata, onReorderStops, onSaveStop, onProviderAction }) {
  const [meta, setMeta] = useState({ route_name: '', driver_name: '', vehicle_name: '', route_date: '', notes: '' });
  const [stopDrafts, setStopDrafts] = useState({});

  useEffect(() => {
    if (route) {
      setMeta({ route_name: route.route_name || '', driver_name: route.driver_name || '', vehicle_name: route.vehicle_name || '', route_date: route.route_date || '', notes: route.notes || '' });
      setStopDrafts(Object.fromEntries((route.stops || []).map((stop) => [stop.id, { delivery_notes: stop.delivery_notes || '', internal_notes: stop.internal_notes || '', latitude: stop.latitude ?? '', longitude: stop.longitude ?? '' }])));
    }
  }, [route?.id]);

  if (!route) {
    return (
      <aside className="order-detail-panel route-detail-panel">
        <div className="empty-state">
          <h2>No route selected</h2>
          <p>Select a route from history to review its stops.</p>
        </div>
      </aside>
    );
  }
  const stopIds = (route.stops || []).map((stop) => stop.id);
  function moveStop(stopId, direction) {
    const index = stopIds.indexOf(stopId);
    const next = [...stopIds];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    onReorderStops(route.id, next);
  }

  function updateStopDraft(stopId, field, value) {
    setStopDrafts((current) => ({ ...current, [stopId]: { ...(current[stopId] || {}), [field]: value } }));
  }

  return (
    <aside className="order-detail-panel route-detail-panel">
      <div className="panel-title compact-title">
        <div>
          <h2>{route.route_number}</h2>
          <p>{route.status} · {route.total_stops} stop(s) · {route.route_date}</p>
        </div>
        <button className="action-button" onClick={() => exportRouteCsv(route.id, route.route_number)} type="button">
          <Download size={17} />
          Export
        </button>
      </div>
      {route.notes && <div className="csv-note">{route.notes}</div>}
      <div className="receiving-form route-form">
        <div className="receiving-header-fields route-header-fields">
          <label className="field"><span>Route Name</span><input value={meta.route_name} onChange={(event) => setMeta((current) => ({ ...current, route_name: event.target.value }))} /></label>
          <label className="field"><span>Date</span><input value={meta.route_date} onChange={(event) => setMeta((current) => ({ ...current, route_date: event.target.value }))} type="date" /></label>
          <label className="field"><span>Driver</span><input value={meta.driver_name} onChange={(event) => setMeta((current) => ({ ...current, driver_name: event.target.value }))} /></label>
          <label className="field"><span>Vehicle</span><input value={meta.vehicle_name} onChange={(event) => setMeta((current) => ({ ...current, vehicle_name: event.target.value }))} /></label>
          <label className="field wide-field"><span>Notes</span><input value={meta.notes} onChange={(event) => setMeta((current) => ({ ...current, notes: event.target.value }))} /></label>
        </div>
        <button className="primary-button" disabled={loading} onClick={() => onSaveMetadata(route.id, meta)} type="button"><Save size={17} />Save Metadata</button>
      </div>
      <div className="csv-note">Routing tools are local-only. No WooCommerce updates are made.</div>
      {providerMessage && <div className="success-strip">{providerMessage}</div>}
      <div className="button-row compact">
        <button className="muted-button" onClick={() => onProviderAction(route.id, 'geocode/preview')} type="button">Geocode Preview</button>
        <button className="muted-button" onClick={() => onProviderAction(route.id, 'geocode/commit')} type="button">Geocode Commit</button>
        <button className="muted-button" onClick={() => onProviderAction(route.id, 'optimize/preview')} type="button">Optimize Preview</button>
        <button className="muted-button" onClick={() => onProviderAction(route.id, 'optimize/commit')} type="button">Optimize Commit</button>
      </div>
      {mapPayload && (
        <div className="csv-note">
          Map provider: {mapPayload.provider_config_public?.provider || 'disabled'} · Missing coordinates: {mapPayload.missing_coordinates_count}
        </div>
      )}
      <TableShell caption={`${route.stops?.length || 0} stop(s)`} columns={['Seq', 'Move', 'Woo Order', 'Customer', 'Shipping', 'Lat', 'Lng', 'Delivery Notes', 'Internal Notes', 'Save']}>
        {(route.stops || []).map((stop) => (
          <tr key={stop.id}>
            <td>{stop.stop_sequence}</td>
            <td><div className="button-row compact"><button className="muted-button" onClick={() => moveStop(stop.id, -1)} type="button">Up</button><button className="muted-button" onClick={() => moveStop(stop.id, 1)} type="button">Down</button></div></td>
            <td className="mono">{stop.woo_order_number || stop.woo_order_id}</td>
            <td>{stop.customer_name}</td>
            <td className="description-cell">{[stop.address_1, stop.address_2, stop.city, stop.state, stop.zip, stop.country].filter(Boolean).join(', ') || formatAddressSummary(stop.shipping_summary)}</td>
            <td><input value={stopDrafts[stop.id]?.latitude ?? ''} onChange={(event) => updateStopDraft(stop.id, 'latitude', event.target.value)} /></td>
            <td><input value={stopDrafts[stop.id]?.longitude ?? ''} onChange={(event) => updateStopDraft(stop.id, 'longitude', event.target.value)} /></td>
            <td><input value={stopDrafts[stop.id]?.delivery_notes ?? ''} onChange={(event) => updateStopDraft(stop.id, 'delivery_notes', event.target.value)} /></td>
            <td><input value={stopDrafts[stop.id]?.internal_notes ?? ''} onChange={(event) => updateStopDraft(stop.id, 'internal_notes', event.target.value)} /></td>
            <td><button className="primary-button" onClick={() => onSaveStop(route.id, stop.id, normalizeStopDraft(stopDrafts[stop.id] || {}))} type="button">Save</button></td>
          </tr>
        ))}
      </TableShell>
    </aside>
  );
}

function routesErrorOrLoading(loading, error) {
  return (
    <>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading routes...</div>}
    </>
  );
}

function StatusText(value) {
  return <span className={`status-pill order-status-${String(value || 'unknown').replace(/[^a-z0-9-]/gi, '-').toLowerCase()}`}>{value || 'unknown'}</span>;
}

function WooCommerceSettingsPage({ status, preview, commitSummary, orderPreview, orderCommitSummary, syncRuns, remapCandidates, remapMappings, remapPreview, remapMessage, loading, error, onCheckConnection, onPreview, onCommit, onPreviewOrders, onCommitOrders, onPreviewRemap, onCommitRemap, onLoadRemap }) {
  const latestRun = syncRuns.find((run) => run.sync_type === 'products') || syncRuns[0];
  const latestOrderRun = syncRuns.find((run) => run.sync_type === 'orders');
  const commitDisabled = !status.configured || !preview || preview.conflict_count > 0 || preview.error_count > 0;
  const orderCommitDisabled = !status.configured || !orderPreview;
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
            <h2>WooCommerce Order Sync</h2>
            <p>Imports processing and on-hold orders into local open orders. It is read-only against WooCommerce and does not allocate or change stock.</p>
          </div>
          <div className="button-row compact">
            <button className="primary-button" disabled={loading || !status.configured} onClick={onPreviewOrders} type="button">
              <Search size={17} />
              Preview Order Sync
            </button>
            <button className="action-button" disabled={loading || orderCommitDisabled} onClick={onCommitOrders} type="button">
              <RefreshCw size={17} />
              Commit Order Sync
            </button>
          </div>
        </div>
        <div className="summary-strip report-summary-strip">
          <Metric label="Default Statuses" value="processing, on-hold" />
          <Metric label="Last Order Sync" value={latestOrderRun ? latestOrderRun.status : 'None'} />
          <Metric label="Last Orders" value={latestOrderRun ? latestOrderRun.total_remote_records : 0} />
          <Metric label="Safety" value="Read-only Woo" />
        </div>
        <div className="csv-note">Order sync stores local order/order line snapshots only. It does not write WooCommerce, update product stock, create stock movements, allocate, pick, or route orders.</div>
        {orderPreview && <WooOrderPreviewSummary preview={orderPreview} />}
        {orderCommitSummary && (
          <div className="success-strip">
            Order sync run {orderCommitSummary.sync_run_id || 'not created'} finished with status {orderCommitSummary.status}. Created {orderCommitSummary.created_count}, updated {orderCommitSummary.updated_count}, skipped {orderCommitSummary.skipped_count}.
          </div>
        )}
      </div>
      {orderPreview && <WooOrderPreviewTable orders={orderPreview.preview_orders || []} />}
      <WooRemapPanel candidates={remapCandidates?.candidates || []} mappings={remapMappings?.mappings || []} preview={remapPreview} message={remapMessage} loading={loading} onPreview={onPreviewRemap} onCommit={onCommitRemap} onRefresh={onLoadRemap} />
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Sync Run History</h2>
            <p>Local WooCommerce sync attempts and outcomes.</p>
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

function WooOrderPreviewSummary({ preview }) {
  return (
    <div className="summary-strip woo-summary-strip">
      <Metric label="Remote Orders" value={preview.total_remote_records} />
      <Metric label="Create" value={preview.create_count} />
      <Metric label="Update" value={preview.update_count} />
      <Metric label="Matched Lines" value={preview.matched_count} />
      <Metric label="Conflicts" value={preview.conflict_count} />
      <Metric label="Unavailable" value={preview.unavailable_count} />
      <Metric label="Unknown" value={preview.unknown_count} />
    </div>
  );
}

function WooOrderPreviewTable({ orders }) {
  const rows = orders.flatMap((order) => (order.lines || []).map((line) => ({ order, line })));
  return (
    <TableShell caption={`${orders.length} order(s), ${rows.length} line(s)`} columns={['Action', 'Order', 'Woo Status', 'Customer', 'Total', 'SKU', 'Barcode', 'Name', 'Qty', 'Match', 'Availability', 'Sellable', 'Shortage', 'Warnings', 'Errors']}>
      {rows.map(({ order, line }) => (
        <tr key={`${order.woo_order_id}-${line.woo_line_item_id || line.sku}`}>
          <td>{order.action}</td>
          <td className="mono">{order.woo_order_number || order.woo_order_id}</td>
          <td>{StatusText(order.woo_status)}</td>
          <td>{order.customer_name}</td>
          <td>{formatCurrency(order.total)}</td>
          <td className="mono">{line.sku}</td>
          <td className="mono">{line.barcode}</td>
          <td className="description-cell">{line.name}</td>
          <td>{formatNumber(line.quantity_ordered)}</td>
          <td>{StatusText(line.matched_status)}</td>
          <td>{StatusText(line.availability_status)}</td>
          <td>{formatNumber(line.sellable_snapshot)}</td>
          <td>{formatNumber(line.shortage_quantity)}</td>
          <td className="description-cell">{[...(order.warnings || []), ...(line.warnings || [])].join(' ')}</td>
          <td className="description-cell">{[...(order.errors || []), ...(line.errors || [])].join(' ')}</td>
        </tr>
      ))}
      {rows.length === 0 && (
        <tr>
          <td colSpan={15}>
            <div className="empty-table-row">No WooCommerce order preview rows loaded.</div>
          </td>
        </tr>
      )}
    </TableShell>
  );
}

function WooRemapPanel({ candidates, mappings, preview, message, loading, onPreview, onCommit, onRefresh }) {
  const [selected, setSelected] = useState({ woo_product_id: '', woo_variation_id: '', item_id: '', note: '' });

  function selectCandidate(candidate) {
    const firstSuggestion = candidate.suggested_items?.[0];
    setSelected({
      woo_product_id: candidate.remote.woo_product_id || '',
      woo_variation_id: candidate.remote.woo_variation_id || '',
      item_id: firstSuggestion?.item_id || candidate.current_mapping?.item_id || '',
      note: '',
    });
  }

  function payload() {
    return {
      woo_product_id: Number(selected.woo_product_id),
      woo_variation_id: selected.woo_variation_id === '' ? null : Number(selected.woo_variation_id),
      item_id: Number(selected.item_id),
      note: selected.note,
    };
  }

  return (
    <div className="wide-panel">
      <div className="panel-title">
        <div>
          <h2>WooCommerce Remap</h2>
          <p>Local-only relinking for Woo product/variation snapshots. It does not write WooCommerce or inventory.</p>
        </div>
        <button className="muted-button" onClick={onRefresh} disabled={loading} type="button"><RefreshCw size={17} />Refresh Remap</button>
      </div>
      <div className="csv-note">This only changes local mapping metadata. Manual Pongo OS fields and quantities are preserved.</div>
      {message && <div className="success-strip">{message}</div>}
      <div className="receiving-form route-form">
        <div className="receiving-header-fields route-header-fields">
          <label className="field"><span>Woo Product ID</span><input value={selected.woo_product_id} onChange={(event) => setSelected((current) => ({ ...current, woo_product_id: event.target.value }))} /></label>
          <label className="field"><span>Woo Variation ID</span><input value={selected.woo_variation_id} onChange={(event) => setSelected((current) => ({ ...current, woo_variation_id: event.target.value }))} /></label>
          <label className="field"><span>Local Item ID</span><input value={selected.item_id} onChange={(event) => setSelected((current) => ({ ...current, item_id: event.target.value }))} /></label>
          <label className="field wide-field"><span>Note</span><input value={selected.note} onChange={(event) => setSelected((current) => ({ ...current, note: event.target.value }))} /></label>
        </div>
        <div className="button-row">
          <button className="primary-button" disabled={loading || !selected.woo_product_id || !selected.item_id} onClick={() => onPreview(payload())} type="button"><Search size={17} />Preview Mapping</button>
          <button className="action-button" disabled={loading || !preview} onClick={() => onCommit(payload())} type="button"><Link2 size={17} />Commit Mapping</button>
        </div>
      </div>
      {preview && (
        <div className="success-strip">
          Preview maps Woo {preview.remote.woo_product_id}{preview.remote.woo_variation_id ? `/${preview.remote.woo_variation_id}` : ''} to item {preview.item.item_id}. {(preview.warnings || []).join(' ')}
        </div>
      )}
      <TableShell caption={`${candidates.length} remap candidate(s)`} columns={['Woo Product', 'Variation', 'SKU', 'Reason', 'Current Item', 'Suggestions', 'Action']}>
        {candidates.map((candidate) => (
          <tr key={`${candidate.remote.woo_product_id}-${candidate.remote.woo_variation_id || 'simple'}`}>
            <td className="mono">{candidate.remote.woo_product_id}</td>
            <td className="mono">{candidate.remote.woo_variation_id}</td>
            <td className="mono">{candidate.remote.woo_sku}</td>
            <td>{candidate.remote.reason}</td>
            <td>{candidate.current_mapping?.item_id || ''}</td>
            <td className="description-cell">{(candidate.suggested_items || []).map((item) => `${item.item_id}:${item.sku || item.description}`).join(', ')}</td>
            <td><button className="muted-button" onClick={() => selectCandidate(candidate)} type="button">Select</button></td>
          </tr>
        ))}
        {candidates.length === 0 && <tr><td colSpan={7}><div className="empty-table-row">No remap candidates found.</div></td></tr>}
      </TableShell>
      <TableShell caption={`${mappings.length} active mapping(s)`} columns={['Item ID', 'Woo Product', 'Variation', 'SKU', 'Source', 'Active', 'Updated']}>
        {mappings.map((mapping) => (
          <tr key={mapping.id}><td>{mapping.item_id}</td><td className="mono">{mapping.woo_product_id}</td><td className="mono">{mapping.woo_variation_id}</td><td className="mono">{mapping.woo_sku}</td><td>{mapping.mapping_source}</td><td>{mapping.active ? 'Yes' : 'No'}</td><td>{formatDateTime(mapping.updated_at)}</td></tr>
        ))}
        {mappings.length === 0 && <tr><td colSpan={7}><div className="empty-table-row">No active local remap records yet.</div></td></tr>}
      </TableShell>
    </div>
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
          <button className="muted-button" disabled title="Not available yet" type="button">
            <Filter size={17} />
            Filter
          </button>
          <button className="action-button" disabled title="Not available yet" type="button">
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
    <div className="table-wrap table-card">
      <div className="table-meta">
        <span>{caption}</span>
        <div className="table-pager">
          <span>20 Results</span>
          <button className="pager-button" aria-label="Previous page" title="Pagination is not available yet" disabled type="button">
            <ChevronLeft size={18} />
          </button>
          <span>1 / 1</span>
          <button className="pager-button active" aria-label="Next page" title="Pagination is not available yet" disabled type="button">
            <ChevronRight size={18} />
          </button>
        </div>
      </div>
      <div className="table-action-band">
        <span>Actions</span>
        <ChevronDown size={18} />
      </div>
      <div className="table-scroll">
        <table className="data-table">
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
      return { title: 'New Item', kicker: 'Item master entry', tabs: [] };
    }
    if (route.itemView === 'detail') {
      const item = items.find((candidate) => String(candidate.id) === String(route.itemId));
      return { title: item ? `Edit ${item.SKU}` : 'Edit Item', kicker: 'Item master entry', tabs: [] };
    }
    return pageMeta.items;
  }
  if (route.pageId === 'locations' && route.locationView === 'new') {
    return { title: 'Add Location', kicker: 'Warehouse and bin setup', tabs: pageMeta.locations.tabs };
  }
  if (route.pageId === 'locations' && route.locationView === 'detail') {
    return { title: 'Edit Location', kicker: 'Warehouse and bin setup', tabs: pageMeta.locations.tabs };
  }
  if (route.pageId === 'orders') {
    const meta = orderSubpageMeta[route.ordersView || 'open'] || orderSubpageMeta.open;
    return { ...meta, tabs: [] };
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
    const matchesBrand = !filters.brand || item.Brand === filters.brand;
    const matchesStatus = filters.status === 'inactive' ? !item.active : item.active;
    const matchesInventoryType = filters.includeNonInventory || !item.nonInventory;
    const matchesStockStatus =
      !filters.stockStatus ||
      (filters.stockStatus === 'in_stock' && toNumber(item['In Stock']) > 0) ||
      (filters.stockStatus === 'out_of_stock' && toNumber(item['In Stock']) <= 0) ||
      (filters.stockStatus === 'under_par' && Boolean(item['Under Par'])) ||
      (filters.stockStatus === 'negative_sellable' && toNumber(item.Sellable) < 0);
    return matchesSearch && matchesCategory && matchesBrand && matchesStatus && matchesInventoryType && matchesStockStatus;
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

function emptyFulfillmentReportFilters() {
  return {
    dateFrom: '',
    dateTo: '',
    warehouse: '',
    inventoryLocation: '',
    sku: '',
    barcode: '',
    category: '',
    brand: '',
    fulfillmentNumber: '',
    wooOrderNumber: '',
    customerEmail: '',
    localStatus: '',
    createdBy: '',
  };
}

function emptySkuOrdersFilters() {
  return {
    startDate: '',
    endDate: '',
    sku: '',
    brand: '',
    category: '',
    orderStatus: '',
    wooStatus: '',
    includeUnmatched: true,
    groupBy: 'sku',
  };
}

function emptyCompletedOrderFilters() {
  return {
    localStatus: '',
    dateFrom: '',
    dateTo: '',
    customerEmail: '',
    wooOrderNumber: '',
    sku: '',
    barcode: '',
    search: '',
  };
}

function emptyRouteCandidateFilters() {
  return {
    localStatus: '',
    customerEmail: '',
    wooOrderNumber: '',
    search: '',
  };
}

function emptyRouteFilters() {
  return {
    status: '',
    dateFrom: '',
    dateTo: '',
    driverName: '',
    vehicleName: '',
    search: '',
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

function formatReportValue(value) {
  if (value === null || value === undefined) {
    return '';
  }
  if (typeof value === 'number') {
    return Number.isInteger(value) ? String(value) : formatNumber(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatDateTime(value);
  }
  return String(value);
}

function formatCountType(value) {
  return value === 'full_location' ? 'Full Location' : 'Selected Items';
}

function Badge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
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

async function exportFulfillmentReportCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/reports/fulfillments/export${plainFiltersToQueryString(fulfillmentReportFiltersToApi(filters))}`);
  if (!response.ok) {
    showPlaceholder('Unable to export fulfillment report from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-fulfillment-report.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportSkuOrdersCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/reports/sku-orders/export${plainFiltersToQueryString(skuOrdersFiltersToApi(filters))}`);
  if (!response.ok) {
    showPlaceholder('Unable to export SKU Orders report from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-sku-orders-report.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportGenericReportCsv(reportKey, filters, label) {
  const response = await fetch(`${API_BASE_URL}/api/reports/${reportKey}/export${plainFiltersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder(`Unable to export ${label} from the backend.`);
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-${reportKey}-report.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportOpenOrdersCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/orders/open/export${plainFiltersToQueryString(openOrderFiltersToApi(filters))}`);
  if (!response.ok) {
    showPlaceholder('Unable to export open orders from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-open-orders-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportCompletedOrdersCsv(filters) {
  const response = await fetch(`${API_BASE_URL}/api/orders/completed/export${plainFiltersToQueryString(completedOrderFiltersToApi(filters))}`);
  if (!response.ok) {
    showPlaceholder('Unable to export completed orders from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-completed-orders-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportAllocationCsv(allocationId, allocationNumber) {
  const response = await fetch(`${API_BASE_URL}/api/allocations/${allocationId}/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export allocation from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-allocation-${allocationNumber || allocationId}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportPickCsv(pickId, pickNumber) {
  const response = await fetch(`${API_BASE_URL}/api/picks/${pickId}/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export pick from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-pick-${pickNumber || pickId}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportFulfillmentCsv(fulfillmentId, fulfillmentNumber) {
  const response = await fetch(`${API_BASE_URL}/api/fulfillments/${fulfillmentId}/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export fulfillment from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-fulfillment-${fulfillmentNumber || fulfillmentId}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportRouteCsv(routeId, routeNumber) {
  const response = await fetch(`${API_BASE_URL}/api/routes/${routeId}/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export route CSV from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `pongo-route-${routeNumber || routeId}.csv`;
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

async function patchJson(path, payload) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
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

function fulfillmentReportFiltersToApi(filters = {}) {
  return {
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    warehouse: filters.warehouse,
    inventory_location: filters.inventoryLocation,
    sku: filters.sku,
    barcode: filters.barcode,
    category: filters.category,
    brand: filters.brand,
    fulfillment_number: filters.fulfillmentNumber,
    woo_order_number: filters.wooOrderNumber,
    customer_email: filters.customerEmail,
    local_status: filters.localStatus,
    created_by: filters.createdBy,
  };
}

function skuOrdersFiltersToApi(filters = {}) {
  return {
    start_date: filters.startDate,
    end_date: filters.endDate,
    sku: filters.sku,
    brand: filters.brand,
    category: filters.category,
    order_status: filters.orderStatus,
    woo_status: filters.wooStatus,
    include_unmatched: filters.includeUnmatched !== false,
    group_by: filters.groupBy || 'sku',
  };
}

function openOrderFiltersToApi(filters = {}) {
  return {
    search: filters.search,
    woo_status: filters.wooStatus,
    availability_status: filters.availabilityStatus,
    matched_status: filters.matchedStatus,
  };
}

function completedOrderFiltersToApi(filters = {}) {
  return {
    local_status: filters.localStatus,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    customer_email: filters.customerEmail,
    woo_order_number: filters.wooOrderNumber,
    sku: filters.sku,
    barcode: filters.barcode,
    search: filters.search,
  };
}

function routeCandidateFiltersToApi(filters = {}) {
  return {
    local_status: filters.localStatus,
    customer_email: filters.customerEmail,
    woo_order_number: filters.wooOrderNumber,
    search: filters.search,
  };
}

function routeFiltersToApi(filters = {}) {
  return {
    status: filters.status,
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
    driver_name: filters.driverName,
    vehicle_name: filters.vehicleName,
    search: filters.search,
  };
}

function normalizeStopDraft(draft) {
  return {
    delivery_notes: draft.delivery_notes || '',
    internal_notes: draft.internal_notes || '',
    latitude: draft.latitude === '' || draft.latitude == null ? null : Number(draft.latitude),
    longitude: draft.longitude === '' || draft.longitude == null ? null : Number(draft.longitude),
  };
}

function formatAddressSummary(summary) {
  if (!summary) {
    return 'No shipping address';
  }
  return [summary.address_1, summary.address_2, summary.city, summary.state, summary.postcode || summary.zip, summary.country].filter(Boolean).join(', ') || 'No shipping address';
}

function todayDateInput() {
  return new Date().toISOString().slice(0, 10);
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
