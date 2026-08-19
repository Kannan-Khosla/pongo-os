import { lazy, Suspense, useEffect, useId, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import './ReportIntelligence.css';
import { API_BASE_URL, apiFetch } from './api';
import { ItemImportHistory, ItemImportWorkspace } from './ItemImportWorkspace';
import MobileCodeScanner from './MobileCodeScanner';
import {
  ArrowLeft,
  BarChart3,
  Bell,
  Boxes,
  CalendarDays,
  Camera,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  ClipboardList,
  Copy,
  Download,
  Edit3,
  EllipsisVertical,
  Filter,
  FileSpreadsheet,
  History,
  LayoutDashboard,
  Link2,
  LogOut,
  MapPin,
  Menu,
  PackagePlus,
  PackageSearch,
  Plus,
  Printer,
  RefreshCw,
  RotateCcw,
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
  X,
} from 'lucide-react';

const ReportIntelligencePage = lazy(() => import('./ReportIntelligence'));
const DEFAULT_ROUTE_START_ADDRESS = '5855 99 Street NW, Edmonton, AB';
const ROUTE_DIRECTIONS = ['N', 'S', 'E', 'W', 'NE', 'NW', 'SE', 'SW', 'Central East', 'Central West'];
const ROUTE_ZONE_POSITIONS = {
  N: { left: 50, top: 16 },
  S: { left: 50, top: 84 },
  E: { left: 84, top: 50 },
  W: { left: 16, top: 50 },
  NE: { left: 76, top: 24 },
  NW: { left: 24, top: 24 },
  SE: { left: 76, top: 76 },
  SW: { left: 24, top: 76 },
  'Central East': { left: 60, top: 50 },
  'Central West': { left: 40, top: 50 },
};
const ROUTE_DRIVER_COLORS = ['#0f149a', '#ef5b3f', '#16835f', '#8b5cf6', '#d97706', '#0369a1', '#be123c', '#4d7c0f'];

function defaultRouteDirectionAssignments(driverCount) {
  const count = Math.max(1, Math.min(50, Number(driverCount) || 1));
  return Object.fromEntries(Array.from({ length: count }, (_, index) => [index + 1, []]));
}

export const browserNavigation = {
  assign: (url) => window.location.assign(url),
};

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
  'Tags',
];
const ITEM_DEFAULT_VISIBLE_COLUMNS = ['SKU / Barcode', 'Product Title', 'Brand', 'Category', 'In Stock', 'Sellable', 'Unit Cost'];

const SEARCH_FIELDS = ['SKU', 'Barcode', 'Description', 'Category', 'Brand', 'Tags', 'Manufacturer', 'Warehouse', 'Inventory Location'];

const BULK_ITEM_FIELD_GROUPS = [
  {
    title: 'Classification',
    fields: [
      { key: 'client', label: 'Client / organization' },
      { key: 'description', label: 'Description / local product title' },
      { key: 'brand', label: 'Brand' },
      { key: 'category', label: 'Category' },
      { key: 'add_tags', label: 'Add tags', placeholder: 'Seasonal, freezer, priority' },
      { key: 'manufacturer', label: 'Manufacturer' },
      { key: 'manufacturer_website', label: 'Manufacturer website', type: 'url' },
      { key: 'unit_of_measurement', label: 'Unit of measurement', placeholder: 'Each, case, bag' },
    ],
  },
  {
    title: 'Costs & planning',
    fields: [
      { key: 'unit_cost', label: 'Unit cost', type: 'number', step: '0.01', min: '0' },
      { key: 'sales_price', label: 'Sales price', type: 'number', step: '0.01', min: '0' },
      { key: 'recommended_retail_price', label: 'Recommended retail price', type: 'number', step: '0.01', min: '0' },
      { key: 'par_level', label: 'Par level', type: 'number', step: '0.001', min: '0' },
      { key: 'default_econ_order', label: 'Default order quantity', type: 'number', step: '0.001', min: '0' },
      { key: 'default_lead_time_days', label: 'Lead time (days)', type: 'number', step: '1', min: '0' },
    ],
  },
  {
    title: 'Storage & handling',
    fields: [
      { key: 'weight', label: 'Weight', type: 'number', step: '0.001', min: '0' },
      { key: 'storage_length', label: 'Storage length', type: 'number', step: '0.001', min: '0' },
      { key: 'storage_width', label: 'Storage width', type: 'number', step: '0.001', min: '0' },
      { key: 'storage_height', label: 'Storage height', type: 'number', step: '0.001', min: '0' },
    ],
  },
  {
    title: 'Item controls',
    fields: [
      { key: 'active', label: 'Active', type: 'boolean' },
      { key: 'reorder', label: 'Reorder enabled', type: 'boolean' },
      { key: 'non_inventory', label: 'Non-inventory item', type: 'boolean' },
      { key: 'assembly', label: 'Assembly', type: 'boolean' },
      { key: 'track_lot', label: 'Track lot', type: 'boolean' },
      { key: 'perishable', label: 'Perishable', type: 'boolean' },
      { key: 'serializable', label: 'Serializable', type: 'boolean' },
    ],
  },
];
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
const emptyItemsPagination = {
  page: 1,
  page_size: 20,
  total: 0,
  total_pages: 1,
  returned_count: 0,
  facets: { categories: [], brands: [] },
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
const emptyBusinessDashboard = {
  generated_at: null,
  today: { summary: {}, data_quality: [] },
  woocommerce_open_orders: { orders: [], total: null, summary: { open_orders_count: null }, statuses: {}, source: null, fetched_at: null, loading: false, error: '' },
  open_orders: { summary: {}, rows: [], data_quality: [] },
  subscriptions: { summary: {}, rows: [], data_quality: [], empty_state: null },
  revenue_comparison: { summary: {}, daily_series: [], data_quality: [] },
  order_map: { summary: {}, city_breakdown: [], markers: [], data_quality: [] },
  data_quality: [],
};
function emptyServerPagination(pageSize = 20) {
  return {
    page: 1,
    page_size: pageSize,
    total: 0,
    total_pages: 1,
    returned_count: 0,
    has_previous: false,
    has_next: false,
  };
}

function preservePagedRequest(filters, currentFilters, defaultPageSize) {
  const requested = filters && Object.keys(filters).length
    ? { ...(currentFilters || {}), ...filters }
    : { ...(currentFilters || {}) };
  const { pageSize, ...query } = requested;
  return {
    ...query,
    page: Math.max(1, Number(requested.page) || 1),
    page_size: Math.max(1, Number(requested.page_size || pageSize) || defaultPageSize),
  };
}
const emptyCompletedOrders = {
  orders: [],
  ...emptyServerPagination(),
};
const emptyWooStatus = {
  configured: false,
  base_url_present: false,
  consumer_key_present: false,
  consumer_secret_present: false,
  base_url: '',
  base_url_host: '',
  environment: 'development',
  configuration_source: 'backend_environment',
  configuration_updated_by: null,
  configuration_updated_at: null,
  read_only: true,
  writeback_enabled: false,
  dry_run: true,
  staging_live_test_mode: false,
  stock_write_allowed: false,
  order_status_write_allowed: false,
  product_metadata_write_allowed: false,
  customer_write_allowed: false,
  coupon_write_allowed: false,
  refund_write_allowed: false,
  delete_allowed: false,
  allowed_host: '',
  host_allowed: false,
  webhook_enabled: false,
  webhook_configured: false,
  webhook_secret_present: false,
  last_webhook_delivery: null,
  last_product_sync: null,
  last_order_sync: null,
  order_history_import: null,
  order_history_coverage: {},
  order_reconciliation: {
    enabled: false,
    running: false,
    healthy: false,
    degraded: false,
    stale: false,
    interval_seconds: 60,
    stale_after_seconds: 300,
    statuses: [],
    last_status: null,
    error_count: 0,
    last_attempt_at: null,
    last_success_at: null,
    last_failure_at: null,
    last_error: '',
    message: '',
  },
  last_error: '',
  message: 'WooCommerce status has not been checked.',
};
const wooOrderSyncStatuses = ['processing', 'on-hold', 'pending', 'completed', 'failed', 'cancelled', 'refunded'];
const ORDER_VIEW_REFRESH_INTERVAL_MS = 120000;
const WOO_SYNC_HEALTH_POLL_INTERVAL_MS = 120000;
const WEBHOOK_EVENT_POLL_INTERVAL_MS = 15000;
const WEBHOOK_EVENT_POLL_LIMIT = 50;
const ORDER_NOTIFICATION_HISTORY_LIMIT = 50;
const DEFAULT_ITEM_PAGE_FILTERS = Object.freeze({ page: 1, pageSize: 50, includeNonInventory: false });
const emptyOpenOrders = {
  orders: [],
  total: 0,
  available_count: 0,
  partial_count: 0,
  unavailable_count: 0,
  unknown_count: 0,
  page: 1,
  page_size: 20,
  total_pages: 1,
  returned_count: 0,
  has_previous: false,
  has_next: false,
};

export function withMutationIdempotency(ref, operation, payload) {
  const fingerprint = JSON.stringify([operation, payload]);
  if (ref.current?.fingerprint !== fingerprint) {
    const suffix = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
    ref.current = { fingerprint, key: `${operation}-${suffix}` };
  }
  return { ...payload, idempotency_key: ref.current.key };
}

export function resetMutationIdempotency(ref) {
  ref.current = null;
}

function normalizeWooStatus(value) {
  return String(value || '').trim().toLowerCase().replace(/^wc-/, '');
}

function normalizeLiveWooOpenOrder(order = {}) {
  return {
    ...order,
    woo_order_id: order.woo_order_id ?? order.id ?? null,
    local_order_id: order.local_order_id ?? null,
    woo_order_number: String(order.number ?? order.woo_order_number ?? order.order_number ?? order.woo_order_id ?? order.id ?? ''),
    customer_name: order.customer_name || order.customer || [order.billing?.first_name, order.billing?.last_name].filter(Boolean).join(' ') || 'Unknown customer',
    customer_email: order.email || order.customer_email || order.billing?.email || '',
    woo_status: normalizeWooStatus(order.status || order.woo_status),
    date_created: order.date_created || order.placed_on || order.date || null,
    total: order.total ?? order.order_total ?? null,
  };
}

function normalizeLiveWooOpenOrders(body = {}) {
  const orders = (Array.isArray(body.orders) ? body.orders : [])
    .map(normalizeLiveWooOpenOrder)
    .filter((order) => order.woo_status === 'processing');
  const exactTotal = Number(body.total ?? body.count ?? body.summary?.open_orders_count ?? orders.length);
  const total = Number.isFinite(exactTotal) ? exactTotal : orders.length;
  return {
    ...body,
    orders,
    total,
    summary: { ...(body.summary || {}), open_orders_count: total },
    loading: false,
    error: '',
  };
}

async function fetchOrderDetailRequest(orderId) {
  const response = await apiFetch(`${API_BASE_URL}/api/orders/${orderId}`);
  if (!response.ok) {
    let detail = '';
    try {
      detail = apiErrorDetail(await response.json());
    } catch {
      detail = await safeResponseText(response);
    }
    throw new Error(detail || `Order detail API returned ${response.status}`);
  }
  return response.json();
}

async function postOrderMutation(path, payload, { idempotencyRef, operation, includeKeyInBody = true }) {
  const mutation = withMutationIdempotency(idempotencyRef, operation, payload);
  const idempotencyKey = mutation.idempotency_key;
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Idempotency-Key': idempotencyKey,
    },
    body: JSON.stringify(includeKeyInBody ? mutation : payload),
  });
  if (!response.ok) {
    let detail = '';
    try {
      detail = apiErrorDetail(await response.json());
    } catch {
      detail = await safeResponseText(response);
    }
    throw new Error(detail || `API returned ${response.status}`);
  }
  return response.json();
}

function updateLiveWooOrderStatus(wooOrderId, targetStatus, payload, idempotencyRef) {
  return postOrderMutation(`/api/orders/woocommerce/${wooOrderId}/status`, { target_status: targetStatus, ...payload }, {
    idempotencyRef,
    operation: `woo-order-${wooOrderId}-${targetStatus}`,
    includeKeyInBody: true,
  });
}

function reconcileLiveWooOrder(wooOrderId, idempotencyRef) {
  return postOrderMutation(`/api/orders/woocommerce/${wooOrderId}/reconcile`, {}, {
    idempotencyRef,
    operation: `woo-order-${wooOrderId}-reconcile`,
    includeKeyInBody: true,
  });
}

function substituteOrderLine(orderId, lineId, payload, idempotencyRef) {
  return postOrderMutation(`/api/orders/${orderId}/lines/${lineId}/substitute`, payload, {
    idempotencyRef,
    operation: `order-${orderId}-line-${lineId}-substitute`,
    includeKeyInBody: true,
  });
}

function prepareCompletedOrderForPicking(orderId, payload, idempotencyRef) {
  return postOrderMutation(`/api/orders/${orderId}/prepare-picking`, payload, {
    idempotencyRef,
    operation: `order-${orderId}-prepare-picking`,
    includeKeyInBody: true,
  });
}

const orderSubpages = [
  { id: 'open', label: 'Open Orders', href: '#/orders/open' },
  { id: 'allocate', label: 'Allocate', href: '#/orders/allocate' },
  { id: 'pick', label: 'Pick Orders', href: '#/orders/pick' },
  { id: 'completed', label: 'Completed Orders', href: '#/orders/completed' },
  { id: 'history', label: 'Order History', href: '#/orders/history' },
];

const inventorySubpages = [
  { id: 'all', label: 'All Inventory', href: '#/inventory/all' },
  { id: 'by-location', label: 'Inventory by Location', href: '#/inventory/by-location' },
  { id: 'low-stock', label: 'Low Stock', href: '#/inventory/low-stock' },
  { id: 'expiring', label: 'Expiring Stock', href: '#/inventory/expiring' },
  { id: 'par-level', label: 'Par Level', href: '#/inventory/par-level' },
  { id: 'movements', label: 'Stock Movements', href: '#/inventory/movements' },
];

const routeSubpages = [
  { id: 'live', label: 'Live Planner', href: '#/routes/live' },
  { id: 'completed', label: 'Completed Routes', href: '#/routes/completed' },
];

const orderSubpageMeta = {
  open: { title: 'Open Orders', kicker: 'Orders / Open' },
  allocate: { title: 'Allocate', kicker: 'Orders / Allocation' },
  pick: { title: 'Pick Orders', kicker: 'Orders / Picking' },
  completed: { title: 'Completed Orders', kicker: 'Orders / Completed' },
  history: { title: 'Order History', kicker: 'Orders / History' },
};

const inventorySubpageMeta = {
  all: { title: 'All Inventory', kicker: 'Inventory / Product stock' },
  'by-location': { title: 'Inventory by Location', kicker: 'Inventory / Warehouse stock' },
  'low-stock': { title: 'Low Stock', kicker: 'Inventory / Under par' },
  expiring: { title: 'Expiring Stock', kicker: 'Inventory / Expiration tracking' },
  'par-level': { title: 'Par Level', kicker: 'Inventory / Reorder planning' },
  movements: { title: 'Stock Movements', kicker: 'Inventory / Audit ledger' },
};

const routeSubpageMeta = {
  live: { title: 'Delivery Routes', kicker: 'Routes / Live planning' },
  completed: { title: 'Completed Routes', kicker: 'Routes / Completed orders' },
};

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'inventory-overview', label: 'Inventory Overview', icon: ClipboardList },
  { id: 'items', label: 'Items', icon: PackageSearch },
  { id: 'inventory', label: 'Inventory', icon: Boxes },
  { id: 'locations', label: 'Locations', icon: MapPin },
  { id: 'receiving', label: 'Receiving', icon: Truck },
  { id: 'scanner', label: 'Scanner', icon: PackageSearch },
  { id: 'orders', label: 'Orders', icon: ShoppingCart },
  { id: 'cycle-count', label: 'Cycle Count', icon: ClipboardCheck },
  { id: 'reports', label: 'Reports', icon: BarChart3 },
  { id: 'routes', label: 'Routes', icon: Route },
  { id: 'insights', label: 'Insights', icon: BarChart3 },
  { id: 'settings', label: 'Settings', icon: Settings },
];

const navigationGroups = [
  { id: 'command', label: 'Command', icon: LayoutDashboard, href: '#dashboard', pages: ['dashboard', 'inventory-overview'] },
  { id: 'commerce', label: 'Commerce', icon: ShoppingCart, href: '#/orders/open', pages: ['orders', 'routes'] },
  { id: 'warehouse', label: 'Warehouse', icon: Boxes, href: '#/inventory/all', pages: ['items', 'inventory', 'locations', 'receiving', 'scanner', 'cycle-count'] },
  { id: 'intelligence', label: 'Intelligence', icon: BarChart3, href: '#insights', pages: ['insights', 'reports'] },
  { id: 'system', label: 'System', icon: Settings, href: '#settings', pages: ['settings'] },
];

const DEFAULT_REPORT_KEY = 'inventory-export';

function navItemHref(item) {
  if (item.id === 'orders') return '#/orders/open';
  if (item.id === 'inventory') return '#/inventory/all';
  if (item.id === 'receiving') return '#/receiving/direct';
  if (item.id === 'reports') return `#/reports/inventory/${DEFAULT_REPORT_KEY}`;
  if (item.id === 'insights') return '#/insights/overview';
  if (item.id === 'routes') return '#/routes/live';
  return `#${item.id}`;
}

const insightTabs = [
  { id: 'overview', label: 'Executive Overview', endpoint: '/api/insights/overview', exportable: false, description: 'Revenue, customers, demand, inventory value, and operational risk.' },
  { id: 'orders-revenue', label: 'Orders & Revenue', endpoint: '/api/insights/orders-revenue', exportable: true, description: 'Order volume, sales, discounts, refunds, payment mix, and daily performance.' },
  { id: 'customer-metrics', label: 'Customer Metrics', endpoint: '/api/insights/customer-metrics', exportable: true, description: 'Customer counts, repeat behavior, lifetime value, dormancy, and reorder readiness.' },
  { id: 'customer-segmentation', label: 'Customer Segmentation', endpoint: '/api/insights/customer-segmentation', exportable: false, description: 'RFM-style segments for champions, loyal buyers, one-time buyers, dormant customers, and lost customers.' },
  { id: 'product-sku', label: 'Product & SKU Metrics', endpoint: '/api/insights/product-sku', exportable: true, description: 'SKU demand, revenue, estimated cost, estimated margin, stock, and movement tiers.' },
  { id: 'subscriptions', label: 'Subscriptions', endpoint: '/api/insights/subscriptions', exportable: false, description: 'Subscription health when local WooCommerce Subscriptions snapshots are available.' },
  { id: 'subscription-products', label: 'Subscription Products', endpoint: '/api/insights/subscription-products', exportable: false, description: 'Subscription product demand and stock risk when subscription data is synced.' },
  { id: 'inventory-forecasting', label: 'Inventory Forecasting', endpoint: '/api/insights/inventory-forecasting', exportable: false, description: 'Velocity, days of stock left, deterministic demand forecast, and reorder suggestions.' },
  { id: 'coupons', label: 'Coupons & Promotions', endpoint: '/api/insights/coupons', exportable: false, description: 'Coupon usage and discount quality when coupon line snapshots exist locally.' },
  { id: 'payment-health', label: 'Payment Health', endpoint: '/api/insights/payment-health', exportable: false, description: 'Payment method mix, failure rates, and duplicate failed-to-success patterns.' },
  { id: 'geography', label: 'Geography & Delivery', endpoint: '/api/insights/geography', exportable: true, description: 'City and postal-code demand, customer density, revenue, and repeat behavior.' },
  { id: 'product-affinity', label: 'Product Affinity', endpoint: '/api/insights/product-affinity', exportable: false, description: 'Frequently bought together SKUs and cross-sell candidates from multi-line orders.' },
  { id: 'reorder-forecast', label: 'Reorder Forecast', endpoint: '/api/insights/reorder-forecast', exportable: true, description: 'Customers likely due or overdue for reorder based on local repeat purchase intervals.' },
];

const insightFiltersByTab = {
  overview: ['start_date', 'end_date', 'brand', 'category', 'sku'],
  'orders-revenue': ['start_date', 'end_date', 'payment_method', 'order_status'],
  'customer-metrics': ['start_date', 'end_date', 'customer_email'],
  'customer-segmentation': ['start_date', 'end_date', 'customer_email'],
  'product-sku': ['start_date', 'end_date', 'brand', 'category', 'sku'],
  subscriptions: ['customer_email', 'sku'],
  'subscription-products': ['brand', 'category', 'sku'],
  'inventory-forecasting': ['start_date', 'end_date', 'brand', 'category', 'sku'],
  coupons: ['start_date', 'end_date'],
  'payment-health': ['start_date', 'end_date', 'payment_method'],
  geography: ['start_date', 'end_date', 'city', 'postal_code'],
  'product-affinity': ['start_date', 'end_date', 'sku'],
  'reorder-forecast': ['start_date', 'end_date', 'customer_email'],
};

const insightFilterLabels = {
  start_date: 'Start Date',
  end_date: 'End Date',
  brand: 'Brand',
  category: 'Category',
  sku: 'SKU',
  customer_email: 'Customer Email',
  city: 'City',
  postal_code: 'Postal Code',
  payment_method: 'Payment Method',
  order_status: 'Order Status',
};

const insightColumnsByTab = {
  overview: ['sku', 'product_name', 'risk_level', 'current_sellable', 'daily_velocity', 'days_of_stock_left'],
  'orders-revenue': ['date', 'order_count', 'gross_sales', 'net_sales', 'units_sold'],
  'customer-metrics': ['customer_name', 'email', 'order_count', 'lifetime_spend', 'average_days_between_orders', 'last_order_date'],
  'customer-segmentation': ['segment', 'customer_count', 'revenue', 'repeat_rate'],
  'product-sku': ['sku', 'product_name', 'brand', 'category', 'units_sold', 'revenue', 'estimated_margin', 'current_sellable'],
  subscriptions: ['subscription_id', 'customer', 'email', 'status', 'next_payment_date', 'subscription_total'],
  'subscription-products': ['sku', 'product_name', 'active_subscriptions', 'upcoming_30_day_units', 'current_sellable', 'stockout_risk'],
  'inventory-forecasting': ['sku', 'product_name', 'current_sellable', 'units_sold_30d', 'daily_velocity', 'days_of_stock_left', 'suggested_reorder_qty', 'risk_level'],
  coupons: ['coupon_code', 'usage_count', 'order_count', 'revenue', 'discount_amount', 'average_order_value'],
  'payment-health': ['payment_method', 'attempt_count', 'success_count', 'failed_count', 'success_rate', 'revenue', 'duplicate_pattern_count'],
  geography: ['city', 'postal_code', 'order_count', 'customer_count', 'revenue', 'average_order_value', 'repeat_customer_rate'],
  'product-affinity': ['base_sku', 'paired_sku', 'pair_order_count', 'attach_rate', 'average_order_value_with_pair', 'suggested_cross_sell_text'],
  'reorder-forecast': ['customer_email', 'customer_name', 'last_order_date', 'most_repeated_sku', 'average_reorder_interval_days', 'days_overdue', 'churn_risk_score', 'recommended_action'],
};

const reportCategories = [
  { id: 'executive', label: 'Executive' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'orders', label: 'Orders' },
  { id: 'operations', label: 'Operations' },
  { id: 'intelligence', label: 'Intelligence' },
  { id: 'receiving', label: 'Receiving' },
  { id: 'sku-barcode', label: 'SKU / Barcode' },
];

const intelligentReportDefinitions = [
  { key: 'executive-weekly', label: 'Executive Weekly', category: 'executive' },
  { key: 'sales-by-sku', label: 'Sales by SKU', category: 'executive' },
  { key: 'inventory-cost-category', label: 'Cost by Category', category: 'inventory' },
  { key: 'inventory-cost-sku', label: 'Cost by SKU', category: 'inventory' },
  { key: 'inventory-in-stock', label: 'Inventory in Stock', category: 'inventory' },
  { key: 'inventory-usage', label: 'Inventory Usage', category: 'inventory' },
  { key: 'inventory-export', label: 'Inventory Export', category: 'inventory' },
  { key: 'unallocated-order-items', label: 'Unallocated Items', category: 'orders' },
  { key: 'incomplete-orders', label: 'Incomplete Orders', category: 'orders' },
  { key: 'order-summary', label: 'Order Summary', category: 'orders' },
  { key: 'daily-item-orders', label: 'Daily Item Orders', category: 'orders' },
  { key: 'detailed-customer-orders', label: 'Customer Orders', category: 'orders' },
  { key: 'delivered-inventory', label: 'Delivered Inventory', category: 'operations' },
  { key: 'received-inventory-intelligence', apiKey: 'received-inventory', label: 'Received Inventory', category: 'operations' },
  { key: 'po-received', label: 'PO Received', category: 'operations' },
  { key: 'inventory-forecast', label: 'Inventory Forecast', category: 'intelligence' },
  { key: 'reorder-intelligence', label: 'Reorder Intelligence', category: 'intelligence' },
];
const intelligentReportKeys = new Set(intelligentReportDefinitions.map((report) => report.key));

const expandedReportDefinitions = [
  { key: 'inventory-valuation', label: 'Inventory Valuation', category: 'inventory', filters: ['warehouse', 'inventory_location', 'brand', 'category', 'sku'] },
  { key: 'low-stock', label: 'Low Stock / Reorder', category: 'inventory', filters: ['warehouse', 'inventory_location', 'brand', 'category', 'sku'] },
  { key: 'stock-movement-ledger', label: 'Stock Movement Ledger', category: 'inventory', filters: ['start_date', 'end_date', 'warehouse', 'inventory_location', 'sku', 'barcode', 'movement_type'] },
  { key: 'item-activity', label: 'Item Activity', category: 'inventory', filters: ['start_date', 'end_date', 'sku', 'barcode', 'movement_type'] },
  { key: 'location-utilization', label: 'Location Utilization', category: 'inventory', filters: ['warehouse', 'inventory_location'] },
  { key: 'margin-by-sku', label: 'Margin by SKU', category: 'inventory', filters: ['start_date', 'end_date', 'brand', 'category', 'sku'] },
  { key: 'receiving-cost', label: 'Receiving Cost', category: 'receiving', filters: ['start_date', 'end_date', 'warehouse', 'inventory_location', 'sku'] },
  { key: 'adjustments', label: 'Adjustment / Damage / Loss', category: 'receiving', filters: ['warehouse', 'inventory_location', 'sku', 'adjustment_type'] },
];

const legacyReportDefinitions = [
  { key: 'received-inventory', label: 'Received Inventory', category: 'receiving', kind: 'received' },
  { key: 'fulfillment', label: 'Fulfillment', category: 'orders', kind: 'fulfillment' },
  { key: 'sku-orders', label: 'SKU Orders', category: 'sku-barcode', kind: 'sku-orders' },
];

const allReportDefinitions = [...intelligentReportDefinitions, ...expandedReportDefinitions, ...legacyReportDefinitions];

const reportFilterLabels = {
  sku: 'SKU',
  barcode: 'Barcode',
  inventory_location: 'Inventory Location',
  start_date: 'Start Date',
  end_date: 'End Date',
  movement_type: 'Movement Type',
  adjustment_type: 'Adjustment Type',
};

function reportHref(report) {
  return `#/reports/${report.category}/${report.key}`;
}

const pageMeta = {
  dashboard: {
    title: 'Dashboard',
    kicker: 'Business snapshot',
    tabs: [],
  },
  'inventory-overview': {
    title: 'Inventory Overview',
    kicker: 'Operational inventory health',
    tabs: ['Health', 'Work Queues', 'Exceptions'],
  },
  insights: {
    title: 'Pongo Insights',
    kicker: 'Business intelligence',
    tabs: [],
  },
  items: {
    title: 'Items',
    kicker: 'Items',
    tabs: [
      { label: 'New Item', href: '#/items/new' },
      { label: 'All Items', href: '#items' },
    ],
  },
  inventory: {
    title: 'Inventory',
    kicker: 'Main Warehouse Inventory',
    tabs: [],
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
    tabs: [],
  },
  scanner: {
    title: 'Scanner',
    kicker: 'Warehouse keyboard-scanner workflows',
    tabs: ['Lookup', 'Receiving', 'Cycle Count', 'Adjustment', 'Picking'],
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
    tabs: reportCategories.map((category) => ({
      label: category.label,
      href: reportHref(allReportDefinitions.find((report) => report.category === category.id)),
      category: category.id,
    })),
  },
  routes: {
    title: 'Routes',
    kicker: 'Route planning',
    tabs: routeSubpages,
  },
  settings: {
    title: 'WooCommerce Connection',
    kicker: 'Settings / Integrations',
    tabs: [
      { label: 'Connection', href: '#/settings/connection' },
      { label: 'Sync & Mapping', href: '#/settings/sync' },
      { label: 'Writeback', href: '#/settings/writeback' },
      { label: 'Google Sheets', href: '#/settings/google-sheets' },
    ],
  },
};

const detailTabs = [];

const settingsViews = [
  { id: 'connection', label: 'Connection', href: '#/settings/connection' },
  { id: 'sync', label: 'Sync & Mapping', href: '#/settings/sync' },
  { id: 'writeback', label: 'Writeback', href: '#/settings/writeback' },
  { id: 'google-sheets', label: 'Google Sheets', href: '#/settings/google-sheets' },
];

const settingsViewMeta = {
  connection: {
    title: 'WooCommerce Connection',
    kicker: 'Settings / Integrations',
  },
  sync: {
    title: 'Sync & Mapping',
    kicker: 'Settings / WooCommerce',
  },
  writeback: {
    title: 'Writeback Control',
    kicker: 'Settings / WooCommerce',
  },
  'google-sheets': {
    title: 'Google Sheets',
    kicker: 'Settings / Integrations',
  },
};

function submitSearchOnEnter(event, submit) {
  if (event.key !== 'Enter') {
    return;
  }
  event.preventDefault();
  submit();
}

function InventoryKeywordSearch({ value, onChange, onSearch = () => {}, onSelect = null, onSubmit = null, label, placeholder, className = '', autoFocus = false, hideLabel = false }) {
  const listboxId = useId();
  const inputRef = useRef(null);
  const [suggestions, setSuggestions] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [activeIndex, setActiveIndex] = useState(-1);
  const dismissedQueryRef = useRef(null);
  const mountedRef = useRef(false);
  const searchRef = useRef(onSearch);
  searchRef.current = onSearch;

  useEffect(() => {
    if (!mountedRef.current) {
      mountedRef.current = true;
      return undefined;
    }
    const query = value.trim();
    if (dismissedQueryRef.current === query) return undefined;
    const timer = window.setTimeout(() => searchRef.current(query), 250);
    return () => window.clearTimeout(timer);
  }, [value]);

  useEffect(() => {
    const query = value.trim();
    if (!query) {
      setSuggestions([]);
      setOpen(false);
      setLoading(false);
      setError('');
      return undefined;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      if (dismissedQueryRef.current === query) return;
      setLoading(true);
      setError('');
      setOpen(true);
      try {
        const response = await apiFetch(`${API_BASE_URL}/api/items/search?q=${encodeURIComponent(query)}&limit=100`, { signal: controller.signal });
        if (!response.ok) throw new Error(`Item search returned ${response.status}`);
        const body = await response.json();
        if (dismissedQueryRef.current !== query) {
          setSuggestions(body.items || []);
          setActiveIndex(-1);
        }
      } catch (searchError) {
        if (searchError.name !== 'AbortError' && dismissedQueryRef.current !== query) {
          setSuggestions([]);
          setError('Suggestions unavailable. Press Enter to search.');
        }
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 100);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [value]);

  function submit(nextValue = value.trim()) {
    dismissedQueryRef.current = nextValue.trim();
    setOpen(false);
    setActiveIndex(-1);
    searchRef.current(nextValue.trim());
  }

  function chooseSuggestion(item) {
    const nextValue = item.sku || item.barcode || item.product_name || item.description || '';
    dismissedQueryRef.current = nextValue.trim();
    onChange(nextValue);
    onSelect?.(item);
    submit(nextValue);
  }

  function changeQuery(nextValue) {
    dismissedQueryRef.current = null;
    setOpen(false);
    setActiveIndex(-1);
    setSuggestions([]);
    setError('');
    onChange(nextValue);
  }

  function handleKeyDown(event) {
    const queryDismissed = dismissedQueryRef.current === value.trim();
    if (event.key === 'ArrowDown' && suggestions.length && !queryDismissed) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => (current + 1) % suggestions.length);
      return;
    }
    if (event.key === 'ArrowUp' && suggestions.length && !queryDismissed) {
      event.preventDefault();
      setOpen(true);
      setActiveIndex((current) => (current <= 0 ? suggestions.length - 1 : current - 1));
      return;
    }
    if (event.key === 'Escape') {
      setOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (open && activeIndex >= 0) chooseSuggestion(suggestions[activeIndex]);
      else {
        submit();
        onSubmit?.(value.trim());
      }
    }
  }

  return (
    <div className={`keyword-item-search ${className}`} onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
    }}>
      {!hideLabel && <span>{label}</span>}
      <div className="keyword-search-input">
        <input
          aria-label={label}
          aria-autocomplete="list"
          aria-controls={listboxId}
          aria-expanded={open}
          aria-activedescendant={activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined}
          autoComplete="off"
          autoFocus={autoFocus}
          onChange={(event) => changeQuery(event.target.value)}
          onFocus={() => value.trim() && dismissedQueryRef.current !== value.trim() && setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          ref={inputRef}
          role="combobox"
          type="search"
          value={value}
        />
        <Search aria-hidden="true" size={18} />
      </div>
      <FloatingMenu ariaLabel="Inventory suggestions" className="keyword-suggestions" id={listboxId} menuRole="listbox" onClose={() => setOpen(false)} open={open} triggerRef={inputRef}>
          {loading && <div className="keyword-suggestion-status" role="status">Finding inventory…</div>}
          {!loading && error && <div className="keyword-suggestion-status">{error}</div>}
          {!loading && !error && !suggestions.length && <div className="keyword-suggestion-status">No matching inventory items</div>}
          {!loading && suggestions.map((item, index) => (
            <button
              aria-selected={index === activeIndex}
              className={`keyword-suggestion${index === activeIndex ? ' is-active' : ''}`}
              id={`${listboxId}-${index}`}
              key={item.id}
              onMouseDown={(event) => event.preventDefault()}
              onClick={() => chooseSuggestion(item)}
              role="option"
              type="button"
            >
              <span className="keyword-suggestion-copy">
                <strong>{decodeHtmlEntities(item.product_name || item.description || 'Untitled inventory item')}</strong>
                <small>{[item.brand, item.category].filter(Boolean).map(decodeHtmlEntities).join(' · ') || 'Inventory item'}</small>
              </span>
              <span className="keyword-suggestion-identifiers">
                {item.sku && <b>SKU {item.sku}</b>}
                {item.barcode && <small>{item.barcode}</small>}
              </span>
            </button>
          ))}
      </FloatingMenu>
    </div>
  );
}

const genericRows = [
  ['Work queue', 'Awaiting setup', 'Planning', 'Main Warehouse'],
  ['Exceptions', 'Needs review', 'Operations', 'Main Warehouse'],
  ['Exports', 'Ready later', 'Reporting', 'Main Warehouse'],
];

const dashboardCards = [
  ['Orders', '0', 'Open order queue', ShoppingCart],
  ['Items', '0', 'Inventory items', PackageSearch],
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
  const [path, queryString = ''] = hash.split('?');
  const query = new URLSearchParams(queryString);
  if (path === 'items/categories') {
    return { pageId: 'items', itemView: 'categories' };
  }
  if (path === 'items/commodities') {
    return { pageId: 'items', itemView: 'commodities' };
  }
  if (path === 'items/new') {
    return { pageId: 'items', itemView: 'new' };
  }
  if (path === 'items/import') {
    const importOutcome = query.get('outcome') || '';
    return { pageId: 'items', itemView: 'import', importPreviewId: query.get('preview') || '', importOutcome: ['add_items', 'update_items', 'update_stock', 'starting_inventory'].includes(importOutcome) ? importOutcome : '' };
  }
  if (path === 'items/imports') {
    return { pageId: 'items', itemView: 'import-history' };
  }
  if (path.startsWith('items/')) {
    return { pageId: 'items', itemView: 'detail', itemId: path.split('/')[1] };
  }
  if (path === 'locations/new') {
    return { pageId: 'locations', locationView: 'new' };
  }
  if (path === 'locations/stock') {
    return { pageId: 'locations', locationView: 'stock' };
  }
  if (path.startsWith('locations/')) {
    return { pageId: 'locations', locationView: 'detail', locationId: path.split('/')[1] };
  }
  if (path === 'orders') {
    return { pageId: 'orders', ordersView: 'open' };
  }
  if (path.startsWith('orders/')) {
    const ordersView = path.split('/')[1] || 'open';
    const knownView = orderSubpages.some((page) => page.id === ordersView);
    return { pageId: 'orders', ordersView: knownView ? ordersView : 'open' };
  }
  if (path === 'inventory' || path.startsWith('inventory/')) {
    const inventoryView = path.split('/')[1] || 'all';
    const knownView = inventorySubpages.some((page) => page.id === inventoryView);
    const requestedPage = Math.max(1, Number.parseInt(query.get('page') || '1', 10) || 1);
    const requestedPageSize = Number.parseInt(query.get('page_size') || '20', 10);
    return {
      pageId: 'inventory',
      inventoryView: knownView ? inventoryView : 'all',
      inventoryPage: requestedPage,
      inventoryPageSize: [20, 50, 100].includes(requestedPageSize) ? requestedPageSize : 20,
      inventorySearch: query.get('search') || '',
      inventoryCategory: query.get('category') || '',
      inventoryBrand: query.get('brand') || '',
      inventoryDataQuality: query.get('data_quality') || '',
      inventorySortBy: query.get('sort_by') || 'sku',
      inventorySortDir: query.get('sort_dir') === 'desc' ? 'desc' : 'asc',
    };
  }
  if (path === 'reports' || path.startsWith('reports/')) {
    const segments = path.split('/');
    const requestedKey = segments[2] || segments[1] || DEFAULT_REPORT_KEY;
    const resolvedKey = requestedKey === 'inventory-valuation' ? DEFAULT_REPORT_KEY : requestedKey;
    const report = allReportDefinitions.find((candidate) => candidate.key === resolvedKey)
      || allReportDefinitions.find((candidate) => candidate.key === DEFAULT_REPORT_KEY);
    return { pageId: 'reports', reportCategory: report.category, reportKey: report.key };
  }
  if (path === 'insights' || path.startsWith('insights/')) {
    const requestedView = path.split('/')[1] || 'overview';
    const view = insightTabs.some((tab) => tab.id === requestedView) ? requestedView : 'overview';
    return { pageId: 'insights', insightsView: view };
  }
  if (path === 'receiving' || path.startsWith('receiving/')) {
    const requestedView = path.split('/')[1] || 'direct';
    const view = ['direct', 'bulk', 'history'].includes(requestedView) ? requestedView : 'direct';
    return { pageId: 'receiving', receivingView: view };
  }
  if (path === 'routes' || path.startsWith('routes/')) {
    const requestedView = path.split('/')[1] || 'live';
    const view = routeSubpages.some((candidate) => candidate.id === requestedView) ? requestedView : 'live';
    return { pageId: 'routes', routesView: view };
  }
  if (path === 'settings' || path.startsWith('settings/')) {
    const requestedView = path.split('/')[1] || 'connection';
    const view = settingsViews.some((candidate) => candidate.id === requestedView) ? requestedView : 'connection';
    return {
      pageId: 'settings',
      settingsView: view,
      googleOAuthResult: view === 'google-sheets' ? query.get('google') || '' : '',
    };
  }
  return navItems.some((item) => item.id === path) ? { pageId: path } : { pageId: 'dashboard' };
}

export default function App({ currentUser = null, onLogout = null }) {
  const isDemo = currentUser?.access_level === 'demo';
  const [route, setRoute] = useState(parseHashRoute);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationButtonRef = useRef(null);
  const [items, setItems] = useState([]);
  const [itemsPagination, setItemsPagination] = useState(emptyItemsPagination);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [itemsError, setItemsError] = useState('');
  const [locations, setLocations] = useState([]);
  const [locationsLoading, setLocationsLoading] = useState(false);
  const [locationsError, setLocationsError] = useState('');
  const [inventorySummary, setInventorySummary] = useState(emptyInventorySummary);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventoryError, setInventoryError] = useState('');
  const [receipts, setReceipts] = useState([]);
  const [receiptsPagination, setReceiptsPagination] = useState(() => emptyServerPagination());
  const [receiptsLoading, setReceiptsLoading] = useState(false);
  const [receiptsError, setReceiptsError] = useState('');
  const [stockMovements, setStockMovements] = useState([]);
  const [stockMovementsPagination, setStockMovementsPagination] = useState(() => emptyServerPagination());
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
  const [businessDashboard, setBusinessDashboard] = useState(emptyBusinessDashboard);
  const [businessDashboardLoading, setBusinessDashboardLoading] = useState(false);
  const [businessDashboardError, setBusinessDashboardError] = useState('');
  const [cycleCounts, setCycleCounts] = useState([]);
  const [cycleCountsPagination, setCycleCountsPagination] = useState(() => emptyServerPagination(50));
  const [cycleCountsLoading, setCycleCountsLoading] = useState(false);
  const [cycleCountsError, setCycleCountsError] = useState('');
  const [wooStatus, setWooStatus] = useState(emptyWooStatus);
  const [wooPreview, setWooPreview] = useState(null);
  const [wooCommitSummary, setWooCommitSummary] = useState(null);
  const [wooOrderPreview, setWooOrderPreview] = useState(null);
  const [wooOrderCommitSummary, setWooOrderCommitSummary] = useState(null);
  const [wooSyncRuns, setWooSyncRuns] = useState([]);
  const [wooSyncRunsPagination, setWooSyncRunsPagination] = useState(() => emptyServerPagination(50));
  const [wooRemapCandidates, setWooRemapCandidates] = useState({ candidates: [], total: 0 });
  const [wooRemapCandidatesPagination, setWooRemapCandidatesPagination] = useState(() => emptyServerPagination(100));
  const [wooRemapMappings, setWooRemapMappings] = useState({ mappings: [], total: 0 });
  const [wooRemapMappingsPagination, setWooRemapMappingsPagination] = useState(() => emptyServerPagination(100));
  const [wooRemapPreview, setWooRemapPreview] = useState(null);
  const [wooRemapMessage, setWooRemapMessage] = useState('');
  const [wooWritebackQueue, setWooWritebackQueue] = useState({ queue: [], total: 0 });
  const [wooWritebackQueuePagination, setWooWritebackQueuePagination] = useState(() => emptyServerPagination(50));
  const [wooStockSyncJobs, setWooStockSyncJobs] = useState([]);
  const [wooStockSyncJobsPagination, setWooStockSyncJobsPagination] = useState(() => emptyServerPagination(25));
  const [wooWritebackPreview, setWooWritebackPreview] = useState(null);
  const [wooWritebackMessage, setWooWritebackMessage] = useState('');
  const [wooLoading, setWooLoading] = useState(false);
  const [wooError, setWooError] = useState('');
  const [wooHealthError, setWooHealthError] = useState('');
  const [openOrders, setOpenOrders] = useState(emptyOpenOrders);
  const [openOrdersLoading, setOpenOrdersLoading] = useState(false);
  const [openOrdersError, setOpenOrdersError] = useState('');
  const [openOrderDetail, setOpenOrderDetail] = useState(null);
  const [completedOrders, setCompletedOrders] = useState(emptyCompletedOrders);
  const [completedOrdersLoading, setCompletedOrdersLoading] = useState(false);
  const [completedOrdersError, setCompletedOrdersError] = useState('');
  const [orderCompletionSummary, setOrderCompletionSummary] = useState(null);
  const [allocationPreview, setAllocationPreview] = useState(null);
  const [allocationCommitSummary, setAllocationCommitSummary] = useState(null);
  const [allocationHistory, setAllocationHistory] = useState([]);
  const [allocationHistoryPagination, setAllocationHistoryPagination] = useState(() => emptyServerPagination());
  const [allocationDetail, setAllocationDetail] = useState(null);
  const [allocationLoading, setAllocationLoading] = useState(false);
  const [allocationError, setAllocationError] = useState('');
  const [pickPreview, setPickPreview] = useState(null);
  const [pickCommitSummary, setPickCommitSummary] = useState(null);
  const [pickHistory, setPickHistory] = useState([]);
  const [pickHistoryPagination, setPickHistoryPagination] = useState(() => emptyServerPagination());
  const [pickDetail, setPickDetail] = useState(null);
  const [pickLoading, setPickLoading] = useState(false);
  const [pickError, setPickError] = useState('');
  const [fulfillmentPreview, setFulfillmentPreview] = useState(null);
  const [fulfillmentCommitSummary, setFulfillmentCommitSummary] = useState(null);
  const [fulfillmentHistory, setFulfillmentHistory] = useState([]);
  const [fulfillmentHistoryPagination, setFulfillmentHistoryPagination] = useState(() => emptyServerPagination());
  const [fulfillmentDetail, setFulfillmentDetail] = useState(null);
  const [fulfillmentLoading, setFulfillmentLoading] = useState(false);
  const [fulfillmentError, setFulfillmentError] = useState('');
  const [routeCandidates, setRouteCandidates] = useState({ total_candidates: 0, candidates: [] });
  const [routeCandidatesPagination, setRouteCandidatesPagination] = useState(() => emptyServerPagination(50));
  const [routeCandidatesLoading, setRouteCandidatesLoading] = useState(false);
  const [routeCandidatesError, setRouteCandidatesError] = useState('');
  const [routePreview, setRoutePreview] = useState(null);
  const [routeCommitSummary, setRouteCommitSummary] = useState(null);
  const [routesHistory, setRoutesHistory] = useState({ routes: [], total: 0 });
  const [routesHistoryPagination, setRoutesHistoryPagination] = useState(() => emptyServerPagination(50));
  const [routeDetail, setRouteDetail] = useState(null);
  const [routeMapPayload, setRouteMapPayload] = useState(null);
  const [routeProviderMessage, setRouteProviderMessage] = useState('');
  const [openOrderRoutePlan, setOpenOrderRoutePlan] = useState(null);
  const [openOrderRoutePlanLoading, setOpenOrderRoutePlanLoading] = useState(false);
  const [openOrderRoutePlanError, setOpenOrderRoutePlanError] = useState('');
  const [routesLoading, setRoutesLoading] = useState(false);
  const [routesError, setRoutesError] = useState('');
  const [orderNotificationHistory, setOrderNotificationHistory] = useState([]);
  const [activeOrderNotifications, setActiveOrderNotifications] = useState([]);
  const [unreadOrderNotificationKeys, setUnreadOrderNotificationKeys] = useState(() => new Set());
  const [orderNotificationHistoryOpen, setOrderNotificationHistoryOpen] = useState(false);
  const webhookEventPollInFlight = useRef(false);
  const wooStatusRequestInFlight = useRef(false);
  const webhookEventCursor = useRef(null);
  const seenWebhookEventIds = useRef(new Set());
  const activeRouteRef = useRef(route);
  const openOrderFiltersRef = useRef({});
  const openOrdersRequestIdRef = useRef(0);
  const openOrdersAbortControllerRef = useRef(null);
  const itemsRequestIdRef = useRef(0);
  const itemsAbortControllerRef = useRef(null);
  const itemFacetsLoadedRef = useRef(false);
  const itemFacetsRequestIdRef = useRef(0);
  const itemFacetsRequestRef = useRef(null);
  const inventorySummaryRequestIdRef = useRef(0);
  const inventorySummaryAbortControllerRef = useRef(null);
  const wooSyncRunsQueryRef = useRef({ page: 1, page_size: 50 });
  const wooSyncRunsRequestIdRef = useRef(0);
  const wooRemapCandidatesQueryRef = useRef({ page: 1, page_size: 100 });
  const wooRemapCandidatesRequestIdRef = useRef(0);
  const wooRemapMappingsQueryRef = useRef({ page: 1, page_size: 100 });
  const wooRemapMappingsRequestIdRef = useRef(0);
  const wooWritebackQueueQueryRef = useRef({ page: 1, page_size: 50 });
  const wooWritebackQueueRequestIdRef = useRef(0);
  const wooStockSyncJobsQueryRef = useRef({ page: 1, page_size: 25 });
  const wooStockSyncJobsRequestIdRef = useRef(0);
  const wooStockSyncTrackingTimeoutRef = useRef(null);
  const wooStockSyncTrackedJobRef = useRef(null);
  const wooOrderFetchTrackingTimeoutRef = useRef(null);
  const wooOrderFetchTrackedJobRef = useRef(null);
  const wooOpenOrdersRequestIdRef = useRef(0);
  const pickMutationRef = useRef(null);
  const wooStockSyncMutationRef = useRef(null);
  activeRouteRef.current = route;

  useEffect(() => {
    const handleHashChange = () => {
      const nextRoute = parseHashRoute();
      setRoute((current) => (JSON.stringify(current) === JSON.stringify(nextRoute) ? current : nextRoute));
    };
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  useEffect(() => {
    if (route.pageId === 'dashboard') {
      loadBusinessDashboard();
    }
    if (route.pageId === 'inventory-overview') {
      loadDashboard();
    }
    if (route.pageId === 'items' && route.itemView === 'detail') {
      loadItem(route.itemId);
    }
    if (route.pageId === 'inventory') {
      loadItems(inventoryRouteToItemFilters(route));
    }
    if (route.pageId === 'receiving') {
      loadLocations({ status: 'active' });
      if ((route.receivingView || 'direct') === 'history') loadReceipts();
      if ((route.receivingView || 'direct') !== 'bulk') loadStockMovements({ movement_type: 'receive_direct' });
    }
    if (route.pageId === 'scanner') {
      loadLocations({ status: 'active' });
    }
    if (route.pageId === 'locations') {
      loadLocations();
    }
    if (route.pageId === 'reports') {
      if (route.reportKey === 'received-inventory') loadReceivedInventoryReport();
      if (route.reportKey === 'fulfillment') loadFulfillmentReport();
      if (route.reportKey === 'sku-orders') loadSkuOrdersReport();
    }
    if (route.pageId === 'cycle-count') {
      loadLocations({ status: 'active' });
      loadCycleCounts();
    }
    if (route.pageId === 'orders') {
      const ordersView = route.ordersView || 'open';
      if (ordersView === 'open') {
        loadOpenOrders({}, { ordersView: 'open', reset: true });
      } else if (ordersView === 'pick') {
        loadOpenOrders({}, { ordersView: 'pick', reset: true });
      } else if (ordersView === 'completed') {
        loadCompletedOrders();
      } else if (ordersView === 'history') {
        loadAllocations();
        loadPicks();
        loadFulfillments();
      }
    }
    if (route.pageId === 'settings' && !isDemo) {
      if (route.settingsView !== 'google-sheets') loadWooStatus();
      if ((route.settingsView || 'connection') === 'sync') {
        loadWooSyncRuns();
        loadWooRemap();
      }
      if (route.settingsView === 'writeback') {
        loadWooWritebackQueue();
        loadWooStockSyncJobs();
      }
    }
    if (route.pageId === 'routes' && (route.routesView || 'live') === 'live') {
      planOpenOrderRoutes({
        start_address: DEFAULT_ROUTE_START_ADDRESS,
        driver_count: 1,
        return_to_start: false,
      });
    }
    if (route.pageId === 'routes' && route.routesView === 'completed') {
      loadRouteCandidates();
      loadRoutes();
    }
  }, [route.pageId, route.inventoryView, route.inventoryPage, route.inventoryPageSize, route.inventorySearch, route.inventoryCategory, route.inventoryBrand, route.inventoryDataQuality, route.inventorySortBy, route.inventorySortDir, route.receivingView, route.ordersView, route.reportKey, route.settingsView, route.routesView, isDemo]);

  useEffect(() => {
    const operationalOrdersView = route.pageId === 'orders' && ['open', 'pick'].includes(route.ordersView || 'open');
    if (operationalOrdersView) return;
    openOrdersAbortControllerRef.current?.abort();
    openOrdersAbortControllerRef.current = null;
    openOrdersRequestIdRef.current += 1;
    setOpenOrdersLoading(false);
  }, [route.pageId, route.ordersView]);

  useEffect(() => {
    const itemCollectionView = route.pageId === 'inventory'
      || (route.pageId === 'items' && !route.itemView);
    if (itemCollectionView) return;
    itemsAbortControllerRef.current?.abort();
    itemsAbortControllerRef.current = null;
    itemsRequestIdRef.current += 1;
    setItemsLoading(false);
  }, [route.pageId, route.itemView]);

  useEffect(() => {
    if (route.pageId === 'inventory') return;
    inventorySummaryAbortControllerRef.current?.abort();
    inventorySummaryAbortControllerRef.current = null;
    inventorySummaryRequestIdRef.current += 1;
    setInventoryLoading(false);
  }, [route.pageId]);

  useEffect(() => {
    if (route.pageId === 'inventory') loadLocations({ status: 'active' });
  }, [route.pageId]);

  useEffect(() => {
    const itemCollectionView = route.pageId === 'inventory' || (route.pageId === 'items' && !route.itemView);
    if (itemCollectionView) loadItemFacets();
  }, [route.pageId, route.itemView]);

  useEffect(() => {
    if (isDemo || route.pageId !== 'settings' || route.settingsView !== 'writeback') return undefined;
    const intervalId = window.setInterval(
      () => loadWooStockSyncJobs(wooStockSyncJobsQueryRef.current),
      3000,
    );
    return () => window.clearInterval(intervalId);
  }, [route.pageId, route.settingsView, isDemo]);

  useEffect(() => {
    const isWritebackView = route.pageId === 'settings' && route.settingsView === 'writeback';
    if (!isWritebackView) {
      stopWooStockSyncJobTracking();
      return undefined;
    }
    return stopWooStockSyncJobTracking;
  }, [route.pageId, route.settingsView]);

  useEffect(() => {
    const isSyncView = route.pageId === 'settings' && route.settingsView === 'sync';
    if (!isSyncView) {
      stopWooOrderFetchJobTracking();
      return undefined;
    }
    return stopWooOrderFetchJobTracking;
  }, [route.pageId, route.settingsView]);

  useEffect(() => {
    const orderAwarePage = ['dashboard', 'orders', 'settings'].includes(route.pageId);
    if (!orderAwarePage) {
      return undefined;
    }
    const refreshVisibleOrderData = () => {
      if (document.visibilityState === 'hidden') {
        return;
      }
      refreshOrderAwarePage();
    };
    const intervalId = window.setInterval(refreshVisibleOrderData, ORDER_VIEW_REFRESH_INTERVAL_MS);
    window.addEventListener('focus', refreshVisibleOrderData);
    document.addEventListener('visibilitychange', refreshVisibleOrderData);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshVisibleOrderData);
      document.removeEventListener('visibilitychange', refreshVisibleOrderData);
    };
  }, [route.pageId, route.ordersView]);

  useEffect(() => {
    const loadVisibleWooHealth = () => {
      if (document.visibilityState !== 'hidden') {
        loadWooStatus(false, { silent: true });
      }
    };
    loadVisibleWooHealth();
    const intervalId = window.setInterval(loadVisibleWooHealth, WOO_SYNC_HEALTH_POLL_INTERVAL_MS);
    window.addEventListener('focus', loadVisibleWooHealth);
    document.addEventListener('visibilitychange', loadVisibleWooHealth);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', loadVisibleWooHealth);
      document.removeEventListener('visibilitychange', loadVisibleWooHealth);
    };
  }, []);

  useEffect(() => {
    if (route.pageId !== 'settings' || route.settingsView !== 'sync' || !['queued', 'running'].includes(wooStatus.order_history_import?.status)) return undefined;
    const pollHistoryImport = () => {
      if (document.visibilityState !== 'hidden') {
        Promise.all([loadWooStatus(false, { silent: true }), loadWooSyncRuns(wooSyncRunsQueryRef.current)]);
      }
    };
    const intervalId = window.setInterval(pollHistoryImport, 3000);
    return () => window.clearInterval(intervalId);
  }, [route.pageId, route.settingsView, wooStatus.order_history_import?.id, wooStatus.order_history_import?.status]);

  useEffect(() => {
    const runWebhookEventPoll = () => {
      if (document.visibilityState === 'hidden') {
        return;
      }
      pollWooWebhookEvents();
    };
    runWebhookEventPoll();
    const intervalId = window.setInterval(runWebhookEventPoll, WEBHOOK_EVENT_POLL_INTERVAL_MS);
    window.addEventListener('focus', runWebhookEventPoll);
    document.addEventListener('visibilitychange', runWebhookEventPoll);
    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener('focus', runWebhookEventPoll);
      document.removeEventListener('visibilitychange', runWebhookEventPoll);
    };
  }, []);

  const activeMeta = getHeaderMeta(route, items);

  function navigate(hash) {
    const nextHash = hash.startsWith('#') ? hash : `#${hash}`;
    if (window.location.hash !== nextHash) {
      window.location.hash = nextHash;
    }
    const nextRoute = parseHashRoute();
    activeRouteRef.current = nextRoute;
    setRoute((current) => (JSON.stringify(current) === JSON.stringify(nextRoute) ? current : nextRoute));
    setNavigationOpen(false);
  }

  function closeNavigation({ restoreFocus = true } = {}) {
    setNavigationOpen(false);
    if (restoreFocus) {
      window.setTimeout(() => navigationButtonRef.current?.focus(), 0);
    }
  }

  function toggleNavigation() {
    if (navigationOpen) {
      closeNavigation();
      return;
    }
    setNavigationOpen(true);
  }

  async function loadItem(itemId) {
    if (!itemId) return;
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/items/${itemId}`);
      if (!response.ok) throw new Error(`Item API returned ${response.status}`);
      const body = await response.json();
      const item = normalizeItem(body.item || body);
      setItems((current) => [item, ...current.filter((candidate) => candidate.id !== item.id)]);
    } catch {
      setItemsError('Unable to load the selected item from the backend.');
    }
  }

  async function loadItems(filters = DEFAULT_ITEM_PAGE_FILTERS) {
    const requestId = itemsRequestIdRef.current + 1;
    itemsRequestIdRef.current = requestId;
    itemsAbortControllerRef.current?.abort();
    const controller = new AbortController();
    itemsAbortControllerRef.current = controller;
    setItemsLoading(true);
    setItemsError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/items${filtersToQueryString(filters, { includeFacets: false })}`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Items API returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId !== itemsRequestIdRef.current) return;
      setItems((body.items || []).map(normalizeItem));
      const responsePage = body.page || 1;
      setItemsPagination((current) => ({
        page: responsePage,
        page_size: body.page_size ?? (body.items || []).length,
        total: body.total ?? (body.items || []).length,
        total_pages: body.total_pages ?? ((body.items || []).length ? 1 : 1),
        returned_count: body.returned_count ?? (body.items || []).length,
        facets: current.facets || { categories: [], brands: [] },
      }));
      const currentRoute = activeRouteRef.current;
      if (filters.page && responsePage !== filters.page && currentRoute.pageId === 'inventory' && (currentRoute.inventoryView || 'all') === 'all') {
        window.location.hash = inventoryRouteHref(currentRoute, { page: responsePage });
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && requestId === itemsRequestIdRef.current) {
        setItemsError('Unable to load items from the backend. Start the FastAPI server and try again.');
      }
    } finally {
      if (requestId === itemsRequestIdRef.current) {
        itemsAbortControllerRef.current = null;
        setItemsLoading(false);
      }
    }
  }

  async function loadItemFacets({ force = false } = {}) {
    if (!force && itemFacetsLoadedRef.current) return;
    if (!force && itemFacetsRequestRef.current) return itemFacetsRequestRef.current;
    const requestId = itemFacetsRequestIdRef.current + 1;
    itemFacetsRequestIdRef.current = requestId;
    const request = (async () => {
      try {
        const response = await apiFetch(`${API_BASE_URL}/api/items/facets`, { signal: new AbortController().signal });
        if (!response.ok) throw new Error(`Item facets API returned ${response.status}`);
        const body = await response.json();
        if (requestId !== itemFacetsRequestIdRef.current) return;
        const facets = body.facets || body;
        setItemsPagination((current) => ({
          ...current,
          facets: {
            categories: facets.categories || [],
            brands: facets.brands || [],
          },
        }));
        itemFacetsLoadedRef.current = true;
      } catch {
        if (requestId === itemFacetsRequestIdRef.current) itemFacetsLoadedRef.current = false;
      } finally {
        if (requestId === itemFacetsRequestIdRef.current) itemFacetsRequestRef.current = null;
      }
    })();
    itemFacetsRequestRef.current = request;
    return request;
  }

  async function saveItem(nextItem) {
    const normalized = normalizeItem(nextItem);
    const isNew = normalized.id == null;
    const url = isNew ? `${API_BASE_URL}/api/items` : `${API_BASE_URL}/api/items/${normalized.id}`;
    const response = await apiFetch(url, {
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
    await loadItemFacets({ force: true });
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
      const response = await apiFetch(`${API_BASE_URL}/api/locations${locationsFiltersToQueryString(filters)}`);
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
    const response = await apiFetch(url, {
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
    const requestId = inventorySummaryRequestIdRef.current + 1;
    inventorySummaryRequestIdRef.current = requestId;
    inventorySummaryAbortControllerRef.current?.abort();
    const controller = new AbortController();
    inventorySummaryAbortControllerRef.current = controller;
    setInventoryLoading(true);
    setInventoryError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/inventory/summary/by-location${inventoryFiltersToQueryString(filters)}`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Inventory API returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId === inventorySummaryRequestIdRef.current) setInventorySummary(body);
    } catch (error) {
      if (error?.name !== 'AbortError' && requestId === inventorySummaryRequestIdRef.current) setInventoryError('Unable to load inventory summary from the backend. Start the FastAPI server and try again.');
    } finally {
      if (requestId === inventorySummaryRequestIdRef.current) {
        inventorySummaryAbortControllerRef.current = null;
        setInventoryLoading(false);
      }
    }
  }

  async function loadReceipts(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 20 };
    setReceiptsLoading(true);
    setReceiptsError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/receipts${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Receipts API returned ${response.status}`);
      }
      const body = await response.json();
      setReceipts(body.receipts || []);
      setReceiptsPagination(paginationFromResponse(body, requestFilters.page_size));
    } catch (error) {
      setReceiptsError('Unable to load receipt history from the backend.');
    } finally {
      setReceiptsLoading(false);
    }
  }

  async function loadStockMovements(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 20 };
    setStockMovementsLoading(true);
    setStockMovementsError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/stock-movements${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Stock movements API returned ${response.status}`);
      }
      const body = await response.json();
      setStockMovements(body.movements || []);
      setStockMovementsPagination(paginationFromResponse(body, requestFilters.page_size));
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
        apiFetch(`${API_BASE_URL}/api/reports/received-inventory${queryString}`),
        apiFetch(`${API_BASE_URL}/api/reports/received-inventory/summary${queryString}`),
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
        apiFetch(`${API_BASE_URL}/api/reports/fulfillments${queryString}`),
        apiFetch(`${API_BASE_URL}/api/reports/fulfillments/summary${queryString}`),
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
        apiFetch(`${API_BASE_URL}/api/reports/sku-orders${queryString}`),
        apiFetch(`${API_BASE_URL}/api/reports/sku-orders/summary${queryString}`),
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
      const response = await apiFetch(`${API_BASE_URL}/api/dashboard?limit=30`);
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

  async function loadBusinessDashboard(options = {}) {
    const silent = options.silent === true;
    if (!silent) {
      setBusinessDashboardLoading(true);
    }
    setBusinessDashboardError('');
    void loadWooCommerceOpenOrders();
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/business-dashboard`);
      if (!response.ok) {
        throw new Error(`Business Dashboard API returned ${response.status}`);
      }
      const body = await response.json();
      setBusinessDashboard((current) => ({ ...emptyBusinessDashboard, ...body, woocommerce_open_orders: current.woocommerce_open_orders }));
    } catch (error) {
      setBusinessDashboardError('Unable to load business dashboard data from the backend.');
    } finally {
      if (!silent) {
        setBusinessDashboardLoading(false);
      }
    }
  }

  async function loadWooCommerceOpenOrders() {
    const requestId = wooOpenOrdersRequestIdRef.current + 1;
    wooOpenOrdersRequestIdRef.current = requestId;
    setBusinessDashboard((current) => ({
      ...current,
      woocommerce_open_orders: { ...current.woocommerce_open_orders, loading: true, error: '' },
    }));
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/business-dashboard/woocommerce-open-orders?page=1&page_size=100`);
      if (!response.ok) throw new Error(`WooCommerce open orders API returned ${response.status}`);
      const body = await response.json();
      if (requestId !== wooOpenOrdersRequestIdRef.current) return;
      const normalized = normalizeLiveWooOpenOrders(body);
      setBusinessDashboard((current) => ({
        ...current,
        woocommerce_open_orders: normalized,
      }));
      return normalized;
    } catch (error) {
      if (requestId !== wooOpenOrdersRequestIdRef.current) return;
      setBusinessDashboard((current) => ({
        ...current,
        woocommerce_open_orders: { ...emptyBusinessDashboard.woocommerce_open_orders, error: 'Live WooCommerce open orders are temporarily unavailable.' },
      }));
      return null;
    }
  }

  async function loadCycleCounts(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 50 };
    setCycleCountsLoading(true);
    setCycleCountsError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/cycle-counts${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Cycle Counts API returned ${response.status}`);
      }
      const body = await response.json();
      setCycleCounts(body.cycle_counts || []);
      setCycleCountsPagination(paginationFromResponse(body, requestFilters.page_size));
    } catch (error) {
      setCycleCountsError('Unable to load cycle count history from the backend.');
    } finally {
      setCycleCountsLoading(false);
    }
  }

  async function loadWooStatus(check = false, options = {}) {
    if (isDemo) {
      setWooStatus(emptyWooStatus);
      setWooError('');
      setWooHealthError('');
      return;
    }
    if (wooStatusRequestInFlight.current) {
      return;
    }
    wooStatusRequestInFlight.current = true;
    const silent = options.silent === true;
    if (!silent) {
      setWooLoading(true);
      setWooError('');
    }
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/status${check ? '?check=true' : ''}`);
      if (!response.ok) {
        throw new Error(`WooCommerce status returned ${response.status}`);
      }
      setWooStatus(await response.json());
      setWooHealthError('');
    } catch (error) {
      const message = 'Automatic WooCommerce order sync health cannot be checked. Verify that the Pongo backend is online.';
      setWooHealthError(message);
      if (!silent) {
        setWooError('Unable to load WooCommerce integration status from the backend.');
      }
    } finally {
      wooStatusRequestInFlight.current = false;
      if (!silent) {
        setWooLoading(false);
      }
    }
  }

  async function loadWooSyncRuns(filters = {}) {
    const requestFilters = preservePagedRequest(filters, wooSyncRunsQueryRef.current, 50);
    const requestId = wooSyncRunsRequestIdRef.current + 1;
    wooSyncRunsRequestIdRef.current = requestId;
    wooSyncRunsQueryRef.current = requestFilters;
    setWooError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/sync-runs${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`WooCommerce sync runs returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId !== wooSyncRunsRequestIdRef.current) return null;
      const pagination = paginationFromResponse(body, requestFilters.page_size);
      setWooSyncRuns(body.sync_runs || []);
      setWooSyncRunsPagination(pagination);
      wooSyncRunsQueryRef.current = { ...requestFilters, page: pagination.page, page_size: pagination.page_size };
      return body;
    } catch (error) {
      if (requestId !== wooSyncRunsRequestIdRef.current) return null;
      setWooError('Unable to load WooCommerce sync run history.');
      return null;
    }
  }

  async function loadWooRemapCandidates(filters = {}) {
    const requestFilters = preservePagedRequest(filters, wooRemapCandidatesQueryRef.current, 100);
    const requestId = wooRemapCandidatesRequestIdRef.current + 1;
    wooRemapCandidatesRequestIdRef.current = requestId;
    wooRemapCandidatesQueryRef.current = requestFilters;
    setWooError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/remap/candidates${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) throw new Error(`Remap candidates returned ${response.status}`);
      const body = await response.json();
      if (requestId !== wooRemapCandidatesRequestIdRef.current) return null;
      const pagination = paginationFromResponse(body, requestFilters.page_size);
      setWooRemapCandidates({ candidates: body.candidates || [], total: body.total || 0 });
      setWooRemapCandidatesPagination(pagination);
      wooRemapCandidatesQueryRef.current = { ...requestFilters, page: pagination.page, page_size: pagination.page_size };
      return body;
    } catch (error) {
      if (requestId !== wooRemapCandidatesRequestIdRef.current) return null;
      setWooError('Unable to load WooCommerce remap candidates.');
      return null;
    }
  }

  async function loadWooRemapMappings(filters = {}) {
    const requestFilters = preservePagedRequest(filters, wooRemapMappingsQueryRef.current, 100);
    const requestId = wooRemapMappingsRequestIdRef.current + 1;
    wooRemapMappingsRequestIdRef.current = requestId;
    wooRemapMappingsQueryRef.current = requestFilters;
    setWooError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/remap/mappings${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) throw new Error(`Remap mappings returned ${response.status}`);
      const body = await response.json();
      if (requestId !== wooRemapMappingsRequestIdRef.current) return null;
      const pagination = paginationFromResponse(body, requestFilters.page_size);
      setWooRemapMappings({ mappings: body.mappings || [], total: body.total || 0 });
      setWooRemapMappingsPagination(pagination);
      wooRemapMappingsQueryRef.current = { ...requestFilters, page: pagination.page, page_size: pagination.page_size };
      return body;
    } catch (error) {
      if (requestId !== wooRemapMappingsRequestIdRef.current) return null;
      setWooError('Unable to load WooCommerce remap mappings.');
      return null;
    }
  }

  async function loadWooRemap() {
    await Promise.all([loadWooRemapCandidates(), loadWooRemapMappings()]);
  }

  async function loadWooWritebackQueue(filters = null) {
    const requestFilters = filters === null
      ? { page: 1, page_size: 50 }
      : preservePagedRequest(filters, wooWritebackQueueQueryRef.current, 50);
    const requestId = wooWritebackQueueRequestIdRef.current + 1;
    wooWritebackQueueRequestIdRef.current = requestId;
    wooWritebackQueueQueryRef.current = requestFilters;
    setWooError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/writeback/queue${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`WooCommerce writeback queue returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId !== wooWritebackQueueRequestIdRef.current) return null;
      const pagination = paginationFromResponse(body, requestFilters.page_size);
      setWooWritebackQueue({ queue: body.queue || [], total: body.total || 0 });
      setWooWritebackQueuePagination(pagination);
      wooWritebackQueueQueryRef.current = { ...requestFilters, page: pagination.page, page_size: pagination.page_size };
      return body;
    } catch (error) {
      if (requestId !== wooWritebackQueueRequestIdRef.current) return null;
      setWooError('Unable to load WooCommerce writeback queue.');
      return null;
    }
  }

  async function loadWooStockSyncJobs(filters = {}) {
    const requestFilters = preservePagedRequest(filters, wooStockSyncJobsQueryRef.current, 25);
    const requestId = wooStockSyncJobsRequestIdRef.current + 1;
    wooStockSyncJobsRequestIdRef.current = requestId;
    wooStockSyncJobsQueryRef.current = requestFilters;
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/writeback/stock/jobs${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) throw new Error(`Stock sync jobs returned ${response.status}`);
      const body = await response.json();
      if (requestId !== wooStockSyncJobsRequestIdRef.current) return null;
      const pagination = paginationFromResponse(body, requestFilters.page_size);
      setWooStockSyncJobs(body.jobs || []);
      setWooStockSyncJobsPagination(pagination);
      wooStockSyncJobsQueryRef.current = { ...requestFilters, page: pagination.page, page_size: pagination.page_size };
      return body;
    } catch (error) {
      if (requestId !== wooStockSyncJobsRequestIdRef.current) return null;
      setWooError(error.message || 'Unable to load stock sync jobs.');
      return null;
    }
  }

  async function changeWooStockSyncJob(jobId, action) {
    setWooLoading(true);
    setWooError('');
    try {
      await postJson(`/api/integrations/woocommerce/writeback/stock/jobs/${jobId}/${action}`, {});
      await loadWooStockSyncJobs(wooStockSyncJobsQueryRef.current);
    } catch (error) {
      setWooError(error.message || `Unable to ${action} stock sync job.`);
    } finally {
      setWooLoading(false);
    }
  }

  function stopWooStockSyncJobTracking() {
    if (wooStockSyncTrackingTimeoutRef.current !== null) {
      window.clearTimeout(wooStockSyncTrackingTimeoutRef.current);
      wooStockSyncTrackingTimeoutRef.current = null;
    }
    wooStockSyncTrackedJobRef.current = null;
  }

  function startWooStockSyncJobTracking(jobId) {
    stopWooStockSyncJobTracking();
    wooStockSyncTrackedJobRef.current = jobId;
    trackWooStockSyncJob(jobId);
  }

  async function saveWooConfiguration(payload) {
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/configuration', payload);
      await loadWooStatus(false, { silent: true });
      return result;
    } catch (error) {
      setWooError(error.message || 'Unable to connect WooCommerce.');
      throw error;
    } finally {
      setWooLoading(false);
    }
  }

  async function changeWooAccessMode(accessMode) {
    if (accessMode === 'read_write' && !window.confirm('Read & write lets Pongo update WooCommerce stock and completed order statuses. Continue?')) return null;
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/access-mode', { access_mode: accessMode });
      await loadWooStatus(false, { silent: true });
      return result;
    } catch (error) {
      setWooError(error.message || 'Unable to change WooCommerce access mode.');
      return null;
    } finally {
      setWooLoading(false);
    }
  }

  async function syncWooStockFromSettings(force) {
    const confirmed = !force || window.confirm('Update all sends every mapped inventory stock level through the existing WooCommerce writeback rules. Continue?');
    if (!confirmed) return null;
    setWooLoading(true);
    setWooError('');
    setWooWritebackMessage('');
    try {
      const payload = withMutationIdempotency(wooStockSyncMutationRef, 'woo-stock-sync', {
        force,
        requested_by: force ? 'settings-update-all' : 'settings-update-changed',
        chunk_size: 50,
      });
      const result = await postJson('/api/integrations/woocommerce/writeback/stock/sync', payload);
      setWooWritebackMessage(`Stock update queued: 0 of ${result.total_items} item(s). You can leave this page safely.`);
      startWooStockSyncJobTracking(result.id);
      await loadWooStockSyncJobs(wooStockSyncJobsQueryRef.current);
      return result;
    } catch (error) {
      setWooError(error.message || 'Unable to update WooCommerce stock.');
      return null;
    } finally {
      setWooLoading(false);
    }
  }

  async function trackWooStockSyncJob(jobId) {
    if (wooStockSyncTrackedJobRef.current !== jobId) return;
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/writeback/stock/jobs/${jobId}`);
      if (!response.ok) throw new Error(`Stock sync job returned ${response.status}`);
      const job = await response.json();
      if (wooStockSyncTrackedJobRef.current !== jobId) return;
      const terminal = ['completed', 'completed_with_errors', 'failed', 'paused', 'cancelled'].includes(job.status);
      setWooWritebackMessage(
        terminal
          ? `Stock update ${job.status.replaceAll('_', ' ')}: ${job.sent_count + job.dry_run_count} sent/dry-run, ${job.failed_count} failed.`
          : `Stock update ${job.progress_percent}%: ${job.processed_items} of ${job.total_items} item(s). You can leave this page safely.`,
      );
      if (terminal) {
        stopWooStockSyncJobTracking();
        resetMutationIdempotency(wooStockSyncMutationRef);
        await loadWooStockSyncJobs(wooStockSyncJobsQueryRef.current);
        await loadWooStatus(false, { silent: true });
      } else {
        wooStockSyncTrackingTimeoutRef.current = window.setTimeout(() => trackWooStockSyncJob(jobId), 2000);
      }
    } catch (error) {
      if (wooStockSyncTrackedJobRef.current === jobId) {
        stopWooStockSyncJobTracking();
        setWooError(error.message || 'Unable to read stock update progress.');
      }
    }
  }

  function publishOrderNotifications(incomingNotifications) {
    const incoming = (incomingNotifications || []).filter((notification) => notification?.key);
    if (!incoming.length) {
      return;
    }
    setOrderNotificationHistory((current) => mergeOrderNotifications(current, incoming, { newestFirst: true, limit: ORDER_NOTIFICATION_HISTORY_LIMIT }));
    setActiveOrderNotifications((current) => mergeOrderNotifications(current, incoming));
    setUnreadOrderNotificationKeys((current) => {
      const next = new Set(current);
      incoming.forEach((notification) => next.add(notification.key));
      return next;
    });
  }

  function markOrderNotificationsRead(notificationKeys) {
    const keys = new Set(notificationKeys || []);
    if (!keys.size) {
      return;
    }
    setUnreadOrderNotificationKeys((current) => new Set([...current].filter((key) => !keys.has(key))));
  }

  function dismissActiveOrderNotifications() {
    markOrderNotificationsRead(activeOrderNotifications.map((notification) => notification.key));
    setActiveOrderNotifications([]);
  }

  function viewOpenOrdersFromNotification() {
    dismissActiveOrderNotifications();
    setOrderNotificationHistoryOpen(false);
  }

  function toggleOrderNotificationHistory() {
    const nextOpen = !orderNotificationHistoryOpen;
    setOrderNotificationHistoryOpen(nextOpen);
    if (nextOpen) {
      setUnreadOrderNotificationKeys(new Set());
    }
  }

  async function refreshLocalOrderDataAfterNotification() {
    const activeRoute = activeRouteRef.current;
    if (activeRoute.pageId === 'orders') {
      if (activeRoute.ordersView === 'completed') {
        await loadCompletedOrders({}, { silent: true });
      } else if (['open', 'pick'].includes(activeRoute.ordersView || 'open')) {
        await refreshVisibleOperationalOrders({ silent: true, preserveDetail: true });
      }
    }
    if (activeRoute.pageId === 'dashboard') {
      await loadBusinessDashboard({ silent: true });
    }
    if (activeRoute.pageId === 'settings') {
      await loadWooStatus();
    }
  }

  async function pollWooWebhookEvents() {
    if (isDemo || webhookEventPollInFlight.current) {
      return null;
    }
    webhookEventPollInFlight.current = true;
    try {
      const currentCursor = webhookEventCursor.current;
      const query = currentCursor === null
        ? `initialize=true&limit=${WEBHOOK_EVENT_POLL_LIMIT}`
        : `after_id=${currentCursor}&limit=${WEBHOOK_EVENT_POLL_LIMIT}`;
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/webhooks/events?${query}`);
      if (!response.ok) {
        throw new Error(`WooCommerce webhook events returned ${response.status}`);
      }
      const body = await response.json();
      const returnedEvents = Array.isArray(body.events) ? body.events : [];
      const returnedIds = returnedEvents.map((event) => toNumber(event.id)).filter((eventId) => eventId > 0);
      const pageHighWater = Math.max(currentCursor || 0, ...returnedIds, 0);
      const hasExplicitNextCursor = body.next_after_id !== null && body.next_after_id !== undefined;
      const nextCursor = hasExplicitNextCursor
        ? Math.max(currentCursor || 0, toNumber(body.next_after_id))
        : (body.has_more ? pageHighWater : Math.max(pageHighWater, toNumber(body.latest_event_id)));

      if (currentCursor === null) {
        returnedIds.forEach((eventId) => seenWebhookEventIds.current.add(eventId));
        webhookEventCursor.current = nextCursor;
        if (body.has_more && nextCursor > 0) {
          Promise.resolve().then(() => pollWooWebhookEvents());
        }
        return body;
      }

      const unseenEvents = returnedEvents.filter((event) => {
        const eventId = toNumber(event.id);
        return eventId > 0 && !seenWebhookEventIds.current.has(eventId);
      });
      returnedIds.forEach((eventId) => seenWebhookEventIds.current.add(eventId));
      webhookEventCursor.current = nextCursor;

      if (unseenEvents.length) {
        const newOrderEvents = unseenEvents.filter(isNewOrderWebhookEvent);
        if (newOrderEvents.length) {
          publishOrderNotifications(newOrderEvents.map(webhookEventToNotification));
        }
        await refreshLocalOrderDataAfterNotification();
      }
      if (body.has_more && nextCursor > currentCursor) {
        Promise.resolve().then(() => pollWooWebhookEvents());
      }
      return body;
    } catch {
      return null;
    } finally {
      webhookEventPollInFlight.current = false;
    }
  }

  async function refreshOrderAwarePage() {
    const activeRoute = activeRouteRef.current;
    if (activeRoute.pageId === 'orders') {
      if (activeRoute.ordersView === 'completed') {
        await loadCompletedOrders({}, { silent: true });
      } else if (['open', 'pick'].includes(activeRoute.ordersView || 'open')) {
        await refreshVisibleOperationalOrders({ silent: true, preserveDetail: true });
      }
    }
    if (activeRoute.pageId === 'dashboard') {
      await loadBusinessDashboard({ silent: true });
    }
    if (activeRoute.pageId === 'settings') {
      const refreshes = [loadWooStatus(false, { silent: true })];
      if ((activeRoute.settingsView || 'connection') === 'sync') {
        refreshes.push(loadWooSyncRuns());
      }
      await Promise.all(refreshes);
    }
  }

  async function refreshVisibleOperationalOrders({ silent = false, preserveDetail = false } = {}) {
    const activeRoute = activeRouteRef.current;
    const ordersView = activeRoute.ordersView || 'open';
    if (activeRoute.pageId !== 'orders' || !['open', 'pick'].includes(ordersView)) return;
    await loadOpenOrders(openOrderFiltersRef.current, {
      silent,
      preserveFilters: true,
      preserveDetail,
      ordersView,
    });
  }

  async function loadOpenOrders(filters = {}, options = {}) {
    const requestId = openOrdersRequestIdRef.current + 1;
    openOrdersRequestIdRef.current = requestId;
    openOrdersAbortControllerRef.current?.abort();
    const controller = new AbortController();
    openOrdersAbortControllerRef.current = controller;
    const silent = options.silent === true;
    const sourceFilters = options.preserveFilters ? openOrderFiltersRef.current : filters;
    const effectiveFilters = {
      ...sourceFilters,
      page: sourceFilters.page || 1,
      pageSize: sourceFilters.pageSize || 20,
    };
    if (!options.preserveFilters) {
      openOrderFiltersRef.current = effectiveFilters;
    }
    if (!silent) {
      setOpenOrdersLoading(true);
    }
    if (options.reset) {
      setOpenOrders(emptyOpenOrders);
      setOpenOrderDetail(null);
    }
    setOpenOrdersError('');
    try {
      const ordersView = options.ordersView || activeRouteRef.current.ordersView || 'open';
      const endpoint = ordersView === 'allocate' ? '/api/orders/allocate' : (ordersView === 'pick' ? '/api/orders/pick' : '/api/orders/open');
      const response = await apiFetch(`${API_BASE_URL}${endpoint}${plainFiltersToQueryString(openOrderFiltersToApi(effectiveFilters))}`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Open Orders API returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId !== openOrdersRequestIdRef.current) return;
      setOpenOrders({ ...emptyOpenOrders, ...body });
      if (!options.preserveDetail) {
        setOpenOrderDetail(null);
      }
    } catch (error) {
      if (error?.name !== 'AbortError' && requestId === openOrdersRequestIdRef.current) {
        setOpenOrdersError('Unable to load open orders from the backend.');
      }
    } finally {
      if (requestId === openOrdersRequestIdRef.current) {
        openOrdersAbortControllerRef.current = null;
        setOpenOrdersLoading(false);
      }
    }
  }

  async function loadCompletedOrders(filters = {}, options = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, pageSize: filters.pageSize || filters.page_size || 20 };
    const silent = options.silent === true;
    if (!silent) {
      setCompletedOrdersLoading(true);
    }
    setCompletedOrdersError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/orders/completed${plainFiltersToQueryString(completedOrderFiltersToApi(requestFilters))}`);
      if (!response.ok) {
        throw new Error(`Completed Orders API returned ${response.status}`);
      }
      const body = await response.json();
      setCompletedOrders({ ...emptyCompletedOrders, ...body, ...paginationFromResponse(body, requestFilters.pageSize) });
    } catch (error) {
      setCompletedOrdersError('Unable to load completed orders from the backend.');
    } finally {
      if (!silent) {
        setCompletedOrdersLoading(false);
      }
    }
  }

  async function loadOpenOrderDetail(orderId) {
    if (!orderId) {
      setOpenOrderDetail(null);
      return null;
    }
    try {
      const body = await fetchOrderDetailRequest(orderId);
      setOpenOrderDetail(body);
      return body;
    } catch (error) {
      setOpenOrdersError('Unable to load order detail from the backend.');
      return null;
    }
  }

  async function loadAllocations(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 20 };
    setAllocationError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/allocations${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Allocations API returned ${response.status}`);
      }
      const body = await response.json();
      setAllocationHistory(body.allocations || []);
      setAllocationHistoryPagination(paginationFromResponse(body, requestFilters.page_size));
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
      const response = await apiFetch(`${API_BASE_URL}/api/allocations/${allocationId}`);
      if (!response.ok) {
        throw new Error(`Allocation detail API returned ${response.status}`);
      }
      setAllocationDetail(await response.json());
    } catch (error) {
      setAllocationError('Unable to load allocation detail from the backend.');
    }
  }

  async function loadPicks(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 20 };
    setPickError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/picks${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Picks API returned ${response.status}`);
      }
      const body = await response.json();
      setPickHistory(body.picks || []);
      setPickHistoryPagination(paginationFromResponse(body, requestFilters.page_size));
    } catch (error) {
      setPickError('Unable to load pick history from the backend.');
    }
  }

  async function loadFulfillments(filters = {}) {
    const requestFilters = { ...filters, page: filters.page || 1, page_size: filters.page_size || filters.pageSize || 20 };
    setFulfillmentError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/fulfillments${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Fulfillments API returned ${response.status}`);
      }
      const body = await response.json();
      setFulfillmentHistory(body.fulfillments || []);
      setFulfillmentHistoryPagination(paginationFromResponse(body, requestFilters.page_size));
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
      const response = await apiFetch(`${API_BASE_URL}/api/fulfillments/${fulfillmentId}`);
      if (!response.ok) {
        throw new Error(`Fulfillment detail API returned ${response.status}`);
      }
      setFulfillmentDetail(await response.json());
    } catch (error) {
      setFulfillmentError('Unable to load fulfillment detail from the backend.');
    }
  }

  async function loadRouteCandidates(filters = {}) {
    const requestFilters = {
      ...routeCandidateFiltersToApi(filters),
      page: filters.page || 1,
      page_size: filters.page_size || filters.pageSize || 50,
    };
    setRouteCandidatesLoading(true);
    setRouteCandidatesError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/routes/candidates${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Route candidates API returned ${response.status}`);
      }
      const body = await response.json();
      setRouteCandidates({ total_candidates: body.total_candidates || 0, candidates: body.candidates || [] });
      setRouteCandidatesPagination(paginationFromResponse(body, requestFilters.page_size));
    } catch (error) {
      setRouteCandidatesError('Unable to load route candidates from the backend.');
    } finally {
      setRouteCandidatesLoading(false);
    }
  }

  async function planOpenOrderRoutes(payload) {
    setOpenOrderRoutePlanLoading(true);
    setOpenOrderRoutePlanError('');
    try {
      setOpenOrderRoutePlan(await postJson('/api/routes/open-orders/plan', payload));
    } catch (error) {
      setOpenOrderRoutePlanError(error.message || 'Unable to plan routes for open orders.');
    } finally {
      setOpenOrderRoutePlanLoading(false);
    }
  }

  async function loadRoutes(filters = {}) {
    const requestFilters = {
      ...routeFiltersToApi(filters),
      page: filters.page || 1,
      page_size: filters.page_size || filters.pageSize || 50,
    };
    setRoutesLoading(true);
    setRoutesError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/routes${plainFiltersToQueryString(requestFilters)}`);
      if (!response.ok) {
        throw new Error(`Routes API returned ${response.status}`);
      }
      const body = await response.json();
      setRoutesHistory({ routes: body.routes || [], total: body.total || 0 });
      setRoutesHistoryPagination(paginationFromResponse(body, requestFilters.page_size));
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
      const response = await apiFetch(`${API_BASE_URL}/api/routes/${routeId}`);
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
      const response = await apiFetch(`${API_BASE_URL}/api/routes/${routeId}/map`);
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
      const response = await apiFetch(`${API_BASE_URL}/api/picks/${pickId}`);
      if (!response.ok) {
        throw new Error(`Pick detail API returned ${response.status}`);
      }
      setPickDetail(await response.json());
    } catch (error) {
      setPickError('Unable to load pick detail from the backend.');
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
      const result = await postJson('/api/picks/preview', { order_ids: [orderId], pick_strategy: 'allocated_first', allow_partial: true, created_by: 'system' });
      setPickPreview(result);
      return result;
    } catch (error) {
      setPickError(error.message || 'Unable to preview picking.');
      return null;
    } finally {
      setPickLoading(false);
    }
  }

  async function commitPick(orderId, lines = []) {
    if (!orderId) {
      setPickError('Select an allocated order before committing a pick.');
      return;
    }
    const confirmed = window.confirm('Picking reduces local Pongo OS In Stock and Allocated quantities for the allocated locations. It does not update WooCommerce, create labels, routes, or notifications.');
    if (!confirmed) {
      return;
    }
    setPickLoading(true);
    setPickError('');
    try {
      const payload = {
        order_ids: lines.length ? [] : [orderId],
        lines,
        pick_strategy: 'allocated_first',
        allow_partial: true,
        created_by: 'system',
        notes: 'Manual quantities from Pick Orders',
      };
      const result = await postJson('/api/picks/commit', withMutationIdempotency(pickMutationRef, 'pick', payload));
      setPickCommitSummary(result);
      if (result.status !== 'posted') {
        setPickError((result.errors || []).join(' ') || 'The pick could not be posted. Review the quantities and try again.');
        return result;
      }
      await refreshVisibleOperationalOrders();
      await loadOpenOrderDetail(orderId);
      await loadPicks();
      await loadInventorySummary();
      resetMutationIdempotency(pickMutationRef);
      return result;
    } catch (error) {
      setPickError(error.message || 'Unable to commit pick.');
      return null;
    } finally {
      setPickLoading(false);
    }
  }

  async function completeOrder(orderId, pickStatus) {
    if (!orderId) {
      setOpenOrdersError('Select an order before completing it.');
      return;
    }
    const fullyPicked = pickStatus === 'picked';
    const confirmed = window.confirm(
      fullyPicked
        ? 'Complete this order in Pongo OS and WooCommerce now? Stock was already reduced during picking.'
        : 'Warning: this order has not been fully picked. Completing it will close the order in Pongo OS and WooCommerce, release remaining allocations, and will not reduce unpicked stock. Continue?',
    );
    if (!confirmed) {
      return;
    }
    setOpenOrdersLoading(true);
    setOpenOrdersError('');
    setOrderCompletionSummary(null);
    try {
      const result = await postJson(`/api/orders/${orderId}/complete/commit`, {
        completion_mode: 'complete',
        reason: fullyPicked ? undefined : 'Completed from Open Orders before picking was finished.',
        queue_woo_status_update: true,
      });
      setOrderCompletionSummary(result);
      if (result.woo_sync_status !== 'sent') {
        setOpenOrdersError(result.woo_sync_error || `Order completed locally, but WooCommerce synchronization is ${result.woo_sync_status || 'pending'}. Review the WooCommerce writeback queue.`);
      }
      await refreshVisibleOperationalOrders();
      await loadCompletedOrders({}, { silent: true });
      await loadInventorySummary();
    } catch (error) {
      setOpenOrdersError(error.message || 'Unable to complete order.');
    } finally {
      setOpenOrdersLoading(false);
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
    const confirmed = window.confirm('Fulfillment is legacy completion compatibility. Stock should already be reduced during picking, and fulfillment will not reduce it again.');
    if (!confirmed) {
      return;
    }
    setFulfillmentLoading(true);
    setFulfillmentError('');
    try {
      const result = await postJson('/api/fulfillments/commit', { order_ids: [orderId], fulfillment_strategy: 'picked_first', allow_partial: true, created_by: 'system', notes: 'Fulfilled from Open Orders' });
      setFulfillmentCommitSummary(result);
      await refreshVisibleOperationalOrders();
      await loadOpenOrderDetail(orderId);
      await loadFulfillments();
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
      await refreshVisibleOperationalOrders();
      await loadOpenOrderDetail(orderId);
      await loadAllocations();
      await loadInventorySummary();
    } catch (error) {
      setAllocationError(error.message || 'Unable to commit allocation.');
    } finally {
      setAllocationLoading(false);
    }
  }

  async function runWooCatalogBatches(endpoint, blockedSkus = []) {
    return runWooCatalogBatchesRequest(endpoint, blockedSkus);
  }

  async function previewWooProductSync() {
    setWooLoading(true);
    setWooError('');
    setWooCommitSummary(null);
    try {
      setWooPreview(await runWooCatalogBatches('/api/integrations/woocommerce/products/preview'));
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
      setWooOrderPreview(await postJson('/api/integrations/woocommerce/orders/preview', { include_statuses: wooOrderSyncStatuses, limit: 500, created_by: 'system' }));
    } catch (error) {
      setWooError(error.message || 'Unable to preview WooCommerce order sync.');
    } finally {
      setWooLoading(false);
    }
  }

  async function commitWooOrderSync() {
    const confirmed = window.confirm('Fetch WooCommerce order changes now? The dedicated worker imports them in safe batches and attempts local auto-allocation.');
    if (!confirmed) {
      return;
    }
    setWooLoading(true);
    setWooError('');
    try {
      const job = await postJson('/api/integrations/woocommerce/orders/fetch-now', {});
      setWooOrderCommitSummary(job);
      await loadWooSyncRuns(wooSyncRunsQueryRef.current);
      startWooOrderFetchJobTracking(job.id);
    } catch (error) {
      setWooError(error.message || 'Unable to queue the WooCommerce order fetch.');
    } finally {
      setWooLoading(false);
    }
  }

  async function startWooOrderHistoryImport() {
    const confirmed = window.confirm('Import the complete WooCommerce order history for reporting? This uses GET requests only. Historical orders will not allocate stock, enter picking, create stock movements, enter routes, or write to WooCommerce.');
    if (!confirmed) return;
    setWooLoading(true);
    setWooError('');
    try {
      const job = await postJson('/api/integrations/woocommerce/orders/history-import', {});
      setWooStatus((current) => ({ ...current, order_history_import: job }));
      await loadWooSyncRuns(wooSyncRunsQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to queue the WooCommerce historical order import.');
    } finally {
      setWooLoading(false);
    }
  }

  function stopWooOrderFetchJobTracking() {
    if (wooOrderFetchTrackingTimeoutRef.current !== null) {
      window.clearTimeout(wooOrderFetchTrackingTimeoutRef.current);
      wooOrderFetchTrackingTimeoutRef.current = null;
    }
    wooOrderFetchTrackedJobRef.current = null;
  }

  function startWooOrderFetchJobTracking(jobId) {
    stopWooOrderFetchJobTracking();
    wooOrderFetchTrackedJobRef.current = jobId;
    trackWooOrderFetchJob(jobId);
  }

  async function trackWooOrderFetchJob(jobId) {
    if (wooOrderFetchTrackedJobRef.current !== jobId) return;
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/sync-runs/${jobId}`);
      if (!response.ok) throw new Error(`Order fetch job returned ${response.status}`);
      const job = await response.json();
      if (wooOrderFetchTrackedJobRef.current !== jobId) return;
      setWooOrderCommitSummary(job);
      const terminal = ['completed', 'completed_with_errors', 'failed'].includes(job.status);
      if (terminal) {
        stopWooOrderFetchJobTracking();
        await Promise.all([loadWooStatus(false, { silent: true }), loadWooSyncRuns(wooSyncRunsQueryRef.current), refreshVisibleOperationalOrders({ silent: true, preserveDetail: true }), loadBusinessDashboard()]);
      } else {
        wooOrderFetchTrackingTimeoutRef.current = window.setTimeout(() => trackWooOrderFetchJob(jobId), 2000);
      }
    } catch (error) {
      if (wooOrderFetchTrackedJobRef.current === jobId) {
        stopWooOrderFetchJobTracking();
        setWooError(error.message || 'Unable to read WooCommerce order fetch progress.');
      }
    }
  }

  async function commitWooProductSync() {
    const confirmed = window.confirm('This maps existing Pongo items by unique SKU or barcode and creates missing Woo products locally. Existing Pongo fields, stock, locations, costs, and history are preserved. Nothing is written to WooCommerce.');
    if (!confirmed) {
      return;
    }
    setWooLoading(true);
    setWooError('');
    try {
      const result = await runWooCatalogBatches('/api/integrations/woocommerce/products/commit', wooPreview?.duplicate_skus || []);
      setWooCommitSummary(result);
      await loadWooSyncRuns(wooSyncRunsQueryRef.current);
      await loadItemFacets({ force: true });
    } catch (error) {
      setWooError(error.message || 'Unable to commit WooCommerce product sync.');
    } finally {
      setWooLoading(false);
    }
  }

  async function previewWooStockWriteback(payload) {
    setWooLoading(true);
    setWooError('');
    setWooWritebackMessage('');
    try {
      setWooWritebackPreview(await postJson('/api/integrations/woocommerce/writeback/stock/preview', payload));
    } catch (error) {
      setWooError(error.message || 'Unable to preview stock writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function previewWooOrderStatusWriteback(payload) {
    setWooLoading(true);
    setWooError('');
    setWooWritebackMessage('');
    try {
      setWooWritebackPreview(await postJson('/api/integrations/woocommerce/writeback/order-status/preview', payload));
    } catch (error) {
      setWooError(error.message || 'Unable to preview order status writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function queueWooWriteback(previewPayload, refreshFilters = null) {
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/writeback/queue', previewPayload);
      setWooWritebackMessage(`Queued ${result.operation_type} as item ${result.id}.`);
      setWooWritebackPreview(null);
      await loadWooWritebackQueue(refreshFilters || wooWritebackQueueQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to queue writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function approveWooWriteback(queueId, refreshFilters = null) {
    setWooLoading(true);
    setWooError('');
    try {
      await postJson(`/api/integrations/woocommerce/writeback/queue/${queueId}/approve`, {});
      await loadWooWritebackQueue(refreshFilters || wooWritebackQueueQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to approve writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function sendWooWriteback(queueId, refreshFilters = null) {
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson(`/api/integrations/woocommerce/writeback/queue/${queueId}/send`, {});
      setWooWritebackMessage(result.status === 'sent' ? 'Send to Staging completed and response was logged.' : `Writeback ${result.status}.`);
      await loadWooWritebackQueue(refreshFilters || wooWritebackQueueQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to send writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function cancelWooWriteback(queueId, refreshFilters = null) {
    setWooLoading(true);
    setWooError('');
    try {
      await postJson(`/api/integrations/woocommerce/writeback/queue/${queueId}/cancel`, {});
      await loadWooWritebackQueue(refreshFilters || wooWritebackQueueQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to cancel writeback.');
    } finally {
      setWooLoading(false);
    }
  }

  async function revalidateWooWriteback(queueId, refreshFilters = null) {
    setWooLoading(true);
    setWooError('');
    try {
      const result = await postJson(`/api/integrations/woocommerce/writeback/queue/${queueId}/revalidate`, {});
      setWooWritebackMessage(`Writeback ${result.id} was regenerated from the current mapping and must be approved again.`);
      await loadWooWritebackQueue(refreshFilters || wooWritebackQueueQueryRef.current);
    } catch (error) {
      setWooError(error.message || 'Unable to revalidate writeback mapping.');
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
    } catch (error) {
      setWooError(error.message || 'Unable to commit remap.');
    } finally {
      setWooLoading(false);
    }
  }

  return (
    <>
      <a className="skip-link" href="#main-content">Skip to workspace</a>
      <div className={`app-shell ${navigationOpen ? 'navigation-open' : ''}`} data-page={route.pageId} data-demo={isDemo ? 'true' : undefined}>
      <Sidebar activePage={route.pageId} route={route} onNavigate={navigate} isOpen={navigationOpen} onClose={closeNavigation} />
      <div className="workspace">
        <TopHeader
          meta={activeMeta}
          currentUser={currentUser}
          onLogout={onLogout}
          notifications={orderNotificationHistory}
          unreadCount={notificationOrderCount(orderNotificationHistory.filter((notification) => unreadOrderNotificationKeys.has(notification.key)))}
          historyOpen={orderNotificationHistoryOpen}
          navigationOpen={navigationOpen}
          navigationButtonRef={navigationButtonRef}
          onMenuToggle={toggleNavigation}
          onNavigate={navigate}
          onToggleHistory={toggleOrderNotificationHistory}
          onCloseHistory={() => setOrderNotificationHistoryOpen(false)}
          onViewOpenOrders={() => setOrderNotificationHistoryOpen(false)}
        />
        {isDemo && (
          <div className="demo-mode-banner" role="status">
            <span className="demo-mode-message">
              <CheckCircle2 size={18} aria-hidden="true" />
              <span><strong>Demo workspace</strong> Mock data only · Read-only · Production inventory is never shown or changed</span>
            </span>
          </div>
        )}
        <NewOrderNotificationRegion
          notifications={activeOrderNotifications}
          onDismiss={dismissActiveOrderNotifications}
          onViewOpenOrders={viewOpenOrdersFromNotification}
        />
        <WooOrderSyncHealthWarning status={wooStatus} error={wooHealthError} />
        <main className="main-content" id="main-content" tabIndex={-1}>
          <PageHeader meta={activeMeta} route={route} />
          <PageBody
            route={route}
            items={items}
            itemsPagination={itemsPagination}
            itemsLoading={itemsLoading}
            itemsError={itemsError}
            onLoadItems={loadItems}
            onRefreshItemFacets={() => loadItemFacets({ force: true })}
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
            receiptsPagination={receiptsPagination}
            receiptsLoading={receiptsLoading}
            receiptsError={receiptsError}
            onLoadReceipts={loadReceipts}
            stockMovements={stockMovements}
            stockMovementsPagination={stockMovementsPagination}
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
            businessDashboard={businessDashboard}
            businessDashboardLoading={businessDashboardLoading}
            businessDashboardError={businessDashboardError}
            onLoadBusinessDashboard={loadBusinessDashboard}
            onLoadWooCommerceOpenOrders={loadWooCommerceOpenOrders}
            cycleCounts={cycleCounts}
            cycleCountsPagination={cycleCountsPagination}
            cycleCountsLoading={cycleCountsLoading}
            cycleCountsError={cycleCountsError}
            onLoadCycleCounts={loadCycleCounts}
            wooStatus={wooStatus}
            wooPreview={wooPreview}
            wooCommitSummary={wooCommitSummary}
            wooOrderPreview={wooOrderPreview}
            wooOrderCommitSummary={wooOrderCommitSummary}
            wooSyncRuns={wooSyncRuns}
            wooSyncRunsPagination={wooSyncRunsPagination}
            onLoadWooSyncRuns={loadWooSyncRuns}
            wooRemapCandidates={wooRemapCandidates}
            wooRemapCandidatesPagination={wooRemapCandidatesPagination}
            onLoadWooRemapCandidates={loadWooRemapCandidates}
            wooRemapMappings={wooRemapMappings}
            wooRemapMappingsPagination={wooRemapMappingsPagination}
            onLoadWooRemapMappings={loadWooRemapMappings}
            wooRemapPreview={wooRemapPreview}
            wooRemapMessage={wooRemapMessage}
            wooWritebackQueue={wooWritebackQueue}
            wooWritebackQueuePagination={wooWritebackQueuePagination}
            onLoadWooWritebackQueue={loadWooWritebackQueue}
            wooStockSyncJobs={wooStockSyncJobs}
            wooStockSyncJobsPagination={wooStockSyncJobsPagination}
            onLoadWooStockSyncJobs={loadWooStockSyncJobs}
            wooWritebackPreview={wooWritebackPreview}
            wooWritebackMessage={wooWritebackMessage}
            wooLoading={wooLoading}
            wooError={wooError}
            onLoadWooStatus={loadWooStatus}
            onSaveWooConfiguration={saveWooConfiguration}
            onChangeWooAccessMode={changeWooAccessMode}
            onPreviewWooProductSync={previewWooProductSync}
            onCommitWooProductSync={commitWooProductSync}
            onPreviewWooOrderSync={previewWooOrderSync}
            onCommitWooOrderSync={commitWooOrderSync}
            onStartWooOrderHistoryImport={startWooOrderHistoryImport}
            onPreviewWooRemap={previewWooRemap}
            onCommitWooRemap={commitWooRemap}
            onLoadWooRemap={loadWooRemap}
            onPreviewWooStockWriteback={previewWooStockWriteback}
            onPreviewWooOrderStatusWriteback={previewWooOrderStatusWriteback}
            onQueueWooWriteback={queueWooWriteback}
            onApproveWooWriteback={approveWooWriteback}
            onSendWooWriteback={sendWooWriteback}
            onCancelWooWriteback={cancelWooWriteback}
            onRevalidateWooWriteback={revalidateWooWriteback}
            onSyncWooStock={syncWooStockFromSettings}
            onResumeWooStockJob={(jobId) => changeWooStockSyncJob(jobId, 'resume')}
            onCancelWooStockJob={(jobId) => changeWooStockSyncJob(jobId, 'cancel')}
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
            orderCompletionSummary={orderCompletionSummary}
            onCompleteOrder={completeOrder}
            allocationPreview={allocationPreview}
            allocationCommitSummary={allocationCommitSummary}
            allocationHistory={allocationHistory}
            allocationHistoryPagination={allocationHistoryPagination}
            onLoadAllocations={loadAllocations}
            allocationDetail={allocationDetail}
            allocationLoading={allocationLoading}
            allocationError={allocationError}
            onPreviewAllocation={previewAllocation}
            onCommitAllocation={commitAllocation}
            onLoadAllocationDetail={loadAllocationDetail}
            pickPreview={pickPreview}
            pickCommitSummary={pickCommitSummary}
            pickHistory={pickHistory}
            pickHistoryPagination={pickHistoryPagination}
            onLoadPicks={loadPicks}
            pickDetail={pickDetail}
            pickLoading={pickLoading}
            pickError={pickError}
            onPreviewPick={previewPick}
            onCommitPick={commitPick}
            onLoadPickDetail={loadPickDetail}
            fulfillmentPreview={fulfillmentPreview}
            fulfillmentCommitSummary={fulfillmentCommitSummary}
            fulfillmentHistory={fulfillmentHistory}
            fulfillmentHistoryPagination={fulfillmentHistoryPagination}
            onLoadFulfillments={loadFulfillments}
            fulfillmentDetail={fulfillmentDetail}
            fulfillmentLoading={fulfillmentLoading}
            fulfillmentError={fulfillmentError}
            onPreviewFulfillment={previewFulfillment}
            onCommitFulfillment={commitFulfillment}
            onLoadFulfillmentDetail={loadFulfillmentDetail}
            routeCandidates={routeCandidates}
            routeCandidatesPagination={routeCandidatesPagination}
            routeCandidatesLoading={routeCandidatesLoading}
            routeCandidatesError={routeCandidatesError}
            routePreview={routePreview}
            routeCommitSummary={routeCommitSummary}
            routesHistory={routesHistory}
            routesHistoryPagination={routesHistoryPagination}
            routeDetail={routeDetail}
            routeMapPayload={routeMapPayload}
            routeProviderMessage={routeProviderMessage}
            openOrderRoutePlan={openOrderRoutePlan}
            openOrderRoutePlanLoading={openOrderRoutePlanLoading}
            openOrderRoutePlanError={openOrderRoutePlanError}
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
            onPlanOpenOrderRoutes={planOpenOrderRoutes}
          />
        </main>
      </div>
      </div>
    </>
  );
}

function Sidebar({ activePage, route, onNavigate, isOpen, onClose }) {
  const [ordersExpanded, setOrdersExpanded] = useState(activePage === 'orders');
  const [inventoryExpanded, setInventoryExpanded] = useState(activePage === 'inventory');
  const closeButtonRef = useRef(null);
  const navListRef = useRef(null);
  const activeGroup = navigationGroups.find((group) => group.pages.includes(activePage)) || navigationGroups[0];

  useEffect(() => {
    if (activePage === 'orders') {
      setOrdersExpanded(true);
    }
    if (activePage === 'inventory') {
      setInventoryExpanded(true);
    }
  }, [activePage]);

  useEffect(() => {
    if (isOpen) {
      closeButtonRef.current?.focus();
    }
  }, [isOpen]);

  useEffect(() => {
    const container = navListRef.current;
    const activeLink = container?.querySelector('[aria-current="page"]');
    if (!container || !activeLink) return;
    const containerRect = container.getBoundingClientRect();
    const linkRect = activeLink.getBoundingClientRect();
    if (linkRect.top < containerRect.top || linkRect.bottom > containerRect.bottom) {
      activeLink.scrollIntoView?.({ block: 'nearest' });
    }
  }, [activePage, route.inventoryView, route.ordersView, inventoryExpanded, ordersExpanded]);

  function renderNavItem(item) {
    const Icon = item.icon;
    const isActive = item.id === activePage;
    const subpages = item.id === 'inventory' ? inventorySubpages : item.id === 'orders' ? orderSubpages : null;
    const expanded = item.id === 'inventory' ? inventoryExpanded : ordersExpanded;
    const toggleExpanded = item.id === 'inventory' ? setInventoryExpanded : setOrdersExpanded;

    if (subpages) {
      return (
        <div className="nav-group" key={item.id}>
          <button className={`nav-link nav-parent ${isActive ? 'active' : ''}`} aria-expanded={expanded} onClick={() => toggleExpanded((current) => !current)} type="button">
            <Icon size={19} strokeWidth={1.8} />
            <span>{item.label}</span>
            <ChevronDown className="nav-caret" size={15} aria-hidden="true" />
          </button>
          {expanded && (
            <div className="subnav-list" aria-label={`${item.label} sub-navigation`}>
              {subpages.map((subpage) => {
                const activeView = item.id === 'inventory' ? route.inventoryView || 'all' : route.ordersView || 'open';
                const childActive = isActive && activeView === subpage.id;
                return (
                  <a className={`subnav-link ${childActive ? 'active' : ''}`} href={subpage.href} key={subpage.id} aria-current={childActive ? 'page' : undefined} onClick={(event) => { event.preventDefault(); onNavigate(subpage.href); }}>
                    {subpage.label}
                  </a>
                );
              })}
            </div>
          )}
        </div>
      );
    }

    const href = navItemHref(item);
    return (
      <a className={`nav-link ${isActive ? 'active' : ''}`} href={href} key={item.id} aria-current={isActive ? 'page' : undefined} onClick={(event) => { event.preventDefault(); onNavigate(href); }}>
        <Icon size={19} strokeWidth={1.8} />
        <span>{item.label}</span>
      </a>
    );
  }

  return (
    <>
      <button className={`navigation-scrim ${isOpen ? 'is-visible' : ''}`} aria-label="Close navigation" onClick={onClose} type="button" />
      <aside className={`sidebar ${isOpen ? 'is-open' : ''}`} id="application-navigation" aria-label="Application navigation" onKeyDown={(event) => { if (event.key === 'Escape' && isOpen) { event.stopPropagation(); onClose(); } }}>
        <nav className="module-rail" aria-label="Module navigation">
          <a className="module-brand" href="#dashboard" aria-label="Pongo OS dashboard" onClick={(event) => { event.preventDefault(); onNavigate('#dashboard'); }}>
            <img src="/pongo-logo.png" alt="" aria-hidden="true" />
          </a>
          <div className="module-links">
            {navigationGroups.map((group) => {
              const Icon = group.icon;
              return (
                <a className={`module-link ${activeGroup.id === group.id ? 'active' : ''}`} href={group.href} key={group.id} onClick={(event) => { event.preventDefault(); onNavigate(group.href); }}>
                  <Icon size={22} strokeWidth={1.8} aria-hidden="true" />
                  <span>{group.label}</span>
                </a>
              );
            })}
          </div>
        </nav>

        <div className="context-rail">
          <div className="context-rail-header">
            <div>
              <span>Pongo OS</span>
              <strong>{activeGroup.label}</strong>
            </div>
            <button className="icon-button navigation-close" aria-label="Close navigation" onClick={onClose} ref={closeButtonRef} type="button">
              <X size={18} aria-hidden="true" />
            </button>
          </div>
          <nav className="nav-list" aria-label="Main navigation" ref={navListRef}>
            {navigationGroups.map((group) => (
              <section className="context-nav-group" key={group.id} aria-labelledby={`nav-${group.id}`}>
                <h2 id={`nav-${group.id}`}>{group.label}</h2>
                {group.pages.map((pageId) => renderNavItem(navItems.find((item) => item.id === pageId)))}
              </section>
            ))}
          </nav>
        </div>
      </aside>
    </>
  );
}

function mergeOrderNotifications(current, incoming, options = {}) {
  const existingKeys = new Set((current || []).map((notification) => notification.key));
  const additions = [];
  (incoming || []).forEach((notification) => {
    if (!notification?.key || existingKeys.has(notification.key)) {
      return;
    }
    existingKeys.add(notification.key);
    additions.push(notification);
  });
  const orderedAdditions = options.newestFirst ? [...additions].reverse() : additions;
  const merged = options.newestFirst ? [...orderedAdditions, ...(current || [])] : [...(current || []), ...orderedAdditions];
  return merged.slice(0, options.limit || ORDER_NOTIFICATION_HISTORY_LIMIT);
}

function webhookEventToNotification(event) {
  return {
    key: `webhook:${event.id}`,
    source: 'webhook',
    eventId: toNumber(event.id),
    orderCount: 1,
    wooOrderId: event.woo_order_id,
    localOrderId: event.local_order_id,
    wooOrderNumber: event.woo_order_number,
    wooStatus: event.woo_status,
    localStatus: event.local_status,
    customerName: event.customer_name,
    currency: event.currency,
    total: event.total,
    receivedAt: event.received_at,
  };
}

function isNewOrderWebhookEvent(event) {
  return event?.event_type ? event.event_type === 'order_created' : event?.topic === 'order.created';
}

function notificationOrderCount(notifications) {
  return (notifications || []).reduce((total, notification) => total + Math.max(1, toNumber(notification.orderCount)), 0);
}

function orderNotificationTitle(notification) {
  if (notification?.source === 'webhook' && notification.wooOrderNumber) {
    return `WooCommerce order #${notification.wooOrderNumber}`;
  }
  const count = Math.max(1, toNumber(notification?.orderCount));
  return `${count} WooCommerce ${count === 1 ? 'order' : 'orders'} imported`;
}

function orderNotificationDetail(notification) {
  const details = [];
  if (notification?.customerName) {
    details.push(notification.customerName);
  }
  if (notification?.total != null) {
    details.push(formatOrderNotificationCurrency(notification.total, notification.currency));
  }
  return details.join(' · ');
}

function formatOrderNotificationCurrency(value, currency) {
  return formatCurrency(value, currency || APP_CURRENCY);
}

function TopHeader({ meta, currentUser, onLogout, notifications = [], unreadCount = 0, historyOpen, navigationOpen, navigationButtonRef, onMenuToggle, onNavigate, onToggleHistory, onCloseHistory, onViewOpenOrders }) {
  return (
    <header className="top-header">
      <div className="header-primary">
        <button className="icon-button navigation-toggle" aria-controls="application-navigation" aria-expanded={navigationOpen} aria-label={navigationOpen ? 'Close navigation' : 'Open navigation'} onClick={onMenuToggle} ref={navigationButtonRef} type="button">
          <Menu size={21} aria-hidden="true" />
        </button>
        <label className="command-jump">
          <Search size={18} aria-hidden="true" />
          <span className="sr-only">Jump to workspace</span>
          <select aria-label="Jump to workspace" value="" onChange={(event) => event.target.value && onNavigate(event.target.value)}>
            <option value="">Jump to a workspace…</option>
            {navItems.map((item) => <option key={item.id} value={navItemHref(item)}>{item.label}</option>)}
          </select>
        </label>
        <div className="header-page-context" aria-label="Current workspace">
          <span>{meta.kicker}</span>
          <strong>{meta.title}</strong>
        </div>
      </div>
      <div className="header-actions">
        <div className="warehouse-context" aria-label="Current warehouse: Main Warehouse">
          <Warehouse size={17} aria-hidden="true" />
          <span><small>Current warehouse</small>Main Warehouse</span>
        </div>
        <div className="notification-center" onKeyDown={(event) => {
          if (event.key === 'Escape' && historyOpen) {
            event.stopPropagation();
            onCloseHistory();
          }
        }}>
          <button
            className="icon-button header-icon notification-bell"
            aria-controls="order-notification-history"
            aria-expanded={historyOpen}
            aria-label={unreadCount ? `Order notifications, ${unreadCount} unread` : 'Order notifications, no unread orders'}
            onClick={onToggleHistory}
            type="button"
          >
            <Bell size={21} aria-hidden="true" />
            {unreadCount > 0 && <span className="notification-badge" aria-hidden="true">{unreadCount > 99 ? '99+' : unreadCount}</span>}
          </button>
          {historyOpen && (
            <section className="notification-popover" id="order-notification-history" aria-label="Order notification history">
              <div className="notification-popover-header">
                <div>
                  <span>Staff alerts</span>
                  <h2>New orders</h2>
                </div>
                <button className="icon-button notification-popover-close" onClick={onCloseHistory} aria-label="Close order notification history" type="button">
                  <X size={18} aria-hidden="true" />
                </button>
              </div>
              <div className="notification-history-list">
                {notifications.map((notification) => (
                  <article className="notification-history-item" key={notification.key}>
                    <span className="notification-history-icon" aria-hidden="true"><Bell size={16} /></span>
                    <div>
                      <strong>{orderNotificationTitle(notification)}</strong>
                      {orderNotificationDetail(notification) && <p>{orderNotificationDetail(notification)}</p>}
                      <time dateTime={notification.receivedAt || undefined}>{formatDateTime(notification.receivedAt)}</time>
                    </div>
                  </article>
                ))}
                {!notifications.length && (
                  <div className="notification-history-empty">
                    <Bell size={22} aria-hidden="true" />
                    <p>No new order notifications this session.</p>
                  </div>
                )}
              </div>
              <a className="notification-history-action" href="#/orders/open" onClick={onViewOpenOrders}>View Open Orders</a>
            </section>
          )}
        </div>
        <details className="account-menu" onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.currentTarget.removeAttribute('open');
            event.currentTarget.querySelector('summary')?.focus();
          }
        }}>
          <summary className="user-chip" aria-label={`Account: ${currentUser?.display_name || 'Pongo Staff'}`}>
            <div className="avatar"><UserCircle size={26} aria-hidden="true" /></div>
            <span>{currentUser?.display_name || 'Pongo Staff'}</span>
            <ChevronDown className="account-chevron" size={15} aria-hidden="true" />
          </summary>
          <div className="account-popover">
            <div className="account-identity">
              <strong>{currentUser?.display_name || 'Pongo Staff'}</strong>
              {currentUser?.email && <small>{currentUser.email}</small>}
              {currentUser?.access_level === 'demo' && <small className="account-access-level">Demo · mock data · read-only</small>}
            </div>
            {onLogout && <button onClick={onLogout} type="button"><LogOut size={16} aria-hidden="true" /> Sign out</button>}
          </div>
        </details>
        {currentUser?.access_level === 'demo' && (
          <div className="demo-powered-by" aria-label="Powered by Mythodus">
            <span className="demo-powered-copy"><span>Powered By:</span><strong>Mythodus</strong></span>
            <img src="/mythodus-logo.jpeg" alt="Mythodus logo" />
          </div>
        )}
      </div>
    </header>
  );
}

function NewOrderNotificationRegion({ notifications = [], onDismiss, onViewOpenOrders }) {
  const orderCount = notificationOrderCount(notifications);
  const singleNotification = notifications.length === 1 ? notifications[0] : null;
  const title = singleNotification?.source === 'webhook' && singleNotification.wooOrderNumber
    ? `New WooCommerce order #${singleNotification.wooOrderNumber} imported`
    : `${orderCount} new WooCommerce ${orderCount === 1 ? 'order' : 'orders'} imported`;
  const detail = singleNotification ? orderNotificationDetail(singleNotification) : 'The new orders are ready for staff review.';

  return (
    <div className="new-order-notification-region" role="status" aria-live="polite" aria-atomic="true">
      {!!notifications.length && (
        <section className="new-order-toast" aria-label="New order notification">
          <span className="new-order-toast-icon" aria-hidden="true"><Bell size={22} /></span>
          <div className="new-order-toast-copy">
            <span>Incoming order</span>
            <strong>{title}</strong>
            {detail && <p>{detail}</p>}
          </div>
          <button className="icon-button new-order-toast-dismiss" onClick={onDismiss} aria-label="Dismiss new order notification" type="button">
            <X size={18} aria-hidden="true" />
          </button>
          <a className="primary-button new-order-toast-action" href="#/orders/open" onClick={onViewOpenOrders}>View Open Orders</a>
        </section>
      )}
    </div>
  );
}

function WooOrderSyncHealthWarning({ status, error }) {
  const health = status?.order_reconciliation;
  if (status?.environment === 'development') {
    return null;
  }
  if (!error && (!status?.configured || !health || health.healthy)) {
    return null;
  }
  const title = error
    ? 'Automatic order sync health is unavailable'
    : (health.degraded ? 'Automatic order sync needs review' : 'Automatic order sync is not healthy');
  const detail = error || health.last_error || health.message || 'Open WooCommerce Settings to review the server reconciliation status.';
  return (
    <section className="woo-sync-health-warning" role="alert" aria-label="WooCommerce order sync warning">
      <span className="woo-sync-health-icon" aria-hidden="true"><TriangleAlert size={21} /></span>
      <div>
        <strong>{title}</strong>
        <p>{detail}</p>
        {health?.last_success_at && <small>Last successful check {formatDateTime(health.last_success_at)}</small>}
      </div>
      <a href="#/settings/sync">Review WooCommerce Settings</a>
    </section>
  );
}

function PageHeader({ meta, route }) {
  const hasNavigationTabs = meta.tabs.some((tab) => typeof tab !== 'string' && tab.href);
  const tabContent = meta.tabs.map((tab, index) => {
    const tabObject = typeof tab === 'string' ? { label: tab } : tab;
    const isActive = isTabActive(tabObject, index, route);
    const className = isActive ? 'tab active' : 'tab';
    return tabObject.href ? (
      <a className={className} href={tabObject.href} key={tabObject.label} aria-current={isActive ? 'page' : undefined}>
        {tabObject.label}
      </a>
    ) : (
      <span className={`${className} is-static`} key={tabObject.label}>
        {tabObject.label}
      </span>
    );
  });

  return (
    <section className="page-heading">
      <div className="page-heading-copy">
        <nav className="page-breadcrumbs" aria-label="Breadcrumb">
          <span>Pongo OS</span>
          <ChevronRight size={13} aria-hidden="true" />
          <span>{meta.kicker}</span>
        </nav>
        <h1>{meta.title}</h1>
      </div>
      {hasNavigationTabs ? (
        <nav className="page-tabs" aria-label={`${meta.title} sections`}>{tabContent}</nav>
      ) : (
        <div className="page-tabs" aria-label={`${meta.title} workflow stages`}>{tabContent}</div>
      )}
    </section>
  );
}

function PageBody({
  route,
  items,
  itemsPagination,
  itemsLoading,
  itemsError,
  onLoadItems,
  onRefreshItemFacets,
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
  receiptsPagination,
  receiptsLoading,
  receiptsError,
  onLoadReceipts,
  stockMovements,
  stockMovementsPagination,
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
  businessDashboard,
  businessDashboardLoading,
  businessDashboardError,
  onLoadBusinessDashboard,
  onLoadWooCommerceOpenOrders,
  cycleCounts,
  cycleCountsPagination,
  cycleCountsLoading,
  cycleCountsError,
  onLoadCycleCounts,
  wooStatus,
  wooPreview,
  wooCommitSummary,
  wooOrderPreview,
  wooOrderCommitSummary,
  wooSyncRuns,
  wooSyncRunsPagination,
  onLoadWooSyncRuns,
  wooRemapCandidates,
  wooRemapCandidatesPagination,
  onLoadWooRemapCandidates,
  wooRemapMappings,
  wooRemapMappingsPagination,
  onLoadWooRemapMappings,
  wooRemapPreview,
  wooRemapMessage,
  wooWritebackQueue,
  wooWritebackQueuePagination,
  onLoadWooWritebackQueue,
  wooStockSyncJobs,
  wooStockSyncJobsPagination,
  onLoadWooStockSyncJobs,
  wooWritebackPreview,
  wooWritebackMessage,
  wooLoading,
  wooError,
  onLoadWooStatus,
  onSaveWooConfiguration,
  onChangeWooAccessMode,
  onPreviewWooProductSync,
  onCommitWooProductSync,
  onPreviewWooOrderSync,
  onCommitWooOrderSync,
  onStartWooOrderHistoryImport,
  onPreviewWooRemap,
  onCommitWooRemap,
  onLoadWooRemap,
  onPreviewWooStockWriteback,
  onPreviewWooOrderStatusWriteback,
  onQueueWooWriteback,
  onApproveWooWriteback,
  onSendWooWriteback,
  onCancelWooWriteback,
  onRevalidateWooWriteback,
  onSyncWooStock,
  onResumeWooStockJob,
  onCancelWooStockJob,
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
  orderCompletionSummary,
  onCompleteOrder,
  allocationPreview,
  allocationCommitSummary,
  allocationHistory,
  allocationHistoryPagination,
  onLoadAllocations,
  allocationDetail,
  allocationLoading,
  allocationError,
  onPreviewAllocation,
  onCommitAllocation,
  onLoadAllocationDetail,
  pickPreview,
  pickCommitSummary,
  pickHistory,
  pickHistoryPagination,
  onLoadPicks,
  pickDetail,
  pickLoading,
  pickError,
  onPreviewPick,
  onCommitPick,
  onLoadPickDetail,
  fulfillmentPreview,
  fulfillmentCommitSummary,
  fulfillmentHistory,
  fulfillmentHistoryPagination,
  onLoadFulfillments,
  fulfillmentDetail,
  fulfillmentLoading,
  fulfillmentError,
  onPreviewFulfillment,
  onCommitFulfillment,
  onLoadFulfillmentDetail,
  routeCandidates,
  routeCandidatesPagination,
  routeCandidatesLoading,
  routeCandidatesError,
  routePreview,
  routeCommitSummary,
  routesHistory,
  routesHistoryPagination,
  routeDetail,
  routeMapPayload,
  routeProviderMessage,
  openOrderRoutePlan,
  openOrderRoutePlanLoading,
  openOrderRoutePlanError,
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
  onPlanOpenOrderRoutes,
}) {
  if (route.pageId === 'items') {
    return <ItemsPage route={route} items={items} pagination={itemsPagination} itemsLoading={itemsLoading} itemsError={itemsError} onLoadItems={onLoadItems} onRefreshItemFacets={onRefreshItemFacets} onSaveItem={onSaveItem} onCloneItem={onCloneItem} />;
  }

  if (route.pageId === 'insights') {
    return <InsightsPage route={route} />;
  }

  if (route.pageId === 'locations') {
    return <LocationsPage route={route} locations={locations} loading={locationsLoading} error={locationsError} onLoadLocations={onLoadLocations} onSaveLocation={onSaveLocation} />;
  }

  if (route.pageId === 'inventory') {
    return (
      <InventoryPage
        route={route}
        items={items}
        pagination={itemsPagination}
        itemsLoading={itemsLoading}
        summary={inventorySummary}
        loading={inventoryLoading}
        error={inventoryError || itemsError}
        onLoadItems={onLoadItems}
        onRefreshItemFacets={onRefreshItemFacets}
        onLoadSummary={onLoadInventorySummary}
        stockMovements={stockMovements}
        stockMovementsPagination={stockMovementsPagination}
        stockMovementsLoading={stockMovementsLoading}
        stockMovementsError={stockMovementsError}
        onLoadStockMovements={onLoadStockMovements}
      />
    );
  }

  if (route.pageId === 'receiving') {
    return (
      <DirectReceivingPage
        route={route}
        items={items}
        locations={locations}
        receipts={receipts}
        receiptsPagination={receiptsPagination}
        receiptsLoading={receiptsLoading}
        receiptsError={receiptsError}
        onLoadReceipts={onLoadReceipts}
        stockMovements={stockMovements}
        stockMovementsPagination={stockMovementsPagination}
        stockMovementsLoading={stockMovementsLoading}
        stockMovementsError={stockMovementsError}
        onLoadStockMovements={onLoadStockMovements}
        onLoadInventorySummary={onLoadInventorySummary}
      />
    );
  }

  if (route.pageId === 'scanner') {
    return <ScannerWorkflowsPage locations={locations} onLoadInventorySummary={onLoadInventorySummary} />;
  }

  if (route.pageId === 'reports') {
    return (
      <ReportsPage
        route={route}
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
        cycleCountsPagination={cycleCountsPagination}
        cycleCountsLoading={cycleCountsLoading}
        cycleCountsError={cycleCountsError}
        onLoadCycleCounts={onLoadCycleCounts}
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
        orderCompletionSummary={orderCompletionSummary}
        onCompleteOrder={onCompleteOrder}
        allocationPreview={allocationPreview}
        allocationCommitSummary={allocationCommitSummary}
        allocationHistory={allocationHistory}
        allocationHistoryPagination={allocationHistoryPagination}
        onLoadAllocations={onLoadAllocations}
        allocationDetail={allocationDetail}
        allocationLoading={allocationLoading}
        allocationError={allocationError}
        onPreviewAllocation={onPreviewAllocation}
        onCommitAllocation={onCommitAllocation}
        onLoadAllocationDetail={onLoadAllocationDetail}
        pickPreview={pickPreview}
        pickCommitSummary={pickCommitSummary}
        pickHistory={pickHistory}
        pickHistoryPagination={pickHistoryPagination}
        onLoadPicks={onLoadPicks}
        pickDetail={pickDetail}
        pickLoading={pickLoading}
        pickError={pickError}
        onPreviewPick={onPreviewPick}
        onCommitPick={onCommitPick}
        onLoadPickDetail={onLoadPickDetail}
        fulfillmentPreview={fulfillmentPreview}
        fulfillmentCommitSummary={fulfillmentCommitSummary}
        fulfillmentHistory={fulfillmentHistory}
        fulfillmentHistoryPagination={fulfillmentHistoryPagination}
        onLoadFulfillments={onLoadFulfillments}
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
    if (route.settingsView === 'google-sheets') return <GoogleSheetsSettingsPage oauthResult={route.googleOAuthResult} />;
    return (
      <WooCommerceSettingsPage
        view={route.settingsView || 'connection'}
        status={wooStatus}
        preview={wooPreview}
        commitSummary={wooCommitSummary}
        orderPreview={wooOrderPreview}
        orderCommitSummary={wooOrderCommitSummary}
        syncRuns={wooSyncRuns}
        syncRunsPagination={wooSyncRunsPagination}
        onLoadSyncRuns={onLoadWooSyncRuns}
        remapCandidates={wooRemapCandidates}
        remapCandidatesPagination={wooRemapCandidatesPagination}
        onLoadRemapCandidates={onLoadWooRemapCandidates}
        remapMappings={wooRemapMappings}
        remapMappingsPagination={wooRemapMappingsPagination}
        onLoadRemapMappings={onLoadWooRemapMappings}
        remapPreview={wooRemapPreview}
        remapMessage={wooRemapMessage}
        writebackQueue={wooWritebackQueue}
        writebackQueuePagination={wooWritebackQueuePagination}
        onLoadWritebackQueue={onLoadWooWritebackQueue}
        stockSyncJobs={wooStockSyncJobs}
        stockSyncJobsPagination={wooStockSyncJobsPagination}
        onLoadStockSyncJobs={onLoadWooStockSyncJobs}
        writebackPreview={wooWritebackPreview}
        writebackMessage={wooWritebackMessage}
        loading={wooLoading}
        error={wooError}
        onCheckConnection={() => onLoadWooStatus(true)}
        onSaveConfiguration={onSaveWooConfiguration}
        onChangeAccessMode={onChangeWooAccessMode}
        onPreview={onPreviewWooProductSync}
        onCommit={onCommitWooProductSync}
        onPreviewOrders={onPreviewWooOrderSync}
        onCommitOrders={onCommitWooOrderSync}
        onStartOrderHistoryImport={onStartWooOrderHistoryImport}
        onPreviewRemap={onPreviewWooRemap}
        onCommitRemap={onCommitWooRemap}
        onLoadRemap={onLoadWooRemap}
        onPreviewStockWriteback={onPreviewWooStockWriteback}
        onPreviewOrderStatusWriteback={onPreviewWooOrderStatusWriteback}
        onQueueWriteback={onQueueWooWriteback}
        onApproveWriteback={onApproveWooWriteback}
        onSendWriteback={onSendWooWriteback}
        onCancelWriteback={onCancelWooWriteback}
        onRevalidateWriteback={onRevalidateWooWriteback}
        onSyncStock={onSyncWooStock}
        onResumeStockJob={onResumeWooStockJob}
        onCancelStockJob={onCancelWooStockJob}
      />
    );
  }

  if (route.pageId === 'routes') {
    return (
      <RoutesPage
        view={route.routesView || 'live'}
        candidatesData={routeCandidates}
        candidatesPagination={routeCandidatesPagination}
        candidatesLoading={routeCandidatesLoading}
        candidatesError={routeCandidatesError}
        preview={routePreview}
        commitSummary={routeCommitSummary}
        routesData={routesHistory}
        routesPagination={routesHistoryPagination}
        detail={routeDetail}
        mapPayload={routeMapPayload}
        providerMessage={routeProviderMessage}
        openOrderPlan={openOrderRoutePlan}
        openOrderPlanLoading={openOrderRoutePlanLoading}
        openOrderPlanError={openOrderRoutePlanError}
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
        onPlanOpenOrders={onPlanOpenOrderRoutes}
      />
    );
  }

  if (route.pageId === 'dashboard') {
    return <BusinessDashboardPage dashboard={businessDashboard} loading={businessDashboardLoading} error={businessDashboardError} onRefresh={onLoadBusinessDashboard} onRefreshLiveOrders={onLoadWooCommerceOpenOrders} />;
  }

  if (route.pageId === 'inventory-overview') {
    return <CommandCenterPage dashboard={dashboard} loading={dashboardLoading} error={dashboardError} onRefresh={onLoadDashboard} />;
  }

  return <StandardPage icon={pageIcon(route.pageId)} title={pageMeta[route.pageId].title} description="Main Warehouse workspace." columns={['Area', 'Status', 'Type', 'Notes']} />;
}

function BusinessDashboardPage({ dashboard, loading, error, onRefresh, onRefreshLiveOrders }) {
  const today = dashboard.today?.summary || {};
  const wooOpenOrders = dashboard.woocommerce_open_orders || emptyBusinessDashboard.woocommerce_open_orders;
  const subscriptions = dashboard.subscriptions || {};
  const revenue = dashboard.revenue_comparison || {};
  const orderMap = dashboard.order_map || {};
  const warnings = dashboard.data_quality || [];
  const [selectedLiveOrder, setSelectedLiveOrder] = useState(null);
  const [liveOrderReady, setLiveOrderReady] = useState(false);
  const [liveOrderLoading, setLiveOrderLoading] = useState(false);
  const [liveOrderMutation, setLiveOrderMutation] = useState({ pending: '', error: '', message: '', retryTarget: '' });
  const liveOrderReconcileRef = useRef(null);
  const liveOrderMutationRef = useRef(null);

  async function loadLiveOrderDetail(row) {
    const summary = normalizeLiveWooOpenOrder(row);
    setSelectedLiveOrder((current) => current?.woo_order_id === summary.woo_order_id ? current : summary);
    setLiveOrderReady(false);
    setLiveOrderLoading(true);
    setLiveOrderMutation((current) => ({ ...current, error: '' }));
    try {
      const result = await reconcileLiveWooOrder(summary.woo_order_id, liveOrderReconcileRef);
      const detail = result.order || (result.local_order_id ? await fetchOrderDetailRequest(result.local_order_id) : null);
      if (!detail) throw new Error('Pongo did not return reconciled order details.');
      resetMutationIdempotency(liveOrderReconcileRef);
      setSelectedLiveOrder(detail);
      setLiveOrderReady(true);
    } catch (detailError) {
      setLiveOrderMutation((current) => ({
        ...current,
        error: `${detailError.message || 'Order details are unavailable.'} Status changes stay disabled until the order is loaded safely.`,
      }));
    } finally {
      setLiveOrderLoading(false);
    }
  }

  async function openLiveOrder(row) {
    const summary = normalizeLiveWooOpenOrder(row);
    setSelectedLiveOrder(summary);
    setLiveOrderMutation({ pending: '', error: '', message: '', retryTarget: '' });
    await loadLiveOrderDetail(summary);
  }

  async function changeLiveOrderStatus(targetStatus) {
    if (!selectedLiveOrder?.woo_order_id || liveOrderMutation.pending || !liveOrderReady) return;
    const orderNumber = selectedLiveOrder.woo_order_number || selectedLiveOrder.woo_order_id;
    const fullyPicked = selectedLiveOrder.pick_status === 'picked'
      || (Number(selectedLiveOrder.total_quantity_ordered || 0) > 0
        && Number(selectedLiveOrder.total_quantity_picked || 0) >= Number(selectedLiveOrder.total_quantity_ordered || 0));
    const confirmation = targetStatus === 'completed'
      ? fullyPicked
        ? `Mark order ${orderNumber} processed? Stock was already reduced during picking. This will mark the order completed in Pongo OS and WooCommerce.`
        : `Mark order ${orderNumber} processed without picking? This will complete the order without reducing stock. You can later use Send to Pick Orders from Completed Orders.`
      : `Cancel order ${orderNumber} in Pongo OS and WooCommerce?`;
    if (!window.confirm(confirmation)) return;
    setLiveOrderMutation({ pending: targetStatus, error: '', message: '', retryTarget: '' });
    try {
      const result = await updateLiveWooOrderStatus(selectedLiveOrder.woo_order_id, targetStatus, {
        reason: targetStatus === 'completed'
          ? 'Marked processed from the live WooCommerce Dashboard.'
          : 'Cancelled from the live WooCommerce Dashboard.',
        completion_mode: targetStatus === 'completed'
          ? (fullyPicked ? 'complete_picked' : 'complete_without_picking')
          : undefined,
        queue_woo_status_update: true,
      }, liveOrderMutationRef);
      const writebackSent = normalizeWooStatus(result.woo_sync_status) === 'sent';
      if (writebackSent) {
        resetMutationIdempotency(liveOrderMutationRef);
        setLiveOrderMutation({
          pending: '',
          error: result.woo_sync_error || '',
          message: result.message || `Order ${orderNumber} was ${targetStatus === 'completed' ? 'marked processed' : 'cancelled'}.`,
          retryTarget: '',
        });
      } else {
        setLiveOrderMutation({
          pending: '',
          error: result.woo_sync_error || result.message || `WooCommerce writeback is ${result.woo_sync_status || 'not confirmed'}.`,
          message: '',
          retryTarget: targetStatus,
        });
      }
      await onRefreshLiveOrders();
    } catch (mutationError) {
      setLiveOrderMutation({ pending: '', error: mutationError.message || 'Unable to update this order.', message: '', retryTarget: targetStatus });
    }
  }

  return (
    <section className="content-panel business-dashboard-page">
      <div className="business-dashboard-hero">
        <div>
          <h2>Dashboard</h2>
          <p>Live business snapshot for orders, customers, revenue, subscriptions, and delivery geography.</p>
          <span>Last refreshed {dashboard.generated_at ? formatDateTime(dashboard.generated_at) : 'not yet'}</span>
        </div>
        <button className="primary-button" onClick={onRefresh} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
      </div>
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading Dashboard...</div>}

      <div className="business-kpi-grid">
        <BusinessMetric
          label="Open Orders"
          value={wooOpenOrders.loading || wooOpenOrders.error ? '—' : wooOpenOrders.summary?.open_orders_count ?? '—'}
          caption={wooOpenOrders.loading ? 'Loading live orders…' : wooOpenOrders.error || (wooOpenOrders.source !== 'woocommerce' && wooOpenOrders.source !== 'demo') ? 'Live orders unavailable' : wooOpenOrders.source === 'demo' ? 'Demo data' : 'Live WooCommerce · Processing only'}
          live
          tone="green"
        />
        <BusinessMetric label="Today's Orders" value={today.today_orders_count || 0} tone="blue" />
        <BusinessMetric label="Today's Revenue" value={formatCurrency(today.today_revenue || 0)} tone="peach" />
        <BusinessMetric label="New Customers" value={today.today_new_customers || 0} tone="orange" />
        <BusinessMetric label="Returning Customers" value={today.today_returning_customers || 0} tone="green" />
        <BusinessMetric label="Subscription Orders" value={today.today_subscription_orders || 0} tone="blue" />
        <BusinessMetric label="AOV" value={formatCurrency(today.average_order_value_today || 0)} tone="peach" />
      </div>

      <div className="business-two-column">
        <BusinessOpenOrdersCard feed={wooOpenOrders} onOpen={openLiveOrder} onRetry={onRefreshLiveOrders} />
        <BusinessSubscriptionsCard subscriptions={subscriptions} />
      </div>

      <BusinessOrderMapCard orderMap={orderMap} />
      <BusinessRevenueCard revenue={revenue} />

      {!!warnings.length && (
        <div className="business-card">
          <div className="panel-title"><div><h2>Data Quality Warnings</h2><p>Local data limitations for this business dashboard.</p></div></div>
          <div className="business-warning-list">
            {warnings.map((warning) => <div className={`business-warning ${warning.severity || 'info'}`} key={warning.code}><strong>{titleize(warning.code)}</strong><span>{warning.message}</span></div>)}
          </div>
        </div>
      )}
      {selectedLiveOrder && (
        <OpenOrderDetailPanel
          order={selectedLiveOrder}
          onClose={() => { setSelectedLiveOrder(null); setLiveOrderReady(false); setLiveOrderMutation({ pending: '', error: '', message: '', retryTarget: '' }); }}
          showPrint={false}
          statusActions={{
            loading: liveOrderLoading,
            ready: liveOrderReady,
            pending: liveOrderMutation.pending,
            error: liveOrderMutation.error,
            message: liveOrderMutation.message,
            retryTarget: liveOrderMutation.retryTarget,
            onRetryDetails: () => loadLiveOrderDetail(selectedLiveOrder),
            onRetry: () => changeLiveOrderStatus(liveOrderMutation.retryTarget),
            onMarkProcessed: () => changeLiveOrderStatus('completed'),
            onCancel: () => changeLiveOrderStatus('cancelled'),
          }}
          title="Live WooCommerce Order"
        />
      )}
    </section>
  );
}

function BusinessMetric({ label, value, tone, caption, live = false }) {
  return (
    <article className={`business-metric-card ${tone}`} aria-atomic={live || undefined} aria-live={live ? 'polite' : undefined}>
      <span>{label}</span>
      <strong>{value}</strong>
      {caption && <small>{caption}</small>}
    </article>
  );
}

function BusinessOpenOrdersCard({ feed, onOpen, onRetry }) {
  const rows = feed.orders || [];
  const total = feed.summary?.open_orders_count ?? feed.total ?? 0;
  const liveUnavailable = Boolean(feed.error);
  const caption = Number(total) > rows.length ? `Showing ${rows.length} of ${total} open orders` : `${total} open order(s)`;
  return (
    <div className="business-card">
      <div className="panel-title">
        <div>
          <h2>Open Orders</h2>
          <p>Live WooCommerce processing orders only.</p>
          {feed.fetched_at && !liveUnavailable && <small>Live WooCommerce · refreshed {formatDateTime(feed.fetched_at)}</small>}
        </div>
      </div>
      {liveUnavailable && (
        <div className="business-live-orders-error" role="alert">
          <span>{feed.error}</span>
          <button className="muted-button" disabled={feed.loading} onClick={onRetry} type="button"><RefreshCw size={16} />Retry</button>
        </div>
      )}
      {feed.loading && <div className="loading-strip" role="status">Loading live WooCommerce orders…</div>}
      {!liveUnavailable && <TableShell caption={caption} className="business-open-orders-table" columns={['Order', 'Customer', 'Email', 'Status', 'Date', 'Total']} showActionBand={false}>
        {rows.map((order) => (
          <tr className="clickable-order-row" key={`${order.woo_order_id}`} onClick={() => onOpen(order)}>
            <td className="mono"><button aria-label={`Open live WooCommerce order ${order.woo_order_number || order.woo_order_id}`} className="table-row-link" onClick={(event) => { event.stopPropagation(); onOpen(order); }} type="button">{order.woo_order_number || order.woo_order_id}</button></td>
            <td>{order.customer_name || 'Unknown customer'}</td>
            <td>{order.customer_email || ''}</td>
            <td>{StatusText(order.woo_status)}</td>
            <td>{formatDateTime(order.date_created)}</td>
            <td>{formatCurrency(order.total)}</td>
          </tr>
        ))}
        {!rows.length && !feed.loading && <tr><td colSpan={6}><div className="empty-table-row">No processing orders are currently open in WooCommerce.</div></td></tr>}
      </TableShell>}
    </div>
  );
}

function BusinessSubscriptionsCard({ subscriptions }) {
  const rows = subscriptions.rows || [];
  const lastSyncedAt = subscriptions.summary?.last_synced_at;
  return (
    <div className="business-card">
      <div className="panel-title">
        <div><h2>Upcoming Subscriptions</h2><p>Upcoming WooCommerce renewals with current Pongo stock.</p></div>
        {lastSyncedAt && <span className="status-pill">Synced {formatDateTime(lastSyncedAt)}</span>}
      </div>
      <div className="subscription-list">
        {rows.slice(0, 8).map((row, index) => (
          <article className="subscription-card" key={`${row.subscription_id || row.order_number || 'subscription'}-${row.line_item_id || index}`}>
            <strong>{row.product_name || row.sku || 'Subscription item'}</strong>
            <span>{row.sku || 'SKU unavailable'} · {row.customer_name || row.customer_email || 'Customer'}</span>
            <small>{row.quantity_due ?? 1} due {row.next_payment_date || 'date unavailable'}</small>
            <small>
              {row.current_in_stock == null
                ? 'Stock unavailable'
                : `In stock ${row.current_in_stock} · Sellable ${row.current_sellable ?? 'unknown'}`}
            </small>
            <em className={row.stockout_risk === 'At risk' ? 'is-risk' : ''}>{row.stockout_risk || StatusText(row.status)}</em>
          </article>
        ))}
        {!rows.length && <div className="soft-empty-state">{subscriptions.empty_state || 'Subscription data is not synced yet.'}</div>}
      </div>
    </div>
  );
}

function BusinessOrderMapCard({ orderMap }) {
  const cityRows = orderMap.city_breakdown || [];
  const markers = orderMap.markers || [];
  const total = orderMap.summary?.total_orders_today || 0;
  return (
    <div className="business-card business-map-card">
      <div className="panel-title">
        <div><h2>Today's Orders Map</h2><p>Orders grouped from local WooCommerce snapshots.</p></div>
        <span className="status-pill">Local Snapshot</span>
      </div>
      <div className="business-map-layout">
        <div className="map-visual" aria-label="Approximate city order map">
          {markers.map((marker, index) => {
            const position = markerPosition(marker);
            return <span className={marker.approximate ? 'map-marker approximate' : 'map-marker'} style={{ left: `${position.left}%`, top: `${position.top}%` }} key={`${marker.marker_label}-${index}`}>{index + 1}</span>;
          })}
          {!markers.length && <div className="map-empty">Map uses city-level approximate markers until address geocoding is configured.</div>}
        </div>
        <div className="city-card-list">
          <article><strong>{total}</strong><span>Today's orders</span></article>
          {cityRows.slice(0, 6).map((row) => <article key={row.city}><strong>{row.city || 'Unknown'}</strong><span>{row.order_count} order(s)</span></article>)}
          {!cityRows.length && <article><strong>No city data</strong><span>Shipping city fields are empty.</span></article>}
        </div>
      </div>
      {(orderMap.data_quality || []).map((warning) => <div className="csv-note" key={warning.code}>{warning.message}</div>)}
    </div>
  );
}

function BusinessRevenueCard({ revenue }) {
  const summary = revenue.summary || {};
  const series = revenue.daily_series || [];
  const maxValue = Math.max(...series.flatMap((row) => [toNumber(row.current_revenue), toNumber(row.previous_revenue)]), 1);
  return (
    <div className="business-card revenue-card">
      <div className="panel-title">
        <div>
          <h2>Revenue per day, {summary.current_period_label || 'current period'} vs {summary.previous_period_label || 'previous period'}</h2>
          <p>WooCommerce revenue per day from local order snapshots.</p>
        </div>
        <span className={toNumber(summary.delta_percent) < 0 ? 'delta-pill negative' : 'delta-pill'}>{formatNumber(summary.delta_percent || 0)}%</span>
      </div>
      <div className="revenue-summary-row">
        <Metric label={summary.current_period_label || 'Current'} value={formatCurrency(summary.current_period_revenue || 0)} />
        <Metric label={summary.previous_period_label || 'Previous'} value={formatCurrency(summary.previous_period_revenue || 0)} />
      </div>
      <div className="revenue-comparison-bars">
        {series.map((row) => (
          <div className="revenue-day" key={row.day_index}>
            <span>{row.day_index}</span>
            <div><i className="current" style={{ height: `${Math.max(5, (toNumber(row.current_revenue) / maxValue) * 100)}%` }} /><i className="previous" style={{ height: `${Math.max(5, (toNumber(row.previous_revenue) / maxValue) * 100)}%` }} /></div>
          </div>
        ))}
        {!series.length && <div className="empty-table-row">No revenue series available yet.</div>}
      </div>
      <div className="chart-legend"><span><i className="legend-current" />Current period</span><span><i className="legend-previous" />Previous month</span></div>
    </div>
  );
}

const insightSummaryOrder = {
  overview: ['gross_sales', 'discount_amount', 'refund_amount', 'net_sales', 'total_orders', 'units_sold', 'average_order_value'],
  'orders-revenue': ['gross_sales', 'discount_amount', 'refund_amount', 'net_sales', 'total_orders', 'units_sold', 'average_order_value'],
};

const insightMetricDefinitions = {
  gross_sales: 'WooCommerce Analytics gross sales for unfiltered ranges; local order lines when Pongo filters are applied.',
  discount_amount: 'WooCommerce Analytics coupon value for unfiltered ranges; local order discounts when Pongo filters are applied.',
  refund_amount: 'Refund value reported by WooCommerce Analytics for the selected unfiltered range.',
  net_sales: 'WooCommerce Analytics net revenue for unfiltered ranges; filtered local product-line sales otherwise.',
  total_orders: 'WooCommerce Analytics order count for unfiltered ranges; matching local orders otherwise.',
  units_sold: 'WooCommerce Analytics item count for unfiltered ranges; matching local item quantities otherwise.',
  average_order_value: 'WooCommerce Analytics average order value for unfiltered ranges; local net sales per order otherwise.',
};

const insightWarningPresentation = {
  limited_order_history: { impact: 'Trend and forecasting confidence is limited until more order snapshots are available.', href: '#settings', label: 'Review sync status' },
  missing_unit_cost: { impact: 'Margin and inventory-value metrics exclude items without cost.', href: '#/inventory/all?data_quality=missing_cost', label: 'Review missing costs' },
  missing_refund_data: { impact: 'Refund amount and refund rate remain unavailable; net figures are not adjusted using fabricated refund values.' },
  woo_analytics_unavailable: { impact: 'Pongo is temporarily showing locally synced order snapshots. Check the WooCommerce connection and refresh.' },
  missing_subscription_data: { impact: 'Subscription dashboards remain unavailable until local subscription snapshots exist.' },
  insufficient_sales_history: { impact: 'Demand, velocity, days-left, and reorder recommendations remain unavailable for affected SKUs until matching sales history exists.' },
  missing_barcode: { impact: 'Scanner-based workflows may require SKU entry for these items.', href: '#/inventory/all?data_quality=missing_barcode', label: 'Review missing barcodes' },
  unmapped_products: { impact: 'Unmapped items cannot be reconciled to WooCommerce reporting.', href: '#/inventory/all?data_quality=unmapped', label: 'Review unmapped items' },
};

function pickFilterValues(filters, allowed) {
  return Object.fromEntries((allowed || []).filter((key) => filters[key] !== undefined && filters[key] !== '').map((key) => [key, filters[key]]));
}

function localDateInput(value) {
  const offset = value.getTimezoneOffset() * 60_000;
  return new Date(value.getTime() - offset).toISOString().slice(0, 10);
}

function completedMonthRange(months, compare = false) {
  const now = new Date();
  const end = new Date(now.getFullYear(), now.getMonth(), 0);
  const start = new Date(end.getFullYear(), end.getMonth() - months + 1, 1);
  const range = { start_date: localDateInput(start), end_date: localDateInput(end) };
  if (!compare) return { ...range, compare_start_date: '', compare_end_date: '' };
  const compareEnd = new Date(start.getFullYear(), start.getMonth(), 0);
  const compareStart = new Date(compareEnd.getFullYear(), compareEnd.getMonth() - months + 1, 1);
  return { ...range, compare_start_date: localDateInput(compareStart), compare_end_date: localDateInput(compareEnd) };
}

function emptyInsightFilters(withDefaultRange = true) {
  return {
    ...(withDefaultRange ? completedMonthRange(1) : { start_date: '', end_date: '', compare_start_date: '', compare_end_date: '' }),
    granularity: 'day',
    brand: '', category: '', sku: '', customer_email: '', city: '', postal_code: '', payment_method: '', order_status: '',
  };
}

function insightRequestFilters(filters, allowed) {
  const request = pickFilterValues(filters, allowed);
  if (allowed.includes('start_date') || allowed.includes('end_date')) {
    ['compare_start_date', 'compare_end_date', 'granularity'].forEach((key) => {
      if (filters[key]) request[key] = filters[key];
    });
  }
  return request;
}

function insightRequestKey(config, filters) {
  return `${config.id}${plainFiltersToQueryString(filters)}`;
}

function InsightsPage({ route }) {
  const activeTab = route.insightsView || 'overview';
  const [cache, setCache] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [filters, setFilters] = useState(() => emptyInsightFilters());
  const [appliedFilters, setAppliedFilters] = useState(() => emptyInsightFilters());
  const tabListRef = useRef(null);
  const tabRefs = useRef({});
  const requestRef = useRef({ id: 0, controller: null });
  const activeConfig = insightTabs.find((tab) => tab.id === activeTab) || insightTabs[0];
  const allowedFilters = insightFiltersByTab[activeTab] || [];
  const activeFilters = insightRequestFilters(appliedFilters, allowedFilters);
  const activeKey = insightRequestKey(activeConfig, activeFilters);
  const activeData = cache[activeKey];

  useEffect(() => {
    loadInsight(activeTab, activeFilters, { background: Boolean(cache[insightRequestKey(activeConfig, activeFilters)]) });
    return () => requestRef.current.controller?.abort();
  }, [activeTab]);

  useEffect(() => {
    setFilters((current) => Object.fromEntries(Object.entries(current).map(([key, value]) => [key, allowedFilters.includes(key) || ((allowedFilters.includes('start_date') || allowedFilters.includes('end_date')) && ['compare_start_date', 'compare_end_date', 'granularity'].includes(key)) ? value : ''])));
    tabRefs.current[activeTab]?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [activeTab]);

  async function loadInsight(tabId = activeTab, forceFilters, { background = false } = {}) {
    const config = insightTabs.find((tab) => tab.id === tabId) || insightTabs[0];
    const requestFilters = forceFilters || insightRequestFilters(filters, insightFiltersByTab[tabId] || []);
    const cacheKey = insightRequestKey(config, requestFilters);
    requestRef.current.controller?.abort();
    const controller = new AbortController();
    const requestId = requestRef.current.id + 1;
    requestRef.current = { id: requestId, controller };
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}${config.endpoint}${plainFiltersToQueryString(requestFilters)}`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Insights API returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId === requestRef.current.id) setCache((current) => ({ ...current, [cacheKey]: body }));
    } catch (loadError) {
      if (loadError?.name !== 'AbortError' && requestId === requestRef.current.id && !background) {
        setError('Unable to load Pongo Insights from the backend.');
      }
    } finally {
      if (requestId === requestRef.current.id) setLoading(false);
    }
  }

  function updateFilter(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  function applyFilters() {
    const nextFilters = insightRequestFilters(filters, allowedFilters);
    setAppliedFilters(filters);
    loadInsight(activeTab, nextFilters);
  }

  function clearFilters() {
    const nextFilters = emptyInsightFilters(false);
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    loadInsight(activeTab, insightRequestFilters(nextFilters, allowedFilters));
  }

  function applyDatePreset(months, compare = false) {
    const nextFilters = { ...filters, ...completedMonthRange(months, compare) };
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    loadInsight(activeTab, insightRequestFilters(nextFilters, allowedFilters));
  }

  function applySalesTemplate(granularity) {
    const nextFilters = { ...filters, ...completedMonthRange(granularity === 'week' ? 3 : 1), granularity };
    setFilters(nextFilters);
    setAppliedFilters(nextFilters);
    if (activeTab === 'orders-revenue') loadInsight(activeTab, insightRequestFilters(nextFilters, insightFiltersByTab['orders-revenue']));
    else selectTab('orders-revenue');
  }

  function selectTab(tabId) {
    window.location.hash = `#/insights/${tabId}`;
  }

  function handleTabKeyDown(event, index) {
    let nextIndex = index;
    if (event.key === 'ArrowRight') nextIndex = (index + 1) % insightTabs.length;
    else if (event.key === 'ArrowLeft') nextIndex = (index - 1 + insightTabs.length) % insightTabs.length;
    else if (event.key === 'Home') nextIndex = 0;
    else if (event.key === 'End') nextIndex = insightTabs.length - 1;
    else return;
    event.preventDefault();
    const nextTab = insightTabs[nextIndex];
    selectTab(nextTab.id);
    window.setTimeout(() => tabRefs.current[nextTab.id]?.focus(), 0);
  }

  function scrollTabs(direction) {
    tabListRef.current?.scrollBy?.({ left: direction * Math.max(240, tabListRef.current.clientWidth * 0.7), behavior: 'smooth' });
  }

  return (
    <section className="content-panel insights-page">
      <div className="insights-hero">
        <div>
          <h2>Pongo Insights</h2>
          <p>Business intelligence, customer behavior, revenue, product demand, and forecasting.</p>
        </div>
        <div className="button-row">
          {activeData?.generated_at && <small>Updated {formatDateTime(activeData.generated_at)}</small>}
          {activeConfig.exportable && <a className="action-button" href={`${API_BASE_URL}/api/insights/${activeConfig.id}/export${plainFiltersToQueryString(activeFilters)}`}><Download size={16} />Export CSV</a>}
          <button className="primary-button" onClick={() => loadInsight(activeTab, activeFilters, { background: Boolean(activeData) })} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
        </div>
      </div>

      <div className="insights-tabs-shell">
        <button className="insights-tab-scroll-button" aria-label="Show previous Insights tabs" onClick={() => scrollTabs(-1)} type="button"><ChevronLeft size={18} /></button>
        <div className="insights-tabs" ref={tabListRef} role="tablist" aria-label="Insights dashboards">
          {insightTabs.map((tab, index) => (
            <button
              className={tab.id === activeTab ? 'insight-tab active' : 'insight-tab'}
              id={`insight-tab-${tab.id}`}
              key={tab.id}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(event) => handleTabKeyDown(event, index)}
              ref={(node) => { tabRefs.current[tab.id] = node; }}
              role="tab"
              aria-controls="insight-dashboard-panel"
              aria-selected={tab.id === activeTab}
              tabIndex={tab.id === activeTab ? 0 : -1}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
        <button className="insights-tab-scroll-button" aria-label="Show more Insights tabs" onClick={() => scrollTabs(1)} type="button"><ChevronRight size={18} /></button>
      </div>

      <div className="filter-card insights-filter-card">
        {(allowedFilters.includes('start_date') || allowedFilters.includes('end_date')) && <p className="filter-context">Date range: {filters.start_date || filters.end_date ? `${filters.start_date || 'earliest'} to ${filters.end_date || 'latest'}` : 'All available local history'}</p>}
        {(allowedFilters.includes('start_date') || allowedFilters.includes('end_date')) && (
          <div className="date-preset-panel">
            <div><span>Quick range</span><small>Completed calendar periods</small></div>
            <div className="date-preset-buttons" aria-label="Insights date presets">
              <button type="button" onClick={() => applyDatePreset(1)}>Last month</button>
              <button type="button" onClick={() => applyDatePreset(2)}>Last 2 months</button>
              <button type="button" onClick={() => applyDatePreset(3)}>Last 3 months</button>
              <button type="button" onClick={() => applyDatePreset(12)}>Last year</button>
              <button type="button" onClick={() => applyDatePreset(1, true)}>Compare 1M</button>
              <button type="button" onClick={() => applyDatePreset(2, true)}>Compare 2M</button>
              <button type="button" onClick={() => applyDatePreset(12, true)}>Compare 1Y</button>
            </div>
            <div className="date-preset-buttons date-view-buttons" aria-label="Insights view templates">
              <button type="button" className={filters.granularity === 'day' && activeTab === 'orders-revenue' ? 'active' : ''} onClick={() => applySalesTemplate('day')}>Sales / day</button>
              <button type="button" className={filters.granularity === 'week' && activeTab === 'orders-revenue' ? 'active' : ''} onClick={() => applySalesTemplate('week')}>Sales / week</button>
              <a href="#/reports/received-inventory">Stock received / day</a>
            </div>
          </div>
        )}
        <div className="filter-grid report-filter-grid">
          {allowedFilters.map((field) => (
            <label className="field" key={field}>
              <span>{insightFilterLabels[field] || titleize(field)}</span>
              <input type={field.endsWith('_date') ? 'date' : 'text'} value={filters[field]} onChange={(event) => updateFilter(field, event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} />
            </label>
          ))}
        </div>
        <div className="button-row">
          <button className="primary-button" onClick={applyFilters} type="button"><Filter size={16} />Apply Filters</button>
          <button className="action-button" onClick={clearFilters} type="button"><X size={16} />Clear</button>
        </div>
      </div>

      <div className="wide-panel insight-dashboard-panel" id="insight-dashboard-panel" role="tabpanel" aria-labelledby={`insight-tab-${activeTab}`}>
        <div className="panel-title">
          <div>
            <h2>{activeConfig.label}</h2>
            <p>{activeConfig.description}</p>
          </div>
          <span className="status-pill">Read only</span>
        </div>
        {error ? <div className="api-error" role="alert"><span>{error}</span><button className="muted-button" onClick={() => loadInsight(activeTab, activeFilters)} type="button">Retry</button></div> : activeData ? <InsightDashboard config={activeConfig} data={activeData} /> : loading ? <div className="loading-strip">Loading {activeConfig.label}...</div> : <div className="empty-state"><h2>Dashboard unavailable</h2><p>Select a tab or refresh to load local analytics.</p></div>}
      </div>
    </section>
  );
}

function InsightDashboard({ config, data }) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const rawSummaryEntries = Object.entries(data.summary || {}).filter(([, value]) => typeof value !== 'object' || value === null);
  const preferredKeys = insightSummaryOrder[config.id];
  const summaryEntries = (preferredKeys ? preferredKeys.map((key) => [key, data.summary?.[key]]).filter(([, value]) => value !== undefined) : rawSummaryEntries).slice(0, 12);
  const tableRows = insightRowsForTab(config.id, data).map((row) => ({ ...row, product_name: row.product_name || row.woo_name || row.name || row.description || '' }));
  const columns = insightColumnsByTab[config.id] || Object.keys(tableRows[0] || {}).slice(0, 8);
  const trendRows = data.trends?.daily_revenue || data.trends?.revenue_by_day || [];
  const totalPages = Math.max(1, Math.ceil(tableRows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const visibleRows = tableRows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  const comparisonEntries = summaryEntries.filter(([key]) => data.comparison?.changes?.[key] !== undefined).slice(0, 6);

  useEffect(() => {
    setPage(1);
  }, [config.id, data]);

  return (
    <div className="insight-report-layout">
      <InsightDataQuality warnings={data.data_quality || []} emptyState={data.empty_state} />
      <div className="summary-strip insights-summary-strip">
        {summaryEntries.map(([key, value]) => <Metric key={key} label={titleize(key)} value={formatInsightValue(key, value)} help={insightMetricDefinitions[key]} />)}
        {!summaryEntries.length && <div className="empty-table-row">No summary metrics available for this dashboard yet.</div>}
      </div>

      {!!comparisonEntries.length && (
        <section className="insight-comparison" aria-label="Prior period comparison">
          <div className="insight-comparison-heading">
            <span>Prior period comparison</span>
            <small>{data.comparison.start_date} to {data.comparison.end_date}</small>
          </div>
          <div className="insight-comparison-grid">
            {comparisonEntries.map(([key]) => {
              const change = data.comparison.changes[key];
              return (
                <article key={key}>
                  <span>{titleize(key)}</span>
                  <strong className={change > 0 ? 'positive' : change < 0 ? 'negative' : ''}>{change === null ? 'No baseline' : `${change > 0 ? '+' : ''}${change}%`}</strong>
                  <small>Previous: {formatInsightValue(key, data.comparison.summary[key])}</small>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {!!trendRows.length && (
        <div className="insight-trend-grid">
          {trendRows.slice(-12).map((row) => {
            const value = toNumber(row.net_sales ?? row.revenue ?? row.order_count);
            const maxValue = Math.max(...trendRows.map((candidate) => toNumber(candidate.net_sales ?? candidate.revenue ?? candidate.order_count)), 1);
            return (
              <div className="trend-block" key={row.date || row.month}>
                <span>{row.date || row.month}</span>
                <div><i style={{ height: `${Math.max(8, (value / maxValue) * 100)}%` }} /></div>
                <strong>{formatInsightValue('net_sales', row.net_sales ?? row.revenue ?? row.order_count)}</strong>
              </div>
            );
          })}
        </div>
      )}

      <TableShell caption="Insights" columns={columns.map(titleize)} pagination={{ page: currentPage, pageSize, total: tableRows.length, totalPages, returnedCount: visibleRows.length, noun: 'insights', onPageChange: setPage, onPageSizeChange: (size) => { setPageSize(size); setPage(1); } }}>
        {visibleRows.map((row, index) => (
          <tr key={`${config.id}-${index}`}>
            {columns.map((column) => <td key={column} className={column.includes('description') || column.includes('text') || column === 'product_name' ? 'description-cell' : ''}>{renderInsightCell(column, row[column])}</td>)}
          </tr>
        ))}
        {!tableRows.length && <tr><td colSpan={columns.length}><div className="empty-table-row">{data.empty_state || 'Not enough data yet for this dashboard.'}</div></td></tr>}
      </TableShell>
    </div>
  );
}

function renderInsightCell(column, value) {
  if (column.includes('status')) return StatusText(value);
  if (column.includes('risk')) return StatusText(value, 'risk');
  if (column.includes('description') || column.includes('text') || column === 'product_name') return <ClampedText value={formatInsightValue(column, value)} />;
  return formatInsightValue(column, value);
}

function InsightDataQuality({ warnings, emptyState }) {
  if (!warnings.length && !emptyState) {
    return null;
  }
  return (
    <div className="insight-warning-list" aria-label="Data quality warnings">
      {emptyState && <div className="insight-warning info"><strong>Empty state</strong><span>{emptyState}</span></div>}
      {warnings.map((warning) => (
        <div className={`insight-warning ${warning.severity || 'info'}`} key={warning.code}>
          <strong>{titleize(warning.code)}</strong>
          <span>{warning.message}</span>
          {insightWarningPresentation[warning.code]?.impact && <small>{insightWarningPresentation[warning.code].impact}</small>}
          {warning.count != null && <small>{formatNumber(warning.count)} affected record(s)</small>}
          {insightWarningPresentation[warning.code]?.href && <a className="warning-action" href={insightWarningPresentation[warning.code].href}>{insightWarningPresentation[warning.code].label}</a>}
        </div>
      ))}
    </div>
  );
}

function insightRowsForTab(tabId, data) {
  if (tabId === 'overview') {
    return data.tables?.stockout_risk || data.trends?.top_skus || [];
  }
  if (tabId === 'orders-revenue') {
    return data.rows?.length ? data.rows : data.trends?.daily_revenue || [];
  }
  if (tabId === 'customer-segmentation') {
    return data.tables?.segments || data.rows || [];
  }
  return data.rows || Object.values(data.tables || {})[0] || [];
}

function ItemsPage({ route, items, pagination, itemsLoading, itemsError, onLoadItems, onRefreshItemFacets, onSaveItem, onCloneItem }) {
  if (route.itemView === 'import') {
    return <ItemImportWorkspace initialPreviewId={route.importPreviewId} initialOutcome={route.importOutcome} onCommitted={onRefreshItemFacets} />;
  }
  if (route.itemView === 'import-history') {
    return <ItemImportHistory onRolledBack={onRefreshItemFacets} />;
  }
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

  return <ItemsList items={items} pagination={pagination} loading={itemsLoading} error={itemsError} onLoadItems={onLoadItems} onRefreshItemFacets={onRefreshItemFacets} />;
}

function InventoryPage({ route, items, pagination = emptyItemsPagination, itemsLoading, summary, loading, error, onLoadItems, onRefreshItemFacets, onLoadSummary, stockMovements, stockMovementsPagination = emptyServerPagination(), stockMovementsLoading, stockMovementsError, onLoadStockMovements }) {
  const inventoryView = route.inventoryView || 'all';
  const [queryDraft, setQueryDraft] = useState(route.inventorySearch || '');
  const activeSearch = route.inventorySearch || '';
  const filters = useMemo(() => ({
    category: route.inventoryCategory || '',
    brand: route.inventoryBrand || '',
    dataQuality: route.inventoryDataQuality || '',
    sortBy: route.inventorySortBy || 'sku',
    sortDir: route.inventorySortDir || 'asc',
  }), [route.inventoryCategory, route.inventoryBrand, route.inventoryDataQuality, route.inventorySortBy, route.inventorySortDir]);
  const [locationRows, setLocationRows] = useState([]);
  const [locationRowsPagination, setLocationRowsPagination] = useState(() => emptyServerPagination(50));
  const [locationRowsLoading, setLocationRowsLoading] = useState(false);
  const [locationRowsError, setLocationRowsError] = useState('');
  const locationRowsRequestIdRef = useRef(0);
  const locationRowsAbortControllerRef = useRef(null);
  const [message, setMessage] = useState('');
  const [stockSyncError, setStockSyncError] = useState('');
  const [stockSyncMode, setStockSyncMode] = useState('');
  const [editingItem, setEditingItem] = useState(null);
  const [adjustingItem, setAdjustingItem] = useState(null);
  const [parItem, setParItem] = useState(null);
  const [cameraScannerOpen, setCameraScannerOpen] = useState(false);
  const [selectedItemIds, setSelectedItemIds] = useState([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [movementFilters, setMovementFilters] = useState({ movement_type: '', warehouse: '', inventory_location: '', date_from: '', date_to: '' });
  const selectionDisabled = itemsLoading || locationRowsLoading;

  const options = useMemo(
    () => ({
      categories: pagination.facets?.categories?.length ? pagination.facets.categories : uniqueOptions(items, 'Category'),
      brands: pagination.facets?.brands?.length ? pagination.facets.brands : uniqueOptions(items, 'Brand'),
    }),
    [items, pagination.facets],
  );

  useEffect(() => {
    setQueryDraft(route.inventorySearch || '');
  }, [route.inventorySearch]);

  useEffect(() => {
    const apiFilters = inventoryView === 'low-stock' ? { ...filters, underPar: 'true' } : filters;
    onLoadSummary({ ...apiFilters, search: activeSearch });
  }, [inventoryView, activeSearch, filters]);

  useEffect(() => {
    const apiFilters = inventoryView === 'low-stock' ? { ...filters, underPar: 'true' } : filters;
    loadLocationRows(apiFilters, activeSearch, items);
  }, [inventoryView, activeSearch, filters, items, route.inventoryPage, route.inventoryPageSize]);

  useEffect(() => () => {
    locationRowsAbortControllerRef.current?.abort();
    locationRowsAbortControllerRef.current = null;
    locationRowsRequestIdRef.current += 1;
  }, []);

  useEffect(() => {
    if (inventoryView === 'movements') {
      onLoadStockMovements({ ...stockMovementFiltersToApi(activeSearch, movementFilters), page: 1, page_size: stockMovementsPagination.page_size || 20 });
    }
  }, [inventoryView, activeSearch]);

  const enrichedLocationRows = useMemo(() => {
    const itemById = new Map(items.map((item) => [item.id, item]));
    return locationRows.map((row) => ({
      ...row,
      item: itemById.get(row.item_id) || normalizeItem({
        id: row.item_id,
        SKU: row.sku,
        Barcode: row.barcode,
        Description: row.description,
        Brand: row.brand,
        Category: row.category,
        'Unit Cost': row.unit_cost,
        active: row.item_active ?? row.active,
      }),
    }));
  }, [items, locationRows]);
  const itemRows = useMemo(() => buildInventoryItemRows(items, enrichedLocationRows, activeSearch, filters, inventoryView), [items, enrichedLocationRows, activeSearch, filters, inventoryView]);
  const groupedRows = useMemo(() => groupLocationRows(enrichedLocationRows), [enrichedLocationRows]);
  const selectableItemIds = useMemo(() => {
    const source = inventoryView === 'by-location' ? enrichedLocationRows.map((row) => row.item_id) : itemRows.map((row) => row.item.id);
    return [...new Set(source.filter(Boolean))];
  }, [inventoryView, enrichedLocationRows, itemRows]);

  useEffect(() => {
    setSelectedItemIds([]);
    setBulkOpen(false);
  }, [inventoryView, activeSearch, filters, route.inventoryPage, route.inventoryPageSize, pagination.page, pagination.page_size]);

  useEffect(() => {
    const loadedItemIds = new Set(items.map((item) => item.id));
    setSelectedItemIds((current) => current.filter((itemId) => loadedItemIds.has(itemId)));
    setBulkOpen(false);
  }, [items]);

  useEffect(() => {
    const visibleIds = new Set(selectableItemIds);
    setSelectedItemIds((current) => current.filter((itemId) => visibleIds.has(itemId)));
    setBulkOpen(false);
  }, [selectableItemIds]);

  function submitSearch(nextSearch = queryDraft) {
    window.location.hash = inventoryRouteHref(route, { search: nextSearch.trim(), page: 1 });
  }

  function searchScannedInventoryCode(value) {
    const scannedValue = value.trim();
    setQueryDraft(scannedValue);
    setMessage(`Searching inventory for scanned code ${scannedValue.slice(0, 80)}.`);
    submitSearch(scannedValue);
  }

  function updateFilter(name, value) {
    window.location.hash = inventoryRouteHref(route, { [name]: value, page: 1 });
  }

  function clearFilters() {
    setQueryDraft('');
    setMovementFilters({ movement_type: '', warehouse: '', inventory_location: '', date_from: '', date_to: '' });
    window.location.hash = inventoryRouteHref(route, { search: '', category: '', brand: '', dataQuality: '', sortBy: 'sku', sortDir: 'asc', page: 1 });
  }

  async function loadLocationRows(nextFilters = filters, search = activeSearch, currentItems = items) {
    const requestId = locationRowsRequestIdRef.current + 1;
    locationRowsRequestIdRef.current = requestId;
    locationRowsAbortControllerRef.current?.abort();
    const controller = new AbortController();
    locationRowsAbortControllerRef.current = controller;
    if (inventoryView !== 'by-location' && currentItems.length === 0) {
      setLocationRows([]);
      setLocationRowsError('');
      setLocationRowsLoading(false);
      locationRowsAbortControllerRef.current = null;
      return;
    }
    setLocationRowsLoading(true);
    setLocationRowsError('');
    try {
      const query = plainFiltersToQueryString({
        search: search || undefined,
        category: nextFilters.category || undefined,
        brand: nextFilters.brand || undefined,
        under_par: nextFilters.underPar || undefined,
        item_ids: inventoryView === 'by-location' ? undefined : currentItems.map((item) => item.id).filter(Boolean).join(',') || undefined,
        page: inventoryView === 'by-location' ? Number(route.inventoryPage || 1) : 1,
        page_size: inventoryView === 'by-location' ? Number(route.inventoryPageSize || 50) : 100,
      });
      const response = await apiFetch(`${API_BASE_URL}/api/inventory/locations${query}`, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Location inventory API returned ${response.status}`);
      }
      const body = await response.json();
      if (requestId === locationRowsRequestIdRef.current) {
        setLocationRows(body.rows || []);
        setLocationRowsPagination(paginationFromResponse(body, inventoryView === 'by-location' ? Number(route.inventoryPageSize || 50) : 100));
      }
    } catch (fetchError) {
      if (fetchError?.name !== 'AbortError' && requestId === locationRowsRequestIdRef.current) setLocationRowsError('Unable to load location stock rows from the backend.');
    } finally {
      if (requestId === locationRowsRequestIdRef.current) {
        locationRowsAbortControllerRef.current = null;
        setLocationRowsLoading(false);
      }
    }
  }

  async function refreshInventory() {
    await onLoadItems(inventoryRouteToItemFilters(route));
    await onLoadSummary({ ...filters, search: activeSearch });
    if (inventoryView === 'movements') {
      await onLoadStockMovements(stockMovementFiltersToApi(activeSearch, movementFilters));
    }
  }

  async function saveProductInfo(item, payload) {
    await patchJson(`/api/items/${item.id}`, payload);
    await onRefreshItemFacets();
    setMessage(`Saved product info for ${item.SKU || productTitle(item) || 'item'}.`);
    setEditingItem(null);
    await refreshInventory();
  }

  async function saveParLevel(item, payload) {
    await patchJson(`/api/items/${item.id}`, payload);
    setMessage(`Saved par level for ${item.SKU || productTitle(item) || 'item'}.`);
    setParItem(null);
    await refreshInventory();
  }

  async function commitStockEdit(payload) {
    const result = await postJson('/api/inventory/adjustments', payload);
    setMessage(`Adjustment ${result.adjustment_number} committed. Changed stock was submitted to WooCommerce writeback.`);
    setAdjustingItem(null);
    await refreshInventory();
  }

  async function syncWooStock(force) {
    const mode = force ? 'all' : 'changed';
    setStockSyncMode(mode);
    setStockSyncError('');
    setMessage('');
    try {
      const result = await postJson('/api/integrations/woocommerce/writeback/stock/sync', {
        force,
        requested_by: force ? 'inventory-update-all' : 'inventory-update-changed',
      });
      if (result.status === 'disabled' || result.status === 'failed') {
        setStockSyncError((result.errors || []).join(' ') || 'WooCommerce stock writeback failed.');
      } else if (result.status === 'no_changes') {
        if (result.skipped_unmapped_count) {
          setStockSyncError(`No stock was sent. ${result.skipped_unmapped_count} local item(s) are not linked to WooCommerce.`);
        } else {
          setMessage(force ? 'No WooCommerce-mapped inventory items were available to update.' : 'WooCommerce stock is already up to date.');
        }
      } else if (result.status === 'dry_run') {
        setMessage(`${result.dry_run_count} stock level(s) passed through dry-run; WooCommerce was not changed.`);
      } else {
        const skipped = result.skipped_unmapped_count ? ` ${result.skipped_unmapped_count} unmapped local item(s) were skipped.` : '';
        setMessage(`${result.sent_count} stock level(s) updated in WooCommerce.${skipped}`);
        if (result.failed_count) setStockSyncError(`${result.failed_count} stock level(s) failed. ${(result.errors || []).join(' ')}`);
      }
      await refreshInventory();
    } catch (syncError) {
      setStockSyncError(syncError.message || 'Unable to update WooCommerce stock.');
    } finally {
      setStockSyncMode('');
    }
  }

  function viewLocationStock(item) {
    window.location.hash = inventoryRouteHref({ ...route, inventoryView: 'by-location' }, { search: item.SKU || item.Barcode || '', page: 1 });
  }

  function viewMovements(item) {
    window.location.hash = inventoryRouteHref({ ...route, inventoryView: 'movements' }, { search: item.SKU || item.Barcode || '', page: 1 });
  }

  function viewOrders(item) {
    window.location.hash = `#/orders/open`;
    setMessage(`Open Orders can be filtered for SKU ${item.SKU || item.Barcode || 'selected item'} from the Orders page.`);
  }

  function toggleInventoryItem(itemId) {
    if (selectionDisabled) return;
    setSelectedItemIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleAllInventoryItems(checked, itemIds = selectableItemIds) {
    if (selectionDisabled) return;
    const targetIds = new Set(itemIds);
    setSelectedItemIds((current) => (checked ? [...new Set([...current, ...itemIds])] : current.filter((id) => !targetIds.has(id))));
  }

  function changeInventoryPage(page) {
    setSelectedItemIds([]);
    setBulkOpen(false);
    window.location.hash = inventoryRouteHref(route, { page });
  }

  function changeInventoryPageSize(pageSize) {
    setSelectedItemIds([]);
    setBulkOpen(false);
    window.location.hash = inventoryRouteHref(route, { pageSize, page: 1 });
  }

  async function finishBulkEdit(result) {
    setMessage(`Updated ${result.updated_count} inventory item(s).`);
    setSelectedItemIds([]);
    await onRefreshItemFacets();
    await refreshInventory();
  }

  return (
    <section className="content-panel inventory-page">
      <div className="inventory-sync-toolbar" aria-label="WooCommerce stock controls">
        <span className="bulk-selection-count" aria-live="polite">{selectedItemIds.length ? `${selectedItemIds.length} selected` : 'Select items to bulk edit'}</span>
        <button className="action-button" disabled={selectionDisabled || !selectedItemIds.length} onClick={() => setBulkOpen(true)} type="button">
          <Edit3 size={17} />
          Bulk Edit
        </button>
        <button className="muted-button" disabled={Boolean(stockSyncMode)} onClick={() => syncWooStock(false)} type="button">
          <RefreshCw size={17} />
          Update Stock
        </button>
        <button className="primary-button" disabled={Boolean(stockSyncMode)} onClick={() => syncWooStock(true)} type="button">
          <Upload size={17} />
          Update Stock All
        </button>
      </div>
      <div className="summary-strip inventory-summary-strip">
        <Metric label="Inventory Records" value={pagination.total ?? items.length} help="Catalog inventory records matching the current filters." />
        <Metric label="In Stock" value={formatNumber(summary.total_in_stock ?? inventoryTotal(items, 'In Stock'))} />
        <Metric label="Allocated" value={formatNumber(summary.total_allocated ?? inventoryTotal(items, 'Allocated'))} />
        <Metric label="Sellable" value={formatNumber(summary.total_sellable ?? inventoryTotal(items, 'Sellable'))} />
        <Metric label="Inventory Value" value={formatCurrency(summary.total_inventory_value ?? inventoryValue(items))} help="On-hand quantity multiplied by known unit cost; items without cost do not add fabricated value." />
        <Metric label="Under Par" value={summary.under_par_count ?? itemRows.filter((row) => row.underPar).length} />
      </div>

      <InventoryScannerSearch value={queryDraft} onChange={setQueryDraft} onSubmit={submitSearch} onClear={clearFilters} filters={filters} options={options} onFilterChange={updateFilter} onOpenScanner={() => setCameraScannerOpen(true)} />

      {error && <div className="api-error">{error}</div>}
      {locationRowsError && <div className="api-error">{locationRowsError}</div>}
      {stockMovementsError && inventoryView === 'movements' && <div className="api-error">{stockMovementsError}</div>}
      {stockSyncError && <div className="api-error" role="alert">{stockSyncError}</div>}
      {message && <div className="api-success" role="status" aria-live="polite">{message}</div>}
      {(loading || locationRowsLoading || itemsLoading) && <div className="loading-strip">Loading inventory...</div>}

      {inventoryView === 'all' && <AllInventoryTable rows={itemRows} pagination={pagination} selectedIds={selectedItemIds} selectionDisabled={selectionDisabled} onToggleSelected={toggleInventoryItem} onToggleAll={toggleAllInventoryItems} onPageChange={changeInventoryPage} onPageSizeChange={changeInventoryPageSize} onEdit={setEditingItem} onStock={setAdjustingItem} onLocation={viewLocationStock} onMovements={viewMovements} onOrders={viewOrders} />}
      {inventoryView === 'by-location' && <><InventoryByLocationView groups={groupedRows} rows={enrichedLocationRows} selectedIds={selectedItemIds} selectionDisabled={selectionDisabled} onToggleSelected={toggleInventoryItem} onToggleAll={toggleAllInventoryItems} onEdit={setEditingItem} onStock={setAdjustingItem} onMovements={viewMovements} /><TablePager pagination={serverTablePagination(locationRowsPagination, 'location rows', changeInventoryPage, changeInventoryPageSize)} /></>}
      {inventoryView === 'low-stock' && <LowStockTable rows={itemRows} pagination={pagination} onPageChange={changeInventoryPage} onPageSizeChange={changeInventoryPageSize} selectedIds={selectedItemIds} selectionDisabled={selectionDisabled} onToggleSelected={toggleInventoryItem} onToggleAll={toggleAllInventoryItems} onEdit={setEditingItem} onStock={setAdjustingItem} onMovements={viewMovements} />}
      {inventoryView === 'expiring' && <ExpiringStockView rows={itemRows.filter((row) => row.item.Perishable || row.item['Track Lot'])} />}
      {inventoryView === 'par-level' && <ParLevelTable rows={itemRows} pagination={pagination} onPageChange={changeInventoryPage} onPageSizeChange={changeInventoryPageSize} selectedIds={selectedItemIds} selectionDisabled={selectionDisabled} onToggleSelected={toggleInventoryItem} onToggleAll={toggleAllInventoryItems} onEdit={setEditingItem} onPar={setParItem} onStock={setAdjustingItem} onMovements={viewMovements} />}
      {inventoryView === 'movements' && <InventoryMovementsView movements={stockMovements} pagination={stockMovementsPagination} loading={stockMovementsLoading} filters={movementFilters} setFilters={setMovementFilters} activeSearch={activeSearch} onLoad={(page = 1, pageSize = stockMovementsPagination.page_size || 20) => onLoadStockMovements({ ...stockMovementFiltersToApi(activeSearch, movementFilters), page, page_size: pageSize })} />}

      {editingItem && <ProductInfoModal item={editingItem} onClose={() => setEditingItem(null)} onSave={saveProductInfo} />}
      {adjustingItem && <StockAdjustmentModal item={adjustingItem} locationRows={enrichedLocationRows.filter((row) => row.item_id === adjustingItem.id)} onClose={() => setAdjustingItem(null)} onCommit={commitStockEdit} />}
      {parItem && <ParLevelModal item={parItem} onClose={() => setParItem(null)} onSave={saveParLevel} />}
      {bulkOpen && <BulkEditModal selectedIds={selectedItemIds} onCommitted={finishBulkEdit} onClose={() => setBulkOpen(false)} />}
      <MobileCodeScanner open={cameraScannerOpen} onClose={() => setCameraScannerOpen(false)} onDetected={searchScannedInventoryCode} />
    </section>
  );
}

function InventoryScannerSearch({ value, onChange, onSubmit, onClear, filters, options, onFilterChange, onOpenScanner }) {
  return (
    <div className="inventory-search-card">
      <div className="inventory-search-row">
        <label className="zenventory-filter-field">
          <span>Category</span>
          <select value={filters.category} onChange={(event) => onFilterChange('category', event.target.value)}>
            <option value="">All Categories</option>
            {[...new Set([filters.category, ...options.categories].filter(Boolean))].map((category) => <option key={category} value={category}>{decodeHtmlEntities(category)}</option>)}
          </select>
        </label>
        <label className="zenventory-filter-field">
          <span>Brand</span>
          <select value={filters.brand} onChange={(event) => onFilterChange('brand', event.target.value)}>
            <option value="">All Brands</option>
            {[...new Set([filters.brand, ...options.brands].filter(Boolean))].map((brand) => <option key={brand} value={brand}>{decodeHtmlEntities(brand)}</option>)}
          </select>
        </label>
        <label className="zenventory-filter-field">
          <span>Data Quality</span>
          <select value={filters.dataQuality} onChange={(event) => onFilterChange('dataQuality', event.target.value)}>
            <option value="">All Records</option>
            <option value="missing_barcode">Barcode missing</option>
            <option value="missing_brand">Brand missing</option>
            <option value="missing_cost">Cost missing</option>
            <option value="unmapped">WooCommerce mapping missing</option>
            <option value="receiving">In receiving staging</option>
            <option value="missing_location">Location unassigned</option>
          </select>
        </label>
        <label className="zenventory-filter-field">
          <span>Sort By</span>
          <select value={filters.sortBy} onChange={(event) => onFilterChange('sortBy', event.target.value)}>
            <option value="sku">SKU</option>
            <option value="description">Product title</option>
            <option value="brand">Brand</option>
            <option value="category">Category</option>
            <option value="in_stock">In stock</option>
            <option value="unit_cost">Unit cost</option>
          </select>
        </label>
        <label className="zenventory-filter-field">
          <span>Sort Direction</span>
          <select value={filters.sortDir} onChange={(event) => onFilterChange('sortDir', event.target.value)}><option value="asc">Ascending</option><option value="desc">Descending</option></select>
        </label>
        <InventoryKeywordSearch className="zenventory-search-field" value={value} onChange={onChange} onSearch={onSubmit} label="Scan or search inventory" placeholder="Search barcode, SKU, product title, or brand" autoFocus />
        <button aria-label="Scan QR code or barcode with camera" className="inventory-camera-button" onClick={onOpenScanner} type="button"><Camera aria-hidden="true" size={17} /> Scan code</button>
        <button className="inventory-search-button" onClick={() => onSubmit(value.trim())} type="button">Search</button>
        <button className="inventory-reset-button" onClick={onClear} type="button">Reset</button>
      </div>
    </div>
  );
}

function AllInventoryTable({ rows, pagination, selectedIds, selectionDisabled = false, onToggleSelected, onToggleAll, onPageChange, onPageSizeChange, onEdit, onStock, onLocation, onMovements, onOrders }) {
  const rowIds = rows.map((row) => row.item.id);
  const allSelected = rowIds.length > 0 && rowIds.every((id) => selectedIds.includes(id));
  return (
    <TableShell caption="Inventory records" columns={[{ key: 'select', label: <input aria-label="Select all visible inventory items" checked={allSelected} disabled={selectionDisabled} onChange={(event) => onToggleAll(event.target.checked, rowIds)} type="checkbox" /> }, 'Actions', 'SKU / Barcode', 'Product Title', 'Brand', 'Category', 'Location', 'In Stock', 'Open Orders', 'Allocated', 'Sellable', 'Unit Cost', 'Value', 'Active']} pagination={{ page: pagination.page, pageSize: pagination.page_size, total: pagination.total, totalPages: pagination.total_pages, returnedCount: pagination.returned_count, noun: 'inventory records', onPageChange, onPageSizeChange }}>
      {rows.map((row) => <InventoryItemRow key={row.item.id} row={row} selected={selectedIds.includes(row.item.id)} selectionDisabled={selectionDisabled} onToggleSelected={onToggleSelected} onEdit={onEdit} onStock={onStock} onLocation={onLocation} onMovements={onMovements} onOrders={onOrders} />)}
      {!rows.length && <tr><td colSpan={14}><div className="empty-table-row">No inventory items match the current search.</div></td></tr>}
    </TableShell>
  );
}

function InventoryItemRow({ row, selected, selectionDisabled = false, onToggleSelected, onEdit, onStock, onLocation, onMovements, onOrders }) {
  const item = row.item;
  return (
    <tr>
      <td><input aria-label={`Select ${item.SKU || productTitle(item) || 'inventory item'}`} checked={selected} disabled={selectionDisabled} onChange={() => onToggleSelected(item.id)} type="checkbox" /></td>
      <td><InventoryRowActions item={item} onEdit={onEdit} onStock={onStock} onLocation={onLocation} onMovements={onMovements} onOrders={onOrders} /></td>
      <td><div className="sku-barcode-cell"><strong>{item.SKU || <DataQualityBadge kind="missing_sku" />}</strong><span>{item.Barcode || <DataQualityBadge kind="missing_barcode" />}</span></div></td>
      <td className="description-cell"><ClampedText value={productTitle(item)} /></td>
      <td>{item.Brand ? decodeHtmlEntities(item.Brand) : <DataQualityBadge kind="missing_brand" />}</td>
      <td>{item.Category ? decodeHtmlEntities(item.Category) : <DataQualityBadge kind="missing_category" />}</td>
      <td>{row.locationSummary ? <LocationPresentation value={row.locationSummary} /> : <DataQualityBadge kind="missing_location" />}</td>
      <td>{formatNumber(item['In Stock'])}</td>
      <td>{formatOpenOrders(item)}</td>
      <td>{formatNumber(item.Allocated)}</td>
      <td>{formatNumber(item.Sellable)}</td>
      <td>{isMissingValue(item['Unit Cost']) ? <DataQualityBadge kind="missing_cost" /> : formatCurrency(item['Unit Cost'])}</td>
      <td>{isMissingValue(item['Unit Cost']) ? 'Not available' : formatCurrency(toNumber(item['In Stock']) * toNumber(item['Unit Cost']))}</td>
      <td><StatusBadge active={item.active} /></td>
    </tr>
  );
}

function InventoryRowActions({ item, onEdit, onStock, onLocation, onMovements, onOrders }) {
  const actions = [
    { label: 'Edit Product Info', icon: Edit3, onClick: () => onEdit(item) },
    { label: 'Edit Current Stock', icon: SlidersHorizontal, onClick: () => onStock(item) },
    { label: 'View Location Stock', onClick: () => onLocation(item) },
    { label: 'View Stock Movements', onClick: () => onMovements(item) },
    { label: 'View Orders for SKU', onClick: () => onOrders(item) },
  ];
  return <InventoryActionsMenu actions={actions} />;
}

function InventoryCompactActions({ item, onEdit, onStock, onMovements }) {
  const actions = [
    { label: 'Edit Product Info', icon: Edit3, onClick: () => onEdit(item) },
    { label: 'Edit Current Stock', icon: SlidersHorizontal, onClick: () => onStock(item) },
    { label: 'View Stock Movements', onClick: () => onMovements(item) },
  ];
  return <InventoryActionsMenu actions={actions} />;
}

function InventoryParActions({ item, onEdit, onPar, onStock, onMovements }) {
  const actions = [
    { label: 'Edit Product Info', icon: Edit3, onClick: () => onEdit(item) },
    { label: 'Edit Par Level', onClick: () => onPar(item) },
    { label: 'Edit Current Stock', icon: SlidersHorizontal, onClick: () => onStock(item) },
    { label: 'View Stock Movements', onClick: () => onMovements(item) },
  ];
  return <InventoryActionsMenu actions={actions} />;
}

function BodyPortal({ children }) {
  useEffect(() => {
    if (typeof document === 'undefined') return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = previousOverflow; };
  }, []);
  if (typeof document === 'undefined') return null;
  return createPortal(<div className="app-shell app-overlay-root">{children}</div>, document.body);
}

function FloatingMenu({ open, triggerRef, onClose, className, align = 'start', closeOnAction = false, menuRole = 'menu', id = undefined, ariaLabel = undefined, children }) {
  const popoverRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const [position, setPosition] = useState(null);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) {
      setPosition(null);
      return undefined;
    }

    function updatePosition() {
      const trigger = triggerRef.current;
      const popover = popoverRef.current;
      if (!trigger || !popover) return;
      const visualViewport = window.visualViewport;
      const viewportLeft = visualViewport?.offsetLeft || 0;
      const viewportTop = visualViewport?.offsetTop || 0;
      const viewportWidth = visualViewport?.width || window.innerWidth;
      const viewportHeight = visualViewport?.height || window.innerHeight;
      const triggerRect = trigger.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      const gutter = 10;
      const gap = 6;
      const mobileWidth = viewportWidth <= 760 ? Math.max(0, viewportWidth - (gutter * 2)) : null;
      const width = mobileWidth ?? Math.min(popoverRect.width, viewportWidth - (gutter * 2));
      const height = Math.min(popoverRect.height, viewportHeight - (gutter * 2));
      const preferredLeft = align === 'end' ? triggerRect.right - width : triggerRect.left;
      const minimumLeft = viewportLeft + gutter;
      const maximumLeft = viewportLeft + viewportWidth - width - gutter;
      const left = Math.min(Math.max(minimumLeft, preferredLeft), Math.max(minimumLeft, maximumLeft));
      const roomBelow = viewportTop + viewportHeight - triggerRect.bottom - gutter;
      const roomAbove = triggerRect.top - viewportTop - gutter;
      const top = roomBelow < height + gap && roomAbove > roomBelow
        ? Math.max(viewportTop + gutter, triggerRect.top - height - gap)
        : Math.min(triggerRect.bottom + gap, Math.max(viewportTop + gutter, viewportTop + viewportHeight - height - gutter));
      setPosition({ left, top, maxHeight: Math.max(0, viewportHeight - (gutter * 2)), width: mobileWidth });
    }

    function closeOnOutsidePointer(event) {
      if (!triggerRef.current?.contains(event.target) && !popoverRef.current?.contains(event.target)) onCloseRef.current();
    }

    function closeOnEscape(event) {
      if (event.key === 'Escape') onCloseRef.current();
    }

    updatePosition();
    document.addEventListener('pointerdown', closeOnOutsidePointer);
    document.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', updatePosition);
    window.addEventListener('scroll', updatePosition, true);
    window.visualViewport?.addEventListener('resize', updatePosition);
    window.visualViewport?.addEventListener('scroll', updatePosition);
    return () => {
      document.removeEventListener('pointerdown', closeOnOutsidePointer);
      document.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', updatePosition);
      window.removeEventListener('scroll', updatePosition, true);
      window.visualViewport?.removeEventListener('resize', updatePosition);
      window.visualViewport?.removeEventListener('scroll', updatePosition);
    };
  }, [align, open, triggerRef]);

  if (!open || typeof document === 'undefined') return null;
  return createPortal(
    <div
      className={`${className} floating-menu`}
      aria-label={ariaLabel}
      id={id}
      onClick={(event) => { if (closeOnAction && event.target.closest?.('button, a')) onCloseRef.current(); }}
      ref={popoverRef}
      role={menuRole}
      style={{
        left: position?.left ?? 0,
        top: position?.top ?? 0,
        maxHeight: position?.maxHeight,
        position: 'fixed',
        visibility: position ? 'visible' : 'hidden',
        width: position?.width,
        zIndex: 1200,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}

function InventoryActionsMenu({ actions }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  return (
    <div className="inventory-actions-menu">
      <button ref={triggerRef} className="inventory-actions-trigger" onClick={() => setOpen((current) => !current)} aria-haspopup="menu" aria-expanded={open} aria-label="Open inventory actions" type="button">
        <Menu size={18} />
        <span>Actions</span>
      </button>
      <FloatingMenu className="inventory-actions-popover" onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <button key={action.label} onClick={() => { setOpen(false); action.onClick(); }} role="menuitem" type="button">
                {Icon ? <Icon size={15} /> : <span className="menu-dot" aria-hidden="true" />}
                {action.label}
              </button>
            );
          })}
      </FloatingMenu>
    </div>
  );
}

function InventoryByLocationView({ groups, rows, selectedIds, selectionDisabled = false, onToggleSelected, onToggleAll, onEdit, onStock, onMovements }) {
  return (
    <div className="location-inventory-sections">
      <InventorySummaryTable groups={groups} />
      {groups.map((group) => {
        const groupRows = rows.filter((row) => inventoryLocationKey(row) === group.key);
        const groupItemIds = [...new Set(groupRows.map((row) => row.item_id).filter(Boolean))];
        const allSelected = groupItemIds.length > 0 && groupItemIds.every((id) => selectedIds.includes(id));
        return (
          <section className="location-operations" key={group.key}>
            <div className="section-heading">
              <div>
                <h3>{group.warehouse || 'Unassigned'} / {group.inventory_location || 'Unassigned'}</h3>
                <p>{group.item_count} item(s), {formatNumber(group.total_sellable)} sellable</p>
              </div>
              <Metric label="Value" value={formatCurrency(group.total_inventory_value)} />
            </div>
            <TableShell caption={`${groupRows.length} location row(s)`} columns={[{ key: 'select', label: <input aria-label={`Select all items in ${group.inventory_location || 'location'}`} checked={allSelected} disabled={selectionDisabled} onChange={(event) => onToggleAll(event.target.checked, groupItemIds)} type="checkbox" /> }, 'Actions', 'SKU / Barcode', 'Product Title', 'Brand', 'Category', 'In Stock', 'Allocated', 'Sellable', 'Unit Cost', 'Value']}>
              {groupRows.map((row) => {
                const item = row.item || {};
                return (
                  <tr key={row.id}>
                    <td><input aria-label={`Select ${row.sku || item.SKU || 'inventory item'}`} checked={selectedIds.includes(row.item_id)} disabled={selectionDisabled} onChange={() => onToggleSelected(row.item_id)} type="checkbox" /></td>
                    <td><InventoryCompactActions item={item} onEdit={onEdit} onStock={onStock} onMovements={onMovements} /></td>
                    <td><div className="sku-barcode-cell"><strong>{row.sku || item.SKU}</strong><span>{row.barcode || item.Barcode}</span></div></td>
                    <td className="description-cell"><ClampedText value={productTitle(item) || row.description} /></td>
                    <td>{item.Brand ? decodeHtmlEntities(item.Brand) : <DataQualityBadge kind="missing_brand" />}</td>
                    <td>{item.Category ? decodeHtmlEntities(item.Category) : <DataQualityBadge kind="missing_category" />}</td>
                    <td>{formatNumber(row.in_stock)}</td>
                    <td>{formatNumber(row.allocated)}</td>
                    <td>{formatNumber(row.sellable)}</td>
                    <td>{formatCurrency(item['Unit Cost'])}</td>
                    <td>{formatCurrency(toNumber(row.in_stock) * toNumber(item['Unit Cost']))}</td>
                  </tr>
                );
              })}
              {!groupRows.length && <tr><td colSpan={11}><div className="empty-table-row">No products in this location.</div></td></tr>}
            </TableShell>
          </section>
        );
      })}
      {!groups.length && <div className="empty-state"><h2>No location inventory found</h2><p>Search or filters did not match any location stock rows.</p></div>}
    </div>
  );
}

function LowStockTable({ rows, pagination, onPageChange, onPageSizeChange, selectedIds, selectionDisabled = false, onToggleSelected, onToggleAll, onEdit, onStock, onMovements }) {
  const lowRows = rows.filter((row) => row.underPar);
  const rowIds = lowRows.map((row) => row.item.id);
  const allSelected = rowIds.length > 0 && rowIds.every((id) => selectedIds.includes(id));
  return (
    <TableShell caption={`${pagination?.total ?? lowRows.length} low stock item(s)`} columns={[{ key: 'select', label: <input aria-label="Select all visible low-stock items" checked={allSelected} disabled={selectionDisabled} onChange={(event) => onToggleAll(event.target.checked, rowIds)} type="checkbox" /> }, 'Actions', 'SKU / Barcode', 'Product Title', 'Location', 'In Stock', 'Allocated', 'Sellable', 'Par Level', 'Under Par', 'Suggested Reorder', 'Open Orders']} pagination={serverTablePagination(pagination, 'low stock items', onPageChange, onPageSizeChange)}>
      {lowRows.map((row) => (
        <tr key={row.item.id}>
          <td><input aria-label={`Select ${row.item.SKU || productTitle(row.item) || 'inventory item'}`} checked={selectedIds.includes(row.item.id)} disabled={selectionDisabled} onChange={() => onToggleSelected(row.item.id)} type="checkbox" /></td>
          <td><InventoryCompactActions item={row.item} onEdit={onEdit} onStock={onStock} onMovements={onMovements} /></td>
          <td><div className="sku-barcode-cell"><strong>{row.item.SKU}</strong><span>{row.item.Barcode}</span></div></td>
          <td className="description-cell"><ClampedText value={productTitle(row.item)} /></td>
          <td>{row.locationSummary}</td>
          <td>{formatNumber(row.item['In Stock'])}</td>
          <td>{formatNumber(row.item.Allocated)}</td>
          <td>{formatNumber(row.item.Sellable)}</td>
          <td>{formatNumber(row.item['Par Level'])}</td>
          <td>{formatNumber(Math.max(0, toNumber(row.item['Par Level']) - toNumber(row.item['In Stock'])))}</td>
          <td>{formatNumber(Math.max(0, toNumber(row.item['Default Econ Order']) || (toNumber(row.item['Par Level']) - toNumber(row.item.Sellable))))}</td>
          <td>{formatOpenOrders(row.item)}</td>
        </tr>
      ))}
      {!lowRows.length && <tr><td colSpan={12}><div className="empty-table-row">No low stock items match the current filters.</div></td></tr>}
    </TableShell>
  );
}

function ExpiringStockView() {
  return (
    <div className="empty-state">
      <h2>No expiring stock records found.</h2>
      <p>Expiration tracking will appear here when receipt lots include expiration dates.</p>
    </div>
  );
}

function ParLevelTable({ rows, pagination, onPageChange, onPageSizeChange, selectedIds, selectionDisabled = false, onToggleSelected, onToggleAll, onEdit, onPar, onStock, onMovements }) {
  const rowIds = rows.map((row) => row.item.id);
  const allSelected = rowIds.length > 0 && rowIds.every((id) => selectedIds.includes(id));
  return (
    <TableShell caption={`${pagination?.total ?? rows.length} par level item(s)`} columns={[{ key: 'select', label: <input aria-label="Select all visible par-level items" checked={allSelected} disabled={selectionDisabled} onChange={(event) => onToggleAll(event.target.checked, rowIds)} type="checkbox" /> }, 'Actions', 'SKU / Barcode', 'Product Title', 'Location', 'In Stock', 'Allocated', 'Sellable', 'Par Level', 'Under Par', 'Reorder Enabled', 'Default Econ Order', 'Suggested Order Qty']} pagination={serverTablePagination(pagination, 'par level items', onPageChange, onPageSizeChange)}>
      {rows.map((row) => (
        <tr key={row.item.id}>
          <td><input aria-label={`Select ${row.item.SKU || productTitle(row.item) || 'inventory item'}`} checked={selectedIds.includes(row.item.id)} disabled={selectionDisabled} onChange={() => onToggleSelected(row.item.id)} type="checkbox" /></td>
          <td><InventoryParActions item={row.item} onEdit={onEdit} onPar={onPar} onStock={onStock} onMovements={onMovements} /></td>
          <td><div className="sku-barcode-cell"><strong>{row.item.SKU}</strong><span>{row.item.Barcode}</span></div></td>
          <td className="description-cell"><ClampedText value={productTitle(row.item)} /></td>
          <td>{row.locationSummary}</td>
          <td>{formatNumber(row.item['In Stock'])}</td>
          <td>{formatNumber(row.item.Allocated)}</td>
          <td>{formatNumber(row.item.Sellable)}</td>
          <td>{formatNumber(row.item['Par Level'])}</td>
          <td>{row.underPar ? 'Yes' : 'No'}</td>
          <td>{row.item['Re-Order'] ? 'Yes' : 'No'}</td>
          <td>{formatNumber(row.item['Default Econ Order'])}</td>
          <td>{formatNumber(Math.max(0, toNumber(row.item['Default Econ Order']) || (toNumber(row.item['Par Level']) - toNumber(row.item.Sellable))))}</td>
        </tr>
      ))}
      {!rows.length && <tr><td colSpan={13}><div className="empty-table-row">No par level rows match the current filters.</div></td></tr>}
    </TableShell>
  );
}

function InventoryMovementsView({ movements, pagination, loading, filters, setFilters, activeSearch, onLoad }) {
  function update(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }
  return (
    <div className="inventory-movement-ledger">
      <div className="toolbar items-toolbar">
        <div className="filter-grid report-filter-grid">
          <label className="field"><span>Movement Type</span><input value={filters.movement_type} onChange={(event) => update('movement_type', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, onLoad)} /></label>
          <label className="field"><span>Warehouse</span><input value={filters.warehouse} onChange={(event) => update('warehouse', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, onLoad)} /></label>
          <label className="field"><span>Inventory Location</span><input value={filters.inventory_location} onChange={(event) => update('inventory_location', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, onLoad)} /></label>
          <label className="field"><span>Date From</span><input type="date" value={filters.date_from} onChange={(event) => update('date_from', event.target.value)} /></label>
          <label className="field"><span>Date To</span><input type="date" value={filters.date_to} onChange={(event) => update('date_to', event.target.value)} /></label>
        </div>
        <div className="button-row"><button className="primary-button" onClick={() => onLoad(1, pagination.page_size || 20)} type="button"><Search size={16} />Filter</button><button className="action-button" onClick={() => exportStockMovementsCsv(stockMovementFiltersToApi(activeSearch, filters))} type="button"><Download size={16} />Export CSV</button></div>
      </div>
      {loading && <div className="loading-strip">Loading stock movements...</div>}
      <TableShell caption={`${pagination?.total ?? movements.length} stock movement(s)`} columns={['Date', 'Movement Type', 'SKU', 'Barcode', 'Product Title', 'Warehouse', 'Location', 'Quantity Change', 'Old Stock', 'New Stock', 'Reference', 'Reason', 'Notes', 'Action']} pagination={serverTablePagination(pagination, 'stock movements', (page) => onLoad(page, pagination.page_size || 20), (pageSize) => onLoad(1, pageSize))}>
        {movements.map((movement) => (
          <tr key={movement.id}>
            <td>{formatDateTime(movement.created_at)}</td>
            <td>{StatusText(movement.movement_type)}</td>
            <td className="mono">{movement.sku}</td>
            <td className="mono">{movement.barcode}</td>
            <td className="description-cell"><ClampedText value={movement.description} /></td>
            <td>{movement.warehouse}</td>
            <td><LocationPresentation value={movement.inventory_location} /></td>
            <td>{formatNumber(movement.quantity_delta)}</td>
            <td>{formatNumber(movement.previous_in_stock ?? movement.previous_location_in_stock)}</td>
            <td>{formatNumber(movement.new_in_stock ?? movement.new_location_in_stock)}</td>
            <td>{movement.reference_number || movement.reference_type || ''}</td>
            <td>{movement.reason || ''}</td>
            <td>{movement.notes || ''}</td>
            <td><a className="action-button btn-sm" href={`#/items/${movement.item_id}`}>View Item</a></td>
          </tr>
        ))}
        {!movements.length && <tr><td colSpan={14}><div className="empty-table-row">No stock movements match the current filters.</div></td></tr>}
      </TableShell>
    </div>
  );
}

function ProductInfoModal({ item, onClose, onSave }) {
  const [form, setForm] = useState(() => ({
    Description: item.Description || '',
    Barcode: item.Barcode || '',
    Brand: item.Brand || '',
    Category: item.Category || '',
    'Unit Cost': item['Unit Cost'] || '',
    'Sales Price': item['Sales Price'] || '',
    Manufacturer: item.Manufacturer || '',
    'Manufacturer Website': item['Manufacturer Website'] || '',
    'Par Level': item['Par Level'] || '',
    active: Boolean(item.active),
  }));
  const [error, setError] = useState('');

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  async function save() {
    setError('');
    try {
      await onSave(item, {
        Description: form.Description,
        Barcode: form.Barcode,
        Brand: form.Brand,
        Category: form.Category,
        'Unit Cost': form['Unit Cost'],
        'Sales Price': form['Sales Price'],
        Manufacturer: form.Manufacturer,
        'Manufacturer Website': form['Manufacturer Website'],
        'Par Level': form['Par Level'],
        active: Boolean(form.active),
      });
    } catch (saveError) {
      setError(saveError.message || 'Unable to save product info.');
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Edit product info">
        <div className="modal-header"><div><h2>Edit Product Info</h2><p>{item.SKU || productTitle(item)}. Stock quantities are not edited here.</p></div><button className="icon-button modal-close" onClick={onClose} aria-label="Close edit product info" title="Close" type="button"><X size={20} /></button></div>
        <div className="form-grid">
          {['Description', 'Barcode', 'Brand', 'Category', 'Manufacturer', 'Manufacturer Website', 'Unit Cost', 'Sales Price', 'Par Level'].map((field) => (
            <label className={`field ${field === 'Description' || field === 'Manufacturer Website' ? 'wide-field' : ''}`} key={field}>
              <span>{field === 'Description' ? 'Product Title' : field}</span>
              <input value={form[field]} onChange={(event) => update(field, event.target.value)} />
            </label>
          ))}
          <label className="check-field"><input checked={form.active} onChange={(event) => update('active', event.target.checked)} type="checkbox" />Active</label>
        </div>
        {error && <div className="api-error">{error}</div>}
        <div className="detail-actions"><button className="muted-button" onClick={onClose} type="button">Cancel</button><button className="primary-button" onClick={save} type="button"><Save size={16} />Save Product Info</button></div>
      </section>
    </div></BodyPortal>
  );
}

function StockAdjustmentModal({ item, locationRows, onClose, onCommit }) {
  const mutationRef = useRef(null);
  const defaultRow = locationRows[0] || null;
  const [form, setForm] = useState({ itemLocationId: defaultRow?.id || '', newQuantity: defaultRow ? String(defaultRow.in_stock) : '', reason: '', notes: '' });
  const [error, setError] = useState('');
  const selectedRow = locationRows.find((row) => String(row.id) === String(form.itemLocationId)) || defaultRow;
  const oldQuantity = toNumber(selectedRow?.in_stock);
  const newQuantity = toNumber(form.newQuantity);
  const quantityChange = roundNumber(newQuantity - oldQuantity);
  const allocated = toNumber(selectedRow?.allocated);

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateLocation(itemLocationId) {
    const row = locationRows.find((candidate) => String(candidate.id) === String(itemLocationId));
    setForm((current) => ({ ...current, itemLocationId, newQuantity: row ? String(row.in_stock) : '' }));
  }

  async function commit() {
    setError('');
    if (!selectedRow) {
      setError('Select a location row before editing stock.');
      return;
    }
    if (form.newQuantity === '' || !Number.isFinite(Number(form.newQuantity)) || newQuantity < 0) {
      setError('Enter a valid final stock quantity of zero or more.');
      return;
    }
    if (newQuantity < allocated) {
      setError(`New stock cannot be below allocated quantity (${formatNumber(allocated)}).`);
      return;
    }
    const confirmed = window.confirm(`Commit stock adjustment for ${item.SKU || productTitle(item)}?\nOld: ${formatNumber(oldQuantity)}\nNew: ${formatNumber(newQuantity)}\nDifference: ${formatNumber(quantityChange)}`);
    if (!confirmed) {
      return;
    }
    try {
      const payload = {
        adjustment_type: quantityChange < 0 ? 'manual_decrease' : 'manual_increase',
        reason: form.reason || null,
        notes: form.notes || null,
        created_by: 'frontend',
        lines: [{ item_id: item.id, inventory_item_location_id: selectedRow.id, new_quantity: newQuantity, notes: form.notes || null }],
      };
      await onCommit(withMutationIdempotency(mutationRef, 'stock-adjustment', payload));
      resetMutationIdempotency(mutationRef);
    } catch (commitError) {
      setError(commitError.message || 'Unable to commit stock edit.');
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Edit current stock">
        <div className="modal-header"><div><h2>Edit Current Stock</h2><p>{item.SKU || productTitle(item)}. This creates an audited stock adjustment.</p></div><button className="icon-button modal-close" onClick={onClose} aria-label="Close edit current stock" title="Close" type="button"><X size={20} /></button></div>
        <div className="form-grid">
          <label className="field wide-field"><span>Location</span><select value={form.itemLocationId} onChange={(event) => updateLocation(event.target.value)}>{locationRows.map((row) => <option key={row.id} value={row.id}>{row.warehouse || 'Unassigned'} / {row.inventory_location || 'Unassigned'} · {formatNumber(row.in_stock)} in stock</option>)}</select></label>
          <label className="field"><span>Final Stock Quantity</span><input min="0" type="number" step="0.001" value={form.newQuantity} onChange={(event) => update('newQuantity', event.target.value)} /></label>
          <label className="field wide-field"><span>Reason (optional)</span><input value={form.reason} onChange={(event) => update('reason', event.target.value)} placeholder="Optional" /></label>
          <label className="field wide-field"><span>Notes</span><textarea value={form.notes} onChange={(event) => update('notes', event.target.value)} /></label>
        </div>
        <div className="summary-strip inventory-adjust-preview">
          <Metric label="Old Stock" value={formatNumber(oldQuantity)} />
          <Metric label="New Stock" value={formatNumber(newQuantity)} />
          <Metric label="Difference" value={formatNumber(quantityChange)} />
          <Metric label="Allocated" value={formatNumber(allocated)} />
        </div>
        {error && <div className="api-error">{error}</div>}
        <div className="detail-actions"><button className="muted-button" onClick={onClose} type="button">Cancel</button><button className="primary-button" onClick={commit} type="button"><Save size={16} />Commit Adjustment</button></div>
      </section>
    </div></BodyPortal>
  );
}

function ParLevelModal({ item, onClose, onSave }) {
  const [form, setForm] = useState({ 'Par Level': item['Par Level'] || '', 'Default Econ Order': item['Default Econ Order'] || '', 'Re-Order': Boolean(item['Re-Order']) });
  const [error, setError] = useState('');
  async function save() {
    setError('');
    try {
      await onSave(item, form);
    } catch (saveError) {
      setError(saveError.message || 'Unable to save par level.');
    }
  }
  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Edit par level">
        <div className="modal-header"><div><h2>Edit Par Level</h2><p>{item.SKU || productTitle(item)}. This does not change stock.</p></div><button className="icon-button modal-close" onClick={onClose} aria-label="Close edit par level" title="Close" type="button"><X size={20} /></button></div>
        <div className="form-grid">
          <label className="field"><span>Par Level</span><input value={form['Par Level']} onChange={(event) => setForm((current) => ({ ...current, 'Par Level': event.target.value }))} /></label>
          <label className="field"><span>Default Econ Order</span><input value={form['Default Econ Order']} onChange={(event) => setForm((current) => ({ ...current, 'Default Econ Order': event.target.value }))} /></label>
          <label className="check-field"><input checked={form['Re-Order']} onChange={(event) => setForm((current) => ({ ...current, 'Re-Order': event.target.checked }))} type="checkbox" />Reorder Enabled</label>
        </div>
        {error && <div className="api-error">{error}</div>}
        <div className="detail-actions"><button className="muted-button" onClick={onClose} type="button">Cancel</button><button className="primary-button" onClick={save} type="button"><Save size={16} />Save Par Level</button></div>
      </section>
    </div></BodyPortal>
  );
}

function InventorySummaryTable({ groups }) {
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>{formatNumber(groups.length)} location group(s)</span>
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
        <span>{formatNumber(locations.length)} location record(s)</span>
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
                <td className="description-cell"><ClampedText value={location.description} /></td>
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

function ItemsCommandMenu({ label, align = 'start', children }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  return (
    <div className="items-command-menu">
      <button ref={triggerRef} aria-expanded={open} className="action-button items-command-trigger" onClick={() => setOpen((current) => !current)} type="button">{label} <ChevronDown size={16} /></button>
      <FloatingMenu align={align} className="items-command-popover" closeOnAction menuRole={null} onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>{children}</FloatingMenu>
    </div>
  );
}

function ItemsList({ items, pagination = emptyItemsPagination, loading, error, onLoadItems, onRefreshItemFacets }) {
  const [mappingOpen, setMappingOpen] = useState(false);
  const [cameraScannerOpen, setCameraScannerOpen] = useState(false);
  const [selectedIds, setSelectedIds] = useState([]);
  const [visibleColumns, setVisibleColumns] = useState(ITEM_DEFAULT_VISIBLE_COLUMNS);
  const [detailId, setDetailId] = useState(null);
  const [detailData, setDetailData] = useState(null);
  const [detailTab, setDetailTab] = useState('overview');
  const [importingNew, setImportingNew] = useState(false);
  const [importError, setImportError] = useState('');
  const [setupItemIds, setSetupItemIds] = useState([]);
  const [setupIndex, setSetupIndex] = useState(0);
  const [savedViews, setSavedViews] = useState([]);
  const [selectedViewId, setSelectedViewId] = useState('');
  const [viewName, setViewName] = useState('');
  const [message, setMessage] = useState('');
  const [bulkOpen, setBulkOpen] = useState(false);
  const [remapOpen, setRemapOpen] = useState(false);
  const [dataQuality, setDataQuality] = useState(null);
  const [filters, setFilters] = useState({
    search: '',
    category: '',
    brand: '',
    status: 'active',
    stockStatus: '',
    latestWooImport: false,
    dataQuality: '',
    includeNonInventory: true,
  });
  const [searchDraft, setSearchDraft] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  const options = useMemo(
    () => ({
      categories: pagination.facets?.categories?.length ? pagination.facets.categories : uniqueOptions(items, 'Category'),
      brands: pagination.facets?.brands?.length ? pagination.facets.brands : uniqueOptions(items, 'Brand'),
    }),
    [items, pagination.facets],
  );

  useEffect(() => {
    setSelectedIds([]);
    onLoadItems({ ...filters, page, pageSize });
  }, [filters, page, pageSize]);

  useEffect(() => {
    setSearchDraft(filters.search);
  }, [filters.search]);

  useEffect(() => {
    const visibleIds = new Set(items.map((item) => item.id));
    setSelectedIds((current) => current.filter((itemId) => visibleIds.has(itemId)));
    setBulkOpen(false);
  }, [items]);

  useEffect(() => {
    loadSavedViews();
    loadDataQuality();
  }, []);

  const displayedItems = items;

  function updateFilter(name, value) {
    setSelectedIds([]);
    setBulkOpen(false);
    setPage(1);
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function searchScannedCode(value) {
    const scannedValue = value.trim();
    setSearchDraft(scannedValue);
    setMessage(`Searching for scanned code ${scannedValue.slice(0, 80)}.`);
    updateFilter('search', scannedValue);
  }

  function clearFilters() {
    setSearchDraft('');
    setSelectedIds([]);
    setBulkOpen(false);
    setPage(1);
    setFilters({
      search: '',
      category: '',
      brand: '',
      status: 'active',
      stockStatus: '',
      latestWooImport: false,
      dataQuality: '',
      includeNonInventory: true,
    });
  }

  async function loadDataQuality() {
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/items/data-quality?active=true`);
      if (response.ok) setDataQuality(await response.json());
    } catch {
      setDataQuality(null);
    }
  }

  async function loadSavedViews() {
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/ui/saved-views?page=items`);
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
    const nextFilters = { ...filters, ...(view.filters || {}) };
    setSelectedIds([]);
    setBulkOpen(false);
    setPage(1);
    setSearchDraft(nextFilters.search || '');
    setFilters(nextFilters);
    setVisibleColumns((view.columns?.length ? view.columns : visibleColumns).map((column) => (column === 'Description' ? 'Product Title' : column)));
    setMessage(`Loaded ${view.name}.`);
  }

  async function deleteView(viewId) {
    const response = await apiFetch(`${API_BASE_URL}/api/ui/saved-views/${viewId}`, { method: 'DELETE' });
    if (response.ok) {
      setMessage('Deleted saved view.');
      setSelectedViewId('');
      await loadSavedViews();
    }
  }

  async function openDetail(itemId, nextTab = 'overview') {
    setDetailId(itemId);
    setDetailData(null);
    setDetailTab(nextTab);
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/items/${itemId}/detail`);
      if (!response.ok) throw new Error(`Detail API returned ${response.status}`);
      setDetailData(await response.json());
    } catch {
      setMessage('Unable to load item detail.');
    }
  }

  async function importNewProducts() {
    setImportingNew(true);
    setImportError('');
    setMessage('');
    try {
      const result = await postJson('/api/integrations/woocommerce/products/import-new', {});
      setMessage(result.message);
      await onRefreshItemFacets();
      await onLoadItems({ ...filters, page, pageSize });
      const itemIds = result.setup_item_ids || [];
      setSetupItemIds(itemIds);
      setSetupIndex(0);
      if (itemIds.length) await openDetail(itemIds[0], 'edit');
    } catch (apiError) {
      setImportError(apiError.message || 'Unable to import new WooCommerce products.');
    } finally {
      setImportingNew(false);
    }
  }

  async function finishImportedItemSetup() {
    await onRefreshItemFacets();
    await onLoadItems({ ...filters, page, pageSize });
    const nextIndex = setupIndex + 1;
    if (nextIndex < setupItemIds.length) {
      setSetupIndex(nextIndex);
      await openDetail(setupItemIds[nextIndex], 'edit');
    } else {
      setSetupItemIds([]);
      setSetupIndex(0);
      setMessage('New WooCommerce products are imported and ready in Pongo.');
      await openDetail(detailId, 'overview');
    }
  }

  function toggleSelected(itemId) {
    if (loading) return;
    setSelectedIds((current) => (current.includes(itemId) ? current.filter((id) => id !== itemId) : [...current, itemId]));
  }

  function toggleAllDisplayed(checked) {
    if (loading) return;
    setSelectedIds(checked ? displayedItems.map((item) => item.id) : []);
  }

  function changeItemsPage(nextPage) {
    setSelectedIds([]);
    setBulkOpen(false);
    setPage(nextPage);
  }

  function changeItemsPageSize(nextPageSize) {
    setSelectedIds([]);
    setBulkOpen(false);
    setPageSize(nextPageSize);
    setPage(1);
  }

  function toggleColumn(column) {
    setVisibleColumns((current) => (current.includes(column) ? current.filter((item) => item !== column) : [...current, column]));
  }

  async function finishBulkEdit(result) {
    setMessage(`Updated ${result.updated_count} item(s).`);
    setSelectedIds([]);
    await onRefreshItemFacets();
    await onLoadItems({ ...filters, page, pageSize });
  }

  const filtersChanged = Boolean(filters.search || filters.category || filters.brand || filters.stockStatus || filters.latestWooImport || filters.dataQuality || filters.status !== 'active' || !filters.includeNonInventory);
  const topQualityIssues = (dataQuality?.issues || []).filter((issue) => issue.count > 0).sort((left, right) => right.count - left.count).slice(0, 5);
  const selectedQualityIssue = (dataQuality?.issues || []).find((issue) => issue.key === filters.dataQuality);
  const csvRepairableQualityIssue = ['missing_title', 'missing_barcode', 'missing_brand', 'missing_category', 'missing_cost'].includes(selectedQualityIssue?.key) ? selectedQualityIssue : null;

  return (
    <section className="content-panel items-page-pro">
      <div className="items-command-bar">
        <div className="items-command-header">
          <div>
            <h2>Item catalog</h2>
            <p>{formatNumber(pagination.total)} matching item(s) · {formatNumber(selectedIds.length)} selected</p>
          </div>
          <div className="button-row items-actions">
            <a className="primary-button" href="#/items/new"><Plus size={17} /> Add item</a>
            <button aria-busy={importingNew} className="action-button items-import-new-button" disabled={importingNew} onClick={importNewProducts} type="button"><PackagePlus size={17} /> {importingNew ? 'Checking WooCommerce…' : 'Import new products'}</button>
            <a className="action-button items-import-button" href="#/items/import"><Upload size={17} /> Import items</a>
            <a className="action-button" href="#/items/import?outcome=update_stock"><RefreshCw size={17} /> Update stock CSV</a>
            <ItemsCommandMenu label="Export">
                <button onClick={() => exportItemsCsv(filters)} type="button"><Download size={16} /><span><strong>Current view</strong><small>Export the current filters</small></span></button>
                <button onClick={() => exportItemsCsv({})} type="button"><Download size={16} /><span><strong>All items</strong><small>Export the complete item list</small></span></button>
                <a href={`${API_BASE_URL}/api/items/import/templates/update_items?include_existing=true`}><FileSpreadsheet size={16} /><span><strong>Editable item details</strong><small>Update existing metadata</small></span></a>
                <a href={`${API_BASE_URL}/api/items/import/templates/add_items`}><FileSpreadsheet size={16} /><span><strong>New-item template</strong><small>Start a clean add-items file</small></span></a>
            </ItemsCommandMenu>
            <ItemsCommandMenu align="end" label="More">
                <button onClick={() => { onLoadItems({ ...filters, page, pageSize }); loadDataQuality(); }} type="button"><RefreshCw size={16} /><span><strong>Refresh items</strong><small>Reload items and quality checks</small></span></button>
                <a href="#/items/imports"><History size={16} /><span><strong>Import history</strong><small>Jobs, changes, and failures</small></span></a>
                <button onClick={() => setMappingOpen(true)} type="button"><Link2 size={16} /><span><strong>Sync WooCommerce catalog</strong><small>Preview storefront mappings</small></span></button>
                <button onClick={() => setRemapOpen(true)} type="button"><Link2 size={16} /><span><strong>Fix connection exceptions</strong><small>Resolve unmatched products</small></span></button>
            </ItemsCommandMenu>
            {!!selectedIds.length && <button className="action-button" disabled={loading} onClick={() => setBulkOpen(true)} type="button"><Edit3 size={17} /> Bulk edit {selectedIds.length}</button>}
            {filtersChanged && <button className="muted-button" onClick={clearFilters} type="button">Clear filters</button>}
          </div>
        </div>
        <div className="items-filter-grid-pro">
          <div className="items-camera-search">
            <InventoryKeywordSearch className="field" value={searchDraft} onChange={setSearchDraft} onSearch={(search) => updateFilter('search', search)} label="SKU / Barcode / Product Title" placeholder="Search SKU, barcode, product title, or brand" />
            <button aria-label="Scan QR code or barcode with camera" className="action-button items-camera-button" onClick={() => setCameraScannerOpen(true)} type="button"><Camera aria-hidden="true" size={18} /> Scan code</button>
          </div>
          <FilterSelect label="Category" value={filters.category} options={options.categories} onChange={(value) => updateFilter('category', value)} />
          <FilterSelect label="Brand" value={filters.brand} options={options.brands} onChange={(value) => updateFilter('brand', value)} />
          <FilterSelect label="Stock Status" value={filters.stockStatus} options={['in_stock', 'out_of_stock', 'under_par', 'negative_sellable']} onChange={(value) => updateFilter('stockStatus', value)} />
          <label className="check-field" title="Show products created by the most recent WooCommerce import that added new items.">
            <input checked={filters.latestWooImport} onChange={(event) => updateFilter('latestWooImport', event.target.checked)} type="checkbox" />
            Latest Woo import
          </label>
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
      {dataQuality && (
        <div className="items-quality-card">
          <section className="items-quality-strip" aria-label="Item data quality">
            <div className="items-quality-score"><span>{dataQuality.completion_percent}%</span><div><strong>Item data completeness</strong><small>{formatNumber(dataQuality.items_needing_attention)} active item(s) need attention</small></div></div>
            <div className="items-quality-issues">{topQualityIssues.map((issue) => <button aria-pressed={filters.dataQuality === issue.key} className={filters.dataQuality === issue.key ? 'active' : ''} key={issue.key} onClick={() => updateFilter('dataQuality', filters.dataQuality === issue.key ? '' : issue.key)} title={issue.description} type="button"><strong>{formatNumber(issue.count)}</strong><span>{issue.label}</span></button>)}</div>
          </section>
          {csvRepairableQualityIssue && (
            <section className="items-quality-remediation" aria-label={`${csvRepairableQualityIssue.label} actions`}>
              <div><strong>{formatNumber(pagination.total)} item(s) in this fix list</strong><span>Export this filtered CSV, fill the missing values, then import it using “Update item details.”</span></div>
              <div className="button-row">
                <button className="action-button" onClick={() => exportItemsCsv({ ...filters, editable: true }, `pongo-items-${csvRepairableQualityIssue.key.replaceAll('_', '-')}.csv`)} type="button"><Download size={16} /> Export CSV</button>
                <a className="primary-button" href="#/items/import?outcome=update_items"><Upload size={16} /> Import completed CSV</a>
              </div>
            </section>
          )}
        </div>
      )}
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
            {['SKU / Barcode', 'Product Title', ...CANONICAL_ITEM_COLUMNS.filter((column) => !['SKU', 'Barcode', 'Description', 'Warehouse', 'Inventory Location', 'Default Location', 'On Order', 'Assembly', 'Serializable', 'Track Lot', 'Perishable', 'Storage Length', 'Storage Width', 'Storage Height', 'Storage Volume'].includes(column))].map((column) => (
              <label className="check-field compact-check" key={column}>
                <input checked={visibleColumns.includes(column)} onChange={() => toggleColumn(column)} type="checkbox" />
                {column}
              </label>
            ))}
          </div>
        </details>
      </div>
      {error && <div className="api-error">{error}</div>}
      {importError && <div className="api-error">{importError}</div>}
      {message && <div className="api-success">{message}</div>}
      {loading && <div className="loading-strip">Loading backend items...</div>}
      <ItemsTable items={displayedItems} loading={loading} pagination={{ page: pagination.page, pageSize: pagination.page_size, total: pagination.total, totalPages: pagination.total_pages, returnedCount: displayedItems.length, noun: 'items', onPageChange: changeItemsPage, onPageSizeChange: changeItemsPageSize }} visibleColumns={visibleColumns} selectedIds={selectedIds} onToggleSelected={toggleSelected} onToggleAll={toggleAllDisplayed} onOpenDetail={openDetail} />
      {mappingOpen && <ImportMappingsModal onClose={() => setMappingOpen(false)} onImported={async () => { await onRefreshItemFacets(); await onLoadItems({ ...filters, page, pageSize }); }} />}
      {detailId && <ItemDetailDrawer detail={detailData} tab={detailTab} setTab={setDetailTab} onClose={() => { setDetailId(null); setSetupItemIds([]); setSetupIndex(0); }} onRefresh={() => openDetail(detailId, detailTab)} onRefreshItemFacets={onRefreshItemFacets} onSetupSaved={setupItemIds.length ? finishImportedItemSetup : null} setupProgress={setupItemIds.length ? { current: setupIndex + 1, total: setupItemIds.length } : null} />}
      {bulkOpen && <BulkEditModal selectedIds={selectedIds} onCommitted={finishBulkEdit} onClose={() => setBulkOpen(false)} />}
      {remapOpen && <LocalRemapSearchModal onClose={() => setRemapOpen(false)} />}
      <MobileCodeScanner open={cameraScannerOpen} onClose={() => setCameraScannerOpen(false)} onDetected={searchScannedCode} />
    </section>
  );
}

function ImportMappingsModal({ onClose, onImported }) {
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function loadPreview() {
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      setPreview(await runWooCatalogBatchesRequest('/api/integrations/woocommerce/products/preview'));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview WooCommerce mappings.');
    } finally {
      setLoading(false);
    }
  }

  async function commitMappings() {
    if (!preview || !window.confirm('Import valid WooCommerce mappings now? This updates only local mapping and Woo-owned reference fields. It does not write to WooCommerce or change local stock.')) return;
    setLoading(true);
    setError('');
    try {
      const result = await runWooCatalogBatchesRequest('/api/integrations/woocommerce/products/commit', preview.duplicate_skus || []);
      setSummary(result);
      await onImported();
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit WooCommerce mappings.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal mapping-import-modal" role="dialog" aria-modal="true" aria-label="Import WooCommerce mappings">
        <div className="modal-header">
          <div><h2>WooCommerce connections</h2><p>One local stock item per simple product or purchasable variation. Variable parents stay informational.</p></div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close WooCommerce connections" type="button"><X size={20} /></button>
        </div>
        <div className="import-steps">
          <section className="import-step mapping-workflow-intro">
            <div><strong>Preview first</strong><p>WooCommerce is read only during this workflow. Local operational stock, costs, barcodes, brands, and locations are preserved.</p></div>
            <div className="button-row"><button className="primary-button" disabled={loading} onClick={loadPreview} type="button"><Search size={17} />{preview ? 'Refresh Preview' : 'Start Import Preview'}</button><button className="action-button" disabled={loading || !preview} onClick={commitMappings} type="button"><Link2 size={17} />Commit Valid Mappings</button></div>
          </section>
          {preview && <WooMappingPreview preview={preview} />}
          {summary && <div className="api-success">Import completed: {summary.created_count} created, {summary.updated_count} updated, {summary.unchanged_count} unchanged, {summary.conflict_count} conflict(s), {summary.error_count} error(s).</div>}
          {loading && <div className="loading-strip">Reading the WooCommerce catalog in batches...</div>}
          {error && <div className="api-error">{error}</div>}
        </div>
      </section>
    </div></BodyPortal>
  );
}

function WooMappingPreview({ preview }) {
  const metrics = [
    ['Examined', preview.total_remote_records], ['Simple', preview.simple_products_examined], ['Variable parents', preview.variable_parents_examined], ['Variations', preview.purchasable_variations_examined], ['New simple', preview.new_simple_count], ['New variations', preview.new_variation_count], ['Updates', preview.update_count], ['Unchanged', preview.unchanged_count], ['Parents skipped', preview.skipped_parent_count], ['Missing SKU', preview.missing_sku_count], ['SKU conflicts', preview.duplicate_sku_conflict_count], ['Mapping conflicts', preview.duplicate_mapping_conflict_count], ['Invalid', preview.invalid_count],
  ];
  return (
    <section className="import-step">
      <h3>Catalog mapping preview</h3>
      <div className="import-metrics mapping-metrics">{metrics.map(([label, value]) => <Metric key={label} label={label} value={value || 0} />)}</div>
      {preview.errors?.length > 0 && <div className="api-error">{preview.errors.slice(0, 12).join(' ')}</div>}
      <div className="preview-table-wrap">
        <table className="preview-table mapping-preview-table">
          <thead><tr><th>Product</th><th>Parent</th><th>Variation</th><th>SKU</th><th>Woo Product</th><th>Variation ID</th><th>Current Mapping</th><th>Proposed Item</th><th>Action</th><th>Warnings / Errors</th></tr></thead>
          <tbody>
            {(preview.preview_rows || []).map((row, index) => (
              <tr key={`${row.woo_product_id}-${row.woo_variation_id || 'parent'}-${index}`}>
                <td><ClampedText value={row.product_name || row.description} /></td><td><ClampedText value={row.parent_product_name || ''} /></td><td>{formatVariationAttributes(row.variation_attributes)}</td><td className="mono">{row.sku}</td><td className="mono">{row.woo_product_id}</td><td className="mono">{row.woo_variation_id}</td><td>{row.current_mapping ? `Mapped item ${row.current_mapping.item_id}` : 'Unmapped'}</td><td><ClampedText value={row.proposed_item?.description || ''} /></td><td><Badge tone={row.action === 'conflict' || row.action === 'error' ? 'danger' : row.action === 'skip' ? 'neutral' : 'success'}>{row.action}</Badge></td><td className="description-cell">{[...(row.warnings || []), ...(row.errors || [])].join(' ')}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function formatVariationAttributes(attributes = []) {
  return attributes.map((attribute) => `${attribute.name || attribute.slug || 'Option'}: ${attribute.option || (attribute.options || []).join(', ')}`).join(' · ');
}

function ImportModal({ onClose, onImported }) {
  const [mode, setMode] = useState('standard');
  const [importOpeningStock, setImportOpeningStock] = useState(false);
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
      const path = mode === 'enrichment' ? '/api/items/enrichment/preview' : '/api/items/import/preview';
      const result = await uploadImportFile(path, file, mode === 'enrichment' ? { import_opening_stock: importOpeningStock } : {});
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
      const path = mode === 'enrichment' ? '/api/items/enrichment/commit' : '/api/items/import/commit';
      const result = await uploadImportFile(path, file, mode === 'enrichment' ? { import_opening_stock: importOpeningStock } : {});
      setSummary(result);
      await onImported();
    } catch (apiError) {
      setError(apiError.message || 'Unable to import CSV.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Import CSV">
        <div className="modal-header">
          <div>
            <h2>Import CSV</h2>
            <p>Choose a standard item import or safely enrich existing Woo-mapped items.</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close import modal" type="button">
            <X size={20} />
          </button>
        </div>
        <div className="import-steps">
          <section className="import-step">
            <h3>Import mode</h3>
            <div className="import-mode-selector">
              <button className={mode === 'standard' ? 'tab-button active' : 'tab-button'} onClick={() => { setMode('standard'); setPreview(null); setSummary(null); }} type="button">Standard Items Import</button>
              <button className={mode === 'enrichment' ? 'tab-button active' : 'tab-button'} onClick={() => { setMode('enrichment'); setPreview(null); setSummary(null); }} type="button">Enrich Woo-Mapped Items</button>
            </div>
            {mode === 'enrichment' && <div className="csv-note">Updates existing mapped items only. Protected Pongo/Woo IDs, mapping type, and mapping status are validated and cannot be changed. Empty cells preserve current values; <code>__CLEAR__</code> is limited to safe local fields.</div>}
          </section>
          <section className="import-step">
            <h3>1. Upload CSV</h3>
            <p>{mode === 'enrichment' ? 'Use the dedicated Export Enrichment Template from Items. Do not match spreadsheets by row position.' : 'Import expects the canonical item CSV header. Extra columns are ignored and reported as warnings.'}</p>
            <input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setSummary(null); setError(''); }} />
            {mode === 'standard' && <button className="muted-button" onClick={downloadSampleCsv} type="button">
              <Download size={17} />
              Download Sample CSV
            </button>}
            {mode === 'enrichment' && <button className="muted-button" onClick={exportEnrichmentCsv} type="button"><Download size={17} />Export Enrichment Template</button>}
            {mode === 'enrichment' && <label className="opening-stock-control"><input checked={importOpeningStock} onChange={(event) => { setImportOpeningStock(event.target.checked); setPreview(null); setSummary(null); }} type="checkbox" /><span><strong>Import opening stock</strong><small>Off by default. Enable only for the first clean migration; valid warehouse/location and no prior stock history are required.</small></span></label>}
          </section>
          <section className="import-step">
            <h3>2. Preview</h3>
            <button className="primary-button" disabled={loading || !file} onClick={previewImport} type="button">
              Preview CSV
            </button>
            {preview && <ImportPreview preview={preview} mode={mode} />}
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
    </div></BodyPortal>
  );
}

function ImportPreview({ preview, mode = 'standard' }) {
  return (
    <div className="import-results">
      <div className="import-metrics">
        <Metric label="Total" value={preview.total_rows} />
        <Metric label="Valid" value={preview.valid_rows} />
        <Metric label="Invalid" value={preview.invalid_rows} />
        <Metric label="Create" value={preview.create_count} />
        <Metric label="Update" value={preview.update_count} />
        {mode === 'enrichment' && <Metric label="Unchanged" value={preview.unchanged_count} />}
        {mode === 'enrichment' && <Metric label="Conflicts" value={preview.conflict_count} />}
        {mode === 'enrichment' && <Metric label="Unmatched" value={preview.unmatched_count} />}
      </div>
      {preview.warnings?.length > 0 && (
        <div className="warning-list">
          {preview.warnings.slice(0, 8).map((warning) => (
            <div key={warning}>{warning}</div>
          ))}
        </div>
      )}
      <ImportErrors errors={preview.errors} />
      {mode === 'enrichment' && <div className="button-row compact"><button className="muted-button" disabled={!preview.conflict_count} onClick={() => downloadPreviewRows(preview.preview_rows, ['conflict'], 'pongo-enrichment-conflicts.csv')} type="button"><Download size={15} />Download Conflicts</button><button className="muted-button" disabled={!preview.unmatched_count} onClick={() => downloadPreviewRows(preview.preview_rows, ['unmatched'], 'pongo-enrichment-unmatched.csv')} type="button"><Download size={15} />Download Unmatched</button><button className="muted-button" disabled={!preview.invalid_rows} onClick={() => downloadPreviewRows(preview.preview_rows, ['conflict', 'unmatched', 'invalid'], 'pongo-enrichment-failed.csv')} type="button"><Download size={15} />Download Failed</button></div>}
      <div className="preview-table-wrap">
        <table className="preview-table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Action</th>
              <th>SKU</th>
              <th>Barcode</th>
              <th>{mode === 'enrichment' ? 'Match' : 'Product Title'}</th>
              <th>{mode === 'enrichment' ? 'Fields Changing' : 'Warnings'}</th>
              {mode === 'enrichment' && <th>Warnings / Errors</th>}
            </tr>
          </thead>
          <tbody>
            {preview.preview_rows.map((row) => (
              <tr key={row.row_number}>
                <td>{row.row_number}</td>
                <td>{row.action}</td>
                <td>{row.sku}</td>
                <td>{row.barcode}</td>
                <td>{mode === 'enrichment' ? row.match_method : decodeHtmlEntities(row.row?.Description || '')}</td>
                <td>{mode === 'enrichment' ? (row.fields_changing || []).join(', ') : (row.warnings || []).join(' ')}</td>
                {mode === 'enrichment' && <td className="description-cell">{[...(row.warnings || []), ...(row.errors || [])].join(' ')}</td>}
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
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Import locations CSV">
        <div className="modal-header">
          <div>
            <h2>Import Locations CSV</h2>
            <p>Warehouse, Location Code, and Location Name are required.</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close import modal" type="button">
            <X size={20} />
          </button>
        </div>
        <div className="import-steps">
          <section className="import-step">
            <h3>1. Upload CSV</h3>
            <p>Expected columns: {CANONICAL_LOCATION_COLUMNS.join(', ')}. Extra columns are ignored and reported as warnings.</p>
            <input type="file" accept=".csv,text/csv" onChange={(event) => { setFile(event.target.files?.[0] || null); setPreview(null); setSummary(null); setError(''); }} />
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
    </div></BodyPortal>
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
                <td>{decodeHtmlEntities(row.name || '')}</td>
                <td>{row.row.Active ? 'Yes' : 'No'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Metric({ label, value, help = '' }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{typeof value === 'number' ? formatNumber(value) : value}</strong>
      {help && <small className="metric-definition">{help}</small>}
    </div>
  );
}

function FilterSelect({ label, value, options, onChange, disabled = false }) {
  return (
    <label className="field">
      <span>{label}</span>
      <div className="select-shell">
        <select disabled={disabled} value={value} onChange={(event) => onChange(event.target.value)}>
          <option value="">All {label}</option>
          {options.map((option) => (
            <option key={option} value={option}>
              {decodeHtmlEntities(String(option))}
            </option>
          ))}
        </select>
        <Filter size={18} />
      </div>
    </label>
  );
}

function ItemsTable({ items, loading = false, pagination, visibleColumns, selectedIds, onToggleSelected, onToggleAll, onOpenDetail }) {
  const allSelected = items.length > 0 && items.every((item) => selectedIds.includes(item.id));
  return (
    <div className="table-wrap">
      <div className="table-meta">
        <span>{formatNumber(pagination?.total ?? items.length)} matching item(s)</span>
        <TablePager pagination={pagination} />
      </div>
      <div className="table-action-band">
        <span>Actions</span>
        <ChevronDown size={18} />
      </div>
      <div className="table-scroll items-table-scroll">
        <table className="items-data-table">
          <thead>
            <tr>
              <th className="sticky-col sticky-action-col"><input aria-label="Select all visible items" checked={allSelected} disabled={loading} onChange={(event) => onToggleAll(event.target.checked)} type="checkbox" /></th>
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
                  <input aria-label={`Select ${item.SKU || productTitle(item) || 'item'}`} checked={selectedIds.includes(item.id)} disabled={loading} onChange={() => onToggleSelected(item.id)} type="checkbox" />
                </td>
                <td className="sticky-col sticky-image-col">
                  <button className="image-cell image-button" onClick={() => onOpenDetail(item.id)} type="button">
                    {item.imageUrl ? <img alt="" src={item.imageUrl} loading="lazy" decoding="async" /> : 'No Image'}
                  </button>
                </td>
                {visibleColumns.map((column) => (
                  <td key={`${item.id}-${column}`} className={column === 'Product Title' ? 'description-cell' : ''}>
                    {column === 'SKU / Barcode' ? (
                      <button className="table-link-button sku-barcode-cell" onClick={() => onOpenDetail(item.id)} type="button">
                        <strong>{item.SKU || 'No SKU'}</strong>
                        <span>{item.Barcode || 'No barcode'}</span>
                      </button>
                    ) : column === 'SKU' || column === 'Product Title' ? (
                      <button className="table-link-button" onClick={() => onOpenDetail(item.id)} type="button">{column === 'Product Title' ? productTitle(item) || 'Open' : formatCell(item[column], column) || 'Open'}</button>
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

function ItemDetailDrawer({ detail, tab, setTab, onClose, onRefresh, onRefreshItemFacets, onSetupSaved, setupProgress }) {
  const item = detail?.item;
  const tabs = ['overview', 'stock', 'activity', 'history', 'edit'];
  return (
    <BodyPortal><div className="drawer-backdrop" role="presentation">
      <aside className="detail-drawer" role="dialog" aria-modal="true" aria-label="Item detail">
        <div className="modal-header">
          <div>
            <h2>{item?.sku || 'Item Detail'}</h2>
            <p>{item ? productTitle(item) || 'Item control center' : 'Loading item control center...'}</p>
          </div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close item detail" type="button"><X size={20} /></button>
        </div>
        {!detail && <div className="loading-strip">Loading item detail...</div>}
        {detail && (
          <>
            {setupProgress && <div className="woo-import-setup-banner"><strong>Set up imported product {setupProgress.current} of {setupProgress.total}</strong><span>SKU and barcode are required. Location, opening stock, cost, brand, and description are optional.</span></div>}
            <div className="tab-row">
              {tabs.map((name) => <button className={tab === name ? 'tab-button active' : 'tab-button'} key={name} onClick={() => setTab(name)} type="button">{name}</button>)}
            </div>
            {tab === 'overview' && <ItemOverview detail={detail} onRefresh={onRefresh} />}
            {tab === 'stock' && <ItemStockByLocation rows={detail.stock_by_location || []} item={item} />}
            {tab === 'activity' && <ItemActivityTimeline rows={detail.recent_activity || []} />}
            {tab === 'history' && <ItemHistoryPanel itemId={item.id} />}
            {tab === 'edit' && <ItemMetadataPanel item={item} key={item.id} onSaved={onSetupSaved || onRefresh} onRefreshItemFacets={onRefreshItemFacets} setupProgress={setupProgress} />}
          </>
        )}
      </aside>
    </div></BodyPortal>
  );
}

function ItemOverview({ detail, onRefresh }) {
  const item = detail.item || {};
  const stats = detail.quick_stats || {};
  return (
    <div className="drawer-section">
      <div className="item-overview-grid">
        <div className="item-photo">{item.image_url ? <img alt="" src={item.image_url} loading="lazy" decoding="async" /> : <PackageSearch size={42} />}</div>
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
      <div className="button-row"><button className="muted-button" onClick={onRefresh} type="button"><RefreshCw size={16} />Refresh Detail</button><a className="action-button" href="#receiving">Receive</a><a className="action-button" href="#/inventory/all">Inventory</a><a className="action-button" href="#cycle-count">Cycle Count</a></div>
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
    apiFetch(`${API_BASE_URL}/api/items/${itemId}/history?section=${section}`).then((response) => response.json()).then(setHistory).catch(() => setHistory({ rows: [], total: 0 }));
  }, [itemId, section]);
  return (
    <div className="drawer-section">
      <FilterSelect label="History" value={section} options={['receipts', 'cycle-counts', 'adjustments', 'allocations', 'picks', 'fulfillments', 'orders', 'stock-movements']} onChange={setSection} />
      <ItemActivityTimeline rows={history.rows || []} />
    </div>
  );
}

function ItemMetadataPanel({ item, onSaved, onRefreshItemFacets, setupProgress }) {
  const [form, setForm] = useState({ sku: item.sku || '', barcode: item.barcode || '', description: item.description || '', category: item.category || '', brand: item.brand || '', manufacturer: item.manufacturer || '', unit_cost: item.unit_cost ?? '', sales_price: item.sales_price ?? '', warehouse: item.warehouse || '', inventory_location: item.inventory_location || '', opening_stock: '', active: item.active });
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  async function saveMetadata(event) {
    event.preventDefault();
    if (setupProgress && (!form.sku.trim() || !form.barcode.trim())) {
      setError('SKU and barcode are required.');
      return;
    }
    if (form.opening_stock !== '' && (!form.warehouse.trim() || !form.inventory_location.trim())) {
      setError('Choose a warehouse and location before adding opening stock.');
      return;
    }
    const payload = {
      SKU: form.sku.trim(),
      Barcode: form.barcode.trim(),
      Description: form.description,
      Category: form.category,
      Brand: form.brand,
      Manufacturer: form.manufacturer,
      'Unit Cost': form.unit_cost === '' ? null : Number(form.unit_cost),
      'Sales Price': form.sales_price === '' ? null : Number(form.sales_price),
      Warehouse: form.warehouse,
      'Inventory Location': form.inventory_location,
      'Default Location': form.inventory_location,
      active: Boolean(form.active),
    };
    setSaving(true);
    setError('');
    setMessage('');
    try {
      const saved = await patchJson(`/api/items/${item.id}`, payload);
      if (form.opening_stock !== '') {
        await postJson(`/api/items/${item.id}/opening-balance`, {
          'In Stock': Number(form.opening_stock),
          Allocated: 0,
          Warehouse: form.warehouse.trim(),
          'Inventory Location': form.inventory_location.trim(),
          idempotencyKey: `woo-import-opening-${item.id}`,
        });
      }
      await onRefreshItemFacets();
      setMessage(saved.wooSyncStatus === 'pending_writeback' ? 'Saved in Pongo. WooCommerce writeback is pending.' : 'Product saved.');
      await onSaved();
    } catch (apiError) {
      setError(apiError.message || 'Unable to save this product.');
    } finally {
      setSaving(false);
    }
  }
  return (
    <form className="drawer-section operation-grid" onSubmit={saveMetadata}>
      <label className="field"><span>SKU {setupProgress ? '(required)' : ''}</span><input disabled={item.sku_locked} required={Boolean(setupProgress)} value={form.sku} onChange={(event) => setForm((current) => ({ ...current, sku: event.target.value }))} />{item.sku_locked && <small>Locked because stock activity has started.</small>}</label>
      <label className="field"><span>Barcode {setupProgress ? '(required)' : ''}</span><input required={Boolean(setupProgress)} value={form.barcode} onChange={(event) => setForm((current) => ({ ...current, barcode: event.target.value }))} /></label>
      <label className="field operation-grid-wide"><span>Description</span><textarea rows={3} value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} /></label>
      {['category', 'brand', 'manufacturer'].map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={form[field]} onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))} /></label>)}
      {['unit_cost', 'sales_price'].map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input min="0" step="0.01" type="number" value={form[field]} onChange={(event) => setForm((current) => ({ ...current, [field]: event.target.value }))} /></label>)}
      <label className="field"><span>Warehouse</span><input value={form.warehouse} onChange={(event) => setForm((current) => ({ ...current, warehouse: event.target.value }))} /></label>
      <label className="field"><span>Inventory location</span><input value={form.inventory_location} onChange={(event) => setForm((current) => ({ ...current, inventory_location: event.target.value }))} /></label>
      <label className="field"><span>Opening stock</span><input min="0" step="0.001" type="number" value={form.opening_stock} onChange={(event) => setForm((current) => ({ ...current, opening_stock: event.target.value }))} /><small>Optional and available only before stock activity starts.</small></label>
      <label className="check-field"><input checked={form.active} onChange={(event) => setForm((current) => ({ ...current, active: event.target.checked }))} type="checkbox" />Active</label>
      <button aria-busy={saving} className="primary-button" disabled={saving} type="submit"><Save size={16} />{saving ? 'Saving…' : setupProgress && setupProgress.current < setupProgress.total ? 'Save & next' : 'Save product'}</button>
      {error && <div className="api-error operation-grid-wide">{error}</div>}
      {message && <div className="api-success operation-grid-wide">{message}</div>}
    </form>
  );
}

function BulkEditModal({ selectedIds, onCommitted, onClose }) {
  const [updates, setUpdates] = useState({});
  const [preview, setPreview] = useState(null);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    apiFetch(`${API_BASE_URL}/api/locations?active=true`)
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('Unable to load locations.'))))
      .then((body) => { if (active) setLocations(body.locations || []); })
      .catch((loadError) => { if (active) setError(loadError.message || 'Unable to load locations.'); });
    return () => { active = false; };
  }, []);

  function updateField(field, value) {
    setPreview(null);
    setError('');
    setUpdates((current) => ({ ...current, [field]: value }));
  }

  function payload() {
    const next = Object.fromEntries(Object.entries(updates).filter(([, value]) => value !== '' && value !== null));
    if (next.location_id) next.location_id = Number(next.location_id);
    if (!next.location_id) delete next.make_default_location;
    return next;
  }

  async function previewChanges() {
    const changes = payload();
    if (!Object.keys(changes).length) {
      setError('Choose at least one field to update.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      setPreview(await postJson('/api/items/bulk/preview', { item_ids: selectedIds, updates: changes }));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview the bulk edit.');
    } finally {
      setLoading(false);
    }
  }

  async function commitChanges() {
    if (!preview?.can_commit) return;
    setLoading(true);
    setError('');
    try {
      const result = await postJson('/api/items/bulk/commit', { item_ids: selectedIds, updates: payload() });
      await onCommitted(result);
      onClose();
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit the bulk edit.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop bulk-edit-backdrop" role="presentation">
      <section className="import-modal bulk-edit-modal" role="dialog" aria-modal="true" aria-labelledby="bulk-edit-title">
        <div className="modal-header">
          <div><h2 id="bulk-edit-title">Bulk edit inventory items</h2><p>{selectedIds.length} selected item(s). SKU, barcode, stock quantities, and WooCommerce identity stay protected.</p></div>
          <button className="icon-button modal-close" onClick={onClose} aria-label="Close bulk edit" title="Close" type="button"><X size={20} /></button>
        </div>
        <div className="bulk-edit-content">
          <section className="bulk-edit-section">
            <div className="bulk-edit-section-heading"><div><span>LOCATION</span><h3>Add an inventory location</h3></div><small>This creates a zero-quantity location assignment. It never moves stock.</small></div>
            <div className="bulk-edit-grid">
              <label className="field bulk-edit-location-field"><span>Inventory location</span><select value={updates.location_id || ''} onChange={(event) => updateField('location_id', event.target.value)}><option value="">Do not change</option>{locations.map((location) => <option key={location.id} value={location.id}>{location.warehouse} / {location.code || location.name}</option>)}</select></label>
              <label className="check-field bulk-edit-default-check"><input checked={Boolean(updates.make_default_location)} disabled={!updates.location_id} onChange={(event) => updateField('make_default_location', event.target.checked)} type="checkbox" />Make this the default location</label>
            </div>
          </section>
          {BULK_ITEM_FIELD_GROUPS.map((group) => (
            <section className="bulk-edit-section" key={group.title}>
              <div className="bulk-edit-section-heading"><h3>{group.title}</h3></div>
              <div className="bulk-edit-grid">
                {group.fields.map((field) => (
                  <label className="field" key={field.key}>
                    <span>{field.label}</span>
                    {field.type === 'boolean' ? (
                      <select value={updates[field.key] ?? ''} onChange={(event) => updateField(field.key, event.target.value)}><option value="">Do not change</option><option value="true">Yes</option><option value="false">No</option></select>
                    ) : (
                      <input min={field.min} placeholder={field.placeholder || 'Do not change'} step={field.step} type={field.type || 'text'} value={updates[field.key] ?? ''} onChange={(event) => updateField(field.key, event.target.value)} />
                    )}
                  </label>
                ))}
              </div>
            </section>
          ))}
          {loading && <div className="loading-strip" role="status" aria-live="polite">Working with selected inventory items...</div>}
          {error && <div className="api-error" role="alert">{error}</div>}
          {preview && <div className="import-results"><div className="import-metrics"><Metric label="Items affected" value={preview.affected_count} /><Metric label="Fields changing" value={(preview.fields_to_update || []).length} /></div>{preview.warnings?.map((warning) => <div className="api-error" key={warning}>{warning}</div>)}</div>}
          <div className="detail-actions bulk-edit-actions"><button className="muted-button" disabled={loading} onClick={onClose} type="button">Cancel</button><button className="muted-button" disabled={loading} onClick={previewChanges} type="button"><Search size={16} />Preview changes</button><button className="primary-button" disabled={loading || !preview?.can_commit} onClick={commitChanges} type="button"><Save size={16} />Apply to {selectedIds.length} item(s)</button></div>
        </div>
      </section>
    </div></BodyPortal>
  );
}

function LocalRemapSearchModal({ onClose }) {
  const [remoteQuery, setRemoteQuery] = useState('');
  const [candidates, setCandidates] = useState([]);
  const [selectedRemote, setSelectedRemote] = useState(null);
  const [itemQuery, setItemQuery] = useState('');
  const [results, setResults] = useState([]);
  const [selectedItem, setSelectedItem] = useState(null);
  const [preview, setPreview] = useState(null);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => { searchRemote(''); }, []);

  async function searchRemote(value = remoteQuery) {
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/integrations/woocommerce/remap/candidates?search=${encodeURIComponent(value)}&limit=100`);
      if (!response.ok) throw new Error(`Remap candidates returned ${response.status}`);
      const body = await response.json();
      setCandidates(body.candidates || []);
    } catch (apiError) {
      setError(apiError.message || 'Unable to load remap candidates.');
    } finally {
      setLoading(false);
    }
  }

  async function searchItems() {
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/items/search?q=${encodeURIComponent(itemQuery)}&limit=20`);
      if (!response.ok) throw new Error(`Item search returned ${response.status}`);
      const body = await response.json();
      setResults(body.items || []);
    } catch (apiError) {
      setError(apiError.message || 'Unable to search local items.');
    } finally {
      setLoading(false);
    }
  }

  function remapPayload() {
    return { woo_product_id: selectedRemote.remote.woo_product_id, woo_variation_id: selectedRemote.remote.woo_variation_id ?? null, item_id: selectedItem.id };
  }

  async function previewRemap() {
    setLoading(true);
    setError('');
    setMessage('');
    try {
      setPreview(await postJson('/api/integrations/woocommerce/remap/preview', remapPayload()));
    } catch (apiError) {
      setError(apiError.message || 'Unable to preview remap.');
    } finally {
      setLoading(false);
    }
  }

  async function commitRemap() {
    if (!preview || preview.errors?.length || !window.confirm('Commit this local mapping? Stock is unchanged and no WooCommerce write is made.')) return;
    setLoading(true);
    setError('');
    try {
      const result = await postJson('/api/integrations/woocommerce/remap/commit', { ...remapPayload(), note: 'Items remap exception workflow' });
      setMessage(`${result.safe_message} ${result.reprocessed_order_lines || 0} order line(s) reprocessed.`);
      setPreview(null);
      await searchRemote(remoteQuery);
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit remap.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal" role="dialog" aria-modal="true" aria-label="Remap WooCommerce exceptions">
        <div className="modal-header"><div><h2>Fix WooCommerce connections</h2><p>Search a Woo record, select a local item, preview conflicts, then save the local connection. Stock and WooCommerce stay unchanged.</p></div><button className="icon-button modal-close" onClick={onClose} aria-label="Close WooCommerce connection fixes" title="Close" type="button"><X size={20} /></button></div>
        <div className="import-steps">
          <section className="import-step"><h3>1. Choose WooCommerce record</h3><div className="scanner-input-row"><input value={remoteQuery} onChange={(event) => setRemoteQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && searchRemote()} placeholder="Search product, variation, SKU, or Woo ID" /><button className="primary-button" onClick={() => searchRemote()} type="button"><Search size={16} />Search Woo Records</button></div>
            <TableShell caption={`${candidates.length} Woo record(s)`} columns={['Product', 'Parent / Attributes', 'SKU', 'Woo Identity', 'Stock Snapshot', 'Status', 'Action']}>
              {candidates.map((candidate) => <tr key={`${candidate.remote.woo_product_id}-${candidate.remote.woo_variation_id || 'simple'}`}><td><ClampedText value={candidate.remote.woo_name} /></td><td className="description-cell"><ClampedText value={`${candidate.remote.parent_product_name || ''} ${formatVariationAttributes(candidate.remote.variation_attributes)}`.trim()} /></td><td>{candidate.remote.woo_sku}</td><td className="mono">{candidate.remote.woo_product_id}{candidate.remote.woo_variation_id ? ` / ${candidate.remote.woo_variation_id}` : ''}</td><td>{formatNumber(candidate.remote.woo_stock_snapshot)}</td><td>{candidate.remote.mapping_status || candidate.remote.reason}</td><td><button className={selectedRemote === candidate ? 'primary-button' : 'muted-button'} onClick={() => { setSelectedRemote(candidate); setPreview(null); }} type="button">Select</button></td></tr>)}
              {!candidates.length && <tr><td colSpan={7}><div className="empty-table-row">No Woo exception records match.</div></td></tr>}
            </TableShell>
          </section>
          <section className="import-step"><h3>2. Choose local Pongo item</h3><div className="scanner-input-row"><input value={itemQuery} onChange={(event) => setItemQuery(event.target.value)} onKeyDown={(event) => event.key === 'Enter' && searchItems()} placeholder="Search SKU, barcode, product name, or brand" /><button className="primary-button" onClick={searchItems} type="button"><Search size={16} />Search Items</button></div>
            <TableShell caption={`${results.length} local candidate(s)`} columns={['SKU', 'Barcode', 'Product Title', 'Brand', 'Current Woo Mapping', 'Action']}>
              {results.map((item) => <tr key={item.id}><td>{item.sku}</td><td>{item.barcode}</td><td className="description-cell"><ClampedText value={item.description} /></td><td>{decodeHtmlEntities(item.brand || '') || <DataQualityBadge kind="missing_brand" />}</td><td>{item.woo_mapping_summary?.mapped ? `${item.woo_mapping_summary.woo_product_id || ''}/${item.woo_mapping_summary.woo_variation_id || ''}` : <DataQualityBadge kind="unmapped" />}</td><td><button className={selectedItem?.id === item.id ? 'primary-button' : 'muted-button'} onClick={() => { setSelectedItem(item); setPreview(null); }} type="button">Select</button></td></tr>)}
              {!results.length && <tr><td colSpan={6}><div className="empty-table-row">Search for a local item to continue.</div></td></tr>}
            </TableShell>
          </section>
          <section className="import-step"><h3>3. Preview and commit</h3><div className="button-row"><button className="primary-button" disabled={loading || !selectedRemote || !selectedItem} onClick={previewRemap} type="button">Preview Mapping</button><button className="action-button" disabled={loading || !preview || preview.errors?.length > 0} onClick={commitRemap} title={preview?.errors?.length ? 'Resolve preview conflicts before commit.' : ''} type="button">Commit Mapping</button></div>{preview && <div className={preview.errors?.length ? 'api-error' : 'api-success'}>{preview.errors?.length ? preview.errors.join(' ') : `Ready to map ${preview.remote.woo_sku || preview.remote.woo_name} to ${preview.item.sku || preview.item.description}.`} {(preview.warnings || []).join(' ')}</div>}</section>
          {loading && <div className="loading-strip">Loading remap data...</div>}{error && <div className="api-error">{error}</div>}{message && <div className="api-success">{message}</div>}
        </div>
      </section>
    </div></BodyPortal>
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
          <p>Clean item metadata entry. Stock quantities are controlled by receiving, counts, and adjustments.</p>
        </div>
      </div>
      <div className="detail-layout">
        <div className="detail-main">
          <FormSection title="Core Identity">
            {renderTextField('SKU', calculatedItem, updateField, { required: true })}
            {renderTextField('Barcode', calculatedItem, updateField)}
            <label className="field wide-field"><span>Product Title</span><input value={calculatedItem.Description || ''} onChange={(event) => updateField('Description', event.target.value)} /></label>
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
            <p>Do not enter stock here. Receive, count, or adjust stock from the operational workflows so every change has an audit trail.</p>
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
            <h2>Inventory Overview</h2>
            <p>Last refreshed {dashboard.generated_at ? formatDateTime(dashboard.generated_at) : 'not yet'}.</p>
          </div>
          <button className="primary-button" onClick={onRefresh} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
        </div>
        {error && <div className="api-error">{error}</div>}
        {loading && <div className="loading-strip">Loading Inventory Overview...</div>}
      </div>
      <DashboardCardSection title="Inventory Health" cards={[
        ['Items', inventory.total_items, 'Total records', PackageSearch],
        ['Active', inventory.active_items, 'Active items', CheckCircle2],
        ['Inventory Value', formatCurrency(inventory.total_inventory_value), 'Local value', Boxes],
        ['Reorder', inventory.reorder_count, 'Under par + reorder', TriangleAlert],
        ['Under Par', inventory.under_par_count, 'Needs review', TriangleAlert],
        ['Damage/Loss', formatCurrency(inventory.damage_loss_value_this_month), 'This month', TriangleAlert],
        ['Receiving', inventory.receiving_this_week, 'Last 7 days', PackagePlus],
        ['Adjustments', inventory.adjustment_count_this_week, 'Last 7 days', SlidersHorizontal],
        ['Negative Sellable', inventory.negative_sellable_count, 'Data warning', TriangleAlert],
        ['Missing SKU', inventory.missing_sku_count, 'Match risk', Search],
      ]} />
      <DashboardCardSection title="Order Operations" cards={[
        ['Open', orders.open_orders_count, 'Local open orders', ShoppingCart],
        ['Allocated', orders.allocated_orders_count, 'Fully allocated', ClipboardList],
        ['Part Allocated', orders.partially_allocated_orders_count, 'Partial reservations', ClipboardList],
        ['Picked', orders.picked_orders_count, 'Ready to complete', ClipboardCheck],
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
              <td className="description-cell"><ClampedText value={warning.description} /></td>
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
            ['Allocate', '#/orders/allocate'],
            ['Pick Orders', '#/orders/pick'],
            ['Completed Orders', '#/orders/completed'],
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

function CycleCountPage({ items, locations, cycleCounts, cycleCountsPagination = emptyServerPagination(50), cycleCountsLoading, cycleCountsError, onLoadCycleCounts, onLoadInventorySummary }) {
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
      lines: current.lines.map((line, lineIndex) => {
        if (lineIndex !== index) return line;
        const nextLine = { ...line, [field]: value };
        if (field === 'query' && !operationalItemMatchesQuery(line.selected_item, value)) nextLine.selected_item = null;
        return nextLine;
      }),
    }));
    setPreview(null);
    setSummary(null);
  }

  function selectLineItem(index, item) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => (lineIndex === index ? { ...line, selected_item: item } : line)),
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
      const response = await apiFetch(`${API_BASE_URL}/api/cycle-counts/${cycleCountId}`);
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
                <th>Product Title</th>
                <th>System Qty</th>
                <th>Counted Quantity</th>
                <th>Notes</th>
                <th>Remove</th>
              </tr>
            </thead>
            <tbody>
              {form.lines.map((line, index) => {
                const item = line.selected_item || findReceivingItem(items, line.query);
                return (
                  <tr key={line.localId}>
                    <td>
                      <InventoryKeywordSearch
                        className="operational-item-lookup"
                        hideLabel
                        label={`Cycle count line ${index + 1} SKU, barcode, or product`}
                        onChange={(value) => updateLine(index, 'query', value)}
                        onSelect={(selectedItem) => selectLineItem(index, selectedItem)}
                        placeholder="Scan or search SKU/barcode/product"
                        value={line.query}
                      />
                    </td>
                    <td className="description-cell"><ClampedText value={productTitle(item)} /></td>
                    <td>{item ? formatNumber(operationalItemStock(item)) : ''}</td>
                    <td>
                      <input aria-label={`Cycle count line ${index + 1} counted quantity`} value={line.counted_quantity} onChange={(event) => updateLine(index, 'counted_quantity', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input aria-label={`Cycle count line ${index + 1} notes`} value={line.notes} onChange={(event) => updateLine(index, 'notes', event.target.value)} />
                    </td>
                    <td>
                      <button className="pager-button" onClick={() => removeLine(index)} disabled={form.lines.length === 1} type="button">
                        <X size={17} />
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
        <CycleCountHistoryTable counts={cycleCounts} pagination={cycleCountsPagination} onLoad={onLoadCycleCounts} onLoadDetail={loadDetail} />
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
              <th>Product Title</th>
              <th>Location</th>
              <th>System Qty</th>
              <th>Counted Qty</th>
              <th>Variance</th>
              <th>Variance Value</th>
            </tr>
          </thead>
          <tbody>
            {(preview.preview_lines || []).map((line) => (
              <tr key={line.line_number}>
                <td>{line.line_number}</td>
                <td>{StatusText(line.status)}</td>
                <td>{line.sku}</td>
                <td className="description-cell"><ClampedText value={line.description} /></td>
                <td><LocationPresentation value={line.inventory_location} /></td>
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

function CycleCountHistoryTable({ counts, pagination, onLoad, onLoadDetail }) {
  return (
    <TableShell
      caption={`${pagination.total} cycle count(s)`}
      columns={['Count Number', 'Status', 'Warehouse', 'Inventory Location', 'Count Type', 'Total Lines', 'Adjustment Lines', 'Created At', 'Posted At', 'Created By', 'Export']}
      pagination={serverTablePagination(
        pagination,
        'cycle counts',
        (page) => onLoad({ page, page_size: pagination.page_size }),
        (pageSize) => onLoad({ page: 1, page_size: pageSize }),
      )}
    >
      {counts.map((count) => (
        <tr key={count.id}>
          <td>
            <button className="link-button mono" onClick={() => onLoadDetail(count.id)} type="button">
              {count.count_number}
            </button>
          </td>
          <td>{StatusText(count.status)}</td>
          <td>{count.warehouse}</td>
          <td><LocationPresentation value={count.inventory_location} /></td>
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
      <TableShell caption={`${detail.lines.length} counted line(s)`} columns={['SKU', 'Barcode', 'Product Title', 'Warehouse', 'Inventory Location', 'System Quantity', 'Counted Quantity', 'Variance Quantity', 'Unit Cost', 'Variance Value', 'Notes']}>
        {detail.lines.map((line) => (
          <tr key={line.id}>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell"><ClampedText value={line.description} /></td>
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

function DirectReceivingPage({ route, items, locations, receipts, receiptsPagination = emptyServerPagination(), receiptsLoading, receiptsError, onLoadReceipts, stockMovements, stockMovementsPagination = emptyServerPagination(), stockMovementsLoading, stockMovementsError, onLoadStockMovements, onLoadInventorySummary }) {
  const mutationRef = useRef(null);
  const mode = route.receivingView || 'direct';
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
  const commitReason = receivingCommitReason(form, preview, loading);
  const hasSelectedLine = form.lines.some((line) => String(line.query || '').trim());
  const currentStep = summary ? 4 : preview?.invalid_lines === 0 ? 3 : hasSelectedLine ? 2 : 1;
  const receivingSteps = ['Create Receipt', 'Select Items', 'Accept Delivery'];

  function updateHeader(field, value) {
    setForm((current) => ({ ...current, [field]: value }));
    setPreview(null);
    setSummary(null);
  }

  function updateLine(index, field, value) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => {
        if (lineIndex !== index) return line;
        const nextLine = { ...line, [field]: value };
        if (field === 'query' && !operationalItemMatchesQuery(line.selected_item, value)) nextLine.selected_item = null;
        return nextLine;
      }),
    }));
    setPreview(null);
    setSummary(null);
  }

  function selectLineItem(index, item) {
    setForm((current) => ({
      ...current,
      lines: current.lines.map((line, lineIndex) => (lineIndex === index ? { ...line, selected_item: item } : line)),
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
    resetMutationIdempotency(mutationRef);
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
      const payload = receivingPayload(form, items);
      const result = await postJson('/api/receipts/direct/commit', withMutationIdempotency(mutationRef, 'direct-receipt', payload));
      setSummary(result);
      await Promise.all([
        onLoadStockMovements({ movement_type: 'receive_direct', page: 1, page_size: stockMovementsPagination.page_size || 20 }),
        onLoadInventorySummary(),
      ]);
      setForm({ warehouse: 'Main Warehouse', reference_number: '', notes: '', lines: [emptyReceivingLine()] });
      setPreview(null);
      resetMutationIdempotency(mutationRef);
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit receiving.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="content-panel receiving-page">
      <nav className="tab-row" aria-label="Receiving modes">
        <a className={mode === 'direct' ? 'tab-button active' : 'tab-button'} href="#/receiving/direct" aria-current={mode === 'direct' ? 'page' : undefined}>Direct Receiving</a>
        <a className={mode === 'bulk' ? 'tab-button active' : 'tab-button'} href="#/receiving/bulk" aria-current={mode === 'bulk' ? 'page' : undefined}>Bulk Receiving Session</a>
        <a className={mode === 'history' ? 'tab-button active' : 'tab-button'} href="#/receiving/history" aria-current={mode === 'history' ? 'page' : undefined}>Receipt History</a>
      </nav>
      {mode === 'direct' && <div className="receiving-form">
        <ol className="receiving-stepper" aria-label="Direct receiving progress">
          {receivingSteps.map((label, index) => {
            const step = index + 1;
            const state = currentStep > receivingSteps.length ? 'complete' : step < currentStep ? 'complete' : step === currentStep ? (preview?.invalid_lines > 0 ? 'error' : 'current') : 'upcoming';
            return <li className="receiving-step" data-state={state} aria-current={state === 'current' || state === 'error' ? 'step' : undefined} key={label}><span className="receiving-step-marker">{state === 'complete' ? '✓' : step}</span><span>{label}</span></li>;
          })}
        </ol>
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
                <th>Product Title</th>
                <th>Inventory Location</th>
                <th>Quantity Received</th>
                <th>Unit Cost</th>
                <th>Notes</th>
                <th>Remove</th>
              </tr>
            </thead>
            <tbody>
              {form.lines.map((line, index) => {
                const item = line.selected_item || findReceivingItem(items, line.query);
                return (
                  <tr key={line.localId}>
                    <td>
                      <InventoryKeywordSearch
                        className="operational-item-lookup"
                        hideLabel
                        label={`Line ${index + 1} SKU or barcode`}
                        onChange={(value) => updateLine(index, 'query', value)}
                        onSelect={(selectedItem) => selectLineItem(index, selectedItem)}
                        placeholder="Scan or search SKU/barcode/product"
                        value={line.query}
                      />
                    </td>
                    <td className="description-cell"><ClampedText value={productTitle(item)} /></td>
                    <td>
                      <select aria-label={`Line ${index + 1} inventory location`} value={line.inventory_location} onChange={(event) => updateLine(index, 'inventory_location', event.target.value)}>
                        <option value="">Select location</option>
                        {locationOptions.map((location) => (
                          <option key={location.id} value={location.code}>
                            {location.warehouse} / {location.code}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input aria-label={`Line ${index + 1} quantity received`} value={line.quantity_received} onChange={(event) => updateLine(index, 'quantity_received', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input aria-label={`Line ${index + 1} unit cost`} value={line.unit_cost} onChange={(event) => updateLine(index, 'unit_cost', event.target.value)} inputMode="decimal" />
                    </td>
                    <td>
                      <input aria-label={`Line ${index + 1} notes`} value={line.notes} onChange={(event) => updateLine(index, 'notes', event.target.value)} />
                    </td>
                    <td className="receiving-action-cell">
                      <button className="pager-button" aria-label={`Remove receiving line ${index + 1}`} onClick={() => removeLine(index)} disabled={form.lines.length === 1} type="button">
                        <X size={17} aria-hidden="true" />
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
          <button className="primary-button" aria-describedby={commitReason ? 'receiving-commit-reason' : undefined} disabled={Boolean(commitReason)} onClick={commitReceiving} type="button">
            Commit Receiving
          </button>
        </div>
        {commitReason && <p className="receiving-disabled-reason" id="receiving-commit-reason" role="status">Commit unavailable: {commitReason}</p>}
        {loading && <div className="loading-strip">Working on receiving...</div>}
        {error && <div className="api-error">{error}</div>}
        {summary && (
          <div className="success-strip">
            Receipt {summary.receipt_number} posted. {summary.total_quantity_received} units received across {summary.total_lines} line(s).
          </div>
        )}
        {preview && <ReceivingPreview preview={preview} />}
      </div>}
      {mode === 'bulk' && <BulkReceivingSession items={items} locations={locations} onCommitted={() => onLoadInventorySummary()} />}
      {mode === 'history' && <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Receipt History</h2>
            <p>Posted direct receiving sessions.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadReceipts({ page: receiptsPagination.page || 1, page_size: receiptsPagination.page_size || 20 })} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
        </div>
        {receiptsError && <div className="api-error">{receiptsError}</div>}
        {receiptsLoading && <div className="loading-strip">Loading receipt history...</div>}
        <ReceiptHistoryTable receipts={receipts} pagination={receiptsPagination} onLoad={onLoadReceipts} />
      </div>}
      {mode !== 'bulk' && <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Recent Stock Movements</h2>
            <p>Audit trail for direct receiving.</p>
          </div>
          <button className="muted-button" onClick={() => onLoadStockMovements({ movement_type: 'receive_direct', page: stockMovementsPagination.page || 1, page_size: stockMovementsPagination.page_size || 20 })} type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
        </div>
        {stockMovementsError && <div className="api-error">{stockMovementsError}</div>}
        {stockMovementsLoading && <div className="loading-strip">Loading stock movements...</div>}
        <StockMovementsTable movements={stockMovements} pagination={stockMovementsPagination} onLoad={(page, pageSize) => onLoadStockMovements({ movement_type: 'receive_direct', page, page_size: pageSize })} />
      </div>}
    </section>
  );
}

function BulkReceivingSession({ items, locations, onCommitted }) {
  const mutationRef = useRef(null);
  const [header, setHeader] = useState({ warehouse: 'Main Warehouse', notes: '' });
  const [scanInput, setScanInput] = useState('');
  const [selectedItem, setSelectedItem] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [inventoryLocation, setInventoryLocation] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [optional, setOptional] = useState({ lot_number: '', expiration_date: '', pallet_number: '', pkg_number: '', item_number: '', sales_price: '', weight: '', notes: '' });
  const [lines, setLines] = useState([]);
  const [preview, setPreview] = useState(null);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState('');
  const activeLocations = locations.filter((location) => location.isActive && (!header.warehouse || location.warehouse === header.warehouse));
  const commitReason = !lines.length ? 'add at least one receiving line.' : !preview ? 'preview the session before committing.' : !preview.can_commit ? 'resolve the validation errors shown below.' : '';

  function addLine() {
    const item = selectedItem || findReceivingItem(items, scanInput);
    setLines((current) => [...current, { localId: crypto.randomUUID?.() || String(Date.now()), item_id: operationalItemId(item), scan_input: scanInput, sku: operationalItemSku(item), barcode: operationalItemBarcode(item), quantity: toNumber(quantity) || 1, warehouse: header.warehouse, inventory_location: inventoryLocation, unit_cost: unitCost, ...optional }]);
    setScanInput('');
    setSelectedItem(null);
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
      const payload = { ...header, source: 'manual', lines };
      const result = await postJson('/api/receipts/bulk/commit', withMutationIdempotency(mutationRef, 'bulk-receipt', payload));
      setSummary(result);
      setLines([]);
      setPreview(null);
      await onCommitted();
      resetMutationIdempotency(mutationRef);
    } catch (apiError) {
      setError(apiError.message || 'Unable to commit bulk receipt.');
    }
  }

  return (
    <div className="receiving-form bulk-session">
      <div className="section-heading"><div><h2>Bulk Receiving Session</h2><p>Multi-row receiving cart committed as one receipt.</p></div><button className="muted-button" onClick={() => { resetMutationIdempotency(mutationRef); setLines([]); setPreview(null); setSummary(null); }} type="button">Clear Session</button></div>
      <div className="receiving-header-fields">
        <FilterSelect label="Warehouse" value={header.warehouse} options={uniqueOptions(locations, 'warehouse')} onChange={(value) => setHeader((current) => ({ ...current, warehouse: value || 'Main Warehouse' }))} />
        <label className="field wide-field"><span>Notes</span><input value={header.notes} onChange={(event) => setHeader((current) => ({ ...current, notes: event.target.value }))} /></label>
      </div>
      <div className="scanner-input-row">
        <InventoryKeywordSearch
          autoFocus
          className="operational-item-lookup"
          hideLabel
          label="Bulk receiving SKU, barcode, or product"
          onChange={(value) => {
            setScanInput(value);
            if (!operationalItemMatchesQuery(selectedItem, value)) setSelectedItem(null);
          }}
          onSelect={setSelectedItem}
          onSubmit={addLine}
          placeholder="Scan or type SKU/barcode"
          value={scanInput}
        />
        <input value={quantity} onChange={(event) => setQuantity(event.target.value)} inputMode="decimal" />
        <select value={inventoryLocation} onChange={(event) => setInventoryLocation(event.target.value)}><option value="">Location</option>{activeLocations.map((location) => <option key={location.id} value={location.code}>{location.warehouse} / {location.code}</option>)}</select>
        <input value={unitCost} onChange={(event) => setUnitCost(event.target.value)} placeholder="Unit cost" inputMode="decimal" />
        <button className="primary-button" onClick={addLine} type="button"><Plus size={16} />Add Line</button>
      </div>
      <details className="optional-fields"><summary>Optional receiving fields</summary><div className="operation-grid">{Object.keys(optional).map((field) => <label className="field" key={field}><span>{field.replace(/_/g, ' ')}</span><input value={optional[field]} onChange={(event) => setOptional((current) => ({ ...current, [field]: event.target.value }))} type={field === 'expiration_date' ? 'date' : 'text'} /></label>)}</div></details>
      <TableShell caption={`${lines.length} cart line(s)`} columns={['Scan', 'SKU', 'Location', 'Qty', 'Unit Cost', 'Notes', 'Remove']}>
        {lines.map((line, index) => <tr key={line.localId}><td>{line.scan_input}</td><td>{line.sku || <DataQualityBadge kind="missing_sku" />}</td><td><LocationPresentation value={line.inventory_location} /></td><td>{formatNumber(line.quantity)}</td><td>{isMissingValue(line.unit_cost) ? <DataQualityBadge kind="missing_cost" /> : formatCurrency(line.unit_cost)}</td><td>{line.notes}</td><td className="receiving-action-cell"><button className="pager-button" aria-label={`Remove bulk receiving line ${index + 1}`} onClick={() => { setLines((current) => current.filter((candidate) => candidate.localId !== line.localId)); setPreview(null); }} type="button"><X size={17} aria-hidden="true" /></button></td></tr>)}
        {!lines.length && <tr><td colSpan={7}><div className="empty-table-row">Scan or add lines to begin.</div></td></tr>}
      </TableShell>
      <div className="detail-actions"><button className="muted-button" onClick={previewSession} type="button">Preview Session</button><button className="primary-button" aria-describedby={commitReason ? 'bulk-receiving-commit-reason' : undefined} disabled={Boolean(commitReason)} onClick={commitSession} type="button">Commit Session</button></div>
      {commitReason && <p className="receiving-disabled-reason" id="bulk-receiving-commit-reason" role="status">Commit unavailable: {commitReason}</p>}
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
        {preview.lines.map((line) => <tr key={line.line_number}><td>{line.line_number}</td><td>{StatusText(line.status)}</td><td>{line.item?.sku}</td><td><LocationPresentation value={line.inventory_location} /></td><td>{formatNumber(line.quantity)}</td><td>{formatNumber(line.old_location_stock)}</td><td>{formatNumber(line.new_location_stock)}</td><td>{line.errors?.join(' ')}</td></tr>)}
      </TableShell>
    </div>
  );
}

function ScannerWorkflowsPage({ locations, onLoadInventorySummary }) {
  const mutationRef = useRef(null);
  const [mode, setMode] = useState('inventory');
  const [form, setForm] = useState({ scan_input: '', quantity: 1, warehouse: 'Main Warehouse', inventory_location: '', counted_quantity: '', adjustment_type: 'correction', quantity_change: '', new_quantity: '', reason: '', notes: '', order_id: '' });
  const [result, setResult] = useState(null);
  const [recent, setRecent] = useState([]);
  const [error, setError] = useState('');
  const activeLocations = locations.filter((location) => location.isActive);
  const modes = [
    { key: 'inventory', label: 'Inventory Lookup' },
    { key: 'location', label: 'Location Lookup' },
    { key: 'receiving', label: 'Receiving' },
    { key: 'cycle-count', label: 'Cycle Count' },
    { key: 'adjustment', label: 'Adjustment' },
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
        const response = await apiFetch(`${API_BASE_URL}/api/scanner/inventory/lookup?scan_input=${encodeURIComponent(form.scan_input)}`);
        nextResult = await response.json();
      } else if (mode === 'location') {
        const response = await apiFetch(`${API_BASE_URL}/api/scanner/location/lookup?scan_input=${encodeURIComponent(form.scan_input)}`);
        nextResult = await response.json();
      } else {
        const endpoint = {
          receiving: `/api/scanner/receiving/scan/${commit ? 'commit' : 'preview'}`,
          'cycle-count': `/api/scanner/cycle-count/${commit ? 'commit' : 'preview'}`,
          adjustment: `/api/scanner/adjustments/${commit ? 'commit' : 'preview'}`,
        }[mode];
        const payload = { ...form, quantity: toNumber(form.quantity), counted_quantity: toNumber(form.counted_quantity), quantity_change: form.quantity_change === '' ? '' : toNumber(form.quantity_change), new_quantity: form.new_quantity === '' ? '' : toNumber(form.new_quantity) };
        const commitPayload = commit && ['receiving', 'adjustment'].includes(mode)
          ? withMutationIdempotency(mutationRef, `scanner-${mode}`, payload)
          : payload;
        nextResult = await postJson(endpoint, commitPayload);
      }
      setResult(nextResult);
      setRecent((current) => [{ mode, scan: form.scan_input, status: nextResult.matched === false || nextResult.can_commit === false ? 'warning' : 'success', at: new Date().toISOString() }, ...current].slice(0, 12));
      if (commit) {
        await onLoadInventorySummary();
        if (['receiving', 'adjustment'].includes(mode)) resetMutationIdempotency(mutationRef);
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
              <h2>Ready to scan</h2>
            </div>
            <Badge tone={result?.matched === false || result?.can_commit === false ? 'warning' : result ? 'success' : 'neutral'}>{result ? 'Result loaded' : 'Waiting'}</Badge>
          </div>
          <div className="scanner-input-row">
            <input autoFocus value={form.scan_input} onChange={(event) => update('scan_input', event.target.value)} onKeyDown={(event) => event.key === 'Enter' && runScan(false)} placeholder={mode === 'location' ? 'Scan location code or name' : 'Scan SKU, barcode, or item ID'} />
            <button className="primary-button" onClick={() => runScan(false)} type="button"><Search size={16} />Scan</button>
          </div>
          {['receiving', 'cycle-count', 'adjustment'].includes(mode) && (
            <div className="operation-grid">
              {mode === 'receiving' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><label className="field"><span>Quantity</span><input value={form.quantity} onChange={(event) => update('quantity', event.target.value)} /></label><label className="field"><span>Unit Cost</span><input value={form.unit_cost || ''} onChange={(event) => update('unit_cost', event.target.value)} /></label></>}
              {mode === 'cycle-count' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><label className="field"><span>Counted Quantity</span><input value={form.counted_quantity} onChange={(event) => update('counted_quantity', event.target.value)} /></label><label className="field"><span>Reason</span><input value={form.reason} onChange={(event) => update('reason', event.target.value)} /></label></>}
              {mode === 'adjustment' && <><ScannerLocationFields form={form} locations={activeLocations} update={update} /><FilterSelect label="Adjustment Type" value={form.adjustment_type} options={['correction', 'damage', 'loss', 'found', 'manual_increase', 'manual_decrease']} onChange={(value) => update('adjustment_type', value)} /><label className="field"><span>Qty Change</span><input value={form.quantity_change} onChange={(event) => update('quantity_change', event.target.value)} /></label><label className="field"><span>New Qty</span><input value={form.new_quantity} onChange={(event) => update('new_quantity', event.target.value)} /></label><label className="field"><span>Reason</span><input value={form.reason} onChange={(event) => update('reason', event.target.value)} /></label></>}
            </div>
          )}
          {['receiving', 'cycle-count', 'adjustment'].includes(mode) && <div className="button-row"><button className="muted-button" onClick={() => runScan(false)} type="button">Preview</button><button className="primary-button" onClick={() => runScan(true)} type="button">Commit</button></div>}
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
      {item && <div className="scanner-match"><strong>{item.sku}</strong><span>{item.barcode}</span><p>{decodeHtmlEntities(item.description || '')}</p></div>}
      {result.stock_by_location && <ItemStockByLocation rows={result.stock_by_location} />}
      {result.items && <TableShell caption={`${result.items.length} location item(s)`} columns={['SKU', 'Product Title', 'Location', 'In Stock', 'Sellable']} >{result.items.map((row) => <tr key={row.id}><td>{row.sku}</td><td>{productTitle(row)}</td><td>{row.inventory_location}</td><td>{formatNumber(row.in_stock)}</td><td>{formatNumber(row.sellable)}</td></tr>)}</TableShell>}
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
              <th>Product Title</th>
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
                <td>{StatusText(line.status)}</td>
                <td>{line.sku}</td>
                <td className="description-cell"><ClampedText value={line.description} /></td>
                <td><LocationPresentation value={line.inventory_location} /></td>
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

function ReceiptHistoryTable({ receipts, pagination, onLoad }) {
  return (
    <TableShell caption={`${pagination?.total ?? receipts.length} receipt(s)`} columns={['Receipt Number', 'Warehouse', 'Reference Number', 'Status', 'Total Lines', 'Total Quantity', 'Received At', 'Created By']} pagination={serverTablePagination(pagination, 'receipts', (page) => onLoad({ page, page_size: pagination.page_size || 20 }), (pageSize) => onLoad({ page: 1, page_size: pageSize }))}>
      {receipts.map((receipt) => (
        <tr key={receipt.id}>
          <td className="mono">{receipt.receipt_number}</td>
          <td>{receipt.warehouse}</td>
          <td>{receipt.reference_number}</td>
          <td>{StatusText(receipt.status)}</td>
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

function StockMovementsTable({ movements, pagination, onLoad }) {
  return (
    <TableShell caption={`${pagination?.total ?? movements.length} movement(s)`} columns={['Created At', 'SKU', 'Barcode', 'Movement Type', 'Quantity Delta', 'Previous In Stock', 'New In Stock', 'Warehouse', 'Inventory Location', 'Reference Number']} pagination={serverTablePagination(pagination, 'movements', (page) => onLoad(page, pagination.page_size || 20), (pageSize) => onLoad(1, pageSize))}>
      {movements.map((movement) => (
        <tr key={movement.id}>
          <td>{formatDateTime(movement.created_at)}</td>
          <td className="mono">{movement.sku}</td>
          <td className="mono">{movement.barcode}</td>
          <td>{StatusText(movement.movement_type)}</td>
          <td>{formatNumber(movement.quantity_delta)}</td>
          <td>{formatNumber(movement.previous_in_stock)}</td>
          <td>{formatNumber(movement.new_in_stock)}</td>
          <td>{movement.warehouse}</td>
          <td><LocationPresentation value={movement.inventory_location} /></td>
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

function ReportsPage({ route, receivedRows, receivedSummary, receivedLoading, receivedError, onLoadReceivedReport, fulfillmentRows, fulfillmentSummary, fulfillmentLoading, fulfillmentError, onLoadFulfillmentReport, skuOrdersRows, skuOrdersSummary, skuOrdersLoading, skuOrdersError, onLoadSkuOrdersReport }) {
  const activeDefinition = allReportDefinitions.find((report) => report.key === route.reportKey) || allReportDefinitions[0];
  const activeReport = activeDefinition.key;
  if (intelligentReportKeys.has(activeReport)) {
    return (
      <Suspense fallback={<div className="ri-report-loading">Loading report workspace…</div>}>
        <ReportIntelligencePage apiBaseUrl={API_BASE_URL} reportKey={activeDefinition.apiKey || activeReport} />
      </Suspense>
    );
  }
  const category = reportCategories.find((candidate) => candidate.id === activeDefinition.category) || reportCategories[0];
  const categoryReports = allReportDefinitions.filter((report) => report.category === category.id);
  const isExpandedReport = expandedReportDefinitions.some((report) => report.key === activeReport);

  return (
    <section className="content-panel report-page">
      <div className="reports-workspace">
        <aside className="report-nav-card" aria-label="Report list">
          <div>
            <span className="report-category-label">{category.label}</span>
            <h2>{category.label} reports</h2>
            <p>Choose one read-only, export-ready view.</p>
          </div>
          <nav className="report-nav-list" aria-label={`${category.label} reports`}>
            {categoryReports.map((report) => (
              <a className={activeReport === report.key ? 'report-nav-button active' : 'report-nav-button'} href={reportHref(report)} key={report.key} aria-current={activeReport === report.key ? 'page' : undefined}>
                {report.label}
              </a>
            ))}
          </nav>
        </aside>
        <div className="report-main-panel">
          {isExpandedReport && <ExpandedReportsPanel activeReport={activeReport} key={activeReport} />}
          {activeReport === 'received-inventory' && <ReceivedInventoryReportPage rows={receivedRows} summary={receivedSummary} loading={receivedLoading} error={receivedError} onLoadReport={onLoadReceivedReport} />}
          {activeReport === 'fulfillment' && <FulfillmentReportPage rows={fulfillmentRows} summary={fulfillmentSummary} loading={fulfillmentLoading} error={fulfillmentError} onLoadReport={onLoadFulfillmentReport} />}
          {activeReport === 'sku-orders' && <SkuOrdersReportPage rows={skuOrdersRows} summary={skuOrdersSummary} loading={skuOrdersLoading} error={skuOrdersError} onLoadReport={onLoadSkuOrdersReport} />}
        </div>
      </div>
    </section>
  );
}

function ExpandedReportsPanel({ activeReport }) {
  const active = activeReport || expandedReportDefinitions[0].key;
  const [filters, setFilters] = useState({ sku: '', barcode: '', brand: '', category: '', warehouse: '', inventory_location: '', start_date: '', end_date: '', movement_type: '', adjustment_type: '' });
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const definition = expandedReportDefinitions.find((report) => report.key === active) || expandedReportDefinitions[0];
  const valuationSummaryKeys = ['inventory_record_count', 'unique_sku_count', 'reported_sku_count', 'valued_sku_count', 'total_units', 'total_inventory_value', 'total_retail_value', 'excluded_record_count', 'missing_cost_count'];
  const summaryEntries = (active === 'inventory-valuation' ? valuationSummaryKeys.map((key) => [key, summary[key]]).filter(([, value]) => value !== undefined) : Object.entries(summary).filter(([, value]) => value === null || ['string', 'number', 'boolean'].includes(typeof value))).slice(0, 9);

  useEffect(() => {
    loadReport();
  }, [active]);

  function update(field, value) {
    setFilters((current) => ({ ...current, [field]: value }));
  }

  async function loadReport(forceFilters = filters) {
    setLoading(true);
    setError('');
    try {
      const requestFilters = pickFilterValues(forceFilters, definition.filters);
      const query = plainFiltersToQueryString(requestFilters);
      const [rowsResponse, summaryResponse] = await Promise.all([apiFetch(`${API_BASE_URL}/api/reports/${active}${query}`), apiFetch(`${API_BASE_URL}/api/reports/${active}/summary${query}`)]);
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

  function applyDatePreset(months) {
    const nextFilters = { ...filters, ...completedMonthRange(months) };
    setFilters(nextFilters);
    loadReport(nextFilters);
  }

  return (
    <section className="wide-panel report-section">
      <div className="panel-title"><div><h2>{definition.label}</h2><p>Read-only local inventory and operations report.</p></div></div>
      <div className="summary-strip report-summary-strip">
        {summaryEntries.map(([key, value]) => <Metric key={key} label={titleize(key)} value={formatInsightValue(key, value)} />)}
        {Object.keys(summary).length === 0 && <Metric label="Rows" value={rows.length} />}
      </div>
      {Array.isArray(summary.exclusion_summary) && summary.exclusion_summary.length > 0 && <div className="insight-warning-list" aria-label="Valuation exclusions">{summary.exclusion_summary.map((entry, index) => <div className="insight-warning warning" key={`${entry.reason || entry.label}-${index}`}><strong>{entry.label || titleize(entry.reason)}</strong><span>{entry.message || `${formatNumber(entry.count)} record(s) excluded.`}</span></div>)}</div>}
      <div className="toolbar report-toolbar">
        {(definition.filters.includes('start_date') || definition.filters.includes('end_date')) && <div className="date-preset-panel report-date-presets"><div><span>Quick range</span><small>Completed calendar periods</small></div><div className="date-preset-buttons" aria-label="Report date presets"><button type="button" onClick={() => applyDatePreset(1)}>Last month</button><button type="button" onClick={() => applyDatePreset(2)}>Last 2 months</button><button type="button" onClick={() => applyDatePreset(3)}>Last 3 months</button><button type="button" onClick={() => applyDatePreset(12)}>Last year</button></div></div>}
        <div className="filter-grid report-filter-grid">
          {definition.filters.map((field) => <label className="field" key={field}><span>{reportFilterLabels[field] || titleize(field)}</span><input value={filters[field]} onChange={(event) => update(field, event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, loadReport)} type={field.endsWith('_date') ? 'date' : 'text'} /></label>)}
        </div>
        <div className="button-row items-actions"><button className="primary-button" onClick={() => loadReport()} type="button"><RefreshCw size={17} />Refresh</button><button className="muted-button" onClick={() => { const cleared = { sku: '', barcode: '', brand: '', category: '', warehouse: '', inventory_location: '', start_date: '', end_date: '', movement_type: '', adjustment_type: '' }; setFilters(cleared); loadReport(cleared); }} type="button"><RotateCcw size={17} />Reset Filters</button><button className="action-button" onClick={() => exportGenericReportCsv(active, pickFilterValues(filters, definition.filters), definition.label)} type="button"><Download size={17} />Export CSV</button></div>
      </div>
      {loading && <div className="loading-strip">Loading {definition.label}...</div>}
      {error ? <div className="api-error" role="alert">{error}</div> : !loading && <GenericReportTable rows={rows} />}
    </section>
  );
}

function GenericReportTable({ rows }) {
  const columns = rows[0] ? Object.keys(rows[0]) : [];
  return (
    <TableShell caption={`${rows.length} row(s)`} columns={columns.length ? columns.map((column) => column.replace(/_/g, ' ')) : ['Report']}>
      {rows.map((row, index) => <tr key={index}>{columns.map((column) => <td key={column} className={column.includes('description') || column.includes('name') ? 'description-cell' : ''}>{renderReportCell(column, row[column])}</td>)}</tr>)}
      {!rows.length && <tr><td colSpan={Math.max(columns.length, 1)}><div className="empty-table-row">No report rows match the current filters.</div></td></tr>}
    </TableShell>
  );
}

function renderReportCell(column, value) {
  if (isMissingValue(value)) {
    const kind = column.includes('barcode') ? 'missing_barcode' : column.includes('brand') ? 'missing_brand' : column.includes('category') ? 'missing_category' : column.includes('cost') ? 'missing_cost' : column.includes('location') ? 'missing_location' : column === 'sku' ? 'missing_sku' : 'unavailable';
    return <DataQualityBadge kind={kind} />;
  }
  if (column.includes('location')) return <LocationPresentation value={value} />;
  if (column.includes('description') || column.includes('name')) return <ClampedText value={formatReportValue(value, column)} />;
  if (column.includes('risk')) return StatusText(value, 'risk');
  if (column.includes('status') || column.endsWith('_type')) return StatusText(value);
  return formatReportValue(value, column);
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

  function applyDatePreset(months) {
    const range = completedMonthRange(months);
    const nextFilters = { ...filters, dateFrom: range.start_date, dateTo: range.end_date };
    setFilters(nextFilters);
    setActiveFilters(nextFilters);
    onLoadReport(nextFilters);
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
        <div className="date-preset-panel report-date-presets">
          <div><span>Stock received</span><small>Filter posted receipts instantly</small></div>
          <div className="date-preset-buttons" aria-label="Received inventory date presets">
            <button type="button" onClick={() => applyDatePreset(1)}>Last month</button>
            <button type="button" onClick={() => applyDatePreset(2)}>Last 2 months</button>
            <button type="button" onClick={() => applyDatePreset(3)}>Last 3 months</button>
            <button type="button" onClick={() => applyDatePreset(12)}>Last year</button>
          </div>
        </div>
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
        <span>{formatNumber(rows.length)} received inventory row(s)</span>
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
              <th>Product Title</th>
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
                <td>{row.warehouse || <DataQualityBadge kind="missing_location" />}</td>
                <td><LocationPresentation value={row.inventory_location} /></td>
                <td className="mono">{row.sku || <DataQualityBadge kind="missing_sku" />}</td>
                <td className="mono">{row.barcode || <DataQualityBadge kind="missing_barcode" />}</td>
                <td className="description-cell"><ClampedText value={row.description} /></td>
                <td>{row.category ? decodeHtmlEntities(row.category) : <DataQualityBadge kind="missing_category" />}</td>
                <td>{row.brand ? decodeHtmlEntities(row.brand) : <DataQualityBadge kind="missing_brand" />}</td>
                <td>{formatNumber(row.quantity_received)}</td>
                <td>{isMissingValue(row.unit_cost) ? <DataQualityBadge kind="missing_cost" /> : formatCurrency(row.unit_cost)}</td>
                <td>{isMissingValue(row.total_received_value) ? 'Not available' : formatCurrency(row.total_received_value)}</td>
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
    <TableShell caption={`${rows.length} fulfillment row(s)`} columns={['Fulfillment', 'Posted At', 'Woo Order', 'Local Status', 'Customer', 'Warehouse', 'Location', 'SKU', 'Barcode', 'Product Title', 'Category', 'Brand', 'Qty Fulfilled', 'Unit Cost', 'Fulfilled Value', 'Stock Before', 'Stock After', 'Allocated Before', 'Allocated After', 'Created By']}>
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
          <td className="description-cell"><ClampedText value={row.description} /></td>
          <td>{row.category ? decodeHtmlEntities(row.category) : <DataQualityBadge kind="missing_category" />}</td>
          <td>{row.brand ? decodeHtmlEntities(row.brand) : <DataQualityBadge kind="missing_brand" />}</td>
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
    <TableShell caption={`${groups.length} SKU group(s)`} columns={['SKU', 'Product Title', 'Brand', 'Category', 'Qty Fulfilled', 'Fulfilled Value', 'Fulfillments', 'Orders']}>
      {groups.map((group) => (
        <tr key={group.sku}><td className="mono">{group.sku}</td><td className="description-cell"><ClampedText value={group.description} /></td><td>{decodeHtmlEntities(group.brand || '')}</td><td>{decodeHtmlEntities(group.category || '')}</td><td>{formatNumber(group.total_quantity_fulfilled)}</td><td>{formatCurrency(group.total_fulfilled_value)}</td><td>{formatNumber(group.fulfillment_count)}</td><td>{formatNumber(group.order_count)}</td></tr>
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
      {error && <div className="api-error">{error}</div>}
      {loading && <div className="loading-strip">Loading SKU Orders report...</div>}
      <TableShell caption={`${rows.length} SKU order row(s)`} columns={['SKU', 'Item', 'Product Title', 'Brand', 'Category', 'Location', 'Orders', 'Ordered', 'Allocated', 'Picked', 'Fulfilled', 'Unfulfilled', 'Unmatched Lines', 'First Order', 'Last Order', 'In Stock', 'Sellable', 'Woo Snapshot']}>
        {rows.map((row) => (
          <tr key={`${row.sku}-${row.item_id || row.location || row.brand || row.category}`}>
            <td className="mono">{row.sku}</td>
            <td>{row.item_id || ''}</td>
            <td className="description-cell"><ClampedText value={row.description} /></td>
            <td>{row.brand ? decodeHtmlEntities(row.brand) : <DataQualityBadge kind="missing_brand" />}</td>
            <td>{row.category ? decodeHtmlEntities(row.category) : <DataQualityBadge kind="missing_category" />}</td>
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
  orderCompletionSummary,
  onCompleteOrder,
  allocationPreview,
  allocationCommitSummary,
  allocationHistory,
  allocationHistoryPagination,
  onLoadAllocations,
  allocationDetail,
  allocationLoading,
  allocationError,
  onPreviewAllocation,
  onCommitAllocation,
  onLoadAllocationDetail,
  pickPreview,
  pickCommitSummary,
  pickHistory,
  pickHistoryPagination,
  onLoadPicks,
  pickDetail,
  pickLoading,
  pickError,
  onPreviewPick,
  onCommitPick,
  onLoadPickDetail,
  fulfillmentPreview,
  fulfillmentCommitSummary,
  fulfillmentHistory,
  fulfillmentHistoryPagination,
  onLoadFulfillments,
  fulfillmentDetail,
  fulfillmentLoading,
  fulfillmentError,
  onPreviewFulfillment,
  onCommitFulfillment,
  onLoadFulfillmentDetail,
}) {
  const emptyOrderFilters = { orderNumber: '', customer: '', containingItem: '', warehouse: '', search: '', wooStatus: '', availabilityStatus: '', matchedStatus: '' };
  const [filters, setFilters] = useState(emptyOrderFilters);
  const [appliedOrderFilters, setAppliedOrderFilters] = useState(emptyOrderFilters);
  const [ordersPageNumber, setOrdersPageNumber] = useState(1);
  const [ordersPageSize, setOrdersPageSize] = useState(20);
  const [orderDialogOpen, setOrderDialogOpen] = useState(false);
  const [selectedOpenOrderIds, setSelectedOpenOrderIds] = useState([]);
  const [bulkActionLoading, setBulkActionLoading] = useState(false);
  const [bulkActionMessage, setBulkActionMessage] = useState('');
  const [bulkActionError, setBulkActionError] = useState('');
  const [bulkPrintOrders, setBulkPrintOrders] = useState([]);
  const unpickMutationRef = useRef(null);
  const substitutionMutationRef = useRef(null);
  const orders = ordersData.orders || [];
  const ordersPageCount = Math.max(1, Number(ordersData.total_pages || 1));
  const pagedOpenOrders = orders;
  const selectedOpenOrderSet = useMemo(() => new Set(selectedOpenOrderIds), [selectedOpenOrderIds]);
  const selectedOrderId = detail?.id;
  const view = route.ordersView || 'open';

  useEffect(() => {
    setOrderDialogOpen(false);
    setSelectedOpenOrderIds([]);
    if (view !== 'open') return;
    const cleared = { orderNumber: '', customer: '', containingItem: '', warehouse: '', search: '', wooStatus: '', availabilityStatus: '', matchedStatus: '' };
    setFilters(cleared);
    setAppliedOrderFilters(cleared);
    setOrdersPageNumber(1);
  }, [view]);

  useEffect(() => {
    const visibleIds = new Set(orders.map((order) => order.id));
    setSelectedOpenOrderIds((current) => current.filter((orderId) => visibleIds.has(orderId)));
  }, [ordersData.orders]);

  useEffect(() => {
    setOrdersPageNumber(Number(ordersData.page || 1));
    if (ordersData.page_size) setOrdersPageSize(Number(ordersData.page_size));
  }, [ordersData.page, ordersData.page_size]);

  useEffect(() => {
    if (bulkPrintOrders.length) printVisibleRoot('bulk-order-printing');
  }, [bulkPrintOrders]);

  function updateFilter(key, value) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function clearFilters() {
    const cleared = emptyOrderFilters;
    setFilters(cleared);
    setAppliedOrderFilters(cleared);
    setOrdersPageNumber(1);
    setSelectedOpenOrderIds([]);
    onLoadOpenOrders({ ...cleared, page: 1, pageSize: ordersPageSize }, { ordersView: 'open' });
  }

  function applyOpenOrderFilters() {
    setAppliedOrderFilters(filters);
    setOrdersPageNumber(1);
    setSelectedOpenOrderIds([]);
    onLoadOpenOrders({ ...filters, page: 1, pageSize: ordersPageSize }, { ordersView: 'open' });
  }

  function changeOpenOrdersPage(page) {
    setOrdersPageNumber(page);
    setSelectedOpenOrderIds([]);
    onLoadOpenOrders({ ...appliedOrderFilters, page, pageSize: ordersPageSize }, { ordersView: 'open', preserveDetail: true });
  }

  function changeOpenOrdersPageSize(pageSize) {
    setOrdersPageSize(pageSize);
    setOrdersPageNumber(1);
    setSelectedOpenOrderIds([]);
    onLoadOpenOrders({ ...appliedOrderFilters, page: 1, pageSize }, { ordersView: 'open', preserveDetail: true });
  }

  async function viewOpenOrder(orderId) {
    const loaded = await onLoadOpenOrderDetail(orderId);
    if (loaded) {
      setOrderDialogOpen(true);
      window.requestAnimationFrame(() => document.getElementById('open-order-detail')?.focus());
    }
  }

  async function editOpenOrder(orderId) {
    await viewOpenOrder(orderId);
  }

  async function substituteOpenOrderLine(line, replacementItem, reason) {
    if (!detail?.id || !line?.id || !replacementItem?.id) throw new Error('The order line or replacement item is unavailable.');
    const result = await substituteOrderLine(detail.id, line.id, {
      replacement_inventory_item_id: Number(replacementItem.id),
      reason,
    }, substitutionMutationRef);
    resetMutationIdempotency(substitutionMutationRef);
    await Promise.all([
      onLoadOpenOrderDetail(detail.id),
      onLoadOpenOrders({ ...appliedOrderFilters, page: ordersPageNumber, pageSize: ordersPageSize }, { ordersView: 'open', preserveDetail: true }),
    ]);
    return result;
  }

  async function printOpenOrder(orderId) {
    const loaded = await onLoadOpenOrderDetail(orderId);
    if (loaded) {
      setOrderDialogOpen(true);
      printVisibleRoot('single-order-printing');
    }
  }

  async function unpickOpenOrder(order) {
    if (!window.confirm(`Unpick order ${order.woo_order_number || order.woo_order_id}? Stock and allocation will be restored at the original pick locations.`)) return;
    setBulkActionLoading(true);
    setBulkActionError('');
    try {
      const payload = { order_ids: [order.id], created_by: 'system', reason: 'Unpicked from Open Orders row action.' };
      const result = await postJson('/api/orders/bulk/unpick', withMutationIdempotency(unpickMutationRef, 'unpick', payload));
      if (result.status === 'rejected') throw new Error((result.errors || []).join(' ') || 'The order could not be unpicked.');
      setBulkActionMessage(`Order ${order.woo_order_number || order.woo_order_id} was unpicked.`);
      await onLoadOpenOrders({ ...appliedOrderFilters, page: ordersPageNumber, pageSize: ordersPageSize }, { ordersView: 'open' });
      resetMutationIdempotency(unpickMutationRef);
    } catch (unpickError) {
      setBulkActionError(unpickError.message || 'Unable to unpick this order.');
    } finally {
      setBulkActionLoading(false);
    }
  }

  async function importOpenOrders() {
    if (!window.confirm('Fetch the latest WooCommerce order changes now?')) return;
    setBulkActionLoading(true);
    setBulkActionError('');
    setBulkActionMessage('');
    try {
      const job = await postJson('/api/integrations/woocommerce/orders/fetch-now', {});
      setBulkActionMessage(`WooCommerce fetch job #${job.id} is ${job.status}. Orders will refresh automatically when the worker finishes.`);
    } catch (importError) {
      setBulkActionError(importError.message || 'Unable to queue the WooCommerce order fetch.');
    } finally {
      setBulkActionLoading(false);
    }
  }

  function toggleOpenOrderSelection(orderId, checked) {
    if (loading) return;
    setSelectedOpenOrderIds((current) => checked ? Array.from(new Set([...current, orderId])) : current.filter((id) => id !== orderId));
  }

  function toggleAllOpenOrders(checked) {
    if (loading) return;
    setSelectedOpenOrderIds(checked ? pagedOpenOrders.map((order) => order.id) : []);
  }

  async function runOpenOrdersBulkAction(action) {
    if (loading || !selectedOpenOrderIds.length) return;
    if (action === 'print') {
      setBulkActionLoading(true);
      setBulkActionError('');
      try {
        const responses = await Promise.all(selectedOpenOrderIds.map((orderId) => apiFetch(`${API_BASE_URL}/api/orders/${orderId}`)));
        if (responses.some((response) => !response.ok)) throw new Error('One or more selected orders could not be loaded for printing.');
        setBulkPrintOrders(await Promise.all(responses.map((response) => response.json())));
      } catch (printError) {
        setBulkActionError(printError.message || 'Unable to print selected orders.');
      } finally {
        setBulkActionLoading(false);
      }
      return;
    }

    const confirmation = action === 'complete'
      ? `Mark ${selectedOpenOrderIds.length} selected order(s) completed in Pongo OS and WooCommerce? Unpicked stock will not be reduced.`
      : `Unpick all picked quantities from ${selectedOpenOrderIds.length} selected order(s)? Stock and allocation will be restored at the original pick locations.`;
    if (!window.confirm(confirmation)) return;
    setBulkActionLoading(true);
    setBulkActionMessage('');
    setBulkActionError('');
    try {
      const endpoint = action === 'complete' ? '/api/orders/bulk/complete' : '/api/orders/bulk/unpick';
      const payload = {
        order_ids: selectedOpenOrderIds,
        created_by: 'system',
        reason: action === 'complete' ? 'Bulk completed from Open Orders.' : 'Bulk unpick all from Open Orders.',
      };
      const result = await postJson(
        endpoint,
        action === 'complete' ? payload : withMutationIdempotency(unpickMutationRef, 'unpick', payload),
      );
      if (result.status === 'rejected') throw new Error((result.errors || []).join(' ') || 'The bulk action was rejected.');
      setBulkActionMessage(`${result.succeeded_count} of ${result.requested_count} selected order(s) updated.`);
      if (result.errors?.length) setBulkActionError(result.errors.join(' '));
      if (action === 'complete') {
        const unsynced = (result.results || []).filter((row) => row.woo_sync_status !== 'sent');
        if (unsynced.length) {
          const syncErrors = [...new Set(unsynced.map((row) => row.woo_sync_error).filter(Boolean))];
          setBulkActionError(syncErrors.length
            ? syncErrors.join(' ')
            : `${unsynced.length} completed order(s) were not sent to WooCommerce. Review the WooCommerce writeback queue.`);
        }
      }
      setSelectedOpenOrderIds([]);
      await onLoadOpenOrders({ ...appliedOrderFilters, page: ordersPageNumber, pageSize: ordersPageSize }, { ordersView: 'open' });
      if (action === 'unpick') resetMutationIdempotency(unpickMutationRef);
    } catch (bulkError) {
      setBulkActionError(bulkError.message || 'Unable to complete the bulk action.');
    } finally {
      setBulkActionLoading(false);
    }
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
              <p>Read-only local allocation, pick, and legacy fulfillment/completion records.</p>
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
        <AllocationHistoryPanel allocations={allocationHistory} pagination={allocationHistoryPagination} onLoad={onLoadAllocations} detail={allocationDetail} onSelect={onLoadAllocationDetail} />
        <PickHistoryPanel picks={pickHistory} pagination={pickHistoryPagination} onLoad={onLoadPicks} detail={pickDetail} onSelect={onLoadPickDetail} />
        <FulfillmentHistoryPanel fulfillments={fulfillmentHistory} pagination={fulfillmentHistoryPagination} onLoad={onLoadFulfillments} detail={fulfillmentDetail} onSelect={onLoadFulfillmentDetail} />
      </section>
    );
  }

  if (view === 'allocate') {
    return (
      <section className="content-panel orders-page">
        <AllocationExceptionsPage onRefreshOperationalOrders={() => onLoadOpenOrders({}, { ordersView: 'allocate' })} />
      </section>
    );
  }

  if (view === 'pick') {
    return (
      <PickOrdersWorkspace
        orders={orders}
        pagination={ordersData}
        loading={loading || pickLoading}
        error={error || pickError}
        order={detail}
        preview={pickPreview}
        commitSummary={pickCommitSummary}
        onLoadOrders={(nextFilters) => onLoadOpenOrders(nextFilters, { ordersView: 'pick' })}
        onLoadOrder={onLoadOpenOrderDetail}
        onPreviewPick={onPreviewPick}
        onCommitPick={onCommitPick}
      />
    );
  }

  return (
    <section className="orders-page zen-orders-page">
      <header className="zen-orders-heading">
        <h2>Open Customer Orders</h2>
        <div className="zen-orders-heading-actions">
          <button disabled={bulkActionLoading} onClick={importOpenOrders} title="Import processing WooCommerce orders" type="button"><Upload size={20} />Import</button>
          <button onClick={() => exportOpenOrdersCsv({})} type="button"><Download size={20} />Export</button>
          <button disabled={loading} onClick={() => onLoadOpenOrders({ ...appliedOrderFilters, page: ordersPageNumber, pageSize: ordersPageSize }, { ordersView: 'open', preserveDetail: true })} type="button"><RefreshCw size={20} />Refresh</button>
        </div>
      </header>

      <div className="zen-orders-filters">
        <label><span>Order Number</span><input onChange={(event) => updateFilter('orderNumber', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyOpenOrderFilters)} value={filters.orderNumber} /></label>
        <label><span>Customer</span><div className="zen-filter-input"><input onChange={(event) => updateFilter('customer', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyOpenOrderFilters)} value={filters.customer} /><Search size={18} /></div></label>
        <label><span>Containing Item</span><div className="zen-filter-input"><input onChange={(event) => updateFilter('containingItem', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyOpenOrderFilters)} value={filters.containingItem} /><Search size={18} /></div></label>
        <label><span>Ship From</span><select onChange={(event) => updateFilter('warehouse', event.target.value)} value={filters.warehouse}><option value="">All Warehouses</option><option value="Main Warehouse">Main Warehouse</option></select></label>
        <div className="zen-orders-filter-buttons">
          <button className="primary-button" disabled={loading} onClick={applyOpenOrderFilters} type="button">Search</button>
          <button className="muted-button" onClick={clearFilters} type="button">Clear</button>
        </div>
      </div>

      {openStatus}
      {allocationError && <div className="api-error">{allocationError}</div>}
      {allocationCommitSummary && <OrderWorkflowSummary summary={allocationCommitSummary} type="Allocation" quantityField="total_quantity_allocated" />}
      {orderCompletionSummary && <div className="success-strip">{orderCompletionSummary.message}</div>}
      {bulkActionMessage && <div className="success-strip">{bulkActionMessage}</div>}
      {bulkActionError && <div className="api-error">{bulkActionError}</div>}

      <OrdersPager count={ordersData.total || 0} page={ordersPageNumber} pageCount={ordersPageCount} pageSize={ordersPageSize} onPageChange={changeOpenOrdersPage} onPageSizeChange={changeOpenOrdersPageSize} />
      <BulkActionsBar
        actions={[
          { label: 'Mark as completed', icon: <CheckCircle2 size={17} />, onSelect: () => runOpenOrdersBulkAction('complete') },
          { label: 'Print', icon: <Printer size={17} />, onSelect: () => runOpenOrdersBulkAction('print') },
          { label: 'Unpick all', icon: <RotateCcw size={17} />, onSelect: () => runOpenOrdersBulkAction('unpick'), danger: true },
        ]}
        busy={bulkActionLoading || loading}
        label="Bulk actions"
        selectedCount={selectedOpenOrderIds.length}
      />
      <OpenOrdersTable
        orders={pagedOpenOrders}
        selectable
        selectedIds={selectedOpenOrderSet}
        selectionDisabled={loading}
        onSelect={viewOpenOrder}
        onToggleAll={toggleAllOpenOrders}
        onToggleSelection={toggleOpenOrderSelection}
        renderActions={(order) => (
          <OrderActionsMenu
            order={order}
            disabled={loading}
            onView={() => viewOpenOrder(order.id)}
            onEdit={() => editOpenOrder(order.id)}
            onPrint={() => printOpenOrder(order.id)}
            onComplete={() => onCompleteOrder(order.id, order.pick_status)}
            onUnpick={() => unpickOpenOrder(order)}
            onTimeline={() => { window.location.hash = '#/orders/history'; }}
          />
        )}
      />
      <OrdersPager count={ordersData.total || 0} page={ordersPageNumber} pageCount={ordersPageCount} pageSize={ordersPageSize} onPageChange={changeOpenOrdersPage} onPageSizeChange={changeOpenOrdersPageSize} />
      {orderDialogOpen && <OpenOrderDetailPanel order={detail} onClose={() => { setOrderDialogOpen(false); onLoadOpenOrderDetail(null); }} onPrint={() => printVisibleRoot('single-order-printing')} onSubstitute={substituteOpenOrderLine} />}
      <BulkPrintSheet orders={bulkPrintOrders} />
    </section>
  );
}

function PickOrdersWorkspace({ orders, pagination = emptyOpenOrders, loading, error, order, preview, commitSummary, onLoadOrders, onLoadOrder, onPreviewPick, onCommitPick }) {
  const bulkPickMutationRef = useRef(null);
  const bulkUnpickMutationRef = useRef(null);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [pickedQuantities, setPickedQuantities] = useState({});
  const [selectedOrderIds, setSelectedOrderIds] = useState([]);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [bulkMessage, setBulkMessage] = useState('');
  const [bulkError, setBulkError] = useState('');
  const selectedOrderSet = useMemo(() => new Set(selectedOrderIds), [selectedOrderIds]);
  const pageCount = Math.max(1, Number(pagination.total_pages || 1));
  const previewOrder = (preview?.preview_orders || []).find((candidate) => candidate.order_id === order?.id);
  const lines = previewOrder?.lines || [];
  const isDetailOpen = Boolean(order && previewOrder);
  const quantityLines = lines
    .map((line) => ({ order_line_id: line.order_line_id, quantity_to_pick: Number(pickedQuantities[line.order_line_id] || 0) }))
    .filter((line) => line.quantity_to_pick > 0);
  const totalPickedNow = quantityLines.reduce((total, line) => total + line.quantity_to_pick, 0);

  useEffect(() => {
    setPickedQuantities(Object.fromEntries(lines.map((line) => [line.order_line_id, 0])));
  }, [previewOrder?.order_id, preview?.total_quantity_to_pick]);

  useEffect(() => {
    const visibleIds = new Set(orders.map((candidate) => candidate.id));
    setSelectedOrderIds((current) => current.filter((orderId) => visibleIds.has(orderId)));
  }, [orders]);

  useEffect(() => {
    setPage(Number(pagination.page || 1));
    if (pagination.page_size) setPageSize(Number(pagination.page_size));
  }, [pagination.page, pagination.page_size]);

  async function openOrder(orderId) {
    setPickedQuantities({});
    const loaded = await onLoadOrder(orderId);
    if (loaded) {
      await onPreviewPick(orderId);
    }
  }

  function updatePickedQuantity(line, rawValue) {
    const parsed = Number(rawValue);
    const maxQuantity = Number(line.recommended_pick_quantity || 0);
    const nextValue = Number.isFinite(parsed) ? Math.min(Math.max(parsed, 0), maxQuantity) : 0;
    setPickedQuantities((current) => ({ ...current, [line.order_line_id]: nextValue }));
  }

  function markAllPicked() {
    setPickedQuantities(Object.fromEntries(lines.map((line) => [line.order_line_id, Number(line.recommended_pick_quantity || 0)])));
  }

  async function confirmPick() {
    if (!order || quantityLines.length === 0) return;
    const result = await onCommitPick(order.id, quantityLines);
    if (result?.status === 'posted') {
      onLoadOrder(null);
    }
  }

  function toggleOrderSelection(orderId, checked) {
    if (loading) return;
    setSelectedOrderIds((current) => checked ? Array.from(new Set([...current, orderId])) : current.filter((id) => id !== orderId));
  }

  function toggleAllOrders(checked) {
    if (loading) return;
    setSelectedOrderIds(checked ? orders.map((candidate) => candidate.id) : []);
  }

  function searchOrders() {
    setPage(1);
    setSelectedOrderIds([]);
    onLoadOrders({ search, page: 1, pageSize });
  }

  function changePage(nextPage) {
    setPage(nextPage);
    setSelectedOrderIds([]);
    onLoadOrders({ search, page: nextPage, pageSize });
  }

  function changePageSize(nextPageSize) {
    setPageSize(nextPageSize);
    setPage(1);
    setSelectedOrderIds([]);
    onLoadOrders({ search, page: 1, pageSize: nextPageSize });
  }

  async function runPickBulkAction(action) {
    if (loading) return;
    const eligibleIds = orders
      .filter((candidate) => selectedOrderSet.has(candidate.id) && (action === 'pick' ? candidate.can_pick : Number(candidate.total_quantity_picked || 0) > 0))
      .map((candidate) => candidate.id);
    if (!eligibleIds.length) return;
    const confirmation = action === 'pick'
      ? `Pick all allocated quantities for ${eligibleIds.length} selected order(s)? This immediately reduces local stock.`
      : `Unpick ${eligibleIds.length} selected order(s)? Stock and allocation will be restored at the original pick locations.`;
    if (!window.confirm(confirmation)) return;
    setBulkBusy(true);
    setBulkMessage('');
    setBulkError('');
    try {
      const pickPayload = { order_ids: eligibleIds, lines: [], pick_strategy: 'allocated_first', allow_partial: false, created_by: 'system', notes: 'Bulk Pick Selected' };
      const unpickPayload = { order_ids: eligibleIds, created_by: 'system', reason: 'Bulk Unpick Selected from Pick Orders.' };
      const result = action === 'pick'
        ? await postJson('/api/picks/commit', withMutationIdempotency(bulkPickMutationRef, 'bulk-pick', pickPayload))
        : await postJson('/api/orders/bulk/unpick', withMutationIdempotency(bulkUnpickMutationRef, 'unpick', unpickPayload));
      if (!['posted', 'completed', 'partial'].includes(result.status)) throw new Error((result.errors || []).join(' ') || 'The bulk action was rejected.');
      const succeeded = result.succeeded_count ?? result.total_orders ?? eligibleIds.length;
      setBulkMessage(`${succeeded} selected order(s) ${action === 'pick' ? 'picked' : 'unpicked'}.`);
      if (result.errors?.length) setBulkError(result.errors.join(' '));
      setSelectedOrderIds([]);
      onLoadOrder(null);
      await onLoadOrders({ search, page, pageSize });
      if (action === 'pick') resetMutationIdempotency(bulkPickMutationRef);
      if (action === 'unpick') resetMutationIdempotency(bulkUnpickMutationRef);
    } catch (bulkActionError) {
      setBulkError(bulkActionError.message || 'Unable to complete the bulk pick action.');
    } finally {
      setBulkBusy(false);
    }
  }

  if (isDetailOpen) {
    return (
      <section className="orders-page pick-workspace pick-page-inline">
        <div className="pick-detail-card">
          <div className="pick-detail-toolbar">
            <button className="muted-button" onClick={() => onLoadOrder(null)} type="button">
              <ArrowLeft size={17} />
              Back to pick list
            </button>
            <div className="pick-detail-heading">
              <span>Order picking</span>
              <h2>Order {order.woo_order_number || order.woo_order_id}</h2>
            </div>
            <div className="pick-progress-pill" aria-live="polite">
              <strong>{formatNumber(totalPickedNow)}</strong>
              <span>picked now</span>
            </div>
          </div>

          <div className="pick-order-facts">
            <div><span>Customer</span><strong>{order.customer_name || '—'}</strong></div>
            <div><span>City</span><strong>{order.shipping_city || '—'}</strong></div>
            <div><span>State</span><strong>{order.shipping_state || '—'}</strong></div>
            <div><span>Shipping via</span><strong>{order.shipping_via || '—'}</strong></div>
            <div><span>Order total</span><strong>{formatCurrency(order.total)}</strong></div>
          </div>

          <div className="pick-safety-note">
            Enter the quantity physically picked for each product. Confirming reduces local In Stock and Allocated quantities and writes the stock-movement audit trail.
          </div>
          {loading && <div className="loading-strip">Updating pick...</div>}
          {error && <div className="api-error">{error}</div>}
          {commitSummary?.pick_id && <div className="success-strip">Pick {commitSummary.pick_number} posted: {formatNumber(commitSummary.total_quantity_picked)} unit(s) picked.</div>}

          <div className="pick-lines-table-wrap">
            <table className="data-table pick-lines-table">
              <caption>{lines.length} product line(s) in this order</caption>
              <thead>
                <tr>
                  <th>SKU</th>
                  <th>Product Title</th>
                  <th>Location</th>
                  <th>Ordered</th>
                  <th>Allocated</th>
                  <th>Already picked</th>
                  <th>Picked</th>
                </tr>
              </thead>
              <tbody>
                {lines.map((line) => (
                  <tr key={line.order_line_id}>
                    <td className="mono">{line.sku || '—'}</td>
                    <td className="pick-product-description">{line.description || 'Unnamed product'}</td>
                    <td><strong>{line.inventory_location || 'No location'}</strong><span className="table-subline">{line.warehouse || ''}</span></td>
                    <td>{formatNumber(line.quantity_ordered)}</td>
                    <td>{formatNumber(line.quantity_allocated)}</td>
                    <td>{formatNumber(line.quantity_previously_picked)}</td>
                    <td>
                      <label className="pick-quantity-field">
                        <span className="sr-only">Picked quantity for {line.description || line.sku}</span>
                        <input
                          aria-label={`Picked quantity for ${line.description || line.sku}`}
                          max={line.recommended_pick_quantity}
                          min="0"
                          onChange={(event) => updatePickedQuantity(line, event.target.value)}
                          step="1"
                          type="number"
                          value={pickedQuantities[line.order_line_id] ?? 0}
                        />
                        <small>max {formatNumber(line.recommended_pick_quantity)}</small>
                      </label>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="pick-confirm-bar">
            <button className="muted-button" disabled={loading || lines.length === 0} onClick={markAllPicked} type="button">
              <ClipboardCheck size={17} />
              Mark all allocated
            </button>
            <span>{formatNumber(totalPickedNow)} unit(s) ready to confirm</span>
            <button className="primary-button" disabled={loading || quantityLines.length === 0} onClick={confirmPick} type="button">
              <CheckCircle2 size={17} />
              Confirm Pick
            </button>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="orders-page pick-workspace pick-page-inline">
      <div className="pick-list-panel">
        <div className="pick-list-search">
          <label className="field">
            <span>Order number or customer</span>
            <div className="input-with-icon">
              <Search size={18} />
              <input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, searchOrders)} placeholder="Search pick orders" type="search" />
            </div>
          </label>
          <button className="primary-button" disabled={loading} onClick={searchOrders} type="button">Search</button>
        </div>
        <BulkActionsBar
          actions={[
            {
              label: 'Pick Selected',
              icon: <ClipboardCheck size={17} />,
              disabled: !orders.some((candidate) => selectedOrderSet.has(candidate.id) && candidate.can_pick),
              onSelect: () => runPickBulkAction('pick'),
            },
            {
              label: 'Unpick Selected',
              icon: <RotateCcw size={17} />,
              disabled: !orders.some((candidate) => selectedOrderSet.has(candidate.id) && Number(candidate.total_quantity_picked || 0) > 0),
              onSelect: () => runPickBulkAction('unpick'),
              danger: true,
            },
          ]}
          busy={bulkBusy || loading}
          label="Pick Orders bulk actions"
          selectedCount={selectedOrderIds.length}
        />
        {loading && <div className="loading-strip">Loading pick orders...</div>}
        {error && <div className="api-error">{error}</div>}
        {bulkMessage && <div className="success-strip">{bulkMessage}</div>}
        {bulkError && <div className="api-error">{bulkError}</div>}
        <div className="pick-orders-table-wrap">
          <table className="data-table pick-orders-table">
            <caption>{pagination.total || 0} order(s) ready to pick</caption>
            <thead>
              <tr>
                <th><input aria-label="Select all pick orders" checked={orders.length > 0 && orders.every((candidate) => selectedOrderSet.has(candidate.id))} disabled={loading} onChange={(event) => toggleAllOrders(event.target.checked)} type="checkbox" /></th>
                <th><span className="sr-only">Open</span></th>
                <th>Order number</th>
                <th>Placed on</th>
                <th>Customer</th>
                <th>City</th>
                <th>Shipping via</th>
                <th>Order total</th>
                <th>Ordered</th>
                <th>Picked</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((pickOrder) => (
                <tr key={pickOrder.id}>
                  <td className="bulk-select-cell"><input aria-label={`Select order ${pickOrder.woo_order_number || pickOrder.woo_order_id}`} checked={selectedOrderSet.has(pickOrder.id)} disabled={loading} onChange={(event) => toggleOrderSelection(pickOrder.id, event.target.checked)} type="checkbox" /></td>
                  <td>
                    <button className="pick-open-button" aria-label={`Open order ${pickOrder.woo_order_number || pickOrder.woo_order_id} for picking`} disabled={loading} onClick={() => openOrder(pickOrder.id)} type="button">
                      <ChevronRight size={20} />
                    </button>
                  </td>
                  <td className="mono pick-order-number">{pickOrder.woo_order_number || pickOrder.woo_order_id}</td>
                  <td>{formatDateTime(pickOrder.date_created)}</td>
                  <td>{pickOrder.customer_name || '—'}</td>
                  <td>{pickOrder.shipping_city || '—'}</td>
                  <td>{pickOrder.shipping_via || '—'}</td>
                  <td>{formatCurrency(pickOrder.total)}</td>
                  <td>{formatNumber(pickOrder.total_quantity_ordered)}</td>
                  <td>{formatNumber(pickOrder.total_quantity_picked)}</td>
                </tr>
              ))}
              {orders.length === 0 && <tr><td colSpan={10}><div className="empty-table-row">No orders are ready to pick.</div></td></tr>}
            </tbody>
          </table>
        </div>
        <OrdersPager count={pagination.total || 0} page={page} pageCount={pageCount} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={changePageSize} />
      </div>
    </section>
  );
}

function AllocationExceptionsPage({ onRefreshOperationalOrders }) {
  const emptyData = {
    lines: [],
    item_groups: [],
    total_orders: 0,
    total_lines: 0,
    total_quantity_unallocated: 0,
    lines_with_available_stock: 0,
    lines_out_of_stock: 0,
    view: 'items',
    total_item_groups: 0,
    returned_item_groups: 0,
    page: 1,
    page_size: 20,
    total_pages: 1,
    returned_count: 0,
    has_previous: false,
    has_next: false,
    warehouses: [],
  };
  const emptyFilters = { search: '', warehouse: '', orderedFrom: '', orderedTo: '', includeFullyAllocated: false };
  const [data, setData] = useState(emptyData);
  const [filters, setFilters] = useState(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [tab, setTab] = useState('items');
  const [focusedItemGroup, setFocusedItemGroup] = useState(null);
  const [adjustingLine, setAdjustingLine] = useState(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const requestIdRef = useRef(0);
  const abortControllerRef = useRef(null);

  useEffect(() => {
    loadExceptions(emptyFilters, 1, 20, 'items');
    return () => {
      abortControllerRef.current?.abort();
      abortControllerRef.current = null;
      requestIdRef.current += 1;
    };
  }, []);

  async function loadExceptions(nextFilters = appliedFilters, nextPage = page, nextPageSize = pageSize, nextView = data.view || tab, nextItemGroup = focusedItemGroup) {
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;
    setLoading(true);
    setError('');
    try {
      const response = await apiFetch(`${API_BASE_URL}/api/allocations/exceptions${plainFiltersToQueryString({
        ...allocationExceptionFiltersToApi(nextFilters),
        view: nextView,
        page: nextPage,
        page_size: nextPageSize,
        item_id: nextItemGroup?.item_id || undefined,
        unmatched_line_id: nextItemGroup?.unmatched_line_id || undefined,
      })}`, { signal: controller.signal });
      if (!response.ok) throw new Error(`Allocation exceptions API returned ${response.status}`);
      const body = await response.json();
      if (requestId !== requestIdRef.current) return;
      const responseView = body.view === 'orders' ? 'orders' : 'items';
      const responsePageSize = Math.max(1, Number(body.page_size) || nextPageSize || 20);
      const totalResults = responseView === 'items' ? Number(body.total_item_groups || 0) : Number(body.total_lines || 0);
      const totalPages = Math.max(1, Number(body.total_pages) || Math.ceil(totalResults / responsePageSize));
      const responsePage = Math.min(totalPages, Math.max(1, Number(body.page) || nextPage || 1));
      setData((current) => ({
        ...emptyData,
        ...body,
        lines: body.lines || [],
        item_groups: body.item_groups || [],
        view: responseView,
        total_item_groups: body.total_item_groups ?? 0,
        returned_item_groups: body.returned_item_groups ?? (responseView === 'items' ? (body.item_groups || groupAllocationExceptionItems(body.lines || [])).length : 0),
        page: responsePage,
        page_size: responsePageSize,
        total_pages: totalPages,
        returned_count: body.returned_count ?? (body.lines || []).length,
        has_previous: body.has_previous ?? responsePage > 1,
        has_next: body.has_next ?? responsePage < totalPages,
        warehouses: Array.isArray(body.warehouses) ? body.warehouses : current.warehouses,
      }));
      setPage(responsePage);
      setPageSize(responsePageSize);
    } catch (loadError) {
      if (loadError?.name !== 'AbortError' && requestId === requestIdRef.current) {
        setError(loadError.message || 'Unable to load allocation exceptions.');
      }
    } finally {
      if (requestId === requestIdRef.current) {
        abortControllerRef.current = null;
        setLoading(false);
      }
    }
  }

  async function runFifoAllocation() {
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const result = await postJson('/api/allocations/auto/commit', {});
      setMessage(`${formatNumber(result.total_quantity_allocated)} unit(s) reserved in first-come-first-served order. ${result.allocated_orders} order(s) became fully allocated.`);
      await loadExceptions(appliedFilters, page, pageSize, data.view || tab, focusedItemGroup);
      await onRefreshOperationalOrders?.();
    } catch (allocationRunError) {
      setError(allocationRunError.message || 'Unable to run FIFO allocation.');
      setLoading(false);
    }
  }

  async function stockSaved(result) {
    setAdjustingLine(null);
    setMessage(`Stock updated${result?.adjustment_number ? ` with ${result.adjustment_number}` : ''}; FIFO allocation was retried automatically.`);
    await loadExceptions(appliedFilters, page, pageSize, data.view || tab, focusedItemGroup);
    await onRefreshOperationalOrders?.();
  }

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function clearFilters() {
    setFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setFocusedItemGroup(null);
    loadExceptions(emptyFilters, 1, pageSize, tab, null);
  }

  function applyFilters() {
    setAppliedFilters(filters);
    setFocusedItemGroup(null);
    loadExceptions(filters, 1, pageSize, tab, null);
  }

  function changePage(nextPage) {
    loadExceptions(appliedFilters, nextPage, pageSize, data.view || tab, focusedItemGroup);
  }

  function changePageSize(nextPageSize) {
    loadExceptions(appliedFilters, 1, nextPageSize, data.view || tab, focusedItemGroup);
  }

  async function exportResults() {
    setExporting(true);
    setError('');
    try {
      await exportAllocationExceptionsCsv(appliedFilters);
    } catch (exportError) {
      setError(exportError.message || 'Unable to export allocation exceptions.');
    } finally {
      setExporting(false);
    }
  }

  function showAffectedOrders(group) {
    setFocusedItemGroup(group);
    setTab('orders');
    loadExceptions(appliedFilters, 1, pageSize, 'orders', group);
  }

  function switchView(nextView) {
    setFocusedItemGroup(null);
    setTab(nextView);
    loadExceptions(appliedFilters, 1, pageSize, nextView, null);
  }

  function showAllOrders() {
    switchView('orders');
  }

  const groupedItems = data.item_groups?.length ? data.item_groups : groupAllocationExceptionItems(data.lines || []);
  const visibleOrderLines = data.lines || [];
  const warehouses = data.warehouses || [];
  const pageCount = Math.max(1, data.total_pages || 1);
  const pagerCount = data.view === 'items' ? data.total_item_groups || 0 : data.total_lines || 0;
  const pagerNoun = data.view === 'items' ? 'item shortages' : 'allocation lines';
  const busy = loading || exporting;

  return (
    <div className="allocation-exceptions-workspace">
      <div className="wide-panel allocation-exceptions-header">
        <div className="panel-title">
          <div>
            <h2>Allocate Orders</h2>
            <p>Available stock is reserved automatically for WooCommerce processing orders, oldest order first.</p>
          </div>
          <div className="button-row compact">
            <button className="muted-button" onClick={() => loadExceptions(appliedFilters, page, pageSize, data.view || tab, focusedItemGroup)} disabled={busy} type="button"><RefreshCw size={17} />Refresh</button>
            <button className="action-button" onClick={exportResults} disabled={busy || !data.total_lines} type="button"><Download size={17} />{exporting ? 'Exporting...' : 'Export Results'}</button>
            <button className="primary-button" onClick={runFifoAllocation} disabled={busy} type="button"><CheckCircle2 size={17} />Run FIFO Allocation</button>
          </div>
        </div>

        {data.total_orders > 0 && (
          <div className="allocation-failure-alert" role="status">
            <div className="allocation-failure-icon"><TriangleAlert size={22} /></div>
            <div>
              <strong>{data.total_orders} order(s) could not be fully auto-allocated</strong>
              <span>Only the unresolved item quantities are listed below. Fully allocated orders move directly to Pick Orders.</span>
            </div>
            <button className="muted-button" disabled={busy} onClick={() => switchView('items')} type="button">Review shortages</button>
          </div>
        )}

        <div className="summary-strip allocation-exception-summary">
          <Metric label="Orders Waiting" value={data.total_orders || 0} />
          <Metric label="Exception Lines" value={data.total_lines || 0} />
          <Metric label="Units Unallocated" value={formatNumber(data.total_quantity_unallocated)} />
          <Metric label="Stock Available" value={data.lines_with_available_stock || 0} />
          <Metric label="Out of Stock" value={data.lines_out_of_stock || 0} />
        </div>

        <div className="allocation-view-tabs" role="tablist" aria-label="Allocation exception views">
          <button className={tab === 'orders' ? 'active' : ''} disabled={busy} onClick={() => switchView('orders')} role="tab" aria-selected={tab === 'orders'} type="button">Orders <span>{data.total_orders || 0}</span></button>
          <button className={tab === 'items' ? 'active' : ''} disabled={busy} onClick={() => switchView('items')} role="tab" aria-selected={tab === 'items'} type="button">Items <span>{data.total_item_groups || 0}</span></button>
        </div>

        <div className="filter-panel allocation-exception-filters">
          <div className="filter-grid">
            <label className="field"><span>Item, order, SKU or barcode</span><div className="input-with-icon"><Search size={18} /><input disabled={busy} value={filters.search} onChange={(event) => updateFilter('search', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, applyFilters)} placeholder="Scan or search" /></div></label>
            <label className="field"><span>Ordered From</span><input disabled={busy} type="date" value={filters.orderedFrom} onChange={(event) => updateFilter('orderedFrom', event.target.value)} /></label>
            <label className="field"><span>Ordered To</span><input disabled={busy} type="date" value={filters.orderedTo} onChange={(event) => updateFilter('orderedTo', event.target.value)} /></label>
            <FilterSelect label="Ship From" value={filters.warehouse} options={warehouses} disabled={busy} onChange={(value) => updateFilter('warehouse', value)} />
          </div>
          <div className="allocation-filter-footer">
            <label className="check-field"><input checked={filters.includeFullyAllocated} disabled={busy} onChange={(event) => updateFilter('includeFullyAllocated', event.target.checked)} type="checkbox" />Include 100% allocated items in list</label>
            <div className="button-row"><button className="muted-button" disabled={busy} onClick={clearFilters} type="button">Clear</button><button className="primary-button" onClick={applyFilters} disabled={busy} type="button"><Filter size={17} />Filter</button></div>
          </div>
        </div>
        {loading && <div className="loading-strip">Reconciling allocation exceptions...</div>}
        {error && <div className="api-error">{error}</div>}
        {message && <div className="success-strip">{message}</div>}
      </div>

      {tab === 'items' ? (
        <AllocationExceptionItemsTable groups={groupedItems} loading={busy} onViewOrders={showAffectedOrders} onAdjustStock={setAdjustingLine} onAllocate={runFifoAllocation} />
      ) : (
        <AllocationExceptionOrdersTable lines={visibleOrderLines} focused={Boolean(focusedItemGroup)} loading={busy} onClearFocus={showAllOrders} onAdjustStock={setAdjustingLine} onAllocate={runFifoAllocation} />
      )}
      <OrdersPager count={pagerCount} disabled={busy} noun={pagerNoun} page={page} pageCount={pageCount} pageSize={pageSize} onPageChange={changePage} onPageSizeChange={changePageSize} />
      {adjustingLine && <AllocationStockModal line={adjustingLine} onClose={() => setAdjustingLine(null)} onSaved={stockSaved} />}
    </div>
  );
}

function AllocationExceptionItemsTable({ groups, loading, onViewOrders, onAdjustStock, onAllocate }) {
  return (
    <TableShell caption={`${groups.length} item exception(s)`} columns={['Actions', 'SKU / Barcode', 'Product Title', 'Affected Orders', 'Ordered', 'Allocated', 'Unallocated', 'Picked', 'Available', 'Reason']} className="allocation-exception-table" showActionBand={false}>
      {groups.map((group) => (
        <tr key={group.key}>
          <td><AllocationExceptionActions label={group.sku || group.barcode || group.description} canAdjust={Boolean(group.item_id)} canAllocate={group.quantity_available > 0} disabled={loading} onView={() => onViewOrders(group)} onAdjust={() => onAdjustStock(group)} onAllocate={onAllocate} /></td>
          <td><strong className="mono">{group.sku || 'Unmatched'}</strong><span className="table-subline mono">{group.barcode || ''}</span></td>
          <td className="description-cell"><ClampedText value={group.description} /></td>
          <td>{group.affected_order_count}</td>
          <td>{formatNumber(group.quantity_ordered)}</td>
          <td>{formatNumber(group.quantity_allocated)}</td>
          <td><strong className="allocation-shortage-number">{formatNumber(group.quantity_unallocated)}</strong></td>
          <td>{formatNumber(group.quantity_picked)}</td>
          <td>{formatNumber(group.quantity_available)}</td>
          <td>{StatusText(group.exception_reason || group.reason_codes?.[0])}</td>
        </tr>
      ))}
      {!groups.length && <tr><td colSpan={10}><div className="empty-table-row">All processing orders are fully allocated. Nothing needs attention.</div></td></tr>}
    </TableShell>
  );
}

function AllocationExceptionOrdersTable({ lines, focused, loading, onClearFocus, onAdjustStock, onAllocate }) {
  return (
    <div className="allocation-order-lines-panel">
      {focused && <div className="focused-allocation-filter"><span>Showing affected orders for one item.</span><button className="muted-button" disabled={loading} onClick={onClearFocus} type="button">Show all orders</button></div>}
      <TableShell caption={`${lines.length} unresolved order line(s)`} columns={['Actions', 'Order', 'Placed On', 'Customer', 'SKU / Barcode', 'Product Title', 'Ordered', 'Allocated', 'Unallocated', 'Picked', 'Available', 'Reason']} className="allocation-exception-table allocation-orders-table" showActionBand={false}>
        {lines.map((line) => (
          <tr key={line.order_line_id}>
            <td><AllocationExceptionActions label={line.woo_order_number} canAdjust={Boolean(line.item_id)} canAllocate={line.quantity_available > 0} disabled={loading} onView={() => { window.location.hash = '#/orders/open'; }} onAdjust={() => onAdjustStock(line)} onAllocate={onAllocate} /></td>
            <td className="mono">{line.woo_order_number || line.woo_order_id}</td>
            <td>{formatDateTime(line.ordered_at)}</td>
            <td>{line.customer_name}</td>
            <td><strong className="mono">{line.sku || 'Unmatched'}</strong><span className="table-subline mono">{line.barcode || ''}</span></td>
            <td className="description-cell"><ClampedText value={line.description} /></td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_allocated)}</td>
            <td><strong className="allocation-shortage-number">{formatNumber(line.quantity_unallocated)}</strong></td>
            <td>{formatNumber(line.quantity_picked)}</td>
            <td>{formatNumber(line.quantity_available)}</td>
            <td>{StatusText(line.exception_reason)}</td>
          </tr>
        ))}
        {!lines.length && <tr><td colSpan={12}><div className="empty-table-row">No processing orders have unresolved allocation lines.</div></td></tr>}
      </TableShell>
    </div>
  );
}

function AllocationExceptionActions({ label, canAdjust, canAllocate, disabled = false, onView, onAdjust, onAllocate }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const actions = [
    { label: 'View affected orders', icon: Search, enabled: true, run: onView },
    { label: 'Update stock levels', icon: SlidersHorizontal, enabled: canAdjust, run: onAdjust },
    { label: 'Allocate available stock', icon: CheckCircle2, enabled: canAllocate, run: onAllocate },
  ];
  return (
    <div className="order-actions-menu">
      <button ref={triggerRef} className="order-actions-trigger" onClick={() => setOpen((value) => !value)} aria-label={`Open allocation actions for ${label || 'exception'}`} aria-haspopup="menu" aria-expanded={open} disabled={disabled} type="button"><EllipsisVertical size={20} /></button>
      <FloatingMenu align="end" className="order-actions-popover allocation-actions-popover" onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>{actions.map((action) => { const Icon = action.icon; return <button key={action.label} disabled={disabled || !action.enabled} onClick={() => { setOpen(false); action.run?.(); }} role="menuitem" type="button"><Icon size={16} />{action.label}</button>; })}</FloatingMenu>
    </div>
  );
}

function AllocationStockModal({ line, onClose, onSaved }) {
  const mutationRef = useRef(null);
  const [locations, setLocations] = useState([]);
  const [locationId, setLocationId] = useState('');
  const [warehouse, setWarehouse] = useState(line.warehouse || 'Main Warehouse');
  const [locationName, setLocationName] = useState(line.inventory_location || 'Receiving');
  const [newQuantity, setNewQuantity] = useState('');
  const [reason, setReason] = useState('Stock found during allocation review');
  const [notes, setNotes] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    apiFetch(`${API_BASE_URL}/api/inventory/locations?item_id=${line.item_id}&page=1&page_size=100`)
      .then((response) => { if (!response.ok) throw new Error('Unable to load item locations.'); return response.json(); })
      .then((body) => {
        if (!active) return;
        const rows = body.rows || [];
        setLocations(rows);
        if (rows[0]) {
          setLocationId(String(rows[0].id));
          setNewQuantity(String(rows[0].in_stock ?? 0));
        } else {
          setNewQuantity('0');
        }
      })
      .catch((loadError) => { if (active) setError(loadError.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [line.item_id]);

  const selected = locations.find((row) => String(row.id) === String(locationId));
  const currentQuantity = toNumber(selected?.in_stock);
  const quantityChange = toNumber(newQuantity) - currentQuantity;

  function selectLocation(value) {
    setLocationId(value);
    const row = locations.find((candidate) => String(candidate.id) === String(value));
    if (row) setNewQuantity(String(row.in_stock ?? 0));
  }

  async function commit() {
    if (newQuantity === '' || !Number.isFinite(Number(newQuantity)) || toNumber(newQuantity) < 0) {
      setError('Enter a valid final stock quantity of zero or more.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      let result;
      if (selected) {
        const payload = {
          adjustment_type: quantityChange < 0 ? 'manual_decrease' : 'manual_increase',
          reason: reason || null,
          notes: notes || null,
          created_by: 'allocation-review',
          lines: [{ item_id: line.item_id, inventory_item_location_id: selected.id, new_quantity: toNumber(newQuantity), notes: notes || null }],
        };
        result = await postJson('/api/inventory/adjustments', withMutationIdempotency(mutationRef, 'allocation-adjustment', payload));
      } else {
        const payload = {
          scan_input: line.sku || line.barcode,
          warehouse,
          inventory_location: locationName,
          new_quantity: toNumber(newQuantity),
          adjustment_type: 'manual_increase',
          reason,
          notes: notes || null,
          created_by: 'allocation-review',
        };
        result = await postJson('/api/scanner/adjustments/commit', withMutationIdempotency(mutationRef, 'allocation-scanner-adjustment', payload));
      }
      await onSaved(result);
      resetMutationIdempotency(mutationRef);
    } catch (commitError) {
      setError(commitError.message || 'Unable to update stock.');
      setLoading(false);
    }
  }

  return (
    <BodyPortal><div className="modal-backdrop" role="presentation">
      <section className="import-modal allocation-stock-modal" role="dialog" aria-modal="true" aria-label="Update stock levels">
        <div className="modal-header"><div><h2>Update Stock Levels</h2><p>{line.sku || line.barcode} · {decodeHtmlEntities(line.description || '')}</p></div><button className="icon-button modal-close" onClick={onClose} aria-label="Close stock adjustment" type="button"><X size={20} /></button></div>
        <div className="allocation-stock-warning"><TriangleAlert size={18} /><span>This creates an audited stock adjustment. Enter only stock that is physically present.</span></div>
        <div className="form-grid">
          {locations.length ? <label className="field wide-field"><span>Location</span><select value={locationId} onChange={(event) => selectLocation(event.target.value)}>{locations.map((row) => <option key={row.id} value={row.id}>{row.warehouse} / {row.inventory_location} · {formatNumber(row.in_stock)} in stock</option>)}</select></label> : <><label className="field"><span>Warehouse</span><input value={warehouse} onChange={(event) => setWarehouse(event.target.value)} /></label><label className="field"><span>New Stock Location</span><input value={locationName} onChange={(event) => setLocationName(event.target.value)} /></label></>}
          <label className="field"><span>Current Stock</span><input value={formatNumber(currentQuantity)} disabled /></label>
          <label className="field"><span>New Stock Quantity</span><input type="number" min="0" step="0.001" value={newQuantity} onChange={(event) => setNewQuantity(event.target.value)} /></label>
          <label className="field wide-field"><span>Reason (optional)</span><input value={reason} onChange={(event) => setReason(event.target.value)} /></label>
          <label className="field wide-field"><span>Note</span><textarea value={notes} onChange={(event) => setNotes(event.target.value)} /></label>
        </div>
        {loading && <div className="loading-strip">Loading stock levels...</div>}
        {error && <div className="api-error">{error}</div>}
        <div className="detail-actions"><button className="muted-button" onClick={onClose} type="button">Cancel</button><button className="primary-button" onClick={commit} disabled={loading || !newQuantity} type="button"><Save size={16} />Update and Auto-Allocate</button></div>
      </section>
    </div></BodyPortal>
  );
}

function allocationItemKey(line) {
  return line.item_id ? `item:${line.item_id}` : `unmatched:${line.order_line_id}`;
}

function groupAllocationExceptionItems(lines) {
  const groups = new Map();
  lines.forEach((line) => {
    const key = allocationItemKey(line);
    const group = groups.get(key) || { key, item_id: line.item_id, sku: line.sku, barcode: line.barcode, description: line.description, quantity_ordered: 0, quantity_allocated: 0, quantity_unallocated: 0, quantity_picked: 0, quantity_available: 0, affectedOrders: new Set(), reason_codes: [], lines: [] };
    group.quantity_ordered += toNumber(line.quantity_ordered);
    group.quantity_allocated += toNumber(line.quantity_allocated);
    group.quantity_unallocated += toNumber(line.quantity_unallocated);
    group.quantity_picked += toNumber(line.quantity_picked);
    group.quantity_available = Math.max(group.quantity_available, toNumber(line.quantity_available));
    group.affectedOrders.add(line.order_id);
    if (!group.reason_codes.includes(line.exception_reason)) group.reason_codes.push(line.exception_reason);
    group.lines.push(line);
    groups.set(key, group);
  });
  return [...groups.values()].map((group) => ({ ...group, affected_order_count: group.affectedOrders.size }));
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

function printVisibleRoot(bodyClass) {
  document.body.classList.add(bodyClass);
  window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
    try {
      window.print();
    } finally {
      document.body.classList.remove(bodyClass);
    }
  }));
}

function BulkActionsBar({ selectedCount, actions, busy = false, label = 'Bulk actions' }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  return (
    <div className="bulk-actions-bar">
      <div>
        <strong>{label}</strong>
        <span>{selectedCount ? `${selectedCount} order${selectedCount === 1 ? '' : 's'} selected` : 'Select one or more orders'}</span>
      </div>
      <div className="bulk-actions-menu">
        <button ref={triggerRef} aria-expanded={open} aria-haspopup="menu" className="bulk-actions-trigger" disabled={busy} onClick={() => setOpen((current) => !current)} type="button">
          Actions
          <ChevronDown size={18} />
        </button>
        <FloatingMenu align="end" className="bulk-actions-popover" onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>
            {actions.map((action) => (
              <button
                className={action.danger ? 'danger-action' : ''}
                disabled={busy || selectedCount === 0 || action.disabled}
                key={action.label}
                onClick={() => {
                  setOpen(false);
                  action.onSelect();
                }}
                role="menuitem"
                type="button"
              >
                {action.icon}
                <span>{action.label}</span>
              </button>
            ))}
        </FloatingMenu>
      </div>
    </div>
  );
}

function InvoiceAddress({ label, address, fallbackName, fallbackEmail, fallbackPhone }) {
  const details = address || {};
  const name = [details.first_name, details.last_name].filter(Boolean).join(' ') || fallbackName || 'Customer';
  const cityLine = [details.city, details.state, details.postcode].filter(Boolean).join(', ');
  return (
    <section className="invoice-address-block">
      <h2>{label}</h2>
      <strong>{name}</strong>
      {(details.company) && <span>{details.company}</span>}
      {(details.address_1) && <span>{details.address_1}</span>}
      {(details.address_2) && <span>{details.address_2}</span>}
      {cityLine && <span>{cityLine}</span>}
      {(details.country) && <span>{details.country}</span>}
      {(details.email || fallbackEmail) && <span>{details.email || fallbackEmail}</span>}
      {(details.phone || fallbackPhone) && <span>{details.phone || fallbackPhone}</span>}
    </section>
  );
}

export function OrderInvoice({ order, className = '' }) {
  if (!order) return null;
  const orderNumber = order.woo_order_number || order.woo_order_id || order.id;
  const paymentMethod = order.payment_method_title || order.payment_method || 'Not provided';
  const invoiceStatus = titleize(normalizeWooStatus(order.woo_status || order.status || order.local_status || order.completion_status) || 'unknown');
  return (
    <article className={`order-invoice ${className}`.trim()} aria-label={`Invoice for order ${orderNumber}`}>
      <header className="invoice-masthead">
        <div className="invoice-brand">
          <img className="invoice-logo" src="/pongo-logo.png" alt="Pongo Pet Supplies" />
        </div>
        <div className="invoice-title">
          <span>Invoice</span>
          <h1>Order #{orderNumber}</h1>
        </div>
      </header>

      <section className="invoice-reference-grid" aria-label="Order and payment details">
        <div><span>Order date</span><strong>{formatDateTime(order.date_created)}</strong></div>
        <div><span>Order status</span><strong>{invoiceStatus}</strong></div>
        <div><span>Payment</span><strong>{paymentMethod}</strong></div>
        <div><span>Ship via</span><strong>{order.shipping_via || 'Not provided'}</strong></div>
      </section>

      <div className="invoice-address-grid">
        <InvoiceAddress
          label="Billing details"
          address={order.billing_summary}
          fallbackName={order.customer_name}
          fallbackEmail={order.customer_email}
          fallbackPhone={order.customer_phone}
        />
        <InvoiceAddress
          label="Shipping details"
          address={order.shipping_summary}
          fallbackName={order.customer_name}
          fallbackEmail={order.customer_email}
          fallbackPhone={order.customer_phone}
        />
      </div>

      <table className="invoice-lines-table">
        <thead>
          <tr><th>SKU / barcode</th><th>Item</th><th>Qty</th><th>Unit price</th><th>Tax</th><th>Line total</th></tr>
        </thead>
        <tbody>
          {(order.lines || []).map((line) => {
            const substitution = line.substitution || {};
            const invoiceSku = line.sku || substitution.original_sku || line.substituted_from_sku;
            const invoiceName = line.name || substitution.original_name || line.substituted_from_name;
            const invoiceBarcode = line.barcode || substitution.original_barcode || line.substituted_from_barcode;
            return <tr key={line.id}>
              <td><strong>{invoiceSku || '—'}</strong><span>{invoiceBarcode || ''}</span></td>
              <td><strong>{decodeHtmlEntities(invoiceName || 'Unnamed product')}</strong></td>
              <td>{formatNumber(line.quantity_ordered)}</td>
              <td>{formatCurrency(line.unit_price)}</td>
              <td>{formatCurrency(line.line_tax)}</td>
              <td>{formatCurrency(line.line_total)}</td>
            </tr>;
          })}
          {!order.lines?.length && <tr><td colSpan="6">No line items were returned for this order.</td></tr>}
        </tbody>
      </table>

      <section className="invoice-closing-grid">
        <div className="invoice-notes">
          <h2>Order notes</h2>
          <p>{order.customer_note || 'No delivery notes were provided.'}</p>
        </div>
        <dl className="invoice-totals">
          <div><dt>Subtotal</dt><dd>{formatCurrency(order.subtotal)}</dd></div>
          <div><dt>Discount</dt><dd>{order.discount_total ? `−${formatCurrency(order.discount_total)}` : formatCurrency(0)}</dd></div>
          <div><dt>Shipping</dt><dd>{formatCurrency(order.shipping_total ?? 0)}</dd></div>
          <div><dt>Tax</dt><dd>{formatCurrency(order.tax_total ?? 0)}</dd></div>
          <div className="invoice-grand-total"><dt>Total</dt><dd>{formatCurrency(order.total)}</dd></div>
        </dl>
      </section>

      <footer className="invoice-footer">
        <span>Pongo Pet Supplies · pongo.ca</span>
        <span>Order #{orderNumber}</span>
      </footer>
    </article>
  );
}

function BulkPrintSheet({ orders }) {
  if (!orders.length || typeof document === 'undefined') return null;
  return createPortal(
    <section className="bulk-print-sheet" aria-label="Selected customer invoices">
      {orders.map((order) => <OrderInvoice key={order.id} order={order} />)}
    </section>,
    document.body,
  );
}

function OrdersPager({ count, page, pageCount, pageSize, onPageChange, onPageSizeChange, noun = 'orders', disabled = false }) {
  const first = count === 0 ? 0 : ((page - 1) * pageSize) + 1;
  const last = Math.min(page * pageSize, count);
  return (
    <div className="zen-orders-pager">
      <span>Showing {formatNumber(first)}–{formatNumber(last)} of {formatNumber(count)} {noun}</span>
      <div>
        <label>
          <span className="sr-only">Rows per page</span>
          <select aria-label="Rows per page" disabled={disabled} onChange={(event) => onPageSizeChange(Number(event.target.value))} value={pageSize}>
            {[20, 50, 100].map((size) => <option key={size} value={size}>{size}</option>)}
          </select>
        </label>
        <button aria-label={`Previous ${noun} page`} disabled={disabled || page <= 1} onClick={() => onPageChange(page - 1)} type="button"><ChevronLeft size={20} /></button>
        <span>Page {formatNumber(page)} of {formatNumber(pageCount)}</span>
        <button aria-label={`Next ${noun} page`} disabled={disabled || page >= pageCount} onClick={() => onPageChange(page + 1)} type="button"><ChevronRight size={20} /></button>
      </div>
    </div>
  );
}

function OpenOrdersTable({ orders, onSelect, renderActions, selectable = false, selectedIds = new Set(), selectionDisabled = false, onToggleSelection, onToggleAll }) {
  const allSelected = orders.length > 0 && orders.every((order) => selectedIds.has(order.id));
  return (
    <table className="zen-orders-table">
        <thead>
          <tr>
            <th><span className="sr-only">Order actions</span></th>
            <th>Order Number</th>
            <th>Placed On</th>
            <th>Customer</th>
            <th>City</th>
            <th>Ship Via</th>
            <th>Order Total</th>
            <th>SKU</th>
            <th>Ordered</th>
            <th>Picked</th>
            {selectable && <th><input aria-label="Select all open orders" checked={allSelected} disabled={selectionDisabled} onChange={(event) => onToggleAll?.(event.target.checked)} type="checkbox" /></th>}
          </tr>
        </thead>
        <tbody>
          {orders.map((order) => (
            <tr key={order.id} onDoubleClick={() => { if (!selectionDisabled) onSelect(order.id); }}>
              <td className="order-actions-cell">{renderActions?.(order)}</td>
              <td className="mono open-order-number" data-label="Order Number">{order.woo_order_number || order.woo_order_id}</td>
              <td data-label="Placed On">{formatDateTime(order.date_created)}</td>
              <td data-label="Customer">{order.customer_name || '—'}</td>
              <td data-label="City">{order.shipping_city || '—'}</td>
              <td data-label="Ship Via">{order.shipping_via || '—'}</td>
              <td data-label="Order Total">{formatCurrency(order.total)}</td>
              <td className="mono" data-label="SKU">{(order.skus || []).length > 1 ? '(Multiple)' : (order.skus || [])[0] || '—'}</td>
              <td data-label="Ordered">{formatNumber(order.total_quantity_ordered)}</td>
              <td data-label="Picked">{formatNumber(order.total_quantity_picked)}</td>
              {selectable && (
                <td className="bulk-select-cell">
                  <input aria-label={`Select order ${order.woo_order_number || order.woo_order_id}`} checked={selectedIds.has(order.id)} disabled={selectionDisabled} onChange={(event) => onToggleSelection?.(order.id, event.target.checked)} type="checkbox" />
                </td>
              )}
            </tr>
          ))}
          {orders.length === 0 && <tr className="zen-orders-empty-row"><td colSpan={selectable ? 11 : 10}><div className="empty-table-row">No open customer orders match the current filters.</div></td></tr>}
        </tbody>
      </table>
  );
}

function openOrderState(order) {
  if (order.pick_status === 'picked') return 'picked';
  if (order.pick_status === 'partially_picked') return 'partially picked';
  return 'not picked';
}

function OrderActionsMenu({ order, disabled, onView, onEdit, onPrint, onComplete, onUnpick, onTimeline }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const orderNumber = order.woo_order_number || order.woo_order_id;

  const actions = [
    { label: 'View order', icon: Search, onClick: onView },
    { label: 'Edit order', icon: Edit3, onClick: onEdit },
    { label: 'Print order', icon: Printer, onClick: onPrint },
    { label: 'Complete order', icon: CheckCircle2, onClick: onComplete, danger: true },
    { label: 'Unpick', icon: RotateCcw, onClick: onUnpick, disabled: Number(order.total_quantity_picked || 0) <= 0 },
    { label: 'View timeline', icon: CalendarDays, onClick: onTimeline },
  ];
  return (
    <div className="order-actions-menu">
      <button ref={triggerRef} className="order-actions-trigger" onClick={() => setOpen((current) => !current)} aria-label={`Open actions for order ${orderNumber}`} aria-haspopup="menu" aria-expanded={open} disabled={disabled} type="button">
        <ClipboardList size={20} />
      </button>
      <FloatingMenu align="end" className="order-actions-popover" onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>
          {actions.map((action) => {
            const Icon = action.icon;
            return (
              <button className={action.danger ? 'danger-action' : ''} disabled={action.disabled} key={action.label} onClick={() => { setOpen(false); action.onClick(); }} role="menuitem" type="button">
                <Icon size={16} />
                {action.label}
              </button>
            );
          })}
      </FloatingMenu>
    </div>
  );
}

function orderLineSubstitution(line = {}) {
  const substitution = line.substitution || {};
  const effectiveSku = line.effective_sku || substitution.replacement_sku || line.replacement_sku || '';
  const effectiveName = line.effective_name || substitution.replacement_name || line.replacement_name || '';
  const substituted = Boolean(
    line.is_substituted
    || line.substituted
    || line.substituted_from_item_id
    || substitution.original_item_id
    || substitution.replacement_item_id,
  );
  if (!substituted) return null;
  return {
    originalSku: line.sku || substitution.original_sku || line.substituted_from_sku || line.original_sku || '',
    originalName: line.name || substitution.original_name || line.substituted_from_name || line.original_name || '',
    effectiveSku: effectiveSku || line.sku || '',
    effectiveName: effectiveName || line.name || '',
  };
}

function inventorySearchItemLabel(item = {}) {
  const candidate = item || {};
  return candidate.product_name || candidate.description || candidate.Description || 'Untitled inventory item';
}

function inventorySearchItemSku(item = {}) {
  const candidate = item || {};
  return candidate.sku || candidate.SKU || '';
}

function OpenOrderDetailPanel({ order, onClose, onPrint, onSubstitute = null, showPrint = true, statusActions = null, title = 'View Customer Order' }) {
  const dialogRef = useRef(null);
  const onCloseRef = useRef(onClose);
  const [substitutionLine, setSubstitutionLine] = useState(null);
  const [replacementQuery, setReplacementQuery] = useState('');
  const [replacementItem, setReplacementItem] = useState(null);
  const [substitutionReason, setSubstitutionReason] = useState('');
  const [substitutionBusy, setSubstitutionBusy] = useState(false);
  const [substitutionError, setSubstitutionError] = useState('');
  const [substitutionMessage, setSubstitutionMessage] = useState('');
  onCloseRef.current = onClose;

  useEffect(() => {
    const previousFocus = document.activeElement;
    window.requestAnimationFrame(() => dialogRef.current?.focus());
    function handleDialogKeys(event) {
      if (event.key === 'Escape') {
        if (event.target?.getAttribute?.('role') === 'combobox' && event.target.getAttribute('aria-expanded') === 'true') return;
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [href], [tabindex]:not([tabindex="-1"])')];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', handleDialogKeys);
    return () => {
      document.removeEventListener('keydown', handleDialogKeys);
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  useEffect(() => {
    setSubstitutionLine(null);
    setReplacementQuery('');
    setReplacementItem(null);
    setSubstitutionReason('');
    setSubstitutionError('');
    setSubstitutionMessage('');
  }, [order?.id]);

  function beginSubstitution(line) {
    setSubstitutionLine(line);
    setReplacementQuery('');
    setReplacementItem(null);
    setSubstitutionReason('');
    setSubstitutionError('');
    setSubstitutionMessage('');
  }

  async function commitSubstitution() {
    const replacementId = replacementItem?.id;
    const reason = substitutionReason.trim();
    if (!replacementId) {
      setSubstitutionError('Choose the replacement inventory item.');
      return;
    }
    if (!reason) {
      setSubstitutionError('Enter a reason for this substitution.');
      return;
    }
    if (Number(replacementId) === Number(substitutionLine?.inventory_item_id || substitutionLine?.item_id)) {
      setSubstitutionError('Choose a different inventory item from the current product.');
      return;
    }
    const originalLabel = substitutionLine?.sku || substitutionLine?.name || 'this item';
    const replacementLabel = inventorySearchItemSku(replacementItem) || inventorySearchItemLabel(replacementItem);
    if (!window.confirm(`Replace ${originalLabel} with ${replacementLabel}? The WooCommerce order line will remain unchanged; Pongo will use the replacement item for inventory.`)) return;
    setSubstitutionBusy(true);
    setSubstitutionError('');
    try {
      const result = await onSubstitute(substitutionLine, replacementItem, reason);
      setSubstitutionMessage(result?.message || `${originalLabel} was substituted with ${replacementLabel}.`);
      setSubstitutionLine(null);
      setReplacementQuery('');
      setReplacementItem(null);
      setSubstitutionReason('');
    } catch (error) {
      setSubstitutionError(error.message || 'Unable to substitute this product.');
    } finally {
      setSubstitutionBusy(false);
    }
  }

  if (!order) return null;
  const shipping = order.shipping_summary || {};
  const address = [
    shipping.address_1,
    shipping.address_2,
    [shipping.city || order.shipping_city, shipping.state || order.shipping_state, shipping.postcode || order.shipping_zip].filter(Boolean).join(' '),
  ].filter(Boolean);
  const hasStatusResult = Boolean(statusActions?.message);
  return (
    <BodyPortal><div className="order-dialog-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section aria-labelledby="open-order-detail-title" aria-modal="true" className="order-detail-dialog print-order-panel" id="open-order-detail" ref={dialogRef} role="dialog" tabIndex={-1}>
        <header className="order-detail-dialog-header">
          <h2 id="open-order-detail-title">{title}</h2>
          <button aria-label="Close customer order" className="icon-button" onClick={onClose} type="button"><X size={20} /></button>
        </header>
        <div className="order-detail-dialog-body">
          {statusActions?.loading && <div className="loading-strip" role="status">Loading local order details…</div>}
          {statusActions?.error && <div className="api-error" role="alert">{statusActions.error}</div>}
          {statusActions?.message && <div className="success-strip" role="status">{statusActions.message}</div>}
          {substitutionError && <div className="api-error" role="alert">{substitutionError}</div>}
          {substitutionMessage && <div className="success-strip" role="status">{substitutionMessage}</div>}
          <div className="order-detail-summary">
            <div className="order-address-card">
              <strong>Ship/Bill To</strong>
              <div>
                <b>{order.customer_name || 'Customer'}</b>
                {address.map((line) => <span key={line}>{line}</span>)}
              </div>
            </div>
            <dl className="order-facts-list">
              <div><dt>Order Number</dt><dd>{order.woo_order_number || order.woo_order_id}</dd></div>
              <div><dt>Placed On</dt><dd>{formatDateTime(order.date_created)}</dd></div>
              <div><dt>Order Reference</dt><dd>{order.woo_order_number || order.woo_order_id}</dd></div>
              <div><dt>Customer</dt><dd>{order.customer_name || '—'}</dd></div>
              <div><dt>Customer Email</dt><dd>{order.customer_email || '—'}</dd></div>
              <div><dt>Status</dt><dd>{StatusText(order.woo_status || order.status || order.local_status)}</dd></div>
              <div><dt>Ship From</dt><dd>{order.ship_from || 'Main Warehouse'}</dd></div>
            </dl>
          </div>
          <div className="order-detail-lines-scroll">
            <table className="order-detail-lines-table">
              <thead><tr><th>SKU</th><th>Product Title</th><th>UOM</th><th>Quantity</th><th>Picked</th><th>Shipped</th><th>Total</th>{onSubstitute && <th>Action</th>}</tr></thead>
              <tbody>
                {(order.lines || []).map((line) => {
                  const substitution = orderLineSubstitution(line);
                  const displayedSku = substitution?.effectiveSku || line.sku;
                  const displayedName = substitution?.effectiveName || line.name;
                  const substitutionLocked = Number(line.quantity_picked || 0) > 0 || Number(line.quantity_fulfilled || 0) > 0 || Number(line.quantity_stock_reduced || 0) > 0;
                  return <tr key={line.id}>
                    <td className="mono">
                      {displayedSku || '—'}
                      {substitution && <small className="order-line-substitution">From {substitution.originalSku || 'original SKU'}</small>}
                    </td>
                    <td>
                      {displayedName || 'Unnamed product'}
                      {substitution && <small className="order-line-substitution">{substitution.originalName || substitution.originalSku || 'Original item'} → {displayedName || displayedSku}</small>}
                    </td>
                    <td>Each</td>
                    <td>{formatNumber(line.quantity_ordered)}</td>
                    <td>{formatNumber(line.quantity_picked)}</td>
                    <td>{formatNumber(line.quantity_fulfilled)}</td>
                    <td>{formatCurrency(line.line_total)}</td>
                    {onSubstitute && <td><button className="link-button order-line-substitute-button" disabled={substitutionBusy || substitutionLocked} onClick={() => beginSubstitution(line)} title={substitutionLocked ? 'Picked or fulfilled lines cannot be substituted.' : undefined} type="button">Substitute</button></td>}
                  </tr>;
                })}
                {!order.lines?.length && <tr><td colSpan={onSubstitute ? 8 : 7}><div className="empty-table-row">No product lines are available for this order.</div></td></tr>}
              </tbody>
            </table>
          </div>
          {substitutionLine && (
            <section aria-labelledby="substitute-order-line-title" className="order-substitution-panel">
              <div className="panel-title">
                <div>
                  <h3 id="substitute-order-line-title">Substitute {substitutionLine.sku || substitutionLine.name || 'order item'}</h3>
                  <p>The WooCommerce order line stays unchanged. Pongo will allocate and deduct the selected replacement product.</p>
                </div>
                <button aria-label="Cancel product substitution" className="icon-button" disabled={substitutionBusy} onClick={() => setSubstitutionLine(null)} type="button"><X size={18} /></button>
              </div>
              <div className="order-substitution-fields">
                <InventoryKeywordSearch
                  label="Replacement inventory item"
                  onChange={(value) => { setReplacementQuery(value); if (value !== inventorySearchItemSku(replacementItem)) setReplacementItem(null); }}
                  onSelect={setReplacementItem}
                  placeholder="Search replacement SKU, barcode, or title"
                  value={replacementQuery}
                />
                <label className="field"><span>Reason <b aria-hidden="true">*</b></span><textarea onChange={(event) => setSubstitutionReason(event.target.value)} placeholder="Why is this product being substituted?" required rows="3" value={substitutionReason} /></label>
              </div>
              {replacementItem && (
                <div className="replacement-item-preview" role="status">
                  <div><span>Replacement</span><strong>{inventorySearchItemLabel(replacementItem)}</strong><small>{inventorySearchItemSku(replacementItem) ? `SKU ${inventorySearchItemSku(replacementItem)}` : 'SKU unavailable'}</small></div>
                  <div><span>Sellable</span><strong>{formatNumber(replacementItem.sellable ?? replacementItem.Sellable)}</strong></div>
                  <div><span>In stock</span><strong>{formatNumber(replacementItem.in_stock ?? replacementItem['In Stock'])}</strong></div>
                </div>
              )}
              <div className="button-row">
                <button className="primary-button" disabled={substitutionBusy || !replacementItem || !substitutionReason.trim()} onClick={commitSubstitution} type="button">{substitutionBusy ? 'Saving substitution…' : 'Confirm substitution'}</button>
                <button className="muted-button" disabled={substitutionBusy} onClick={() => setSubstitutionLine(null)} type="button">Cancel</button>
              </div>
            </section>
          )}
        </div>
        <footer className="order-detail-dialog-footer">
          {statusActions && !statusActions.ready && !statusActions.loading && <button className="primary-button" onClick={statusActions.onRetryDetails} type="button"><RefreshCw size={17} />Retry order details</button>}
          {statusActions?.ready && statusActions.retryTarget && !hasStatusResult && <button className="primary-button" disabled={Boolean(statusActions.pending)} onClick={statusActions.onRetry} type="button"><RefreshCw size={17} />{statusActions.pending ? 'Retrying WooCommerce…' : 'Retry WooCommerce update'}</button>}
          {statusActions?.ready && !statusActions.retryTarget && !hasStatusResult && <button className="primary-button" disabled={Boolean(statusActions.pending)} onClick={statusActions.onMarkProcessed} type="button"><CheckCircle2 size={17} />{statusActions.pending === 'completed' ? 'Marking processed…' : 'Mark processed'}</button>}
          {statusActions?.ready && !statusActions.retryTarget && !hasStatusResult && <button className="muted-button danger-button" disabled={Boolean(statusActions.pending)} onClick={statusActions.onCancel} type="button">{statusActions.pending === 'cancelled' ? 'Cancelling…' : 'Cancel order'}</button>}
          {showPrint && <button className="primary-button" onClick={onPrint} type="button"><Printer size={17} />Print</button>}
          <button className="muted-button" onClick={onClose} type="button">Close</button>
        </footer>
      </section>
      {showPrint && typeof document !== 'undefined' && createPortal(
        <OrderInvoice className="order-invoice-print" order={order} />,
        document.body,
      )}
    </div></BodyPortal>
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
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Product Title', 'Warehouse', 'Location', 'Ordered', 'Allocated', 'Previously Picked', 'Remaining To Pick', 'Recommended', 'Picked After', 'Status', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell"><ClampedText value={line.description} /></td>
            <td>{line.warehouse}</td>
            <td>{line.inventory_location}</td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_allocated)}</td>
            <td>{formatNumber(line.quantity_previously_picked)}</td>
            <td>{formatNumber(line.remaining_to_pick)}</td>
            <td>{formatNumber(line.recommended_pick_quantity)}</td>
            <td>{formatNumber(line.quantity_picked_after)}</td>
            <td>{StatusText(line.pick_status)}</td>
            <td className="description-cell"><ClampedText value={(line.warnings || []).join(' ')} /></td>
            <td className="description-cell"><ClampedText value={(line.errors || []).join(' ')} /></td>
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
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Product Title', 'Ordered', 'Allocated', 'Picked', 'Previously Fulfilled', 'Remaining To Fulfill', 'Recommended', 'Status', 'In Stock', 'Allocated Stock', 'Sellable', 'Warehouse', 'Location', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell"><ClampedText value={line.description} /></td>
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
            <td className="description-cell"><ClampedText value={(line.warnings || []).join(' ')} /></td>
            <td className="description-cell"><ClampedText value={(line.errors || []).join(' ')} /></td>
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
      <TableShell caption={`${rows.length} preview line(s)`} columns={['Order', 'SKU', 'Barcode', 'Product Title', 'Ordered', 'Previously Allocated', 'Remaining', 'In Stock', 'Allocated', 'Sellable', 'Recommended', 'Shortage', 'Status', 'Warnings', 'Errors']}>
        {rows.map(({ order, line }) => (
          <tr key={`${order.order_id}-${line.order_line_id}`}>
            <td className="mono">{order.woo_order_number || order.order_id}</td>
            <td className="mono">{line.sku}</td>
            <td className="mono">{line.barcode}</td>
            <td className="description-cell"><ClampedText value={line.description} /></td>
            <td>{formatNumber(line.quantity_ordered)}</td>
            <td>{formatNumber(line.quantity_previously_allocated)}</td>
            <td>{formatNumber(line.remaining_to_allocate)}</td>
            <td>{formatNumber(line.in_stock)}</td>
            <td>{formatNumber(line.allocated)}</td>
            <td>{formatNumber(line.sellable)}</td>
            <td>{formatNumber(line.recommended_allocate_quantity)}</td>
            <td>{formatNumber(line.shortage_quantity)}</td>
            <td>{StatusText(line.allocation_status)}</td>
            <td className="description-cell"><ClampedText value={(line.warnings || []).join(' ')} /></td>
            <td className="description-cell"><ClampedText value={(line.errors || []).join(' ')} /></td>
          </tr>
        ))}
      </TableShell>
    </div>
  );
}

function AllocationHistoryPanel({ allocations, pagination = emptyServerPagination(), onLoad, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Allocation History</h2>
            <p>Posted local allocation records. Picking is not built yet.</p>
          </div>
        </div>
        <TableShell caption={`${pagination?.total ?? allocations.length} allocation record(s)`} columns={['Allocation', 'Status', 'Woo Order', 'Lines', 'Qty Allocated', 'Created By', 'Created At', 'Posted At']} pagination={serverTablePagination(pagination, 'allocations', (page) => onLoad?.({ page, page_size: pagination.page_size || 20 }), (pageSize) => onLoad?.({ page: 1, page_size: pageSize }))}>
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

function PickHistoryPanel({ picks, pagination = emptyServerPagination(), onLoad, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Pick History</h2>
            <p>Posted local pick records. Picking reduces local In Stock and Allocated at the picked location.</p>
          </div>
        </div>
        <TableShell caption={`${pagination?.total ?? picks.length} pick record(s)`} columns={['Pick', 'Status', 'Woo Order', 'Lines', 'Qty Picked', 'Created By', 'Created At', 'Posted At']} pagination={serverTablePagination(pagination, 'picks', (page) => onLoad?.({ page, page_size: pagination.page_size || 20 }), (pageSize) => onLoad?.({ page: 1, page_size: pageSize }))}>
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

function FulfillmentHistoryPanel({ fulfillments, pagination = emptyServerPagination(), onLoad, detail, onSelect }) {
  return (
    <div className="orders-grid allocation-history-grid">
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Fulfillment History</h2>
            <p>Legacy local completion records. Stock reduction now happens during picking.</p>
          </div>
        </div>
        <TableShell caption={`${pagination?.total ?? fulfillments.length} fulfillment record(s)`} columns={['Fulfillment', 'Status', 'Woo Order', 'Lines', 'Qty Fulfilled', 'Created By', 'Created At', 'Posted At']} pagination={serverTablePagination(pagination, 'fulfillments', (page) => onLoad?.({ page, page_size: pagination.page_size || 20 }), (pageSize) => onLoad?.({ page: 1, page_size: pageSize }))}>
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

function canPrepareCompletedOrderForPicking(order) {
  return Boolean(
    order.completed_without_picking
    && Number(order.total_quantity_ordered || 0) > Number(order.total_quantity_picked || 0)
    && Number(order.line_count || 0) > 0,
  );
}

function CompletedOrderActionsMenu({ order, busy, onView, onPrint, onPreparePicking }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);
  const orderNumber = order.woo_order_number || order.woo_order_id;
  const actions = [
    { label: 'View order', icon: Search, onClick: onView },
    { label: 'Reprint invoice', icon: Printer, onClick: onPrint },
    canPrepareCompletedOrderForPicking(order) ? { label: 'Send to Pick Orders', icon: ClipboardCheck, onClick: onPreparePicking } : null,
  ].filter(Boolean);
  return (
    <div className="order-actions-menu">
      <button aria-expanded={open} aria-haspopup="menu" aria-label={`Open completed order actions for ${orderNumber}`} className="order-actions-trigger" disabled={busy} onClick={() => setOpen((current) => !current)} ref={triggerRef} type="button"><ClipboardList size={20} /></button>
      <FloatingMenu align="start" className="order-actions-popover" onClose={() => setOpen(false)} open={open} triggerRef={triggerRef}>
        {actions.map((action) => {
          const Icon = action.icon;
          return <button key={action.label} onClick={() => { setOpen(false); action.onClick(); }} role="menuitem" type="button"><Icon size={16} />{action.label}</button>;
        })}
      </FloatingMenu>
    </div>
  );
}

function CompletedOrdersPanel({ ordersData, loading, error, onLoadCompletedOrders }) {
  const [filters, setFilters] = useState(emptyCompletedOrderFilters);
  const [activeFilters, setActiveFilters] = useState(emptyCompletedOrderFilters);
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionOrderId, setActionOrderId] = useState(null);
  const [actionError, setActionError] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [printAfterLoad, setPrintAfterLoad] = useState(false);
  const preparePickingMutationRef = useRef(null);
  const orders = ordersData.orders || [];
  const totals = orders.reduce(
    (acc, order) => ({
      quantityFulfilled: acc.quantityFulfilled + Number(order.total_quantity_fulfilled || 0),
      remaining: acc.remaining + Number(order.total_remaining_to_fulfill || 0),
      value: acc.value + Number(order.total_fulfilled_value || 0),
    }),
    { quantityFulfilled: 0, remaining: 0, value: 0 },
  );

  useEffect(() => {
    if (!printAfterLoad || !selectedOrder) return;
    setPrintAfterLoad(false);
    window.requestAnimationFrame(() => printVisibleRoot('single-order-printing'));
  }, [printAfterLoad, selectedOrder]);

  function updateFilter(name, value) {
    setFilters((current) => ({ ...current, [name]: value }));
  }

  function applyFilters() {
    setActiveFilters(filters);
    onLoadCompletedOrders({ ...filters, page: 1, pageSize: ordersData.page_size || 20 });
  }

  function clearFilters() {
    const cleared = emptyCompletedOrderFilters();
    setFilters(cleared);
    setActiveFilters(cleared);
    onLoadCompletedOrders({ ...cleared, page: 1, pageSize: ordersData.page_size || 20 });
  }

  async function openCompletedOrder(order, print = false) {
    setDetailLoading(true);
    setActionError('');
    setActionMessage('');
    setActionOrderId(order.id);
    try {
      setSelectedOrder(await fetchOrderDetailRequest(order.id));
      setPrintAfterLoad(print);
    } catch (detailError) {
      setActionError(detailError.message || 'Unable to load this completed order.');
    } finally {
      setDetailLoading(false);
      setActionOrderId(null);
    }
  }

  async function prepareForPicking(order) {
    const orderNumber = order.woo_order_number || order.woo_order_id;
    if (!window.confirm(`Send completed order ${orderNumber} to Pick Orders? WooCommerce will remain completed while Pongo prepares its unpicked inventory lines.`)) return;
    setActionOrderId(order.id);
    setActionError('');
    setActionMessage('');
    try {
      const result = await prepareCompletedOrderForPicking(order.id, {
        reason: 'Prepared for late picking from Completed Orders.',
      }, preparePickingMutationRef);
      resetMutationIdempotency(preparePickingMutationRef);
      setActionMessage(result.message || `Order ${orderNumber} is ready in Pick Orders.`);
      await onLoadCompletedOrders({ ...activeFilters, page: ordersData.page || 1, pageSize: ordersData.page_size || 20 });
      window.location.hash = '#/orders/pick';
    } catch (prepareError) {
      setActionError(prepareError.message || 'Unable to prepare this order for picking.');
    } finally {
      setActionOrderId(null);
    }
  }

  return (
    <div className="wide-panel">
      <div className="panel-title">
        <div>
          <h2>Completed Orders</h2>
          <p>Search, review, reprint, or prepare eligible completed orders for late picking.</p>
        </div>
        <div className="button-row compact">
          <button className="muted-button" onClick={() => onLoadCompletedOrders({ ...activeFilters, page: ordersData.page || 1, pageSize: ordersData.page_size || 20 })} disabled={loading} type="button"><RefreshCw size={17} />Refresh</button>
          <button className="action-button" onClick={() => exportCompletedOrdersCsv(activeFilters)} type="button"><Download size={17} />Export CSV</button>
        </div>
      </div>
      <div className="summary-strip report-summary-strip">
        <Metric label="Orders" value={ordersData.total || 0} />
        <Metric label="Page Qty Fulfilled" value={formatNumber(totals.quantityFulfilled)} />
        <Metric label="Page Remaining" value={formatNumber(totals.remaining)} />
        <Metric label="Page Fulfilled Value" value={formatCurrency(totals.value)} />
      </div>
      <div className="filter-panel">
        <div className="filter-grid orders-filter-grid">
          <FilterSelect label="Local Status" value={filters.localStatus} options={['completed', 'closed', 'fulfilled', 'partially_fulfilled']} onChange={(value) => updateFilter('localStatus', value)} />
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
      {error && <div className="api-error" role="alert">{error}</div>}
      {actionError && <div className="api-error" role="alert">{actionError}</div>}
      {actionMessage && <div className="success-strip" role="status">{actionMessage}</div>}
      {(loading || detailLoading) && <div className="loading-strip" role="status">{detailLoading ? 'Loading completed order details…' : 'Loading completed orders...'}</div>}
      <TableShell caption={`${ordersData.total || 0} completed order(s)`} className="completed-orders-table" columns={['Actions', 'Woo Order', 'Woo Status', 'Local Status', 'Completion', 'Customer', 'Email', 'Order Total', 'Picked', 'Completed Without Picking', 'Stock Reduced', 'Qty Ordered', 'Qty Allocated', 'Qty Picked', 'Qty Fulfilled', 'Closed']} pagination={serverTablePagination(ordersData, 'completed orders', (page) => onLoadCompletedOrders({ ...activeFilters, page, pageSize: ordersData.page_size || 20 }), (pageSize) => onLoadCompletedOrders({ ...activeFilters, page: 1, pageSize }))}>
        {orders.map((order) => (
          <tr key={order.id}>
            <td className="completed-actions-cell"><CompletedOrderActionsMenu busy={loading || actionOrderId === order.id} onPreparePicking={() => prepareForPicking(order)} onPrint={() => openCompletedOrder(order, true)} onView={() => openCompletedOrder(order)} order={order} /></td>
            <td className="mono completed-order-number" data-label="Woo Order">{order.woo_order_number || order.woo_order_id}</td>
            <td data-label="Woo Status">{StatusText(order.woo_status)}</td>
            <td data-label="Local Status">{StatusText(order.local_status)}</td>
            <td data-label="Completion">{StatusText(order.completion_status)}</td>
            <td data-label="Customer">{order.customer_name}</td>
            <td className="completed-secondary-cell" data-label="Email">{order.customer_email}</td>
            <td data-label="Order Total">{formatCurrency(order.total)}</td>
            <td data-label="Picked">{order.total_quantity_picked > 0 ? 'Yes' : 'No'}</td>
            <td data-label="Completed Without Picking">{order.completed_without_picking ? 'Yes' : 'No'}</td>
            <td className="completed-secondary-cell" data-label="Stock Reduced">{formatNumber(order.total_quantity_stock_reduced)}</td>
            <td className="completed-secondary-cell" data-label="Qty Ordered">{formatNumber(order.total_quantity_ordered)}</td>
            <td className="completed-secondary-cell" data-label="Qty Allocated">{formatNumber(order.total_quantity_allocated)}</td>
            <td className="completed-secondary-cell" data-label="Qty Picked">{formatNumber(order.total_quantity_picked)}</td>
            <td className="completed-secondary-cell" data-label="Qty Fulfilled">{formatNumber(order.total_quantity_fulfilled)}</td>
            <td data-label="Closed">{formatDateTime(order.closed_at || order.completed_at || order.date_modified || order.date_created)}</td>
          </tr>
        ))}
        {orders.length === 0 && <tr className="completed-orders-empty"><td colSpan={16}><div className="empty-table-row">No completed orders match the current filters.</div></td></tr>}
      </TableShell>
      {selectedOrder && <OpenOrderDetailPanel onClose={() => setSelectedOrder(null)} onPrint={() => printVisibleRoot('single-order-printing')} order={selectedOrder} title="Completed Customer Order" />}
    </div>
  );
}

function routeStopSearchUrl(address) {
  const query = new URLSearchParams({ api: '1', query: address });
  return `https://www.google.com/maps/search/?${query.toString()}`;
}

function hasRouteCoordinates(stop) {
  return [stop.latitude, stop.longitude].every((value) => value != null && String(value).trim() !== '' && Number.isFinite(Number(value)));
}

function positionedRouteStops(drivers) {
  const rows = drivers.flatMap((driver) => (driver.stops || []).map((stop) => ({ driver, stop })));
  const located = rows.filter(({ stop }) => hasRouteCoordinates(stop));
  const latitudes = located.map(({ stop }) => Number(stop.latitude));
  const longitudes = located.map(({ stop }) => Number(stop.longitude));
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const latitudeRange = Math.max(maxLatitude - minLatitude, 0.01);
  const longitudeRange = Math.max(maxLongitude - minLongitude, 0.01);
  const hasCoordinateBounds = located.length > 1;
  const zoneCounts = {};

  return rows.map(({ driver, stop }) => {
    const hasCoordinates = hasRouteCoordinates(stop);
    if (hasCoordinates) {
      return {
        driver,
        stop,
        approximate: false,
        left: hasCoordinateBounds ? 8 + ((Number(stop.longitude) - minLongitude) / longitudeRange) * 84 : 54,
        top: hasCoordinateBounds ? 8 + ((maxLatitude - Number(stop.latitude)) / latitudeRange) * 84 : 46,
      };
    }
    const base = ROUTE_ZONE_POSITIONS[stop.direction] || ROUTE_ZONE_POSITIONS['Central East'];
    const occurrence = zoneCounts[stop.direction] || 0;
    zoneCounts[stop.direction] = occurrence + 1;
    const angle = occurrence * 2.4;
    const radius = Math.min(10, 2 + Math.floor(occurrence / 2) * 1.4);
    return {
      driver,
      stop,
      approximate: true,
      left: Math.max(5, Math.min(95, base.left + Math.cos(angle) * radius)),
      top: Math.max(5, Math.min(95, base.top + Math.sin(angle) * radius)),
    };
  });
}

function OpenOrderRouteMap({ plan }) {
  const drivers = plan?.drivers || [];
  const oneDriverLinks = drivers.length === 1 ? drivers[0].google_maps_links || [] : [];
  const markers = positionedRouteStops(drivers);
  const lines = drivers.map((driver) => {
    const points = markers.filter((marker) => marker.driver.driver_number === driver.driver_number);
    return { driver, points: [{ left: 50, top: 50 }, ...points] };
  });

  return (
    <section className="route-map-card" aria-labelledby="route-map-title">
      <div className="panel-title compact-title">
        <div>
          <h3 id="route-map-title">All planned stops</h3>
          <p>{markers.length} stop{markers.length === 1 ? '' : 's'} across {drivers.length} driver route{drivers.length === 1 ? '' : 's'}. Tap any stop to open it in Google Maps.</p>
        </div>
        <div className="route-map-time">
          <span>Parallel finish estimate</span>
          <strong>{formatNumber(plan.estimated_completion_minutes || 0)} min</strong>
        </div>
      </div>
      {oneDriverLinks.length > 0 && (
        <div className="route-map-google-launch">
          <div>
            <strong>Google Maps for Driver 1</strong>
            <span>{oneDriverLinks.length === 1 ? `Open all ${markers.length} planned stops in Google Maps.` : `Open ${oneDriverLinks.length} continuous parts in order to cover all ${markers.length} planned stops.`}</span>
          </div>
          <div className="button-row compact" aria-label="Driver 1 Google Maps route">
            {oneDriverLinks.map((link) => (
              <a className="primary-button" href={link.url} key={`map-launch-${link.part_number}`} rel="noreferrer" target="_blank">
                <MapPin aria-hidden="true" size={16} />
                {oneDriverLinks.length === 1 ? 'Open planned route in Google Maps' : `Open ${link.label}`}
              </a>
            ))}
          </div>
        </div>
      )}
      <div className="route-map-layout">
        <div className="route-map-canvas" role="group" aria-label={`Route map with ${markers.length} planned delivery stops`}>
          <svg aria-hidden="true" className="route-map-lines" preserveAspectRatio="none" viewBox="0 0 100 100">
            {lines.map(({ driver, points }) => (
              <polyline
                fill="none"
                key={driver.driver_number}
                points={points.map((point) => `${point.left},${point.top}`).join(' ')}
                stroke={ROUTE_DRIVER_COLORS[(driver.driver_number - 1) % ROUTE_DRIVER_COLORS.length]}
                strokeDasharray="2 1.5"
                strokeWidth="0.65"
              />
            ))}
          </svg>
          {Object.entries(ROUTE_ZONE_POSITIONS).map(([zone, position]) => (
            <span className="route-map-zone" key={zone} style={{ left: `${position.left}%`, top: `${position.top}%` }}>{zone}</span>
          ))}
          <span className="route-map-warehouse" style={{ left: '50%', top: '50%' }} title={plan.start_address}><Warehouse aria-hidden="true" size={17} /></span>
          {markers.map(({ driver, stop, left, top, approximate }) => (
            <a
              aria-label={`Open order ${stop.woo_order_number || stop.woo_order_id || stop.order_id} in Google Maps`}
              className={approximate ? 'route-map-stop approximate' : 'route-map-stop'}
              href={routeStopSearchUrl(stop.address)}
              key={`${driver.driver_number}-${stop.order_id}`}
              rel="noreferrer"
              style={{ background: ROUTE_DRIVER_COLORS[(driver.driver_number - 1) % ROUTE_DRIVER_COLORS.length], left: `${left}%`, top: `${top}%` }}
              target="_blank"
              title={`${driver.driver_label} · Stop ${stop.stop_sequence} · ${stop.address}`}
            >
              {stop.stop_sequence}
            </a>
          ))}
          {!markers.length && <div className="map-empty">Choose open orders and build a route to plot the stops.</div>}
        </div>
        <div className="route-map-legend">
          <div className="route-map-totals">
            <Metric label="Assigned" value={plan.assigned_order_count ?? markers.length} />
            <Metric label="Unassigned" value={plan.unassigned_order_count || 0} />
            <Metric label="Driver time total" value={`${formatNumber(plan.total_estimated_duration_minutes || 0)} min`} />
          </div>
          {drivers.map((driver) => (
            <article key={driver.driver_number}>
              <i style={{ background: ROUTE_DRIVER_COLORS[(driver.driver_number - 1) % ROUTE_DRIVER_COLORS.length] }} />
              <div><strong>{driver.driver_label}</strong><span>{driver.stop_count} stop{driver.stop_count === 1 ? '' : 's'} · {driver.estimated_duration_minutes || 0} min</span></div>
            </article>
          ))}
          {plan.map?.missing_coordinate_count > 0 && <small>Outlined markers use their assigned direction zone until verified coordinates are available.</small>}
        </div>
      </div>
    </section>
  );
}

function OpenOrderRoutePlanner({ plan, loading, error, onPlan }) {
  const [form, setForm] = useState({
    startAddress: DEFAULT_ROUTE_START_ADDRESS,
    driverCount: 1,
    returnToStart: false,
    assignmentMethod: 'equal_time',
  });
  const [shareMessage, setShareMessage] = useState('');
  const [selectedOrderIds, setSelectedOrderIds] = useState([]);
  const [orderDirections, setOrderDirections] = useState({});
  const [driverDirections, setDriverDirections] = useState(() => defaultRouteDirectionAssignments(1));
  const [orderSearch, setOrderSearch] = useState('');
  const initializedOrdersRef = useRef(false);

  const availableOrders = plan?.available_orders || [];
  const normalizedDriverCount = Math.max(1, Math.min(50, Number(form.driverCount) || 1));
  const selectedOrderIdSet = new Set(selectedOrderIds);
  const filteredOrders = availableOrders.filter((order) => {
    const query = orderSearch.trim().toLocaleLowerCase();
    if (!query) return true;
    return [order.woo_order_number, order.woo_order_id, order.customer_name, order.address, order.postal_area]
      .some((value) => String(value || '').toLocaleLowerCase().includes(query));
  });
  const allVisibleSelected = filteredOrders.length > 0 && filteredOrders.every((order) => selectedOrderIdSet.has(order.order_id));
  const hasDirectionSelection = Object.values(driverDirections).some((directions) => directions.length > 0);

  useEffect(() => {
    if (!plan || initializedOrdersRef.current) return;
    setSelectedOrderIds(availableOrders.map((order) => order.order_id));
    setOrderDirections(Object.fromEntries(availableOrders.map((order) => [order.order_id, order.direction])));
    initializedOrdersRef.current = true;
  }, [plan]);

  function updateForm(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  function updateDriverCount(value) {
    updateForm('driverCount', value);
    const count = Math.max(1, Math.min(50, Number(value) || 1));
    setDriverDirections((current) => Object.fromEntries(
      Array.from({ length: count }, (_, index) => [index + 1, current[index + 1] || []]),
    ));
  }

  function toggleOrder(orderId) {
    setSelectedOrderIds((current) => (current.includes(orderId) ? current.filter((id) => id !== orderId) : [...current, orderId]));
  }

  function selectVisibleOrders() {
    const visibleIds = filteredOrders.map((order) => order.order_id);
    setSelectedOrderIds((current) => [...new Set([...current, ...visibleIds])]);
  }

  function clearVisibleOrders() {
    const visibleIds = new Set(filteredOrders.map((order) => order.order_id));
    setSelectedOrderIds((current) => current.filter((id) => !visibleIds.has(id)));
  }

  function toggleDriverDirection(driverNumber, direction) {
    setDriverDirections((current) => {
      const selected = current[driverNumber] || [];
      return {
        ...current,
        [driverNumber]: selected.includes(direction) ? selected.filter((candidate) => candidate !== direction) : [...selected, direction],
      };
    });
  }

  function buildPlan({ driverCount = normalizedDriverCount, assignmentMethod = form.assignmentMethod } = {}) {
    onPlan({
      start_address: form.startAddress.trim() || DEFAULT_ROUTE_START_ADDRESS,
      driver_count: driverCount,
      return_to_start: form.returnToStart,
      order_ids: selectedOrderIds,
      assignment_method: assignmentMethod,
      order_directions: selectedOrderIds.map((orderId) => ({ order_id: orderId, direction: orderDirections[orderId] || 'Central East' })),
      direction_assignments: assignmentMethod === 'directions'
        ? Array.from({ length: driverCount }, (_, index) => ({ driver_number: index + 1, directions: driverDirections[index + 1] || [] }))
        : [],
    });
  }

  function buildOneDriverPlan() {
    updateDriverCount(1);
    updateForm('assignmentMethod', 'equal_time');
    buildPlan({ driverCount: 1, assignmentMethod: 'equal_time' });
  }

  async function shareLink(link, driverLabel) {
    setShareMessage('');
    try {
      if (navigator.share) {
        await navigator.share({
          title: `${driverLabel} · ${link.label}`,
          text: `Pongo delivery route for ${driverLabel}`,
          url: link.url,
        });
        setShareMessage(`Shared ${driverLabel} ${link.label}.`);
        return;
      }
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(link.url);
      } else {
        const copyField = document.createElement('textarea');
        copyField.value = link.url;
        copyField.setAttribute('readonly', '');
        copyField.style.position = 'fixed';
        copyField.style.opacity = '0';
        document.body.appendChild(copyField);
        copyField.select();
        document.execCommand('copy');
        copyField.remove();
      }
      setShareMessage(`Copied ${driverLabel} ${link.label} link.`);
    } catch (shareError) {
      if (shareError?.name !== 'AbortError') setShareMessage('Unable to share automatically. Open Google Maps and copy the address from your browser.');
    }
  }

  const drivers = plan?.drivers || [];
  const excludedOrders = plan?.excluded_orders || [];
  const unassignedOrders = plan?.unassigned_orders || [];

  return (
    <section className="wide-panel open-order-route-planner" aria-labelledby="open-order-route-planner-title">
      <div className="panel-title route-planner-heading">
        <div>
          <span className="route-planner-kicker"><Route aria-hidden="true" size={16} /> Live delivery planning</span>
          <h2 id="open-order-route-planner-title">Plan selected open orders</h2>
          <p>Choose today’s deliveries, balance estimated workload, or assign the ten delivery zones to specific drivers.</p>
        </div>
        <div className="button-row route-planner-actions">
          <button className="primary-button route-planner-submit" disabled={loading || !form.startAddress.trim() || selectedOrderIds.length === 0} onClick={buildOneDriverPlan} type="button">
            <MapPin aria-hidden="true" size={18} />
            {loading ? 'Building map…' : `Map ${selectedOrderIds.length} selected for 1 driver`}
          </button>
          <button className="muted-button route-planner-submit" disabled={loading || !form.startAddress.trim() || selectedOrderIds.length === 0 || (form.assignmentMethod === 'directions' && !hasDirectionSelection)} onClick={buildPlan} type="button">
            <Route aria-hidden="true" size={18} />
            {loading ? 'Planning routes…' : `Plan ${selectedOrderIds.length} selected`}
          </button>
        </div>
      </div>

      <div className="route-planner-controls">
        <label className="field route-start-field">
          <span>Starting location</span>
          <div className="input-with-icon">
            <input aria-label="Starting location" autoComplete="street-address" maxLength={500} onChange={(event) => updateForm('startAddress', event.target.value)} value={form.startAddress} />
            <MapPin aria-hidden="true" size={18} />
          </div>
          <small>All drivers begin here.</small>
        </label>
        <label className="field route-driver-count-field">
          <span>Drivers</span>
          <input aria-label="Number of drivers" inputMode="numeric" max="50" min="1" onChange={(event) => updateDriverCount(event.target.value)} type="number" value={form.driverCount} />
          <small>Choose 1, 2, 3, or any number up to 50.</small>
        </label>
        <label className="route-return-toggle">
          <input checked={form.returnToStart} onChange={(event) => updateForm('returnToStart', event.target.checked)} type="checkbox" />
          <span><strong>Return to starting location</strong><small>Add a final Google Maps link back to 5855 99 Street.</small></span>
        </label>
      </div>

      <fieldset className="route-strategy-options">
        <legend>How should orders be split?</legend>
        <label className={form.assignmentMethod === 'equal_time' ? 'selected' : ''}>
          <input checked={form.assignmentMethod === 'equal_time'} name="route-assignment-method" onChange={() => updateForm('assignmentMethod', 'equal_time')} type="radio" />
          <span><strong>Equal estimated time</strong><small>Balances area, postal transitions, and stop workload so driver estimates stay as close as possible.</small></span>
        </label>
        <label className={form.assignmentMethod === 'directions' ? 'selected' : ''}>
          <input checked={form.assignmentMethod === 'directions'} name="route-assignment-method" onChange={() => updateForm('assignmentMethod', 'directions')} type="radio" />
          <span><strong>Direction zones</strong><small>Assign one or more zones to each driver. A zone can be shared by multiple drivers.</small></span>
        </label>
      </fieldset>

      {form.assignmentMethod === 'directions' && (
        <div className="route-driver-zone-assignments" aria-label="Direction assignments by driver">
          {Array.from({ length: normalizedDriverCount }, (_, index) => {
            const driverNumber = index + 1;
            return (
              <fieldset key={driverNumber}>
                <legend>Driver {driverNumber}</legend>
                <div>{ROUTE_DIRECTIONS.map((direction) => <label key={direction}><input checked={(driverDirections[driverNumber] || []).includes(direction)} onChange={() => toggleDriverDirection(driverNumber, direction)} type="checkbox" /><span>{direction}</span></label>)}</div>
              </fieldset>
            );
          })}
          {!hasDirectionSelection && <small className="route-zone-help">Choose at least one direction for a driver to build this plan.</small>}
        </div>
      )}

      {plan && (
        <section className="route-order-selector" aria-labelledby="route-order-selector-title">
          <div className="route-order-selector-heading">
            <div><h3 id="route-order-selector-title">Choose open orders</h3><p>{selectedOrderIds.length} of {availableOrders.length} routable orders selected.</p></div>
            <div className="button-row compact"><button className="muted-button" disabled={!filteredOrders.length || allVisibleSelected} onClick={selectVisibleOrders} type="button">Select visible</button><button className="muted-button" disabled={!filteredOrders.some((order) => selectedOrderIdSet.has(order.order_id))} onClick={clearVisibleOrders} type="button">Clear visible</button></div>
          </div>
          <label className="field route-order-search"><span>Find an order</span><div className="input-with-icon"><input aria-label="Find an open order" onChange={(event) => setOrderSearch(event.target.value)} placeholder="Order, customer, postal code, or address" value={orderSearch} /><Search aria-hidden="true" size={18} /></div></label>
          <div className="route-order-table-wrap">
            <table className="route-order-table">
              <thead><tr><th><input aria-label="Select all visible open orders" checked={allVisibleSelected} onChange={(event) => (event.target.checked ? selectVisibleOrders() : clearVisibleOrders())} type="checkbox" /></th><th>Order</th><th>Customer</th><th>Delivery address</th><th>Direction</th></tr></thead>
              <tbody>
                {filteredOrders.map((order) => {
                  const orderNumber = order.woo_order_number || order.woo_order_id || order.order_id;
                  return <tr key={order.order_id}><td><input aria-label={`Select order ${orderNumber}`} checked={selectedOrderIdSet.has(order.order_id)} onChange={() => toggleOrder(order.order_id)} type="checkbox" /></td><td><strong>#{orderNumber}</strong><small>{order.postal_area || 'No postal area'}</small></td><td>{order.customer_name || 'Customer name unavailable'}</td><td>{order.address}</td><td><select aria-label={`Direction for order ${orderNumber}`} onChange={(event) => setOrderDirections((current) => ({ ...current, [order.order_id]: event.target.value }))} value={orderDirections[order.order_id] || order.direction}>{ROUTE_DIRECTIONS.map((direction) => <option key={direction} value={direction}>{direction.charAt(0).toUpperCase() + direction.slice(1)}</option>)}</select></td></tr>;
                })}
                {filteredOrders.length === 0 && <tr><td colSpan={5}><div className="empty-table-row">No open orders match this search.</div></td></tr>}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {error && <div className="api-error" role="alert">{error}</div>}
      {loading && <div className="loading-strip" role="status">Building routes for the selected open orders…</div>}
      {shareMessage && <div className="api-success" role="status" aria-live="polite">{shareMessage}</div>}

      {plan && !loading && (
        <>
          <div className="summary-strip route-planner-summary">
            <Metric label="Open Orders" value={plan.total_open_orders} />
            <Metric label="Selected" value={plan.selected_order_count ?? plan.routable_order_count} />
            <Metric label="Assigned" value={plan.assigned_order_count ?? plan.routable_order_count} />
            <Metric label="Drivers" value={plan.effective_driver_count} />
            <Metric label="Finish Estimate" value={`${formatNumber(plan.estimated_completion_minutes || 0)} min`} />
          </div>
          <OpenOrderRouteMap plan={plan} />
          {(plan.warnings || []).map((warning) => <div className="route-planner-warning" key={warning}><TriangleAlert aria-hidden="true" size={17} /><span>{warning}</span></div>)}

          {drivers.length > 0 ? (
            <div className="driver-route-grid">
              {drivers.map((driver) => (
                <article className="driver-route-card" key={driver.driver_number}>
                  <header>
                    <div><span>Driver route</span><h3>{driver.driver_label}</h3>{driver.directions?.length > 0 && <small>{driver.directions.map((direction) => direction.charAt(0).toUpperCase() + direction.slice(1)).join(' · ')}</small>}</div>
                    <strong>{driver.stop_count} stop{driver.stop_count === 1 ? '' : 's'} · {driver.estimated_duration_minutes || 0} min est.</strong>
                  </header>
                  <ol className="driver-stop-list">
                    {(driver.stops || []).map((stop) => (
                      <li key={stop.order_id}>
                        <span className="driver-stop-number">{stop.stop_sequence}</span>
                        <div><strong>Order #{stop.woo_order_number || stop.woo_order_id || stop.order_id}</strong><span>{stop.customer_name || 'Customer name unavailable'}</span><small>{stop.address}</small></div>
                      </li>
                    ))}
                  </ol>
                  <div className="driver-map-links" aria-label={`${driver.driver_label} Google Maps links`}>
                    {(driver.google_maps_links || []).map((link) => (
                      <div className="driver-map-link" key={`${driver.driver_number}-${link.part_number}`}>
                        <div><strong>{link.label}</strong><small>{link.returns_to_start ? 'Return leg' : `${link.stop_count} delivery stop${link.stop_count === 1 ? '' : 's'}`}</small></div>
                        <div className="button-row compact">
                          <button aria-label={`Share ${driver.driver_label} ${link.label}`} className="muted-button" onClick={() => shareLink(link, driver.driver_label)} type="button"><Copy aria-hidden="true" size={16} /> Share</button>
                          <a className="primary-button" href={link.url} rel="noreferrer" target="_blank"><MapPin aria-hidden="true" size={16} /> Open Maps</a>
                        </div>
                      </div>
                    ))}
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <div className="route-planner-empty"><CheckCircle2 aria-hidden="true" size={22} /><div><strong>{availableOrders.length ? 'No orders selected for this plan' : 'No routable open orders right now'}</strong><span>{availableOrders.length ? 'Choose at least one open order above, then plan the routes.' : 'New WooCommerce processing orders will appear here after they sync.'}</span></div></div>
          )}

          {excludedOrders.length > 0 && (
            <details className="route-excluded-orders">
              <summary>{excludedOrders.length} order{excludedOrders.length === 1 ? '' : 's'} need a delivery address</summary>
              <div>
                {excludedOrders.map((order) => <p key={order.order_id}><strong>Order #{order.woo_order_number || order.order_id}</strong><span>{order.customer_name || 'Customer name unavailable'} · {order.reason}</span></p>)}
              </div>
            </details>
          )}
          {unassignedOrders.length > 0 && (
            <details className="route-excluded-orders">
              <summary>{unassignedOrders.length} selected order{unassignedOrders.length === 1 ? '' : 's'} not assigned</summary>
              <div>
                {unassignedOrders.map((order) => <p key={`${order.order_id}-${order.reason_code}`}><strong>Order #{order.woo_order_number || order.order_id}</strong><span>{order.direction ? `${order.direction} · ` : ''}{order.reason}</span></p>)}
              </div>
            </details>
          )}
        </>
      )}
    </section>
  );
}

function RoutesPage({
  view = 'live',
  openOrderPlan,
  openOrderPlanLoading,
  openOrderPlanError,
  candidatesData,
  candidatesPagination = emptyServerPagination(50),
  candidatesLoading,
  candidatesError,
  preview,
  commitSummary,
  routesData,
  routesPagination = emptyServerPagination(50),
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
  onPlanOpenOrders,
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
      {view === 'live' ? (
        <OpenOrderRoutePlanner plan={openOrderPlan} loading={openOrderPlanLoading} error={openOrderPlanError} onPlan={onPlanOpenOrders} />
      ) : (
        <>
      <div className="wide-panel">
        <div className="panel-title">
          <div>
            <h2>Completed-order route records</h2>
            <p>Create and review saved routes for completed orders without mixing them into today’s live planner.</p>
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
            <label className="field">
              <span>Order Date</span>
              <div className="input-with-icon">
                <input value={candidateFilters.routeDate} onChange={(event) => updateCandidateFilter('routeDate', event.target.value)} onKeyDown={(event) => submitSearchOnEnter(event, () => onLoadCandidates(candidateFilters))} type="date" />
                <CalendarDays size={18} />
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
        {candidatesError && <div className="api-error">{candidatesError}</div>}
        {error && <div className="api-error">{error}</div>}
        {(candidatesLoading || loading) && <div className="loading-strip">Working with local routes...</div>}
        {commitSummary && (
          <div className={commitSummary.status === 'draft' || commitSummary.status === 'finalized' || commitSummary.status === 'cancelled' ? 'success-strip' : 'api-error'}>
            Route action finished with status {commitSummary.status}. {commitSummary.route_number ? `Route ${commitSummary.route_number}.` : ''} {(commitSummary.errors || []).join(' ')}
          </div>
        )}
        <RouteCandidatesTable
          candidates={candidates}
          pagination={candidatesPagination}
          filters={candidateFilters}
          onLoad={onLoadCandidates}
          selectedOrderIds={selectedOrderIds}
          onToggle={toggleOrder}
        />
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
        {routesErrorOrLoading(loading, error)}
        <RouteHistoryTable
          routes={routes}
          pagination={routesPagination}
          filters={routeFilters}
          onLoad={onLoadRoutes}
          detail={detail}
          onSelect={onLoadDetail}
          onFinalize={onFinalize}
          onCancel={onCancel}
        />
      </div>
      <RouteDetailPanel route={detail} mapPayload={mapPayload} providerMessage={providerMessage} loading={loading} onSaveMetadata={onSaveMetadata} onReorderStops={onReorderStops} onSaveStop={onSaveStop} onProviderAction={onProviderAction} />
        </>
      )}
    </section>
  );
}

function RouteCandidatesTable({ candidates, pagination, filters, onLoad, selectedOrderIds, onToggle }) {
  return (
    <TableShell
      caption={`${pagination.total} candidate order(s)`}
      columns={['Select', 'Woo Order', 'Local Status', 'Customer', 'Email', 'Phone', 'Shipping', 'Order Total', 'Fulfilled Lines', 'Qty Fulfilled', 'Date Created', 'Warning']}
      pagination={serverTablePagination(
        pagination,
        'route candidates',
        (page) => onLoad({ ...filters, page, page_size: pagination.page_size }),
        (pageSize) => onLoad({ ...filters, page: 1, page_size: pageSize }),
      )}
    >
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

function RouteHistoryTable({ routes, pagination, filters, onLoad, detail, onSelect, onFinalize, onCancel }) {
  return (
    <TableShell
      caption={`${pagination.total} route(s)`}
      columns={['Route', 'Status', 'Date', 'Name', 'Driver', 'Vehicle', 'Stops', 'Created By', 'Created At', 'Actions']}
      pagination={serverTablePagination(
        pagination,
        'routes',
        (page) => onLoad({ ...filters, page, page_size: pagination.page_size }),
        (pageSize) => onLoad({ ...filters, page: 1, page_size: pageSize }),
      )}
    >
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

const statusPresentation = {
  active: { label: 'Active', tone: 'success' },
  completed: { label: 'Completed', tone: 'success' },
  committed: { label: 'Committed', tone: 'success' },
  success: { label: 'Success', tone: 'success' },
  sent: { label: 'Sent', tone: 'success' },
  ready: { label: 'Ready', tone: 'success' },
  low: { label: 'Low stock', tone: 'warning' },
  under_par: { label: 'Under par', tone: 'warning' },
  missing_cost: { label: 'Cost missing', tone: 'warning' },
  warning: { label: 'Warning', tone: 'warning' },
  pending: { label: 'Pending', tone: 'warning' },
  receiving: { label: 'Receiving staging', tone: 'info', help: 'Inbound stock awaiting put-away.' },
  receive_direct: { label: 'Direct receiving', tone: 'info' },
  in_progress: { label: 'In progress', tone: 'info' },
  processing: { label: 'Processing', tone: 'info' },
  available: { label: 'Available', tone: 'success' },
  partial: { label: 'Partially available', tone: 'warning' },
  insufficient_history: { label: 'Insufficient history', tone: 'info' },
  unavailable: { label: 'Not available', tone: 'neutral' },
  draft: { label: 'Draft', tone: 'neutral' },
  out_of_stock: { label: 'Out of stock', tone: 'danger' },
  failed: { label: 'Failed', tone: 'danger' },
  error: { label: 'Error', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
  canceled: { label: 'Cancelled', tone: 'danger' },
};

const riskStatusPresentation = {
  low: { label: 'Low risk', tone: 'success' },
  medium: { label: 'Medium risk', tone: 'warning' },
  high: { label: 'High risk', tone: 'danger' },
  lost: { label: 'Lost', tone: 'danger' },
  overstock: { label: 'Overstock', tone: 'info' },
  insufficient_history: { label: 'Insufficient history', tone: 'info' },
};

function StatusText(value, context = '') {
  if (isMissingValue(value)) return <DataQualityBadge kind="unavailable" />;
  const key = String(value).trim().toLowerCase();
  const presentation = (context === 'risk' ? riskStatusPresentation[key] : null) || statusPresentation[key] || { label: titleize(value), tone: 'neutral' };
  return <span className={`status-pill status-${presentation.tone} order-status-${key.replace(/[^a-z0-9-]/g, '-')}`} aria-label={presentation.help ? `${presentation.label}: ${presentation.help}` : presentation.label} title={presentation.help || undefined}>{presentation.label}</span>;
}

function GoogleSheetsSettingsPage({ oauthResult = '' }) {
  const [status, setStatus] = useState({ configured: false, configuration_source: 'not_configured', oauth_redirect_uri: '' });
  const [form, setForm] = useState({ client_id: '', client_secret: '', folder_id: '' });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(oauthResult === 'denied'
    ? 'Google access was not approved. Nothing was changed.'
    : oauthResult === 'failed'
      ? 'Google connection could not be completed. Check the OAuth client and authorized redirect URI, then try again.'
      : '');
  const [message, setMessage] = useState(oauthResult === 'connected'
    ? 'Google Sheets is connected. Verified reports can now open directly in Google Sheets.'
    : '');

  useEffect(() => {
    let active = true;
    async function loadConfiguration() {
      try {
        const response = await apiFetch(`${API_BASE_URL}/api/reports/google-sheets/configuration`);
        const body = await response.json();
        if (!response.ok) throw new Error(apiErrorDetail(body));
        if (!active) return;
        setStatus(body);
        setForm((current) => ({ ...current, folder_id: body.folder_id || '' }));
      } catch (loadError) {
        if (active) setError(loadError.message || 'Could not load the Google Sheets connection.');
      } finally {
        if (active) setLoading(false);
      }
    }
    loadConfiguration();
    return () => { active = false; };
  }, []);

  async function connectGoogle(event) {
    event.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const body = await postJson('/api/reports/google-sheets/oauth/start', form);
      browserNavigation.assign(body.authorization_url);
    } catch (connectError) {
      setError(connectError.message || 'Could not start Google sign-in.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="content-panel settings-page">
      {(loading || error) && <div className="integration-feedback" aria-live="polite">
        {loading && <div className="loading-strip">Checking the Google Sheets connection…</div>}
        {error && <div className="api-error">{error}</div>}
      </div>}
      <section className="integration-console" aria-labelledby="google-sheets-integration-title">
        <aside className="integration-rail" aria-label="Connected systems">
          <div className="integration-rail-heading"><span>Connected systems</span><strong>02</strong></div>
          <a className="integration-source" href="#/settings/connection">
            <span className="integration-source-mark">woo</span>
            <span><strong>WooCommerce</strong><small>Store operations</small></span>
            <span className="integration-status-dot is-live" aria-hidden="true" />
          </a>
          <a className="integration-source active" href="#/settings/google-sheets" aria-current="page">
            <span className="integration-source-mark"><FileSpreadsheet size={19} /></span>
            <span><strong>Google Sheets</strong><small>{status.configured ? 'Connected' : 'Needs connection'}</small></span>
            <span className={`integration-status-dot ${status.configured ? 'is-live' : ''}`} aria-hidden="true" />
          </a>
          <div className="integration-rail-note">
            <span>Portable Pongo storage</span>
            <p>Credentials are encrypted in Pongo’s database and never returned to this browser.</p>
          </div>
        </aside>

        <div className="integration-workspace">
          <header className="integration-masthead">
            <div>
              <span className="integration-eyebrow">Reporting / Google Sheets</span>
              <h2 id="google-sheets-integration-title">Connect report sharing</h2>
              <p>Save the Google connection once, then every verified report can open directly in Google Sheets.</p>
            </div>
            <div className={`integration-health ${status.configured ? 'is-connected' : ''}`} role="status">
              <span className="integration-health-pulse" aria-hidden="true" />
              <div><strong>{status.configured ? 'Connected' : 'Not connected'}</strong><small>Pongo database</small></div>
            </div>
          </header>

          <div className="integration-control-grid">
            <form className="integration-credentials" onSubmit={connectGoogle}>
              <div className="integration-section-label">
                <span>01</span><div><strong>Google OAuth app</strong><small>One-time setup; Google handles account approval</small></div>
              </div>
              <div className="integration-key-grid">
                <label className="integration-field">
                  <span>OAuth client ID</span>
                  <input type="text" required={!status.client_id_present} value={form.client_id} onChange={(event) => setForm((current) => ({ ...current, client_id: event.target.value }))} placeholder={status.client_id_present ? 'Saved — enter only to replace' : 'Google OAuth client ID'} autoComplete="off" />
                </label>
                <label className="integration-field">
                  <span>OAuth client secret</span>
                  <input type="password" required={!status.client_secret_present} value={form.client_secret} onChange={(event) => setForm((current) => ({ ...current, client_secret: event.target.value }))} placeholder={status.client_secret_present ? 'Saved — enter only to replace' : 'Google OAuth client secret'} autoComplete="new-password" />
                </label>
              </div>
              <label className="integration-field">
                <span>Authorized redirect URI</span>
                <input type="text" readOnly value={status.oauth_redirect_uri || ''} aria-describedby="google-redirect-help" />
              </label>
              <p id="google-redirect-help" className="integration-access-audit">Add this exact URI to the OAuth web client in Google Cloud.</p>
              <label className="integration-field">
                <span>Google Drive folder ID <small>(optional)</small></span>
                <input type="text" value={form.folder_id} onChange={(event) => setForm((current) => ({ ...current, folder_id: event.target.value }))} placeholder="Leave blank to use My Drive" autoComplete="off" />
              </label>
              <div className="integration-form-footer">
                <p>{status.configuration_source === 'pongo_database'
                  ? `Encrypted in Pongo${status.configuration_updated_by ? ` · saved by ${status.configuration_updated_by}` : ''}. Blank client fields keep the saved OAuth app.`
                  : 'Google credentials are stored inside Pongo—not in Heroku or any hosting provider.'}</p>
                <button className="primary-button integration-connect-button" disabled={loading} type="submit"><Link2 size={17} />{loading ? 'Opening Google…' : status.configured ? 'Reconnect Google Account' : 'Sign in with Google'}</button>
              </div>
              {message && <div className="integration-inline-success" role="status">{message}</div>}
            </form>

            <section className="integration-operations" aria-labelledby="google-setup-title">
              <div className="integration-section-label">
                <span>02</span><div><strong id="google-setup-title">One-time Google setup</strong><small>Complete these steps in Google Cloud</small></div>
              </div>
              <ol className="integration-setup-list">
                <li><strong>Enable two APIs</strong><span>Google Sheets API and Google Drive API.</span></li>
                <li><strong>Create an OAuth web client</strong><span>Add the authorized redirect URI shown on this page.</span></li>
                <li><strong>Connect your Google account</strong><span>Click once, choose the account, and approve access in Google.</span></li>
                <li><strong>Choose a folder</strong><span>Optional: paste the ID from a Google Drive folder URL.</span></li>
              </ol>
              <div className="integration-safety-line"><span>Hosting portability</span><strong>Database-backed</strong></div>
              <p className="integration-access-audit">If Pongo moves hosts, migrate the database and the existing master encryption key. No Google credentials need to be recreated.</p>
            </section>
          </div>
        </div>
      </section>
    </section>
  );
}

function WooCommerceSettingsPage({ view = 'connection', status, preview, commitSummary, orderPreview, orderCommitSummary, syncRuns, syncRunsPagination = emptyServerPagination(50), onLoadSyncRuns, remapCandidates, remapCandidatesPagination = emptyServerPagination(100), onLoadRemapCandidates, remapMappings, remapMappingsPagination = emptyServerPagination(100), onLoadRemapMappings, remapPreview, remapMessage, writebackQueue, writebackQueuePagination = emptyServerPagination(50), onLoadWritebackQueue, stockSyncJobs, stockSyncJobsPagination = emptyServerPagination(25), onLoadStockSyncJobs, writebackPreview, writebackMessage, loading, error, onCheckConnection, onSaveConfiguration, onChangeAccessMode, onPreview, onCommit, onPreviewOrders, onCommitOrders, onStartOrderHistoryImport, onPreviewRemap, onCommitRemap, onLoadRemap, onPreviewStockWriteback, onPreviewOrderStatusWriteback, onQueueWriteback, onApproveWriteback, onSendWriteback, onCancelWriteback, onRevalidateWriteback, onSyncStock, onResumeStockJob, onCancelStockJob }) {
  const latestRun = syncRuns.find((run) => run.sync_type === 'products') || syncRuns[0];
  const latestOrderRun = syncRuns.find((run) => run.sync_type === 'orders');
  const reconciliation = status.order_reconciliation || {};
  const historyImport = status.order_history_import || {};
  const historyCoverage = status.order_history_coverage || {};
  const historyImportActive = ['queued', 'running'].includes(historyImport.status);
  const commitDisabled = !status.configured || !preview || preview.error_count > 0;
  const [connectionForm, setConnectionForm] = useState({ base_url: status.base_url || '', consumer_key: '', consumer_secret: '' });
  const [connectionMessage, setConnectionMessage] = useState('');
  const [hostChangeAuthorized, setHostChangeAuthorized] = useState(false);
  const requestedHost = hostnameFromUrl(connectionForm.base_url);
  const allowedHost = normalizeHostname(status.allowed_host);
  const hostMismatch = Boolean(requestedHost && allowedHost && requestedHost !== allowedHost);

  useEffect(() => {
    setConnectionForm((current) => ({ ...current, base_url: status.base_url || current.base_url }));
    setHostChangeAuthorized(false);
  }, [status.base_url]);

  async function connectWooCommerce(event) {
    event.preventDefault();
    if (hostMismatch && !hostChangeAuthorized) return;
    setConnectionMessage('');
    try {
      const payload = hostMismatch
        ? { ...connectionForm, allow_host_change: hostChangeAuthorized }
        : connectionForm;
      const result = await onSaveConfiguration(payload);
      setConnectionForm((current) => ({ ...current, consumer_key: '', consumer_secret: '' }));
      setConnectionMessage(result.message);
    } catch {
      // The shared API error is rendered below the connection workspace.
    }
  }

  return (
    <section className="content-panel settings-page" data-settings-view={view}>
      {(loading || error) && (
        <div className="integration-feedback" aria-live="polite">
          {loading && <div className="loading-strip">Working with the Pongo backend…</div>}
          {error && <div className="api-error">{error}</div>}
        </div>
      )}
      {view === 'connection' && <section className="integration-console" aria-labelledby="woocommerce-integration-title">
        <aside className="integration-rail" aria-label="Connected systems">
          <div className="integration-rail-heading">
            <span>Connected systems</span>
            <strong>01</strong>
          </div>
          <button className="integration-source active" type="button" aria-current="page">
            <span className="integration-source-mark">woo</span>
            <span><strong>WooCommerce</strong><small>{status.configured ? status.base_url_host : 'Needs connection'}</small></span>
            <span className={`integration-status-dot ${status.configured ? 'is-live' : ''}`} aria-hidden="true" />
          </button>
          <div className="integration-rail-note">
            <span>Encrypted backend storage</span>
            <p>Configure here. Keys never return to the browser after saving.</p>
          </div>
        </aside>

        <div className="integration-workspace">
          <header className="integration-masthead">
            <div>
              <span className="integration-eyebrow">Marketplace / WooCommerce</span>
              <h2 id="woocommerce-integration-title">Store connection &amp; operations</h2>
              <p>Connect Pongo to your WooCommerce store, then run the existing catalog, order, mapping, and stock workflows from one place.</p>
            </div>
            <div className={`integration-health ${hostMismatch ? 'needs-review' : (status.configured ? 'is-connected' : '')}`} role="status">
              <span className="integration-health-pulse" aria-hidden="true" />
              <div>
                <strong>{hostMismatch ? 'Host review required' : (connectionMessage ? 'Connected' : (status.configured ? 'Configured' : 'Not connected'))}</strong>
                <small>{hostMismatch ? requestedHost : `${status.environment || 'development'} environment`}</small>
              </div>
            </div>
          </header>

          <div className="integration-control-grid">
            <form className="integration-credentials" onSubmit={connectWooCommerce}>
              <div className="integration-section-label">
                <span>01</span>
                <div><strong>Connection credentials</strong><small>Verify first, save second</small></div>
              </div>
              <label className="integration-field">
                <span>Store URL</span>
                <input
                  type="url"
                  required
                  value={connectionForm.base_url}
                  onChange={(event) => {
                    setConnectionForm((current) => ({ ...current, base_url: event.target.value }));
                    setHostChangeAuthorized(false);
                  }}
                  placeholder="https://pongo.ca"
                  autoComplete="url"
                />
              </label>
              {hostMismatch && (
                <div className="integration-host-warning" role="alert">
                  <div className="integration-host-warning-heading">
                    <span>Host replacement required</span>
                    <strong>Explicit approval</strong>
                  </div>
                  <div className="integration-host-comparison" aria-label="WooCommerce host comparison">
                    <div>
                      <span>Currently authorized</span>
                      <strong>{allowedHost}</strong>
                    </div>
                    <ChevronRight size={18} aria-hidden="true" />
                    <div>
                      <span>Requested host</span>
                      <strong>{requestedHost}</strong>
                    </div>
                  </div>
                  <label className="integration-host-authorization">
                    <input
                      type="checkbox"
                      checked={hostChangeAuthorized}
                      onChange={(event) => setHostChangeAuthorized(event.target.checked)}
                    />
                    <span>
                      <strong>Authorize replacing the WooCommerce host</strong>
                      <small>This changes which store Pongo connects to. Existing credentials remain unchanged when the key fields are blank.</small>
                    </span>
                  </label>
                </div>
              )}
              <div className="integration-key-grid">
                <label className="integration-field">
                  <span>Consumer key</span>
                  <input
                    type="password"
                    value={connectionForm.consumer_key}
                    onChange={(event) => setConnectionForm((current) => ({ ...current, consumer_key: event.target.value }))}
                    placeholder={status.consumer_key_present ? 'Saved — enter only to replace' : 'ck_…'}
                    autoComplete="new-password"
                  />
                </label>
                <label className="integration-field">
                  <span>Consumer secret</span>
                  <input
                    type="password"
                    value={connectionForm.consumer_secret}
                    onChange={(event) => setConnectionForm((current) => ({ ...current, consumer_secret: event.target.value }))}
                    placeholder={status.consumer_secret_present ? 'Saved — enter only to replace' : 'cs_…'}
                    autoComplete="new-password"
                  />
                </label>
              </div>
              <div className="integration-form-footer">
                <p>
                  {status.configuration_source === 'pongo_database'
                    ? `Encrypted in Pongo${status.configuration_updated_by ? ` · saved by ${status.configuration_updated_by}` : ''}. Blank key fields keep the saved credentials.`
                    : 'Save once to move this connection into encrypted Pongo storage.'}
                </p>
                <button className="primary-button integration-connect-button" disabled={loading || !connectionForm.base_url || (hostMismatch && !hostChangeAuthorized)} type="submit">
                  <CheckCircle2 size={17} />
                  {loading ? 'Verifying…' : 'Save & verify connection'}
                </button>
              </div>
              {connectionMessage && <div className="integration-inline-success" role="status">{connectionMessage}</div>}
            </form>

            <nav className="integration-operations" aria-label="WooCommerce settings pages">
              <div className="integration-section-label">
                <span>02</span>
                <div><strong>Store access</strong><small>Choose what Pongo may do in WooCommerce</small></div>
              </div>
              <div className="integration-access-mode" role="group" aria-label="WooCommerce access mode">
                <button
                  type="button"
                  className={status.access_mode !== 'read_write' ? 'is-active' : ''}
                  aria-pressed={status.access_mode !== 'read_write'}
                  disabled={loading}
                  onClick={() => onChangeAccessMode('read_only')}
                >
                  <span>Read only</span>
                  <small>GET requests only. Sync products and orders without changing WooCommerce.</small>
                </button>
                <button
                  type="button"
                  className={status.access_mode === 'read_write' ? 'is-active is-write' : ''}
                  aria-pressed={status.access_mode === 'read_write'}
                  disabled={loading}
                  onClick={() => onChangeAccessMode('read_write')}
                >
                  <span>Read &amp; write</span>
                  <small>Enable Pongo stock updates, completed-order status writes, and background writeback jobs.</small>
                </button>
              </div>
              <p className="integration-access-audit">
                {status.access_mode_updated_by
                  ? `Last changed by ${status.access_mode_updated_by} · ${formatDateTime(status.access_mode_updated_at)}`
                  : 'Using the deployment default until a team member changes it.'}
              </p>
              <div className="integration-section-label integration-workflow-label">
                <span>03</span>
                <div><strong>Continue setup</strong><small>Each workflow has its own page</small></div>
              </div>
              <div className="integration-destination-list">
                <a href="#/settings/sync">
                  <span className="integration-destination-icon"><RefreshCw size={19} /></span>
                  <span><strong>Sync &amp; Mapping</strong><small>Catalog import, orders, remapping, and run history</small></span>
                  <ChevronRight size={18} aria-hidden="true" />
                </a>
                <a href="#/settings/writeback">
                  <span className="integration-destination-icon is-live"><Upload size={19} /></span>
                  <span><strong>Writeback Control</strong><small>Stock updates, order status, and guarded queue</small></span>
                  <ChevronRight size={18} aria-hidden="true" />
                </a>
              </div>
              <button className="muted-button integration-test-button" onClick={onCheckConnection} disabled={loading || !status.configured} type="button"><CheckCircle2 size={17} />Test current connection</button>
              <div className="integration-safety-line">
                <span>Effective access</span>
                <strong>{status.access_mode === 'read_write' ? 'Live read & write' : 'GET requests only'}</strong>
              </div>
            </nav>
          </div>
        </div>
      </section>}

      {view === 'sync' && <>
      <SettingsViewIntro
        number="02"
        eyebrow="Operational sync"
        title="One preview before every commit"
        description="Catalog, order, and mapping changes keep their existing guarded preview and commit flow. Nothing in this page bypasses Pongo’s allocation or inventory rules."
        status={status.configured ? 'Connection ready' : 'Connection required'}
        tone={status.configured ? 'success' : 'warning'}
      />
      <div className="wide-panel settings-operation-panel">
        <div className="panel-title">
          <div>
            <h2>WooCommerce Catalog Mapping &amp; Import</h2>
            <p>Reads WooCommerce in batches, maps existing items by unique SKU then barcode, and creates only missing products. Existing Pongo fields and item IDs stay unchanged.</p>
          </div>
          <div className="button-row compact">
            <button className="muted-button" onClick={onCheckConnection} type="button">
              <CheckCircle2 size={17} />
              Check Connection
            </button>
            <button className="primary-button" disabled={loading || !status.configured} onClick={onPreview} type="button">
              <Search size={17} />
              Preview Catalog Mapping
            </button>
            <button className="action-button" disabled={loading || commitDisabled} onClick={onCommit} type="button">
              <RefreshCw size={17} />
              Import &amp; Map Catalog
            </button>
          </div>
        </div>
        <div className="summary-strip report-summary-strip">
          <Metric label="Configured" value={status.configured ? 'Yes' : 'No'} />
          <Metric label="Environment" value={status.environment || 'unknown'} />
          <Metric label="Base Host" value={status.base_url_host || (status.base_url_present ? 'Present' : 'Missing')} />
          <Metric label="Allowed Host" value={status.host_allowed ? 'Matched' : 'Not matched'} />
          <Metric label="Read-only" value={status.read_only ? 'Yes' : 'No'} />
          <Metric label="Dry-run" value={status.dry_run ? 'On' : 'Off'} />
          <Metric label="Live Test" value={status.staging_live_test_mode ? 'On' : 'Off'} />
          <Metric label="Last Sync" value={status.last_product_sync?.status || latestRun?.status || 'None'} />
        </div>
        {status.configured && status.message && <div className="csv-note">{status.message}</div>}
        {preview && <WooPreviewSummary preview={preview} />}
        {commitSummary && (
          <div className="success-strip">
            Catalog import finished with status {commitSummary.status}. Created {commitSummary.created_count}, mapped {commitSummary.updated_count}, conflicts {commitSummary.conflict_count}, and left {commitSummary.unmatched_local_count} local item(s) unmatched.
          </div>
        )}
        {commitSummary?.unmatched_local_count > 0 && (
          <div className="warning-strip">
            Unmatched local SKUs: {(commitSummary.unmatched_local_skus || []).join(', ')}{commitSummary.unmatched_local_count > (commitSummary.unmatched_local_skus || []).length ? ' …' : ''}
          </div>
        )}
      </div>
      {preview && <WooPreviewTable rows={preview.preview_rows || []} />}
      <div className="wide-panel settings-operation-panel">
        <div className="panel-title">
          <div>
            <h2>WooCommerce Order Sync</h2>
            <p>Checks automatically every two minutes. Use Fetch Orders Now for an immediate priority job; the worker imports in memory-safe batches.</p>
          </div>
          <div className="button-row compact">
            <button className="primary-button" disabled={loading || !status.configured} onClick={onPreviewOrders} type="button">
              <Search size={17} />
              Preview Order Sync
            </button>
            <button className="action-button" disabled={loading || !status.configured} onClick={onCommitOrders} type="button">
              <RefreshCw size={17} />
              Fetch Orders Now
            </button>
          </div>
        </div>
        <div className="summary-strip report-summary-strip">
          <Metric label="Sync Statuses" value="open + completed snapshots" />
          <Metric label="Last Order Sync" value={status.last_order_sync?.status || latestOrderRun?.status || 'None'} />
          <Metric label="Last Orders" value={status.last_order_sync?.total_remote_records || latestOrderRun?.total_remote_records || 0} />
          <Metric label="Webhook Receiver" value={status.webhook_configured ? 'Ready' : (status.webhook_enabled ? 'Needs setup' : 'Off')} />
          <Metric label="Webhook Secret" value={status.webhook_secret_present ? 'Present' : 'Missing'} />
          <Metric label="Last Webhook" value={status.last_webhook_delivery?.status || 'None'} />
          <Metric label="Webhook Order" value={status.last_webhook_delivery?.woo_order_id ? `#${status.last_webhook_delivery.woo_order_id}` : 'None'} />
          <Metric label="Server Reconciliation" value={reconciliation.healthy ? 'Healthy' : (reconciliation.degraded ? 'Needs review' : (reconciliation.enabled ? 'Attention' : 'Off'))} />
          <Metric label="Last Server Success" value={reconciliation.last_success_at ? formatDateTime(reconciliation.last_success_at) : 'None'} />
        </div>
        {status.configured && reconciliation.enabled && !reconciliation.healthy && (
          <div className="warning-strip">
            {reconciliation.message || 'Server order reconciliation needs attention.'}
            {reconciliation.last_error ? ` ${reconciliation.last_error}` : ''}
          </div>
        )}
        {status.last_webhook_delivery && (
          <div className="api-success">
            Last webhook delivery {status.last_webhook_delivery.status} {formatDateTime(status.last_webhook_delivery.received_at)}.
            {status.last_webhook_delivery.created_order ? ' A new local order was created.' : ' No new local order was created.'}
          </div>
        )}
        {orderPreview && <WooOrderPreviewSummary preview={orderPreview} />}
        {orderCommitSummary && ['queued', 'running'].includes(orderCommitSummary.status) && (
          <div className="success-strip">
            Order fetch job #{orderCommitSummary.id} is {orderCommitSummary.status}. You can leave this page; the worker continues in the background.
          </div>
        )}
        {orderCommitSummary && !['queued', 'running'].includes(orderCommitSummary.status) && (
          <div className="success-strip">
            Order fetch job #{orderCommitSummary.id || orderCommitSummary.sync_run_id} finished with status {orderCommitSummary.status}. Created {orderCommitSummary.created_count}, updated {orderCommitSummary.updated_count}, skipped {orderCommitSummary.skipped_count}.
          </div>
        )}
      </div>
      {orderPreview && <WooOrderPreviewTable orders={orderPreview.preview_orders || []} />}
      <div className="wide-panel settings-operation-panel">
        <div className="panel-title">
          <div>
            <h2>Historical Reporting Baseline</h2>
            <p>Imports the complete WooCommerce order history across all statuses in resumable pages so customer, sales, SKU, and order intelligence uses the full local record.</p>
          </div>
          <button className="action-button" disabled={loading || !status.configured || historyImportActive} onClick={onStartOrderHistoryImport} type="button">
            <Download size={17} />
            {historyImportActive ? 'Import running' : (historyImport.status === 'failed' ? 'Resume history import' : 'Import full order history')}
          </button>
        </div>
        <div className="summary-strip report-summary-strip">
          <Metric label="Coverage" value={historyCoverage.verified_complete ? 'Verified' : 'Not verified'} />
          <Metric label="Job Status" value={historyImport.status || 'Not started'} />
          <Metric label="Orders Scanned" value={historyImport.total_remote_records || 0} />
          <Metric label="New Snapshots" value={historyImport.created_count || 0} />
          <Metric label="Already Local" value={historyImport.updated_count || 0} />
          <Metric label="Local Orders" value={historyCoverage.local_order_count || 0} />
          <Metric label="Archived Snapshots" value={historyCoverage.source_absent_snapshot_count || 0} />
          <Metric label="Order Dates" value={historyCoverage.distinct_order_dates || 0} />
          <Metric label="Earliest Order" value={historyCoverage.earliest_order_at ? formatDateTime(historyCoverage.earliest_order_at) : 'None'} />
          <Metric label="Latest Order" value={historyCoverage.latest_order_at ? formatDateTime(historyCoverage.latest_order_at) : 'None'} />
        </div>
        {historyImportActive && (
          <div className="loading-strip" role="status">
            Importing {historyImport.progress?.current_status === 'any' ? 'all order statuses' : (historyImport.progress?.current_status || 'orders')}, page {historyImport.progress?.next_page || 1}. The worker safely resumes after restarts; you can leave this page.
          </div>
        )}
        {historyCoverage.verified_complete && (
          <div className="api-success">Full historical order coverage was verified {historyCoverage.verified_at ? formatDateTime(historyCoverage.verified_at) : ''}.</div>
        )}
        {historyImport.status === 'completed_with_errors' && historyImport.progress?.coverage_complete && (
          <div className="warning-strip">Order and customer coverage is complete. {historyImport.error_count || 0} item mapping issue(s) remain available in sync history for review.</div>
        )}
        {historyImport.status === 'completed_with_errors' && !historyImport.progress?.coverage_complete && (
          <div className="api-error">The history scan finished with errors, so full order coverage is not verified. Review Sync Run History and run it again.</div>
        )}
        {historyImport.status === 'failed' && (
          <div className="api-error">{historyImport.progress?.last_error || historyImport.notes || 'Historical order import paused. Resume it from the last committed page.'}</div>
        )}
      </div>
      </>}
      {view === 'writeback' && <>
        <SettingsViewIntro
          number="03"
          eyebrow="Controlled outbound changes"
          title="Write only what has been reviewed"
          description="Stock and order-status updates still pass through Pongo’s existing preview, queue, approval, environment, and host safeguards."
          status={status.dry_run ? 'Dry-run active' : (status.writeback_enabled ? 'Live guard active' : 'Writes disabled')}
          tone={status.dry_run ? 'info' : (status.writeback_enabled ? 'warning' : 'neutral')}
        />
        <WooWritebackPanel status={status} queue={writebackQueue?.queue || []} queuePagination={writebackQueuePagination} onLoadQueue={onLoadWritebackQueue} stockSyncJobs={stockSyncJobs || []} stockSyncJobsPagination={stockSyncJobsPagination} onLoadStockSyncJobs={onLoadStockSyncJobs} preview={writebackPreview} message={writebackMessage} loading={loading} onPreviewStock={onPreviewStockWriteback} onPreviewOrderStatus={onPreviewOrderStatusWriteback} onQueue={onQueueWriteback} onApprove={onApproveWriteback} onSend={onSendWriteback} onCancel={onCancelWriteback} onRevalidate={onRevalidateWriteback} onSyncStock={onSyncStock} onResumeStockJob={onResumeStockJob} onCancelStockJob={onCancelStockJob} />
      </>}
      {view === 'sync' && <>
      <WooRemapPanel candidates={remapCandidates?.candidates || []} candidatePagination={remapCandidatesPagination} onLoadCandidates={onLoadRemapCandidates} mappings={remapMappings?.mappings || []} mappingPagination={remapMappingsPagination} onLoadMappings={onLoadRemapMappings} preview={remapPreview} message={remapMessage} loading={loading} onPreview={onPreviewRemap} onCommit={onCommitRemap} onRefresh={onLoadRemap} />
      <div className="wide-panel settings-operation-panel">
        <div className="panel-title">
          <div>
            <h2>Sync Run History</h2>
            <p>Local WooCommerce sync attempts and outcomes.</p>
          </div>
        </div>
        <WooSyncRunsTable runs={syncRuns} pagination={syncRunsPagination} onLoad={onLoadSyncRuns} />
      </div>
      </>}
    </section>
  );
}

function SettingsViewIntro({ number, eyebrow, title, description, status, tone = 'neutral' }) {
  return (
    <section className="settings-view-intro">
      <span className="settings-view-number">{number}</span>
      <div>
        <span className="settings-view-eyebrow">{eyebrow}</span>
        <h2>{title}</h2>
        <p>{description}</p>
      </div>
      <span className={`settings-view-state is-${tone}`}>{status}</span>
    </section>
  );
}

function WooPreviewSummary({ preview }) {
  return (
    <div className="summary-strip woo-summary-strip">
      <Metric label="Remote Records" value={preview.total_remote_records} />
      <Metric label="Create Missing" value={preview.create_count} />
      <Metric label="Map Existing" value={preview.update_count} />
      <Metric label="Matched" value={preview.matched_count} />
      <Metric label="Skipped" value={preview.skipped_count} />
      <Metric label="Conflicts" value={preview.conflict_count} />
      <Metric label="Errors" value={preview.error_count} />
    </div>
  );
}

function useClientPagination(rows, noun) {
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const totalPages = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const pageRows = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  return {
    pageRows,
    pagination: {
      page: currentPage,
      pageSize,
      total: rows.length,
      totalPages,
      returnedCount: pageRows.length,
      noun,
      onPageChange: (nextPage) => setPage(Math.max(1, Math.min(totalPages, nextPage))),
      onPageSizeChange: (nextPageSize) => {
        setPageSize(nextPageSize);
        setPage(1);
      },
    },
  };
}

function WooPreviewTable({ rows }) {
  const paged = useClientPagination(rows, 'preview rows');
  return (
    <TableShell caption={`${rows.length} preview row(s)`} columns={['Action', 'Remote Type', 'Woo Product ID', 'Woo Variation ID', 'SKU', 'Barcode', 'Product Title', 'Category', 'Brand', 'Price', 'Stock Status', 'Woo Stock Snapshot', 'Local Item ID', 'Warnings', 'Errors']} pagination={paged.pagination}>
      {paged.pageRows.map((row) => (
        <tr key={`${row.woo_product_id}-${row.woo_variation_id || 'simple'}-${row.sku}`}>
          <td>{row.action}</td>
          <td>{row.remote_type}</td>
          <td>{row.woo_product_id}</td>
          <td>{row.woo_variation_id}</td>
          <td className="mono">{row.sku}</td>
          <td className="mono">{row.barcode}</td>
          <td className="description-cell"><ClampedText value={row.description} /></td>
          <td>{row.category ? decodeHtmlEntities(row.category) : <DataQualityBadge kind="missing_category" />}</td>
          <td>{row.brand ? decodeHtmlEntities(row.brand) : <DataQualityBadge kind="missing_brand" />}</td>
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
  const paged = useClientPagination(rows, 'order lines');
  return (
    <TableShell caption={`${orders.length} order(s), ${rows.length} line(s)`} columns={['Action', 'Order', 'Woo Status', 'Customer', 'Total', 'SKU', 'Barcode', 'Name', 'Qty', 'Match', 'Availability', 'Sellable', 'Shortage', 'Warnings', 'Errors']} pagination={paged.pagination}>
      {paged.pageRows.map(({ order, line }) => (
        <tr key={`${order.woo_order_id}-${line.woo_line_item_id || line.sku}`}>
          <td>{order.action}</td>
          <td className="mono">{order.woo_order_number || order.woo_order_id}</td>
          <td>{StatusText(order.woo_status)}</td>
          <td>{order.customer_name}</td>
          <td>{formatCurrency(order.total)}</td>
          <td className="mono">{line.sku}</td>
          <td className="mono">{line.barcode}</td>
          <td className="description-cell"><ClampedText value={line.name} /></td>
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

function WooWritebackPanel({ status, queue, queuePagination = emptyServerPagination(50), onLoadQueue, stockSyncJobs, stockSyncJobsPagination = emptyServerPagination(25), onLoadStockSyncJobs, preview, message, loading, onPreviewStock, onPreviewOrderStatus, onQueue, onApprove, onSend, onCancel, onRevalidate, onSyncStock, onResumeStockJob, onCancelStockJob }) {
  const [stockForm, setStockForm] = useState({ sku: '', item_id: '', proposed_stock_quantity: '' });
  const [orderForm, setOrderForm] = useState({ woo_order_id: '', order_id: '', proposed_status: 'completed' });
  const [queueFilter, setQueueFilter] = useState('all');
  const [queueSearch, setQueueSearch] = useState('');
  const queueFilterInitializedRef = useRef(false);
  const liveLabel = status.dry_run ? 'Dry Run On' : 'Live Staging Writes On';

  useEffect(() => {
    if (!queueFilterInitializedRef.current) {
      queueFilterInitializedRef.current = true;
      return undefined;
    }
    const timeoutId = window.setTimeout(() => {
      onLoadQueue({
        status: queueFilter === 'all' ? undefined : queueFilter,
        search: queueSearch.trim() || undefined,
        page: 1,
        page_size: queuePagination.page_size,
      });
    }, 250);
    return () => window.clearTimeout(timeoutId);
  }, [queueFilter, queueSearch]);

  function activeQueueQuery() {
    return {
      status: queueFilter === 'all' ? undefined : queueFilter,
      search: queueSearch.trim() || undefined,
      page: queuePagination.page,
      page_size: queuePagination.page_size,
    };
  }

  function stockPayload() {
    return {
      sku: stockForm.sku || null,
      item_id: stockForm.item_id ? Number(stockForm.item_id) : null,
      proposed_stock_quantity: stockForm.proposed_stock_quantity === '' ? null : Number(stockForm.proposed_stock_quantity),
    };
  }
  function orderPayload() {
    return {
      woo_order_id: orderForm.woo_order_id ? Number(orderForm.woo_order_id) : null,
      order_id: orderForm.order_id ? Number(orderForm.order_id) : null,
      proposed_status: orderForm.proposed_status,
    };
  }
  return (
    <section className="writeback-workspace">
      <div className="writeback-overview-card">
        <div className="writeback-overview-header">
          <div>
            <span className="settings-view-eyebrow">Environment safeguards</span>
            <h2>WooCommerce write policy</h2>
            <p>Every outbound change continues through the current Pongo write guards.</p>
          </div>
          <span className={`status-pill ${status.dry_run ? 'order-status-pending' : 'order-status-completed'}`}>{liveLabel}</span>
        </div>
        <div className="writeback-guard-grid">
          <Metric label="Environment" value={status.environment || 'unknown'} />
          <Metric label="Writeback" value={status.writeback_enabled ? 'Enabled' : 'Blocked'} />
          <Metric label="Mode" value={status.dry_run ? 'Dry-run' : 'Live guarded'} />
          <Metric label="Stock" value={status.stock_write_allowed ? 'Allowed' : 'Blocked'} />
          <Metric label="Order Status" value={status.order_status_write_allowed ? 'Allowed' : 'Blocked'} />
          <Metric label="Allowed Host" value={status.allowed_host || 'Not set'} />
        </div>
        <div className="writeback-policy-line">
          <TriangleAlert size={18} aria-hidden="true" />
          <div>
            <strong>Hard-blocked operations</strong>
            <span>Product metadata · Customer writes · Coupons · Refunds · Delete</span>
          </div>
          <div className="button-row compact">
            <button className="muted-button" disabled={loading || !status.configured} onClick={() => onSyncStock(false)} type="button"><RefreshCw size={16} />Update changed stock</button>
            <button className="primary-button" disabled={loading || !status.configured} onClick={() => onSyncStock(true)} type="button"><Upload size={16} />Update all stock</button>
          </div>
        </div>
      </div>

      {message && <div className="success-strip">{message}</div>}

      <section className="writeback-queue-card" aria-labelledby="stock-sync-jobs-title">
        <div className="writeback-queue-header">
          <div>
            <span className="settings-view-eyebrow">Resumable catalog jobs</span>
            <h2 id="stock-sync-jobs-title">Update All history</h2>
            <p>Progress and failures persist after refresh. Paused jobs can resume from their saved chunk.</p>
          </div>
        </div>
        <TableShell
          caption={`${stockSyncJobsPagination.total} stock sync job(s)`}
          columns={['Created', 'Status', 'Progress', 'Sent', 'Failed', 'Last error', 'Actions']}
          pagination={serverTablePagination(
            stockSyncJobsPagination,
            'stock sync jobs',
            (page) => onLoadStockSyncJobs({ page, page_size: stockSyncJobsPagination.page_size }),
            (pageSize) => onLoadStockSyncJobs({ page: 1, page_size: pageSize }),
          )}
        >
          {stockSyncJobs.map((job) => (
            <tr key={job.id}>
              <td>{formatDateTime(job.created_at)}</td>
              <td>{StatusText(job.status)}</td>
              <td>{job.progress_percent}% · {job.processed_items}/{job.total_items}</td>
              <td>{job.sent_count + job.dry_run_count}</td>
              <td>{job.failed_count}</td>
              <td className="description-cell">
                {job.errors?.length ? (
                  <details>
                    <summary>{job.last_error || `${job.errors.length} error(s)`}</summary>
                    <ul>{job.errors.map((error, index) => <li key={`${job.id}-${index}`}>{error}</li>)}</ul>
                    <a
                      href={`data:text/plain;charset=utf-8,${encodeURIComponent(job.errors.join('\n'))}`}
                      download={`pongo-stock-sync-job-${job.id}-errors.txt`}
                    >Download error report</a>
                  </details>
                ) : '—'}
              </td>
              <td><div className="button-row compact">
                <button className="muted-button" disabled={loading || !['paused', 'completed_with_errors'].includes(job.status)} onClick={() => onResumeStockJob(job.id)} type="button">Resume</button>
                <button className="muted-button" disabled={loading || !['queued', 'running', 'paused'].includes(job.status)} onClick={() => onCancelStockJob(job.id)} type="button">Cancel</button>
              </div></td>
            </tr>
          ))}
          {!stockSyncJobs.length && <tr><td colSpan={7}><div className="empty-table-row">No Update All jobs have been created.</div></td></tr>}
        </TableShell>
      </section>

      <div className="writeback-action-layout">
        <article className="writeback-action-card">
          <div className="writeback-action-heading">
            <span className="writeback-action-icon"><Boxes size={20} /></span>
            <div><h3>Preview a stock change</h3><p>Target one mapped item by SKU or local item ID.</p></div>
          </div>
          <div className="writeback-field-grid">
            <label className="field"><span>SKU</span><input value={stockForm.sku} onChange={(event) => setStockForm((current) => ({ ...current, sku: event.target.value }))} placeholder="e.g. 70001" /></label>
            <label className="field"><span>Item ID</span><input value={stockForm.item_id} onChange={(event) => setStockForm((current) => ({ ...current, item_id: event.target.value }))} inputMode="numeric" /></label>
            <label className="field is-wide"><span>Proposed Woo stock</span><input value={stockForm.proposed_stock_quantity} onChange={(event) => setStockForm((current) => ({ ...current, proposed_stock_quantity: event.target.value }))} inputMode="decimal" /></label>
          </div>
          <button className="primary-button writeback-preview-button" disabled={loading || (!stockForm.sku && !stockForm.item_id)} onClick={() => onPreviewStock(stockPayload())} type="button"><Search size={17} />Preview stock writeback</button>
        </article>

        <article className="writeback-action-card">
          <div className="writeback-action-heading">
            <span className="writeback-action-icon is-order"><ShoppingCart size={20} /></span>
            <div><h3>Preview an order status</h3><p>Target one Woo or local order before queueing it.</p></div>
          </div>
          <div className="writeback-field-grid">
            <label className="field"><span>Woo Order ID</span><input value={orderForm.woo_order_id} onChange={(event) => setOrderForm((current) => ({ ...current, woo_order_id: event.target.value }))} inputMode="numeric" /></label>
            <label className="field"><span>Local Order ID</span><input value={orderForm.order_id} onChange={(event) => setOrderForm((current) => ({ ...current, order_id: event.target.value }))} inputMode="numeric" /></label>
            <label className="field is-wide"><span>Proposed Status</span><select value={orderForm.proposed_status} onChange={(event) => setOrderForm((current) => ({ ...current, proposed_status: event.target.value }))}><option value="processing">processing</option><option value="on-hold">on-hold</option><option value="completed">completed</option><option value="cancelled">cancelled</option><option value="refunded">refunded</option><option value="failed">failed</option></select></label>
          </div>
          <button className="primary-button writeback-preview-button" disabled={loading || (!orderForm.woo_order_id && !orderForm.order_id)} onClick={() => onPreviewOrderStatus(orderPayload())} type="button"><Search size={17} />Preview order writeback</button>
        </article>
      </div>

      {preview && (
        <div className="writeback-preview-ready">
          <div><strong>Preview ready</strong><span>{titleize(preview.operation_type)} is ready to enter the guarded queue.</span></div>
          <button className="primary-button" disabled={loading} onClick={() => onQueue(preview, activeQueueQuery())} type="button"><Plus size={16} />Add to queue</button>
        </div>
      )}

      <section className="writeback-queue-card" aria-labelledby="writeback-queue-title">
        <div className="writeback-queue-header">
          <div>
            <span className="settings-view-eyebrow">Review queue</span>
            <h2 id="writeback-queue-title">Writeback activity</h2>
            <p>{formatNumber(queuePagination.total)} matching queue item(s). Only the current server page is loaded.</p>
          </div>
          <label className="writeback-queue-search">
            <span className="sr-only">Search writeback queue</span>
            <Search size={16} aria-hidden="true" />
            <input value={queueSearch} onChange={(event) => setQueueSearch(event.target.value)} placeholder="Search operation, entity, Woo ID…" />
          </label>
        </div>
        <div className="writeback-queue-filters" aria-label="Filter writeback queue">
          {['all', 'pending', 'approved', 'failed', 'sent', 'cancelled'].map((filter) => (
            <button className={queueFilter === filter ? 'is-active' : ''} aria-pressed={queueFilter === filter} onClick={() => setQueueFilter(filter)} type="button" key={filter}>{titleize(filter)}</button>
          ))}
        </div>
        <WooWritebackQueueTable
          rows={queue}
          dryRun={status.dry_run}
          loading={loading}
          onApprove={(queueId) => onApprove(queueId, activeQueueQuery())}
          onSend={(queueId) => onSend(queueId, activeQueueQuery())}
          onCancel={(queueId) => onCancel(queueId, activeQueueQuery())}
          onRevalidate={(queueId) => onRevalidate(queueId, activeQueueQuery())}
          pagination={{
            ...serverTablePagination(
              queuePagination,
              'queue items',
              (page) => onLoadQueue({ status: queueFilter === 'all' ? undefined : queueFilter, search: queueSearch.trim() || undefined, page, page_size: queuePagination.page_size }),
              (pageSize) => onLoadQueue({ status: queueFilter === 'all' ? undefined : queueFilter, search: queueSearch.trim() || undefined, page: 1, page_size: pageSize }),
            ),
          }}
        />
      </section>
    </section>
  );
}

function WooWritebackQueueTable({ rows, dryRun, loading, onApprove, onSend, onCancel, onRevalidate, pagination }) {
  return (
    <TableShell className="writeback-queue-table" caption={`${pagination.total} matching queue item(s)`} columns={['Created', 'Operation', 'Entity', 'Woo ID', 'Status', 'Environment', 'Dry-run', 'Preview', 'Actions']} showActionBand={false} pagination={pagination}>
      {rows.map((row) => (
        <tr key={row.id}>
          <td>{formatDateTime(row.created_at)}</td>
          <td>{row.operation_type}</td>
          <td>{row.entity_type} {row.entity_id}</td>
          <td className="mono">{row.woo_entity_id}</td>
          <td>{StatusText(row.status)}</td>
          <td>{row.environment}</td>
          <td>{row.dry_run ? 'Yes' : 'No'}</td>
          <td className="description-cell">{writebackPreviewLabel(row)}</td>
          <td>
            <div className="button-row compact">
              <button className="muted-button" disabled={loading || !['pending', 'failed'].includes(row.status)} onClick={() => onApprove(row.id)} type="button">{row.status === 'failed' ? 'Retry' : 'Approve'}</button>
              {['update_product_stock', 'update_variation_stock'].includes(row.operation_type) && <button className="muted-button" disabled={loading || !['pending', 'failed'].includes(row.status)} onClick={() => onRevalidate(row.id)} type="button">Revalidate Mapping</button>}
              <button className="action-button" disabled={loading || row.status !== 'approved'} onClick={() => onSend(row.id)} type="button">{dryRun || row.dry_run ? 'Dry Run Send' : 'Send to Staging'}</button>
              <button className="muted-button" disabled={loading || !['pending', 'approved', 'failed'].includes(row.status)} onClick={() => onCancel(row.id)} type="button">Cancel</button>
            </div>
          </td>
        </tr>
      ))}
      {rows.length === 0 && <tr><td colSpan={9}><div className="empty-table-row">No staging writeback queue items yet.</div></td></tr>}
    </TableShell>
  );
}

function writebackPreviewLabel(row) {
  const preview = row.preview_json || {};
  if (row.operation_type === 'update_product_stock') {
    return `${preview.sku || 'item'}: Woo stock ${formatNumber(preview.woo_stock_snapshot)} -> ${formatNumber(preview.proposed_woo_stock)}`;
  }
  if (row.operation_type === 'update_order_status') {
    return `${preview.woo_order_number || preview.woo_order_id}: ${preview.current_woo_status || 'unknown'} -> ${preview.proposed_status}`;
  }
  return row.operation_type;
}

function WooRemapPanel({ candidates, candidatePagination = emptyServerPagination(100), onLoadCandidates, mappings, mappingPagination = emptyServerPagination(100), onLoadMappings, preview, message, loading, onPreview, onCommit, onRefresh }) {
  const [selected, setSelected] = useState({ woo_product_id: '', woo_variation_id: '', item_id: '', note: '' });
  const [selectedCandidate, setSelectedCandidate] = useState(null);

  function selectCandidate(candidate) {
    const firstSuggestion = candidate.suggested_items?.[0];
    setSelected({
      woo_product_id: candidate.remote.woo_product_id || '',
      woo_variation_id: candidate.remote.woo_variation_id || '',
      item_id: firstSuggestion?.item_id || candidate.current_mapping?.item_id || '',
      note: '',
    });
    setSelectedCandidate(candidate);
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
    <div className="wide-panel settings-operation-panel">
      <div className="panel-title">
        <div>
          <h2>WooCommerce Remap</h2>
          <p>Local-only relinking for Woo product/variation snapshots. It does not write WooCommerce or inventory.</p>
        </div>
        <button className="muted-button" onClick={onRefresh} disabled={loading} type="button"><RefreshCw size={17} />Refresh Remap</button>
      </div>
      {message && <div className="success-strip">{message}</div>}
      <div className="receiving-form route-form">
        <div className="receiving-header-fields route-header-fields">
          <div className="field"><span>Selected Woo record</span><strong>{selectedCandidate ? `${selectedCandidate.remote.woo_name || selectedCandidate.remote.woo_sku} (${selectedCandidate.remote.woo_product_id}${selectedCandidate.remote.woo_variation_id ? `/${selectedCandidate.remote.woo_variation_id}` : ''})` : 'Choose a candidate below'}</strong></div>
          <label className="field"><span>Suggested local item</span><select value={selected.item_id} onChange={(event) => setSelected((current) => ({ ...current, item_id: event.target.value }))}><option value="">Choose item</option>{(selectedCandidate?.suggested_items || []).map((item) => <option key={item.item_id} value={item.item_id}>{item.sku || item.description}</option>)}</select></label>
          <label className="field wide-field"><span>Note</span><input value={selected.note} onChange={(event) => setSelected((current) => ({ ...current, note: event.target.value }))} /></label>
        </div>
        <div className="button-row">
          <button className="primary-button" disabled={loading || !selected.woo_product_id || !selected.item_id} onClick={() => onPreview(payload())} type="button"><Search size={17} />Preview Mapping</button>
          <button className="action-button" disabled={loading || !preview || preview.errors?.length > 0} onClick={() => onCommit(payload())} type="button"><Link2 size={17} />Commit Mapping</button>
        </div>
      </div>
      {preview && (
        <div className={preview.errors?.length ? 'api-error' : 'success-strip'}>
          Preview maps Woo {preview.remote.woo_product_id}{preview.remote.woo_variation_id ? `/${preview.remote.woo_variation_id}` : ''} to {preview.item.sku || preview.item.description}. {(preview.warnings || []).join(' ')} {(preview.errors || []).join(' ')}
        </div>
      )}
      <TableShell caption={`${candidatePagination.total} remap candidate(s)`} columns={['Woo Product', 'Variation', 'SKU', 'Reason', 'Current Item', 'Suggestions', 'Action']} pagination={serverTablePagination(candidatePagination, 'remap candidates', (page) => onLoadCandidates({ page, page_size: candidatePagination.page_size }), (pageSize) => onLoadCandidates({ page: 1, page_size: pageSize }))}>
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
      <TableShell caption={`${mappingPagination.total} active mapping(s)`} columns={['Item ID', 'Woo Product', 'Variation', 'SKU', 'Source', 'Active', 'Updated']} pagination={serverTablePagination(mappingPagination, 'active mappings', (page) => onLoadMappings({ page, page_size: mappingPagination.page_size }), (pageSize) => onLoadMappings({ page: 1, page_size: pageSize }))}>
        {mappings.map((mapping) => (
          <tr key={mapping.id}><td>{mapping.item_id}</td><td className="mono">{mapping.woo_product_id}</td><td className="mono">{mapping.woo_variation_id}</td><td className="mono">{mapping.woo_sku}</td><td>{mapping.mapping_source}</td><td>{mapping.active ? 'Yes' : 'No'}</td><td>{formatDateTime(mapping.updated_at)}</td></tr>
        ))}
        {mappings.length === 0 && <tr><td colSpan={7}><div className="empty-table-row">No active local remap records yet.</div></td></tr>}
      </TableShell>
    </div>
  );
}

function WooSyncRunsTable({ runs, pagination = emptyServerPagination(50), onLoad }) {
  return (
    <TableShell caption={`${pagination?.total ?? runs.length} sync run(s)`} columns={['Started At', 'Completed At', 'Sync Type', 'Status', 'Total Records', 'Created', 'Updated', 'Matched', 'Skipped', 'Conflicts', 'Errors', 'Created By']} pagination={serverTablePagination(pagination, 'sync runs', (page) => onLoad?.({ page, page_size: pagination.page_size || 50 }), (pageSize) => onLoad?.({ page: 1, page_size: pageSize }))}>
      {runs.map((run) => (
        <tr key={run.id}>
          <td>{formatDateTime(run.started_at)}</td>
          <td>{formatDateTime(run.completed_at)}</td>
          <td>{titleize(run.sync_type)}</td>
          <td>{StatusText(run.status)}</td>
          <td>{formatNumber(run.total_remote_records)}</td>
          <td>{formatNumber(run.created_count)}</td>
          <td>{formatNumber(run.updated_count)}</td>
          <td>{formatNumber(run.matched_count)}</td>
          <td>{formatNumber(run.skipped_count)}</td>
          <td>{formatNumber(run.conflict_count)}</td>
          <td>{formatNumber(run.error_count)}</td>
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

function TableShell({ caption, columns, children, className = '', showActionBand = true, pagination = null }) {
  return (
    <div className={`table-wrap table-card ${className}`.trim()}>
      <div className="table-meta">
        <span>{caption}</span>
        <TablePager pagination={pagination} />
      </div>
      {showActionBand && (
        <div className="table-action-band">
          <span>Actions</span>
          <ChevronDown size={18} />
        </div>
      )}
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={typeof column === 'string' ? column : column.key}>{typeof column === 'string' ? column : column.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>{children}</tbody>
        </table>
      </div>
    </div>
  );
}

function paginationFromResponse(body = {}, fallbackPageSize = 20) {
  const pageSize = Math.max(1, Number(body.page_size || fallbackPageSize || 20));
  const total = Math.max(0, Number(body.total ?? body.total_candidates ?? 0));
  const totalPages = Math.max(1, Number(body.total_pages || Math.ceil(total / pageSize) || 1));
  const page = Math.min(totalPages, Math.max(1, Number(body.page || 1)));
  const returnedRows = body.orders
    || body.receipts
    || body.movements
    || body.allocations
    || body.picks
    || body.fulfillments
    || body.sync_runs
    || body.cycle_counts
    || body.routes
    || body.queue
    || body.jobs
    || body.transfers
    || body.adjustments
    || body.candidates
    || body.rows
    || [];
  return {
    page,
    page_size: pageSize,
    total,
    total_pages: totalPages,
    returned_count: Math.max(0, Number(body.returned_count ?? returnedRows.length ?? 0)),
    has_previous: body.has_previous ?? page > 1,
    has_next: body.has_next ?? page < totalPages,
  };
}

function serverTablePagination(meta, noun, onPageChange, onPageSizeChange) {
  return {
    page: meta?.page || 1,
    pageSize: meta?.page_size || 20,
    total: meta?.total || 0,
    totalPages: meta?.total_pages || 1,
    returnedCount: meta?.returned_count || 0,
    noun,
    onPageChange,
    onPageSizeChange,
  };
}

function TablePager({ pagination }) {
  if (!pagination) return null;
  const total = Math.max(0, toNumber(pagination.total));
  const pageSize = Math.max(1, toNumber(pagination.pageSize) || 20);
  const totalPages = total === 0 ? 0 : Math.max(1, toNumber(pagination.totalPages) || Math.ceil(total / pageSize));
  const page = totalPages === 0 ? 0 : Math.min(totalPages, Math.max(1, toNumber(pagination.page) || 1));
  const returnedCount = Math.max(0, toNumber(pagination.returnedCount));
  const rangeStart = total && returnedCount ? (page - 1) * pageSize + 1 : 0;
  const rangeEnd = total && returnedCount ? Math.min(total, rangeStart + returnedCount - 1) : 0;
  const noun = pagination.noun || 'records';
  return (
    <div className="table-pager" aria-label={`${titleize(noun)} pagination`}>
      <span>Showing {formatNumber(rangeStart)}–{formatNumber(rangeEnd)} of {formatNumber(total)} {noun}</span>
      <label className="table-page-size"><span>Rows per page</span><select aria-label="Rows per page" value={pageSize} onChange={(event) => pagination.onPageSizeChange?.(Number(event.target.value))}>{[20, 50, 100].map((size) => <option value={size} key={size}>{size}</option>)}</select></label>
      <button className="pager-button" aria-label="Previous page" onClick={() => pagination.onPageChange?.(page - 1)} disabled={page <= 1} type="button"><ChevronLeft size={18} aria-hidden="true" /></button>
      {totalPages > 0 ? <><label className="table-page-number"><span className="sr-only">Current page</span><select aria-label="Current page" value={page} onChange={(event) => pagination.onPageChange?.(Number(event.target.value))}>{Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => <option value={pageNumber} key={pageNumber}>{pageNumber}</option>)}</select></label><span>of {formatNumber(totalPages)}</span></> : <span>No pages</span>}
      <button className="pager-button active" aria-label="Next page" onClick={() => pagination.onPageChange?.(page + 1)} disabled={page >= totalPages || total === 0} type="button"><ChevronRight size={18} aria-hidden="true" /></button>
    </div>
  );
}

function getHeaderMeta(route, items) {
  if (route.pageId === 'items') {
    if (route.itemView === 'import') {
      return { title: 'Import Items', kicker: 'Guided CSV workspace', tabs: [] };
    }
    if (route.itemView === 'import-history') {
      return { title: 'Import History', kicker: 'Item import audit trail', tabs: [] };
    }
    if (route.itemView === 'new') {
      return { title: 'New Item', kicker: 'Item', tabs: [] };
    }
    if (route.itemView === 'detail') {
      const item = items.find((candidate) => String(candidate.id) === String(route.itemId));
      return { title: item ? `Edit ${item.SKU}` : 'Edit Item', kicker: 'Item', tabs: [] };
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
  if (route.pageId === 'inventory') {
    const meta = inventorySubpageMeta[route.inventoryView || 'all'] || inventorySubpageMeta.all;
    return { ...meta, tabs: [] };
  }
  if (route.pageId === 'reports') {
    const report = allReportDefinitions.find((candidate) => candidate.key === route.reportKey) || allReportDefinitions[0];
    const category = reportCategories.find((candidate) => candidate.id === report.category);
    return { title: report.label, kicker: `Reports / ${category?.label || 'Inventory'}`, tabs: pageMeta.reports.tabs };
  }
  if (route.pageId === 'settings') {
    const meta = settingsViewMeta[route.settingsView || 'connection'] || settingsViewMeta.connection;
    return { ...meta, tabs: pageMeta.settings.tabs };
  }
  if (route.pageId === 'routes') {
    const meta = routeSubpageMeta[route.routesView || 'live'] || routeSubpageMeta.live;
    return { ...meta, tabs: pageMeta.routes.tabs };
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
  if (route.pageId === 'reports' && tab.category) {
    return route.reportCategory === tab.category;
  }
  if (route.pageId === 'settings' && tab.href) {
    return tab.href === `#/settings/${route.settingsView || 'connection'}`;
  }
  if (route.pageId === 'routes' && tab.href) {
    return tab.href === `#/routes/${route.routesView || 'live'}`;
  }
  return index === 0;
}

function uniqueOptions(items, field) {
  return [...new Set(items.map((item) => item[field]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function buildInventoryItemRows(items, locationRows, activeSearch, filters, inventoryView) {
  const rowsByItem = new Map();
  locationRows.forEach((row) => {
    if (!rowsByItem.has(row.item_id)) {
      rowsByItem.set(row.item_id, []);
    }
    rowsByItem.get(row.item_id).push(row);
  });
  const query = String(activeSearch || '').trim().toLowerCase();
  return items
    .filter((item) => {
      const itemLocationRows = rowsByItem.get(item.id) || [];
      const matchesSearch =
        !query ||
        SEARCH_FIELDS.some((field) => String(item[field] ?? '').toLowerCase().includes(query)) ||
        itemLocationRows.some((row) => [row.warehouse, row.inventory_location, row.location_code, row.location_name].some((value) => String(value || '').toLowerCase().includes(query)));
      const matchesCategory = !filters.category || item.Category === filters.category;
      const matchesBrand = !filters.brand || item.Brand === filters.brand;
      const underPar = Boolean(item['Under Par']) || itemLocationRows.some((row) => row.under_par);
      const matchesView = inventoryView !== 'low-stock' ? true : underPar;
      return matchesSearch && matchesCategory && matchesBrand && matchesView;
    })
    .map((item) => {
      const itemLocationRows = rowsByItem.get(item.id) || [];
      const defaultRow = itemLocationRows.find((row) => row.is_default_location) || itemLocationRows[0];
      const extraLocations = Math.max(0, itemLocationRows.length - 1);
      const locationSummary = defaultRow ? `${defaultRow.inventory_location || defaultRow.location_code || 'Unassigned'}${extraLocations ? ` +${extraLocations} locations` : ''}` : item['Default Location'] || item['Inventory Location'] || 'Unassigned';
      return { item, locationRows: itemLocationRows, locationSummary, underPar: Boolean(item['Under Par']) || itemLocationRows.some((row) => row.under_par) };
    });
}

function inventoryLocationKey(row) {
  return `${row.warehouse || ''}::${row.inventory_location || ''}`;
}

function groupLocationRows(rows) {
  const groups = new Map();
  rows.forEach((row) => {
    const key = inventoryLocationKey(row);
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        warehouse: row.warehouse || '',
        inventory_location: row.inventory_location || '',
        item_count: 0,
        total_in_stock: 0,
        total_allocated: 0,
        total_sellable: 0,
        total_on_order: 0,
        total_inventory_value: 0,
        under_par_count: 0,
      });
    }
    const group = groups.get(key);
    group.item_count += 1;
    group.total_in_stock += toNumber(row.in_stock);
    group.total_allocated += toNumber(row.allocated);
    group.total_sellable += toNumber(row.sellable);
    group.total_on_order += toNumber(row.on_order);
    group.total_inventory_value += toNumber(row.in_stock) * toNumber(row.item?.['Unit Cost']);
    group.under_par_count += row.under_par ? 1 : 0;
  });
  return [...groups.values()].sort((a, b) => `${a.warehouse} ${a.inventory_location}`.localeCompare(`${b.warehouse} ${b.inventory_location}`));
}

function inventoryTotal(items, field) {
  return items.reduce((total, item) => total + toNumber(item[field]), 0);
}

function inventoryValue(items) {
  return items.reduce((total, item) => total + toNumber(item['In Stock']) * toNumber(item['Unit Cost']), 0);
}

function formatOpenOrders(item) {
  const quantity = toNumber(item.open_order_quantity);
  const count = toNumber(item.open_orders_count);
  if (quantity && count) {
    return `${formatNumber(quantity)} qty / ${formatNumber(count)} order${count === 1 ? '' : 's'}`;
  }
  if (quantity) {
    return `${formatNumber(quantity)} qty`;
  }
  if (count) {
    return `${formatNumber(count)} order${count === 1 ? '' : 's'}`;
  }
  return '0';
}

function stockMovementFiltersToApi(search, filters = {}) {
  return {
    search,
    movement_type: filters.movement_type,
    warehouse: filters.warehouse,
    inventory_location: filters.inventory_location,
    date_from: filters.date_from,
    date_to: filters.date_to,
  };
}

function productTitle(item = {}) {
  return decodeHtmlEntities(item?.wooName || item?.woo_name || item?.Description || item?.description || '');
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
    routeDate: '',
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
  return typeof value === 'string' ? decodeHtmlEntities(value) : value || '';
}

const APP_LOCALE = 'en-CA';
const APP_CURRENCY = 'CAD';
const numberFormatter = new Intl.NumberFormat(APP_LOCALE, { maximumFractionDigits: 3 });
const percentFormatter = new Intl.NumberFormat(APP_LOCALE, { maximumFractionDigits: 1, style: 'percent' });
const dateTimeFormatter = new Intl.DateTimeFormat(APP_LOCALE, { dateStyle: 'medium', timeStyle: 'short' });
const currencyFormatters = new Map();

function isMissingValue(value) {
  return value === null || value === undefined || value === '';
}

function decodeHtmlEntities(value) {
  if (typeof value !== 'string' || !value.includes('&')) return value ?? '';
  if (typeof document === 'undefined') return value;
  decodeHtmlEntities.decoder ||= document.createElement('textarea');
  decodeHtmlEntities.decoder.innerHTML = value;
  return decodeHtmlEntities.decoder.value;
}

function formatCurrency(value, currency = APP_CURRENCY) {
  if (isMissingValue(value)) return '—';
  const currencyCode = /^[A-Z]{3}$/.test(String(currency || '').toUpperCase()) ? String(currency).toUpperCase() : APP_CURRENCY;
  if (!currencyFormatters.has(currencyCode)) currencyFormatters.set(currencyCode, new Intl.NumberFormat(APP_LOCALE, { style: 'currency', currency: currencyCode }));
  return currencyFormatters.get(currencyCode).format(toNumber(value));
}

function formatNumber(value) {
  if (isMissingValue(value)) return '—';
  return numberFormatter.format(toNumber(value));
}

function formatPercent(value) {
  if (isMissingValue(value)) return '—';
  return percentFormatter.format(toNumber(value) / 100);
}

function formatDateTime(value) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? decodeHtmlEntities(String(value)) : dateTimeFormatter.format(date);
}

export { formatCurrency, formatDateTime, formatInsightValue, formatNumber, formatPercent, formatReportValue };

function formatReportValue(value, key = '') {
  if (value === null || value === undefined || value === '') {
    return 'Not available';
  }
  if (typeof value === 'number') {
    if (/(^|_)(count|rows|skus|units|items|orders|customers|locations)$/i.test(key)) return formatNumber(value);
    if (/(_rate|_percent|percentage)$/i.test(key)) return formatPercent(value);
    if (/(revenue|sales|value|amount|discount|cost|margin|spend|price|aov|order_total|subscription_total)/i.test(key)) return formatCurrency(value);
    return formatNumber(value);
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatDateTime(value);
  }
  return decodeHtmlEntities(String(value));
}

function formatInsightValue(key, value) {
  if (value === null || value === undefined) {
    return 'Not available';
  }
  if (typeof value === 'boolean') {
    return value ? 'Yes' : 'No';
  }
  if (typeof value === 'number') {
    if (/(^|_)(count|rows|skus|units|items|orders|customers|locations)$/i.test(String(key))) {
      return formatNumber(value);
    }
    if (/(_rate|_percent|percentage|margin_percent)$/i.test(String(key))) {
      return formatPercent(value);
    }
    if (/(revenue|sales|value|amount|discount|cost|margin|spend|price|aov|order_total|subscription_total)/i.test(String(key))) {
      return formatCurrency(value);
    }
    return formatNumber(value);
  }
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return formatDateTime(value);
  }
  if (typeof value === 'string' && /(status|risk)$/i.test(String(key))) {
    return titleize(value);
  }
  if (typeof value === 'object') {
    return decodeHtmlEntities(value.sku || value.product_name || value.description || value.label || '');
  }
  return decodeHtmlEntities(String(value));
}

function titleize(value) {
  return decodeHtmlEntities(String(value || ''))
    .replace(/_/g, ' ')
    .replace(/-/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function markerPosition(marker) {
  const latitude = toNumber(marker.latitude);
  const longitude = toNumber(marker.longitude);
  const minLat = 53.15;
  const maxLat = 53.75;
  const minLng = -114.05;
  const maxLng = -113.1;
  const left = Math.min(92, Math.max(8, ((longitude - minLng) / (maxLng - minLng)) * 100));
  const top = Math.min(88, Math.max(12, 100 - ((latitude - minLat) / (maxLat - minLat)) * 100));
  return { left, top };
}

function formatCountType(value) {
  return value === 'full_location' ? 'Full Location' : 'Selected Items';
}

function Badge({ tone = 'neutral', children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

const dataQualityLabels = {
  missing_sku: 'SKU missing',
  missing_barcode: 'Barcode missing',
  missing_brand: 'Brand missing',
  missing_category: 'Category missing',
  missing_cost: 'Cost missing',
  missing_location: 'Location unassigned',
  unmapped: 'Mapping missing',
  receiving: 'Receiving staging',
  unavailable: 'Not available',
};

function DataQualityBadge({ kind }) {
  const tone = kind === 'receiving' ? 'info' : kind === 'unavailable' ? 'neutral' : 'warning';
  return <span className={`badge badge-${tone} data-quality-badge`}>{dataQualityLabels[kind] || titleize(kind)}</span>;
}

function ClampedText({ value }) {
  if (isMissingValue(value)) return <DataQualityBadge kind="unavailable" />;
  const text = decodeHtmlEntities(String(value));
  return <span className="clamped-text" title={text} aria-label={text} tabIndex={0}>{text}</span>;
}

function LocationPresentation({ value }) {
  if (isMissingValue(value) || /^unassigned$/i.test(String(value).trim())) return <DataQualityBadge kind="missing_location" />;
  const text = decodeHtmlEntities(String(value));
  if (/^receiving\b/i.test(text)) {
    const suffix = text.replace(/^receiving/i, '');
    return <span className="location-presentation"><DataQualityBadge kind="receiving" />{suffix && <small>{suffix}</small>}</span>;
  }
  return text;
}

function BooleanBadge({ value }) {
  return <span className={value ? 'boolean-badge yes' : 'boolean-badge no'}>{value ? 'Yes' : 'No'}</span>;
}

function StatusBadge({ active }) {
  return <span className={active ? 'status-pill' : 'status-pill inactive'}>{active ? 'Active' : 'Inactive'}</span>;
}

async function exportItemsCsv(filters, filename = 'pongo-inventory-items-export.csv') {
  const response = await apiFetch(`${API_BASE_URL}/api/items/export${filtersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder('Unable to export CSV from the backend. Start the FastAPI server and try again.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportEnrichmentCsv() {
  const response = await apiFetch(`${API_BASE_URL}/api/items/enrichment/export`);
  if (!response.ok) {
    showPlaceholder('Unable to export the enrichment template. Import WooCommerce mappings first and confirm FastAPI is running.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-woo-enrichment-template.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function downloadPreviewRows(rows = [], actions = [], fileName = 'pongo-import-exceptions.csv') {
  const selected = rows.filter((row) => actions.includes(row.action));
  if (!selected.length) return;
  const rawColumns = [...new Set(selected.flatMap((row) => Object.keys(row.raw_row || row.row || {})))];
  const columns = [...rawColumns, 'Import Action', 'Error Message'];
  const quote = (value) => `"${String(value ?? '').replace(/"/g, '""')}"`;
  const csv = [columns.map(quote).join(','), ...selected.map((row) => columns.map((column) => quote(column === 'Import Action' ? row.action : column === 'Error Message' ? [...(row.warnings || []), ...(row.errors || [])].join(' ') : (row.raw_row || row.row || {})[column])).join(','))].join('\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportLocationsCsv(filters) {
  const response = await apiFetch(`${API_BASE_URL}/api/locations/export${locationsFiltersToQueryString(filters)}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/inventory/export/by-location${inventoryFiltersToQueryString(filters)}`);
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

async function exportStockMovementsCsv(filters) {
  const response = await apiFetch(`${API_BASE_URL}/api/stock-movements/export${plainFiltersToQueryString(filters)}`);
  if (!response.ok) {
    showPlaceholder('Unable to export stock movements from the backend.');
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-stock-movements-export.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportReceivedInventoryCsv(filters) {
  const response = await apiFetch(`${API_BASE_URL}/api/reports/received-inventory/export${plainFiltersToQueryString(receivedInventoryFiltersToApi(filters))}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/reports/fulfillments/export${plainFiltersToQueryString(fulfillmentReportFiltersToApi(filters))}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/reports/sku-orders/export${plainFiltersToQueryString(skuOrdersFiltersToApi(filters))}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/reports/${reportKey}/export${plainFiltersToQueryString(filters)}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/orders/open/export${plainFiltersToQueryString(openOrderFiltersToApi(filters))}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/orders/completed/export${plainFiltersToQueryString(completedOrderFiltersToApi(filters))}`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/allocations/${allocationId}/export`);
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

async function exportAllocationExceptionsCsv(filters) {
  const response = await apiFetch(`${API_BASE_URL}/api/allocations/exceptions/export${plainFiltersToQueryString(allocationExceptionFiltersToApi(filters))}`);
  if (!response.ok) throw new Error(`Allocation exceptions export returned ${response.status}`);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'pongo-allocation-exceptions.csv';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function exportPickCsv(pickId, pickNumber) {
  const response = await apiFetch(`${API_BASE_URL}/api/picks/${pickId}/export`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/fulfillments/${fulfillmentId}/export`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/routes/${routeId}/export`);
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
  const response = await apiFetch(`${API_BASE_URL}/api/cycle-counts/${cycleCountId}/export`);
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

async function uploadImportFile(path, file, fields = {}) {
  const formData = new FormData();
  formData.append('file', file);
  Object.entries(fields).forEach(([key, value]) => formData.append(key, String(value)));
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const detail = await safeResponseText(response);
    throw new Error(detail || `Import API returned ${response.status}`);
  }
  return response.json();
}

async function runWooCatalogBatchesRequest(endpoint, blockedSkus = []) {
  let page = 1;
  const countKeys = ['total_remote_records', 'create_count', 'update_count', 'matched_count', 'skipped_count', 'conflict_count', 'error_count', 'simple_products_examined', 'variable_parents_examined', 'purchasable_variations_examined', 'new_simple_count', 'new_variation_count', 'unchanged_count', 'skipped_parent_count', 'missing_sku_count', 'duplicate_sku_conflict_count', 'duplicate_mapping_conflict_count', 'unmapped_count', 'invalid_count'];
  const summary = { configured: true, status: 'completed', warnings: [], errors: [], preview_rows: [], unmatched_local_count: 0, unmatched_local_skus: [] };
  countKeys.forEach((key) => { summary[key] = 0; });
  while (page) {
    const batch = await postJson(endpoint, { include_statuses: ['publish'], page, per_page: 50, blocked_skus: blockedSkus, created_by: 'items-import-mappings' });
    countKeys.forEach((key) => { summary[key] += Number(batch[key] || 0); });
    summary.configured = summary.configured && batch.configured !== false;
    summary.sync_run_id = batch.sync_run_id || summary.sync_run_id;
    summary.warnings.push(...(batch.warnings || []));
    summary.errors.push(...(batch.errors || []));
    summary.preview_rows.push(...(batch.preview_rows || []));
    summary.unmatched_local_count = batch.unmatched_local_count || 0;
    summary.unmatched_local_skus = batch.unmatched_local_skus || [];
    page = batch.has_more ? (batch.next_page || page + 1) : null;
  }
  if (endpoint.endsWith('/preview')) {
    const counts = new Map();
    summary.preview_rows.forEach((row) => {
      if (row.remote_type === 'variable') return;
      const sku = String(row.sku || '').trim().toLowerCase();
      if (sku) counts.set(sku, (counts.get(sku) || 0) + 1);
    });
    summary.duplicate_skus = [...counts.entries()].filter(([, count]) => count > 1).map(([sku]) => sku);
    summary.preview_rows = summary.preview_rows.map((row) => {
      const sku = String(row.sku || '').trim().toLowerCase();
      if (row.remote_type === 'variable' || !summary.duplicate_skus.includes(sku)) return row;
      const message = 'Duplicate WooCommerce SKU; this product was not changed.';
      return { ...row, action: 'conflict', status: 'conflict', errors: (row.errors || []).includes(message) ? row.errors : [...(row.errors || []), message] };
    });
    summary.create_count = summary.preview_rows.filter((row) => row.action === 'create').length;
    summary.update_count = summary.preview_rows.filter((row) => row.action === 'update').length;
    summary.unchanged_count = summary.preview_rows.filter((row) => row.action === 'unchanged').length;
    summary.skipped_count = summary.preview_rows.filter((row) => row.action === 'skip').length;
    summary.conflict_count = summary.preview_rows.filter((row) => row.action === 'conflict').length;
    summary.error_count = summary.preview_rows.filter((row) => row.action === 'error').length;
    summary.errors = summary.preview_rows.flatMap((row) => row.errors || []);
  } else if (summary.conflict_count || summary.error_count) {
    summary.status = 'completed_with_errors';
  }
  return summary;
}

async function postJson(path, payload) {
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = apiErrorDetail(body);
    } catch {
      detail = await safeResponseText(response);
    }
    throw new Error(detail || `API returned ${response.status}`);
  }
  return response.json();
}

async function patchJson(path, payload) {
  const response = await apiFetch(`${API_BASE_URL}${path}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    let detail = '';
    try {
      const body = await response.json();
      detail = apiErrorDetail(body);
    } catch {
      detail = await safeResponseText(response);
    }
    throw new Error(detail || `API returned ${response.status}`);
  }
  return response.json();
}

function apiErrorDetail(body) {
  const detail = body?.detail ?? body;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail?.errors)) return detail.errors.join(' ');
  if (typeof detail?.message === 'string') return detail.message;
  return JSON.stringify(detail);
}

function normalizeHostname(value) {
  return String(value || '').trim().toLowerCase().replace(/\.$/, '');
}

function hostnameFromUrl(value) {
  try {
    return normalizeHostname(new URL(value).hostname);
  } catch {
    return '';
  }
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

function filtersToQueryString(filters = {}, options = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.category) params.set('category', filters.category);
  if (filters.brand) params.set('brand', filters.brand);
  if (filters.status === 'active') params.set('active', 'true');
  if (filters.status === 'inactive') params.set('active', 'false');
  if (filters.stockStatus) params.set('stock_status', filters.stockStatus);
  if (filters.latestWooImport) params.set('latest_woo_import', 'true');
  params.set('include_non_inventory', String(Boolean(filters.includeNonInventory)));
  if (filters.page) params.set('page', String(filters.page));
  if (filters.pageSize) params.set('page_size', String(filters.pageSize));
  if (filters.sortBy) params.set('sort_by', filters.sortBy);
  if (filters.sortDir) params.set('sort_direction', filters.sortDir);
  if (filters.dataQuality) params.set('data_quality', filters.dataQuality);
  if (filters.editable) params.set('editable', 'true');
  if (options.includeFacets !== undefined) params.set('include_facets', String(Boolean(options.includeFacets)));
  const query = params.toString();
  return query ? `?${query}` : '';
}

function inventoryRouteToItemFilters(route) {
  const paged = (route.inventoryView || 'all') === 'all';
  return {
    search: route.inventorySearch || '',
    category: route.inventoryCategory || '',
    brand: route.inventoryBrand || '',
    includeNonInventory: true,
    page: paged ? route.inventoryPage || 1 : undefined,
    pageSize: paged ? route.inventoryPageSize || 20 : undefined,
    sortBy: route.inventorySortBy || 'sku',
    sortDir: route.inventorySortDir || 'asc',
    dataQuality: route.inventoryDataQuality || '',
  };
}

function inventoryRouteHref(route, changes = {}) {
  const next = {
    page: route.inventoryPage || 1,
    pageSize: route.inventoryPageSize || 20,
    search: route.inventorySearch || '',
    category: route.inventoryCategory || '',
    brand: route.inventoryBrand || '',
    dataQuality: route.inventoryDataQuality || '',
    sortBy: route.inventorySortBy || 'sku',
    sortDir: route.inventorySortDir || 'asc',
    ...changes,
  };
  const params = new URLSearchParams({ page: String(Math.max(1, next.page)), page_size: String(next.pageSize) });
  if (next.search) params.set('search', next.search);
  if (next.category) params.set('category', next.category);
  if (next.brand) params.set('brand', next.brand);
  if (next.dataQuality) params.set('data_quality', next.dataQuality);
  if (next.sortBy && next.sortBy !== 'sku') params.set('sort_by', next.sortBy);
  if (next.sortDir && next.sortDir !== 'asc') params.set('sort_dir', next.sortDir);
  return `#/inventory/${route.inventoryView || 'all'}?${params.toString()}`;
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

function allocationExceptionFiltersToApi(filters = {}) {
  return {
    search: filters.search,
    warehouse: filters.warehouse,
    ordered_from: filters.orderedFrom,
    ordered_to: filters.orderedTo,
    include_fully_allocated: filters.includeFullyAllocated || undefined,
  };
}

function inventoryFiltersToQueryString(filters = {}) {
  const params = new URLSearchParams();
  if (filters.search) params.set('search', filters.search);
  if (filters.warehouse) params.set('warehouse', filters.warehouse);
  if (filters.inventoryLocation) params.set('inventory_location', filters.inventoryLocation);
  if (filters.defaultLocation) params.set('default_location', filters.defaultLocation);
  if (filters.category) params.set('category', filters.category);
  if (filters.brand) params.set('brand', filters.brand);
  if (filters.underPar) params.set('under_par', filters.underPar);
  if (filters.dataQuality) params.set('data_quality', filters.dataQuality);
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
    order_number: filters.orderNumber,
    customer: filters.customer,
    containing_item: filters.containingItem,
    warehouse: filters.warehouse,
    woo_status: filters.wooStatus,
    availability_status: filters.availabilityStatus,
    matched_status: filters.matchedStatus,
    page: filters.page,
    page_size: filters.pageSize,
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
    page: filters.page,
    page_size: filters.pageSize || filters.page_size,
  };
}

function routeCandidateFiltersToApi(filters = {}) {
  return {
    route_date: filters.routeDate,
    local_status: filters.localStatus,
    customer_email: filters.customerEmail,
    woo_order_number: filters.wooOrderNumber,
    search: filters.search,
    page: filters.page,
    page_size: filters.pageSize || filters.page_size,
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
    if (!['In Stock', 'Allocated', 'Sellable', 'Under Par', 'On Order', 'Storage Volume'].includes(column)) {
      payload[column] = item[column];
    }
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

function operationalItemId(item) {
  return item?.id || null;
}

function operationalItemSku(item) {
  return String(item?.sku ?? item?.SKU ?? '').trim();
}

function operationalItemBarcode(item) {
  return String(item?.barcode ?? item?.Barcode ?? '').trim();
}

function operationalItemStock(item) {
  return item?.in_stock ?? item?.['In Stock'] ?? null;
}

function operationalItemMatchesQuery(item, query) {
  const normalizedQuery = String(query || '').trim().toLowerCase();
  if (!item || !normalizedQuery) return false;
  return [operationalItemSku(item), operationalItemBarcode(item)].some((value) => value.toLowerCase() === normalizedQuery);
}

function findReceivingItem(items, query) {
  const normalizedQuery = String(query || '').trim().toLowerCase();
  if (!normalizedQuery) {
    return null;
  }
  return items.find((item) => operationalItemMatchesQuery(item, normalizedQuery)) || null;
}

function receivingPayload(form, items) {
  return {
    warehouse: form.warehouse,
    reference_number: form.reference_number,
    notes: form.notes,
    created_by: 'system',
    lines: form.lines.map((line) => {
      const item = line.selected_item || findReceivingItem(items, line.query);
      const query = String(line.query || '').trim();
      const sku = operationalItemSku(item);
      const barcode = operationalItemBarcode(item);
      return {
        item_id: operationalItemId(item),
        sku: sku || query || null,
        barcode: barcode || (!item && query ? query : null),
        inventory_location: line.inventory_location,
        default_location: line.inventory_location,
        quantity_received: toNumber(line.quantity_received),
        unit_cost: line.unit_cost === '' ? null : toNumber(line.unit_cost),
        notes: line.notes,
      };
    }),
  };
}

function receivingCommitReason(form, preview, loading) {
  if (loading) return 'receipt validation is still in progress.';
  const selectedLines = (form.lines || []).filter((line) => String(line.query || '').trim());
  if (!selectedLines.length) return 'add at least one SKU or barcode.';
  if (selectedLines.some((line) => !String(line.inventory_location || '').trim())) return 'choose a destination location for every selected item.';
  if (selectedLines.some((line) => !Number.isFinite(Number(line.quantity_received)) || Number(line.quantity_received) <= 0)) return 'enter a quantity greater than zero for every selected item.';
  if (!preview) return 'preview the receipt after completing the required fields.';
  if (toNumber(preview.invalid_lines) > 0) return `resolve ${formatNumber(preview.invalid_lines)} validation error${toNumber(preview.invalid_lines) === 1 ? '' : 's'} shown below.`;
  return '';
}

function cycleCountPayload(form, items) {
  return {
    warehouse: form.warehouse,
    inventory_location: form.inventory_location || null,
    count_type: form.count_type,
    notes: form.notes,
    created_by: 'system',
    lines: form.lines.map((line) => {
      const item = line.selected_item || findReceivingItem(items, line.query);
      const query = String(line.query || '').trim();
      const sku = operationalItemSku(item);
      const barcode = operationalItemBarcode(item);
      return {
        item_id: operationalItemId(item),
        sku: sku || query || null,
        barcode: barcode || (!item && query ? query : null),
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
