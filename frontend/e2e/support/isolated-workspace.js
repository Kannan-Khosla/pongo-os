import { expect } from '@playwright/test';

export async function registerOperator(page, { displayName, runId }) {
  await page.goto('/');
  await page.getByRole('tab', { name: 'Register' }).click();
  await page.getByLabel('Display name').fill(displayName);
  await page.getByLabel('Email address').fill(`e2e+${runId.toLowerCase()}@example.com`);
  await page.getByLabel('Password', { exact: true }).fill('correct-horse-battery-staple');
  await page.getByRole('button', { name: 'Create account' }).click();
  await expect(page.getByLabel(`Account: ${displayName}`)).toBeVisible();
}

export async function createActiveLocation(page, apiBase, runId) {
  const code = `E2E-${runId}`;
  const response = await page.request.post(`${apiBase}/api/locations`, {
    data: {
      warehouse: 'Main Warehouse',
      code,
      name: `E2E Rack ${runId}`,
      is_active: true,
      is_default: false,
    },
  });
  await expect(response).toBeOK();
  return response.json();
}
