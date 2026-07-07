import { useEffect, useState } from 'react';
import {
  BarChart3,
  Bell,
  Boxes,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  ClipboardCheck,
  ClipboardList,
  Download,
  Edit3,
  Filter,
  LayoutDashboard,
  Link2,
  MapPin,
  Menu,
  MoreVertical,
  PackageSearch,
  Plus,
  RefreshCw,
  Route,
  Search,
  Settings,
  ShoppingCart,
  SlidersHorizontal,
  Truck,
  Upload,
  UserCircle,
  Warehouse,
} from 'lucide-react';

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
  { id: 'settings', label: 'Admin / Settings', icon: Settings },
];

const pageMeta = {
  dashboard: {
    title: 'Dashboard',
    kicker: 'Operational snapshot',
    tabs: ['Today', 'Work Queues', 'Exceptions'],
  },
  items: {
    title: 'Items',
    kicker: 'Item master',
    tabs: ['Main', 'Nutrition', 'Categories', 'Customizations'],
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

const tableRows = [
  ['000437', 'Utility Classic Collar Black, Small', 'Dog Harness, Lead & Collar', 'Each', '4.75', '9.49', 'Main Warehouse', 'Aisle 01', '24'],
  ['001001', 'Outback Grill Canned Cat Food - 3oz', 'Cats', 'Each', '0.00', '2.35', 'Main Warehouse', 'Receiving', '7'],
  ['001009', "World's Best Multiple Cat Scented Clumping Litter - 7Lb", 'Cat Litter', 'Each', '14.00', '18.99', 'Main Warehouse', 'Aisle 04', '13'],
  ['100408', 'Nutram Cat OC Cognitive+ Kitten Tubes', 'Cat Food', 'Each', '0.00', '12.99', 'Main Warehouse', 'Aisle 02', '14'],
  ['100411', 'Nutram Cat OC Immunity+ Tubes', 'Cat Food', 'Each', '0.00', '12.99', 'Main Warehouse', 'Aisle 02', '16'],
];

const genericRows = [
  ['Work queue', 'Awaiting setup', 'Planning', 'Main Warehouse'],
  ['Exceptions', 'Needs review', 'Operations', 'Main Warehouse'],
  ['Exports', 'Ready later', 'Reporting', 'Main Warehouse'],
];

function getInitialPage() {
  const fromHash = window.location.hash.replace('#', '');
  return navItems.some((item) => item.id === fromHash) ? fromHash : 'dashboard';
}

export default function App() {
  const [activePage, setActivePage] = useState(getInitialPage);

  useEffect(() => {
    const handleHashChange = () => setActivePage(getInitialPage());
    window.addEventListener('hashchange', handleHashChange);
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  const activeMeta = pageMeta[activePage];

  return (
    <div className="app-shell">
      <Sidebar activePage={activePage} onNavigate={setActivePage} />
      <div className="workspace">
        <TopHeader />
        <main className="main-content">
          <PageHeader meta={activeMeta} />
          <PageBody pageId={activePage} />
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
            <a
              className={`nav-link ${isActive ? 'active' : ''}`}
              href={`#${item.id}`}
              key={item.id}
              onClick={() => onNavigate(item.id)}
            >
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

function PageHeader({ meta }) {
  return (
    <section className="page-heading">
      <div>
        <p>{meta.kicker}</p>
        <h1>{meta.title}</h1>
      </div>
      <div className="page-tabs" role="tablist" aria-label={`${meta.title} sections`}>
        {meta.tabs.map((tab, index) => (
          <button className={index === 0 ? 'tab active' : 'tab'} key={tab} type="button">
            {tab}
          </button>
        ))}
      </div>
    </section>
  );
}

function PageBody({ pageId }) {
  if (pageId === 'items') {
    return <ItemsPage />;
  }

  if (pageId === 'inventory') {
    return (
      <StandardPage
        icon={Boxes}
        title="Inventory list placeholder"
        description="Stock-by-location table layout for Main Warehouse."
        columns={['SKU', 'Category', 'Description', 'UOM', 'In Stock', 'Allocated', 'Sellable', 'Location']}
      />
    );
  }

  if (pageId === 'receiving') {
    return <ReceivingPlaceholder />;
  }

  if (pageId === 'dashboard') {
    return <DashboardPlaceholder />;
  }

  return (
    <StandardPage
      icon={pageIcon(pageId)}
      title={`${pageMeta[pageId].title} placeholder`}
      description="Admin layout with filters, actions, and table structure."
      columns={['Area', 'Status', 'Type', 'Notes']}
    />
  );
}

function ItemsPage() {
  return (
    <section className="content-panel">
      <div className="toolbar">
        <div className="filter-grid">
          <label className="field">
            <span>Search</span>
            <div className="input-with-icon">
              <input placeholder="SKU, barcode, or description" type="search" />
              <Search size={18} />
            </div>
          </label>
          <label className="field">
            <span>Category</span>
            <div className="select-shell">
              <select defaultValue="all">
                <option value="all">All Categories</option>
              </select>
              <Filter size={18} />
            </div>
          </label>
          <div className="field status-field">
            <span>Show</span>
            <div className="radio-row">
              <label>
                <input defaultChecked name="item-status" type="radio" />
                Active
              </label>
              <label>
                <input name="item-status" type="radio" />
                Inactive
              </label>
            </div>
          </div>
          <label className="check-field">
            <input defaultChecked type="checkbox" />
            Include Non Inventory
          </label>
        </div>
        <div className="button-row">
          <button className="primary-button" type="button">
            <Search size={17} />
            Search
          </button>
          <button className="muted-button" type="button">
            Reset
          </button>
          <button className="muted-button" type="button">
            Clear
          </button>
          <button className="action-button" type="button">
            <RefreshCw size={17} />
            Refresh
          </button>
          <button className="action-button" type="button">
            <Link2 size={17} />
            Remap
          </button>
          <button className="action-button" type="button">
            <Upload size={17} />
            Import
          </button>
          <button className="action-button" type="button">
            <Download size={17} />
            Export
          </button>
        </div>
      </div>
      <TableShell
        caption="Showing placeholder records 1-5"
        columns={[
          'Image',
          'SKU',
          'Description',
          'Category',
          'UOM',
          'Unit Cost',
          'Sales Price',
          'Warehouse',
          'Inventory Location',
          'In Stock',
          'Active',
          'Actions',
        ]}
      >
        {tableRows.map((row) => (
          <tr key={row[0]}>
            <td>
              <div className="image-cell">Add Image</div>
            </td>
            <td className="mono">{row[0]}</td>
            <td>{row[1]}</td>
            <td>{row[2]}</td>
            <td>{row[3]}</td>
            <td>{row[4]}</td>
            <td>{row[5]}</td>
            <td>{row[6]}</td>
            <td>{row[7]}</td>
            <td>{row[8]}</td>
            <td>
              <span className="status-pill">Active</span>
            </td>
            <td>
              <button className="round-action" aria-label={`Edit ${row[0]}`} type="button">
                <Edit3 size={17} />
              </button>
            </td>
          </tr>
        ))}
      </TableShell>
    </section>
  );
}

function DashboardPlaceholder() {
  const cards = [
    ['Items', 'Placeholder', PackageSearch],
    ['Inventory', 'Placeholder', Boxes],
    ['Open Orders', 'Placeholder', ShoppingCart],
    ['Cycle Counts', 'Placeholder', ClipboardCheck],
  ];

  return (
    <section className="dashboard-grid">
      {cards.map(([label, value, Icon]) => (
        <article className="summary-card" key={label}>
          <div className="summary-icon">
            <Icon size={24} />
          </div>
          <div>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        </article>
      ))}
      <div className="content-panel wide-panel">
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
        <button className="add-button" aria-label="Add placeholder receiving row" type="button">
          <Plus size={22} />
        </button>
        <label className="toggle-label">
          <span>Enable One to One Scanning</span>
          <input type="checkbox" />
        </label>
      </div>
      <TableShell
        caption="Direct receiving placeholder"
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
  const rows = columns.length === 4 ? genericRows : tableRows.map((row) => [row[0], row[2], row[1], row[3], row[8], '0', row[8], row[7]]);

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
      <TableShell caption="Placeholder records" columns={columns}>
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
          <span>1 / 1</span>
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
