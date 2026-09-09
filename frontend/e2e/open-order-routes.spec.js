import { expect, test } from '@playwright/test';

test('shares one complete shipping route per driver without an embedded map', async ({ page }) => {
  const start = '5855 99 Street NW, Edmonton, AB';
  const orders = Array.from({ length: 9 }, (_, index) => ({
    order_id: index + 1,
    woo_order_number: `ROUTE-${index + 1}`,
    customer_name: `Route customer ${index + 1}`,
    address: `${100 + index} Shipping Way, Edmonton, AB, T5J 0N3, CA`,
    direction: index < 5 ? 'N' : 'S',
  }));
  const requests = [];
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: undefined });
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: async (text) => { window.copiedRoute = text; } },
    });
  });
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/me') return route.fulfill({ json: { authenticated: true, user: { display_name: 'Route QA', role: 'admin' } } });
    if (path !== '/api/routes/open-orders/plan') return route.fulfill({ json: {} });
    const request = route.request().postDataJSON();
    requests.push(request);
    const selected = orders.filter((order) => !request.order_ids || request.order_ids.includes(order.order_id));
    const groups = request.driver_count === 2 ? [selected.slice(0, 5), selected.slice(5)] : [selected];
    const drivers = groups.filter((group) => group.length).map((stops, index) => {
      const capacityError = stops.length + Number(request.return_to_start) > 9;
      const optimized = request.optimize && index === 0;
      const query = new URLSearchParams({
        api: '1', origin: request.start_address, travelmode: 'driving',
        destination: request.return_to_start ? request.start_address : stops.at(-1).address,
        waypoints: (request.return_to_start ? stops : stops.slice(0, -1)).map((stop) => stop.address).join('|'),
      });
      return {
        driver_number: index + 1, driver_label: `Driver ${index + 1}`,
        stop_count: stops.length, estimated_duration_minutes: 30,
        directions: [...new Set(stops.map((stop) => stop.direction))],
        stops: stops.map((stop, stopIndex) => ({ ...stop, stop_sequence: stopIndex + 1 })),
        optimization_status: optimized ? 'optimized' : request.optimize ? 'unavailable' : 'not_requested',
        optimization_message: optimized ? 'Google route totals include travel and delivery time.' : 'Route optimization unavailable or not requested; this is a rough estimate.',
        google_maps_error: capacityError ? 'One Google Maps route can hold 8 shipping stops when returning to the start. Add drivers or select fewer orders.' : null,
        google_maps_links: capacityError ? [] : [{
          part_number: 1, label: 'Route', stop_count: stops.length,
          returns_to_start: request.return_to_start,
          requires_google_maps_app: stops.length - Number(!request.return_to_start) > 3,
          url: `https://www.google.com/maps/dir/?${query}`,
        }],
      };
    });
    return route.fulfill({ json: {
      start_address: request.start_address, return_to_start: request.return_to_start,
      total_open_orders: orders.length, available_orders: orders,
      selected_order_count: selected.length, assigned_order_count: selected.length,
      effective_driver_count: drivers.length, unassigned_order_count: 0,
      estimated_completion_minutes: 30, total_estimated_duration_minutes: drivers.length * 30,
      estimate_basis: 'Google route totals include travel and delivery time; unoptimized drivers use rough estimates.',
      drivers, warnings: [], excluded_orders: [], unassigned_orders: [],
    } });
  });

  await page.goto('/#/routes/live');
  const planner = page.getByRole('region', { name: 'Plan selected open orders' });
  await expect(planner.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(1);
  expect(requests.every((request) => request.optimize === false)).toBe(true);
  await expect(planner.getByRole('spinbutton', { name: 'Minutes per delivery' })).toHaveValue('5');
  await expect(planner.locator('iframe, .route-map-canvas, .route-map-card')).toHaveCount(0);
  await expect(planner.getByRole('columnheader', { name: 'Shipping address' })).toBeVisible();
  await expect(planner.getByRole('list', { name: 'Driver 1 shipping stops' }).getByRole('listitem')).toHaveCount(9);
  await expect(planner.getByText('Not optimized.')).toBeVisible();
  await expect(planner.getByText(/Open in the Google Maps app to keep every stop/)).toBeVisible();
  const originalLink = await planner.getByRole('link', { name: 'Open Google Maps' }).getAttribute('href');
  const originalQuery = new URL(originalLink).searchParams;
  expect([...originalQuery.get('waypoints').split('|'), originalQuery.get('destination')]).toEqual(orders.map((order) => order.address));
  await planner.getByRole('button', { name: 'Share route for Driver 1' }).click();
  expect(await page.evaluate(() => window.copiedRoute)).toBe(originalLink);
  await page.evaluate(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: async (data) => { window.sharedRoute = data; } });
  });
  await planner.getByRole('button', { name: 'Share route for Driver 1' }).click();
  expect(await page.evaluate(() => window.sharedRoute.url)).toBe(originalLink);

  for (const width of [1440, 900, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    const button = await planner.getByRole('link', { name: 'Open Google Maps' }).boundingBox();
    expect(button.x).toBeGreaterThanOrEqual(0);
    expect(button.x + button.width).toBeLessThanOrEqual(width);
    if (width !== 900) await page.screenshot({ path: test.info().outputPath(`route-planner-${width}.png`), fullPage: true, animations: 'disabled' });
  }

  await planner.getByRole('spinbutton', { name: 'Number of drivers' }).fill('2');
  await expect(planner.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(0);
  await expect(planner.getByText('Route settings changed. Create routes to get updated driver links.')).toBeVisible();
  await planner.getByRole('radio', { name: /Direction zones/ }).check();
  await planner.getByRole('group', { name: 'Driver 1', exact: true }).getByRole('checkbox', { name: 'N', exact: true }).check();
  await planner.getByRole('group', { name: 'Driver 2', exact: true }).getByRole('checkbox', { name: 'S', exact: true }).check();
  await planner.getByRole('button', { name: 'Create routes' }).click();
  await expect(planner.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(2);
  expect(requests.at(-1)).toMatchObject({
    optimize: true, driver_count: 2, assignment_method: 'directions',
    order_ids: orders.map((order) => order.order_id),
    direction_assignments: [{ driver_number: 1, directions: ['N'] }, { driver_number: 2, directions: ['S'] }],
    service_minutes: 5,
  });
  await expect(planner.getByText('Google optimized.')).toBeVisible();
  await expect(planner.getByText('Not optimized.')).toBeVisible();
  for (const [index, card] of (await planner.locator('.driver-route-card').all()).entries()) {
    await expect(card.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(1);
    await expect(card.getByRole('button', { name: `Share route for Driver ${index + 1}` })).toHaveCount(1);
  }

  await planner.getByRole('spinbutton', { name: 'Number of drivers' }).fill('1');
  await planner.getByRole('radio', { name: /Optimize across drivers/ }).check();
  await planner.getByRole('checkbox', { name: /Return to starting location/ }).check();
  await planner.getByRole('button', { name: 'Create routes' }).click();
  await expect(planner.getByText(/One Google Maps route can hold 8 shipping stops/)).toBeVisible();
  await expect(planner.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(0);
  await expect(planner.getByRole('button', { name: /Share route for/ })).toHaveCount(0);
  await expect(planner.getByRole('list', { name: 'Driver 1 shipping stops' }).getByRole('listitem')).toHaveCount(9);
  expect(errors).toEqual([]);
});

test('optimizes a 40-stop route with delivery time without dropping or pre-limiting stops', async ({ page }) => {
  const orders = Array.from({ length: 40 }, (_, index) => ({
    order_id: index + 1, woo_order_number: `FLEET-${index + 1}`,
    customer_name: `Fleet customer ${index + 1}`,
    address: `${100 + index} Shipping Way, Edmonton, AB, CA`, direction: 'N',
  }));
  const requests = [];
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/auth/me') return route.fulfill({ json: { authenticated: true, user: { display_name: 'Route QA', role: 'admin' } } });
    if (path !== '/api/routes/open-orders/plan') return route.fulfill({ json: {} });
    const request = route.request().postDataJSON();
    requests.push(request);
    const stops = (request.optimize ? [...orders].reverse() : orders).map((order, index) => ({ ...order, stop_sequence: index + 1 }));
    return route.fulfill({ json: {
      start_address: request.start_address, return_to_start: false,
      total_open_orders: 40, available_orders: orders, selected_order_count: 40,
      assigned_order_count: 40, effective_driver_count: 1, unassigned_order_count: 0,
      estimated_completion_minutes: 345, total_estimated_duration_minutes: 345,
      estimate_basis: 'Google route totals include travel and delivery time.',
      drivers: [{
        driver_number: 1, driver_label: 'Driver 1', stop_count: 40,
        estimated_duration_minutes: 345, stops,
        optimization_status: request.optimize ? 'optimized' : 'not_requested',
        google_maps_links: [],
        google_maps_error: 'One Google Maps link cannot include 40 deliveries. All stops remain listed.',
      }],
      warnings: [], excluded_orders: [], unassigned_orders: [],
    } });
  });
  await page.goto('/#/routes/live');
  const planner = page.getByRole('region', { name: 'Plan selected open orders' });
  const minutes = planner.getByRole('spinbutton', { name: 'Minutes per delivery' });
  const create = planner.getByRole('button', { name: 'Create routes' });
  await expect(planner.getByRole('list', { name: 'Driver 1 shipping stops' }).getByRole('listitem')).toHaveCount(40);
  await expect(minutes).toHaveValue('5');
  await expect(planner.getByText(/The Google Maps link limit does not limit optimization/)).toBeVisible();
  await expect(planner.getByText(/Add drivers|fewer orders|cannot include 40/)).toHaveCount(0);
  expect(requests.length).toBeGreaterThan(0);
  expect(requests.every((request) => request.optimize === false)).toBe(true);
  const previewRequests = requests.length;
  for (const value of ['', '-1', '61', '2.5']) {
    await minutes.fill(value);
    await expect(create).toBeDisabled();
    await expect(minutes).toHaveAttribute('aria-invalid', 'true');
  }
  await minutes.fill('0');
  await expect(create).toBeEnabled();
  await minutes.fill('60');
  await expect(create).toBeEnabled();
  await minutes.fill('7');
  expect(requests).toHaveLength(previewRequests);
  await create.click();
  await expect(planner.getByText('Google optimized.')).toBeVisible();
  expect(requests).toHaveLength(previewRequests + 1);
  expect(requests.at(-1)).toMatchObject({ optimize: true, service_minutes: 7, order_ids: orders.map((order) => order.order_id) });
  const stopRows = planner.getByRole('list', { name: 'Driver 1 shipping stops' }).getByRole('listitem');
  await expect(stopRows).toHaveCount(40);
  await expect(stopRows.first()).toContainText('Order #FLEET-40');
  await expect(stopRows.last()).toContainText('Order #FLEET-1');
  await expect(planner.getByText('40 stops · 345 min total est.')).toBeVisible();
  await expect(planner.getByRole('button', { name: /Share route for/ })).toHaveCount(0);
  await expect(planner.getByRole('link', { name: 'Open Google Maps' })).toHaveCount(0);
  for (const width of [1440, 900, 375]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    await minutes.scrollIntoViewIfNeeded();
    const bounds = await minutes.boundingBox();
    expect(bounds.x).toBeGreaterThanOrEqual(0);
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width);
    if (width !== 900) await page.screenshot({ path: test.info().outputPath(`fleet-route-${width}.png`), fullPage: true, animations: 'disabled' });
  }
  await minutes.fill('8');
  await expect(planner.getByText('Google optimized.')).toHaveCount(0);
  expect(requests).toHaveLength(previewRequests + 1);
  expect(errors).toEqual([]);
});
