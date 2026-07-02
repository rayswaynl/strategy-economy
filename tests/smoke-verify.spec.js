/**
 * smoke-verify.spec.js
 * Verifies the P1+P2+P3 fixes from feat/improve-jul2:
 *  1. Seed race fix: edit a field before Generate → diff is non-empty
 *  2. Unknown WFBE_UP_* constant → visible warning strip appears
 *  3. Brand bar "← All Tools" link → href is https://miksuu.com/tools
 *  4. 0 console errors throughout
 */
const { test, expect } = require('@playwright/test');

const BASE = 'http://localhost:8104';

test.describe('feat/improve-jul2 smoke suite', () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on('console', (msg) => {
      if(msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    await page.goto(BASE);
    await page.waitForFunction(
      () => document.querySelector('#model-status b')?.textContent?.includes('ready'),
      { timeout: 10000 }
    );
  });

  // ── 1. Seed race: edit before Generate produces non-empty diff ──────────
  test('edit before first Generate produces non-empty change-list', async ({ page }) => {
    // Without the fix, captureSeeds() would snapshot the already-edited value
    // and Generate would produce "No changes detected".
    // With the fix, seeds are captured at loadData() time before any edit.

    // Change a value in the model directly (simulates a UI edit)
    await page.evaluate(() => {
      window.MODEL.economy['WFBE_C_ECONOMY_INCOME_COEF'] = 9999;
    });

    // Open constants export drawer and generate (no source pasted → change-list mode)
    await page.evaluate(() => {
      window.EXPORT.openConstants();
      window.EXPORT.patchMode('changelist');
    });
    await page.evaluate(() => window.EXPORT.generate());

    const output = await page.evaluate(() => window.EXPORT.getOutput());
    // Must contain our edited value, not "No changes detected"
    expect(output).toContain('9999');
    expect(output).not.toContain('No changes detected');
  });

  // ── 2. Unknown WFBE_UP_* constant → warning strip visible ───────────────
  test('pasting source with unknown WFBE_UP_* name shows warning strip', async ({ page }) => {
    // Open upgrades drawer
    await page.evaluate(() => window.EXPORT.openUpgrades());

    // Paste source text containing an unknown constant name
    const fakeSource = [
      'missionNamespace setVariable [Format ["WFBE_C_UPGRADES_%1_LINKS","CDF"],[',
      '  [WFBE_UP_BARRACKS,0],[WFBE_UP_UNKNOWN_FUTURE_UPGRADE,1]',
      ']];',
    ].join('\n');
    await page.evaluate((src) => window.EXPORT.setSource(src), fakeSource);

    // The validation strip should be visible now
    const strip = await page.locator('#ep-validation-strip');
    await expect(strip).toBeVisible();

    const stripText = await strip.textContent();
    expect(stripText).toContain('WFBE_UP_UNKNOWN_FUTURE_UPGRADE');
    expect(stripText).toContain('WARNING');
  });

  // ── 3. Brand bar "← All Tools" link ─────────────────────────────────────
  test('brand bar has "← All Tools" link pointing to miksuu.com/tools', async ({ page }) => {
    const link = page.locator('.brandbar .back-link');
    await expect(link).toBeVisible();
    const href = await link.getAttribute('href');
    expect(href).toBe('https://miksuu.com/tools');
    const text = await link.textContent();
    expect(text.trim()).toBe('← All Tools');
  });

  // ── 4. Zero console errors ───────────────────────────────────────────────
  test('no console errors on load and generate', async ({ page }) => {
    // Generate an upgrades change-list
    await page.evaluate(() => {
      window.EXPORT.openUpgrades();
      window.EXPORT.patchMode('changelist');
    });
    await page.evaluate(() => window.EXPORT.generate());

    const errors = consoleErrors.filter(e =>
      !e.includes('favicon') && !e.includes('net::ERR_')
    );
    expect(errors).toEqual([]);
  });
});
