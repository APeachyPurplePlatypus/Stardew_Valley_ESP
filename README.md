# Stardew Valley ESP

An intelligent agent that reads your Stardew Valley save files and generates a personalised daily walkthrough to help you 100% the game as efficiently as possible.

The agent tracks your progress day-to-day, alerts you to tasks nearing completion, and adapts its coaching to your current season, luck, relationships, and active quests. It does not highlight entities, provide wallhacks, or modify the game in any way — it only reads save data.

---

## Features

- **Morning Brief** — every time you sleep in-game, the agent wakes up with you: current luck, weather forecast, wallet, active quests, and top relationships shown in a clean terminal summary
- **Daily Diff** — compares yesterday's save against today's to report exactly what you accomplished: stone mined, fish caught, quests completed, friendships gained, level-ups, new bundle donations
- **Fish Availability** — lists every fish catchable right now based on your current season, weather, and fishing level — including location hints and skill requirements
- **Community Center Tracker** — parses bundle definitions directly from your save file (works with remixed bundles too), tracks donation progress per slot, and surfaces the bundles closest to completion with their missing items
- **LLM Coaching Prompt** — generates a structured prompt ready to send to any LLM (Claude, GPT-4, etc.) for a step-by-step personalised walkthrough; fishing conditions and bundle status are included in context
- **Watch Mode** — uses `watchdog` to automatically fire analysis the moment you sleep in-game, no manual steps required
- **JSON Output** — all data is also written as structured JSON for use by other tools or scripts

---

## Project Structure

```
agents/          Game State Agent and future agents
scripts/         Utility scripts (XML → Excel attribute dumper)
saves/           Stardew Valley save folders (committed for dev/testing)
output/          Generated outputs — recreated on each run, not committed
commit_summaries/ Per-commit documentation
WORKFLOW.md      Architecture, data flow, and development notes
```

---

## Setup

**Requirements:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/APeachyPurplePlatypus/Stardew_Valley_ESP.git
cd Stardew_Valley_ESP

# Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# Install dependencies
pip install watchdog openpyxl
```

---

## Usage

### Watch Mode (recommended)
Automatically analyses your save every time you sleep in-game.

```bash
# Against your live game saves (default)
python agents/game_state_agent.py

# Against the dev saves in this repo
python agents/game_state_agent.py --saves-dir saves
```

The agent watches `%APPDATA%\StardewValley\Saves` by default on Windows.
Press `Ctrl+C` to stop.

### One-Shot Mode
Analyse the current save once and exit — useful for testing.

```bash
python agents/game_state_agent.py --once

# Against dev saves
python agents/game_state_agent.py --saves-dir saves --once
```

### JSON Output Only
Prints the Morning Brief as clean JSON — useful for piping to other tools.

```bash
python agents/game_state_agent.py --saves-dir saves --json
```

### Attribute Dumper
Extracts every XML attribute from your save into an Excel spreadsheet for research.

```bash
python scripts/parse_save.py
# Output: output/Stardew_Save_Attributes.xlsx
```

---

## LLM Integration

`output/coach_prompt.txt` is written on every run and can be sent to any cloud LLM:

```python
import anthropic
from pathlib import Path

client = anthropic.Anthropic()
prompt = Path("output/coach_prompt.txt").read_text(encoding="utf-8")

response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    messages=[{"role": "user", "content": prompt}]
)
print(response.content[0].text)
```

---

## Output Files

All generated files land in `output/` and are gitignored (recreated on each run):

| File | Description |
|---|---|
| `output/morning_brief.json` | Full structured game state as JSON |
| `output/coach_prompt.txt` | LLM-ready coaching prompt |
| `output/Stardew_Save_Attributes.xlsx` | Full XML attribute dump (from `parse_save.py`) |

---

## Save Profiles (Dev / Testing)

Two save files are committed for development and testing:

| Profile | State | Purpose |
|---|---|---|
| `Tolkien_432258440` | Day 2, Spring, Year 1 — brand new farm | Tests early-game logic, quest detection, early-game bundles |
| `Pelican_350931629` | Day 225, Winter, Year 2 — near-endgame, all skills maxed | Tests stat parsing, advanced save format, large friendship/recipe lists, 73-species fish collection, near-complete CC |

> Note: the two saves use different XML stat formats. The agent handles both automatically. See `WORKFLOW.md` for details.

---

## Architecture

See [WORKFLOW.md](WORKFLOW.md) for full architecture documentation including:
- Component map and data flow diagram
- Save file format findings (dual stat storage formats)
- Field location reference (which data comes from which file)
- Pending enhancements backlog
- Development workflow and branching strategy
