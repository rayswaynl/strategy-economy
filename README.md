# Strategy & Economy Editor

A browser-based, offline, single-file **balance & strategy tuner** for Arma 2 **WASP "Warfare"** — part of the [Miksuu's Warfare tools](https://miksuu.com/tools) suite (sibling to [WDDM](https://github.com/rayswaynl/WDDM), [Loadout Lab](https://github.com/rayswaynl/loadout-lab), [Sector & Town Planner](https://github.com/rayswaynl/sector-planner)).

**▶ Live: https://rayswaynl.github.io/strategy-economy/**

## What it does

Tune the whole WASP economy, tech-tree, and AI commander in one place — three **linked** panels that share data the way the mission does at runtime:

- **Tech-Tree** — the 22 upgrades per faction: per-level cost `[funds, supply]`, research time, prerequisites, and the AI's upgrade queue (`AI_ORDER`).
- **Economy** — starting funds/supply, the income engine (`income = ΣtownSV × coef`), supply caps, unit/structure/support prices, anti-stack tuning.
- **AI Commander** — budget seed, spearhead targeting weights, decision intervals, bootstrap stipend, artillery.

The point is the **cross-links**: the AI's queue *is* the Tech-Tree's `AI_ORDER`; the artillery-cooldown array is shared by all three; the AI's starting budget is derived from the Economy's starting funds. Edit one, the linked values update live — with formula previews (income, AI seed, affordability).

## Output

Paste your `Upgrades_<faction>.sqf` and/or `Init_CommonConstants.sqf` → the tool patches **only the values you changed** in place and gives you the file back (a no-op edit returns it byte-for-byte identical — only touched constants/arrays differ). Or, in seeded mode, copy a change-list of the edited lines. AI tunables that live in the AI-commander refactor branch (not the live file) are emitted in a clearly-labelled "proposed" block, never injected silently.

## Unique core

Where the sibling tools edit space (footprints, maps) or kit, this one edits **systems** — a cross-referenced balance model with live math, not a spatial or list editor.

## License

Unofficial, non-commercial reference tool for mission development. Arma 2 / WASP config © **Bohemia Interactive** / WFBE authors.
