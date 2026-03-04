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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# OLLAMA LOCAL LLM
# ─────────────────────────────────────────────────────────────────────────────

def call_ollama(prompt: str, model: str, base_url: str) -> str:
    """Send prompt to a local Ollama instance and return the full response text."""
    import urllib.request
    import urllib.error

    payload = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
    }).encode()

    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", "").strip()
    except urllib.error.URLError as e:
        raise RuntimeError(f"Ollama not reachable at {base_url}: {e}")


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

        # Statistics — stored as <stats><Values><item><key><string>…
        for item in root.findall("stats/Values/item"):
            key  = item.findtext("key/string", "")
            # values can be <unsignedInt> or <int>
            v_el = item.find("value/unsignedInt")
            if v_el is None:
                v_el = item.find("value/int")
            if key and v_el is not None and v_el.text:
                attr = self.STAT_MAP.get(key)
                if attr:
                    setattr(state, attr, int(v_el.text))

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

    # ── World Data (from main save file) ─────────────────────────────────────

    def _parse_world(self, state: GameState) -> None:
        """
        Extract root-level world fields from the large main save file using
        iterparse so we don't load the entire tree — we stop as soon as we
        have what we need.
        """
        if not self.main_save_file.exists():
            log.warning(f"Main save file not found: {self.main_save_file}")
            return

        targets = {"dailyLuck", "weatherForTomorrow", "isRaining"}
        found: dict[str, str] = {}

        # iterparse yields (event, element) as the file is read.
        # We only care about top-level children of <SaveGame>, which appear
        # before the massive <locations> element, so this is fast in practice.
        depth = 0
        for event, elem in ET.iterparse(self.main_save_file, events=("start", "end")):
            if event == "start":
                depth += 1
            else:
                depth -= 1
                # Only capture direct children of the root (depth 0 after "end")
                if depth == 1 and elem.tag in targets and elem.tag not in found:
                    found[elem.tag] = (elem.text or "").strip()
                elem.clear()  # free memory as we go
                if len(found) == len(targets):
                    break

        state.daily_luck       = float(found.get("dailyLuck", 0))
        state.weather_tomorrow = found.get("weatherForTomorrow", "Sun")
        state.is_raining       = found.get("isRaining", "false").lower() == "true"


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
    brief_json    = json.dumps(brief.as_dict(), indent=2)
    recap_section = diff.as_text() if diff else "(First session — no previous data.)"

    prompt = f"""You are a warm, knowledgeable Stardew Valley coach helping a player plan their day.

## Yesterday's Recap
{recap_section}

## Today's Morning Brief (structured data)
```json
{brief_json}
```

## Your Task
Write a friendly, personalised **Daily Walkthrough** for Day {s.day} of {s.season}, Year {s.year}.

Structure your response EXACTLY as follows:

### Good Morning!
A short (2-3 sentence) encouraging opener that references today's luck ({brief._luck_info()[0]}),
the weather, and any big wins from yesterday.

### Top Priorities
Numbered list of 3-5 specific, actionable tasks ranked by importance.
Base them on the player's active quests, current season, skill levels, and daily luck.
Include *why* each task matters right now.

### Social Round
Which 1-3 villagers to visit today, and what to bring (gifts, conversation topics).
Prioritise anyone with low friendship points or active social quests.

### Evening Checklist
2-3 things to do before bed (watering, shipping bin, tool upgrades, etc.).

### Coach's Tip
One strategic insight tailored to their exact progress (Day {s.day}, {s.season}, Year {s.year}).
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
        ollama: bool = False,
        ollama_model: str = "ministral:8b",
        ollama_url: str = "http://localhost:11434",
    ):
        self.saves_dir    = saves_dir
        self.save_folder  = self._find_save_folder()
        # Output dir: caller can override; defaults to ../output relative to saves_dir
        self.output_dir   = output_dir or (saves_dir.parent / "output")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._observer: Optional[Observer] = None
        self.ollama       = ollama
        self.ollama_model = ollama_model
        self.ollama_url   = ollama_url
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

            # Ollama — optional local LLM response
            if self.ollama:
                print(f"\n[Ollama] Querying {self.ollama_model} ...")
                try:
                    response = call_ollama(prompt, self.ollama_model, self.ollama_url)
                    print("\n" + "=" * 60)
                    print(response)
                    print("=" * 60 + "\n")
                    response_path = self.output_dir / "coach_response.txt"
                    response_path.write_text(response, encoding="utf-8")
                    log.info(f"Coach response saved -> {response_path}")
                except RuntimeError as e:
                    print(f"[Ollama ERROR] {e}")

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
    parser.add_argument(
        "--ollama",
        action="store_true",
        help="Send the coaching prompt to a local Ollama model and print the response.",
    )
    parser.add_argument(
        "--ollama-model",
        default="ministral:8b",
        help="Ollama model tag to use (default: ministral:8b).",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434).",
    )
    args = parser.parse_args()

    saves_dir = args.saves_dir.expanduser().resolve()
    if not saves_dir.exists():
        print(f"ERROR: Saves directory not found: {saves_dir}")
        print("       Use --saves-dir to point at your Saves folder.")
        sys.exit(1)

    agent = GameStateAgent(
        saves_dir,
        ollama=args.ollama,
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
    )

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
