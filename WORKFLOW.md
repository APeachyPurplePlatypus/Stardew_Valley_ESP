# Stardew Valley ESP — Workflow & Architecture

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [Folder Structure](#2-folder-structure)
3. [Architecture](#3-architecture)
4. [Data Flow](#4-data-flow)
5. [Save File Profiles](#5-save-file-profiles)
6. [Save File Format Findings](#6-save-file-format-findings)
7. [Agent Component Reference](#7-agent-component-reference)
8. [Development Workflow](#8-development-workflow)
9. [Pending Enhancements](#9-pending-enhancements)

---

## 1. Project Overview

An automated agent that reads Stardew Valley save files, diffs the game state between days, and generates a structured Morning Brief + LLM coaching prompt. The goal is to give the player a personalised daily walkthrough each time they wake up in-game.

**Entry points:**

| Command | Purpose |
|---|---|
| `python agents/game_state_agent.py --saves-dir saves --once` | One-shot analysis (dev/test) |
| `python agents/game_state_agent.py --saves-dir saves` | Watch mode (triggers on each in-game sleep) |
| `python agents/game_state_agent.py --saves-dir saves --json` | JSON output only (for piping) |
| `python agents/game_state_agent.py` | Watch mode (reads from `%APPDATA%\StardewValley\Saves`) |
| `python agents/game_state_agent.py --live --once` | One live snapshot from stardew-mcp WebSocket |
| `python agents/game_state_agent.py --live` | Watch for in-game day changes via WebSocket |
| `python agents/game_state_agent.py --live --live-url ws://...` | Custom WebSocket URL |
| `python agents/stardew_mcp_server.py` | MCP server for Claude Desktop (stdio transport) |
| `python scripts/parse_save.py` | Dump all XML attributes to `output/Stardew_Save_Attributes.xlsx` |

**Dependencies:**
- `watchdog` (save-file watch mode only)
- `openpyxl` (parse_save.py only)
- `websockets` (live WebSocket mode)
- `mcp` (Claude Desktop MCP server)
- `anthropic` (optional — only for `run_coaching_agent` tool)

---

## 2. Folder Structure

```
Stardew_Valley_ESP/
├── agents/                     # Autonomous agent scripts
│   ├── game_state_agent.py     # Main Game State Agent (see §3)
│   └── stardew_mcp_server.py   # MCP server for Claude Desktop
│
├── scripts/                    # Utility / analysis scripts
│   └── parse_save.py           # XML → Excel attribute dumper
│
├── saves/                      # Stardew Valley save folders (gitignored content)
│   ├── Tolkien_432258440/      # Beginner save profile (Day 2, Spring, Year 1)
│   └── Pelican_350931629/      # Advanced save profile (Day 225, Winter, Year 2)
│
├── output/                     # Generated outputs (all gitignored except .gitkeep)
│   ├── .gitkeep
│   ├── morning_brief.json      # Structured game state (re-created each run)
│   ├── coach_prompt.txt        # LLM-ready coaching prompt (re-created each run)
│   └── Stardew_Save_Attributes.xlsx  # Full XML attribute dump (from parse_save.py)
│
├── stardew-mcp/                # Cloned SMAPI mod source (not committed — clone separately)
│   └── mod/StardewMCP/         # C# mod project (build target)
│
├── commit_summaries/           # Per-commit documentation
├── WORKFLOW.md                 # This document
└── README.md
```

---

## 3. Architecture

### agents/game_state_agent.py — Component Map

```
┌───────────────────────────────────────────────────────────────┐
│                       GameStateAgent                          │
│   (orchestrator: discovers save folder, owns observer loop)   │
└──────────┬──────────────────────────────────┬─────────────────┘
           │ on_save_detected()                │ live_once() / live_watch()
           ▼                                   ▼
┌──────────────────┐  ┌──────────────┐   ┌───────────────┐
│   SaveParser     │  │  SaveParser  │   │  LiveAdapter  │
│   (current)      │  │ (use_old)    │   │  WebSocket    │
│   SaveGameInfo   │  │  *_old files │   │  ws://...8765 │
│   + main save    │  └──────┬───────┘   └──────┬────────┘
└────────┬─────────┘         │ GameState         │ GameState
         │ GameState          └─────────┐        │ (live fields)
         └──────────────────────────────┴────────┘
                                        │
                                        ▼
                            ┌─────────────────────┐
                            │   _run_analysis()   │
                            └──────────┬──────────┘
                                       ▼
                        ┌──────────────────────────┐
                        │      GameStateDiff        │
                        │  compares yesterday vs    │
                        │  today (save-file mode)   │
                        └────────────┬─────────────┘
                                     ▼
                        ┌──────────────────────────┐
                        │       MorningBrief        │
                        │  formats current state    │
                        └──────┬───────────────┬───┘
                               │               │
                    ┌──────────▼──────┐  ┌─────▼──────────────────┐
                    │  Text summary   │  │   build_llm_prompt()    │
                    │  (terminal)     │  │   coach_prompt.txt      │
                    └─────────────────┘  └────────────────────────┘
                    output/morning_brief.json
                    output/coach_prompt.txt   ← send to any LLM
```

### agents/stardew_mcp_server.py — Claude Desktop MCP

```
Claude Desktop
      │  stdio (MCP protocol)
      ▼
stardew_mcp_server.py (FastMCP)
      │                                    │
      ▼ get_live_state()                   ▼ get_bundle_status()
      │ get_surroundings()                 │ get_fish_collection()
      │ get_catchable_fish()               │ generate_coaching_prompt()
      │ run_coaching_agent() *             │ (live + save combined)
      ▼                                    ▼
 LiveAdapter                          SaveParser
 ws://localhost:8765/game             %APPDATA%\StardewValley\Saves
      │                                    │
      ▼                                    ▼
 SMAPI mod (C#)                      Stardew Valley save file
 stardew-mcp                         (written on each in-game sleep)

* run_coaching_agent requires ANTHROPIC_API_KEY env var
```

### SaveParser — Two-File Strategy

Each save folder contains two files the agent reads:

| File | Size | Content | Used For |
|---|---|---|---|
| `SaveGameInfo` | ~23 KB | Farmer snapshot | Money, skills, stats, quests, friendships, date, `fishCaught` |
| `{FolderName}` | 2–10 MB | Full world state | `dailyLuck`, `weatherForTomorrow`, `isRaining`, `bundleData`, Community Center bundles |
| `*_old` variants | same | Previous day's copies | Yesterday's state for diffing |

The world file is loaded with `ET.parse()` (full tree) since Community Center data is nested deeply inside `<locations>`.

---

## 4. Data Flow

### Save-File Mode (default)
```
In-game sleep
      │
      ▼
Stardew Valley writes
  SaveGameInfo      (farmer snapshot — ~23 KB)
  SaveGameInfo_old  (previous day backup)
  {SaveName}        (full world — 2-10 MB)
  {SaveName}_old    (previous world backup)
      │
      ▼
watchdog detects SaveGameInfo change
      │  (1.5s debounce to let all files finish writing)
      ▼
SaveParser(current).parse()   →  GameState (today)
SaveParser(use_old).parse()   →  GameState (yesterday)
      │
      ▼
GameStateDiff.compute()
  • money delta
  • 14 tracked stats (stone, fish, monsters, crops, gifts…)
  • skill level-ups
  • quest completions / new quests
  • friendship point gains / new NPCs met
  • new fish species caught
  • bundle donation progress + bundle completions
  • new minerals / artifacts found
  • new achievements unlocked
  • new cooking / crafting recipes learned
      │
      ▼
_run_analysis()  →  MorningBrief + GameStateDiff
MorningBrief.as_dict()   →  output/morning_brief.json
MorningBrief.as_text()   →  terminal box display
build_llm_prompt()       →  output/coach_prompt.txt   ← send to any LLM
```

### Live WebSocket Mode (--live)
```
stardew-mcp SMAPI mod broadcasts every 1 second:
  ws://localhost:8765/game  →  {"id":"","type":"state","success":true,"data":{...}}

      │
      ▼
LiveAdapter.get_snapshot()  or  .watch(callback)
      │
      ▼
from_live_json(data)  →  GameState
  (position, time_of_day, current_location, ascii_map populated)
      │
      ▼
_run_analysis(state, yesterday=None)
  (no diff in live mode — no _old files consulted)
      │
      ▼
MorningBrief.as_text()  +  build_llm_prompt()
  (prompt includes live section: time, location, ascii surroundings map)
      │
      ▼
output/morning_brief.json  +  output/coach_prompt.txt
```

### Claude Desktop MCP Mode (stardew_mcp_server.py)
```
User asks Claude Desktop a question
      │
      ▼
Claude calls relevant tool(s):

  Simple question → get_live_state / get_surroundings / get_catchable_fish
                         │
                         ▼
                    LiveAdapter (WebSocket)
                    returns JSON → Claude answers directly

  Bundle/collection → get_bundle_status / get_fish_collection
                         │
                         ▼
                    SaveParser (most recent save file)
                    returns JSON → Claude answers directly

  Complex planning → generate_coaching_prompt
                         │
                         ▼
                    LiveAdapter + SaveParser (combined)
                    returns full context prompt
                         │
                         ▼
                    Claude reasons through the plan itself
                    (no additional API call needed)
```

---

## 5. Save File Profiles

Two save profiles are committed for development and testing:

### Tolkien_432258440 — Beginner
| Field | Value |
|---|---|
| Day | 2, Spring, Year 1 |
| Money | 500g |
| Total Earned | 0g |
| All Skills | 0 |
| Days Played | 2 |
| Active Quests | Introductions, Getting Started |
| Friendships | Lewis 0pts, Robin 0pts |
| Mine Depth | 0 |
| Achievements | 0 |
| Stat Format | `stats/Values/item` key-value pairs (1.6 format) |

**Use case:** Testing early-game logic, quest detection, first-day diffs.

### Pelican_350931629 — Advanced (near-endgame)
| Field | Value |
|---|---|
| Day | 29, Winter, Year 2 (225 total days played) |
| Money | 500g (wallet) |
| Total Earned | 24,060,325g |
| All Skills | 10 (maxed) |
| Friendships | All NPCs at 10 hearts |
| Mine Depth | 282 (Skull Cavern territory) |
| Times Reached Mine Bottom | 5 |
| Stone Gathered | 13,409 |
| Items Shipped | 60,639 |
| Times Fished | 836 |
| Monsters Killed | 4,815 |
| Achievements | 30 |
| Cooking Recipes Known | 80 |
| Crafting Recipes Known | 129 |
| Special Keys | Rusty Key, Skull Key, Dwarvish Translation |
| House Upgrade | Level 3 (fully upgraded) |
| Stat Format | Direct child elements under `<stats>` (legacy format) |

**Use case:** Testing stat parsing on advanced saves, endgame coaching prompts, stress-testing the diff engine with large friendship/recipe/mail lists.

---

## 6. Save File Format Findings

### Critical: Dual Stat Storage Formats

Stardew Valley has changed how statistics are stored across game versions. Both formats must be supported:

**Format A — `stats/Values/item` (1.6 new saves, e.g. Tolkien)**
```xml
<stats>
  <Values>
    <item>
      <key><string>stoneGathered</string></key>
      <value><unsignedInt>20</unsignedInt></value>
    </item>
    ...
  </Values>
  <stoneGathered xsi:nil="true" />  <!-- legacy fields nulled out -->
</stats>
```

**Format B — Direct child elements (legacy saves, e.g. Pelican)**
```xml
<stats>
  <stoneGathered>13409</stoneGathered>
  <rocksCrushed>6389</rocksCrushed>
  <!-- also PascalCase duplicates in advanced saves: -->
  <StoneGathered>13409</StoneGathered>
  ...
</stats>
```

**Resolution:** `SaveParser._parse_farmer()` detects which format is present and falls back to Format B. The parser uses a case-insensitive lookup so PascalCase duplicates are handled automatically.

### Additional Fields Present Only in Advanced Saves

| XML Path | Tolkien | Pelican | Agent Support |
|---|---|---|---|
| `basicShipped/item` | 0 items | 199 items | Not yet |
| `mineralsFound/item` | 0 items | 53 items | ✅ Tracked (name + count, diff new types) |
| `fishCaught/item` | 0 items | 73 species | ✅ Tracked (species count + diff) |
| `archaeologyFound/item` | 0 items | 43 items | ✅ Tracked (name + count, diff new finds) |
| `achievements/int` | 0 | 30 | ✅ Tracked (ID list, diff new unlocks) |
| `professions/int` | 0 | 10 | ✅ Tracked |
| `cookingRecipes/item` | 1 | 80 | ✅ Tracked (name list + diff new recipes) |
| `craftingRecipes/item` | 11 | 129 | ✅ Tracked (name list + diff new recipes) |
| `secretNotesSeen/int` | 0 | 36 | Not yet |
| `specialItems` | 0 items | 15 items | Not yet |
| `mailReceived/string` | 2 items | 286 items | Not yet |
| `houseUpgradeLevel` | 0 | 3 | ✅ Tracked |
| `deepestMineLevel` | 0 | 282 | ✅ Tracked |
| `hasSkullKey` | nil | true | ✅ Tracked |
| `hasRustyKey` | nil | true | ✅ Tracked |
| `bundleData/item` (main save) | 31 bundles | 31 bundles | ✅ Parsed (see below) |
| CommunityCenter `areasComplete` | 0/6 | 6/6 | ✅ Tracked |
| CommunityCenter `bundles` | 0 donated | 23/31 complete | ✅ Tracked (slot-level) |

### SaveGameInfo vs Main Save — Field Location Reference

| Data Point | Source File | XML Path |
|---|---|---|
| Day / Season / Year | `SaveGameInfo` | `dayOfMonthForSaveGame`, `seasonForSaveGame`, `yearForSaveGame` |
| Money | `SaveGameInfo` | `money` |
| Total Earned | `SaveGameInfo` | `totalMoneyEarned` |
| Skill levels | `SaveGameInfo` | `farmingLevel`, `miningLevel`, etc. |
| Stats | `SaveGameInfo` | `stats/Values/item` OR `stats/<name>` (dual format) |
| Quests | `SaveGameInfo` | `questLog/Quest` |
| Friendships | `SaveGameInfo` | `friendshipData/item` |
| Dialogue events | `SaveGameInfo` | `activeDialogueEvents/item` |
| Fish caught | `SaveGameInfo` | `fishCaught/item` — `key/int` (item ID) → `value/ArrayOfInt/int` |
| Minerals found | `SaveGameInfo` | `mineralsFound/item` — `key/int` (item ID) → `value/int` (count) |
| Artifacts found | `SaveGameInfo` | `archaeologyFound/item` — `key/int` → `value/ArrayOfInt/int` [found, donated] |
| Achievements | `SaveGameInfo` | `achievements/int` (list of int IDs) |
| Recipes | `SaveGameInfo` | `cookingRecipes/item` + `craftingRecipes/item` — `key/string` (name) |
| Daily luck | Main save | `SaveGame/dailyLuck` (root level) |
| Weather tomorrow | Main save | `SaveGame/weatherForTomorrow` |
| Is raining | Main save | `SaveGame/isRaining` |
| Bundle definitions | Main save | `SaveGame/bundleData/item` — key `"Room/ID"`, value `"name/reward/items/numRequired/color"` |
| CC room completion | Main save | `SaveGame/locations/GameLocation[@name=CommunityCenter]/areasComplete/boolean` (6 booleans) |
| CC bundle donations | Main save | `SaveGame/locations/GameLocation[@name=CommunityCenter]/bundles/item` — `key/int` → `ArrayOfBoolean` |

### Bundle Format Details

`bundleData` value format:
```
name / reward / item_id qty quality [item_id qty quality ...] / numRequired / color [/ displayName]
```
- `reward`: `"O item_id qty"` or `"BO item_id qty"` (big object)
- Items: space-separated triplets — `item_id qty quality` (quality: 0=Normal, 1=Silver, 2=Gold, 4=Iridium)
- Item ID `-1` = gold payment; `qty` is the gold amount (e.g. `2500` → "2,500g")
- `numRequired`: `-1` means all items required; positive = exact count needed; clamped to `min(required, len(items))` to handle remixed bundle edge cases
- Bundle definitions are embedded in the save — remixed bundles work automatically

CC bundle donation array:
- `bundles` dict maps bundle ID → `ArrayOfBoolean` with `n_items × 3` booleans
- Slot `i` is considered donated if `any(bools[i*3 : i*3+3])` is True

---

## 7. Agent Component Reference

### GameState (dataclass)
Central data model. All fields default to zero/empty so partial saves still parse safely.

Key fields:
- `money`, `stamina`, `max_stamina`, `health`, `max_health` — player vitals
- `farming_level`, `fishing_level`, `foraging_level`, `mining_level`, `combat_level` — skills
- `friendship: list[FriendshipState]` — NPC relationships
- `quests: list[QuestState]` — active quest log
- `fish_caught: dict[str, int]` — fish species → catch count
- `minerals_found: dict[str, int]` — mineral name → count
- `artifacts_found: dict[str, int]` — artifact name → count
- `achievements: list[int]` — list of unlocked achievement IDs
- `recipes_cooking: list[str]` — cooking recipe names known
- `recipes_crafting: list[str]` — crafting recipe names known
- `cc_bundles: list[BundleState]` — Community Center bundle progress
- `cc_rooms_complete: list[bool]` — 6 room completion flags

Live-only fields (populated by `from_live_json()`, zero/empty in save-file mode):
- `time_of_day: int` — military time 600–2600 (600=6am, 2600=2am next day)
- `current_location: str` — current map (e.g. "Farm", "FarmHouse", "Town")
- `position_x / position_y: int` — tile coordinates
- `ascii_map: str` — 61×61 ASCII surroundings map from SMAPI mod

### from_live_json(data) → GameState

Maps a stardew-mcp WebSocket broadcast to a `GameState`. The actual payload shape (confirmed against the running mod) is:

```json
{
  "player": {
    "name": "Tolkien",
    "x": 64, "y": 15,
    "location": "Farm",
    "energy": 270, "maxEnergy": 270,
    "health": 100, "maxHealth": 100,
    "money": 500,
    "inventory": [{"slot":0,"name":"Axe","displayName":"Axe","stack":1,"category":"Tool",...}]
  },
  "time": {
    "timeOfDay": 1010, "timeString": "10:10 AM",
    "day": 2, "season": "spring", "year": 1,
    "dayOfWeek": "Tuesday", "isNight": false
  },
  "world": {
    "weather": "sunny",
    "isOutdoors": true, "isFarm": true
  },
  "skills": {
    "farming": 0, "mining": 0, "foraging": 0, "fishing": 0, "combat": 0,
    "farmingXp": 0, "miningXp": 20, ...
  },
  "quests": [{"id":"9","name":"Introductions","isComplete":false,"reward":0,...}],
  "relationships": [{"npcName":"Lewis","friendshipPoints":0,"status":"Friendly","talkedToToday":false,...}],
  "surroundings": {
    "asciiMap": "...",
    "nearbyNPCs": [], "nearbyMonsters": [], "nearbyObjects": [],
    "nearbyTiles": [], "nearbyBuildings": [], "warpPoints": [], ...
  }
}
```

Key field mappings (from WebSocket → GameState):
- `player.energy` → `stamina`, `player.maxEnergy` → `max_stamina`
- `player.location` → `current_location` (not `world.location`)
- `player.x` / `player.y` → `position_x` / `position_y` (not `player.position.x`)
- `time.season` → `season` (lowercase "spring" → capitalised "Spring")
- `time.timeOfDay` → `time_of_day` (not `world.timeOfDay`)
- `time.day` → `day` (not `world.dayOfMonth`)
- `world.weather` → `weather_tomorrow` (lowercase "sunny"/"rainy"/"stormy")
- `skills` → skill levels (top-level object, not nested in `player`)
- `quests[].name` → `QuestState.title` (not `questLog[].title`)
- `quests[].isComplete` → `QuestState.completed` (not `completed`)
- `relationships[]` → `FriendshipState` list (not `player.friendships` dict)
- `surroundings.nearbyNPCs` → nearby NPCs (capital NPC, not `nearbyNpcs`)
- `surroundings.nearbyMonsters` → monsters (not `monsters`)
- `surroundings.nearbyObjects` → objects (not `objects`)

Fish collection and bundle data are **not** in the WebSocket payload — read from save file separately and overlaid in `generate_coaching_prompt`.

### LiveAdapter
WebSocket client for the stardew-mcp SMAPI mod (`ws://localhost:8765/game`).
- `get_snapshot() → GameState` — sends `{"type":"get_state"}`, waits for response
- `watch(callback, interval_seconds=0)` — streams state broadcasts; fires `callback(GameState)` on each new in-game day

Requires `pip install websockets`.

### stardew-mcp SMAPI Mod — Build Notes

**Repo:** https://github.com/Hunter-Thompson/stardew-mcp
**Project path:** `mod/StardewMCP/StardewMCP.csproj` (not `StardewMod/` as the upstream README states)
**Build output:** `bin/Debug/net6.0/StardewMCP 1.0.0.zip`
**Mods folder:** `C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods\`

**Stardew 1.6 compatibility fix** (required):
The upstream code has a build error (`CS8917`) in `CommandExecutor.cs` around line 3342 where `.Count` on `craftingRecipes`/`cookingRecipes` is ambiguous due to Netcode type changes. Fix:

```csharp
// Before (fails):
["totalCraftingRecipes"] = Game1.player.craftingRecipes.Count,
["totalCookingRecipes"]  = Game1.player.cookingRecipes.Count

// After (works):
int totalCraftingRecipes = 0;
foreach (var _ in Game1.player.craftingRecipes.Keys) totalCraftingRecipes++;
int totalCookingRecipes = 0;
foreach (var _ in Game1.player.cookingRecipes.Keys) totalCookingRecipes++;

["totalCraftingRecipes"] = totalCraftingRecipes,
["totalCookingRecipes"]  = totalCookingRecipes
```

### stardew_mcp_server.py — MCP Server for Claude Desktop

Stdio-based MCP server using `FastMCP`. Exposes seven tools:

| Tool | Data source | Notes |
|---|---|---|
| `get_live_state` | WebSocket | Full state + vitals (health, stamina, money, skills, quests, friendships) |
| `get_surroundings` | WebSocket | ASCII map + nearby NPCs, monsters, objects, time, location |
| `get_catchable_fish` | WebSocket (season/weather) | Live conditions; no game required for season/weather detection |
| `get_bundle_status` | Save file | Reflects last in-game sleep; gold bundles show "2,500g" format |
| `get_fish_collection` | Save file | Reflects last in-game sleep |
| `generate_coaching_prompt` | WebSocket + save file | Combined context for complex planning; Claude reasons directly |
| `run_coaching_agent` | WebSocket + save file | Spawns a second Claude via API; requires `ANTHROPIC_API_KEY` |

Configure via environment variables in `claude_desktop_config.json`:
- `STARDEW_WS_URL` (default: `ws://localhost:8765/game`)
- `STARDEW_SAVES_DIR` (default: `%APPDATA%\StardewValley\Saves`)
- `STARDEW_COACH_MODEL` (default: `claude-opus-4-6`) — model used by `run_coaching_agent`
- `ANTHROPIC_API_KEY` — optional; only needed for `run_coaching_agent`

**Agent behaviour:** For complex planning requests, Claude Desktop calls `generate_coaching_prompt` to load full game context and then reasons through the plan itself. `run_coaching_agent` is only invoked if the user explicitly requests it.

### SaveParser
- `__init__(save_folder, use_old=False)` — selects current or `_old` file pair
- `parse() → GameState` — runs both `_parse_farmer` and `_parse_world`
- `_parse_farmer()` — reads `SaveGameInfo`; handles dual stat format; parses fish, minerals (int key IDs), artifacts (int key IDs), achievements, recipes
- `_parse_world()` — full `ET.parse()` of main save for world fields + bundle data
- `_parse_bundles(state, world_root)` — parses `bundleData` definitions + CC donation progress; gold bundles (item_id=-1) use qty as amount; required count clamped to item count

### GameStateDiff
- `compute() → dict[str, str]` — returns keyed activity strings, empty dict if no changes
- `as_text() → str` — human-readable bullet list
- Tracks: money delta, 14 stats, skill level-ups, quest changes, friendship gains, new fish/mineral/artifact types, new achievements, new recipes, bundle donations

### MorningBrief
- `as_dict() → dict` — machine-readable JSON-safe structure
- `as_text() → str` — box-drawn terminal display
- Luck bands: Very Bad / Bad / Neutral / Good / Very Good based on `dailyLuck` float
- Weather descriptions cover: Sun, Rain, Storm, Snow, Wind, Festival, Wedding, GreenRain
- Live mode: shows `time_of_day` and `current_location` in the header box

### build_llm_prompt(brief, diff)
Returns a markdown prompt with yesterday's recap + today's JSON brief. Sections: Good Morning / Top Priorities / Social Round / Evening Checklist / Coach's Tip.

Includes dedicated **Fishing** section (today's catchable fish by season + weather) and **Community Center Progress** section (incomplete bundles closest to completion with missing items listed).

Live mode adds a **Live State** section: time of day, location, position, and ASCII surroundings map.

Prompt is ~2,000–3,000 tokens; recommended minimum model context window: **8,192 tokens**.

### Constants and Helpers
- `FISH_ID_NAMES: dict[int, str]` — 59 fish species mapped from integer save IDs
- `BUNDLE_ITEM_NAMES: dict[int, str]` — 80+ item IDs for all standard and remixed bundle items
- `MINERAL_NAMES: dict[int, str]` — 53 mineral types (gems + geode minerals, IDs 60–86, 538–578)
- `ARTIFACT_NAMES: dict[int, str]` — 40 artifact types (IDs 96–127, 580–589)
- `ACHIEVEMENT_NAMES: dict[int, str]` — 41 achievement IDs (0–40)
- `FISH_SCHEDULE: list` — 60-entry availability table: `(name, seasons_frozenset, weather, location, min_fishing_level)`
- `get_catchable_fish(season, is_raining, fishing_level) → list` — filters schedule by today's conditions
- `_fmt_time(t: int) → str` — converts military time (e.g. 1410) to "2:10pm"

### GameStateAgent
- Auto-discovers the most recently modified save folder in `saves_dir`
- Writes all outputs to `output_dir` (defaults to `../output` relative to `saves_dir`)
- Debounces watchdog events with a 3-second window + 1.5-second write delay
- `_run_analysis(today, yesterday)` — shared pipeline used by both save-file and live modes
- `live_once(url)` / `live_watch(url)` — live WebSocket run modes using `LiveAdapter`

---

## 8. Development Workflow

### Branching Strategy
```
main                ← stable, always deployable
feature/<name>      ← new features (PR → main)
fix/<name>          ← bug fixes (PR → main)
```

### Running Against Test Saves
```bash
# Quick one-shot against local saves (no watchdog needed)
python agents/game_state_agent.py --saves-dir saves --once

# Test Tolkien (beginner) specifically
python -c "
from agents.game_state_agent import SaveParser, MorningBrief
from pathlib import Path
s = SaveParser(Path('saves/Tolkien_432258440')).parse()
print(MorningBrief(s).as_text())
"

# Test Pelican (advanced) specifically
python -c "
from agents.game_state_agent import SaveParser, MorningBrief
from pathlib import Path
s = SaveParser(Path('saves/Pelican_350931629')).parse()
print(MorningBrief(s).as_text())
"

# Test live WebSocket (game must be running with SMAPI + stardew-mcp)
python agents/game_state_agent.py --live --once
```

### Verify WebSocket Payload Shape
```python
python -c "
import websockets.sync.client as ws, json
c = ws.connect('ws://localhost:8765/game')
data = json.loads(c.recv())['data']
c.close()
print('TOP KEYS:', list(data.keys()))
print('PLAYER KEYS:', list(data['player'].keys()))
print('location:', data['player']['location'])
print('time:', data['time']['timeString'])
"
```

### Adding a New Tracked Field
1. Add the field to `GameState` with a zero default
2. Add the XML key → attribute mapping to `SaveParser.STAT_MAP` (for stat fields) or parse it directly in `_parse_farmer`
3. Add a diff entry in `GameStateDiff.compute()` if it should appear in the daily recap
4. Add it to `MorningBrief.as_dict()` if it should appear in the morning brief
5. Update `from_live_json()` if the field is available from the WebSocket
6. Test against both Tolkien and Pelican saves

---

## 9. Pending Enhancements

### Short Term
- [x] **Achievement tracking** — diff `achievements/int` list; report newly unlocked achievements
- [x] **Recipe tracking** — `recipes_cooking`/`recipes_crafting` store full name lists; diffs report newly learned recipes
- [x] **Mineral/artifact tracking** — diff `mineralsFound` and `archaeologyFound`; integer ID → name mapping from stardewids/objects.json
- [ ] **Multi-farm support** — when multiple save folders exist, prompt user to select or monitor all
- [ ] **Shipped items tracking** — `basicShipped/item` (199 items in Pelican, 0 in Tolkien)

### Medium Term
- [x] **LLM prompt generation** — `coach_prompt.txt` written on every run
- [x] **Fish collection tracking** — diff `fishCaught/item`; `FISH_ID_NAMES` maps 59 species
- [x] **Fish availability lookup** — `FISH_SCHEDULE` + `get_catchable_fish()` by season/weather/level
- [x] **Bundle tracker** — parse `bundleData` and CC donation booleans; surfaces closest-to-complete bundles
- [ ] **Seasonal crop planner** — advise on which crops to plant given current day and days left in season
- [ ] **Secret notes tracker** — `secretNotesSeen/int` list

### Long Term
- [ ] **Time-series logging** — append each day's `GameState` to a SQLite DB for trend analysis
- [ ] **Farm layout parser** — read building placement from `<locations>` in main save
- [ ] **Web dashboard** — serve `morning_brief.json` via a simple Flask/FastAPI endpoint

### Live / MCP (Completed)
- [x] **Live WebSocket mode** — `LiveAdapter` + `--live`/`--live-url` CLI flags
- [x] **Claude Desktop MCP server** — `stardew_mcp_server.py` with 7 tools via stdio MCP
- [x] **from_live_json() field mapping** — corrected against actual Hunter-Thompson/stardew-mcp payload shape
- [x] **stardew-mcp build fix** — CommandExecutor.cs patched for Stardew 1.6 Netcode type changes

---

*Last updated: 2026-03-04*
*Game version tested: 1.6.15 | Python: 3.13 | SMAPI: 4.x | stardew-mcp: 1.0.0*
