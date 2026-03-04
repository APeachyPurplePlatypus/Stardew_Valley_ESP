# PR Summary — Workflow Documentation & Save Format Fixes

**Branch:** `feature/new-feature`
**Commits:** `0c6f996`, `74e1909`
**Files changed:** 3 files, +559 / -6 lines
**Date:** 2026-03-03

---

## What Changed

### 1. `WORKFLOW.md` — New Architecture Document

A full living reference document for the project covering:

- **Architecture diagram** — how `SaveParser`, `GameStateDiff`, `MorningBrief`, and `build_llm_prompt` connect
- **Data flow** — from in-game sleep → file write → watchdog trigger → diff → Morning Brief → LLM prompt
- **Two-file strategy** — why the agent reads `SaveGameInfo` (23 KB) for farmer data and the main save (2–10 MB) via `iterparse` for world data
- **Save profiles** — verified stats for both Tolkien (Day 2 Yr1, beginner) and Pelican (Day 225 Yr2, near-endgame)
- **Dual stat format discovery** — documents the XML structural difference between 1.6 new saves and legacy saves (see fixes below)
- **Field location reference table** — which data comes from `SaveGameInfo` vs the main save file
- **Pending enhancements backlog** — achievements, professions, house upgrades, fish collection, LLM wiring, time-series DB, bundle tracker
- **Development workflow** — branching strategy, how to run against each test save

### 2. `agents/game_state_agent.py` — Two Bug Fixes

**Bug 1: Pelican save showed all-zero stats**

Root cause: the agent only read stats from the 1.6 key-value format (`stats/Values/item`), but the Pelican save uses the legacy direct-child format (`stats/stoneGathered`, `stats/rocksCrushed`, etc.).

Fix: `_parse_farmer()` now detects which format is present and falls back to direct-child parsing. The lookup is case-insensitive, so PascalCase duplicates (`StoneGathered`, `RocksCrushed`) found in some advanced saves are handled automatically.

Before:
```
Pelican stats — stone: 0, rocks: 0, fished: 0, shipped: 0, monsters: 0
```
After:
```
Pelican stats — stone: 13,409  rocks: 6,389  fished: 836  shipped: 60,639  monsters: 4,815
```

**Bug 2: Pelican weather displayed as `"0"` instead of `"Sun"`**

Root cause: older saves store `weatherForTomorrow` as an integer enum (`0`=Sun, `1`=Rain, `2`=Storm, etc.) while newer saves use the string name directly.

Fix: added `_normalise_weather()` static method to `SaveParser` that maps integer codes to string names before the value reaches `GameState`. `MorningBrief.WEATHER_DESC` lookup now works correctly for both save generations.

Before:
```
Tomorrow: 0.
```
After:
```
Tomorrow: Sunny -- remember to water your crops.
```

Both fixes verified against Tolkien (Format A, string weather) and Pelican (Format B, integer weather).

### 3. `README.md` — Full Usage Guide

Replaced the original two-sentence description with complete documentation:

- Setup (venv, pip install)
- All four run modes with exact commands (watch, one-shot, JSON, attribute dumper)
- LLM integration code snippet (Anthropic SDK, `claude-opus-4-6`)
- Output files reference table
- Save profiles table explaining Tolkien vs Pelican and their purposes
- Link to `WORKFLOW.md` for architecture details

---

## Key Discovery

The two committed save files expose a previously unknown compatibility gap: Stardew Valley has changed its stat storage XML schema across versions. Any agent or tool that only supports one format will silently show wrong data for saves created on the other format. Both formats are now supported and tested.
