# Stardew Valley ESP

An intelligent agent that reads your Stardew Valley save files and generates a personalised daily walkthrough to help you 100% the game as efficiently as possible.

The agent tracks your progress day-to-day, alerts you to tasks nearing completion, and adapts its coaching to your current season, luck, relationships, and active quests. It does not highlight entities, provide wallhacks, or modify the game in any way — it only reads save data.

---

## Features

- **Morning Brief** — every time you sleep in-game, the agent wakes up with you: current luck, weather forecast, wallet, active quests, and top relationships shown in a clean terminal summary
- **Daily Diff** — compares yesterday's save against today's to report exactly what you accomplished: stone mined, fish caught, quests completed, friendships gained, level-ups, new bundle donations
- **Fish Availability** — lists every fish catchable right now based on your current season, weather, and fishing level — including location hints and skill requirements
- **Community Center Tracker** — parses bundle definitions directly from your save file (works with remixed bundles too), tracks donation progress per slot, and surfaces the bundles closest to completion with their missing items
- **LLM Coaching Prompt** — generates a structured prompt and optionally sends it to a local Ollama model for a step-by-step personalised walkthrough for the new day; fishing conditions and bundle status are included in context
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

### Ollama Integration (Local LLM)
Pass `--ollama` to send the coaching prompt to a local [Ollama](https://ollama.com) model and save the response to `output/coach_response.md`.

```bash
# Default model: ministral:8b, default URL: http://localhost:11434
python agents/game_state_agent.py --saves-dir saves --once --ollama

# Choose a different model
python agents/game_state_agent.py --saves-dir saves --once --ollama --ollama-model mistral-small3.1:24b

# Point at a remote Ollama instance
python agents/game_state_agent.py --saves-dir saves --once --ollama --ollama-url http://192.168.1.5:11434

# Increase timeout for large/slow models (default: 300s)
python agents/game_state_agent.py --saves-dir saves --once --ollama --ollama-timeout 600

# Disable chain-of-thought reasoning for thinking models (qwen3, deepseek-r1)
python agents/game_state_agent.py --saves-dir saves --once --ollama --ollama-model qwen3:8b --no-think
```

Ollama must be running and the model must be pulled before use:
```bash
ollama pull mistral-small3.1:24b
```

Without `--ollama` the agent still runs as before — `coach_prompt.txt` is written but no LLM is called.

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

### Local (Ollama) — recommended, no API key needed

Use the `--ollama` flag (see [Usage](#usage) above). The response is printed to the terminal and saved to `output/coach_response.md`.

### Cloud (Claude API)

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
| `output/coach_response.md` | LLM response from Ollama (only when `--ollama` is used) |
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
