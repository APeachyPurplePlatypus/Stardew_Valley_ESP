# Stardew Valley ESP

An intelligent (read as sloppy and expensive) agent that reads your Stardew Valley save files and generates a personalised daily walkthrough to help you 100% the game as efficiently as possible.

The agent tracks your progress day-to-day, alerts you to tasks nearing completion, and adapts its coaching to your current season, luck, relationships, and active quests. It does not highlight entities, provide wallhacks, or modify the game in any way — it only reads save data.

---

## Features

- **Morning Brief** — every time you sleep in-game, the agent wakes up with you: current luck, weather forecast, wallet, active quests, and top relationships shown in a clean terminal summary. JSON output is grouped into logical sections (`daily`, `progress`, `collections`, `profile`, `community_center`) for easy consumption by LLMs and downstream tools
- **Daily Diff** — compares yesterday's save against today's to report exactly what you accomplished: money changes, 15 tracked stats (including steps taken), skill level-ups, quests completed, friendships gained, fish caught, mine depth progress, house upgrades, unlock flags, bundle donations, new recipes, new minerals/artifacts, new achievements. Each change is a structured `DiffEntry` with category, importance level (1-3), and optional numeric delta — displayed sorted by importance (level-ups and unlocks first, minor stats last)
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
scripts/         Utility scripts (XML → Excel dumper, MCP configurator)
mods/            Pre-built SMAPI mods (StardewMCP) for easy installation
saves/           Stardew Valley save folders (committed for dev/testing)
output/          Generated outputs — recreated on each run, not committed
WORKFLOW.md      Architecture, data flow, and development notes
```

---

## Quick Start

### Prerequisites

- **Python 3.10+** — [python.org/downloads](https://python.org/downloads/) (check "Add Python to PATH" on Windows)
- **Stardew Valley** — Steam, GOG, or any PC version
- **Git** — to clone the repo ([git-scm.com](https://git-scm.com/))

### 1. Clone the repo

```bash
git clone https://github.com/APeachyPurplePlatypus/Stardew_Valley_ESP.git
cd Stardew_Valley_ESP
```

### 2. Run the setup script

**Windows:**
```
releases\version_dev1\setup.bat
```

**macOS / Linux:**
```bash
chmod +x releases/version_dev1/setup.sh
./releases/version_dev1/setup.sh
```

The setup script will:
1. Create a Python virtual environment and install all dependencies
2. Install Claude Desktop if not already present (winget on Windows, brew/dpkg on macOS/Linux)
3. Configure Claude Desktop's MCP server for stardew-esp (auto-detects paths)
4. Install SMAPI if not present (downloads latest from GitHub)
5. Copy the bundled StardewMCP mod to your Stardew Valley Mods folder
6. Launch Claude Desktop when finished

### 3. Launch the game

Start Stardew Valley through **SMAPI** (run `StardewModdingAPI.exe`, not `Stardew Valley.exe`). You should see `[StardewMCP]` in the SMAPI console window — this confirms the mod is loaded.

### 4. Start coaching

Open Claude Desktop, click the **+** button in the chat input, and select **"Start Coaching"**. Claude will read your live game state and give you a personalised daily briefing.

You can also ask Claude anything directly — it has real-time access to your game.

<img src="images/Screenshot%202026-03-04%20201437.png" alt="Claude Desktop with stardew-esp MCP connected" width="45%">

### Verify everything is working

After loading a save, you can confirm the WebSocket is live:

```bash
python -c "
import websockets.sync.client as ws
c = ws.connect('ws://localhost:8765/game')
print(c.recv()[:200])
"
```

If this prints a JSON message, you're all set. If it fails, see the [FAQ](FAQ.md) for troubleshooting.

> **Optional:** set the `ANTHROPIC_API_KEY` environment variable to enable the `run_coaching_agent` tool (spawns a separate Claude API call for deep analysis). This is not required — Claude Desktop can do complex planning without it.

### Manual Setup

If you prefer to set things up manually:

```bash
# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

# Install all dependencies
pip install -r releases/version_dev1/requirements.txt

# Configure Claude Desktop MCP (auto-detects paths)
python scripts/configure_mcp.py
```

For SMAPI and mod installation, see [Live Setup](#live-setup) below.

---

## Usage

### Claude Desktop (recommended)
After running the setup script, launch Stardew Valley through SMAPI and open Claude Desktop.

To start coaching, click the **+** button in the chat input and select **"Start Coaching"** — this pre-fills a prompt that triggers a full daily briefing with zero typing.

You can also ask Claude anything directly:

- *"What should I do today?"*
- *"What's my Community Center progress?"*
- *"Plan the most efficient path to 100% this season"*

Claude has real-time access to your game state, surroundings, inventory, and save data.

### Live WebSocket Mode (CLI)
The default CLI mode. Connects to the stardew-mcp SMAPI mod for real-time game state — time of day, player position, 61×61 ASCII surroundings map, and everything from save files.

```bash
# Watch mode — re-analyses on each new in-game day (default):
python agents/game_state_agent.py --live

# One live snapshot:
python agents/game_state_agent.py --live --once

# Custom WebSocket URL:
python agents/game_state_agent.py --live --live-url ws://localhost:8765/game
```

### Save-File Mode (offline)
Works without the game running — reads save files directly. Useful for testing or offline analysis.

```bash
# Watch mode — triggers on each in-game sleep:
python agents/game_state_agent.py

# One-shot analysis:
python agents/game_state_agent.py --once

# Against dev saves in this repo:
python agents/game_state_agent.py --saves-dir saves --once

# JSON output only (for piping to other tools):
python agents/game_state_agent.py --saves-dir saves --json
```

The agent watches `%APPDATA%\StardewValley\Saves` by default on Windows.

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

> **Note:** If you used `setup.bat` or `setup.sh`, steps 1–3 were done automatically. Skip to step 4.

1. **Complete [Live Setup](#live-setup)** (SMAPI + StardewMCP mod) — required for live tools. Save-file tools work without the game running.

2. **Install Python MCP SDK:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Claude Desktop** — run the auto-configurator:
   ```bash
   python scripts/configure_mcp.py
   ```
   This merges the `stardew-esp` MCP server entry into your Claude Desktop config, auto-detecting all paths. Existing MCP servers are preserved.

   > To configure manually, edit `%APPDATA%\Claude\claude_desktop_config.json`:
   > ```json
   > {
   >   "mcpServers": {
   >     "stardew-esp": {
   >       "command": "C:/path/to/.venv/Scripts/python.exe",
   >       "args": ["C:/path/to/Stardew_Valley_ESP/agents/stardew_mcp_server.py"],
   >       "env": {
   >         "STARDEW_SAVES_DIR": "C:/Users/<you>/AppData/Roaming/StardewValley/Saves"
   >       }
   >     }
   >   }
   > }
   > ```
   > Optional: add `"ANTHROPIC_API_KEY": "sk-ant-..."` to the `env` block to enable `run_coaching_agent`.

4. **Restart Claude Desktop** fully (quit from system tray, relaunch). The stardew-esp tools will appear in the tool picker (hammer icon).

5. **Start a conversation.** Example prompts:
   - *"What should I do today?"* — Claude calls `get_live_state` and advises
   - *"What's my Community Center progress?"* — calls `get_bundle_status`
   - *"Plan the most efficient path to 100% this season"* — calls `generate_coaching_prompt` then reasons through a full plan

---

## Live Setup

Both `--live` mode and the live Claude Desktop MCP tools require **SMAPI** and the **StardewMCP mod**.

> **Note:** If you used `setup.bat` or `setup.sh`, SMAPI and the StardewMCP mod were installed automatically. Skip to step 3.

1. **Install SMAPI:** https://smapi.io

2. **Install the StardewMCP mod** — a pre-built copy is included in `mods/StardewMCP/`. Copy it to your game's Mods folder:
   ```powershell
   # Windows (default Steam path):
   xcopy /s /i mods\StardewMCP "C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\Mods\StardewMCP"
   ```
   ```bash
   # Linux:
   cp -r mods/StardewMCP ~/.steam/steam/steamapps/common/Stardew\ Valley/Mods/
   ```

   > Alternatively, build from source: see [Hunter-Thompson/stardew-mcp](https://github.com/Hunter-Thompson/stardew-mcp) and `WORKFLOW.md §7` for build notes.

3. **Launch Stardew Valley through SMAPI** (run `StardewModdingAPI.exe`, not `Stardew Valley.exe`). You should see `[StardewMCP]` listed in the SMAPI console.

4. **Verify the WebSocket is live** (after loading a save):
   ```python
   python -c "
   import websockets.sync.client as ws
   c = ws.connect('ws://localhost:8765/game')
   print(c.recv()[:200])
   "
   ```
   Should print a JSON state message.

---

## Output Files

All generated files land in `output/` and are gitignored (recreated on each run):

| File | Description |
|---|---|
| `output/morning_brief.json` | Structured game state as JSON (grouped: `daily`, `progress`, `collections`, `profile`, `community_center`) |
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

## Third-Party Sources

This project uses data and tools from:

- **[SMAPI](https://github.com/Pathoschild/SMAPI)** (Pathoschild) — LGPL v3 — Stardew Valley modding API
- **[stardewids](https://github.com/MateusAquino/stardewids)** (MateusAquino) — MIT — item ID-to-name mappings
- **[stardew-mcp](https://github.com/Hunter-Thompson/stardew-mcp)** (Hunter-Thompson) — SMAPI WebSocket mod

See [THIRD_PARTY.md](THIRD_PARTY.md) for full attribution and license details.

## FAQ & Troubleshooting

Having issues? Check the [FAQ](FAQ.md) for solutions to common problems including setup issues, WebSocket connection failures, empty game state, and Claude Desktop configuration.

---

## Token Usage Estimates

Approximate token costs when using Claude Desktop with the stardew-esp MCP tools:

| Component | Tokens | Notes |
|---|---|---|
| MCP server instructions | ~200 | System prompt, loaded once per conversation |
| "Start Coaching" prompt | ~50 | Pre-filled user message |
| `get_live_state` response | ~7,000 | Full morning brief JSON (~28 KB) |
| `get_catchable_fish` response | ~500 | Fish list for current season/weather |
| `get_bundle_status` response | ~1,500 | Community Center bundle progress |
| `generate_coaching_prompt` response | ~1,500 | Structured coaching text (~5.7 KB) |
| Claude's coaching response | ~500–1,000 | Depends on complexity of advice |

**Typical first interaction (Start Coaching):** ~10,000–11,000 tokens

This assumes Claude calls `get_live_state` + `get_catchable_fish` + `get_bundle_status` to build a full daily briefing. Follow-up questions within the same conversation are cheaper since context is already loaded.
