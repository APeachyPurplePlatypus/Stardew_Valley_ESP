Stardew Valley ESP — DEV1 Release
===================================

An intelligent agent that reads your live Stardew Valley game state and
generates personalised coaching through Claude Desktop.

Quick Start (Windows)
---------------------
1. Double-click setup.bat
   - Installs Python (if needed), Claude Desktop, SMAPI, and the StardewMCP mod
   - Configures Claude Desktop to connect to the MCP server
   - Starts the MCP server when finished

2. Launch Stardew Valley through SMAPI (StardewModdingAPI.exe)

3. In Claude Desktop, click "+" and select "Start Coaching"

To start the server again later, run start.bat.

Quick Start (macOS / Linux)
---------------------------
1. chmod +x setup.sh && ./setup.sh
2. Launch Stardew Valley through SMAPI
3. In Claude Desktop, click "+" and select "Start Coaching"

What's in this folder
---------------------
setup.bat / setup.sh    One-click setup scripts (Windows / macOS+Linux)
start.bat               Launches the MCP server after initial setup
requirements.txt        Python package dependencies
stardew_mcp_server.py   MCP server — exposes game state to Claude Desktop
game_state_agent.py     Core agent — parses saves, connects to WebSocket
configure_mcp.py        Auto-configures Claude Desktop MCP settings
mods/StardewMCP/        Pre-built SMAPI mod for live game state

Requirements
------------
- Python 3.10+ (auto-installed by setup if missing)
- Stardew Valley (Steam, GOG, or any PC version)
- Claude Desktop (auto-installed by setup if missing)

Troubleshooting
---------------
- If tools don't appear in Claude Desktop, restart it fully (quit from
  system tray, not just close the window).
- If live state returns empty data, make sure you've loaded a save in
  Stardew Valley (not just the title screen).
- See FAQ.md in the main repository for more solutions.

Repository: https://github.com/APeachyPurplePlatypus/Stardew_Valley_ESP
