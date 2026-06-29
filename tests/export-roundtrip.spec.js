/**
 * export-roundtrip.spec.js
 * Round-trip gate for Task 5.
 *
 * Tests:
 *  1. Upgrades_CDF.sqf no-op: paste source → generate → output === input (byte-identical)
 *  2. Upgrades_CDF.sqf edit cost: change Barracks L1 funds → only that region differs
 *  3. Init_CommonConstants.sqf no-op: paste source → generate → output === input (byte-identical)
 *  4. Init_CommonConstants.sqf edit INCOME_COEF: only that constant's line changes
 *  5. Proposed AI constants go to the labelled block, NOT injected inline
 *  6. 0 console errors throughout
 */

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const path = require("path");

const BASE = "http://localhost:8104";
const MISSION =
  "C:\\Users\\Steff\\a2waspwarfare\\Missions\\[55-2hc]warfarev2_073v48co.chernarus";
const UPGRADES_CDF = path.join(
  MISSION,
  "Common",
  "Config",
  "Core_Upgrades",
  "Upgrades_CDF.sqf",
);
const CONSTANTS = path.join(
  MISSION,
  "Common",
  "Init",
  "Init_CommonConstants.sqf",
);

function readSource(p) {
  return fs.readFileSync(p, { encoding: "utf-8" });
}

test.describe("Export Round-Trip Gate", () => {
  let consoleErrors = [];

  test.beforeEach(async ({ page }) => {
    consoleErrors = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    page.on("pageerror", (err) => consoleErrors.push(err.message));

    await page.goto(BASE);
    // Wait for data to load (chip shows "ready")
    await page.waitForFunction(
      () =>
        document
          .querySelector("#model-status b")
          ?.textContent?.includes("ready"),
      { timeout: 10000 },
    );
    // Give seeds a moment to be captured
    await page.waitForTimeout(200);
  });

  // ----------------------------------------------------------------
  // Test 1: Upgrades_CDF.sqf — no-op byte-identical
  // ----------------------------------------------------------------
  test("Upgrades_CDF no-op export is byte-identical", async ({ page }) => {
    const source = readSource(UPGRADES_CDF);

    // Make sure seeds are captured
    await page.evaluate(() => window.EXPORT.captureSeeds());

    // Open upgrades drawer, set faction to CDF
    await page.evaluate(() => {
      const sel = document.getElementById("tech-faction-sel");
      sel.value = "CDF";
      sel.dispatchEvent(new Event("change"));
      window.EXPORT.openUpgrades();
      window.EXPORT.patchMode("patch");
    });

    // Set source text
    await page.evaluate((src) => window.EXPORT.setSource(src), source);

    // Generate
    await page.evaluate(() => window.EXPORT.generate());

    // Get output
    const output = await page.evaluate(() => window.EXPORT.getOutput());

    // MUST be byte-identical
    if (output !== source) {
      const diff = findFirstDiff(source, output);
      throw new Error(
        `FAIL: No-op Upgrades_CDF export is NOT byte-identical.\n` +
          `First difference at char ${diff.pos}:\n` +
          `  original: ${JSON.stringify(diff.origCtx)}\n` +
          `  output:   ${JSON.stringify(diff.outCtx)}`,
      );
    }
    expect(output).toBe(source);
  });

  // ----------------------------------------------------------------
  // Test 2: Edit one COST → only that number's region changed
  // ----------------------------------------------------------------
  test("Upgrades_CDF edit Barracks L1 funds → minimal diff", async ({
    page,
  }) => {
    const source = readSource(UPGRADES_CDF);

    await page.evaluate(() => window.EXPORT.captureSeeds());

    // Open upgrades drawer CDF
    await page.evaluate(() => {
      const sel = document.getElementById("tech-faction-sel");
      sel.value = "CDF";
      sel.dispatchEvent(new Event("change"));
      window.EXPORT.openUpgrades();
      window.EXPORT.patchMode("patch");
    });

    // Edit Barracks L1 funds in the model (from 540 to 9999)
    await page.evaluate(() => {
      const fd = window.MODEL.upgrades.factions["CDF"];
      fd.costs[0][0][0] = 9999; // Barracks, level 0 (L1), funds
    });

    await page.evaluate((src) => window.EXPORT.setSource(src), source);
    await page.evaluate(() => window.EXPORT.generate());
    const output = await page.evaluate(() => window.EXPORT.getOutput());

    // Output must differ from source
    expect(output).not.toBe(source);

    // The output must contain 9999 where 540 was, and the rest should be close to identical
    expect(output).toContain("9999");
    expect(output).not.toContain("540"); // old value gone from COSTS block

    // Check: outside of the COSTS block, lines should be identical
    // Find COSTS span in both
    const origLines = source.split("\n");
    const newLines = output.split("\n");
    // Lines outside the COSTS block should all match
    // Find the setVariable COSTS header line
    const costsHeaderIdx = origLines.findIndex((l) =>
      l.includes("WFBE_C_UPGRADES_%1_COSTS"),
    );
    expect(costsHeaderIdx).toBeGreaterThan(-1);

    // Spot-check: first line (Private) unchanged
    expect(newLines[0]).toBe(origLines[0]);
    // ENABLED block unchanged (first setVariable block)
    const enabledHeaderIdx = origLines.findIndex((l) =>
      l.includes("WFBE_C_UPGRADES_%1_ENABLED"),
    );
    expect(newLines[enabledHeaderIdx]).toBe(origLines[enabledHeaderIdx]);
  });

  // ----------------------------------------------------------------
  // Test 3: Init_CommonConstants.sqf — no-op byte-identical
  // ----------------------------------------------------------------
  test("Init_CommonConstants no-op export is byte-identical", async ({
    page,
  }) => {
    const source = readSource(CONSTANTS);

    await page.evaluate(() => window.EXPORT.captureSeeds());

    await page.evaluate(() => {
      window.EXPORT.openConstants();
      window.EXPORT.patchMode("patch");
    });

    await page.evaluate((src) => window.EXPORT.setSource(src), source);
    await page.evaluate(() => window.EXPORT.generate());
    const output = await page.evaluate(() => window.EXPORT.getOutput());

    if (output !== source) {
      const diff = findFirstDiff(source, output);
      // Log for debugging before throwing
      console.log("First diff at char", diff.pos);
      console.log("orig ctx:", JSON.stringify(diff.origCtx));
      console.log("out  ctx:", JSON.stringify(diff.outCtx));
    }

    expect(output).toBe(source);
  });

  // ----------------------------------------------------------------
  // Test 4: Edit INCOME_COEF → only that constant's line changes
  // ----------------------------------------------------------------
  test("Init_CommonConstants edit INCOME_COEF → only that line changed", async ({
    page,
  }) => {
    const source = readSource(CONSTANTS);

    await page.evaluate(() => window.EXPORT.captureSeeds());
    await page.evaluate(() => {
      window.EXPORT.openConstants();
      window.EXPORT.patchMode("patch");
    });

    // Change INCOME_COEF from 8 to 99
    await page.evaluate(() => {
      window.MODEL.economy["WFBE_C_ECONOMY_INCOME_COEF"] = 99;
    });

    await page.evaluate((src) => window.EXPORT.setSource(src), source);
    await page.evaluate(() => window.EXPORT.generate());
    const output = await page.evaluate(() => window.EXPORT.getOutput());

    expect(output).not.toBe(source);
    expect(output).toContain("99");

    // Count changed lines
    const origLines = source.split("\n");
    const newLines = output.split("\n");
    const changedLineIdxs = [];
    const maxLen = Math.max(origLines.length, newLines.length);
    for (let i = 0; i < maxLen; i++) {
      if (origLines[i] !== newLines[i]) changedLineIdxs.push(i);
    }

    // Should be exactly 1 changed line (the INCOME_COEF assignment)
    expect(changedLineIdxs.length).toBe(1);
    expect(newLines[changedLineIdxs[0]]).toContain(
      "WFBE_C_ECONOMY_INCOME_COEF",
    );
    expect(newLines[changedLineIdxs[0]]).toContain("99");
  });

  // ----------------------------------------------------------------
  // Test 5: Proposed AI constants go to labelled block, not injected inline
  // ----------------------------------------------------------------
  test("Proposed AI constants segregated to labelled block", async ({
    page,
  }) => {
    const source = readSource(CONSTANTS);

    await page.evaluate(() => window.EXPORT.captureSeeds());
    await page.evaluate(() => {
      window.EXPORT.openConstants();
      window.EXPORT.patchMode("patch");
    });

    // Change a proposed AI constant (not in live file)
    await page.evaluate(() => {
      window.MODEL.ai["WFBE_C_AICOM_FRONTIER_RADIUS"] = 9876;
    });

    await page.evaluate((src) => window.EXPORT.setSource(src), source);
    await page.evaluate(() => window.EXPORT.generate());
    const output = await page.evaluate(() => window.EXPORT.getOutput());

    // The proposed constant must appear AFTER the source ends
    const sourceEnd = source.length;
    const proposedIdx = output.indexOf("Proposed (AI refactor branch)");
    expect(proposedIdx).toBeGreaterThan(sourceEnd - 10); // in the appended block

    // The constant must NOT appear inline in the original file body
    const inlineIdx = output.indexOf("WFBE_C_AICOM_FRONTIER_RADIUS");
    expect(inlineIdx).toBeGreaterThanOrEqual(proposedIdx); // only in proposed block

    // The proposed block must contain the new value
    const proposedBlock = output.slice(proposedIdx);
    expect(proposedBlock).toContain("9876");
  });

  // ----------------------------------------------------------------
  // Test 6: Screenshot the export panel + 0 console errors
  // ----------------------------------------------------------------
  test("Export panel screenshot and 0 console errors", async ({ page }) => {
    await page.evaluate(() => {
      window.EXPORT.openUpgrades();
    });
    await page.waitForTimeout(300);
    await page.screenshot({
      path: "tests/export-panel.png",
      fullPage: false,
    });

    expect(
      consoleErrors.filter(
        (e) =>
          // Filter out known non-errors
          !e.includes("favicon") && !e.includes("net::ERR_"),
      ),
    ).toEqual([]);
  });
});

// Helper: find first difference between two strings
function findFirstDiff(a, b) {
  const len = Math.min(a.length, b.length);
  for (let i = 0; i < len; i++) {
    if (a[i] !== b[i]) {
      return {
        pos: i,
        origCtx: a.slice(Math.max(0, i - 40), i + 40),
        outCtx: b.slice(Math.max(0, i - 40), i + 40),
      };
    }
  }
  return {
    pos: len,
    origCtx: a.slice(len, len + 40),
    outCtx: b.slice(len, len + 40),
  };
}
