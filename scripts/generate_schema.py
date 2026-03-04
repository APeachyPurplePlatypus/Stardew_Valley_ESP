#!/usr/bin/env python3
"""
Generate a comprehensive schema template of all extractable Stardew Valley save data.

Reads the most recently modified save folder (or a specified one) and writes
output/game_state_schema.json — a fully annotated snapshot of every field
the save files expose, with current values and type metadata.

_old files are never read. Only the current save files are used.

Usage:
    python scripts/generate_schema.py                              # latest save
    python scripts/generate_schema.py --saves-dir saves            # local dev saves
    python scripts/generate_schema.py --saves-dir saves --save Pelican_350931629
    python scripts/generate_schema.py --saves-dir saves --output my_schema.json
"""

import json
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

_REPO = Path(__file__).parent.parent
DEFAULT_SAVES = _REPO / "saves"

_NS = "{http://www.w3.org/2001/XMLSchema-instance}"

SEASONS = {0: "Spring", 1: "Summer", 2: "Fall", 3: "Winter"}
SEASON_NAMES = {"spring": "Spring", "summer": "Summer", "fall": "Fall", "winter": "Winter"}

XP_THRESHOLDS = [0, 100, 380, 770, 1300, 2150, 3300, 4800, 6900, 10000, 15000]
SKILL_NAMES   = ["Farming", "Fishing", "Foraging", "Mining", "Combat", "Luck"]

PROFESSION_NAMES = {
    0: "Rancher",      1: "Tiller",        2: "Coopmaster",   3: "Shepherd",
    4: "Artisan",      5: "Agriculturist",  6: "Fisher",       7: "Trapper",
    8: "Angler",       9: "Pirate",        10: "Mariner",     11: "Luremaster",
    12: "Forester",   13: "Gatherer",      14: "Lumberjack",  15: "Tapper",
    16: "Botanist",   17: "Tracker",       18: "Miner",       19: "Geologist",
    20: "Blacksmith", 21: "Prospector",    22: "Excavator",   23: "Gemologist",
    24: "Fighter",    25: "Scout",         26: "Brute",       27: "Defender",
    28: "Acrobat",    29: "Desperado",
}

HOUSE_UPGRADE_LABELS = {0: "Cabin", 1: "Kitchen", 2: "Cellar", 3: "Full House"}

STAT_MAP = {
    "stoneGathered":   "stone_gathered",
    "itemsShipped":    "items_shipped",
    "rocksCrushed":    "rocks_crushed",
    "timesFished":     "times_fished",
    "stepsTaken":      "steps_taken",
    "daysPlayed":      "days_played",
    "cropsShipped":    "crops_shipped",
    "itemsForaged":    "items_foraged",
    "monstersKilled":  "monsters_killed",
    "itemsCrafted":    "items_crafted",
    "giftsGiven":      "gifts_given",
    "weedsEliminated": "weeds_eliminated",
    "dirtHoed":        "dirt_hoed",
    "geodesCracked":   "geodes_cracked",
    "itemsCooked":     "items_cooked",
    "averageBedtime":  "average_bedtime",
    "millisecondsPlayed": "milliseconds_played",
    "timesUnconscious":   "times_unconscious",
    "timesFarmed":        "times_farmed",
}

WEATHER_NAMES = {
    "0": "Sun", "1": "Rain", "2": "Storm", "3": "Snow",
    "4": "Wind", "5": "Festival", "6": "Wedding", "7": "GreenRain",
}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _xp_to_level(xp: int) -> int:
    level = 0
    for threshold in XP_THRESHOLDS[1:]:
        if xp >= threshold:
            level += 1
        else:
            break
    return min(level, 10)


def _xp_progress(xp: int, level: int) -> dict:
    if level >= 10:
        return {"current_xp": xp, "xp_to_next": 0, "progress_pct": 100.0}
    t_cur  = XP_THRESHOLDS[level]
    t_next = XP_THRESHOLDS[level + 1]
    needed = t_next - t_cur
    pct    = round((xp - t_cur) / needed * 100, 1) if needed else 100.0
    return {
        "current_xp":  xp,
        "xp_to_next":  max(0, t_next - xp),
        "xp_needed_for_level": needed,
        "progress_pct": pct,
    }


def _get_nil_bool(root, path: str) -> bool:
    """Return True only if element exists, is NOT xsi:nil, and its text is 'true'."""
    el = root.find(path)
    if el is None or el.get(f"{_NS}nil") == "true":
        return False
    return (el.text or "").strip().lower() == "true"


def _get(root, path: str, default: str = "") -> str:
    el = root.find(path)
    return (el.text or "").strip() if el is not None else default


def _geti(root, path: str, default: int = 0) -> int:
    try:
        return int(_get(root, path, str(default)))
    except (ValueError, TypeError):
        return default


def _getf(root, path: str, default: float = 0.0) -> float:
    try:
        return float(_get(root, path, str(default)))
    except (ValueError, TypeError):
        return default


def _find_save_folder(saves_dir: Path, save_name: str = "") -> Path:
    """Return the specified or most recently modified save folder.
    Never selects folders ending in _old."""
    if save_name:
        folder = saves_dir / save_name
        if not folder.is_dir():
            raise FileNotFoundError(f"Save folder not found: {folder}")
        return folder
    # Filter out any folder ending in _old (safety rule)
    folders = [f for f in saves_dir.iterdir() if f.is_dir() and not f.name.endswith("_old")]
    if not folders:
        raise FileNotFoundError(f"No save folders found in {saves_dir}")
    return max(folders, key=lambda f: f.stat().st_mtime)


def _find_world_file(folder: Path) -> Path:
    """Find the world save file inside the folder, never selecting _old files."""
    candidates = [
        f for f in folder.iterdir()
        if f.is_file()
        and not f.name.endswith("_old")        # never read _old files
        and f.name != "SaveGameInfo"            # that's the farmer file
        and not f.suffix                        # world file has no extension
    ]
    if not candidates:
        raise FileNotFoundError(f"No world save file found in {folder}")
    # Prefer the file that matches the folder name exactly
    for c in candidates:
        if c.name == folder.name:
            return c
    return candidates[0]


# ─────────────────────────────────────────────────────────────────────────────
# FARMER SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

def build_farmer_schema(farmer_file: Path) -> dict:
    """Extract all available fields from SaveGameInfo into a schema dict."""
    tree = ET.parse(farmer_file)
    root = tree.getroot()  # <Farmer>

    # ── Identity ──────────────────────────────────────────────────────────────
    farmer_name = _get(root, "name")
    farm_name   = _get(root, "farmName")

    gender = ""
    g_el = root.find("Gender")
    if g_el is None:
        g_el = root.find("gender")
    if g_el is not None and g_el.get(f"{_NS}nil") != "true":
        gender = (g_el.text or "").strip()
    else:
        im_el = root.find("isMale")
        if im_el is not None and im_el.get(f"{_NS}nil") != "true":
            gender = "Male" if (im_el.text or "").lower() == "true" else "Female"

    pet_type = ""
    p_el = root.find("whichPetType")
    if p_el is not None and p_el.get(f"{_NS}nil") != "true":
        pet_type = (p_el.text or "").strip()
    else:
        cp_el = root.find("catPerson")
        if cp_el is not None and cp_el.get(f"{_NS}nil") != "true":
            pet_type = "Cat" if (cp_el.text or "").lower() == "true" else "Dog"

    # ── Date ──────────────────────────────────────────────────────────────────
    day          = _geti(root, "dayOfMonthForSaveGame")
    season_idx   = _geti(root, "seasonForSaveGame")
    season       = SEASONS.get(season_idx, "Spring")
    year         = _geti(root, "yearForSaveGame")

    # ── Finances ──────────────────────────────────────────────────────────────
    money              = _geti(root, "money")
    total_money_earned = _geti(root, "totalMoneyEarned")

    # ── Vitals ────────────────────────────────────────────────────────────────
    health      = _geti(root, "health", 100)
    max_health  = _geti(root, "maxHealth", 100)
    stamina     = _getf(root, "stamina", 270.0)
    max_stamina = _geti(root, "maxStamina", 270)

    # ── Skill levels ──────────────────────────────────────────────────────────
    skill_levels = {
        "Farming":  _geti(root, "farmingLevel"),
        "Fishing":  _geti(root, "fishingLevel"),
        "Foraging": _geti(root, "foragingLevel"),
        "Mining":   _geti(root, "miningLevel"),
        "Combat":   _geti(root, "combatLevel"),
        "Luck":     _geti(root, "luckLevel"),
    }

    # ── Experience points (raw XP, array of 6) ────────────────────────────────
    raw_xp = []
    for xp_el in root.findall("experiencePoints/int"):
        try:
            raw_xp.append(int(xp_el.text or 0))
        except (ValueError, TypeError):
            raw_xp.append(0)
    while len(raw_xp) < 6:
        raw_xp.append(0)

    skills_detail = {}
    for i, name in enumerate(SKILL_NAMES):
        lvl = skill_levels.get(name, 0)
        xp  = raw_xp[i]
        skills_detail[name] = {
            "level": lvl,
            **_xp_progress(xp, lvl),
        }

    # ── Professions ───────────────────────────────────────────────────────────
    professions = []
    for p_el in root.findall("professions/int"):
        try:
            pid = int(p_el.text or 0)
            professions.append({"id": pid, "name": PROFESSION_NAMES.get(pid, f"Unknown({pid})")})
        except (ValueError, TypeError):
            pass

    # ── Progression flags ─────────────────────────────────────────────────────
    deepest_mine_level   = _geti(root, "deepestMineLevel")
    house_upgrade_level  = _geti(root, "houseUpgradeLevel")
    has_skull_key        = _get_nil_bool(root, "hasSkullKey")
    has_rusty_key        = _get_nil_bool(root, "hasRustyKey")
    has_special_charm    = _get_nil_bool(root, "hasSpecialCharm")
    can_understand_dwarves = _get_nil_bool(root, "canUnderstandDwarves")
    has_club_card        = _get_nil_bool(root, "hasClubCard")
    has_magnifying_glass = _get_nil_bool(root, "hasMagnifyingGlass")
    has_magic_ink        = _get_nil_bool(root, "hasMagicInk")
    has_dark_talisman    = _get_nil_bool(root, "hasDarkTalisman")
    has_town_key         = _get_nil_bool(root, "HasTownKey")

    # ── Inventory (full item list) ─────────────────────────────────────────────
    inventory = []
    for slot_idx, item_el in enumerate(root.findall("items/Item")):
        if item_el.get(f"{_NS}nil") == "true":
            continue
        name     = item_el.findtext("name", "") or ""
        item_id  = item_el.findtext("itemId", "") or ""
        stack    = int(item_el.findtext("stack", "1") or 1)
        category = int(item_el.findtext("category", "0") or 0)
        quality  = int(item_el.findtext("quality", "0") or 0)
        price    = int(item_el.findtext("price", "0") or 0)
        ulvl     = item_el.findtext("upgradeLevel")
        if not name:
            continue
        inventory.append({
            "slot":          slot_idx,
            "name":          name,
            "item_id":       item_id,
            "stack":         stack,
            "category":      category,
            "quality":       quality,
            "price":         price,
            "upgrade_level": int(ulvl) if ulvl is not None else None,
        })

    tools    = [it for it in inventory if it["category"] == -99]
    seeds    = [it for it in inventory if it["category"] == -74]
    resources = [it for it in inventory if it["category"] == -16]

    # ── Cooking recipes ───────────────────────────────────────────────────────
    cooking_recipes = []
    for item in root.findall("cookingRecipes/item"):
        name = item.findtext("key/string", "") or ""
        times = item.findtext("value/int", "0") or "0"
        if name:
            try:
                cooking_recipes.append({"name": name, "times_cooked": int(times)})
            except (ValueError, TypeError):
                cooking_recipes.append({"name": name, "times_cooked": 0})

    # ── Crafting recipes ──────────────────────────────────────────────────────
    crafting_recipes = []
    for item in root.findall("craftingRecipes/item"):
        name = item.findtext("key/string", "") or ""
        times = item.findtext("value/int", "0") or "0"
        if name:
            try:
                crafting_recipes.append({"name": name, "times_crafted": int(times)})
            except (ValueError, TypeError):
                crafting_recipes.append({"name": name, "times_crafted": 0})

    # ── Cumulative statistics (handles both XML formats) ──────────────────────
    cumulative_stats: dict = {v: 0 for v in STAT_MAP.values()}

    stat_set = False
    for item in root.findall("stats/Values/item"):
        key  = item.findtext("key/string", "")
        v_el = item.find("value/unsignedInt")
        if v_el is None:
            v_el = item.find("value/int")
        if key and v_el is not None and v_el.text:
            attr = STAT_MAP.get(key)
            if attr:
                try:
                    cumulative_stats[attr] = int(v_el.text)
                    stat_set = True
                except (ValueError, TypeError):
                    pass

    if not stat_set:
        lower_map = {k.lower(): v for k, v in STAT_MAP.items()}
        stats_el  = root.find("stats")
        if stats_el is not None:
            for child in stats_el:
                if child.get(f"{_NS}nil") == "true" or not child.text:
                    continue
                attr = lower_map.get(child.tag.lower())
                if attr:
                    try:
                        cumulative_stats[attr] = int(child.text)
                    except (ValueError, TypeError):
                        pass

    # ── Friendships ───────────────────────────────────────────────────────────
    friendships = []
    for item in root.findall("friendshipData/item"):
        npc    = item.findtext("key/string", "")
        points = int(item.findtext("value/Friendship/Points", "0") or 0)
        status = item.findtext("value/Friendship/Status", "Unknown") or "Unknown"
        talked = item.findtext("value/Friendship/TalkedToToday", "false") == "true"
        if npc:
            friendships.append({
                "npc":         npc,
                "points":      points,
                "hearts":      points // 250,
                "status":      status,
                "talked_today": talked,
            })
    friendships.sort(key=lambda f: f["points"], reverse=True)

    # ── Active quests ─────────────────────────────────────────────────────────
    active_quests = []
    for quest in root.findall("questLog/Quest"):
        title = (
            quest.findtext("_questTitle")
            or quest.findtext("questTitle")
            or "Unknown Quest"
        )
        completed    = quest.findtext("completed", "false") == "true"
        money_reward = int(quest.findtext("moneyReward", "0") or 0)
        active_quests.append({
            "title":        title,
            "completed":    completed,
            "money_reward": money_reward,
        })

    # ── Active dialogue events ─────────────────────────────────────────────────
    dialogue_events = {}
    for item in root.findall("activeDialogueEvents/item"):
        k    = item.findtext("key/string", "")
        v_el = item.find("value/int")
        if k and v_el is not None:
            dialogue_events[k] = int(v_el.text or 0)

    # ── Mail received (progression tracking) ──────────────────────────────────
    mail_received = [el.text for el in root.findall("mailReceived/string") if el.text]

    # ── Locations visited ─────────────────────────────────────────────────────
    locations_visited = [el.text for el in root.findall("locationsVisited/string") if el.text]

    # ── Achievements ──────────────────────────────────────────────────────────
    achievements = []
    for el in root.findall("achievements/int"):
        try:
            achievements.append(int(el.text or 0))
        except (ValueError, TypeError):
            pass

    return {
        "identity": {
            "farmer_name":   farmer_name,
            "farm_name":     farm_name,
            "gender":        gender,
            "pet_type":      pet_type,
            "game_version":  _get(root, "gameVersion"),
            "unique_id":     _get(root, "UniqueMultiplayerID"),
        },
        "date": {
            "day":          day,
            "season":       season,
            "season_index": season_idx,
            "year":         year,
            "label":        f"Day {day}, {season}, Year {year}",
            "save_time":    _geti(root, "saveTime"),
        },
        "finances": {
            "wallet":              money,
            "total_money_earned":  total_money_earned,
            "club_coins":          _geti(root, "clubCoins"),
            "qi_gems":             _geti(root, "qiGems"),
        },
        "vitals": {
            "health":      health,
            "max_health":  max_health,
            "health_pct":  round(health / max_health * 100, 1) if max_health else 0.0,
            "stamina":     int(stamina),
            "max_stamina": max_stamina,
            "stamina_pct": round(stamina / max_stamina * 100, 1) if max_stamina else 0.0,
        },
        "skills": skills_detail,
        "professions": professions,
        "progression": {
            "deepest_mine_level":     deepest_mine_level,
            "house_upgrade_level":    house_upgrade_level,
            "house_label":            HOUSE_UPGRADE_LABELS.get(house_upgrade_level, "Unknown"),
            "has_skull_key":          has_skull_key,
            "has_rusty_key":          has_rusty_key,
            "has_special_charm":      has_special_charm,
            "can_understand_dwarves": can_understand_dwarves,
            "has_club_card":          has_club_card,
            "has_magnifying_glass":   has_magnifying_glass,
            "has_magic_ink":          has_magic_ink,
            "has_dark_talisman":      has_dark_talisman,
            "has_town_key":           has_town_key,
            "achievements_unlocked":  len(achievements),
            "achievement_ids":        achievements,
            "locations_visited":      locations_visited,
            "mail_received_count":    len(mail_received),
        },
        "inventory": inventory,
        "inventory_summary": {
            "total_items": len(inventory),
            "tools":       [{"name": it["name"], "upgrade_level": it["upgrade_level"]} for it in tools],
            "seeds":       [{"name": it["name"], "stack": it["stack"]} for it in seeds],
            "resources":   [{"name": it["name"], "stack": it["stack"]} for it in resources],
        },
        "recipes": {
            "cooking_known":   len(cooking_recipes),
            "crafting_known":  len(crafting_recipes),
            "cooking_list":    cooking_recipes,
            "crafting_list":   crafting_recipes,
        },
        "cumulative_stats": cumulative_stats,
        "friendships": friendships,
        "active_quests": active_quests,
        "active_dialogue_events": dialogue_events,
    }


# ─────────────────────────────────────────────────────────────────────────────
# WORLD SCHEMA
# ─────────────────────────────────────────────────────────────────────────────

def build_world_schema(world_file: Path) -> dict:
    """Extract world-level fields from the main save file using iterparse."""
    targets = {
        "dailyLuck", "weatherForTomorrow", "isRaining",
        "isSnowing", "isLightning", "isDebrisWeather",
        "mine_lowestLevelReached", "goldenWalnuts", "goldenWalnutsFound",
        "currentSeason", "year", "dayOfMonth",
        "farmPerfect",
    }
    found: dict[str, str] = {}

    depth = 0
    for event, elem in ET.iterparse(world_file, events=("start", "end")):
        if event == "start":
            depth += 1
        else:
            depth -= 1
            if depth == 1 and elem.tag in targets and elem.tag not in found:
                found[elem.tag] = (elem.text or "").strip()
            elem.clear()
            if len(found) == len(targets):
                break

    raw_weather = found.get("weatherForTomorrow", "Sun")
    weather     = WEATHER_NAMES.get(raw_weather, raw_weather)

    season_raw  = found.get("currentSeason", "")
    season      = SEASON_NAMES.get(season_raw.lower(), season_raw) if season_raw else ""

    return {
        "daily_luck":               float(found.get("dailyLuck", 0) or 0),
        "weather_tomorrow":         weather,
        "is_raining":               found.get("isRaining", "false").lower() == "true",
        "is_snowing":               found.get("isSnowing", "false").lower() == "true",
        "is_lightning":             found.get("isLightning", "false").lower() == "true",
        "is_debris_weather":        found.get("isDebrisWeather", "false").lower() == "true",
        "current_season":           season,
        "day_of_month":             int(found.get("dayOfMonth", 0) or 0),
        "year":                     int(found.get("year", 1) or 1),
        "mine_lowest_level_reached": int(found.get("mine_lowestLevelReached", 0) or 0),
        "golden_walnuts":           int(found.get("goldenWalnuts", 0) or 0),
        "golden_walnuts_found":     int(found.get("goldenWalnutsFound", 0) or 0),
        "farm_perfect":             found.get("farmPerfect", "false").lower() == "true",
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a comprehensive schema of all Stardew Valley save data.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--saves-dir",
        type=Path,
        default=DEFAULT_SAVES,
        help=f"Path to the Saves folder (default: {DEFAULT_SAVES})",
    )
    parser.add_argument(
        "--save",
        default="",
        metavar="FOLDER_NAME",
        help="Specific save folder name (e.g. Tolkien_432258440). Default: most recently modified.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON file path (default: output/game_state_schema.json)",
    )
    args = parser.parse_args()

    saves_dir = args.saves_dir.expanduser().resolve()
    if not saves_dir.exists():
        print(f"ERROR: Saves directory not found: {saves_dir}")
        raise SystemExit(1)

    folder       = _find_save_folder(saves_dir, args.save)
    farmer_file  = folder / "SaveGameInfo"
    world_file   = _find_world_file(folder)

    if not farmer_file.exists():
        print(f"ERROR: SaveGameInfo not found in {folder}")
        raise SystemExit(1)

    print(f"Save folder : {folder}")
    print(f"Farmer file : {farmer_file.name}")
    print(f"World file  : {world_file.name}")

    farmer_schema = build_farmer_schema(farmer_file)
    world_schema  = build_world_schema(world_file)

    schema = {
        "_meta": {
            "generated_at":  datetime.now().isoformat(timespec="seconds"),
            "save_folder":   folder.name,
            "farmer_file":   farmer_file.name,
            "world_file":    world_file.name,
            "description":   (
                "Comprehensive schema of all extractable Stardew Valley save data. "
                "_old files are never read — only current save files are used."
            ),
        },
        **farmer_schema,
        "world": world_schema,
    }

    output_dir  = _REPO / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output or (output_dir / "game_state_schema.json")

    output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSchema written: {output_path}")

    # Summary
    inv_count     = len(farmer_schema.get("inventory", []))
    cooking_count = farmer_schema.get("recipes", {}).get("cooking_known", 0)
    craft_count   = farmer_schema.get("recipes", {}).get("crafting_known", 0)
    prof_count    = len(farmer_schema.get("professions", []))
    friend_count  = len(farmer_schema.get("friendships", []))
    print(
        f"  {inv_count} inventory items | "
        f"{cooking_count} cooking + {craft_count} crafting recipes | "
        f"{prof_count} professions | "
        f"{friend_count} NPCs tracked"
    )


if __name__ == "__main__":
    main()
