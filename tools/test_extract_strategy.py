"""
Unit tests for extract_strategy.py  —  inline fixtures only, no filesystem deps.
"""

import unittest
from extract_strategy import (
    parse_sqf_value,
    parse_upgrade_ids,
    parse_faction_upgrades,
    parse_labels,
    parse_constants,
    strip_sqf_comments,
)


class TestSqfValueParser(unittest.TestCase):
    """Tests for the low-level SQF value parser."""

    def test_integer(self):
        val, end = parse_sqf_value('42;', 0)
        self.assertEqual(val, 42)
        self.assertIsInstance(val, int)

    def test_negative_integer(self):
        val, end = parse_sqf_value('-7', 0)
        self.assertEqual(val, -7)

    def test_float(self):
        val, end = parse_sqf_value('1.2', 0)
        self.assertAlmostEqual(val, 1.2)
        self.assertIsInstance(val, float)

    def test_bool_true(self):
        val, end = parse_sqf_value('true', 0)
        self.assertIs(val, True)

    def test_bool_false(self):
        val, end = parse_sqf_value('false', 0)
        self.assertIs(val, False)

    def test_string(self):
        val, end = parse_sqf_value('"hello world"', 0)
        self.assertEqual(val, 'hello world')

    def test_string_with_escaped_quote(self):
        val, end = parse_sqf_value('"say ""hi"""', 0)
        self.assertEqual(val, 'say "hi"')

    def test_empty_array(self):
        val, end = parse_sqf_value('[]', 0)
        self.assertEqual(val, [])

    def test_flat_int_array(self):
        val, end = parse_sqf_value('[1, 2, 3]', 0)
        self.assertEqual(val, [1, 2, 3])

    def test_nested_array(self):
        val, end = parse_sqf_value('[[1,2],[3,4]]', 0)
        self.assertEqual(val, [[1, 2], [3, 4]])

    def test_deeply_nested(self):
        val, end = parse_sqf_value('[[[540,0],[1350,0]],[[250,0]]]', 0)
        self.assertEqual(val, [[[540, 0], [1350, 0]], [[250, 0]]])

    def test_mixed_array(self):
        val, end = parse_sqf_value('[1, true, "x", [2]]', 0)
        self.assertEqual(val, [1, True, 'x', [2]])

    def test_whitespace_tolerance(self):
        val, end = parse_sqf_value('[  1 ,\n  2 ,\n  3  ]', 0)
        self.assertEqual(val, [1, 2, 3])

    def test_multiline_nested(self):
        fixture = """[
            [[540,0],[1350,0],[2070,0]],
            [[250,0],[950,0],[1900,0],[3500,0]]
        ]"""
        val, end = parse_sqf_value(fixture, 0)
        self.assertEqual(val[0], [[540, 0], [1350, 0], [2070, 0]])
        self.assertEqual(val[1], [[250, 0], [950, 0], [1900, 0], [3500, 0]])


class TestStripComments(unittest.TestCase):
    def test_line_comment(self):
        out = strip_sqf_comments('x = 1; // comment\ny = 2;')
        self.assertNotIn('//', out)
        self.assertIn('y = 2', out)

    def test_block_comment(self):
        out = strip_sqf_comments('a /* block */ b')
        self.assertNotIn('block', out)
        self.assertIn('a', out)
        self.assertIn('b', out)

    def test_multiline_block_comment(self):
        out = strip_sqf_comments('start /*\nfoo\nbar\n*/ end')
        self.assertNotIn('foo', out)
        self.assertIn('end', out)


class TestParseUpgradeIds(unittest.TestCase):
    FIXTURE = """
//--- Common Upgrades, each number match the upgrades arrays.
WFBE_UP_BARRACKS = 0;
WFBE_UP_LIGHT = 1;
WFBE_UP_HEAVY = 2;
WFBE_UP_AIR = 3;
WFBE_UP_PARATROOPERS = 4;
WFBE_UP_UAV = 5;
WFBE_UP_SUPPLYRATE = 6;
WFBE_UP_RESPAWNRANGE = 7;
WFBE_UP_AIRLIFT = 8;
WFBE_UP_FLARESCM = 9;
WFBE_UP_ARTYTIMEOUT = 10;
WFBE_UP_ICBM = 11;
WFBE_UP_FASTTRAVEL = 12;
WFBE_UP_GEAR = 13;
WFBE_UP_AMMOCOIN = 14;
WFBE_UP_EASA = 15;
WFBE_UP_SUPPLYPARADROP = 16;
WFBE_UP_ARTYAMMO = 17;
WFBE_UP_IRSMOKE = 18;
WFBE_UP_AIRAAM = 19;
WFBE_UP_AAR = 20;
WFBE_UP_UNITCOST = 21;
"""

    def test_all_ids_found(self):
        ids = parse_upgrade_ids(self.FIXTURE)
        self.assertEqual(len(ids), 22)

    def test_barracks_is_zero(self):
        ids = parse_upgrade_ids(self.FIXTURE)
        self.assertEqual(ids['BARRACKS'], 0)

    def test_unitcost_is_21(self):
        ids = parse_upgrade_ids(self.FIXTURE)
        self.assertEqual(ids['UNITCOST'], 21)

    def test_icbm_is_11(self):
        ids = parse_upgrade_ids(self.FIXTURE)
        self.assertEqual(ids['ICBM'], 11)

    def test_returns_dict(self):
        ids = parse_upgrade_ids(self.FIXTURE)
        self.assertIsInstance(ids, dict)


class TestParseFactionUpgrades(unittest.TestCase):
    """Test parse_faction_upgrades with a minimal fixture."""

    # Minimal fixture covering COSTS, LEVELS, TIMES, LINKS, AI_ORDER, ENABLED
    FIXTURE = """
Private ["_side"];
_side = _this;

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_ENABLED", _side], [
    true, //--- Barracks
    false //--- Light
]];

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_COSTS", _side], [
    [[540,0],[1350,0],[2070,0]], //--- Barracks
    [[250,0],[950,0]] //--- Light
]];

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_LEVELS", _side], [
    3, //--- Barracks
    2  //--- Light
]];

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_TIMES", _side], [
    [30,60,90], //--- Barracks
    [40,60]     //--- Light
]];

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_LINKS", _side], [
    [[WFBE_UP_GEAR,2],[WFBE_UP_GEAR,3]], //--- Barracks
    [[],[]]                               //--- Light
]];

missionNamespace setVariable [Format["WFBE_C_UPGRADES_%1_AI_ORDER", _side], [
    [WFBE_UP_BARRACKS,1],
    [WFBE_UP_LIGHT,1],
    [WFBE_UP_BARRACKS,2]
]];
"""

    UP_IDS = {
        'BARRACKS': 0, 'LIGHT': 1, 'GEAR': 13,
    }

    def _parse(self):
        return parse_faction_upgrades(self.FIXTURE, self.UP_IDS)

    def test_costs_barracks(self):
        data = self._parse()
        self.assertEqual(data['costs'][0], [[540, 0], [1350, 0], [2070, 0]])

    def test_costs_light(self):
        data = self._parse()
        self.assertEqual(data['costs'][1], [[250, 0], [950, 0]])

    def test_levels(self):
        data = self._parse()
        self.assertEqual(data['levels'], [3, 2])

    def test_times(self):
        data = self._parse()
        self.assertEqual(data['times'][0], [30, 60, 90])

    def test_links_resolve_up_ids(self):
        data = self._parse()
        # WFBE_UP_GEAR = 13 in our UP_IDS
        self.assertEqual(data['links'][0][0], [13, 2])
        self.assertEqual(data['links'][0][1], [13, 3])

    def test_ai_order_resolves_up_ids(self):
        data = self._parse()
        self.assertEqual(data['ai_order'][0], [0, 1])  # BARRACKS=0, level=1
        self.assertEqual(data['ai_order'][1], [1, 1])  # LIGHT=1, level=1

    def test_enabled_simple_booleans(self):
        data = self._parse()
        self.assertIs(data['enabled'][0], True)
        self.assertIs(data['enabled'][1], False)

    def test_all_keys_present(self):
        data = self._parse()
        for key in ('enabled', 'levels', 'costs', 'times', 'links', 'ai_order'):
            self.assertIn(key, data)


class TestParseConstants(unittest.TestCase):

    def test_bare_scalar(self):
        text = 'WFBE_C_ECONOMY_INCOME_COEF = 8;'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_ECONOMY_INCOME_COEF'), 8)

    def test_bare_float(self):
        text = 'WFBE_C_ECONOMY_INCOME_DIVIDED = 1.2;'
        consts = parse_constants(text)
        self.assertAlmostEqual(consts.get('WFBE_C_ECONOMY_INCOME_DIVIDED'), 1.2)

    def test_isnilguard_scalar(self):
        text = 'if (isNil "WFBE_C_ECONOMY_FUNDS_START_WEST") then {WFBE_C_ECONOMY_FUNDS_START_WEST = 800};'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_ECONOMY_FUNDS_START_WEST'), 800)

    def test_isnilguard_debug_else(self):
        text = 'if (isNil "WFBE_C_ECONOMY_FUNDS_START_WEST") then {WFBE_C_ECONOMY_FUNDS_START_WEST = if (WF_Debug) then {900000} else {800}};'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_ECONOMY_FUNDS_START_WEST'), 800)

    def test_array_constant(self):
        text = 'WFBE_C_ARTILLERY_INTERVALS = [550, 500, 450, 400, 350, 300, 250];'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_ARTILLERY_INTERVALS'), [550, 500, 450, 400, 350, 300, 250])

    def test_respawn_ranges_array(self):
        text = 'WFBE_C_RESPAWN_RANGES = [250, 350, 500];'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_RESPAWN_RANGES'), [250, 350, 500])

    def test_artillery_intervals_debug_else_block(self):
        """WFBE_C_ARTILLERY_INTERVALS is inside if WF_Debug then {...} else {...}."""
        text = """
if WF_Debug then
{
    WFBE_C_ARTILLERY_INTERVALS = [15, 15, 15, 15, 15, 15, 15];
} else
{
    WFBE_C_ARTILLERY_INTERVALS = [550, 500, 450, 400, 350, 300, 250];
};
"""
        consts = parse_constants(text)
        # Should capture the else (prod) branch
        self.assertEqual(consts.get('WFBE_C_ARTILLERY_INTERVALS'), [550, 500, 450, 400, 350, 300, 250])

    def test_ai_commander_enabled_isnilguard(self):
        text = 'if (isNil "WFBE_C_AI_COMMANDER_ENABLED") then {WFBE_C_AI_COMMANDER_ENABLED = 1};'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_AI_COMMANDER_ENABLED'), 1)

    def test_bare_ai_scalar(self):
        text = 'WFBE_C_AI_COMMANDER_MOVE_INTERVALS = 3600;'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_AI_COMMANDER_MOVE_INTERVALS'), 3600)

    def test_supply_levels_array(self):
        text = 'WFBE_C_TOWNS_SUPPLY_LEVELS_TIME = [1, 2, 3, 4, 5];'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_TOWNS_SUPPLY_LEVELS_TIME'), [1, 2, 3, 4, 5])

    def test_units_support_heal_price(self):
        text = 'WFBE_C_UNITS_SUPPORT_HEAL_PRICE = 125;'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_UNITS_SUPPORT_HEAL_PRICE'), 125)

    def test_hq_repair_price(self):
        text = 'WFBE_C_BASE_HQ_REPAIR_PRICE_1ST = 25000;'
        consts = parse_constants(text)
        self.assertEqual(consts.get('WFBE_C_BASE_HQ_REPAIR_PRICE_1ST'), 25000)

    def test_ignores_non_matching(self):
        text = 'SOME_RANDOM_VAR = 99;'
        consts = parse_constants(text)
        self.assertNotIn('SOME_RANDOM_VAR', consts)


class TestParseLabels(unittest.TestCase):
    FIXTURE = """
missionNamespace setVariable [Format["WFBE_C_UPGRADES_LABELS"], [
    localize 'strwfbarracks',
    localize 'strwflightfactory',
    localize 'strwfheavyfactory',
    localize 'strwfaircraftfactory',
    localize 'STR_WF_TACTICAL_Paratroop',
    localize 'str_dn_uav',
    localize 'STR_WF_UPGRADE_Supply',
    localize 'STR_WF_UPGRADE_RespawnRange',
    localize 'STR_WF_UPGRADE_Airlift',
    localize 'STR_WF_UPGRADE_Countermeasures',
    localize 'STR_WF_UPGRADE_ArtilleryUpgrade',
    localize 'STR_WF_ICBM',
    localize 'STR_WF_TACTICAL_FastTravel',
    localize 'STR_WF_UPGRADE_Gear',
    localize 'STR_WF_Ammo',
    'EASA',
    localize 'STR_WF_TACTICAL_Paradrop',
    localize 'STR_WF_UPGRADE_ArtilleryAmmo',
    localize 'STR_WF_UPGRADE_IRS',
    localize 'STR_WF_UPGRADE_AirAA',
    localize 'STR_WF_UPGRADE_AntiAirRadar',
    localize 'STR_WF_UPGRADE_UnitCost'
]];
"""

    def test_label_count(self):
        labels = parse_labels(self.FIXTURE)
        self.assertEqual(len(labels), 22)

    def test_first_label(self):
        labels = parse_labels(self.FIXTURE)
        self.assertEqual(labels[0], 'strwfbarracks')

    def test_easa_bare_string(self):
        labels = parse_labels(self.FIXTURE)
        # Index 15 is 'EASA' (bare single-quoted string)
        self.assertEqual(labels[15], 'EASA')

    def test_last_label(self):
        labels = parse_labels(self.FIXTURE)
        self.assertEqual(labels[21], 'STR_WF_UPGRADE_UnitCost')


if __name__ == '__main__':
    unittest.main(verbosity=2)
