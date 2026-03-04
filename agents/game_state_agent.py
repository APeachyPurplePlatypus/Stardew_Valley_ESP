#!/usr/bin/env python3
"""
Stardew Valley Game State Agent
================================
Monitors your Stardew Valley save folder, compares game state between days,
and generates a Morning Brief + LLM-ready coaching prompt.

SETUP:
    pip install watchdog

USAGE:
    # Watch mode — waits for you to sleep in-game, then auto-analyses:
    python game_state_agent.py

    # One-shot mode — analyse the current save and exit:
    python game_state_agent.py --once

    # Custom saves path (default is %%APPDATA%%\\StardewValley\\Saves):
    python game_state_agent.py --saves-dir "C:/path/to/Saves"

    # Point at the local dev copy in this repo:
    python game_state_agent.py --saves-dir "Saves"
"""

import os
import sys
import json
import time
import logging
import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Stub so the class definition below doesn't fail at import time
    class FileSystemEventHandler:  # type: ignore[no-redef]
        pass
    Observer = None  # type: ignore[assignment,misc]

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_SAVES_DIR = Path(os.path.expandvars(r"%APPDATA%\StardewValley\Saves"))

SEASONS = {0: "Spring", 1: "Summer", 2: "Fall", 3: "Winter"}
SEASON_NAMES = {"spring": "Spring", "summer": "Summer", "fall": "Fall", "winter": "Winter"}

XP_THRESHOLDS = [0, 100, 380, 770, 1300, 2150, 3300, 4800, 6900, 10000, 15000]
SKILL_NAMES   = ["Farming", "Fishing", "Foraging", "Mining", "Combat", "Luck"]

PROFESSION_NAMES = {
    0: "Rancher",     1: "Tiller",       2: "Coopmaster",  3: "Shepherd",
    4: "Artisan",     5: "Agriculturist", 6: "Fisher",      7: "Trapper",
    8: "Angler",      9: "Pirate",       10: "Mariner",    11: "Luremaster",
    12: "Forester",  13: "Gatherer",     14: "Lumberjack", 15: "Tapper",
    16: "Botanist",  17: "Tracker",      18: "Miner",      19: "Geologist",
    20: "Blacksmith",21: "Prospector",   22: "Excavator",  23: "Gemologist",
    24: "Fighter",   25: "Scout",        26: "Brute",      27: "Defender",
    28: "Acrobat",   29: "Desperado",
}

HOUSE_UPGRADE_LABELS = {0: "Cabin", 1: "Kitchen", 2: "Cellar", 3: "Full House"}

# ── Fish item ID → display name (Stardew Valley 1.6, confirmed via stardewids) ─
FISH_ID_NAMES: dict[int, str] = {
    128: "Pufferfish",      129: "Anchovy",           130: "Tuna",
    131: "Sardine",         132: "Bream",              136: "Largemouth Bass",
    137: "Smallmouth Bass", 138: "Rainbow Trout",      139: "Salmon",
    140: "Walleye",         141: "Perch",              142: "Carp",
    143: "Catfish",         144: "Pike",               145: "Sunfish",
    146: "Red Mullet",      147: "Herring",            148: "Eel",
    149: "Octopus",         150: "Red Snapper",        151: "Squid",
    152: "Seaweed",         153: "Green Algae",        154: "Sea Cucumber",
    155: "Super Cucumber",  156: "Ghostfish",          157: "White Algae",
    158: "Stonefish",       159: "Crimsonfish",        160: "Angler",
    161: "Ice Pip",         162: "Lava Eel",           163: "Legend",
    164: "Sandfish",        165: "Scorpion Carp",
    267: "Flounder",        269: "Midnight Carp",      372: "Clam",
    682: "Mutant Carp",     698: "Sturgeon",           699: "Tiger Trout",
    700: "Bullhead",        701: "Tilapia",            702: "Chub",
    704: "Dorado",          705: "Albacore",           706: "Shad",
    707: "Lingcod",         708: "Halibut",
    715: "Lobster",         716: "Crayfish",           717: "Crab",
    718: "Cockle",          719: "Mussel",             720: "Shrimp",
    721: "Snail",           722: "Periwinkle",         723: "Oyster",
    734: "Woodskip",        775: "Glacierfish",        795: "Void Salmon",
    796: "Slimejack",       798: "Midnight Squid",     799: "Spook Fish",
    800: "Blobfish",        836: "Stingray",           837: "Lionfish",
    838: "Blue Discus",     898: "Son of Crimsonfish", 899: "Ms. Angler",
    900: "Legend II",       901: "Radioactive Carp",   902: "Glacierfish Jr.",
}

# ── Bundle item ID → display name (extracted from bundleData in both dev saves) ─
BUNDLE_ITEM_NAMES: dict[int, str] = {
    16: "Wild Horseradish",  18: "Daffodil",          20: "Leek",
    22: "Dandelion",         24: "Parsnip",            62: "Aquamarine",
    74: "Prismatic Shard",   78: "Cave Carrot",        80: "Quartz",
    82: "Fire Quartz",       84: "Frozen Tear",        86: "Earth Crystal",
    88: "Coconut",           90: "Cactus Fruit",      128: "Pufferfish",
    130: "Tuna",            131: "Sardine",           132: "Bream",
    136: "Largemouth Bass", 140: "Walleye",           142: "Carp",
    143: "Catfish",         145: "Sunfish",           148: "Eel",
    150: "Red Snapper",     156: "Ghostfish",         164: "Sandfish",
    174: "Large Egg",       178: "Hay",               182: "Large Egg",
    186: "Large Milk",      188: "Green Bean",        190: "Cauliflower",
    192: "Potato",          194: "Fried Egg",         228: "Maki Roll",
    254: "Melon",           256: "Tomato",            257: "Morel",
    258: "Blueberry",       259: "Fiddlehead Fern",   260: "Hot Pepper",
    262: "Wheat",           266: "Red Cabbage",       270: "Corn",
    272: "Eggplant",        276: "Pumpkin",           280: "Yam",
    334: "Copper Bar",      335: "Iron Bar",          336: "Gold Bar",
    340: "Honey",           344: "Jelly",             348: "Wine",
    372: "Clam",            376: "Poppy",             388: "Wood",
    390: "Stone",           392: "Nautilus Shell",    396: "Spice Berry",
    397: "Sea Urchin",      398: "Grape",             402: "Sweet Pea",
    404: "Common Mushroom", 406: "Wild Plum",         408: "Hazelnut",
    410: "Blackberry",      412: "Winter Root",       414: "Crystal Fruit",
    416: "Snow Yam",        418: "Crocus",            420: "Red Mushroom",
    421: "Sunflower",       422: "Purple Mushroom",   424: "Cheese",
    426: "Goat Cheese",     428: "Cloth",             430: "Truffle",
    432: "Truffle Oil",     438: "L. Goat Milk",      440: "Wool",
    442: "Duck Egg",        444: "Duck Feather",      445: "Caviar",
    446: "Rabbit's Foot",   454: "Ancient Fruit",     536: "Frozen Geode",
    613: "Apple",           634: "Apricot",           635: "Orange",
    636: "Peach",           637: "Pomegranate",       638: "Cherry",
    698: "Sturgeon",        699: "Tiger Trout",       700: "Bullhead",
    701: "Tilapia",         702: "Chub",              706: "Shad",
    709: "Hardwood",        715: "Lobster",           716: "Crayfish",
    717: "Crab",            718: "Cockle",            719: "Mussel",
    720: "Shrimp",          721: "Snail",             722: "Periwinkle",
    723: "Oyster",          724: "Maple Syrup",       725: "Oak Resin",
    726: "Pine Tar",        734: "Woodskip",          766: "Slime",
    767: "Bat Wing",        768: "Solar Essence",     769: "Void Essence",
    795: "Void Salmon",     807: "Dinosaur Mayonnaise",
}

# ── Fish availability schedule ─────────────────────────────────────────────────
# Each entry: (name, seasons_frozenset, weather, location_hint, min_fishing_level)
#   weather: "any" | "sun" | "rain"
#   seasons: lowercase frozenset from {"spring","summer","fall","winter"}
_S = frozenset
FISH_SCHEDULE: list = [
    # ── Ocean ──────────────────────────────────────────────────────────────────
    ("Pufferfish",       _S({"summer"}),                      "sun",  "Ocean",                      0),
    ("Anchovy",          _S({"spring", "fall"}),               "any",  "Ocean",                      0),
    ("Tuna",             _S({"summer", "winter"}),             "any",  "Ocean",                      0),
    ("Sardine",          _S({"spring", "fall", "winter"}),     "any",  "Ocean",                      0),
    ("Red Mullet",       _S({"summer", "fall"}),               "any",  "Ocean",                      0),
    ("Herring",          _S({"spring", "winter"}),             "any",  "Ocean",                      0),
    ("Eel",              _S({"spring", "fall"}),               "rain", "Ocean",                      3),
    ("Octopus",          _S({"summer"}),                      "any",  "Ocean",                      6),
    ("Red Snapper",      _S({"summer", "fall"}),               "any",  "Ocean",                      0),
    ("Squid",            _S({"winter"}),                      "any",  "Ocean",                      4),
    ("Sea Cucumber",     _S({"fall", "winter"}),               "any",  "Ocean",                      0),
    ("Super Cucumber",   _S({"summer", "fall"}),               "any",  "Ocean (night)",              8),
    ("Crimsonfish",      _S({"summer"}),                      "any",  "Ocean (east pier)",          5),
    ("Flounder",         _S({"spring", "summer"}),             "any",  "Ocean",                      0),
    ("Tilapia",          _S({"summer", "fall"}),               "any",  "Ocean",                      0),
    ("Albacore",         _S({"fall", "winter"}),               "any",  "Ocean",                      0),
    ("Halibut",          _S({"spring", "summer", "winter"}),   "any",  "Ocean",                      0),
    # ── River ──────────────────────────────────────────────────────────────────
    ("Bream",            _S({"spring","summer","fall","winter"}),"any","River (night)",              0),
    ("Smallmouth Bass",  _S({"spring", "fall"}),               "any",  "River",                      0),
    ("Rainbow Trout",    _S({"summer"}),                      "sun",  "River / Mountain Lake",      0),
    ("Salmon",           _S({"fall"}),                        "any",  "River",                      0),
    ("Walleye",          _S({"fall"}),                        "rain", "River",                      0),
    ("Catfish",          _S({"spring", "fall"}),               "rain", "River",                      4),
    ("Pike",             _S({"summer", "winter"}),             "any",  "River",                      0),
    ("Sunfish",          _S({"spring", "summer"}),             "sun",  "River",                      0),
    ("Shad",             _S({"spring", "summer", "fall"}),     "rain", "River",                      0),
    ("Lingcod",          _S({"winter"}),                      "any",  "River",                      5),
    ("Tiger Trout",      _S({"fall", "winter"}),               "any",  "River",                      5),
    ("Angler",           _S({"fall"}),                        "any",  "River (north bridge)",       3),
    ("Midnight Carp",    _S({"fall", "winter"}),               "any",  "River / Mountain (night)",   0),
    # ── Mountain Lake ──────────────────────────────────────────────────────────
    ("Largemouth Bass",  _S({"spring","summer","fall","winter"}),"any","Mountain Lake",              0),
    ("Carp",             _S({"spring", "summer", "fall"}),     "any",  "Mountain Lake",              0),
    ("Bullhead",         _S({"spring","summer","fall","winter"}),"any","Mountain Lake",              0),
    ("Sturgeon",         _S({"summer", "winter"}),             "any",  "Mountain Lake",              0),
    ("Legend",           _S({"spring"}),                      "rain", "Mountain Lake",              10),
    # ── Other freshwater ───────────────────────────────────────────────────────
    ("Perch",            _S({"winter"}),                      "any",  "River / Lake",               0),
    ("Chub",             _S({"spring","summer","fall","winter"}),"any","Mountain / Forest River",    0),
    ("Dorado",           _S({"summer"}),                      "any",  "Forest River",               0),
    ("Woodskip",         _S({"spring","summer","fall","winter"}),"any","Secret Woods",               0),
    # ── Desert ─────────────────────────────────────────────────────────────────
    ("Sandfish",         _S({"summer", "fall"}),               "any",  "Desert",                     0),
    ("Scorpion Carp",    _S({"summer"}),                      "any",  "Desert",                     4),
    # ── Mines / Underground ────────────────────────────────────────────────────
    ("Ghostfish",        _S({"spring","summer","fall","winter"}),"any","Mines (lv 20 / 60)",         0),
    ("Stonefish",        _S({"spring","summer","fall","winter"}),"any","Mines (lv 20)",              0),
    ("Ice Pip",          _S({"spring","summer","fall","winter"}),"any","Mines (lv 60)",              5),
    ("Lava Eel",         _S({"spring","summer","fall","winter"}),"any","Mines (lv 100)",             7),
    # ── Key-gated locations ────────────────────────────────────────────────────
    ("Mutant Carp",      _S({"spring","summer","fall","winter"}),"any","Sewers (Rusty Key)",         0),
    ("Void Salmon",      _S({"spring","summer","fall","winter"}),"any","Witch's Swamp",              0),
    ("Slimejack",        _S({"spring","summer","fall","winter"}),"any","Sewers / Slime Hutch",       0),
    ("Glacierfish",      _S({"winter"}),                      "any",  "Arrowhead Island",           6),
    # ── Ginger Island ──────────────────────────────────────────────────────────
    ("Stingray",         _S({"spring","summer","fall","winter"}),"any","Ginger Island (Pirate Cove)", 0),
    ("Lionfish",         _S({"spring","summer","fall","winter"}),"any","Ginger Island (ocean)",      0),
    ("Blue Discus",      _S({"spring","summer","fall","winter"}),"any","Ginger Island (river)",      0),
    # ── Legendary II (Mr. Qi extended family quest) ────────────────────────────
    ("Son of Crimsonfish",_S({"summer"}),                     "any",  "Ocean east pier [Qi Quest]", 5),
    ("Ms. Angler",       _S({"fall"}),                        "any",  "River north bridge [Qi Quest]", 3),
    ("Legend II",        _S({"spring"}),                      "rain", "Mountain Lake [Qi Quest]",   10),
    ("Radioactive Carp", _S({"spring","summer","fall","winter"}),"any","Mutant Bug Lair [Qi Quest]", 0),
    ("Glacierfish Jr.",  _S({"winter"}),                      "any",  "Arrowhead Island [Qi Quest]", 6),
]


def get_catchable_fish(season: str, is_raining: bool, fishing_level: int = 0) -> list:
    """
    Return sorted list of (name, location, level_note) tuples catchable today.

    Args:
        season: Current season (Spring/Summer/Fall/Winter)
        is_raining: True if currently raining or storming
        fishing_level: Player's Fishing skill level (used for min-level notes)
    """
    season_lower = season.lower()
    results = []
    for name, seasons, condition, location, min_level in FISH_SCHEDULE:
        if season_lower not in seasons:
            continue
        if condition == "rain" and not is_raining:
            continue
        if condition == "sun" and is_raining:
            continue
        note = f"(fishing {min_level}+)" if min_level > 0 else ""
        results.append((name, location, note))
    return sorted(results, key=lambda x: x[0])


# XSI namespace constant — used for nil-bool XML pattern
_NS = "{http://www.w3.org/2001/XMLSchema-instance}"


def _xp_progress(xp: int, level: int) -> dict:
    """Return XP progress info toward the next skill level."""
    if level >= 10:
        return {"current_xp": xp, "xp_to_next": 0, "progress_pct": 100.0}
    t_cur  = XP_THRESHOLDS[level]
    t_next = XP_THRESHOLDS[level + 1]
    needed = t_next - t_cur
    pct    = round((xp - t_cur) / needed * 100, 1) if needed else 100.0
    return {"current_xp": xp, "xp_to_next": max(0, t_next - xp), "progress_pct": pct}


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class QuestState:
    title: str
    completed: bool
    money_reward: int


@dataclass
class FriendshipState:
    npc: str
    points: int
    status: str
    talked_today: bool


@dataclass
class BundleItem:
    item_id: int
    item_name: str
    quantity: int
    quality: int    # 0=Normal, 1=Silver, 2=Gold, 4=Iridium
    donated: bool


@dataclass
class BundleState:
    id: int
    name: str
    room: str
    items: list          # list[BundleItem]
    items_donated: int
    items_total: int
    required: int        # slots needed to complete bundle
    is_complete: bool    # donated_count >= required

    def is_done(self) -> bool:
        return self.is_complete

    def missing_items(self) -> list:
        return [it for it in self.items if not it.donated]


@dataclass
class GameState:
    # ── Date / World ─────────────────────────────────────────────────────────
    day: int = 0
    season: str = "Spring"
    year: int = 1
    save_time: int = 0
    daily_luck: float = 0.0
    weather_tomorrow: str = "Sun"
    is_raining: bool = False

    # ── Finances ─────────────────────────────────────────────────────────────
    money: int = 0
    total_money_earned: int = 0

    # ── Skills ───────────────────────────────────────────────────────────────
    farming_level: int = 0
    fishing_level: int = 0
    foraging_level: int = 0
    mining_level: int = 0
    combat_level: int = 0
    luck_level: int = 0

    # ── Cumulative Statistics ─────────────────────────────────────────────────
    stone_gathered: int = 0
    items_shipped: int = 0
    rocks_crushed: int = 0
    times_fished: int = 0
    steps_taken: int = 0
    days_played: int = 0
    crops_shipped: int = 0
    items_foraged: int = 0
    monsters_killed: int = 0
    items_crafted: int = 0
    gifts_given: int = 0
    weeds_eliminated: int = 0
    dirt_hoed: int = 0
    geodes_cracked: int = 0
    items_cooked: int = 0

    # ── Social ───────────────────────────────────────────────────────────────
    dialogue_events: dict = field(default_factory=dict)
    friendship: list = field(default_factory=list)   # list[FriendshipState]

    # ── Quests ───────────────────────────────────────────────────────────────
    quests: list = field(default_factory=list)        # list[QuestState]

    # ── Identity ──────────────────────────────────────────────────────────────
    farmer_name: str = ""
    farm_name: str = ""
    gender: str = ""
    pet_type: str = ""

    # ── Vitals ────────────────────────────────────────────────────────────────
    health: int = 100
    max_health: int = 100
    stamina: float = 270.0
    max_stamina: int = 270

    # ── Skill XP (raw, 6 values indexed 0–5: Farm/Fish/Forage/Mine/Combat/Luck)
    experience_points: list = field(default_factory=lambda: [0] * 6)

    # ── Professions ───────────────────────────────────────────────────────────
    professions: list = field(default_factory=list)  # list[int]

    # ── Progression flags ─────────────────────────────────────────────────────
    deepest_mine_level: int = 0
    house_upgrade_level: int = 0
    has_skull_key: bool = False
    has_rusty_key: bool = False
    has_special_charm: bool = False
    can_understand_dwarves: bool = False

    # ── Inventory ─────────────────────────────────────────────────────────────
    inventory_items: list = field(default_factory=list)  # list[dict]

    # ── Recipes (counts only) ─────────────────────────────────────────────────
    recipes_cooking_count: int = 0
    recipes_crafting_count: int = 0

    # ── World-file extras ─────────────────────────────────────────────────────
    mine_lowest_level_reached: int = 0
    golden_walnuts: int = 0
    golden_walnuts_found: int = 0

    # ── Fishing collection ────────────────────────────────────────────────────
    fish_caught: dict = field(default_factory=dict)          # {name: catch_count}

    # ── Community Center ──────────────────────────────────────────────────────
    cc_rooms_complete: list = field(default_factory=list)    # list[bool], 6 rooms
    cc_bundles: list = field(default_factory=list)           # list[BundleState]


# ─────────────────────────────────────────────────────────────────────────────
# SAVE PARSER
# ─────────────────────────────────────────────────────────────────────────────

class SaveParser:
    """
    Parse a Stardew Valley save folder into a GameState.

    Stardew writes two files per save:
      - SaveGameInfo          (≈23 KB) — farmer snapshot, used for farmer data
      - {FolderName}          (≈2-10 MB) — full world state, used for dailyLuck / weather

    The _old variants are yesterday's copies, used to diff against today.
    """

    # Stat key mapping: (save-file key → GameState attribute)
    STAT_MAP = {
        "stoneGathered":  "stone_gathered",
        "itemsShipped":   "items_shipped",
        "rocksCrushed":   "rocks_crushed",
        "timesFished":    "times_fished",
        "stepsTaken":     "steps_taken",
        "daysPlayed":     "days_played",
        "cropsShipped":   "crops_shipped",
        "itemsForaged":   "items_foraged",
        "monstersKilled": "monsters_killed",
        "itemsCrafted":   "items_crafted",
        "giftsGiven":     "gifts_given",
        "weedsEliminated":"weeds_eliminated",
        "dirtHoed":       "dirt_hoed",
        "geodesCracked":  "geodes_cracked",
        "itemsCooked":    "items_cooked",
    }

    def __init__(self, save_folder: Path, use_old: bool = False):
        suffix = "_old" if use_old else ""
        self.farmer_file   = save_folder / f"SaveGameInfo{suffix}"
        self.main_save_file = save_folder / f"{save_folder.name}{suffix}"

    def exists(self) -> bool:
        return self.farmer_file.exists()

    def parse(self) -> GameState:
        state = GameState()
        self._parse_farmer(state)
        self._parse_world(state)
        return state

    # ── Farmer Data (from SaveGameInfo) ──────────────────────────────────────

    def _parse_farmer(self, state: GameState) -> None:
        tree = ET.parse(self.farmer_file)
        root = tree.getroot()  # <Farmer>

        def get(path: str, default: str = "") -> str:
            el = root.find(path)
            return (el.text or "").strip() if el is not None else default

        def geti(path: str, default: int = 0) -> int:
            val = get(path, str(default))
            try:
                return int(val)
            except (ValueError, TypeError):
                return default

        def getf(path: str, default: float = 0.0) -> float:
            val = get(path, str(default))
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        def get_nil_bool(path: str) -> bool:
            """Return True only if element exists, is not xsi:nil, and text is 'true'."""
            el = root.find(path)
            if el is None or el.get(f"{_NS}nil") == "true":
                return False
            return (el.text or "").strip().lower() == "true"

        # Date
        state.day    = geti("dayOfMonthForSaveGame")
        state.season = SEASONS.get(geti("seasonForSaveGame"), "Spring")
        state.year   = geti("yearForSaveGame")
        state.save_time = geti("saveTime")

        # Finances
        state.money               = geti("money")
        state.total_money_earned  = geti("totalMoneyEarned")

        # Skills
        state.farming_level  = geti("farmingLevel")
        state.fishing_level  = geti("fishingLevel")
        state.foraging_level = geti("foragingLevel")
        state.mining_level   = geti("miningLevel")
        state.combat_level   = geti("combatLevel")
        state.luck_level     = geti("luckLevel")

        # Statistics — two formats exist across game versions:
        #   Format A (1.6 new saves):  stats/Values/item  key-value pairs
        #   Format B (legacy saves):   stats/<statName>   direct child elements
        stat_set = False
        for item in root.findall("stats/Values/item"):
            key  = item.findtext("key/string", "")
            v_el = item.find("value/unsignedInt")
            if v_el is None:
                v_el = item.find("value/int")
            if key and v_el is not None and v_el.text:
                attr = self.STAT_MAP.get(key)
                if attr:
                    setattr(state, attr, int(v_el.text))
                    stat_set = True

        if not stat_set:
            # Format B: direct child elements under <stats>
            # Also handles PascalCase duplicates (e.g. StoneGathered) by
            # building a case-insensitive lookup of the STAT_MAP keys.
            lower_map = {k.lower(): v for k, v in self.STAT_MAP.items()}
            stats_el = root.find("stats")
            if stats_el is not None:
                ns = "{http://www.w3.org/2001/XMLSchema-instance}"
                for child in stats_el:
                    if child.get(f"{ns}nil") == "true" or not child.text:
                        continue
                    attr = lower_map.get(child.tag.lower())
                    if attr:
                        try:
                            setattr(state, attr, int(child.text))
                        except ValueError:
                            pass

        # Active dialogue events
        for item in root.findall("activeDialogueEvents/item"):
            k    = item.findtext("key/string", "")
            v_el = item.find("value/int")
            if k and v_el is not None:
                state.dialogue_events[k] = int(v_el.text or 0)

        # Friendship data
        for item in root.findall("friendshipData/item"):
            npc         = item.findtext("key/string", "")
            points      = int(item.findtext("value/Friendship/Points", "0") or 0)
            status      = item.findtext("value/Friendship/Status", "Unknown") or "Unknown"
            talked      = item.findtext("value/Friendship/TalkedToToday", "false") == "true"
            if npc:
                state.friendship.append(
                    FriendshipState(npc=npc, points=points, status=status, talked_today=talked)
                )

        # Quest log
        for quest in root.findall("questLog/Quest"):
            title = (
                quest.findtext("_questTitle")
                or quest.findtext("questTitle")
                or "Unknown Quest"
            )
            completed    = quest.findtext("completed", "false") == "true"
            money_reward = int(quest.findtext("moneyReward", "0") or 0)
            state.quests.append(QuestState(title=title, completed=completed, money_reward=money_reward))

        # ── Identity (dual format: newer=Gender/whichPetType, older=isMale/catPerson)
        state.farmer_name = get("name")
        state.farm_name   = get("farmName")
        g_el = root.find("Gender")
        if g_el is None:
            g_el = root.find("gender")
        if g_el is not None and g_el.get(f"{_NS}nil") != "true":
            state.gender = (g_el.text or "").strip()
        else:
            im_el = root.find("isMale")
            if im_el is not None and im_el.get(f"{_NS}nil") != "true":
                state.gender = "Male" if (im_el.text or "").lower() == "true" else "Female"
        p_el = root.find("whichPetType")
        if p_el is not None and p_el.get(f"{_NS}nil") != "true":
            state.pet_type = (p_el.text or "").strip()
        else:
            cp_el = root.find("catPerson")
            if cp_el is not None and cp_el.get(f"{_NS}nil") != "true":
                state.pet_type = "Cat" if (cp_el.text or "").lower() == "true" else "Dog"

        # ── Vitals
        state.health      = geti("health", 100)
        state.max_health  = geti("maxHealth", 100)
        state.stamina     = getf("stamina", 270.0)
        state.max_stamina = geti("maxStamina", 270)

        # ── Skill XP (array of 6 ints: Farm/Fish/Forage/Mine/Combat/Luck)
        state.experience_points = []
        for xp_el in root.findall("experiencePoints/int"):
            try:
                state.experience_points.append(int(xp_el.text or 0))
            except (ValueError, TypeError):
                state.experience_points.append(0)
        while len(state.experience_points) < 6:
            state.experience_points.append(0)

        # ── Professions
        state.professions = []
        for p_el in root.findall("professions/int"):
            try:
                state.professions.append(int(p_el.text or 0))
            except (ValueError, TypeError):
                pass

        # ── Progression flags
        state.deepest_mine_level     = geti("deepestMineLevel")
        state.house_upgrade_level    = geti("houseUpgradeLevel")
        state.has_skull_key          = get_nil_bool("hasSkullKey")
        state.has_rusty_key          = get_nil_bool("hasRustyKey")
        state.has_special_charm      = get_nil_bool("hasSpecialCharm")
        state.can_understand_dwarves = get_nil_bool("canUnderstandDwarves")

        # ── Inventory (skip nil/empty slots)
        state.inventory_items = []
        for slot_idx, item_el in enumerate(root.findall("items/Item")):
            if item_el.get(f"{_NS}nil") == "true":
                continue
            name     = item_el.findtext("name", "") or ""
            item_id  = item_el.findtext("itemId", "") or ""
            stack    = int(item_el.findtext("stack", "1") or 1)
            category = int(item_el.findtext("category", "0") or 0)
            ulvl     = item_el.findtext("upgradeLevel")
            if not name:
                continue
            state.inventory_items.append({
                "slot":          slot_idx,
                "name":          name,
                "item_id":       item_id,
                "stack":         stack,
                "category":      category,
                "upgrade_level": int(ulvl) if ulvl is not None else None,
            })

        # ── Recipes (counts only — list parsing is done by generate_schema.py)
        state.recipes_cooking_count  = len(root.findall("cookingRecipes/item"))
        state.recipes_crafting_count = len(root.findall("craftingRecipes/item"))

        # ── Fish caught: int ID → [count, maxSize]
        state.fish_caught = {}
        for item in root.findall("fishCaught/item"):
            k_el = item.find("key/int")
            if k_el is None:
                continue
            try:
                fish_id = int(k_el.text or 0)
            except (ValueError, TypeError):
                continue
            name = FISH_ID_NAMES.get(fish_id)
            if name is None:
                continue
            count_el = item.find("value/ArrayOfInt/int")
            count = int(count_el.text or 1) if count_el is not None else 1
            state.fish_caught[name] = count

    # ── World Data (from main save file) ─────────────────────────────────────

    def _parse_world(self, state: GameState) -> None:
        """
        Extract root-level world fields and Community Center bundle data from the
        main save file.  Uses full ET.parse() so we can access nested locations.
        Files are typically 2–10 MB — acceptable for the features we need.
        """
        if not self.main_save_file.exists():
            log.warning(f"Main save file not found: {self.main_save_file}")
            return

        tree = ET.parse(self.main_save_file)
        root = tree.getroot()  # <SaveGame>

        def ftext(path: str, default: str = "") -> str:
            el = root.find(path)
            return (el.text or "").strip() if el is not None else default

        state.daily_luck       = float(ftext("dailyLuck") or 0)
        state.weather_tomorrow = self._normalise_weather(ftext("weatherForTomorrow", "Sun"))
        state.is_raining       = ftext("isRaining", "false").lower() == "true"
        state.mine_lowest_level_reached = int(ftext("mine_lowestLevelReached") or 0)
        state.golden_walnuts            = int(ftext("goldenWalnuts") or 0)
        state.golden_walnuts_found      = int(ftext("goldenWalnutsFound") or 0)

        self._parse_bundles(state, root)

    def _parse_bundles(self, state: GameState, world_root: ET.Element) -> None:
        """Parse Community Center bundle definitions and donation progress."""

        # ── 1. Parse bundle definitions from bundleData ───────────────────────
        # Key format:   "Room/bundleID"
        # Value format: "name/reward/item_id qty quality .../numRequired/color[/displayName]"
        #   numRequired: -1 means all items required; positive = exact count needed
        bundle_defs: dict[int, dict] = {}
        for item in world_root.findall("bundleData/item"):
            key_str = item.findtext("key/string", "")
            val_str = item.findtext("value/string", "")
            if not key_str or not val_str:
                continue
            key_parts = key_str.split("/")
            if len(key_parts) < 2:
                continue
            room = key_parts[0]
            try:
                bundle_id = int(key_parts[1])
            except ValueError:
                continue

            parts = val_str.split("/")
            if len(parts) < 3:
                continue
            bundle_name = parts[0]

            raw = parts[2].split()
            items_def = []
            for i in range(0, len(raw) - 2, 3):
                try:
                    items_def.append((int(raw[i]), int(raw[i + 1]), int(raw[i + 2])))
                except (ValueError, IndexError):
                    continue

            n_items = len(items_def)
            try:
                num_required = int(parts[3]) if len(parts) > 3 else -1
            except ValueError:
                num_required = -1
            if num_required <= 0:
                num_required = n_items

            bundle_defs[bundle_id] = {
                "name":     bundle_name,
                "room":     room,
                "items":    items_def,
                "required": num_required,
            }

        # ── 2. Find CommunityCenter GameLocation ──────────────────────────────
        cc_elem = None
        for loc in world_root.iter("GameLocation"):
            if loc.findtext("name") == "CommunityCenter":
                cc_elem = loc
                break

        if cc_elem is None:
            return  # Joja route or not yet reachable

        # ── 3. Room completion flags (6 booleans) ─────────────────────────────
        state.cc_rooms_complete = [
            (b.text or "").strip().lower() == "true"
            for b in cc_elem.findall("areasComplete/boolean")
        ]

        # ── 4. Per-bundle donation booleans ───────────────────────────────────
        # Each bundle stores n_items * 3 booleans; slot i is donated when
        # any of booleans[i*3 .. i*3+3] is True.
        bundle_progress: dict[int, list] = {}
        for bitem in cc_elem.findall("bundles/item"):
            k_el = bitem.find("key/int")
            if k_el is None:
                continue
            try:
                bid = int(k_el.text or 0)
            except ValueError:
                continue
            bools = [
                (b.text or "").strip().lower() == "true"
                for b in bitem.findall("value/ArrayOfBoolean/boolean")
            ]
            bundle_progress[bid] = bools

        # ── 5. Build BundleState objects ──────────────────────────────────────
        state.cc_bundles = []
        for bundle_id, defn in sorted(bundle_defs.items()):
            bools     = bundle_progress.get(bundle_id, [])
            items_def = defn["items"]
            required  = defn["required"]

            bundle_items = []
            donated_count = 0
            for i, (item_id, qty, quality) in enumerate(items_def):
                start    = i * 3
                donated  = any(bools[start: start + 3]) if start + 3 <= len(bools) else False
                if donated:
                    donated_count += 1
                item_name = (
                    BUNDLE_ITEM_NAMES.get(item_id)
                    or FISH_ID_NAMES.get(item_id)
                    or f"Item #{item_id}"
                )
                bundle_items.append(BundleItem(
                    item_id=item_id, item_name=item_name,
                    quantity=qty, quality=quality, donated=donated,
                ))

            state.cc_bundles.append(BundleState(
                id=bundle_id,
                name=defn["name"],
                room=defn["room"],
                items=bundle_items,
                items_donated=donated_count,
                items_total=len(items_def),
                required=required,
                is_complete=(donated_count >= required),
            ))

    # Older saves store weatherForTomorrow as an integer enum; newer saves use
    # string names.  Both must resolve to the same string keys used by WEATHER_DESC.
    _WEATHER_INT = {"0": "Sun", "1": "Rain", "2": "Storm", "3": "Snow",
                    "4": "Wind", "5": "Festival", "6": "Wedding", "7": "GreenRain"}

    @staticmethod
    def _normalise_weather(raw: str) -> str:
        return SaveParser._WEATHER_INT.get(raw.strip(), raw.strip())


# ─────────────────────────────────────────────────────────────────────────────
# GAME STATE DIFF
# ─────────────────────────────────────────────────────────────────────────────

class GameStateDiff:
    """Compare two GameState instances and produce a human-readable activity log."""

    def __init__(self, yesterday: GameState, today: GameState):
        self.yesterday = yesterday
        self.today     = today

    def compute(self) -> dict[str, str]:
        y, t = self.yesterday, self.today
        results: dict[str, str] = {}

        # ── Finances ─────────────────────────────────────────────────────────
        money_delta  = t.money - y.money
        earned_delta = t.total_money_earned - y.total_money_earned

        if money_delta > 0:
            results["money_gained"] = f"Your wallet grew by {money_delta:,}g (now {t.money:,}g)."
        elif money_delta < 0:
            results["money_spent"]  = f"You spent {abs(money_delta):,}g (wallet: {t.money:,}g)."

        if earned_delta > 0:
            results["money_earned"] = f"Total earnings +{earned_delta:,}g from sales/rewards."

        # ── Statistics ───────────────────────────────────────────────────────
        STAT_MESSAGES = [
            ("stone_gathered",   "{n:,} stone gathered."),
            ("rocks_crushed",    "{n:,} rocks/nodes crushed in the mines."),
            ("times_fished",     "Fished {n:,} time(s)."),
            ("items_shipped",    "{n:,} item(s) shipped to Pierre's box."),
            ("crops_shipped",    "{n:,} crop(s) shipped."),
            ("items_foraged",    "{n:,} foraged item(s) collected."),
            ("monsters_killed",  "{n:,} monster(s) defeated."),
            ("items_crafted",    "{n:,} item(s) crafted."),
            ("gifts_given",      "{n:,} gift(s) given to villagers."),
            ("weeds_eliminated", "{n:,} weeds cleared."),
            ("dirt_hoed",        "{n:,} soil tile(s) hoed."),
            ("geodes_cracked",   "{n:,} geode(s) cracked at Clint's."),
            ("items_cooked",     "{n:,} meal(s) cooked."),
        ]

        for attr, template in STAT_MESSAGES:
            delta = getattr(t, attr) - getattr(y, attr)
            if delta > 0:
                results[attr] = template.format(n=delta)

        # ── Skills ───────────────────────────────────────────────────────────
        SKILL_ATTRS = [
            ("farming_level",  "Farming"),
            ("fishing_level",  "Fishing"),
            ("foraging_level", "Foraging"),
            ("mining_level",   "Mining"),
            ("combat_level",   "Combat"),
        ]
        for attr, label in SKILL_ATTRS:
            delta = getattr(t, attr) - getattr(y, attr)
            if delta > 0:
                results[f"skill_{attr}"] = (
                    f"[LEVEL UP] {label} reached level {getattr(t, attr)}!"
                )

        # ── Quests ───────────────────────────────────────────────────────────
        y_quests = {q.title: q for q in y.quests}
        t_quests = {q.title: q for q in t.quests}

        for title, q in t_quests.items():
            if q.completed and (title not in y_quests or not y_quests[title].completed):
                reward = f" (+{q.money_reward:,}g)" if q.money_reward > 0 else ""
                results[f"quest_done_{title}"] = f"[QUEST COMPLETE] '{title}'{reward}."

        for title, q in t_quests.items():
            if title not in y_quests:
                results[f"quest_new_{title}"] = f"[NEW QUEST] '{title}' added to your log."

        # ── Friendships ──────────────────────────────────────────────────────
        y_friends = {f.npc: f for f in y.friendship}
        t_friends = {f.npc: f for f in t.friendship}

        for npc, tf in t_friends.items():
            yf = y_friends.get(npc)
            if yf:
                delta = tf.points - yf.points
                if delta > 0:
                    hearts = tf.points // 250
                    results[f"friend_{npc}"] = (
                        f"Friendship with {npc} +{delta} pts → {hearts} heart(s) ({tf.points} total)."
                    )
            else:
                results[f"met_{npc}"] = f"You met {npc} for the first time!"

        # ── Dialogue Events (new ones, excluding memory markers) ─────────────
        new_events = set(t.dialogue_events) - set(y.dialogue_events)
        clean_events = [e for e in new_events if not e.endswith("_memory_oneday")]
        if clean_events:
            results["dialogue"] = f"New story moments triggered: {', '.join(clean_events)}."

        # ── New fish species caught ───────────────────────────────────────────
        new_fish = set(t.fish_caught) - set(y.fish_caught)
        if new_fish:
            results["new_fish"] = f"New fish species caught: {', '.join(sorted(new_fish))}."

        # ── Bundle progress ───────────────────────────────────────────────────
        y_bundles = {b.id: b for b in y.cc_bundles}
        t_bundles = {b.id: b for b in t.cc_bundles}
        for bid, tb in t_bundles.items():
            yb = y_bundles.get(bid)
            if yb and tb.is_done() and not yb.is_done():
                results[f"bundle_done_{bid}"] = (
                    f"[BUNDLE COMPLETE] '{tb.name}' ({tb.room}) completed!"
                )
            elif yb and tb.items_donated > yb.items_donated:
                delta = tb.items_donated - yb.items_donated
                results[f"bundle_prog_{bid}"] = (
                    f"Bundle '{tb.name}': +{delta} item(s) donated "
                    f"({tb.items_donated}/{tb.required} needed)."
                )

        return results

    def as_text(self) -> str:
        diff = self.compute()
        if not diff:
            return "(Nothing notable recorded for yesterday.)"
        lines = ["=== Yesterday's Accomplishments ==="]
        lines += [f"  * {v}" for v in diff.values()]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# MORNING BRIEF
# ─────────────────────────────────────────────────────────────────────────────

class MorningBrief:
    """Format a GameState into a structured Morning Brief."""

    # (low_inclusive, high_exclusive, label, coaching_tip)
    LUCK_BANDS = [
        (-1.00, -0.07, "Very Bad",  "Stay home — skip the mines, avoid the casino today."),
        (-0.07, -0.02, "Bad",       "Keep it safe: farm chores and social visits only."),
        (-0.02,  0.02, "Neutral",   "Average day — work on whatever you need most."),
        ( 0.02,  0.07, "Good",      "Good luck! Try deeper mine levels or fishing."),
        ( 0.07,  1.00, "Very Good", "Exceptional luck! Hit Skull Cavern or buy lottery tickets."),
    ]

    WEATHER_DESC = {
        "Sun":      "Sunny -- remember to water your crops.",
        "Rain":     "Rainy -- crops water themselves, great day for the mines!",
        "Storm":    "Thunderstorm -- fish at the beach pier for legend catches.",
        "Snow":     "Snowy -- winter day, focus on the mines or community center.",
        "Wind":     "Windy -- foraging items appear; watch for Spring/Fall debris.",
        "Festival": "Festival day -- check the calendar for the event location.",
        "Wedding":  "Wedding day -- congratulations!",
        "GreenRain":"Green Rain -- forage rare items in Cindersap Forest.",
    }

    def __init__(self, state: GameState):
        self.state = state

    def _luck_info(self) -> tuple[str, str]:
        luck = self.state.daily_luck
        for lo, hi, label, tip in self.LUCK_BANDS:
            if lo <= luck < hi:
                return label, tip
        return "Neutral", "An average day."

    def _weather_desc(self) -> str:
        return self.WEATHER_DESC.get(
            self.state.weather_tomorrow,
            f"{self.state.weather_tomorrow}."
        )

    def as_dict(self) -> dict:
        s = self.state
        luck_label, luck_tip = self._luck_info()
        active_quests  = [q for q in s.quests if not q.completed]
        top_friends    = sorted(s.friendship, key=lambda f: f.points, reverse=True)[:6]

        return {
            "date": {
                "day":    s.day,
                "season": s.season,
                "year":   s.year,
                "label":  f"Day {s.day}, {s.season}, Year {s.year}",
            },
            "luck": {
                "value":  round(s.daily_luck, 4),
                "label":  luck_label,
                "tip":    luck_tip,
            },
            "weather_tomorrow": {
                "key":  s.weather_tomorrow,
                "desc": self._weather_desc(),
            },
            "is_raining_now": s.is_raining,
            "finances": {
                "wallet":        s.money,
                "total_earned":  s.total_money_earned,
            },
            "skills": {
                "Farming":  s.farming_level,
                "Fishing":  s.fishing_level,
                "Foraging": s.foraging_level,
                "Mining":   s.mining_level,
                "Combat":   s.combat_level,
            },
            "active_quests": [
                {
                    "title":  q.title,
                    "reward": q.money_reward,
                }
                for q in active_quests
            ],
            "top_friendships": [
                {
                    "npc":    f.npc,
                    "points": f.points,
                    "hearts": f.points // 250,
                    "status": f.status,
                }
                for f in top_friends
            ],
            "cumulative_stats": {
                "stone_gathered":   s.stone_gathered,
                "rocks_crushed":    s.rocks_crushed,
                "items_shipped":    s.items_shipped,
                "times_fished":     s.times_fished,
                "monsters_killed":  s.monsters_killed,
                "items_crafted":    s.items_crafted,
                "gifts_given":      s.gifts_given,
                "days_played":      s.days_played,
            },
            "identity": {
                "farmer_name": s.farmer_name,
                "farm_name":   s.farm_name,
                "gender":      s.gender,
                "pet_type":    s.pet_type,
            },
            "vitals": {
                "health":      s.health,
                "max_health":  s.max_health,
                "health_pct":  round(s.health / s.max_health * 100, 1) if s.max_health else 0.0,
                "stamina":     int(s.stamina),
                "max_stamina": s.max_stamina,
                "stamina_pct": round(s.stamina / s.max_stamina * 100, 1) if s.max_stamina else 0.0,
            },
            "progression": {
                "deepest_mine_level":        s.deepest_mine_level,
                "mine_lowest_level_reached": s.mine_lowest_level_reached,
                "house_upgrade_level":       s.house_upgrade_level,
                "house_label":               HOUSE_UPGRADE_LABELS.get(s.house_upgrade_level, "Unknown"),
                "has_skull_key":             s.has_skull_key,
                "has_rusty_key":             s.has_rusty_key,
                "has_special_charm":         s.has_special_charm,
                "can_understand_dwarves":    s.can_understand_dwarves,
                "golden_walnuts_found":      s.golden_walnuts_found,
                "golden_walnuts_remaining":  s.golden_walnuts,
            },
            "inventory_summary": {
                "total_items": len(s.inventory_items),
                "tools": [
                    {"name": it["name"], "upgrade_level": it["upgrade_level"]}
                    for it in s.inventory_items if it["category"] == -99
                ],
                "seeds": [
                    {"name": it["name"], "stack": it["stack"]}
                    for it in s.inventory_items if it["category"] == -74
                ],
                "resources": [
                    {"name": it["name"], "stack": it["stack"]}
                    for it in s.inventory_items if it["category"] == -16
                ],
            },
            "recipes": {
                "cooking_known":  s.recipes_cooking_count,
                "crafting_known": s.recipes_crafting_count,
            },
            "professions": [
                {"id": pid, "name": PROFESSION_NAMES.get(pid, f"Unknown({pid})")}
                for pid in s.professions
            ],
            "skills_detail": {
                name: {
                    "level": getattr(s, f"{name.lower()}_level"),
                    **_xp_progress(
                        s.experience_points[i] if i < len(s.experience_points) else 0,
                        getattr(s, f"{name.lower()}_level"),
                    )
                }
                for i, name in enumerate(["Farming", "Fishing", "Foraging", "Mining", "Combat"])
            },
            "fish_collection": {
                "total_species": len(s.fish_caught),
                "species": sorted(s.fish_caught.keys()),
            },
            "catchable_fish_today": [
                {"name": name, "location": loc, "note": note}
                for name, loc, note in get_catchable_fish(s.season, s.is_raining, s.fishing_level)
            ],
            "community_center": {
                "rooms_complete": s.cc_rooms_complete,
                "rooms_done": sum(s.cc_rooms_complete) if s.cc_rooms_complete else 0,
                "rooms_total": len(s.cc_rooms_complete),
                "all_complete": all(s.cc_rooms_complete) if s.cc_rooms_complete else False,
                "bundles": [
                    {
                        "id":          b.id,
                        "name":        b.name,
                        "room":        b.room,
                        "donated":     b.items_donated,
                        "required":    b.required,
                        "total":       b.items_total,
                        "is_complete": b.is_done(),
                        "missing": [
                            {"name": it.item_name, "qty": it.quantity, "quality": it.quality}
                            for it in b.missing_items()
                        ],
                    }
                    for b in s.cc_bundles
                ],
            },
        }

    def as_text(self) -> str:
        d  = self.as_dict()
        s  = self.state
        luck_label, luck_tip = self._luck_info()
        W  = 46  # box width (inner)

        def row(left: str, right: str = "", width: int = W) -> str:
            content = f"  {left:<{width - len(right) - 2}}{right}"
            return f"|{content[:width]}|"

        def divider(char: str = "-") -> str:
            return f"+{char * W}+"

        wallet_str = f"{s.money:,}g"
        earned_str = f"{s.total_money_earned:,}g earned all-time"

        lines = [
            divider("="),
            f"|{'  MORNING BRIEF':^{W}}|",
            f"|{'  ' + d['date']['label']:^{W}}|",
            divider("-"),
            row(f"  Wallet:    {wallet_str}"),
            row(f"  Luck:      {luck_label} ({s.daily_luck:+.3f})"),
            row(f"  Tip:       {luck_tip[:W - 13]}"),
            row(f"  Tomorrow:  {self._weather_desc()[:W - 13]}"),
            divider("-"),
            f"|{'  SKILLS':^{W}}|",
            row(
                f"  Farm:{s.farming_level}  Fish:{s.fishing_level}  "
                f"Forage:{s.foraging_level}  Mine:{s.mining_level}  "
                f"Combat:{s.combat_level}"
            ),
            divider("-"),
            f"|{'  ACTIVE QUESTS':^{W}}|",
        ]

        active = [q for q in s.quests if not q.completed]
        if active:
            for q in active:
                reward = f"  [{q.money_reward:,}g]" if q.money_reward > 0 else ""
                title  = q.title[: W - 6 - len(reward)]
                lines.append(row(f"  * {title}{reward}"))
        else:
            lines.append(row("  * (no active quests)"))

        lines += [
            divider("-"),
            f"|{'  TOP RELATIONSHIPS':^{W}}|",
        ]

        top = sorted(s.friendship, key=lambda f: f.points, reverse=True)[:5]
        if top:
            for f in top:
                hearts = min(f.points // 250, 14)
                bar    = ("*" * hearts).ljust(14)
                lines.append(row(f"  {f.npc:<12} {f.points:>5}pts  [{bar}]"))
        else:
            lines.append(row("  (no relationships yet)"))

        lines.append(divider("="))
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# LLM PROMPT BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_llm_prompt(brief: MorningBrief, diff: Optional[GameStateDiff] = None) -> str:
    """
    Build a prompt ready to send to Claude, Gemini, or any LLM.
    The model will act as a Stardew Valley coach giving a personalised walkthrough.

    Usage example (Anthropic SDK):
        import anthropic
        client = anthropic.Anthropic()
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            messages=[{"role": "user", "content": build_llm_prompt(brief, diff)}]
        )
        print(response.content[0].text)
    """
    s             = brief.state
    d             = brief.as_dict()
    brief_json    = json.dumps(d, indent=2)
    recap_section = diff.as_text() if diff else "(First session — no previous data.)"
    luck_label, _ = brief._luck_info()

    # ── Mine depth hint ───────────────────────────────────────────────────────
    mine_level = s.deepest_mine_level
    if mine_level == 0:
        mine_hint = "Has not entered the mines yet."
    elif mine_level < 40:
        mine_hint = f"Reached mine floor {mine_level} (copper zone, floors 1–39)."
    elif mine_level < 80:
        mine_hint = f"Reached mine floor {mine_level} (iron zone, floors 40–79)."
    elif mine_level < 120:
        mine_hint = f"Reached mine floor {mine_level} (gold zone, nearing the bottom)."
    else:
        mine_hint = f"Cleared the regular mines (floor {mine_level}) — Skull Cavern accessible."

    # ── Professions summary ───────────────────────────────────────────────────
    if s.professions:
        prof_names = [PROFESSION_NAMES.get(p, str(p)) for p in s.professions]
        prof_hint  = ", ".join(prof_names)
    else:
        prof_hint = "None yet (requires level 5+ in a skill)"

    # ── Tool summary ──────────────────────────────────────────────────────────
    tools = d.get("inventory_summary", {}).get("tools", [])
    tool_str = ", ".join(
        f"{t['name']}(L{t['upgrade_level']})" if t.get("upgrade_level") is not None
        else t["name"]
        for t in tools
    ) or "Standard starter tools"

    # ── Seeds in bag ─────────────────────────────────────────────────────────
    seeds = d.get("inventory_summary", {}).get("seeds", [])
    seed_str = ", ".join(f"{it['name']} x{it['stack']}" for it in seeds) or "None"

    # ── Skills close to leveling up (≥75% progress) ───────────────────────────
    levelup_hints = []
    for i, skill_name in enumerate(["Farming", "Fishing", "Foraging", "Mining", "Combat"]):
        lvl = getattr(s, f"{skill_name.lower()}_level")
        if lvl < 10:
            xp   = s.experience_points[i] if i < len(s.experience_points) else 0
            prog = _xp_progress(xp, lvl)
            if prog["progress_pct"] >= 75.0:
                levelup_hints.append(
                    f"{skill_name} level {lvl} → {lvl + 1} "
                    f"({prog['progress_pct']}%, {prog['xp_to_next']} XP to go)"
                )
    skill_levelup_section = (
        "Skills close to leveling up:\n" + "\n".join(f"  - {h}" for h in levelup_hints)
        if levelup_hints
        else "No skills close to leveling up."
    )

    # ── Fish availability today ────────────────────────────────────────────────
    catchable = get_catchable_fish(s.season, s.is_raining, s.fishing_level)
    if catchable:
        weather_label = "rainy" if s.is_raining else "sunny"
        fish_lines = "\n".join(
            f"  - {name} — {loc}{(' ' + note) if note else ''}"
            for name, loc, note in catchable[:15]
        )
        fish_section = (
            f"Fish catchable today ({s.season}, {weather_label}):\n{fish_lines}"
        )
        if len(catchable) > 15:
            fish_section += f"\n  … and {len(catchable) - 15} more"
    else:
        fish_section = f"No fish catchable in {s.season} with current weather."

    if s.fish_caught:
        species_list = sorted(s.fish_caught.keys())
        fish_caught_str = (
            f"{len(species_list)} species caught — "
            + ", ".join(species_list[:10])
            + (f" (+{len(species_list) - 10} more)" if len(species_list) > 10 else "")
        )
    else:
        fish_caught_str = "No fish caught yet."

    # ── Community Center bundle status ────────────────────────────────────────
    if s.cc_bundles:
        rooms_done  = sum(s.cc_rooms_complete) if s.cc_rooms_complete else 0
        rooms_total = len(s.cc_rooms_complete) if s.cc_rooms_complete else 6
        cc_header   = f"Community Center: {rooms_done}/{rooms_total} rooms complete"
        incomplete  = [b for b in s.cc_bundles if not b.is_done()]
        if not incomplete:
            cc_section = f"{cc_header}\n  All bundles complete — congratulations!"
        else:
            close = sorted(incomplete, key=lambda b: b.items_donated / max(b.required, 1), reverse=True)[:5]
            bundle_lines = []
            for b in close:
                missing = b.missing_items()
                missing_str = ", ".join(
                    f"{it.item_name} x{it.quantity}" for it in missing[:4]
                )
                if len(missing) > 4:
                    missing_str += f" (+{len(missing) - 4} more)"
                bundle_lines.append(
                    f"  - {b.name} ({b.room}): {b.items_donated}/{b.required} donated"
                    + (f" — still need: {missing_str}" if missing_str else "")
                )
            cc_section = f"{cc_header}\n  Closest to completion:\n" + "\n".join(bundle_lines)
            if len(incomplete) > 5:
                cc_section += f"\n  … and {len(incomplete) - 5} more incomplete bundles"
    else:
        cc_section = "Community Center: bundle data unavailable (save not yet loaded)."

    # ── Ginger Island walnut hint (only if player has found any) ─────────────
    walnut_line = ""
    if s.golden_walnuts_found > 0:
        walnut_line = (
            f"\n- Ginger Island: {s.golden_walnuts_found} Golden Walnuts found, "
            f"{s.golden_walnuts} remaining to spend."
        )

    # ── Vitals hint (only shown if depleted) ─────────────────────────────────
    vitals_line = ""
    if s.max_health and s.health < s.max_health:
        vitals_line += f"\n- Health: {s.health}/{s.max_health} (depleted — avoid risky combat today)."
    if s.max_stamina and int(s.stamina) < s.max_stamina:
        vitals_line += f"\n- Stamina: {int(s.stamina)}/{s.max_stamina} (depleted)."

    house_label  = HOUSE_UPGRADE_LABELS.get(s.house_upgrade_level, "Unknown")
    unlock_flags = ", ".join(filter(None, [
        "Skull Key"   if s.has_skull_key          else "",
        "Rusty Key"   if s.has_rusty_key           else "",
        "Special Charm" if s.has_special_charm     else "",
        "Dwarf Language" if s.can_understand_dwarves else "",
    ])) or "None"

    prompt = f"""You are a warm, knowledgeable Stardew Valley coach helping a player plan their day.

## Player Profile
- Farmer: {s.farmer_name or "Unknown"} | Farm: {s.farm_name or "Unknown"} | Pet: {s.pet_type or "Unknown"}
- House: {house_label} (upgrade level {s.house_upgrade_level}/3)
- Professions: {prof_hint}
- Unlocks obtained: {unlock_flags}
- Mine progress: {mine_hint}
- Recipes known: {s.recipes_cooking_count} cooking, {s.recipes_crafting_count} crafting
- Tools: {tool_str}
- Seeds in bag: {seed_str}{walnut_line}{vitals_line}

## Yesterday's Recap
{recap_section}

## Today's Morning Brief (full structured data)
```json
{brief_json}
```

## Skill Progress
{skill_levelup_section}

## Fishing
{fish_section}
Fish collection: {fish_caught_str}

## Community Center Progress
{cc_section}

## Your Task
Write a friendly, personalised **Daily Walkthrough** for Day {s.day} of {s.season}, Year {s.year}.

Structure your response EXACTLY as follows:

### Good Morning!
A short (2-3 sentence) encouraging opener that references today's luck ({luck_label}),
the weather ({d['weather_tomorrow']['desc']}), and any big wins from yesterday.
Mention {s.farmer_name or "the farmer"}'s current stage ({house_label}, {mine_hint.lower()}).

### Top Priorities
Numbered list of 3-5 specific, actionable tasks ranked by importance.
Base them on: active quests, current season, skill levels, daily luck, tools, mine progress, seeds in bag, catchable fish today, and incomplete CC bundles.
Include *why* each task matters right now AND specific items/locations to target.
If any skill is close to leveling ({skill_levelup_section.splitlines()[0]}), suggest activities that grant that XP.
If bundle items are in season or catchable today, call that out explicitly.

### Social Round
Which 1-3 villagers to visit today, and what to bring (gifts, conversation topics).
Check the friendship data above and prioritise anyone below 4 hearts or with social quests active.

### Evening Checklist
2-3 things to do before bed (watering, shipping bin, tool upgrade at Clint's, etc.).
Reference the player's current tools: {tool_str}.

### Coach's Tip
One strategic insight tailored to their exact progress (Day {s.day}, {s.season}, Year {s.year}).
Consider their mine depth, house level ({s.house_upgrade_level}/3), and chosen professions ({prof_hint}).
Think ahead: what should they be building toward over the next week?

Keep it practical, specific, and encouraging. Use actual numbers from the data above.
"""
    return prompt


# ─────────────────────────────────────────────────────────────────────────────
# FILE WATCHER (watchdog)
# ─────────────────────────────────────────────────────────────────────────────

class SaveFileHandler(FileSystemEventHandler):
    """Watchdog event handler that fires whenever the SaveGameInfo file changes."""

    def __init__(self, watch_filename: str, agent: "GameStateAgent"):
        super().__init__()
        self._watch = watch_filename   # e.g. "SaveGameInfo"
        self._agent = agent
        self._last_fire = 0.0          # debounce timestamp

    def on_modified(self, event):
        if event.is_directory:
            return
        if Path(event.src_path).name == self._watch:
            now = time.monotonic()
            # Debounce: ignore duplicate events within 3 seconds
            if now - self._last_fire < 3.0:
                return
            self._last_fire = now
            log.info(f"Save change detected: {event.src_path}")
            # Small delay so the game finishes writing all files
            time.sleep(1.5)
            self._agent.on_save_detected()


# ─────────────────────────────────────────────────────────────────────────────
# GAME STATE AGENT
# ─────────────────────────────────────────────────────────────────────────────

class GameStateAgent:
    """
    Main agent: discovers the save folder, parses current + previous state,
    diffs them, and emits the Morning Brief.
    """

    def __init__(
        self,
        saves_dir: Path,
        output_dir: Optional[Path] = None,
    ):
        self.saves_dir   = saves_dir
        self.save_folder = self._find_save_folder()
        # Output dir: caller can override; defaults to ../output relative to saves_dir
        self.output_dir  = output_dir or (saves_dir.parent / "output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._observer: Optional[Observer] = None
        log.info(f"Save folder: {self.save_folder}")
        log.info(f"Output dir:  {self.output_dir}")

    # ── Discovery ─────────────────────────────────────────────────────────────

    def _find_save_folder(self) -> Path:
        """Return the most recently modified save folder."""
        folders = [f for f in self.saves_dir.iterdir() if f.is_dir()]
        if not folders:
            raise FileNotFoundError(f"No save folders found in {self.saves_dir}")
        return max(folders, key=lambda f: f.stat().st_mtime)

    # ── Parsing ───────────────────────────────────────────────────────────────

    def parse_current(self) -> GameState:
        return SaveParser(self.save_folder, use_old=False).parse()

    def parse_previous(self) -> Optional[GameState]:
        parser = SaveParser(self.save_folder, use_old=True)
        if not parser.exists():
            log.info("No _old save files found — skipping yesterday's diff.")
            return None
        return parser.parse()

    # ── Analysis ──────────────────────────────────────────────────────────────

    def on_save_detected(self) -> None:
        """Run a full analysis cycle (parse → diff → brief → prompt)."""
        log.info("Running analysis…")
        try:
            today     = self.parse_current()
            yesterday = self.parse_previous()

            print()
            print("=" * 50)

            # Diff
            diff = None
            if yesterday:
                diff = GameStateDiff(yesterday, today)
                print(diff.as_text())
                print()

            # Morning Brief (text)
            brief = MorningBrief(today)
            print(brief.as_text())
            print()

            # Morning Brief (JSON) → output/
            brief_json = json.dumps(brief.as_dict(), indent=2, ensure_ascii=False)
            json_path  = self.output_dir / "morning_brief.json"
            json_path.write_text(brief_json, encoding="utf-8")
            log.info(f"Brief saved → {json_path}")

            # LLM Prompt → output/
            prompt      = build_llm_prompt(brief, diff)
            prompt_path = self.output_dir / "coach_prompt.txt"
            prompt_path.write_text(prompt, encoding="utf-8")
            log.info(f"LLM prompt saved → {prompt_path}")

            print("--- LLM Coach Prompt preview (first 400 chars) ---")
            print(prompt[:400])
            print("  [... full prompt saved to coach_prompt.txt]")
            print("=" * 50)

        except Exception:
            log.exception("Error during analysis — check the save files.")

    # ── Run Modes ─────────────────────────────────────────────────────────────

    def run_once(self) -> None:
        """Analyse the current save once and exit."""
        self.on_save_detected()

    def start_watching(self) -> None:
        """Block and watch for new saves, re-analysing on each sleep."""
        if not WATCHDOG_AVAILABLE:
            print(
                "ERROR: watchdog not installed. Run:  pip install watchdog\n"
                "       Or use --once to analyse the current save without watching."
            )
            sys.exit(1)

        handler  = SaveFileHandler("SaveGameInfo", self)
        observer = Observer()
        observer.schedule(handler, str(self.save_folder), recursive=False)
        observer.start()

        print(f"\nWatching: {self.save_folder}")
        print("Go play! The agent will analyse each time you sleep in-game.")
        print("Press Ctrl+C to stop.\n")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            observer.stop()
            observer.join()
            log.info("Watcher stopped.")


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Stardew Valley Game State Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--saves-dir",
        type=Path,
        default=DEFAULT_SAVES_DIR,
        help=f"Path to your StardewValley/Saves folder (default: {DEFAULT_SAVES_DIR})",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Analyse the current save once and exit (no watching).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the Morning Brief as JSON to stdout instead of formatted text.",
    )
    args = parser.parse_args()

    saves_dir = args.saves_dir.expanduser().resolve()
    if not saves_dir.exists():
        print(f"ERROR: Saves directory not found: {saves_dir}")
        print("       Use --saves-dir to point at your Saves folder.")
        sys.exit(1)

    agent = GameStateAgent(saves_dir)

    if args.json:
        # JSON-only output mode
        state = agent.parse_current()
        brief = MorningBrief(state)
        print(json.dumps(brief.as_dict(), indent=2, ensure_ascii=False))
        return

    if args.once:
        agent.run_once()
    else:
        agent.start_watching()


if __name__ == "__main__":
    main()
