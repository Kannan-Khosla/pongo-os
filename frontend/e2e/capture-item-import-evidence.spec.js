import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { expect, test } from '@playwright/test';

test.skip(process.env.PONGO_CAPTURE_EVIDENCE !== '1', 'Run explicitly to refresh release screenshots.');

const evidenceDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../docs/evidence/item-import');

async function capture(page, name) {
  await page.screenshot({ path: path.join(evidenceDir, name), animations: 'disabled' });
}

test('capture the guided item import release evidence', async ({ page }) => {
  const runId = randomUUID().replaceAll('-', '').slice(0, 8).toUpperCase();
  const duplicateSku = `EVIDENCE-${runId}-DUP`;
  await page.setViewportSize({ width: 1205, height: 708 });
  await page.goto('/#/items/import');
  await expect(page.getByRole('heading', { name: 'What do you want this file to do?' })).toBeVisible();
  await capture(page, 'import-overview.png');

  await page.getByRole('button', { name: /Add new items/ }).click();
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Upload your CSV' })).toBeVisible();
  await capture(page, 'upload.png');

  const csv = [
    'SKU,Product name,Barcode,Category,Brand,Unit cost,Active',
    `EVIDENCE-${runId}-A,Premium dog food,700${runId}01,Dog Food,Pongo,18.50,Yes`,
    `${duplicateSku},Premium cat treats,700${runId}02,Cat Treats,Pongo,5.25,Yes`,
    `${duplicateSku},Duplicate to exclude,700${runId}03,Cat Treats,Pongo,5.25,Yes`,
  ].join('\n');
  await page.locator('input[type="file"]').setInputFiles({ name: 'premium-items.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await page.getByRole('button', { name: 'Upload and match columns' }).click();
  await expect(page.getByRole('heading', { name: 'Match your columns' })).toBeVisible();
  await capture(page, 'column-mapping.png');

  await page.getByRole('button', { name: 'Validate rows' }).click();
  await expect(page.getByRole('button', { name: 'Edit row 3' })).toBeVisible();
  await capture(page, 'review-and-fix.png');
  await page.getByRole('button', { name: 'Edit row 3' }).click();
  const editor = page.getByRole('dialog', { name: 'Fix item data' });
  await editor.getByRole('textbox', { name: 'SKU' }).fill(`EVIDENCE-${runId}-B`);
  await editor.getByRole('button', { name: 'Save and revalidate' }).click();
  await page.getByRole('button', { name: 'Exclude row 4' }).click();
  await page.getByRole('button', { name: 'Review import' }).click();
  await expect(page.getByRole('heading', { name: 'Confirm the exact changes' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Import \d+ ready items?/ })).toBeVisible();
  await capture(page, 'exact-changes.png');

  await page.getByRole('checkbox', { name: /I reviewed the outcome/ }).check();
  await page.getByRole('button', { name: /Import \d+ ready items?/ }).click();
  await expect(page.getByRole('heading', { name: 'Import completed' })).toBeVisible();
  await capture(page, 'import-results.png');
  await page.getByRole('link', { name: 'View history' }).click();
  await expect(page.getByRole('heading', { name: 'Import History', exact: true })).toBeVisible();
  await expect(page.getByText('premium-items.csv', { exact: true }).first()).toBeVisible();
  await capture(page, 'import-history.png');

  await page.setViewportSize({ width: 1549, height: 752 });
  await page.goto('/#items');
  const importedItem = page.getByText('Premium dog food', { exact: true }).first();
  await expect(importedItem).toBeVisible();
  await importedItem.scrollIntoViewIfNeeded();
  await capture(page, 'items-after-import.png');

  await page.setViewportSize({ width: 1205, height: 708 });
  await page.goto('/#/items/import');
  await expect(page.getByRole('heading', { name: 'Import completed' })).toBeVisible();
  await page.getByRole('button', { name: 'Start another import' }).click();
  await page.getByRole('button', { name: /Set starting inventory/ }).click();
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Upload your CSV' })).toBeVisible();
  await capture(page, 'starting-inventory.png');
});
