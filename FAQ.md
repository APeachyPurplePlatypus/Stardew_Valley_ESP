# FAQ & Troubleshooting

Common questions and solutions for Stardew Valley ESP.

---

## Setup Issues

### Python is not found or wrong version

**Symptom:** Setup script says Python is not installed, or you get syntax errors when running the agent.

**Solution:**
- Install Python 3.10 or newer from [python.org](https://python.org/downloads/)
- On Windows, make sure to check **"Add Python to PATH"** during installation
- Verify with: `python --version`
- If you have multiple Python versions, use `python3` instead of `python`

---

### Claude Desktop not installed after setup

**Symptom:** Setup script says it installed Claude Desktop but it doesn't appear.

**Solution:**
- **Windows:** Run `winget install Anthropic.Claude` manually in an admin terminal. If winget itself is missing, install Claude Desktop from [claude.ai/download](https://claude.ai/download)
- **macOS:** Run `brew install --cask claude` or download from [claude.ai/download](https://claude.ai/download)
- **Linux:** Download the `.deb` package from [claude.ai/download](https://claude.ai/download) and install with `sudo dpkg -i claude-desktop*.deb`

---

### Claude Desktop doesn't launch after setup

**Symptom:** Setup completes but Claude Desktop doesn't open automatically.

**Solution:**
- Launch Claude Desktop manually from your Start Menu / Applications folder
- On Windows, the executable is typically at:
  - `%LOCALAPPDATA%\AnthropicClaude\claude.exe`
  - `%LOCALAPPDATA%\Programs\claude-desktop\claude.exe`
- The auto-launch is a convenience — manual launch works identically

---

### SMAPI download fails during setup

**Symptom:** Setup script can't download SMAPI from GitHub.

**Solution:**
1. Download SMAPI manually from [smapi.io](https://smapi.io) or the [GitHub releases page](https://github.com/Pathoschild/SMAPI/releases)
2. Run the SMAPI installer and point it to your Stardew Valley installation
3. Re-run the setup script — it will detect SMAPI is already installed and skip that step

---

### Stardew Valley install path not detected

**Symptom:** Setup script can't find your Stardew Valley installation to copy the StardewMCP mod.

**Solution:**
- Copy the mod manually:
  ```
  # From the project root:
  xcopy /s /i mods\StardewMCP "<your Stardew Valley path>\Mods\StardewMCP"
  ```
- Common install locations:
  - **Steam (Windows):** `C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley\`
  - **GOG (Windows):** `C:\Program Files (x86)\GOG Galaxy\Games\Stardew Valley\`
  - **Steam (macOS):** `~/Library/Application Support/Steam/steamapps/common/Stardew Valley/`
  - **Steam (Linux):** `~/.steam/steam/steamapps/common/Stardew Valley/`

---

## MCP / Claude Desktop Issues

### MCP tools don't appear in Claude Desktop

**Symptom:** You open Claude Desktop but don't see the stardew-esp tools in the tool picker (hammer icon).

**Solutions:**
1. **Restart Claude Desktop fully** — quit from the system tray (not just close the window), then relaunch
2. **Verify your config** — open `%APPDATA%\Claude\claude_desktop_config.json` (Windows) and check that the `stardew-esp` server entry exists with correct paths
3. **Re-run the configurator:** `python scripts/configure_mcp.py`
4. **Check the Python path** — the `command` field in the config must point to the Python executable inside your virtual environment (`.venv/Scripts/python.exe` on Windows)

---

### "mcp package not installed" error

**Symptom:** Claude Desktop logs show `mcp package not installed` when trying to use stardew-esp tools.

**Solution:**
- Activate your virtual environment and install dependencies:
  ```bash
  .venv\Scripts\activate        # Windows
  # source .venv/bin/activate   # macOS/Linux
  pip install -r releases/version_dev1/requirements.txt
  ```
- Make sure the MCP config `command` points to `.venv/Scripts/python.exe`, not your system Python

---

### "Start Coaching" prompt not showing

**Symptom:** You click the "+" button in Claude Desktop but don't see the "Start Coaching" option.

**Solution:**
- MCP prompts appear under the "+" menu in the chat input area
- Make sure you've restarted Claude Desktop after setup
- Verify the MCP server is running (check Claude Desktop's developer console for errors)
- You can always type the prompt manually instead — the "Start Coaching" button is just a convenience

---

## Live Game Issues

### WebSocket connection fails

**Symptom:** Tools return errors about connecting to `ws://localhost:8765/game`.

**Solutions:**
1. **Is the game running?** Stardew Valley must be running through SMAPI (not launched directly)
2. **Is the mod loaded?** Check the SMAPI console window for `[StardewMCP]` in the startup messages
3. **Have you loaded a save?** The WebSocket only broadcasts data after you've loaded into a farm — it won't work from the title screen
4. **Test the connection manually:**
   ```python
   python -c "
   import websockets.sync.client as ws
   c = ws.connect('ws://localhost:8765/game')
   print(c.recv()[:200])
   "
   ```

---

### Live state returns empty or zero data

**Symptom:** `get_live_state` returns data but everything is empty — player name is blank, day is 0, money is 0.

**Cause:** You're on the title screen or a menu. The game broadcasts empty state when no save is loaded.

**Solution:** Load into your farm first, then try again. The data populates once you're in-game.

---

### SMAPI console shows errors for StardewMCP

**Symptom:** SMAPI loads but shows red error messages related to StardewMCP.

**Solutions:**
- Make sure your Stardew Valley is version **1.6** or newer (the mod targets 1.6+)
- Make sure SMAPI is up to date — download the latest from [smapi.io](https://smapi.io)
- Verify the mod files are complete in `Mods/StardewMCP/`:
  - `StardewMCP.dll`
  - `manifest.json`
  - `websocket-sharp.dll`

---

### Surroundings map shows wrong area

**Symptom:** The ASCII map from `get_surroundings` doesn't match where you think you are.

**Explanation:** The surroundings map is a 61x61 tile snapshot centred on the player's current position. It updates every ~1 second. If you moved since the last update, the map may be slightly behind. Call the tool again for a fresh snapshot.

---

## Save File Issues

### Save file tools return stale data

**Symptom:** `get_bundle_status` or `get_fish_collection` show yesterday's data.

**Explanation:** Save-file-based tools read from your last save. Stardew Valley only writes save files when you go to sleep. The data will update after your next in-game sleep.

---

### Save directory not found

**Symptom:** Agent can't find your save files.

**Solution:**
- The default save location on Windows is: `%APPDATA%\StardewValley\Saves`
- Set the `STARDEW_SAVES_DIR` environment variable to your saves folder, or pass `--saves-dir` when running the CLI agent
- For MCP, add `STARDEW_SAVES_DIR` to the `env` block in your Claude Desktop MCP config

---

## Coaching / API Issues

### `run_coaching_agent` says API key not set

**Symptom:** The `run_coaching_agent` tool returns an error about missing `ANTHROPIC_API_KEY`.

**Explanation:** This tool spawns a separate Claude API call, which requires a paid API key. It is **optional** — Claude Desktop can do complex planning without it by using `generate_coaching_prompt` instead.

**If you want to use it:**
1. Get an API key from [console.anthropic.com](https://console.anthropic.com)
2. Add it to your MCP config's `env` block:
   ```json
   "env": {
     "ANTHROPIC_API_KEY": "sk-ant-..."
   }
   ```
3. Restart Claude Desktop

---

## General

### How many tokens does a coaching session use?

A typical first interaction (using "Start Coaching") uses approximately **10,000–11,000 tokens**. See the [Token Usage Estimates](README.md#token-usage-estimates) section in the README for a full breakdown.

### Does this modify my game or save files?

No. Stardew Valley ESP is **read-only**. It reads save files and receives game state over WebSocket but never writes to or modifies anything in the game. It does not provide wallhacks, entity highlighting, or any gameplay modifications.

### Can I use this with multiplayer?

The agent reads from the host player's save file and WebSocket connection. It has not been tested with split-screen or multiplayer farmhands. It should work for the host player in a multiplayer session, but farmhand data may be incomplete.
