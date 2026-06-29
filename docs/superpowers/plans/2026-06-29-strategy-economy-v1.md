# Strategy & Economy Editor v1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

**Goal:** A single-file offline tuner for WASP's **tech-tree + economy + AI-commander**, as three **linked** panels that share data, with live formula previews, exporting paste-ready config blocks.

**Architecture:** Python generators parse the WASP config → seed JSON; `index.html` (vanilla JS, WDDM dark theme) renders 3 panels with cross-links + export.

**Tech Stack:** Python 3.12 (stdlib); vanilla JS/CSS; Playwright. **Reuse** WDDM/Loadout Lab tokens (gunmetal `#14171B`, steel, olive, orange `#D9763C`, bone; Oswald/Inter/JetBrains Mono) + the validation/picker patterns.

## Source files (read-only) — base = `C:\Users\Steff\a2waspwarfare\Missions\[55-2hc]warfarev2_073v48co.chernarus`
- `Common\Init\Init_CommonConstants.sqf` — **the central file**: upgrade ID constants (`WFBE_UP_*` = 0..21), ALL economy + AI + balance constants.
- `Common\Config\Core_Upgrades\Upgrades_<F>.sqf` — per-faction upgrade data. Factions `<F>`: CDF, RU, US, USMC, GUE, INS, CO_US, CO_RU, CO_GUE, OA_TKA, OA_TKGUE.
- `Common\Config\Core_Upgrades\Labels_Upgrades.sqf` — global `WFBE_C_UPGRADES_LABELS` (22 strings).
- `Common\Config\Core\Core_<F>.sqf` — unit prices `classname → [label,pic,price,buildTime,crew,upgradeLevel,factory,isVeh,faction,turrets]` (price idx 2, upgrade idx 5).
- `Common\Config\Core_Structures\Structures_<F>.sqf` — structure supply-costs.

## Grounding — data structures (verbatim shapes)
**(A) Tech-Tree** — per faction, six arrays keyed by side (set via `missionNamespace setVariable [format["WFBE_C_UPGRADES_%1_<KIND>",_side], [...]]`):
- `ENABLED` `[bool×22]`; `LEVELS` `[int×22]` (max level per upgrade); `COSTS` `[ [[funds,supply],…per level], …×22 ]`; `TIMES` `[ [secs…per level], …×22 ]`; `LINKS` `[ [ [prereqId,reqLvl],… per level ], …×22 ]`; `AI_ORDER` `[ [upgradeId,level], … ]` (ordered AI research queue).
- Example (CDF): Barracks(0) COSTS `[[540,0],[1350,0],[2070,0]]`; Heavy(2) `[[1200,0],[4400,0],[9500,0],[10500,0]]`; ICBM(11) `[[49500,80000]]`. Upgrade IDs 0..21 = BARRACKS,LIGHT,HEAVY,AIR,PARATROOPERS,UAV,SUPPLYRATE,RESPAWNRANGE,AIRLIFT,FLARESCM,ARTYTIMEOUT,ICBM,FASTTRAVEL,GEAR,AMMOCOIN,EASA,SUPPLYPARADROP,ARTYAMMO,IRSMOKE,AIRAAM,AAR,UNITCOST.

**(B) Economy** — bare/`isNil`-guarded scalars + arrays in `Init_CommonConstants.sqf`:
- Starting: `WFBE_C_ECONOMY_FUNDS_START_{WEST,EAST,GUER}`, `..._SUPPLY_START_{...}`. Income: `..._INCOME_INTERVAL=60`, `..._INCOME_SYSTEM=3`, `..._INCOME_COEF=8`, `..._INCOME_DIVIDED=1.2`, `..._INCOME_PERCENT_MAX=30`, `..._SUPPLY_MAX_TEAM_LIMIT=50000`, `WFBE_C_MAX_ECONOMY_SUPPLY_LIMIT=40000`. Arrays: `WFBE_C_ARTILLERY_INTERVALS=[550,500,…,250]`, `WFBE_C_RESPAWN_RANGES=[250,350,500]`, `WFBE_C_TOWNS_SUPPLY_LEVELS_TIME=[1..5]`, `..._TRUCK=[5,6,7,8,10]`. Support prices `WFBE_C_UNITS_SUPPORT_{HEAL,REARM,REFUEL,REPAIR}_PRICE`, `..._CREW_COST`, `WFBE_C_PLAYERS_GEAR_SELL_COEF=0.6`. HQ repair `WFBE_C_BASE_HQ_REPAIR_PRICE_{1ST,2ND,3RD,CASH}`. Structure caps `WFBE_C_STRUCTURES_MAX*`. Anti-stack `TEAM_SKILL_TICKS_*`, `PLAYER_NUMBER_DIFFERENCE_MODIFIER`, etc. Income formula (preview): `income = round(ΣtownSV × INCOME_COEF)`.

**(C) AI Commander** — constants in `Init_CommonConstants.sqf`: `WFBE_C_AI_COMMANDER_ENABLED`, `WFBE_C_AI_MAX`, `..._MOVE_INTERVALS`, `..._SUPPLY_TRUCKS_MAX`, `WFBE_C_AI_PATROL_RANGE`, `WFBE_C_AI_TOWN_ATTACK_HOPS_WP`, the `WFBE_C_AICOM_*` spearhead params (FRONTIER_RADIUS, DISTANCE_DIVISOR, HQ_PULL_DIVISOR, FAR_PENALTY, SPEARHEAD_TOWNS_MAX), bootstrap (`..._BOOTSTRAP_{MAXTIME,FUNDS,SUPPLY}`), `WFBE_C_AI_COMMANDER_{STRATEGY,BASE,TEAMS}_INTERVAL`, `..._BUILD_GRACE`, `..._ARTILLERY`, `..._LOCK`, `..._FUNDS_PER_EXTRA_TEAM`, `..._TEAMS_TARGET`, `..._RELIEF_MAX`. AI fund seed = `FUNDS_START_{side} × 1.5` (in `Server\Init\Init_Server.sqf`). NOTE: a few strategy ratios (HQ-hunt `1.5/1.1/1.2`) are HARDCODED in `AI_Commander.sqf` — expose as **display-only** in v1 (extracting them is a v2 code change).

**Cross-links (the linked-panel value):** `AI_ORDER` (A) = AI's queue (C); `ARTILLERY_INTERVALS`/`RESPAWN_RANGES`/`SUPPLY_LEVELS_*` (B) drive A's upgrade labels + C's gates; `FUNDS_START` (B) → AI seed `×1.5` (C); unit `upgradeLevel` (Core_*) ↔ A's factory upgrades. The tool surfaces these (edit one → linked value/preview updates).

---

## Task 1: Generators — parse config → seed JSON
**Files:** `tools/extract_strategy.py`, `tools/test_extract_strategy.py`.
- [ ] **Step 1: tests** (inline fixtures): parse the upgrade ID constants; parse one `missionNamespace setVariable [..._COSTS,[...]]` block → nested arrays; parse a scalar `VAR = 8;` and an `if (isNil "VAR") then {VAR = 800}`; parse an array constant `WFBE_C_ARTILLERY_INTERVALS=[...]`.
- [ ] **Step 2-3: implement** `extract_strategy`: (a) `upgrade_ids` from `Init_CommonConstants.sqf` (`WFBE_UP_*`); (b) per faction, the 6 `WFBE_C_UPGRADES_%1_*` arrays from `Upgrades_<F>.sqf` → `{enabled,levels,costs,times,links,ai_order}`; (c) labels from `Labels_Upgrades.sqf`; (d) ALL economy + AI scalars/arrays from `Init_CommonConstants.sqf` (handle both `VAR=…` and `isNil`-guarded forms). Robust SQF value parsing (nested `[]`, numbers, bools).
- [ ] **Step 4-5: run** → `assets/data/`: `upgrades.json` (`{ids:{NAME:idx}, labels:[…], factions:{CDF:{enabled,levels,costs,times,links,ai_order}, …}}`), `economy.json` (named constants → value), `ai.json` (named AI constants → value, + the hardcoded-ratios noted as `_displayOnly`). Sanity: 22 upgrade ids; CDF Barracks costs `[[540,0],[1350,0],[2070,0]]`; INCOME_COEF=8; FUNDS_START_WEST=800. **Step 6: commit** `feat(tools): parse WASP upgrades + economy + AI constants -> seed JSON`.

## Task 2: Shell + Panel B (Economy)
**Files:** `index.html`.
- [ ] Shell: WDDM tokens/brand bar (retitle "STRATEGY & ECONOMY"); a 3-tab/3-section layout (Tech-Tree · Economy · AI Commander) + a shared export bar. Fetch the 3 JSONs.
- [ ] Panel B: grouped editable fields for every economy constant (starting funds/supply per side; income system/interval/coef/divisor/%max; supply caps; support prices; HQ repair; structure caps; anti-stack). Inputs typed (number/select/array-of-numbers). A live **income preview** (`income = ΣtownSV × coef`, with a sample town-SV input). Edits mutate the model.
- [ ] Verify (Playwright 8101): 0 errors; every economy field renders + edits; income preview updates. Screenshot. Commit `feat: shell + economy panel`.

## Task 3: Panel A (Tech-Tree) + AI_ORDER
**Files:** `index.html`.
- [ ] Faction selector → loads that faction's upgrade data. For each of 22 upgrades: enable toggle, max-level, and a per-level grid of cost `[funds,supply]` + research time; prerequisite editor (`links`: pick other upgradeId + reqLevel per level). Labels from `labels`.
- [ ] AI_ORDER editor: an ordered list of `[upgradeId, level]` (add/remove/reorder). 
- [ ] Verify (Playwright): switch factions; edit a cost/level/prereq; edit AI_ORDER; 0 errors. Screenshot. Commit `feat: tech-tree panel + AI upgrade queue`.

## Task 4: Panel C (AI Commander) + cross-links + previews
**Files:** `index.html`.
- [ ] Panel C: editable fields for every AI constant (enable/lock/grace, intervals, spearhead weights, bootstrap, artillery, team params, fund-seed ×1.5). The hardcoded HQ-hunt ratios shown **display-only** with a note.
- [ ] **Cross-links**: AI_ORDER shown in C is the SAME data as A (edit in either, reflected in both); show `ARTILLERY_INTERVALS`/`RESPAWN_RANGES` as shared (a badge "shared with Economy"); compute the **AI seed preview** = `FUNDS_START_side × 1.5` live from Panel B; an **affordability hint** per AI_ORDER entry ("AI affords Barracks L1 at ~X funds"). 
- [ ] Verify (Playwright): edit FUNDS_START in B → AI seed preview in C updates; edit AI_ORDER in A → reflected in C; 0 errors. Screenshot. Commit `feat: AI panel + cross-panel links + previews`.

## Task 5: Export (regenerate config + round-trip gate)
**Files:** `index.html`.
- [ ] Export `Upgrades_<faction>.sqf`: regenerate the 6 `setVariable` blocks from the model in the file's exact format. Export the `Init_CommonConstants.sqf` economy+AI blocks (regenerate the changed constant lines/arrays). Provide copy + download.
- [ ] **Round-trip gate (Playwright)**: load seed → export with NO edits → the regenerated values parse back equal to the seed (semantic round-trip; for the constants, the emitted lines re-parse to the same values). Edit one cost → only that value differs. Change-list export option. Commit `feat: export Upgrades_*.sqf + Init_CommonConstants blocks + round-trip`.

## Task 6: Verify + finish + deploy + tile
- [ ] generator tests pass; full Playwright smoke (3 panels, cross-links, export round-trip); 0 errors; screenshots.
- [ ] README usage; commit. Controller: merge `feat/v1`→main, push, enable Pages, verify live.
- [ ] Controller: add tile to miksuu hub (`tools.ts`: `{slug:"strategy-economy", name:"Strategy & Economy", description:"…", url:"https://rayswaynl.github.io/strategy-economy/"}`); **user approves the miksuu deploy**.

## Self-Review
- 3 linked panels (A/B/C) → Tasks 2-4; cross-links + previews = the unique core → Task 4; export + round-trip → Task 5; deploy+tile → Task 6.
- AI hardcoded ratios = display-only (honest scope); per-faction upgrades + global economy/AI; regenerate config blocks as output.
