"""
extract_strategy.py  —  parse WASP config files → seed JSON for Strategy & Economy editor.

Usage:
    python tools/extract_strategy.py --mission <mission-dir> [--out <output-dir>]

Outputs (in <output-dir>, default assets/data/):
    upgrades.json  — {ids, labels, factions}
    economy.json   — economy constants
    ai.json        — AI commander constants

Python 3.12, stdlib only.
"""

import argparse
import json
import os
import re
import sys

# ---------------------------------------------------------------------------
# SQF value parser
# ---------------------------------------------------------------------------

def strip_sqf_comments(text: str) -> str:
    """Remove // line comments and /* … */ block comments from SQF text."""
    # Block comments first
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Line comments
    text = re.sub(r'//[^\n]*', '', text)
    return text


def parse_sqf_value(text: str, pos: int = 0):
    """
    Parse a single SQF value starting at *pos* in *text*.
    Returns (value, end_pos).

    Supported:
      [...]          → list
      "..."          → str (raw token, escape \" handled)
      true / false   → bool
      integer        → int
      float          → float
    """
    # Skip whitespace
    while pos < len(text) and text[pos] in ' \t\r\n':
        pos += 1

    if pos >= len(text):
        raise ValueError("Unexpected end of input while parsing SQF value")

    ch = text[pos]

    # Array
    if ch == '[':
        return _parse_array(text, pos)

    # String
    if ch == '"':
        return _parse_string(text, pos)

    # Boolean / keyword
    m = re.match(r'(true|false|nil)\b', text[pos:], re.IGNORECASE)
    if m:
        tok = m.group(1).lower()
        if tok == 'true':
            return True, pos + m.end()
        if tok == 'false':
            return False, pos + m.end()
        return None, pos + m.end()

    # Number (int or float, possibly negative)
    m = re.match(r'-?\d+\.\d*([eE][+-]?\d+)?|-?\.\d+([eE][+-]?\d+)?|-?\d+([eE][+-]?\d+)?', text[pos:])
    if m:
        raw = m.group(0)
        end = pos + m.end()
        if '.' in raw or 'e' in raw.lower():
            return float(raw), end
        return int(raw), end

    raise ValueError(f"Cannot parse SQF value at pos {pos}: ...{text[pos:pos+40]!r}...")


def _parse_string(text: str, pos: int):
    """Parse a quoted SQF string (double-quote, "" escapes)."""
    assert text[pos] == '"'
    pos += 1
    buf = []
    while pos < len(text):
        ch = text[pos]
        if ch == '"':
            # "" → single " (SQF style), else end of string
            if pos + 1 < len(text) and text[pos + 1] == '"':
                buf.append('"')
                pos += 2
            else:
                pos += 1
                break
        elif ch == '\\':
            # Handle \", \\, etc.
            if pos + 1 < len(text):
                buf.append(text[pos + 1])
                pos += 2
            else:
                pos += 1
        else:
            buf.append(ch)
            pos += 1
    return ''.join(buf), pos


def _parse_array(text: str, pos: int):
    """Parse a SQF array [...], returning (list, end_pos)."""
    assert text[pos] == '['
    pos += 1
    items = []
    # skip whitespace
    while pos < len(text) and text[pos] in ' \t\r\n':
        pos += 1

    if pos < len(text) and text[pos] == ']':
        return items, pos + 1

    while pos < len(text):
        # skip whitespace
        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1

        if pos >= len(text):
            break

        if text[pos] == ']':
            pos += 1
            break

        value, pos = parse_sqf_value(text, pos)
        items.append(value)

        # skip whitespace
        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1

        if pos < len(text) and text[pos] == ',':
            pos += 1
        elif pos < len(text) and text[pos] == ']':
            pos += 1
            break

    return items, pos


# ---------------------------------------------------------------------------
# Upgrade ID constants  (WFBE_UP_* = N)
# ---------------------------------------------------------------------------

def parse_upgrade_ids(text: str) -> dict:
    """
    Extract WFBE_UP_* = <int> assignments.
    Returns dict mapping name-without-prefix to integer index,
    e.g. {"BARRACKS": 0, "LIGHT": 1, ...}
    """
    ids = {}
    # Match bare assignment: WFBE_UP_NAME = N;
    for m in re.finditer(r'\bWFBE_UP_([A-Z0-9_]+)\s*=\s*(\d+)\s*;', text):
        ids[m.group(1)] = int(m.group(2))
    return ids


# ---------------------------------------------------------------------------
# Faction upgrade arrays
# ---------------------------------------------------------------------------

# Lookup table of WFBE_UP_* names to indices (populated from the constants file).
_UP_CONST_RE = re.compile(r'\bWFBE_UP_([A-Z0-9_]+)\b')

def _resolve_up_refs(value, up_ids: dict):
    """
    Recursively replace WFBE_UP_NAME string tokens in a parsed structure with
    their integer values.  During parsing of SQF the LINKS array contains
    strings like "WFBE_UP_BARRACKS" that we could not resolve as numbers.
    We instead capture them as strings during SQF parse and fix them up here.
    """
    if isinstance(value, str) and value.startswith('WFBE_UP_'):
        name = value[len('WFBE_UP_'):]
        return up_ids.get(name, value)
    if isinstance(value, list):
        return [_resolve_up_refs(v, up_ids) for v in value]
    return value


def _parse_sqf_value_with_up_names(text: str, pos: int, up_ids: dict):
    """
    Like parse_sqf_value but when we encounter a bare WFBE_UP_* identifier
    (not a number, not a string, not a bool) we return the integer from up_ids.
    """
    # Skip whitespace
    while pos < len(text) and text[pos] in ' \t\r\n':
        pos += 1

    if pos >= len(text):
        raise ValueError("Unexpected end of input")

    ch = text[pos]

    if ch == '[':
        return _parse_array_with_up_names(text, pos, up_ids)

    if ch == '"':
        return _parse_string(text, pos)

    # Boolean
    m = re.match(r'(true|false|nil)\b', text[pos:], re.IGNORECASE)
    if m:
        tok = m.group(1).lower()
        if tok == 'true':
            return True, pos + m.end()
        if tok == 'false':
            return False, pos + m.end()
        return None, pos + m.end()

    # WFBE_UP_ identifier
    m = re.match(r'WFBE_UP_([A-Z0-9_]+)', text[pos:])
    if m:
        name = m.group(1)
        idx = up_ids.get(name, -1)
        return idx, pos + m.end()

    # Number
    m = re.match(r'-?\d+\.\d*([eE][+-]?\d+)?|-?\.\d+([eE][+-]?\d+)?|-?\d+([eE][+-]?\d+)?', text[pos:])
    if m:
        raw = m.group(0)
        end = pos + m.end()
        if '.' in raw or 'e' in raw.lower():
            return float(raw), end
        return int(raw), end

    raise ValueError(f"Cannot parse value at pos {pos}: ...{text[pos:pos+40]!r}...")


def _parse_array_with_up_names(text: str, pos: int, up_ids: dict):
    assert text[pos] == '['
    pos += 1
    items = []
    while pos < len(text) and text[pos] in ' \t\r\n':
        pos += 1

    if pos < len(text) and text[pos] == ']':
        return items, pos + 1

    while pos < len(text):
        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1

        if pos >= len(text):
            break
        if text[pos] == ']':
            pos += 1
            break

        value, pos = _parse_sqf_value_with_up_names(text, pos, up_ids)
        items.append(value)

        while pos < len(text) and text[pos] in ' \t\r\n':
            pos += 1

        if pos < len(text) and text[pos] == ',':
            pos += 1
        elif pos < len(text) and text[pos] == ']':
            pos += 1
            break

    return items, pos


def _extract_setvar_value(text: str, kind_token: str, up_ids: dict):
    """
    Find the array literal assigned to WFBE_C_UPGRADES_%1_<kind_token>
    via missionNamespace setVariable [Format[...], [...]].

    The format call has the variable name in the first string arg and the
    value array as the second element of the outer array.

    Pattern:
        missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_KIND", _side], [
            ...
        ]];

    We find the matching closing bracket pair robustly.
    """
    # Match the keyword within the format string (case-insensitive)
    pat = re.compile(
        r'missionNamespace\s+setVariable\s*\[\s*'
        r'Format\s*\[\s*"WFBE_C_UPGRADES_%1_' + re.escape(kind_token) + r'"\s*,[^\]]*\]\s*,\s*'
        r'(\[)',
        re.IGNORECASE | re.DOTALL
    )
    m = pat.search(text)
    if not m:
        return None

    # m.start(1) is the position of the opening '[' of the value array
    array_start = m.start(1)

    if kind_token.upper() in ('LINKS', 'AI_ORDER'):
        val, _ = _parse_array_with_up_names(text, array_start, up_ids)
    else:
        val, _ = _parse_array(text, array_start)

    return val


def _resolve_enabled_array(raw: list) -> list:
    """
    ENABLED arrays contain Python True/False (from parsed 'true'/'false')
    but also None where we couldn't parse complex SQF expressions.
    Normalize: True→True, False→False, None→None (unknown; keep as null).
    """
    # Already parsed by _parse_enabled_array below
    return raw


def _parse_enabled_array(text: str) -> list:
    """
    The ENABLED array mixes true/false literals with complex SQF if-then-else
    expressions that depend on runtime state.  We parse what we can and fall
    back to None for complex expressions.

    Strategy: strip the outer array brackets, split on top-level commas,
    classify each element.
    """
    pat = re.compile(
        r'missionNamespace\s+setVariable\s*\[\s*'
        r'Format\s*\[\s*"WFBE_C_UPGRADES_%1_ENABLED"\s*,[^\]]*\]\s*,\s*'
        r'(\[)',
        re.IGNORECASE | re.DOTALL
    )
    m = pat.search(text)
    if not m:
        return []

    # Find the matching ']' for the outer array
    start = m.start(1)
    depth = 0
    end = start
    for i in range(start, len(text)):
        if text[i] == '[':
            depth += 1
        elif text[i] == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = text[start + 1:end]

    # Split on top-level commas
    items = []
    depth = 0
    buf = []
    for ch in inner:
        if ch in '([{':
            depth += 1
            buf.append(ch)
        elif ch in ')]}':
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            items.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        items.append(''.join(buf).strip())

    result = []
    for item in items:
        item_clean = item.strip()
        if item_clean.lower() == 'true':
            result.append(True)
        elif item_clean.lower() == 'false':
            result.append(False)
        else:
            # Complex expression — use None to mean "runtime-determined"
            result.append(None)
    return result


def parse_faction_upgrades(text: str, up_ids: dict) -> dict:
    """
    Parse all six WFBE_C_UPGRADES_%1_<KIND> arrays from a faction file.
    Returns dict: {enabled, levels, costs, times, links, ai_order}
    """
    clean = strip_sqf_comments(text)
    enabled = _parse_enabled_array(clean)
    levels = _extract_setvar_value(clean, 'LEVELS', up_ids)
    costs = _extract_setvar_value(clean, 'COSTS', up_ids)
    times = _extract_setvar_value(clean, 'TIMES', up_ids)
    links = _extract_setvar_value(clean, 'LINKS', up_ids)
    ai_order = _extract_setvar_value(clean, 'AI_ORDER', up_ids)

    return {
        'enabled': enabled or [],
        'levels': levels or [],
        'costs': costs or [],
        'times': times or [],
        'links': links or [],
        'ai_order': ai_order or [],
    }


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def parse_labels(text: str) -> list:
    """
    Extract WFBE_C_UPGRADES_LABELS array.
    Labels may be  localize 'STR_...'  or bare strings.
    We capture the raw token (localize key or literal string).
    """
    clean = strip_sqf_comments(text)

    # Find the setVariable for WFBE_C_UPGRADES_LABELS (no %1 in the key)
    pat = re.compile(
        r'missionNamespace\s+setVariable\s*\[\s*'
        r'Format\s*\[\s*"WFBE_C_UPGRADES_LABELS"\s*\]\s*,\s*'
        r'(\[)',
        re.IGNORECASE | re.DOTALL
    )
    m = pat.search(clean)
    if not m:
        # Try simpler form without Format wrapper
        pat2 = re.compile(
            r'missionNamespace\s+setVariable\s*\[\s*'
            r'"WFBE_C_UPGRADES_LABELS"\s*,\s*(\[)',
            re.IGNORECASE | re.DOTALL
        )
        m = pat2.search(clean)

    if not m:
        return []

    # Find the matching ']' for the array
    start = m.start(1)
    depth = 0
    end = start
    for i in range(start, len(clean)):
        if clean[i] == '[':
            depth += 1
        elif clean[i] == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
    inner = clean[start + 1:end]

    labels = []
    # Each element is either:
    #   localize 'STR_...'
    #   localize "STR_..."
    #   'EASA'  (bare single-quoted string in SQF)
    #   "EASA"  (bare double-quoted)
    # Split on top-level commas
    depth = 0
    buf = []
    for ch in inner:
        if ch in '([{':
            depth += 1
            buf.append(ch)
        elif ch in ')]}':
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            labels.append(''.join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        labels.append(''.join(buf).strip())

    result = []
    for lbl in labels:
        lbl = lbl.strip()
        # localize 'STR_...' or localize "STR_..."
        m2 = re.match(r"localize\s+['\"]([^'\"]+)['\"]", lbl, re.IGNORECASE)
        if m2:
            result.append(m2.group(1))
            continue
        # bare double-quoted string
        m3 = re.match(r'"([^"]*)"', lbl)
        if m3:
            result.append(m3.group(1))
            continue
        # bare single-quoted string (SQF also supports this)
        m4 = re.match(r"'([^']*)'", lbl)
        if m4:
            result.append(m4.group(1))
            continue
        # Unknown
        result.append(lbl)

    return result


# ---------------------------------------------------------------------------
# Constants (economy + AI) — both VAR=N; and isNil-guarded forms
# ---------------------------------------------------------------------------

# Prefixes that count as "AI" constants
_AI_PREFIXES = (
    'WFBE_C_AI_',
    'WFBE_C_AICOM_',
)

# Allowed name prefixes to capture
_CAPTURE_PREFIXES = (
    'WFBE_C_ECONOMY_',
    'WFBE_C_AI_',
    'WFBE_C_AICOM_',
    'WFBE_C_ARTILLERY_INTERVALS',
    'WFBE_C_RESPAWN_RANGES',
    'WFBE_C_TOWNS_SUPPLY_LEVELS_',
    'WFBE_C_UNITS_SUPPORT_',
    'WFBE_C_UNITS_CREW_COST',
    'WFBE_C_PLAYERS_GEAR_SELL_COEF',
    'WFBE_C_BASE_HQ_REPAIR_',
    'WFBE_C_STRUCTURES_MAX',
    'TEAM_SKILL_TICKS_',
    'PLAYER_NUMBER_DIFFERENCE_MODIFIER',
    'SUPPLY_COMPENSATION_AMOUNT_',
    'TEAM_WEST_TICKS_NO_PLAYERS',
    'TEAM_EAST_TICKS_NO_PLAYERS',
    'SUPPLY_INCOME_TICK_MODIFIER_MULTIPLIER',
    'WFBE_SUPPLY_MISSION_SCORE_COEF',
    'WFBE_UPGRADE_SCORE_COEF',
    'WFBE_C_MAX_ECONOMY_SUPPLY_LIMIT',
)


def _should_capture(name: str) -> bool:
    for p in _CAPTURE_PREFIXES:
        if name.startswith(p):
            return True
    return False


def _is_ai_const(name: str) -> bool:
    for p in _AI_PREFIXES:
        if name.startswith(p):
            return True
    return False


def _extract_brace_body(text: str, start: int) -> tuple:
    """
    Given *start* pointing at '{', extract the content up to the matching '}'.
    Returns (body_content, pos_after_closing_brace).
    """
    assert text[start] == '{'
    depth = 0
    i = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], len(text)


def _parse_debug_else_value(rhs_text: str):
    """
    Handle: if (WF_Debug) then {...} else {VALUE}
    Returns the parsed Python value from the else branch, or raises ValueError.
    """
    rhs = rhs_text.strip()
    # Match: if (WF_Debug) then {
    head_pat = re.compile(
        r'if\s*\(\s*WF_Debug\s*\)\s+then\s*(\{)',
        re.IGNORECASE
    )
    hm = head_pat.match(rhs)
    if not hm:
        raise ValueError("Not a WF_Debug conditional")

    # Skip the then-body using brace depth tracking
    _, after_then = _extract_brace_body(rhs, hm.start(1))

    # Find 'else' after the then-body
    tail_after_then = rhs[after_then:]
    else_m = re.search(r'\belse\b', tail_after_then, re.IGNORECASE)
    if not else_m:
        raise ValueError("No else branch found")

    # Position in rhs after the 'else' keyword
    after_else_in_tail = else_m.end()
    after_else_abs = after_then + after_else_in_tail

    # Find the opening '{' of the else body
    brace_pos = rhs.find('{', after_else_abs)
    if brace_pos == -1:
        raise ValueError("No else brace")

    else_body, _ = _extract_brace_body(rhs, brace_pos)
    value, _ = parse_sqf_value(else_body.strip(), 0)
    return value


def parse_constants(text: str, names_or_prefixes=None) -> dict:
    """
    Parse scalars and arrays from SQF text.

    Handles:
      VAR = value;
      if (isNil "VAR") then {VAR = value};
      if (isNil "VAR") then {VAR = if (WF_Debug) then {X} else {Y}};
        → captures Y (the non-debug branch)

    Also handles WFBE_C_ARTILLERY_INTERVALS which is inside:
      if WF_Debug then { ... } else { WFBE_C_ARTILLERY_INTERVALS = [...]; }

    Returns {name: value} dict.
    """
    clean = strip_sqf_comments(text)
    result = {}

    # ---- Form 1: bare assignments  VAR = value;
    bare_pat = re.compile(
        r'\b([A-Z][A-Z0-9_]+)\s*=\s*',
        re.IGNORECASE
    )
    for m in bare_pat.finditer(clean):
        name = m.group(1)
        if not _should_capture(name):
            continue
        val_start = m.end()
        try:
            value, val_end = parse_sqf_value(clean, val_start)
            tail = clean[val_end:val_end + 10].lstrip()
            if tail.startswith(';') or tail.startswith(']') or tail.startswith(','):
                if name not in result:
                    result[name] = value
        except Exception:
            pass

    # ---- Form 2: isNil-guarded   if (isNil "VAR") then { ... }
    # We need brace-depth extraction to handle nested braces in the body.
    isnilguard_head = re.compile(
        r'if\s*\(\s*isNil\s+"([A-Z][A-Z0-9_]*)"\s*\)\s+then\s*(\{)',
        re.IGNORECASE
    )
    for m in isnilguard_head.finditer(clean):
        guard_name = m.group(1)
        if not _should_capture(guard_name):
            continue

        brace_start = m.start(2)
        body, _ = _extract_brace_body(clean, brace_start)

        # Find the assignment  VARNAME = <rhs>  inside body
        assign_pat = re.compile(
            r'\b' + re.escape(guard_name) + r'\s*=\s*',
            re.IGNORECASE
        )
        am = assign_pat.search(body)
        if not am:
            continue

        rhs_text = body[am.end():]

        # Try WF_Debug conditional first
        try:
            value = _parse_debug_else_value(rhs_text)
            if guard_name not in result:
                result[guard_name] = value
            continue
        except Exception:
            pass

        # Simple value
        try:
            value, _ = parse_sqf_value(rhs_text, 0)
            if guard_name not in result:
                result[guard_name] = value
        except Exception:
            pass

    # ---- Form 3: WFBE_C_ARTILLERY_INTERVALS inside if WF_Debug then {...} else {...}
    # Find the WF_Debug block pattern and capture the else body.
    debug_block_head = re.compile(
        r'if\s+WF_Debug\s+then\s*(\{)',
        re.IGNORECASE
    )
    for dm in debug_block_head.finditer(clean):
        brace_start = dm.start(1)
        _, after_then = _extract_brace_body(clean, brace_start)

        tail = clean[after_then:].lstrip()
        if not tail.lower().startswith('else'):
            continue

        # Find the else brace
        else_brace_pos = clean.find('{', after_then)
        if else_brace_pos == -1:
            continue
        else_body, _ = _extract_brace_body(clean, else_brace_pos)

        for am in bare_pat.finditer(else_body):
            name = am.group(1)
            if not _should_capture(name):
                continue
            val_start = am.end()
            try:
                value, val_end = parse_sqf_value(else_body, val_start)
                tail2 = else_body[val_end:val_end + 10].lstrip()
                if tail2.startswith(';') or tail2.startswith(']') or tail2.startswith(',') or val_end >= len(else_body) - 5:
                    result[name] = value
            except Exception:
                pass

    # Optional allow-list filter
    if names_or_prefixes:
        result = {k: v for k, v in result.items() if any(k.startswith(p) or k == p for p in names_or_prefixes)}

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _read_file(path: str) -> str:
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def main():
    parser = argparse.ArgumentParser(description='Parse WASP config → seed JSON')
    parser.add_argument('--mission', required=True,
                        help='Path to the mission root directory')
    parser.add_argument('--out', default='assets/data',
                        help='Output directory (default: assets/data)')
    args = parser.parse_args()

    mission_dir = args.mission
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    upgrades_dir = os.path.join(mission_dir, 'Common', 'Config', 'Core_Upgrades')
    constants_file = os.path.join(mission_dir, 'Common', 'Init', 'Init_CommonConstants.sqf')
    labels_file = os.path.join(upgrades_dir, 'Labels_Upgrades.sqf')

    # --- Step 1: upgrade IDs ---
    print(f"Reading constants from: {constants_file}")
    constants_text = _read_file(constants_file)
    up_ids = parse_upgrade_ids(constants_text)
    print(f"  Upgrade IDs found: {len(up_ids)} — {sorted(up_ids.items(), key=lambda x: x[1])}")

    # --- Step 2: labels ---
    print(f"Reading labels from: {labels_file}")
    labels_text = _read_file(labels_file)
    labels = parse_labels(labels_text)
    print(f"  Labels found: {len(labels)}")

    # --- Step 3: per-faction upgrades ---
    factions = {}
    faction_files = [f for f in os.listdir(upgrades_dir)
                     if f.startswith('Upgrades_') and f.endswith('.sqf')]
    faction_files.sort()
    print(f"\nFaction files found: {[os.path.splitext(f)[0].replace('Upgrades_', '') for f in faction_files]}")

    for fname in faction_files:
        faction_name = os.path.splitext(fname)[0].replace('Upgrades_', '')
        fpath = os.path.join(upgrades_dir, fname)
        print(f"  Parsing faction: {faction_name} ({fname})")
        faction_text = _read_file(fpath)
        fdata = parse_faction_upgrades(faction_text, up_ids)
        factions[faction_name] = fdata
        print(f"    enabled={len(fdata['enabled'])} levels={len(fdata['levels'])} "
              f"costs={len(fdata['costs'])} times={len(fdata['times'])} "
              f"links={len(fdata['links'])} ai_order={len(fdata['ai_order'])}")

    upgrades_json = {
        'ids': up_ids,
        'labels': labels,
        'factions': factions,
    }

    # --- Step 4: constants ---
    print(f"\nParsing constants from {constants_file}")
    all_consts = parse_constants(constants_text)
    print(f"  Total constants captured: {len(all_consts)}")

    economy_consts = {k: v for k, v in all_consts.items() if not _is_ai_const(k)}
    ai_consts = {k: v for k, v in all_consts.items() if _is_ai_const(k)}

    # Add display-only hardcoded AI strategy ratios (from AI_Commander.sqf, v2 change)
    ai_consts['_displayOnly_HQ_HUNT_RATIO_ATTACK'] = 1.5
    ai_consts['_displayOnly_HQ_HUNT_RATIO_RETREAT'] = 1.1
    ai_consts['_displayOnly_HQ_HUNT_RATIO_FLANK'] = 1.2

    print(f"  Economy constants: {len(economy_consts)}")
    print(f"  AI constants: {len(ai_consts)}")

    # --- Step 5: write output ---
    upgrades_path = os.path.join(out_dir, 'upgrades.json')
    economy_path = os.path.join(out_dir, 'economy.json')
    ai_path = os.path.join(out_dir, 'ai.json')

    with open(upgrades_path, 'w', encoding='utf-8') as f:
        json.dump(upgrades_json, f, indent=2)
    with open(economy_path, 'w', encoding='utf-8') as f:
        json.dump(economy_consts, f, indent=2)
    with open(ai_path, 'w', encoding='utf-8') as f:
        json.dump(ai_consts, f, indent=2)

    # --- Sanity check ---
    print('\n--- Sanity Check ---')
    print(f"Upgrade ID count: {len(up_ids)} (expected 22)")
    print(f"BARRACKS index: {up_ids.get('BARRACKS')} (expected 0)")
    print(f"UNITCOST index: {up_ids.get('UNITCOST')} (expected 21)")

    if 'CDF' in factions:
        cdf = factions['CDF']
        barracks_costs = cdf['costs'][0] if cdf['costs'] else None
        print(f"CDF Barracks costs: {barracks_costs} (expected [[540,0],[1350,0],[2070,0]])")
        icbm_idx = up_ids.get('ICBM', 11)
        icbm_costs = cdf['costs'][icbm_idx] if len(cdf['costs']) > icbm_idx else None
        print(f"CDF ICBM costs: {icbm_costs} (expected [[49500,80000]])")

    print(f"INCOME_COEF: {economy_consts.get('WFBE_C_ECONOMY_INCOME_COEF')} (expected 8)")
    print(f"FUNDS_START_WEST: {economy_consts.get('WFBE_C_ECONOMY_FUNDS_START_WEST')} (expected 800)")
    print(f"ARTILLERY_INTERVALS: {economy_consts.get('WFBE_C_ARTILLERY_INTERVALS')} (expected [550,500,450,...])")
    print(f"AI_COMMANDER_ENABLED: {ai_consts.get('WFBE_C_AI_COMMANDER_ENABLED')} (expected 1)")
    print(f"AI_COMMANDER_MOVE_INTERVALS: {ai_consts.get('WFBE_C_AI_COMMANDER_MOVE_INTERVALS')} (expected 3600)")

    upgrades_size = os.path.getsize(upgrades_path)
    economy_size = os.path.getsize(economy_path)
    ai_size = os.path.getsize(ai_path)
    print(f'\nOutput files:')
    print(f"  {upgrades_path} ({upgrades_size:,} bytes)")
    print(f"  {economy_path} ({economy_size:,} bytes)")
    print(f"  {ai_path} ({ai_size:,} bytes)")
    print('\nDone.')


if __name__ == '__main__':
    main()
