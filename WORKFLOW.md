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
| `python agents/game_state_agent.py` | Live mode (reads from `%APPDATA%\StardewValley\Saves`) |
| `python agents/game_state_agent.py --saves-dir saves --once --ollama` | One-shot + Ollama coaching response |
| `python scripts/parse_save.py` | Dump all XML attributes to `output/Stardew_Save_Attributes.xlsx` |

**Ollama flags:**

| Flag | Default | Description |
|---|---|---|
| `--ollama` | off | Enable local LLM call via Ollama |
| `--ollama-model` | `ministral:8b` | Ollama model tag to use |
| `--ollama-url` | `http://localhost:11434` | Ollama server base URL |
| `--ollama-timeout` | `300` | Seconds to wait for response |
| `--no-think` | off | Suppress chain-of-thought for qwen3/deepseek-r1 models |

**Dependencies:** `watchdog` (watch mode only), `openpyxl` (parse_save.py only), Ollama (`--ollama` only — no pip install)

---

## 2. Folder Structure

```
Stardew_Valley_ESP/
├── agents/                     # Autonomous agent scripts
│   └── game_state_agent.py     # Main Game State Agent (see §3)
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
│   ├── coach_response.md       # Ollama response (only when --ollama, UTF-8 with emoji)
│   └── Stardew_Save_Attributes.xlsx  # Full XML attribute dump (re-created by parse_save.py)
│
├── input/                      # Reserved for future input data
├── intermediate/               # Reserved for intermediate processing artifacts
├── commit_summaries/           # Per-commit documentation
│   └── INITIAL_COMMIT_SUMMARY.md
│
├── WORKFLOW.md                 # This document
└── README.md
```

---

## 3. Architecture

### agents/game_state_agent.py — Component Map

```
┌─────────────────────────────────────────────────────────────┐
│                      GameStateAgent                         │
│  (orchestrator: discovers save folder, owns observer loop)  │
└───────────┬─────────────────────────────────────────────────┘
            │ on_save_detected()
            ▼
┌───────────────────┐     ┌───────────────────┐
│   SaveParser      │     │   SaveParser       │
│   (current)       │     │   (use_old=True)   │
│   SaveGameInfo    │     │   SaveGameInfo_old │
│   + main save     │     │   + main_old       │
└────────┬──────────┘     └────────┬───────────┘
         │ GameState                │ GameState
         └──────────┬───────────────┘
                    ▼
         ┌──────────────────┐
         │  GameStateDiff   │  compares yesterday vs today
         └────────┬─────────┘
                  │ dict[str, str]  activity log
                  ▼
         ┌──────────────────┐
         │  MorningBrief    │  formats current state
         └────────┬─────────┘
                  │
         ┌────────▼─────────┐   ┌────────────────────────┐
         │  Text summary    │   │  build_llm_prompt()     │
         │  (terminal)      │   │  coach_prompt.txt       │
         └──────────────────┘   └────────────┬───────────┘
                                             │ --ollama flag
                                ┌────────────▼───────────┐
                                │  call_ollama()          │
                                │  → Ollama REST API      │
                                │  coach_response.md      │
                                └────────────────────────┘
         output/morning_brief.json
         output/coach_prompt.txt
         output/coach_response.md  (only when --ollama)
```

### SaveParser — Two-File Strategy

Each save folder contains two files the agent reads:

| File | Size | Content | Used For |
|---|---|---|---|
| `SaveGameInfo` | ~23 KB | Farmer snapshot | Money, skills, stats, quests, friendships, date, `fishCaught` |
| `{FolderName}` | 2–10 MB | Full world state | `dailyLuck`, `weatherForTomorrow`, `isRaining`, `bundleData`, Community Center bundles |
| `*_old` variants | same | Previous day's copies | Yesterday's state for diffing |

The world file is loaded with `ET.parse()` (full tree) since Community Center data is nested deeply inside `<locations>`.  Files are 2–10 MB — acceptable performance for the bundle and world-state features we need.

---

## 4. Data Flow

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
  • new dialogue events
  • new fish species caught
  • bundle donation progress + bundle completions
      │
      ▼
MorningBrief.as_dict()   →  output/morning_brief.json
MorningBrief.as_text()   →  terminal box display
build_llm_prompt()       →  output/coach_prompt.txt
      │  (if --ollama)
      ▼
call_ollama()            →  output/coach_response.md + terminal print
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
| Day | 29, Winter, Year 2 (225 total days played across both years) |
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

**Resolution:** `SaveParser._parse_farmer()` detects which format is present and falls back to Format B. The parser uses a case-insensitive lookup so PascalCase duplicates are handled automatically. ✅ Fixed in `agents/game_state_agent.py`.

### Additional Fields Present Only in Advanced Saves

The following collections are populated in Pelican but empty in Tolkien. Future agent versions should extract these:

| XML Path | Tolkien | Pelican | Agent Support |
|---|---|---|---|
| `basicShipped/item` | 0 items | 199 items | Not yet |
| `mineralsFound/item` | 0 items | 53 items | Not yet |
| `fishCaught/item` | 0 items | 73 species | ✅ Tracked (species count + diff) |
| `archaeologyFound/item` | 0 items | 43 items | Not yet |
| `achievements/int` | 0 | 30 | Not yet |
| `professions/int` | 0 | 10 | ✅ Tracked |
| `cookingRecipes/item` | 1 | 80 | ✅ Tracked (count) |
| `craftingRecipes/item` | 11 | 129 | ✅ Tracked (count) |
| `secretNotesSeen/int` | 0 | 36 | Not yet |
| `specialItems` | 0 items | 15 items | Not yet |
| `mailReceived/string` | 2 items | 286 items | Not yet |
| `houseUpgradeLevel` | 0 | 3 | ✅ Tracked |
| `deepestMineLevel` | 0 | 282 | ✅ Tracked |
| `hasSkullKey` | nil | true | ✅ Tracked |
| `hasRustyKey` | nil | true | ✅ Tracked |
| `bundleData/item` (main save) | 31 bundles | 31 bundles | ✅ Parsed (see §6 below) |
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
| Fish caught | `SaveGameInfo` | `fishCaught/item` — `key/int` (item ID) → `value/ArrayOfInt/int` (count, max size) |
| Daily luck | Main save | `SaveGame/dailyLuck` (root level) |
| Weather tomorrow | Main save | `SaveGame/weatherForTomorrow` |
| Is raining | Main save | `SaveGame/isRaining` |
| Bundle definitions | Main save | `SaveGame/bundleData/item` — key `"Room/ID"`, value `"name/reward/items/numRequired/color"` |
| CC room completion | Main save | `SaveGame/locations/GameLocation[@name=CommunityCenter]/areasComplete/boolean` (6 booleans) |
| CC bundle donations | Main save | `SaveGame/locations/GameLocation[@name=CommunityCenter]/bundles/item` — `key/int` → `ArrayOfBoolean` (n_items × 3 booleans per slot) |

### Bundle Format Details

`bundleData` value format:
```
name / reward / item_id qty quality [item_id qty quality ...] / numRequired / color [/ displayName]
```
- `reward`: `"O item_id qty"` or `"BO item_id qty"` (big object)
- Items: space-separated triplets — `item_id qty quality` (quality: 0=Normal, 1=Silver, 2=Gold, 4=Iridium)
- `numRequired`: `-1` means all items are required; positive value = exact count needed
- Bundle definitions are embedded in the save — remixed bundles work automatically

CC bundle donation array:
- `bundles` dict maps bundle ID → `ArrayOfBoolean` with `n_items × 3` booleans
- Slot `i` is considered donated if `any(bools[i*3 : i*3+3])` is True (first boolean in the triplet is the primary flag)

---

## 7. Agent Component Reference

### GameState (dataclass)
Central data model. All fields default to zero/empty so partial saves still parse safely.

### SaveParser
- `__init__(save_folder, use_old=False)` — selects current or `_old` file pair
- `parse() → GameState` — runs both `_parse_farmer` and `_parse_world`
- `_parse_farmer()` — reads `SaveGameInfo`; handles dual stat format; parses `fishCaught` using `FISH_ID_NAMES`
- `_parse_world()` — full `ET.parse()` of main save for world fields + bundle data
- `_parse_bundles(state, world_root)` — parses `bundleData` definitions + Community Center donation progress

### GameStateDiff
- `compute() → dict[str, str]` — returns keyed activity strings, empty dict if no changes
- `as_text() → str` — human-readable bullet list

### MorningBrief
- `as_dict() → dict` — machine-readable JSON-safe structure
- `as_text() → str` — box-drawn terminal display (46-char wide)
- Luck bands: Very Bad / Bad / Neutral / Good / Very Good based on `dailyLuck` float
- Weather descriptions cover: Sun, Rain, Storm, Snow, Wind, Festival, Wedding, GreenRain

### build_llm_prompt(brief, diff)
Returns a markdown prompt with yesterday's recap + today's JSON brief. Structured output sections: Good Morning / Top Priorities / Social Round / Evening Checklist / Coach's Tip.

Includes dedicated **Fishing** section (today's catchable fish by season + weather) and **Community Center Progress** section (incomplete bundles closest to completion with missing items listed).

Prompt is ~2,000–3,000 tokens depending on CC bundle count; recommended minimum model context window: **8,192 tokens**.

### Constants and Helpers
- `FISH_ID_NAMES: dict[int, str]` — 59 fish species mapped from integer save IDs (confirmed against stardewids/objects.json for 1.6)
- `BUNDLE_ITEM_NAMES: dict[int, str]` — 80+ item IDs covering all standard and remixed bundle items
- `FISH_SCHEDULE: list` — 60-entry availability table: `(name, seasons_frozenset, weather, location, min_fishing_level)`
- `get_catchable_fish(season, is_raining, fishing_level) → list` — filters schedule by today's conditions, returns `(name, location, note)` tuples

### call_ollama(prompt, model, base_url, timeout, think)
Sends the coaching prompt to a local Ollama instance via stdlib `urllib` (no pip install needed).

- `stream=False` — waits for the full response before returning
- `think=False` — prepends `/no_think` to the prompt and sets `{"think": false}` in the request body; suppresses chain-of-thought for `qwen3` and `deepseek-r1` models
- Raises `RuntimeError` if Ollama is unreachable (surfaced as `[Ollama ERROR]` in terminal)
- Response saved to `output/coach_response.md` (UTF-8) before printing, so emoji are always preserved even if the terminal can't render them

**To call with Claude instead:**
```python
import anthropic
client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}]
)
print(response.content[0].text)
```

### GameStateAgent
- Auto-discovers the most recently modified save folder in `saves_dir`
- Writes all outputs to `output_dir` (defaults to `../output` relative to `saves_dir`)
- Debounces watchdog events with a 3-second window + 1.5-second write delay
- Ollama params: `ollama`, `ollama_model`, `ollama_url`, `ollama_timeout`, `ollama_think` — all exposed as CLI flags

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
```

### Adding a New Tracked Field
1. Add the field to `GameState` with a zero default
2. Add the XML key → attribute mapping to `SaveParser.STAT_MAP` (for stat fields) or parse it directly in `_parse_farmer`
3. Add a diff entry in `GameStateDiff.compute()` if it should appear in the daily recap
4. Add it to `MorningBrief.as_dict()` if it should appear in the morning brief
5. Test against both Tolkien and Pelican saves

---

## 9. Pending Enhancements

### Short Term
- [ ] **Achievement tracking** — diff `achievements/int` list; report newly unlocked achievements
- [ ] **Recipe tracking** — diff `cookingRecipes/item` and `craftingRecipes/item` to report newly learned recipes
- [ ] **Mineral/artifact tracking** — diff `mineralsFound` and `archaeologyFound`
- [ ] **Multi-farm support** — when multiple save folders exist, prompt user to select or monitor all

### Medium Term
- [x] **LLM integration** — Ollama local LLM via `--ollama` flag; `call_ollama()` uses stdlib urllib, no pip deps
- [x] **Fish collection tracking** — diff `fishCaught/item` to report new species; `FISH_ID_NAMES` maps 59 species
- [x] **Fish availability lookup** — `FISH_SCHEDULE` + `get_catchable_fish()` lists catchable fish by season/weather/level
- [x] **Bundle tracker** — parse `bundleData` and Community Center donation booleans from main save; surfaces closest-to-complete bundles in prompt
- [ ] **Seasonal crop planner** — advise on which crops to plant given current day and days left in season

### Long Term
- [ ] **Time-series logging** — append each day's `GameState` to a SQLite DB for trend analysis
- [ ] **Farm layout parser** — read building placement from the main save's `<locations>` element
- [ ] **Web dashboard** — serve `morning_brief.json` via a simple Flask/FastAPI endpoint

---

*Last updated: 2026-03-05*
*Game version tested: 1.6.15 | Python: 3.13*
