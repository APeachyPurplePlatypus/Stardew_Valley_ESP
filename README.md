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
- **Live WebSocket Mode** — connects to the stardew-mcp SMAPI mod for real-time game state (1-second updates): live time of day, position, surroundings map, inventory, and more
- **Claude Desktop MCP** — exposes game state as MCP tools so Claude Desktop can query your live game directly and act as an interactive coach
- **JSON Output** — all data is also written as structured JSON for use by other tools or scripts

---

## Project Structure

```
agents/          Game State Agent, Live Adapter, and MCP server
scripts/         Utility scripts (XML → Excel attribute dumper)
saves/           Stardew Valley save folders (committed for dev/testing)
output/          Generated outputs — recreated on each run, not committed
archive/         Archived outputs from previous features
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

# Core dependencies (save-file mode)
pip install watchdog openpyxl

# Live mode + Claude Desktop MCP (additional)
pip install websockets mcp
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

### Live WebSocket Mode
Requires the **stardew-mcp SMAPI mod** running inside Stardew Valley (see [Live Setup](#live-setup) below).

```bash
# One live snapshot (game must be running with SMAPI + stardew-mcp):
python agents/game_state_agent.py --live --once

# Watch mode — re-analyses on each new in-game day:
python agents/game_state_agent.py --live

# Custom WebSocket URL:
python agents/game_state_agent.py --live --live-url ws://localhost:8765/game
```

Live mode adds time of day, player position, and a 61×61 ASCII surroundings map to the coaching prompt.

### Attribute Dumper
Extracts every XML attribute from your save into an Excel spreadsheet for research.

```bash
python scripts/parse_save.py
# Output: output/Stardew_Save_Attributes.xlsx
```

---

## Claude Desktop MCP Integration

The `stardew_mcp_server.py` exposes your live game state as **MCP tools** that Claude Desktop can call directly during a conversation — so Claude acts as a fully interactive coach with real-time awareness of what you're doing.

### Tools exposed

| Tool | Description |
|---|---|
| `get_live_state` | Current time, location, health, stamina, money, skills, quests, friendships |
| `get_surroundings` | 61×61 ASCII tile map + nearby NPCs, monsters, and objects |
| `get_catchable_fish` | Fish available right now (season/weather/skill aware) |
| `get_bundle_status` | Community Center bundle progress (from save file) |
| `get_fish_collection` | All fish species caught so far (from save file) |
| `generate_coaching_prompt` | Full structured coaching prompt combining live + save data |

### MCP Setup

1. **Complete [Live Setup](#live-setup)** (SMAPI + stardew-mcp mod).

2. **Install Python MCP SDK:**
   ```bash
   pip install mcp websockets
   ```

3. **Configure Claude Desktop** — edit `%APPDATA%\Claude\claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "stardew-esp": {
         "command": "python",
         "args": ["C:/path/to/Stardew_Valley_ESP/agents/stardew_mcp_server.py"],
         "env": {
           "STARDEW_SAVES_DIR": "C:/Users/<you>/AppData/Roaming/StardewValley/Saves"
         }
       }
     }
   }
   ```

4. **Restart Claude Desktop.** The stardew-esp tools will appear in the tool picker.

5. **Start a conversation:** "What should I do today? Check my game state." Claude will call `get_live_state` and `get_bundle_status` automatically.

---

## Live Setup

Both `--live` mode and the Claude Desktop MCP server require the **stardew-mcp SMAPI mod**.

1. **Install SMAPI:** https://smapi.io

2. **Build and install the mod:**
   ```bash
   git clone https://github.com/Hunter-Thompson/stardew-mcp
   cd stardew-mcp
   dotnet build StardewMod
   # Copy the compiled StardewMod folder into %APPDATA%\StardewValley\Mods\
   ```
   > Requires .NET 6 SDK: https://dotnet.microsoft.com/download/dotnet/6.0

3. **Launch Stardew Valley through SMAPI** (not directly). The mod broadcasts game state to `ws://localhost:8765/game` every 1 second.

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
- Live WebSocket protocol details
- Pending enhancements backlog
- Development workflow and branching strategy
