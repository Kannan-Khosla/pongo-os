import { createHmac, randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { createActiveLocation, registerOperator } from './support/isolated-workspace.js';

const apiBase = process.env.PONGO_E2E_API_URL || 'http://127.0.0.1:8000';
const wooBase = process.env.PONGO_E2E_WOO_URL || 'http://127.0.0.1:9000';
const webhookSecret = 'pongo-e2e-webhook-secret-at-least-32-characters';

async function json(response) {
  if (!response.ok()) {
    throw new Error(`${response.status()} ${await response.text()}`);
  }
  return response.json();
}

test('import → opening balance → automatic allocation → bulk pick → completion → Woo update → report', async ({ page }) => {
  const runId = randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase();
  const sku = `E2E-FOOD-${runId}`;
  const barcode = `E2E-BAR-${runId}`;
  const productId = Number.parseInt(runId.slice(0, 6), 16) + 10_000;
  const orderId = productId + 20_000_000;
  await registerOperator(page, { displayName: 'Production E2E Operator', runId });
  const location = await createActiveLocation(page, apiBase, runId);

  const columns = ['Client', 'SKU', 'Product name', 'Category', 'Unit of measurement', 'Warehouse', 'Inventory location', 'Default location', 'Barcode', 'Manufacturer', 'Recommended retail price', 'Sales price', 'Unit cost', 'Weight', 'Default economic order', 'Default lead time days', 'Par level', 'Track lot', 'Reorder', 'Storage length', 'Storage width', 'Storage height', 'Brand'];
  const row = ['Pongo', sku, 'E2E Duck Food', 'Dog Food', 'Each', location.warehouse, location.code, location.code, barcode, 'E2E Brand', '15.00', '12.00', '5.00', '1', '6', '5', '3', 'true', 'true', '1', '1', '1', 'E2E Brand'];
  const csv = `${columns.join(',')}\n${row.join(',')}\n`;
  await page.goto('/#/items/import');
  await page.getByRole('button', { name: /Add new items/ }).click();
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.locator('input[type="file"]').setInputFiles({ name: 'e2e-items.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: 'Upload and match columns' }).click();
  await page.getByRole('button', { name: 'Validate rows' }).click();
  await expect(page.getByText('Every row is ready')).toBeVisible();
  await page.getByRole('button', { name: 'Review import' }).click();
  await page.getByRole('checkbox', { name: /I reviewed the outcome/ }).check();
  await page.getByRole('button', { name: /Import \d+ ready items?/ }).click();
  await expect(page.getByRole('heading', { name: 'Import completed' })).toBeVisible();

  const items = await json(await page.request.get(`${apiBase}/api/items?sku=${encodeURIComponent(sku)}`));
  const item = items.items[0];
  expect(item['In Stock']).toBe(0);
  await json(await page.request.post(`${apiBase}/api/items/${item.id}/opening-balance`, {
    data: { 'In Stock': 10, Allocated: 0, Warehouse: location.warehouse, 'Inventory Location': location.code, idempotencyKey: randomUUID(), createdBy: 'playwright' },
  }));
  await json(await page.request.post(`${apiBase}/api/integrations/woocommerce/remap/commit`, {
    data: { woo_product_id: productId, woo_variation_id: null, item_id: item.id, note: 'E2E contract mapping' },
  }));

  await json(await page.request.post(`${wooBase}/reset`));
  const order = {
    id: orderId, number: String(orderId), status: 'processing', currency: 'CAD', total: '24.00',
    date_created: '2026-07-31T12:00:00Z', date_modified: '2026-07-31T12:00:00Z',
    billing: { first_name: 'E2E', last_name: 'Customer', email: 'customer@example.invalid' },
    shipping: { first_name: 'E2E', last_name: 'Customer', address_1: '1 Test Way', city: 'Calgary', state: 'AB', postcode: 'T1T1T1', country: 'CA' },
    line_items: [{ id: orderId + 1, product_id: productId, variation_id: 0, name: 'E2E Duck Food', sku, quantity: 2, price: '12.00', subtotal: '24.00', total: '24.00', meta_data: [{ key: 'barcode', value: barcode }] }],
  };
  const raw = JSON.stringify(order);
  const signature = createHmac('sha256', webhookSecret).update(raw).digest('base64');
  const delivery = await json(await page.request.post(`${apiBase}/api/integrations/woocommerce/webhooks/orders`, {
    data: raw,
    headers: {
      'Content-Type': 'application/json',
      'X-WC-Webhook-Source': `${wooBase}/`,
      'X-WC-Webhook-Topic': 'order.created',
      'X-WC-Webhook-Resource': 'order',
      'X-WC-Webhook-Event': 'created',
      'X-WC-Webhook-Signature': signature,
      'X-WC-Webhook-ID': String(orderId),
      'X-WC-Webhook-Delivery-ID': randomUUID(),
    },
  }));
  expect(delivery.status).toBe('processed');

  await page.goto('/#/orders/pick');
  await page.getByRole('checkbox', { name: `Select order ${orderId}` }).check();
  await page.getByRole('button', { name: 'Actions', exact: true }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('menuitem', { name: 'Pick Selected', exact: true }).click();
  await expect(page.getByText('1 selected order(s) picked.')).toBeVisible();

  await page.goto('/#/orders/open');
  await page.getByRole('checkbox', { name: `Select order ${orderId}` }).check();
  await page.getByRole('button', { name: 'Actions', exact: true }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('menuitem', { name: 'Mark as completed' }).click();
  await expect(page.getByText('1 of 1 selected order(s) updated.')).toBeVisible();

  const writes = (await json(await page.request.get(`${wooBase}/writes`))).writes;
  expect(writes).toEqual(expect.arrayContaining([
    expect.objectContaining({ entity: 'product', id: productId, payload: expect.objectContaining({ stock_quantity: 8 }) }),
    expect.objectContaining({ entity: 'order', id: orderId, payload: { status: 'completed' } }),
  ]));

  const report = await page.request.get(`${apiBase}/api/reports/inventory-valuation/export?sku=${encodeURIComponent(sku)}`);
  expect(report.ok()).toBeTruthy();
  expect(report.headers()['content-type']).toContain('text/csv');
  expect(await report.text()).toContain(sku);
  const verifiedRun = await json(await page.request.post(`${apiBase}/api/reports/runs/inventory-export`, {
    data: { filters: { warehouse: location.warehouse, sku }, generated_by: 'playwright' },
  }));
  expect(verifiedRun.rows).toEqual(expect.arrayContaining([expect.objectContaining({ sku })]));
  await page.goto('/#/reports/inventory/inventory-export');
  await expect(page.getByRole('heading', { name: 'Inventory Export', level: 1 }).last()).toBeVisible();
  await page.getByLabel('SKU').fill(sku);
  await page.getByRole('button', { name: 'Generate verified report' }).click();
  await expect(page.getByRole('cell', { name: sku })).toBeVisible({ timeout: 10_000 });
});
