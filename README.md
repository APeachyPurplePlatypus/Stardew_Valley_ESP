# Stardew Valley ESP

An intelligent agent that reads your Stardew Valley save files and generates a personalised daily walkthrough to help you 100% the game as efficiently as possible.

The agent tracks your progress day-to-day, alerts you to tasks nearing completion, and adapts its coaching to your current season, luck, relationships, and active quests. It does not highlight entities, provide wallhacks, or modify the game in any way — it only reads save data.

---

## Features

- **Morning Brief** — every time you sleep in-game, the agent wakes up with you: current luck, weather forecast, wallet, active quests, and top relationships shown in a clean terminal summary
- **Daily Diff** — compares yesterday's save against today's to report exactly what you accomplished: stone mined, fish caught, quests completed, friendships gained, level-ups, new bundle donations, new recipes, new minerals/artifacts, new achievements
- **Fish Availability** — lists every fish catchable right now based on your current season, weather, and fishing level — including location hints and skill requirements
- **Community Center Tracker** — parses bundle definitions directly from your save file (works with remixed bundles too), tracks donation progress per slot, and surfaces the bundles closest to completion with their missing items
- **Collection Tracking** — tracks minerals found, artifacts discovered, achievements unlocked, and cooking/crafting recipes learned; all diffed day-to-day
- **LLM Coaching Prompt** — generates a structured prompt ready for Claude Desktop or any LLM for a step-by-step personalised walkthrough; fishing conditions and bundle status are included in context
- **Watch Mode** — uses `watchdog` to automatically fire analysis the moment you sleep in-game, no manual steps required
- **Live WebSocket Mode** — connects to the stardew-mcp SMAPI mod for real-time game state (1-second updates): live time of day, position, surroundings map, inventory, and more
- **Claude Desktop MCP** — exposes game state as MCP tools so Claude Desktop can query your live game directly and act as an interactive coach; no API key required for complex planning
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

No API key is required. Claude Desktop is already Claude — for complex planning tasks it calls `generate_coaching_prompt` to load full game context and then reasons through the plan itself.

### Tools exposed

| Tool | Data source | Description |
|---|---|---|
| `get_live_state` | WebSocket | Current time, location, health, stamina, money, skills, quests, friendships |
| `get_surroundings` | WebSocket | 61×61 ASCII tile map + nearby NPCs, monsters, and objects |
| `get_catchable_fish` | WebSocket | Fish available right now (season/weather/skill aware) |
| `get_bundle_status` | Save file | Community Center bundle progress (reflects last sleep) |
| `get_fish_collection` | Save file | All fish species caught so far |
| `generate_coaching_prompt` | WebSocket + save file | Full structured coaching prompt for complex planning |
| `run_coaching_agent` | WebSocket + save file | Spawns a Claude API subagent (requires `ANTHROPIC_API_KEY`) |

### MCP Setup

1. **Complete [Live Setup](#live-setup)** (SMAPI + stardew-mcp mod) — required for live tools. Save-file tools work without the game running.

2. **Install Python MCP SDK:**
   ```bash
   pip install mcp websockets
   ```

3. **Configure Claude Desktop** — edit `%APPDATA%\Claude\claude_desktop_config.json`.
   Use the **full path** to your Python executable (run `where python` to find it):
   ```json
   {
     "mcpServers": {
       "stardew-esp": {
         "command": "C:/Users/<you>/AppData/Local/Microsoft/WindowsApps/python.exe",
         "args": ["C:/path/to/Stardew_Valley_ESP/agents/stardew_mcp_server.py"],
         "env": {
           "STARDEW_SAVES_DIR": "C:/Users/<you>/AppData/Roaming/StardewValley/Saves"
         }
       }
     }
   }
   ```
   > Optional: add `"ANTHROPIC_API_KEY": "sk-ant-..."` to the `env` block to enable `run_coaching_agent`.

4. **Restart Claude Desktop** fully (quit from system tray, relaunch). The stardew-esp tools will appear in the tool picker (hammer icon).

5. **Start a conversation.** Example prompts:
   - *"What should I do today?"* — Claude calls `get_live_state` and advises
   - *"What's my Community Center progress?"* — calls `get_bundle_status`
   - *"Plan the most efficient path to 100% this season"* — calls `generate_coaching_prompt` then reasons through a full plan

---

## Live Setup

Both `--live` mode and the live Claude Desktop MCP tools require the **stardew-mcp SMAPI mod**.

1. **Install SMAPI:** https://smapi.io

2. **Install .NET 6 SDK** (required to build the mod):
   https://dotnet.microsoft.com/download/dotnet/6.0

3. **Build and install the mod:**
   ```powershell
   git clone https://github.com/Hunter-Thompson/stardew-mcp
   cd stardew-mcp\mod\StardewMCP
   dotnet build
   ```
   > Note: the project is at `mod/StardewMCP/` — not `StardewMod/` as the upstream README states.
   >
   > The build patches one upstream compatibility error in `CommandExecutor.cs` (CS8917 — Stardew 1.6 changed the type of `craftingRecipes`/`cookingRecipes`). If the build fails with that error, see the fix in `WORKFLOW.md §7`.

   Extract the output zip into your game's Mods folder:
   ```powershell
   # Default Steam install path:
   Expand-Archive "bin\Debug\net6.0\StardewMCP 1.0.0.zip" `
     -DestinationPath "C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods\"
   ```

4. **Launch Stardew Valley through SMAPI** (run `StardewModdingAPI.exe`, not `Stardew Valley.exe`). You should see `[StardewMCP]` listed in the SMAPI console.

5. **Verify the WebSocket is live** (after loading a save):
   ```python
   python -c "
   import websockets.sync.client as ws
   c = ws.connect('ws://localhost:8765/game')
   print(c.recv()[:200])
   "
   ```
   Should print a JSON state message.

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
- Live WebSocket protocol details and actual payload field names
- stardew-mcp mod build notes and compatibility fix
- Pending enhancements backlog
- Development workflow and branching strategy

## Third Party Github Sources

  - https://github.com/MateusAquino/stardewids/tree/main
  - https://github.com/Hunter-Thompson/stardew-mcp/tree/main
  