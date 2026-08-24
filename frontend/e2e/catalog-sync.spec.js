import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';
import { registerOperator } from './support/isolated-workspace.js';

const apiBase = process.env.PONGO_E2E_API_URL || 'http://127.0.0.1:8000';
const wooBase = process.env.PONGO_E2E_WOO_URL || 'http://127.0.0.1:9000';

async function json(response) {
  if (!response.ok()) throw new Error(`${response.status()} ${await response.text()}`);
  return response.json();
}

async function findItem(page, sku) {
  const body = await json(await page.request.get(`${apiBase}/api/items?sku=${encodeURIComponent(sku)}`));
  return body.items.find((item) => item.SKU === sku);
}

test('catalog sync survives the worker boundary, imports every variation, and restores after reload', async ({ page }) => {
  const runId = randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase();
  await registerOperator(page, { displayName: 'Catalog E2E Operator', runId });
  await json(await page.request.post(`${wooBase}/reset`));

  await page.goto('/#/settings/catalog');
  await expect(page.getByRole('heading', { name: 'WooCommerce Products', level: 1 })).toBeVisible();
  await page.getByRole('button', { name: 'Update products from WooCommerce' }).click();
  await expect(page.getByText(/You can leave this page while Pongo updates your products/i)).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Completed' })).toBeVisible({ timeout: 60_000 });

  const terminal = await json(await page.request.get(`${apiBase}/api/integrations/woocommerce/catalog-syncs/current`));
  expect(terminal.run).toMatchObject({ status: 'completed', created_count: 3, conflict_count: 0 });

  const simple = await findItem(page, 'E2E-CATALOG-SIMPLE');
  const smallVariation = await findItem(page, 'E2E-CATALOG-VAR-SMALL');
  const largeVariation = await findItem(page, 'E2E-CATALOG-VAR-LARGE');
  expect(simple).toMatchObject({ SKU: 'E2E-CATALOG-SIMPLE', 'In Stock': 0 });
  expect(smallVariation).toMatchObject({
    SKU: 'E2E-CATALOG-VAR-SMALL',
    'In Stock': 0,
    wooProductId: 910_000_010,
    wooVariationId: 910_000_011,
  });
  expect(largeVariation).toMatchObject({
    SKU: 'E2E-CATALOG-VAR-LARGE',
    'In Stock': 0,
    wooProductId: 910_000_010,
    wooVariationId: 910_000_012,
  });
  expect(largeVariation.id).not.toBe(smallVariation.id);
  expect(await findItem(page, 'E2E-CATALOG-PARENT')).toBeUndefined();

  expect((await json(await page.request.get(`${wooBase}/writes`))).writes).toEqual([]);

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Completed' })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Update #/)).toBeVisible();
  await expect(page.getByText(/Finished/)).toBeVisible();

  await page.setViewportSize({ width: 375, height: 812 });
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
});
