import { randomUUID } from 'node:crypto';
import { expect, test } from '@playwright/test';

const apiBase = process.env.PONGO_E2E_API_URL || 'http://127.0.0.1:8000';

async function chooseOutcome(page, name) {
  await page.getByRole('button', { name }).click();
  await page.getByRole('button', { name: 'Continue' }).click();
}

async function uploadAndValidate(page, name, csv) {
  await page.locator('input[type="file"]').setInputFiles({ name, mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: 'Upload and match columns' }).click();
  await page.getByRole('button', { name: 'Validate rows' }).click();
}

async function expectNoDocumentOverflow(page) {
  const dimensions = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client + 1);
}

test('repairs, imports, audits, and updates items without changing stock', async ({ page }) => {
  const runId = randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase();
  const sku = `IMPORT-${runId}-A`;
  const correctedSku = `IMPORT-${runId}-B`;
  const duplicateSku = `IMPORT-${runId}-DUP`;

  await page.goto('/#/items/import');
  await chooseOutcome(page, /Add new items/);
  await uploadAndValidate(page, 'guided-items.csv', [
    'SKU,Product name,Barcode,Category,Brand,Unit cost,Active',
    `${sku},Original product,600${runId}01,Dog Food,Pongo QA,12.50,Yes`,
    `${duplicateSku},Correct this duplicate,600${runId}02,Cat Treats,Pongo QA,4.25,Yes`,
    `${duplicateSku},Exclude this duplicate,600${runId}03,Cat Treats,Pongo QA,4.25,Yes`,
  ].join('\n'));

  await page.getByRole('button', { name: 'Edit row 3' }).click();
  const editor = page.getByRole('dialog', { name: 'Fix item data' });
  await editor.getByRole('textbox', { name: 'SKU' }).fill(correctedSku);
  await editor.getByRole('button', { name: 'Save and revalidate' }).click();
  await page.getByRole('button', { name: 'Exclude row 4' }).click();
  await expect(page.getByText('Every row is ready')).toBeVisible();
  for (const [width, height] of [[1920, 1080], [1440, 900], [1280, 800], [1024, 768]]) {
    await page.setViewportSize({ width, height });
    await expectNoDocumentOverflow(page);
  }
  await page.setViewportSize({ width: 1205, height: 708 });

  await page.getByRole('button', { name: 'Review import' }).click();
  await page.getByRole('checkbox', { name: /I reviewed the outcome/ }).check();
  await page.getByRole('button', { name: /Import \d+ ready items?/ }).click();
  await expect(page.getByRole('heading', { name: 'Import completed' })).toBeVisible();
  await expect(page.getByText('Created').locator('..').getByText('2')).toBeVisible();
  await expect(page.getByText('Excluded').locator('..').getByText('1')).toBeVisible();

  let items = await (await page.request.get(`${apiBase}/api/items?sku=${encodeURIComponent(sku)}`)).json();
  expect(items.items[0]['In Stock']).toBe(0);

  await page.getByRole('link', { name: 'View history' }).click();
  await expect(page.getByRole('cell', { name: 'Completed' }).first()).toBeVisible();
  await page.getByRole('table').getByRole('button').first().click();
  await expect(page.getByText(/2 created · 0 updated · 0 unchanged · 1 excluded/)).toBeVisible();
  await page.setViewportSize({ width: 900, height: 800 });
  await expectNoDocumentOverflow(page);

  await page.getByRole('link', { name: 'New import' }).click();
  await chooseOutcome(page, /Update item details/);
  await uploadAndValidate(page, 'guided-update.csv', `SKU,Product name\n${sku},Updated product`);
  await expect(page.getByText('Every row is ready')).toBeVisible();
  await page.getByRole('button', { name: 'Review import' }).click();
  await expect(page.getByRole('row', { name: `${sku} Product name Original product Updated product` })).toBeVisible();
  await page.getByRole('checkbox', { name: /I reviewed the outcome/ }).check();
  await page.getByRole('button', { name: /Import \d+ ready items?/ }).click();
  await expect(page.getByRole('heading', { name: 'Import completed' })).toBeVisible();

  items = await (await page.request.get(`${apiBase}/api/items?sku=${encodeURIComponent(sku)}`)).json();
  expect(items.items[0].Description).toBe('Updated product');
  expect(items.items[0]['In Stock']).toBe(0);
});
