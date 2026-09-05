export const company = {
  name: 'Northstar Commerce',
  subtitle: 'Operations workspace',
  stats: [
    { label: 'SKUs', value: '2,487', detail: '96% data complete', trend: '+42 this month' },
    { label: 'Open orders', value: '186', detail: '42 ready to pick', trend: '14 since 8 AM' },
    { label: 'Inventory value', value: '$842,430', detail: 'Across 3 warehouses', trend: '+3.8% this quarter' },
    { label: 'Order accuracy', value: '98.4%', detail: '30-day average', trend: '+0.6 pts' },
  ],
};

export const commandMetrics = [
  { label: 'Open orders', value: '186', meta: '14 new today', tone: 'violet' },
  { label: 'Ready to pick', value: '42', meta: '8 priority', tone: 'aqua' },
  { label: 'Low stock', value: '18', meta: '5 below safety', tone: 'amber' },
  { label: 'Receiving today', value: '1,260', meta: 'units · 6 receipts', tone: 'blue' },
  { label: 'Inventory value', value: '$842k', meta: '3 warehouses', tone: 'indigo' },
  { label: 'Fulfillment rate', value: '96.8%', meta: '+1.4 pts this week', tone: 'green' },
];

export const pipeline = [
  { id: 'orders', label: 'Orders', value: 186, detail: 'Orders imported from the storefront and ready for operational review.' },
  { id: 'allocated', label: 'Allocated', value: 158, detail: 'Stock is reserved locally. Available quantities reflect every allocation.' },
  { id: 'ready', label: 'Ready to pick', value: 42, detail: 'Orders with complete allocations can move directly to the warehouse floor.' },
  { id: 'picking', label: 'Picking', value: 11, detail: 'Active pick sessions show line-by-line progress and scan verification.' },
  { id: 'completed', label: 'Completed', value: 64, detail: 'Completed today with fulfillment history and stock movement records.' },
];

export const attentionItems = [
  { id: 'low-stock', label: '18 low-stock products', meta: '5 below safety stock', tone: 'warning', rows: ['AeroCharge Dock · 4 available', 'Field Notes Pack · 8 available', 'Transit Cable Kit · 0 available'] },
  { id: 'barcodes', label: '6 products missing barcodes', meta: 'Catalog data quality', tone: 'neutral', rows: ['Modular Divider Set', 'Studio Utility Apron', 'Thermal Label Roll'] },
  { id: 'sync', label: '3 sync exceptions', meta: 'Two duplicates, one missing SKU', tone: 'danger', rows: ['Duplicate: PAC-104', 'Duplicate: CAB-208', 'Missing SKU: Commerce #8814'] },
  { id: 'receiving', label: '4 receiving discrepancies', meta: 'Pending operator review', tone: 'info', rows: ['Receipt RC-2048 · −2 units', 'Receipt RC-2044 · +4 units', 'Receipt RC-2041 · damaged line'] },
];

export const locations = [
  { id: 'all', name: 'All warehouses' },
  { id: 'atlas', name: 'Atlas Warehouse' },
  { id: 'meridian', name: 'Meridian Warehouse' },
  { id: 'summit', name: 'Summit Warehouse' },
];

export const inventory = [
  {
    id: 'aero-dock', product: 'AeroCharge Dock', category: 'Electronics', sku: 'ACD-440', barcode: '847100043210',
    location: 'Atlas · A-03', warehouse: 'atlas', onHand: 28, allocated: 24, available: 4, status: 'Low stock', cost: 42.5,
    valuation: 1190, description: 'Four-port aluminum charging dock for shared workspaces.',
    byLocation: [{ name: 'Atlas · A-03', units: 28 }, { name: 'Meridian · C-08', units: 34 }, { name: 'Summit · B-02', units: 16 }],
    movements: ['−4 pick · Order #10428', '+24 receipt · RC-2048', '−2 adjustment · Count CC-188'],
  },
  {
    id: 'field-notes', product: 'Field Notes Pack', category: 'Office', sku: 'FNP-118', barcode: '847100011842',
    location: 'Meridian · C-12', warehouse: 'meridian', onHand: 19, allocated: 11, available: 8, status: 'Low stock', cost: 6.8,
    valuation: 129.2, description: 'Recycled paper project notebook set, pack of three.',
    byLocation: [{ name: 'Atlas · D-09', units: 44 }, { name: 'Meridian · C-12', units: 19 }, { name: 'Summit · A-07', units: 31 }],
    movements: ['−6 fulfillment · Order #10422', '+60 receipt · RC-2039', '−1 damage adjustment'],
  },
  {
    id: 'transit-cable', product: 'Transit Cable Kit', category: 'Electronics', sku: 'TCK-208', barcode: '847100020844',
    location: 'Summit · B-16', warehouse: 'summit', onHand: 8, allocated: 8, available: 0, status: 'Out of stock', cost: 18.25,
    valuation: 146, description: 'Compact multi-connector travel cable system.',
    byLocation: [{ name: 'Atlas · A-11', units: 0 }, { name: 'Meridian · B-06', units: 12 }, { name: 'Summit · B-16', units: 8 }],
    movements: ['−8 allocation · Order #10425', '−12 fulfillment · Order #10404', '+20 transfer · Meridian'],
  },
  {
    id: 'utility-apron', product: 'Studio Utility Apron', category: 'Apparel', sku: 'SUA-602', barcode: '847100060260',
    location: 'Atlas · E-04', warehouse: 'atlas', onHand: 142, allocated: 18, available: 124, status: 'Healthy', cost: 24.4,
    valuation: 3464.8, description: 'Adjustable utility apron with reinforced tool pockets.',
    byLocation: [{ name: 'Atlas · E-04', units: 142 }, { name: 'Meridian · A-02', units: 61 }, { name: 'Summit · C-11', units: 48 }],
    movements: ['+80 receipt · RC-2047', '−3 fulfillment · Order #10413', '−1 sample adjustment'],
  },
  {
    id: 'label-roll', product: 'Thermal Label Roll', category: 'Packaging', sku: 'TLR-910', barcode: '847100091097',
    location: 'Meridian · P-02', warehouse: 'meridian', onHand: 580, allocated: 72, available: 508, status: 'Healthy', cost: 3.15,
    valuation: 1827, description: 'High-adhesion 4 × 6 thermal shipping labels.',
    byLocation: [{ name: 'Atlas · P-01', units: 410 }, { name: 'Meridian · P-02', units: 580 }, { name: 'Summit · P-01', units: 290 }],
    movements: ['−48 transfer · Atlas', '+360 receipt · RC-2040', '−12 warehouse use'],
  },
  {
    id: 'divider-set', product: 'Modular Divider Set', category: 'Equipment', sku: 'MDS-324', barcode: '847100032429',
    location: 'Summit · D-05', warehouse: 'summit', onHand: 96, allocated: 10, available: 86, status: 'Healthy', cost: 31.5,
    valuation: 3024, description: 'Configurable drawer divider system for small-parts storage.',
    byLocation: [{ name: 'Atlas · F-06', units: 54 }, { name: 'Meridian · D-12', units: 72 }, { name: 'Summit · D-05', units: 96 }],
    movements: ['+30 transfer · Meridian', '−4 fulfillment · Order #10401', '+72 receipt · RC-2035'],
  },
];

export const orders = [
  {
    id: '10428', customer: 'Lumen Works', items: 4, allocation: 'Allocated', pick: 'Picking', status: 'Picking', total: 428.6, age: '38 min',
    progress: 50, lines: [{ product: 'AeroCharge Dock', sku: 'ACD-440', quantity: 2, allocated: 2 }, { product: 'Thermal Label Roll', sku: 'TLR-910', quantity: 8, allocated: 8 }, { product: 'Field Notes Pack', sku: 'FNP-118', quantity: 3, allocated: 3 }],
    timeline: ['Order synced · 9:04 AM', 'Allocated · 9:08 AM', 'Pick started · 9:31 AM'],
  },
  {
    id: '10427', customer: 'Keystone Studio', items: 3, allocation: 'Required', pick: 'Waiting', status: 'Allocation required', total: 214.4, age: '52 min',
    progress: 10, lines: [{ product: 'Transit Cable Kit', sku: 'TCK-208', quantity: 10, allocated: 8 }, { product: 'Studio Utility Apron', sku: 'SUA-602', quantity: 2, allocated: 2 }],
    timeline: ['Order synced · 8:50 AM', 'Allocation exception · 8:51 AM'],
  },
  {
    id: '10425', customer: 'Northline Office', items: 6, allocation: 'Allocated', pick: 'Ready', status: 'Ready', total: 786.2, age: '1 hr',
    progress: 25, lines: [{ product: 'Modular Divider Set', sku: 'MDS-324', quantity: 4, allocated: 4 }, { product: 'AeroCharge Dock', sku: 'ACD-440', quantity: 6, allocated: 6 }],
    timeline: ['Order synced · 8:31 AM', 'Allocated · 8:34 AM', 'Ready for pick · 8:35 AM'],
  },
  {
    id: '10422', customer: 'Arc & Foundry', items: 2, allocation: 'Allocated', pick: 'Complete', status: 'Completed', total: 96.8, age: '2 hrs',
    progress: 100, lines: [{ product: 'Field Notes Pack', sku: 'FNP-118', quantity: 6, allocated: 6 }, { product: 'Thermal Label Roll', sku: 'TLR-910', quantity: 4, allocated: 4 }],
    timeline: ['Order synced · 7:46 AM', 'Pick completed · 8:22 AM', 'Fulfilled · 8:27 AM'],
  },
];

export const pickItems = [
  { id: 'label', product: 'Thermal Label Roll', sku: 'TLR-910', barcode: '847100091097', location: 'P-01', quantity: 8 },
  { id: 'dock', product: 'AeroCharge Dock', sku: 'ACD-440', barcode: '847100043210', location: 'A-03', quantity: 2 },
  { id: 'notes', product: 'Field Notes Pack', sku: 'FNP-118', barcode: '847100011842', location: 'D-09', quantity: 3 },
  { id: 'apron', product: 'Studio Utility Apron', sku: 'SUA-602', barcode: '847100060260', location: 'E-04', quantity: 1 },
];

export const receipt = {
  id: 'RC-2048', supplier: 'Brightline Distribution', warehouse: 'Atlas Warehouse', skuCount: 24, units: 560,
  lines: [
    { product: 'AeroCharge Dock', sku: 'ACD-440', expected: 120, received: 120 },
    { product: 'Thermal Label Roll', sku: 'TLR-910', expected: 360, received: 360 },
    { product: 'Field Notes Pack', sku: 'FNP-118', expected: 80, received: 78 },
  ],
};

export const warehouses = [
  {
    id: 'atlas', name: 'Atlas Warehouse', subtitle: 'Primary fulfillment hub', skus: 1864, units: 18420, value: '$486,200', capacity: 74,
    zones: [{ name: 'A-01', skus: 214, units: 2420, value: '$74,600', capacity: 68 }, { name: 'A-02', skus: 186, units: 3180, value: '$81,440', capacity: 81 }, { name: 'A-03', skus: 228, units: 2760, value: '$96,810', capacity: 77 }],
  },
  {
    id: 'meridian', name: 'Meridian Warehouse', subtitle: 'Regional replenishment', skus: 1210, units: 11980, value: '$238,910', capacity: 62,
    zones: [{ name: 'B-01', skus: 141, units: 1840, value: '$44,880', capacity: 59 }, { name: 'B-02', skus: 177, units: 2120, value: '$57,420', capacity: 66 }],
  },
  {
    id: 'summit', name: 'Summit Warehouse', subtitle: 'Overflow and returns', skus: 842, units: 6540, value: '$117,320', capacity: 48,
    zones: [{ name: 'C-01', skus: 96, units: 1120, value: '$23,480', capacity: 44 }, { name: 'C-02', skus: 118, units: 980, value: '$21,760', capacity: 51 }],
  },
];

export const reports = {
  valuation: { label: 'Inventory valuation', metrics: [['Total value', '$842,430'], ['Units', '36,940'], ['Avg. unit cost', '$22.81']], rows: [['Atlas', '$486,200', '57.7%'], ['Meridian', '$238,910', '28.4%'], ['Summit', '$117,320', '13.9%']], chart: [42, 47, 45, 52, 58, 61, 67] },
  lowStock: { label: 'Low stock', metrics: [['Products', '18'], ['Below safety', '5'], ['Reorder value', '$18,240']], rows: [['AeroCharge Dock', '4', '48'], ['Field Notes Pack', '8', '80'], ['Transit Cable Kit', '0', '60']], chart: [68, 59, 48, 42, 31, 24, 18] },
  movements: { label: 'Stock movement', metrics: [['Movement rows', '2,148'], ['Units in', '3,420'], ['Units out', '2,860']], rows: [['Receiving', '+3,420', '56.7%'], ['Fulfillment', '−2,420', '40.1%'], ['Adjustments', '−192', '3.2%']], chart: [38, 57, 44, 72, 61, 82, 74] },
  skuOrders: { label: 'SKU orders', metrics: [['SKUs ordered', '684'], ['Order lines', '1,426'], ['Units', '3,112']], rows: [['TLR-910', '128', '486'], ['ACD-440', '96', '214'], ['FNP-118', '72', '196']], chart: [31, 45, 38, 64, 57, 76, 69] },
  receiving: { label: 'Receiving', metrics: [['Receipts', '42'], ['Units', '6,840'], ['Value', '$118,460']], rows: [['Brightline Distribution', '18', '2,940'], ['Apex Supply Co.', '14', '2,180'], ['Vector Materials', '10', '1,720']], chart: [35, 41, 52, 48, 66, 72, 81] },
  fulfillment: { label: 'Fulfillment', metrics: [['Orders', '604'], ['Units', '4,188'], ['Accuracy', '98.4%']], rows: [['Atlas', '382', '98.9%'], ['Meridian', '148', '97.8%'], ['Summit', '74', '97.2%']], chart: [48, 52, 57, 60, 68, 71, 78] },
};

export const insightRanges = {
  '7D': { revenue: '$184k', orders: '604', units: '4,188', sellThrough: '68%', daysSupply: '41', chart: [32, 45, 39, 58, 52, 71, 66] },
  '30D': { revenue: '$742k', orders: '2,486', units: '17,904', sellThrough: '72%', daysSupply: '38', chart: [24, 31, 38, 36, 47, 54, 62] },
  '90D': { revenue: '$2.18m', orders: '7,204', units: '52,180', sellThrough: '75%', daysSupply: '36', chart: [18, 26, 31, 42, 49, 57, 69] },
  '12M': { revenue: '$8.64m', orders: '28,640', units: '208k', sellThrough: '78%', daysSupply: '34', chart: [22, 28, 35, 44, 51, 63, 77] },
};

export const insightCards = [
  { title: 'Highest velocity', value: 'Thermal Label Roll', meta: '486 units · 7D', tone: 'aqua' },
  { title: 'Stock risk', value: 'Transit Cable Kit', meta: '0 available · 18 allocated', tone: 'danger' },
  { title: 'Reorder candidates', value: '12 products', meta: '$14,280 suggested value', tone: 'violet' },
];

export const initialRoute = [
  { id: 'downtown', name: 'Downtown', orders: 8, eta: '10:20' },
  { id: 'west-end', name: 'West End', orders: 6, eta: '10:48' },
  { id: 'north-industrial', name: 'North Industrial', orders: 11, eta: '11:26' },
  { id: 'south-business', name: 'South Business District', orders: 7, eta: '12:04' },
];

export const integrationCapabilities = ['Product sync', 'Variation sync', 'Order sync', 'Inventory synchronization', 'Controlled writeback'];

export const systemHealth = [
  { label: 'Commerce sync', value: 'Healthy', meta: 'Catalog checked 4 min ago' },
  { label: 'Orders sync', value: 'Current', meta: 'Last fetch 2 min ago' },
  { label: 'Inventory', value: 'Healthy', meta: 'No failed movements' },
  { label: 'Writeback safety', value: 'Protected', meta: 'Approval required' },
  { label: 'API', value: 'Operational', meta: '99.99% sample status' },
];

export const showcaseModules = [
  { id: 'command', label: 'Command center' },
  { id: 'inventory', label: 'Inventory' },
  { id: 'orders', label: 'Orders' },
  { id: 'picking', label: 'Picking' },
  { id: 'receiving', label: 'Receiving' },
  { id: 'warehouse', label: 'Warehouse' },
  { id: 'reports', label: 'Reports' },
  { id: 'insights', label: 'Insights' },
  { id: 'routes', label: 'Routes' },
  { id: 'integrations', label: 'Integrations' },
];
