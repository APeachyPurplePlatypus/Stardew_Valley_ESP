# Third-Party Software and Data Sources

This project uses code, data, and tools from the following third-party sources.

---

## SMAPI — Stardew Modding API

- **Author:** Pathoschild
- **Repository:** https://github.com/Pathoschild/SMAPI
- **License:** GNU Lesser General Public License v3.0 (LGPL-3.0)
- **Usage:** Required runtime dependency. The setup script downloads and installs the latest SMAPI release from GitHub. SMAPI is the modding framework that loads the StardewMCP mod into the game. It is not bundled in this repository.
- **License text:** https://github.com/Pathoschild/SMAPI/blob/develop/LICENSE.txt

---

## stardewids

- **Author:** MateusAquino
- **Repository:** https://github.com/MateusAquino/stardewids
- **License:** MIT License
- **Usage:** Item ID-to-display-name mappings from `objects.json` were used to build the following constant dictionaries in `agents/game_state_agent.py`:
  - `MINERAL_NAMES` — mineral item IDs (60–86, 538–578) to display names
  - `ARTIFACT_NAMES` — artifact item IDs (96–127, 580–589) to display names
  - `FISH_ID_NAMES` — fish item IDs to species names
  - `BUNDLE_ITEM_NAMES` — bundle item IDs to display names

  These are static data mappings (not executable code) derived from Stardew Valley 1.6 game data.

---

## stardew-mcp

- **Author:** Hunter-Thompson
- **Repository:** https://github.com/Hunter-Thompson/stardew-mcp
- **License:** No license specified (all rights reserved by default)
- **Usage:** SMAPI mod that exposes live game state via WebSocket (`ws://localhost:8765/game`). A pre-built copy of the compiled mod is bundled in `mods/StardewMCP/` for ease of installation. The following components in this project integrate with its WebSocket protocol:
  - `agents/game_state_agent.py` — `LiveAdapter` class (WebSocket client), `from_live_json()` function (payload mapping)
  - `agents/stardew_mcp_server.py` — MCP server that connects to the stardew-mcp WebSocket to serve live game state to Claude Desktop

  **Note:** This mod has no explicit open-source license. The pre-built binary is included at the repository owner's discretion to simplify user setup. If the upstream author adds a license or requests removal, this will be updated accordingly.
