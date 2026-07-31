(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}" /></svg>`;

  const screenConfig = {
    command: {
      module: "command",
      eyebrow: "Workspace",
      title: "Command",
      links: [
        ["command", "Command Center", "home", ""],
        ["command", "Priority queue", "warning", "5"],
        ["command", "Activity", "clock", ""]
      ]
    },
    orders: {
      module: "orders",
      eyebrow: "Commerce",
      title: "Orders",
      links: [
        ["orders", "Open orders", "orders", "8"],
        ["orders", "Allocation", "layers", "3", "allocation"],
        ["pick", "Picking", "scan", "4"],
        ["orders", "Completed", "check", "", "completed"],
        ["orders", "History", "clock", "", "history"]
      ]
    },
    pick: {
      module: "orders",
      eyebrow: "Commerce",
      title: "Picking",
      links: [
        ["orders", "Open orders", "orders", "8"],
        ["orders", "Allocation", "layers", "3", "allocation"],
        ["pick", "Picking", "scan", "4"],
        ["orders", "Completed", "check", "", "completed"],
        ["orders", "History", "clock", "", "history"]
      ]
    },
    inventory: {
      module: "inventory",
      eyebrow: "Warehouse",
      title: "Inventory",
      links: [
        ["inventory", "All inventory", "box", "246"],
        ["location", "By location", "map", ""],
        ["inventory", "Low stock", "warning", "5", "low"],
        ["inventory", "Expiring", "clock", "", "expiring"],
        ["inventory", "Par levels", "layers", "", "par"],
        ["inventory", "Movements", "refresh", "", "movements"]
      ]
    },
    location: {
      module: "inventory",
      eyebrow: "Warehouse",
      title: "Inventory",
      links: [
        ["inventory", "All inventory", "box", "246"],
        ["location", "By location", "map", ""],
        ["inventory", "Low stock", "warning", "5", "low"],
        ["inventory", "Par levels", "layers", "", "par"],
        ["inventory", "Movements", "refresh", "", "movements"]
      ]
    },
    receiving: {
      module: "operations",
      eyebrow: "Warehouse",
      title: "Operations",
      links: [
        ["receiving", "Receiving", "truck", "2"],
        ["pick", "Scan console", "scan", ""],
        ["inventory", "Cycle count", "refresh", "", "cycle"],
        ["location", "Locations", "map", ""]
      ]
    },
    insights: {
      module: "intelligence",
      eyebrow: "Intelligence",
      title: "Insights",
      links: [
        ["insights", "Overview", "chart", ""],
        ["insights", "Reports", "grid", "12", "reports"],
        ["insights", "Exports", "download", "", "exports"]
      ]
    },
    integrations: {
      module: "system",
      eyebrow: "System",
      title: "Integrations",
      links: [
        ["integrations", "WooCommerce", "plug", "1"],
        ["integrations", "Sync runs", "refresh", "", "runs"],
        ["integrations", "Mapping queue", "layers", "7", "mapping"],
        ["settings", "Settings", "settings", ""]
      ]
    },
    settings: {
      module: "system",
      eyebrow: "System",
      title: "Settings",
      links: [
        ["integrations", "WooCommerce", "plug", "1"],
        ["settings", "Company", "settings", ""],
        ["settings", "Users", "user", ""],
        ["settings", "Warehouses", "box", ""],
        ["settings", "System", "layers", ""]
      ]
    },
    components: {
      module: "library",
      eyebrow: "Reference",
      title: "UI library",
      links: [
        ["components", "Foundations", "grid", ""],
        ["components", "Components", "layers", ""],
        ["components", "States", "info", ""]
      ]
    }
  };

  const orders = [
    ["1058", "Sample Customer 01", "Today · 14:30", "Ready", "success", "6", "$184.20", "Local delivery"],
    ["1057", "Sample Customer 02", "Today · 15:00", "Needs allocation", "warning", "4", "$96.45", "Pickup"],
    ["1056", "Sample Customer 03", "Tomorrow", "Allocated", "info", "9", "$241.80", "Local delivery"],
    ["1055", "Sample Customer 04", "Tomorrow", "Exception", "danger", "3", "$78.99", "Shipping"],
    ["1054", "Sample Customer 05", "Jul 20", "Ready", "success", "7", "$162.30", "Pickup"],
    ["1053", "Sample Customer 06", "Jul 21", "Unallocated", "neutral", "2", "$44.00", "Shipping"]
  ];

  const inventory = [
    ["DOG-FOOD-12", "North Range Adult Dog Food · 12 kg", "48", "12", "A-01-02", "Healthy", "success"],
    ["CAT-LIT-CL20", "Cloud Cat Litter · 20 lb", "9", "12", "A-02-01", "Below par", "warning"],
    ["TRT-SALM-150", "Salmon Training Treats · 150 g", "0", "8", "B-01-04", "Out of stock", "danger"],
    ["DOG-TOY-RNG", "Rubber Enrichment Ring", "61", "10", "B-03-02", "Healthy", "success"],
    ["CAT-CAN-CH85", "Chicken Cat Food · 85 g", "144", "36", "C-01-01", "Healthy", "success"],
    ["BED-ORTH-M", "Orthopedic Pet Bed · Medium", "5", "5", "BULK-02", "At par", "info"]
  ];

  const state = {
    screen: location.hash.slice(1) in screenConfig ? location.hash.slice(1) : "command",
    view: "",
    preview: "populated",
    selectedOrders: new Set(),
    pickQty: 3,
    pickOrder: "1058",
    insight: "Revenue",
    lastFocus: null
  };

  const pageHeading = ({ module, title, description, actions = "" }) => `
    <div class="page-heading">
      <div>
        <div class="breadcrumbs"><span>${module}</span><span>${title}</span></div>
        <h1>${title}</h1>
        <p>${description}</p>
      </div>
      ${actions ? `<div class="heading-actions">${actions}</div>` : ""}
    </div>`;

  const button = (label, kind = "secondary", iconName = "", attrs = "") =>
    `<button class="button button-${kind}" ${attrs}>${iconName ? icon(iconName) : ""}${label}</button>`;

  const metric = (label, value, foot, tone = "", delta = "") => `
    <article class="card metric-card ${tone}">
      <div class="metric-label"><span>${label}</span>${tone === "live" ? '<span class="status live">Live</span>' : ""}</div>
      <strong class="metric-value">${value}</strong>
      <div class="metric-foot">${delta ? `<span class="delta ${delta.startsWith("−") ? "down" : ""}">${delta}</span>` : ""}<span>${foot}</span></div>
    </article>`;

  const lineChart = () => `
    <div class="chart-wrap">
      <div class="chart-axis"><span>$8k</span><span>$6k</span><span>$4k</span><span>$2k</span><span>$0</span></div>
      <div class="line-chart" role="img" aria-label="Seven-day sales trend rises from 3.1 to 6.8 thousand dollars, above the prior period on five days.">
        <svg viewBox="0 0 700 190" preserveAspectRatio="none">
          <defs><linearGradient id="area-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#3038cf" stop-opacity=".20"/><stop offset="1" stop-color="#3038cf" stop-opacity="0"/></linearGradient></defs>
          <path class="area" d="M0 142 L110 127 L220 135 L330 89 L440 101 L550 58 L700 36 L700 190 L0 190Z" />
          <path class="line" d="M0 142 L110 127 L220 135 L330 89 L440 101 L550 58 L700 36" />
          <path class="compare" d="M0 151 L110 139 L220 113 L330 121 L440 92 L550 104 L700 76" />
        </svg>
      </div>
    </div>
    <div class="chart-x"><span>Fri</span><span>Sat</span><span>Sun</span><span>Mon</span><span>Tue</span><span>Wed</span><span>Thu</span></div>`;

  const commandScreen = () => `
    <section class="page" data-page="command">
      ${pageHeading({
        module: "Command",
        title: "Good morning, Operations",
        description: "Business pulse, warehouse risk and the next best action—one operational front door.",
        actions: `${button("Receive stock", "secondary", "truck", 'data-screen="receiving"')}${button("Open orders", "primary", "orders", 'data-screen="orders"')}`
      })}
      <div class="signal-strip">${icon("info")}<div><strong>Read-only commerce sync is healthy.</strong> <span>7 product mappings need review before the next refresh.</span></div><button data-screen="integrations">Review queue ${icon("arrow")}</button></div>
      <div class="grid grid-4">
        ${metric("Revenue today", "$6,842", "vs. 30-day daily average", "", "+12.4%")}
        ${metric("Open orders", "18", "8 are ready for picking", "live", "+3")}
        ${metric("Units available", "4,286", "across 246 sellable items", "success", "+84")}
        ${metric("Inventory risk", "5", "3 below par · 2 out", "warning", "−2")}
      </div>
      <div class="grid grid-2">
        <article class="card priority-card">
          <div class="card-header"><div><h2>Priority queue</h2><p>Ranked by operational impact</p></div><span class="status live">5 actions</span></div>
          <div class="priority-list">
            <div class="priority-row"><span class="priority-icon">${icon("warning")}</span><div><strong>3 orders blocked by stock</strong><span>Resolve allocation before the 14:30 wave</span></div>${button("Resolve", "quiet", "", 'data-screen="orders" data-view="allocation"')}</div>
            <div class="priority-row"><span class="priority-icon info">${icon("layers")}</span><div><strong>7 product mappings need review</strong><span>Local fields remain protected</span></div>${button("Map", "quiet", "", 'data-screen="integrations"')}</div>
            <div class="priority-row"><span class="priority-icon success">${icon("truck")}</span><div><strong>Receiving session ready</strong><span>24 expected units · Main warehouse</span></div>${button("Continue", "quiet", "", 'data-screen="receiving"')}</div>
          </div>
        </article>
        <article class="card chart-card">
          <div class="card-header"><div><h2>Sales velocity</h2><p>Fictional preview data · last 7 days</p></div><div class="chart-legend"><span><i class="legend-dot"></i>Current</span><span><i class="legend-dot compare"></i>Prior</span></div></div>
          ${lineChart()}
        </article>
      </div>
      <div class="grid grid-3">
        <article class="card"><div class="card-header"><h2>Order pipeline</h2><span>18 open</span></div><div class="card-body"><div class="bar-list"><div class="bar-row"><span>Unallocated</span><div class="bar-track"><i style="width:28%"></i></div><strong>5</strong></div><div class="bar-row"><span>Allocated</span><div class="bar-track"><i style="width:39%"></i></div><strong>7</strong></div><div class="bar-row"><span>Ready to pick</span><div class="bar-track"><i style="width:33%"></i></div><strong>6</strong></div></div></div></article>
        <article class="card"><div class="card-header"><h2>Stock posture</h2><span>246 items</span></div><div class="card-body"><div class="bar-list"><div class="bar-row"><span>Healthy</span><div class="bar-track"><i style="width:82%"></i></div><strong>201</strong></div><div class="bar-row"><span>At risk</span><div class="bar-track"><i style="width:16%"></i></div><strong>40</strong></div><div class="bar-row"><span>Out</span><div class="bar-track"><i style="width:2%"></i></div><strong>5</strong></div></div></div></article>
        <article class="card"><div class="card-header"><h2>Recent movement</h2><span>10 min</span></div><div class="card-body"><div class="timeline"><div class="timeline-row"><time>10:42</time><strong>+24 received</strong><span>Session RCV-0241</span></div><div class="timeline-row"><time>10:37</time><strong>−6 allocated</strong><span>Order #1058</span></div><div class="timeline-row"><time>10:31</time><strong>+2 adjusted</strong><span>Count CC-0088</span></div></div></div></article>
      </div>
    </section>`;

  const orderRows = () => orders.map(([id, customer, due, status, tone, lines, total, method]) => `
    <tr class="${state.selectedOrders.has(id) ? "is-selected" : ""}">
      <td data-label="Select"><input type="checkbox" data-order-select="${id}" aria-label="Select order ${id}" ${state.selectedOrders.has(id) ? "checked" : ""}></td>
      <td data-label="Order" data-priority="high"><button class="button button-quiet mono" data-order="${id}">#${id}</button></td>
      <td data-label="Customer" class="wide-cell"><span class="cell-main">${customer}</span><span class="cell-sub">${method}</span></td>
      <td data-label="Due"><span class="cell-main">${due}</span></td>
      <td data-label="Status"><span class="status ${tone}">${status}</span></td>
      <td data-label="Lines" class="num">${lines}</td>
      <td data-label="Total" class="num"><strong>${total}</strong></td>
      <td data-label="Actions"><button class="icon-button" data-order="${id}" aria-label="Open order ${id}">${icon("more")}</button></td>
    </tr>`).join("");

  const ordersScreen = () => `
    <section class="page" data-page="orders">
      ${pageHeading({
        module: "Commerce / Orders",
        title: state.view === "allocation" ? "Allocation exceptions" : state.view === "completed" ? "Completed orders" : state.view === "history" ? "Order history" : "Open orders",
        description: state.view === "allocation" ? "Resolve stock conflicts before committing allocation." : "Prioritize, filter and move orders into the warehouse flow.",
        actions: `${button("Export", "secondary", "download", 'data-action="toast"')}${button("Refresh", "primary", "refresh", 'data-action="toast"')}`
      })}
      <div class="toolbar">
        <div class="filter-fields">
          <label class="field grow"><span>Search</span><span class="search-control">${icon("search")}<input class="control" type="search" placeholder="Order, customer or method" aria-label="Search orders"></span></label>
          <label class="field"><span>Fulfilment</span><select class="control"><option>All methods</option><option>Local delivery</option><option>Pickup</option><option>Shipping</option></select></label>
          <label class="field"><span>Due window</span><select class="control"><option>All dates</option><option>Today</option><option>Next 3 days</option></select></label>
        </div>
        ${button("Filters", "secondary", "filter", 'data-action="toggle-filters"')}
      </div>
      <div class="filter-chips"><span class="chip">Status: Open <button data-action="remove-chip" aria-label="Remove status filter">${icon("x")}</button></span><span class="chip">Warehouse: Main <button data-action="remove-chip" aria-label="Remove warehouse filter">${icon("x")}</button></span></div>
      <div class="table-card">
        <div class="table-top"><div><strong>8 orders</strong> <span>· Fictional preview records</span></div><div class="table-actions">${button("Columns", "secondary", "grid", 'data-action="toast"')}</div></div>
        <div class="table-scroll"><table class="data-table"><caption>Open orders</caption><thead><tr><th><input type="checkbox" data-action="select-all" aria-label="Select all orders"></th><th>Order</th><th>Customer</th><th>Due</th><th>Status</th><th class="num">Lines</th><th class="num">Total</th><th>Actions</th></tr></thead><tbody>${orderRows()}</tbody></table></div>
        <div class="pagination"><span>Showing 1–6 of 8</span><div class="pager"><button aria-label="Previous page" disabled>${icon("chevron")}</button><strong>1 / 2</strong><button aria-label="Next page">${icon("chevron")}</button></div></div>
      </div>
      <div class="bulk-dock" ${state.selectedOrders.size ? "" : "hidden"} aria-live="polite"><div><strong>${state.selectedOrders.size} selected</strong><span> · actions preserve an audit trail</span></div><div class="heading-actions">${button("Clear", "secondary", "", 'data-action="clear-selection"')}${button("Allocate", "primary", "layers", 'data-action="bulk-allocate"')}</div></div>
    </section>`;

  const pickScreen = () => `
    <section class="page" data-page="pick">
      ${pageHeading({
        module: "Commerce / Picking",
        title: "Pick station",
        description: "A floor-first workspace with the next location, expected item and scan result in one sight line.",
        actions: `${button("Pause wave", "secondary", "clock", 'data-action="toast"')}${button("Complete order", "primary", "check", 'data-action="complete-pick"')}`
      })}
      <div class="signal-strip">${icon("scan")}<div><strong>Wave PCK-041 is active.</strong> <span>4 orders · 29 units · sorted by shortest warehouse path.</span></div><button data-action="toast">Wave details ${icon("arrow")}</button></div>
      <div class="split-workspace">
        <article class="card">
          <div class="card-header"><div><h2>Pick queue</h2><p>Optimized by Main warehouse path</p></div><span class="status live">4 ready</span></div>
          <div class="queue-list">
            ${[["1058","6 lines","14:30"],["1054","7 lines","15:00"],["1052","4 lines","16:00"],["1049","12 lines","Tomorrow"]].map(([id,lines,due], index) => `<button class="queue-row ${state.pickOrder === id ? "is-active" : ""}" data-pick-order="${id}"><span class="queue-index">${index + 1}</span><span><strong>Order #${id}</strong><span>${lines} · ${index === 0 ? "Local delivery" : "Pickup"}</span></span><em>${due}</em></button>`).join("")}
          </div>
        </article>
        <div class="scan-stage">
          <div class="scan-head"><div><span>Next pick · A-01-02</span><h2>North Range Adult Dog Food</h2></div><span class="status info">3 of 8 lines</span></div>
          <div class="card-body" style="padding-top:0">
            <div class="grid grid-3">
              <div class="fact"><span>Order</span><strong class="mono">#${state.pickOrder}</strong></div>
              <div class="fact"><span>SKU</span><strong class="mono">DOG-FOOD-12</strong></div>
              <div class="fact"><span>Quantity</span><strong>${state.pickQty} / 6</strong></div>
            </div>
            <div style="margin:16px 0" role="progressbar" aria-valuemin="0" aria-valuemax="8" aria-valuenow="3" aria-label="Order picking progress, 3 of 8 lines"><div class="progress-track"><i style="width:37.5%"></i></div><div class="progress-meta"><span>3 of 8 lines verified</span><span>37%</span></div></div>
          </div>
          <div class="scan-input">${icon("scan")}<input id="pick-scan" autocomplete="off" placeholder="Scan SKU or barcode, then press Enter" aria-describedby="pick-scan-help"></div>
          <div class="scan-result" id="pick-scan-result" role="status"><strong>Scanner ready</strong><span id="pick-scan-help">Use DOG-FOOD-12 for success or DEMO-FAIL for failure.</span></div>
          <div class="card-body" style="padding-top:0"><div class="scan-actions">${button("−", "secondary", "", 'data-action="pick-decrease" aria-label="Decrease picked quantity"')}${button("+", "secondary", "", 'data-action="pick-increase" aria-label="Increase picked quantity"')}${button("Verify line", "primary", "check", 'data-action="verify-pick"')}</div></div>
        </div>
      </div>
    </section>`;

  const inventoryRows = () => inventory.map(([sku, name, available, par, locationName, status, tone], index) => {
    const allocated = [6, 3, 0, 4, 12, 2][index];
    const openOrders = [3, 2, 4, 1, 8, 1][index];
    const inStock = Number(available) + allocated;
    return `
    <tr class="${index === 0 ? "is-selected" : ""}">
      <td data-label="SKU" data-priority="high"><button class="button button-quiet mono" data-action="toast">${sku}</button></td>
      <td data-label="Barcode"><span class="mono">P2-${String(401000 + index * 137)}</span></td>
      <td data-label="Description" class="wide-cell"><span class="cell-main">${name}</span><span class="cell-sub">Sample Brand ${String.fromCharCode(65 + index)} · par ${par}</span></td>
      <td data-label="Location"><span class="mono">${locationName}</span></td>
      <td data-label="In stock" class="num">${inStock}</td>
      <td data-label="Open orders" class="num">${openOrders}</td>
      <td data-label="Allocated" class="num">${allocated}</td>
      <td data-label="Sellable" class="num"><strong>${available}</strong></td>
      <td data-label="Status"><span class="status ${tone}">${status}</span></td>
      <td data-label="Edit"><button class="icon-button" data-action="toast" aria-label="Edit ${sku}">${icon("edit")}</button></td>
    </tr>`;
  }).join("");

  const inventoryScreen = () => `
    <section class="page" data-page="inventory">
      ${pageHeading({
        module: "Warehouse / Inventory",
        title: state.view === "low" ? "Low-stock queue" : state.view === "par" ? "Par levels" : state.view === "movements" ? "Stock movement ledger" : "All inventory",
        description: "A sellable-unit view that keeps stock health, physical location and the immutable movement trail connected.",
        actions: `${button("Export", "secondary", "download", 'data-action="toast"')}${button("New item", "primary", "plus", 'data-action="toast"')}`
      })}
      <div class="grid grid-4">
        ${metric("Sellable items", "246", "100% mapped to a stock unit")}
        ${metric("Units available", "4,286", "Main warehouse", "success")}
        ${metric("Below par", "3", "needs replenishment", "warning")}
        ${metric("Out of stock", "2", "blocks 3 open orders", "live")}
      </div>
      <div class="toolbar">
        <div class="filter-fields">
          <label class="field grow"><span>Search SKU, barcode, name or brand</span><span class="search-control">${icon("search")}<input class="control" type="search" placeholder="Try DOG-FOOD-12 or Sample Brand A"></span></label>
          <label class="field"><span>Stock health</span><select class="control"><option>All health states</option><option>Healthy</option><option>Below par</option><option>Out of stock</option></select></label>
          <label class="field"><span>Location</span><select class="control"><option>All locations</option><option>Aisle A</option><option>Aisle B</option><option>Bulk</option></select></label>
        </div>
        ${button("Scan", "secondary", "scan", 'data-screen="pick"')}
      </div>
      <div class="table-card">
        <div class="table-top"><div><strong>246 inventory items</strong> <span>· 6 shown</span></div><div class="table-actions">${button("Density", "secondary", "grid", 'data-action="toast"')}</div></div>
        <div class="table-scroll"><table class="data-table"><caption>Inventory items</caption><thead><tr><th>SKU</th><th>Barcode</th><th>Description</th><th>Location</th><th class="num">In stock</th><th class="num">Open orders</th><th class="num">Allocated</th><th class="num">Sellable</th><th>Status</th><th>Edit</th></tr></thead><tbody>${inventoryRows()}</tbody></table></div>
        <div class="pagination"><span>Showing 1–6 of 246</span><div class="pager"><button aria-label="Previous page" disabled>${icon("chevron")}</button><strong>1 / 41</strong><button aria-label="Next page">${icon("chevron")}</button></div></div>
      </div>
    </section>`;

  const locationScreen = () => `
    <section class="page" data-page="location">
      ${pageHeading({
        module: "Warehouse / Inventory",
        title: "Inventory by location",
        description: "Navigate the physical hierarchy first, then inspect every item and movement held there.",
        actions: `${button("Print labels", "secondary", "download", 'data-action="toast"')}${button("Move stock", "primary", "arrow", 'data-action="open-move"')}`
      })}
      <div class="location-map">
        <aside class="card location-tree" aria-label="Location hierarchy">
          <div class="tree-group">Main warehouse</div>
          <button class="tree-link"><span>All locations</span><b>4,286</b></button>
          <button class="tree-link is-active"><span>Aisle A</span><b>1,842</b></button>
          <button class="tree-link"><span>Aisle B</span><b>986</b></button>
          <button class="tree-link"><span>Cold storage</span><b>612</b></button>
          <button class="tree-link"><span>Bulk</span><b>846</b></button>
        </aside>
        <div class="grid">
          <div class="grid grid-4">${metric("Aisle A units", "1,842", "43% of warehouse")}${metric("Inventory value", "$38.4k", "fictional landed value", "success")}${metric("Occupied bins", "18 / 24", "75% capacity", "warning")}${metric("Risk signals", "1", "one item below par", "live")}</div>
          <div class="toolbar"><div class="filter-fields"><label class="field grow"><span>Filter products in Aisle A</span><span class="search-control">${icon("search")}<input class="control" type="search" placeholder="SKU, product or brand"></span></label><label class="field"><span>Product group</span><select class="control"><option>All groups</option><option>Food</option><option>Treats</option><option>Accessories</option></select></label><label class="field"><span>Stock status</span><select class="control"><option>All states</option><option>Healthy</option><option>Below par</option></select></label></div></div>
          <div class="table-card"><div class="table-top"><div><strong>Aisle A</strong> <span>· sorted by bin</span></div><span class="status success">Counted Jul 15</span></div><div class="table-scroll"><table class="data-table"><caption>Stock in Aisle A</caption><thead><tr><th>Bin</th><th>SKU</th><th>Item</th><th class="num">On hand</th><th class="num">Allocated</th><th class="num">Available</th></tr></thead><tbody>${inventory.slice(0,4).map(([sku,name,available], index) => `<tr><td data-label="Bin"><strong class="mono">A-0${index + 1}-0${index + 2}</strong></td><td data-label="SKU"><span class="mono">${sku}</span></td><td data-label="Item" class="wide-cell">${name}</td><td data-label="On hand" class="num">${Number(available) + 6}</td><td data-label="Allocated" class="num">6</td><td data-label="Available" class="num"><strong>${available}</strong></td></tr>`).join("")}</tbody></table></div></div>
        </div>
      </div>
    </section>`;

  const receivingScreen = () => `
    <section class="page" data-page="receiving">
      ${pageHeading({
        module: "Warehouse / Operations",
        title: "Direct receiving",
        description: "Build a local receipt, preview every movement, then commit once. No purchase order required.",
        actions: `${button("Discard session", "secondary", "x", 'data-action="open-discard"')}${button("Preview receipt", "primary", "arrow", 'data-action="preview-receipt"')}`
      })}
      <div class="signal-strip">${icon("info")}<div><strong>Draft RCV-0241.</strong> <span>No stock changes until you preview and commit. Every committed line writes a movement row.</span></div><button data-action="toast">Safety rules ${icon("arrow")}</button></div>
      <div class="grid grid-3">
        <article class="card metric-card success"><div class="metric-label">1 · Add items <span class="status success">Complete</span></div><strong class="metric-value">3</strong><div class="metric-foot">unique sellable units</div></article>
        <article class="card metric-card live"><div class="metric-label">2 · Set quantities <span class="status live">Active</span></div><strong class="metric-value">24</strong><div class="metric-foot">total units expected</div></article>
        <article class="card metric-card"><div class="metric-label">3 · Review & commit <span class="status neutral">Pending</span></div><strong class="metric-value">—</strong><div class="metric-foot">movement preview required</div></article>
      </div>
      <div class="split-workspace">
        <div class="scan-stage">
          <div class="scan-head"><div><span>Add to draft</span><h2>Scan or enter an item</h2></div><span class="status live">Scanner ready</span></div>
          <div class="scan-input">${icon("scan")}<input id="receive-scan" autocomplete="off" placeholder="Scan SKU or barcode, then press Enter" aria-describedby="receive-scan-help"></div>
          <div class="scan-result" id="receive-scan-result" role="status"><strong>Waiting for input</strong><span id="receive-scan-help">Try CAT-LIT-CL20 in this fictional demo.</span></div>
        </div>
        <article class="card">
          <div class="card-header"><div><h2>Session details</h2><p>Required for the stock-movement audit row</p></div><span class="mono">RCV-0241</span></div>
          <div class="card-body"><div class="grid grid-2"><label class="field"><span>Destination</span><select class="control"><option>Main warehouse</option></select></label><label class="field"><span>Received at</span><input class="control" type="datetime-local" value="2026-07-17T10:30"></label><label class="field grow"><span>Reference</span><input class="control" value="Sample inbound delivery"></label><label class="field grow"><span>Internal note</span><input class="control" placeholder="Optional"></label></div></div>
        </article>
      </div>
      <div class="table-card"><div class="table-top"><div><strong>3 receipt lines</strong> <span>· 24 units</span></div>${button("Add manually", "secondary", "plus", 'data-action="toast"')}</div><div class="table-scroll"><table class="data-table"><caption>Draft receiving lines</caption><thead><tr><th>SKU</th><th>Item</th><th>Location</th><th class="num">Quantity</th><th>After receipt</th><th>Actions</th></tr></thead><tbody>${inventory.slice(0,3).map(([sku,name,available],index) => `<tr><td data-label="SKU"><span class="mono">${sku}</span></td><td data-label="Item" class="wide-cell">${name}</td><td data-label="Location"><select class="control"><option>${index === 2 ? "B-01-04" : `A-0${index + 1}-0${index + 2}`}</option></select></td><td data-label="Quantity" class="num"><input class="control num" type="number" value="${[8,10,6][index]}" min="1" style="width:80px"></td><td data-label="After receipt"><span class="status info">${Number(available)+[8,10,6][index]} available</span></td><td data-label="Actions"><button class="icon-button" aria-label="Remove ${sku}" data-action="toast">${icon("x")}</button></td></tr>`).join("")}</tbody></table></div></div>
    </section>`;

  const insightsScreen = () => {
    const tabs = ["Revenue", "Customers", "Products", "Subscriptions", "Payments", "Geography", "Forecasts"];
    return `
      <section class="page" data-page="insights">
        ${pageHeading({
          module: "Intelligence / Insights",
          title: "Commerce intelligence",
          description: "Decision-ready trends grouped by business question, with visible data scope and export behavior.",
          actions: `${button("Schedule", "secondary", "clock", 'data-action="toast"')}${button("Export view", "primary", "download", 'data-action="toast"')}`
        })}
        <div class="signal-strip">${icon("info")}<div><strong>Fictional analytics data.</strong> <span>Current view: Jul 1–17 · compared with the prior 17 days · sales timezone America/Edmonton.</span></div><button data-action="toast">Data notes ${icon("arrow")}</button></div>
        <div class="toolbar"><div class="filter-fields"><label class="field"><span>Date range</span><select class="control"><option>Jul 1–17, 2026</option><option>Last 30 days</option><option>Quarter to date</option></select></label><label class="field"><span>Compare with</span><select class="control"><option>Prior period</option><option>Prior year</option><option>No comparison</option></select></label><label class="field"><span>Channel</span><select class="control"><option>All channels</option><option>Online store</option><option>Subscriptions</option></select></label></div>${button("Apply", "primary", "filter", 'data-action="toast"')}</div>
        <div class="card"><div class="insight-tabs" role="tablist" aria-label="Insight categories">${tabs.map(tab => `<button class="insight-tab ${state.insight === tab ? "is-active" : ""}" role="tab" aria-selected="${state.insight === tab}" data-insight="${tab}">${tab}</button>`).join("")}</div></div>
        <div class="grid grid-4">
          ${metric("Net revenue", "$82,640", "Jul 1–17", "", "+8.7%")}
          ${metric("Average order", "$114.30", "across 723 orders", "success", "+2.1%")}
          ${metric("Refund rate", "1.8%", "13 refunded orders", "warning", "−0.4 pt")}
          ${metric("Forecast", "$151k", "month-end estimate", "live", "+5.6%")}
        </div>
        <div class="grid grid-2">
          <article class="card chart-card"><div class="card-header"><div><h2>${state.insight} trend</h2><p>Daily net revenue with prior-period comparison</p></div><div class="chart-legend"><span><i class="legend-dot"></i>Current</span><span><i class="legend-dot compare"></i>Prior</span></div></div>${lineChart()}</article>
          <article class="card"><div class="card-header"><div><h2>Revenue by channel</h2><p>Backing values for the chart</p></div><span class="status info">Net</span></div><div class="card-body"><div class="bar-list" role="img" aria-label="Online store contributes 62 percent of revenue, subscriptions 21, local delivery 11 and pickup 6 percent."><div class="bar-row"><span>Online store</span><div class="bar-track"><i style="width:62%"></i></div><strong>62%</strong></div><div class="bar-row"><span>Subscriptions</span><div class="bar-track"><i style="width:21%"></i></div><strong>21%</strong></div><div class="bar-row"><span>Local delivery</span><div class="bar-track"><i style="width:11%"></i></div><strong>11%</strong></div><div class="bar-row"><span>Pickup</span><div class="bar-track"><i style="width:6%"></i></div><strong>6%</strong></div></div></div></article>
        </div>
        <div class="table-card"><div class="table-top"><div><strong>Daily backing data</strong> <span>· values shown in CAD</span></div>${button("Download CSV", "secondary", "download", 'data-action="toast"')}</div><div class="table-scroll"><table class="data-table"><caption>Daily analytics backing data</caption><thead><tr><th>Date</th><th class="num">Orders</th><th class="num">Gross</th><th class="num">Refunds</th><th class="num">Net</th><th class="num">AOV</th></tr></thead><tbody>${[["Jul 17",46,"$7,022","$180","$6,842","$148.74"],["Jul 16",42,"$6,280","$0","$6,280","$149.52"],["Jul 15",39,"$5,940","$96","$5,844","$149.85"],["Jul 14",51,"$7,184","$241","$6,943","$136.14"]].map(row => `<tr>${row.map((cell,index) => `<td data-label="${["Date","Orders","Gross","Refunds","Net","AOV"][index]}" class="${index ? "num" : ""}">${cell}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>
      </section>`;
  };

  const integrationsScreen = () => `
    <section class="page" data-page="integrations">
      ${pageHeading({
        module: "System / Integrations",
        title: "WooCommerce operations",
        description: "Connection health, read-only product refresh, mapping review and guarded writeback in one audit-grade console.",
        actions: `${button("View audit log", "secondary", "clock", 'data-action="toast"')}${button("Refresh products", "primary", "refresh", 'data-action="sync"')}`
      })}
      <div class="integration-hero"><div class="integration-logo" aria-hidden="true">W</div><div><h2>WooCommerce · Sample store</h2><p>Connected through backend environment variables · credentials never enter this prototype or the frontend.</p></div><span class="status success">Connected · read-only</span></div>
      <div class="guard-grid">
        <div class="guard"><span>API reachability</span><strong class="status success">Healthy</strong></div>
        <div class="guard"><span>Last product refresh</span><strong>2 min ago</strong></div>
        <div class="guard"><span>Mapping queue</span><strong>7 need review</strong></div>
        <div class="guard"><span>Stock writeback</span><strong class="status warning">Locked</strong></div>
      </div>
      <div class="grid grid-3">
        <article class="card metric-card success"><div class="metric-label">Products discovered <span class="status success">Read</span></div><strong class="metric-value">246</strong><div class="metric-foot">simple products and variations</div></article>
        <article class="card metric-card warning"><div class="metric-label">Mapping exceptions <span class="status warning">Review</span></div><strong class="metric-value">7</strong><div class="metric-foot">manual Pongo fields protected</div></article>
        <article class="card metric-card live"><div class="metric-label">Pending writeback <span class="status live">Blocked</span></div><strong class="metric-value">0</strong><div class="metric-foot">early-stage safety lock enabled</div></article>
      </div>
      <div class="grid grid-2">
        <article class="card"><div class="card-header"><div><h2>Safety boundary</h2><p>Explicit policy before any external mutation</p></div><span class="status warning">Guarded</span></div><div class="card-body"><div class="priority-list"><div class="priority-row"><span class="priority-icon success">${icon("check")}</span><div><strong>Read-only product refresh</strong><span>Available; never overwrites Pongo-owned fields</span></div><span class="status success">Allowed</span></div><div class="priority-row"><span class="priority-icon">${icon("warning")}</span><div><strong>Live stock writeback</strong><span>Locked until local workflows and reconciliation are approved</span></div><button class="button button-danger" data-action="open-guard">Inspect lock</button></div></div></div></article>
        <article class="card"><div class="card-header"><div><h2>Recent sync runs</h2><p>Fictional operational events</p></div>${button("All runs", "quiet", "arrow", 'data-action="toast"')}</div><div class="card-body"><div class="timeline"><div class="timeline-row"><time>10:44:18</time><strong>Product refresh complete</strong><span>246 inspected · 0 overwritten</span><span class="status success">Success</span></div><div class="timeline-row"><time>09:18:04</time><strong>Mapping review saved</strong><span>4 records resolved by Ops Admin</span><span class="status info">Audit</span></div><div class="timeline-row"><time>Yesterday</time><strong>Order refresh interrupted</strong><span>Timeout · retry retained the prior snapshot</span><span class="status danger">Recovered</span></div></div></div></article>
      </div>
      <div class="table-card"><div class="table-top"><div><strong>Mapping review queue</strong> <span>· 7 records</span></div>${button("Open mapping workspace", "secondary", "layers", 'data-action="toast"')}</div><div class="table-scroll"><table class="data-table"><caption>WooCommerce mapping review queue</caption><thead><tr><th>Remote ID</th><th>Remote item</th><th>Suggested local SKU</th><th>Reason</th><th>Status</th><th>Action</th></tr></thead><tbody>${[["WC-8412","Sample product variation A","DOG-FOOD-12","SKU match"],["WC-8418","Sample product variation B","CAT-LIT-CL20","Barcode match"],["WC-8441","Sample simple product C","—","No unique match"]].map((row,index) => `<tr><td data-label="Remote ID"><span class="mono">${row[0]}</span></td><td data-label="Remote item" class="wide-cell">${row[1]}</td><td data-label="Suggested SKU"><span class="mono">${row[2]}</span></td><td data-label="Reason">${row[3]}</td><td data-label="Status"><span class="status ${index === 2 ? "warning" : "info"}">${index === 2 ? "Manual review" : "Suggested"}</span></td><td data-label="Action"><button class="button button-quiet" data-action="toast">Review</button></td></tr>`).join("")}</tbody></table></div></div>
    </section>`;

  const settingsScreen = () => `
    <section class="page" data-page="settings">
      ${pageHeading({
        module: "System / Settings",
        title: "Organization settings",
        description: "Calm, grouped configuration with explicit ownership and honest roadmap boundaries.",
        actions: button("View change history", "secondary", "clock", 'data-action="toast"')
      })}
      <div class="settings-layout">
        <aside class="card settings-nav" aria-label="Settings sections"><button class="is-active">Company</button><button>Users <span class="status neutral">Roadmap</span></button><button>Warehouses <span class="status neutral">Roadmap</span></button><button>System <span class="status neutral">Roadmap</span></button><button class="button-danger" data-action="open-reset">Reset demo</button></aside>
        <article class="card">
          <form id="settings-form" novalidate>
            <div class="settings-form">
              <section class="form-section"><h3>Organization</h3><p>Used in operational exports and internal labels.</p><label class="field"><span>Display name</span><input class="control" name="displayName" value="Pongo Pet Supplies" required></label><label class="field"><span>Operational timezone</span><select class="control" name="timezone"><option>America/Edmonton</option></select></label></section>
              <section class="form-section"><h3>Operations contact</h3><p>Receives failure and reconciliation alerts.</p><label class="field"><span>Email address</span><input class="control" id="ops-email" name="opsEmail" type="email" value="ops@example.test" aria-describedby="ops-email-help ops-email-error" required><small class="help-text" id="ops-email-help">Fictional preview address; no messages are sent.</small><small class="error-text" id="ops-email-error" hidden>Enter a complete email address.</small></label><label class="field"><span>Daily summary</span><span class="toggle"><input type="checkbox" checked aria-label="Send daily summary"><span>Send at 07:00 local time</span></span></label></section>
              <section class="form-section"><h3>Inventory defaults</h3><p>Defaults never replace explicit values on an item or movement.</p><label class="field"><span>Default warehouse</span><select class="control"><option>Main warehouse</option></select></label><label class="field"><span>Low-stock warning window</span><select class="control"><option>7 days projected demand</option><option>14 days projected demand</option></select></label></section>
              <section class="form-section"><h3>Integration safety</h3><p>Connection details stay in backend environment variables; this screen controls operational policy only.</p><label class="field"><span>WooCommerce mode</span><input class="control" value="Read-only refresh" disabled><small class="help-text">Live stock writeback remains locked.</small></label><label class="field"><span>Mapping review</span><button type="button" class="button button-secondary" data-screen="integrations">Open integration workspace ${icon("arrow")}</button></label></section>
            </div>
            <div class="save-bar"><span id="save-status">No unsaved changes</span>${button("Save settings", "primary", "check", 'type="submit"')}</div>
          </form>
        </article>
      </div>
    </section>`;

  const componentsScreen = () => `
    <section class="page" data-page="components">
      ${pageHeading({
        module: "Reference / UI library",
        title: "Pongo OS v2 components",
        description: "A compact implementation reference for Command Nexus foundations, components, states and interaction contracts."
      })}
      <article class="card"><div class="card-header"><div><h2>Signature palette</h2><p>Deep indigo operational chrome + light work canvas + warm live signal</p></div><span class="status info">AA pairs documented</span></div><div class="card-body"><div class="token-row">${[["Pongo 950","#080A3D"],["Pongo 900","#0B0E68"],["Pongo 800","#0F149A"],["Pongo 650","#3038CF"],["Live 500","#E86732"],["Canvas","#F4F5F9"],["Success","#08654D"],["Danger","#A52A22"]].map(([name,hex]) => `<div class="swatch"><i style="background:${hex}"></i><span>${name}</span><code>${hex}</code></div>`).join("")}</div></div></article>
      <div class="gallery-grid">
        <article class="card"><div class="card-header"><h2>Typography</h2><span>UI + mono identifiers</span></div><div class="card-body type-sample"><h2>Operational clarity</h2><h3>Decisions above decoration</h3><p>Readable body copy uses a system-safe humanist sans stack.</p><p class="mono" style="margin-top:14px">SKU DOG-FOOD-12 · ORDER #1058</p></div></article>
        <article class="card"><div class="card-header"><h2>Actions</h2><span>One primary per region</span></div><div class="card-body component-stack">${button("Primary", "primary", "check", 'data-action="toast"')}${button("Secondary", "secondary", "edit", 'data-action="toast"')}${button("Quiet", "quiet", "arrow", 'data-action="toast"')}${button("Danger", "danger", "warning", 'data-action="open-reset"')}<button class="button button-primary" disabled>Disabled</button></div></article>
        <article class="card"><div class="card-header"><h2>Status language</h2><span>Dot + text, never color alone</span></div><div class="card-body component-stack"><span class="status success">Healthy</span><span class="status warning">Needs review</span><span class="status danger">Exception</span><span class="status info">Allocated</span><span class="status live">Live</span><span class="status neutral">Draft</span></div></article>
        <article class="card"><div class="card-header"><h2>Fields</h2><span>Visible labels and persistent help</span></div><div class="card-body grid grid-2"><label class="field"><span>SKU or barcode</span><input class="control" value="DOG-FOOD-12"><small class="help-text">Scanner input ends with Enter.</small></label><label class="field"><span>Warehouse</span><select class="control"><option>Main warehouse</option></select></label><label class="field"><span>Example error</span><input class="control error" value="invalid" aria-describedby="gallery-error"><small class="error-text" id="gallery-error">Use an uppercase SKU with hyphens.</small></label><label class="field"><span>Disabled</span><input class="control" value="System owned" disabled></label></div></article>
        <article class="card"><div class="card-header"><h2>Loading</h2><span>Shown after 300 ms</span></div><div class="card-body"><div class="skeleton skeleton-line short"></div><div class="skeleton skeleton-line"></div><div class="skeleton skeleton-block"></div></div></article>
        <article class="card"><div class="card-header"><h2>Interaction layers</h2><span>Focus-aware prototype</span></div><div class="card-body component-stack">${button("Open drawer", "secondary", "layers", 'data-order="1058"')}${button("Open command", "secondary", "command", 'data-action="open-command"')}${button("Guarded action", "danger", "warning", 'data-action="open-guard"')}${button("Toast", "primary", "bell", 'data-action="toast"')}</div></article>
        <article class="card"><div class="card-header"><h2>Search, filters and chips</h2><span>Applied state remains visible</span></div><div class="card-body"><label class="field"><span>Search records</span><span class="search-control">${icon("search")}<input class="control" type="search" placeholder="Order, SKU or barcode"></span></label><div class="filter-chips" style="margin-top:12px"><span class="chip">Status: Open <button data-action="remove-chip" aria-label="Remove open status">${icon("x")}</button></span><span class="chip">Warehouse: Main <button data-action="remove-chip" aria-label="Remove warehouse">${icon("x")}</button></span>${button("Filters", "secondary", "filter", 'data-action="toast"')}</div></div></article>
        <article class="card"><div class="card-header"><h2>Alerts and operational states</h2><span>Icon + text + consequence</span></div><div class="card-body grid"><div class="signal-strip">${icon("info")}<div><strong>Read-only mode</strong> <span>Local fields remain protected during refresh.</span></div></div><div class="signal-strip" style="border-color:#f4b7b2;background:var(--danger-soft)">${icon("error")}<div><strong>Recoverable error</strong> <span>Prior data remains available; retry keeps filters.</span></div></div></div></article>
      </div>
      <div class="grid grid-2">
        <article class="card chart-card"><div class="card-header"><div><h2>Chart system</h2><p>Labelled series plus textual backing data</p></div><div class="chart-legend"><span><i class="legend-dot"></i>Current</span><span><i class="legend-dot compare"></i>Prior</span></div></div>${lineChart()}</article>
        <article class="card"><div class="card-header"><h2>Icon language</h2><span>20 px outline, no emoji</span></div><div class="card-body component-stack">${["home","orders","box","truck","chart","plug","settings","search","scan","warning","check","refresh","edit","map","layers","download"].map(name => `<button class="icon-button" aria-label="${name} icon example" data-action="toast">${icon(name)}</button>`).join("")}</div></article>
      </div>
      <div class="table-card"><div class="table-top"><div><strong>Data table pattern</strong> <span>selected row, status, identifier and row action</span></div><span class="status info">2 records</span></div><div class="table-scroll"><table class="data-table"><caption>Component gallery table example</caption><thead><tr><th>Identifier</th><th>Description</th><th>Status</th><th class="num">Quantity</th><th>Action</th></tr></thead><tbody><tr class="is-selected"><td data-label="Identifier"><span class="mono">ITEM-001</span></td><td data-label="Description" class="wide-cell">Selected inventory record</td><td data-label="Status"><span class="status success">Healthy</span></td><td data-label="Quantity" class="num">48</td><td data-label="Action"><button class="icon-button" data-action="toast" aria-label="Edit ITEM-001">${icon("edit")}</button></td></tr><tr><td data-label="Identifier"><span class="mono">ITEM-002</span></td><td data-label="Description" class="wide-cell">Low-stock inventory record</td><td data-label="Status"><span class="status warning">Below par</span></td><td data-label="Quantity" class="num">4</td><td data-label="Action"><button class="icon-button" data-action="toast" aria-label="Edit ITEM-002">${icon("edit")}</button></td></tr></tbody></table></div></div>
      <div class="grid grid-2"><div class="state-card" style="width:100%"><span class="state-icon">${icon("box")}</span><h2>Empty state</h2><p>No records match the current filters. Clear filters without losing the search term.</p>${button("Clear filters", "primary", "x", 'data-action="toast"')}</div><div class="state-card" style="width:100%"><span class="state-icon error">${icon("error")}</span><h2>Error state</h2><p>The request failed, but prior local work is preserved and the recovery action is explicit.</p>${button("Retry", "primary", "refresh", 'data-action="toast"')}</div></div>
    </section>`;

  const screenRenderers = {
    command: commandScreen,
    orders: ordersScreen,
    pick: pickScreen,
    inventory: inventoryScreen,
    location: locationScreen,
    receiving: receivingScreen,
    insights: insightsScreen,
    integrations: integrationsScreen,
    settings: settingsScreen,
    components: componentsScreen
  };

  const alternateState = () => {
    const config = screenConfig[state.screen];
    if (state.preview === "loading") return `
      <section class="page"><h1 class="sr-only">Loading ${config.title}</h1><div class="state-skeleton" aria-busy="true" aria-label="Loading ${config.title}"><div class="skeleton skeleton-line short" style="height:14px"></div><div class="skeleton skeleton-line" style="height:34px;width:46%"></div><div class="grid grid-4">${Array.from({length:4}, () => '<div class="card card-body"><div class="skeleton skeleton-line short"></div><div class="skeleton skeleton-line" style="height:28px"></div><div class="skeleton skeleton-line"></div></div>').join("")}</div><div class="card card-body" style="margin-top:16px"><div class="skeleton skeleton-line short"></div><div class="skeleton skeleton-block" style="height:260px"></div></div></div></section>`;
    const isError = state.preview === "error";
    return `<section class="state-page"><div class="state-card"><span class="state-icon ${isError ? "error" : ""}">${icon(isError ? "error" : "box")}</span><h1>${isError ? `${config.title} could not load` : `No ${config.title.toLowerCase()} data yet`}</h1><p>${isError ? "The fictional preview simulates a recoverable network failure. Your local work is unchanged; retry or return to Command Center." : "This is the intentionally designed first-run state. It explains what belongs here and provides one useful next step."}</p>${isError ? `${button("Retry", "primary", "refresh", 'data-action="retry"')}${button("Command Center", "quiet", "home", 'data-screen="command"')}` : button(state.screen === "orders" ? "Import orders" : state.screen === "inventory" ? "Create first item" : "Start setup", "primary", "plus", 'data-action="toast"')}</div></section>`;
  };

  const renderContext = () => {
    const config = screenConfig[state.screen];
    $("#context-eyebrow").textContent = config.eyebrow;
    $("#context-title").textContent = config.title;
    $("#context-nav").innerHTML = config.links.map(([screen, label, iconName, count, view = ""]) => `
      <button class="context-link ${screen === state.screen && (!view || view === state.view) ? "is-active" : ""}" data-screen="${screen}" ${view ? `data-view="${view}"` : ""}>
        ${icon(iconName)}<span>${label}</span>${count ? `<b>${count}</b>` : ""}
      </button>`).join("");
    $$(".module-link").forEach(link => link.classList.toggle("is-active", link.dataset.module === config.module));
  };

  const render = ({ focusMain = false } = {}) => {
    renderContext();
    $("#main-content").innerHTML = state.preview === "populated" ? screenRenderers[state.screen]() : alternateState();
    $$("[data-state]").forEach(control => control.classList.toggle("is-active", control.dataset.state === state.preview));
    document.title = `${screenConfig[state.screen].title} — Pongo OS v2 concept`;
    if (focusMain) $("#main-content").focus({ preventScroll: true });
  };

  const announce = (message) => {
    const live = $("#live-region");
    live.textContent = "";
    window.setTimeout(() => { live.textContent = message; }, 20);
  };

  const setScreen = (screen, view = "", push = true) => {
    if (!screenConfig[screen]) return;
    state.screen = screen;
    state.view = view;
    state.preview = "populated";
    $("#app-shell").classList.remove("mobile-nav-open", "context-open");
    $(".mobile-menu").setAttribute("aria-expanded", "false");
    if (push) history.pushState({ screen }, "", `#${screen}`);
    render({ focusMain: true });
  };

  const toast = (title = "Prototype action complete", detail = "This interaction is simulated; no data or external system changed.") => {
    const node = document.createElement("div");
    node.className = "toast";
    node.innerHTML = `<span>${icon("check")}</span><div><strong>${title}</strong><small>${detail}</small></div><button aria-label="Dismiss notification">${icon("x")}</button>`;
    $("#toast-region").append(node);
    node.querySelector("button").addEventListener("click", () => node.remove());
    window.setTimeout(() => node.isConnected && node.remove(), 5200);
    announce(title);
  };

  const closeLayer = (layerSelector) => {
    const layer = $(layerSelector);
    if (!layer || layer.hidden) return;
    layer.hidden = true;
    layer.innerHTML = "";
    document.body.style.overflow = "";
    if (state.lastFocus?.isConnected) state.lastFocus.focus();
  };

  const openLayer = (layerSelector, markup, focusSelector) => {
    state.lastFocus = document.activeElement;
    const layer = $(layerSelector);
    layer.innerHTML = markup;
    layer.hidden = false;
    document.body.style.overflow = "hidden";
    window.setTimeout(() => $(focusSelector, layer)?.focus(), 20);
  };

  const openOrder = (id) => {
    const row = orders.find(order => order[0] === id) || orders[0];
    const [orderId, customer, due, status, tone, lines, total, method] = row;
    openLayer("#drawer-layer", `
      <button class="layer-scrim" data-action="close-drawer" aria-label="Close order detail"></button>
      <aside class="drawer" role="dialog" aria-modal="true" aria-labelledby="order-drawer-title" tabindex="-1">
        <div class="drawer-head"><div><span>Order detail · fictional record</span><h2 id="order-drawer-title">Order #${orderId}</h2></div><button class="icon-button" data-action="close-drawer" aria-label="Close order detail">${icon("x")}</button></div>
        <div class="drawer-body">
          <div class="component-stack"><span class="status ${tone}">${status}</span><span class="status info">${method}</span></div>
          <div class="detail-facts" style="margin-top:14px"><div class="fact"><span>Customer</span><strong>${customer}</strong></div><div class="fact"><span>Due</span><strong>${due}</strong></div><div class="fact"><span>Lines</span><strong>${lines}</strong></div><div class="fact"><span>Total</span><strong>${total}</strong></div></div>
          <section class="detail-section"><h3>Order lines</h3><div class="priority-list card"><div class="priority-row"><span class="queue-index">1</span><div><strong>North Range Adult Dog Food</strong><span class="mono">DOG-FOOD-12 · A-01-02</span></div><strong>× 2</strong></div><div class="priority-row"><span class="queue-index">2</span><div><strong>Salmon Training Treats</strong><span class="mono">TRT-SALM-150 · B-01-04</span></div><strong>× 4</strong></div></div></section>
          <section class="detail-section"><h3>Audit timeline</h3><div class="timeline"><div class="timeline-row"><time>10:38</time><strong>Inventory checked</strong><span>One sellable unit reserved</span></div><div class="timeline-row"><time>10:31</time><strong>Order imported</strong><span>Read-only WooCommerce sync</span></div></div></section>
          <section class="detail-section"><div class="signal-strip">${icon("info")}<div><strong>Local workflow only.</strong> <span>No external status changes occur in this concept.</span></div></div></section>
        </div>
        <div class="drawer-foot">${button("Open full page", "secondary", "arrow", 'data-action="toast"')}${button(status === "Needs allocation" ? "Resolve allocation" : "Send to picking", "primary", "scan", 'data-action="drawer-primary"')}</div>
      </aside>`, ".drawer");
  };

  const openCommand = () => openLayer("#modal-layer", `
    <button class="layer-scrim" data-action="close-modal" aria-label="Close command menu"></button>
    <section class="modal" role="dialog" aria-modal="true" aria-labelledby="command-title">
      <div class="modal-head"><h2 id="command-title">Search and command</h2><button class="icon-button" data-action="close-modal" aria-label="Close command menu">${icon("x")}</button></div>
      <div class="modal-body">
        <label class="field"><span>Search destinations, records or actions</span><span class="search-control">${icon("search")}<input id="command-input" class="control" autocomplete="off" placeholder="Try orders, DOG-FOOD-12 or receive"></span></label>
        <div class="command-results" id="command-results">
          <button class="command-result" data-screen="orders"><span>${icon("orders")}</span><span><strong>Open orders</strong><small>8 open · Commerce</small></span><kbd>↵</kbd></button>
          <button class="command-result" data-screen="inventory"><span>${icon("box")}</span><span><strong>Find inventory item</strong><small>Search SKU or barcode</small></span><kbd>I</kbd></button>
          <button class="command-result" data-screen="receiving"><span>${icon("truck")}</span><span><strong>Start direct receiving</strong><small>Warehouse operation</small></span><kbd>R</kbd></button>
          <button class="command-result" data-screen="integrations"><span>${icon("refresh")}</span><span><strong>Review sync health</strong><small>Read-only integration console</small></span><kbd>S</kbd></button>
        </div>
      </div>
      <div class="modal-foot"><span class="help-text">Esc closes · Enter follows a result · scanning resolves identifiers</span></div>
    </section>`, "#command-input");

  const openGuard = (kind = "writeback") => {
    const reset = kind === "reset";
    const discard = kind === "discard";
    const word = reset ? "RESET" : discard ? "DISCARD" : "UNLOCK";
    const title = reset ? "Reset preview settings?" : discard ? "Discard receiving draft?" : "Live writeback is locked";
    const body = reset ? "This only resets fictional browser state. It never touches production data." : discard ? "The 3 draft lines will be cleared in this prototype. No inventory has changed." : "The proposed product keeps WooCommerce stock writeback unavailable until read-only sync, reconciliation and local audit workflows are approved.";
    openLayer("#modal-layer", `
      <button class="layer-scrim" data-action="close-modal" aria-label="Cancel guarded action"></button>
      <section class="modal" role="dialog" aria-modal="true" aria-labelledby="guard-title">
        <div class="modal-head"><h2 id="guard-title">${title}</h2><button class="icon-button" data-action="close-modal" aria-label="Cancel guarded action">${icon("x")}</button></div>
        <div class="modal-body"><div class="signal-strip">${icon("warning")}<div><strong>Guarded operation.</strong> <span>${body}</span></div></div><label class="field" style="margin-top:16px"><span>Type ${word} to confirm</span><input id="guard-input" class="control" autocomplete="off" data-confirm-word="${word}"><small class="help-text">The confirm button remains disabled until the text matches exactly.</small></label></div>
        <div class="modal-foot">${button("Cancel", "secondary", "", 'data-action="close-modal"')}<button class="button button-danger" id="guard-confirm" data-action="guard-confirm" disabled>${reset ? "Reset demo" : discard ? "Discard draft" : "Keep writeback locked"}</button></div>
      </section>`, "#guard-input");
  };

  const previewReceipt = () => openLayer("#modal-layer", `
    <button class="layer-scrim" data-action="close-modal" aria-label="Close receipt preview"></button>
    <section class="modal" role="dialog" aria-modal="true" aria-labelledby="receipt-title">
      <div class="modal-head"><h2 id="receipt-title">Preview 3 stock movements</h2><button class="icon-button" data-action="close-modal" aria-label="Close receipt preview">${icon("x")}</button></div>
      <div class="modal-body"><div class="signal-strip">${icon("info")}<div><strong>Review before commit.</strong> <span>24 units will be added at Main warehouse; one audit row per line.</span></div></div><div class="timeline" style="margin-top:14px"><div class="timeline-row"><time>+8</time><strong class="mono">DOG-FOOD-12</strong><span>A-01-02 · 48 → 56</span></div><div class="timeline-row"><time>+10</time><strong class="mono">CAT-LIT-CL20</strong><span>A-02-01 · 9 → 19</span></div><div class="timeline-row"><time>+6</time><strong class="mono">TRT-SALM-150</strong><span>B-01-04 · 0 → 6</span></div></div></div>
      <div class="modal-foot">${button("Back to edit", "secondary", "edit", 'data-action="close-modal"')}${button("Commit receipt", "primary", "check", 'data-action="commit-receipt"')}</div>
    </section>`, ".modal");

  const updateSelection = () => {
    const bulkDock = $(".bulk-dock");
    if (!bulkDock) return;
    const count = state.selectedOrders.size;
    bulkDock.hidden = count === 0;
    $("strong", bulkDock).textContent = `${count} selected`;
    $$('[data-order-select]').forEach(box => box.closest("tr").classList.toggle("is-selected", box.checked));
    announce(`${count} orders selected`);
  };

  document.addEventListener("click", (event) => {
    const target = event.target.closest("button, a");
    if (!target) return;

    if (target.dataset.screen) {
      closeLayer("#modal-layer");
      setScreen(target.dataset.screen, target.dataset.view || "");
      return;
    }
    if (target.dataset.state) {
      state.preview = target.dataset.state;
      render({ focusMain: true });
      return;
    }
    if (target.dataset.order) {
      openOrder(target.dataset.order);
      return;
    }
    if (target.dataset.pickOrder) {
      state.pickOrder = target.dataset.pickOrder;
      render();
      toast(`Order #${state.pickOrder} loaded`, "The floor station now shows the selected fictional order.");
      return;
    }
    if (target.dataset.insight) {
      state.insight = target.dataset.insight;
      render();
      announce(`${state.insight} insights selected`);
      return;
    }

    const action = target.dataset.action;
    if (!action) return;
    const actions = {
      "toggle-mobile-nav": () => {
        const open = $("#app-shell").classList.toggle("mobile-nav-open");
        $(".mobile-menu").setAttribute("aria-expanded", String(open));
      },
      "close-mobile-nav": () => $("#app-shell").classList.remove("mobile-nav-open"),
      "collapse-context": () => {
        const collapsed = $("#app-shell").classList.toggle("context-collapsed");
        target.setAttribute("aria-expanded", String(!collapsed));
      },
      "open-command": openCommand,
      "close-modal": () => closeLayer("#modal-layer"),
      "close-drawer": () => closeLayer("#drawer-layer"),
      "toast": () => toast(),
      "sync": () => toast("Read-only refresh started", "The concept demonstrates a safe refresh; no API request was made."),
      "toggle-filters": () => toast("Filters are already visible", "On mobile the same control would open a filter sheet."),
      "remove-chip": () => { target.closest(".chip")?.remove(); toast("Filter removed"); },
      "select-all": () => {
        const shouldSelect = state.selectedOrders.size !== orders.length;
        state.selectedOrders = shouldSelect ? new Set(orders.map(order => order[0])) : new Set();
        render();
      },
      "clear-selection": () => { state.selectedOrders.clear(); render(); },
      "bulk-allocate": () => {
        const count = state.selectedOrders.size;
        state.selectedOrders.clear();
        render();
        toast(`${count} orders queued for allocation`, "A production implementation would show a preview before committing reservations.");
      },
      "pick-decrease": () => { state.pickQty = Math.max(0, state.pickQty - 1); render(); },
      "pick-increase": () => { state.pickQty = Math.min(6, state.pickQty + 1); render(); },
      "verify-pick": () => toast("Line verified", `${state.pickQty} of 6 units confirmed with an audit event.`),
      "complete-pick": () => toast("Completion blocked in concept", "Verify all 8 lines before completing the fictional order."),
      "open-move": () => toast("Move-stock flow opened", "The production pattern would preview source and destination movement rows."),
      "open-guard": () => openGuard("writeback"),
      "open-reset": () => openGuard("reset"),
      "open-discard": () => openGuard("discard"),
      "guard-confirm": () => { closeLayer("#modal-layer"); toast("Safe state preserved", "The guarded demo action completed without changing production or external data."); },
      "preview-receipt": previewReceipt,
      "commit-receipt": () => { closeLayer("#modal-layer"); toast("Receipt committed in preview", "24 fictional units and 3 simulated movement rows were created in browser memory only."); },
      "drawer-primary": () => { closeLayer("#drawer-layer"); setScreen("pick"); },
      "retry": () => { state.preview = "loading"; render(); window.setTimeout(() => { state.preview = "populated"; render(); toast("Connection restored"); }, 650); }
    };
    actions[action]?.();
  });

  document.addEventListener("change", (event) => {
    if (event.target.matches("[data-order-select]")) {
      const id = event.target.dataset.orderSelect;
      if (event.target.checked) state.selectedOrders.add(id); else state.selectedOrders.delete(id);
      updateSelection();
    }
    if (event.target.closest("#settings-form")) $("#save-status").textContent = "Unsaved changes";
  });

  document.addEventListener("input", (event) => {
    if (event.target.id === "guard-input") {
      $("#guard-confirm").disabled = event.target.value !== event.target.dataset.confirmWord;
    }
    if (event.target.id === "command-input") {
      const query = event.target.value.trim().toLowerCase();
      $$(".command-result").forEach(result => result.hidden = !result.textContent.toLowerCase().includes(query));
    }
  });

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      openCommand();
    }
    if (event.key === "Escape") {
      closeLayer("#modal-layer");
      closeLayer("#drawer-layer");
      $("#app-shell").classList.remove("mobile-nav-open", "context-open");
    }
    if (event.key === "Enter" && event.target.id === "pick-scan") {
      event.preventDefault();
      const success = event.target.value.trim().toUpperCase() === "DOG-FOOD-12";
      const result = $("#pick-scan-result");
      result.className = `scan-result ${success ? "success" : "error"}`;
      result.innerHTML = success ? `<strong>Verified · DOG-FOOD-12</strong><span>Correct item at A-01-02. Quantity ready to confirm.</span>` : `<strong>Scan does not match</strong><span>Expected DOG-FOOD-12. No quantity changed.</span>`;
      announce(success ? "Correct item verified" : "Scan does not match expected item");
      event.target.select();
    }
    if (event.key === "Enter" && event.target.id === "receive-scan") {
      event.preventDefault();
      const success = event.target.value.trim().toUpperCase() === "CAT-LIT-CL20";
      const result = $("#receive-scan-result");
      result.className = `scan-result ${success ? "success" : "error"}`;
      result.innerHTML = success ? `<strong>CAT-LIT-CL20 found</strong><span>Item already exists in this draft; quantity focus would move to its row.</span>` : `<strong>No sellable unit found</strong><span>Check the barcode or create a manual item first.</span>`;
      announce(success ? "Receiving item found" : "No sellable unit found");
      event.target.select();
    }
  });

  document.addEventListener("submit", (event) => {
    if (event.target.id !== "settings-form") return;
    event.preventDefault();
    const email = $("#ops-email");
    const valid = email.validity.valid;
    email.classList.toggle("error", !valid);
    $("#ops-email-error").hidden = valid;
    email.setAttribute("aria-invalid", String(!valid));
    if (!valid) {
      email.focus();
      announce("Settings form has one error");
      return;
    }
    $("#save-status").textContent = "Saved just now · browser memory only";
    toast("Settings saved", "The preview stored no persistent data and contacted no service.");
  });

  window.addEventListener("popstate", () => {
    const screen = location.hash.slice(1);
    if (screenConfig[screen]) {
      state.screen = screen;
      state.view = "";
      render({ focusMain: true });
    }
  });

  render();
})();
