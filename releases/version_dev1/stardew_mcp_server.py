#!/usr/bin/env python3
"""
Stardew Valley MCP Server
=========================
A Model Context Protocol (MCP) server for Claude Desktop that exposes live
Stardew Valley game state via the stardew-mcp SMAPI mod WebSocket.

REQUIREMENTS:
    pip install mcp websockets

SMAPI MOD:
    1. Install SMAPI: https://smapi.io
    2. Clone & build the stardew-mcp SMAPI mod:
       git clone https://github.com/Hunter-Thompson/stardew-mcp
       cd stardew-mcp/mod/StardewMCP
       dotnet build StardewMCP.csproj
       # Copy compiled mod folder to the game's Mods directory:
       # C:\\Program Files (x86)\\Steam\\steamapps\\common\\Stardew Valley\\Mods\\
    3. Launch Stardew Valley through SMAPI (not directly).
       The mod broadcasts game state to ws://localhost:8765/game every 1 second.

CLAUDE DESKTOP SETUP:
    Add this to %APPDATA%\\Claude\\claude_desktop_config.json:

    {
      "mcpServers": {
        "stardew-esp": {
          "command": "C:/Users/<you>/AppData/Local/Microsoft/WindowsApps/python.exe",
          "args": ["C:/path/to/Stardew_Valley_ESP/agents/stardew_mcp_server.py"]
        }
      }
    }

    Then restart Claude Desktop. The stardew-esp tools will appear in the
    tool picker when you start a new conversation.

NOTE: All data comes from the live WebSocket (stardew-mcp SMAPI mod).
      The game must be running with SMAPI for any tool to work.
"""

# ─────────────────────────────────────────────────────────────────────────────
# THIRD-PARTY DEPENDENCIES
# ─────────────────────────────────────────────────────────────────────────────
# stardew-mcp (Hunter-Thompson) — No license specified
#   https://github.com/Hunter-Thompson/stardew-mcp
#   This MCP server connects to the stardew-mcp SMAPI mod's WebSocket endpoint
#   to serve live game state to Claude Desktop.
#
# See THIRD_PARTY.md for full attribution details.
# ─────────────────────────────────────────────────────────────────────────────

import os
import json
import logging
from pathlib import Path

# ── MCP SDK ──────────────────────────────────────────────────────────────────
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    raise SystemExit(
        "mcp package not installed.\n"
        "Run:  pip install mcp\n"
        "Docs: https://github.com/modelcontextprotocol/python-sdk"
    )

# ── Stardew ESP internals ─────────────────────────────────────────────────────
# Import shared logic from game_state_agent in the same directory.
import sys
_here = Path(__file__).parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from game_state_agent import (  # noqa: E402
    GameState,
    DiffEntry,
    MorningBrief,
    LiveAdapter,
    from_live_json,
    get_catchable_fish as _get_catchable_fish,
    build_llm_prompt,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

WS_URL          = os.environ.get("STARDEW_WS_URL", "ws://localhost:8765/game")
ANTHROPIC_MODEL = os.environ.get("STARDEW_COACH_MODEL", "claude-opus-4-6")

# ─────────────────────────────────────────────────────────────────────────────
# MCP SERVER
# ─────────────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "stardew-esp",
    instructions=(
        "You are a Stardew Valley coach with live access to the player's game.\n\n"
        "Tool usage guide:\n"
        "- Always start with get_live_state to understand the current situation.\n"
        "- Use get_surroundings when the player asks about their immediate area, "
        "nearby enemies, or what they can see.\n"
        "- Use get_catchable_fish before any fishing advice.\n"
        "- For complex planning tasks (multi-day strategy, season planning, full "
        "100% roadmap), call generate_coaching_prompt to get rich context, then "
        "reason through the plan yourself using that context. Do not call "
        "run_coaching_agent unless the user explicitly asks to use the API subagent.\n\n"
        "When a user request is simple (single question, quick tip), answer "
        "directly from tool output. When it requires multi-step reasoning or "
        "planning, call generate_coaching_prompt and produce the analysis yourself."
    ),
)

# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_live_state() -> GameState:
    """Connect to the SMAPI WebSocket and return current game state."""
    adapter = LiveAdapter(WS_URL)
    return adapter.get_snapshot()


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_live_state() -> str:
    """
    Get the current live game state from Stardew Valley via the stardew-mcp
    SMAPI mod WebSocket. Returns key stats including: time of day, location,
    position, health, stamina, money, skills, active quests, and top friendships.

    The game must be running with SMAPI and the stardew-mcp mod installed.
    """
    state = _get_live_state()
    brief = MorningBrief(state)
    data  = brief.as_dict()

    # Add live-only fields to the output
    data["live"] = {
        "time_of_day":      state.time_of_day,
        "location":         state.current_location,
        "position":         {"x": state.position_x, "y": state.position_y},
        "health":           state.health,
        "max_health":       state.max_health,
        "stamina":          int(state.stamina),
        "max_stamina":      state.max_stamina,
    }

    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def get_surroundings() -> str:
    """
    Get the player's current surroundings as a 61×61 ASCII tile map plus
    lists of nearby NPCs, monsters, and interactable objects. Useful for
    understanding what's immediately around the player.

    The game must be running with SMAPI and the stardew-mcp mod installed.
    """
    import websockets.sync.client as ws_client  # type: ignore[import]
    import json as _json

    with ws_client.connect(WS_URL, open_timeout=5) as conn:
        conn.send(_json.dumps({"type": "get_state"}))
        for _ in range(20):
            raw = conn.recv(timeout=3)
            msg = _json.loads(raw)
            if msg.get("type") in ("state", "response") and "data" in msg:
                data = msg["data"]
                sur  = data.get("surroundings", {})
                p    = data.get("player", {})
                t    = data.get("time", {})
                result = {
                    "location":     p.get("location", ""),
                    "position":     {"x": p.get("x", 0), "y": p.get("y", 0)},
                    "time":         t.get("timeString", ""),
                    "ascii_map":    sur.get("asciiMap", ""),
                    "nearby_npcs":  sur.get("nearbyNPCs", []),
                    "monsters":     sur.get("nearbyMonsters", []),
                    "objects":      sur.get("nearbyObjects", []),
                }
                return _json.dumps(result, indent=2, ensure_ascii=False)

    return json.dumps({"error": "No surroundings data received"})


@mcp.tool()
def get_catchable_fish() -> str:
    """
    List every fish catchable right now based on the current season, weather,
    and fishing skill level. Includes location hints and minimum skill requirements.
    """
    state = _get_live_state()
    fish  = _get_catchable_fish(
        state.season, state.is_raining, state.fishing_level,
        has_rusty_key=state.has_rusty_key,
        mine_level=state.deepest_mine_level,
        has_island_access=state.golden_walnuts_found > 0,
    )
    result = {
        "season":         state.season,
        "is_raining":     state.is_raining,
        "fishing_level":  state.fishing_level,
        "catchable_fish": [
            {"name": name, "location": loc, "note": note}
            for name, loc, note in fish
        ],
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_coaching_prompt() -> str:
    """
    Generate a structured coaching prompt that summarises the player's current
    game state from the live WebSocket. Returns the full context text ready
    for multi-step planning and reasoning.

    The game must be running with SMAPI and the stardew-mcp mod installed.
    """
    state  = _get_live_state()
    brief  = MorningBrief(state)
    prompt = build_llm_prompt(brief, diff=None)
    return prompt


@mcp.tool()
def run_coaching_agent(task: str = "") -> str:
    """
    Spawn a dedicated Claude subagent to perform complex multi-step analysis
    using the full game state as context. Use this for tasks that require
    deep reasoning, multi-day planning, or cross-system strategy — for example:

    - "Plan the most efficient path to complete the Community Center"
    - "Which skills should I level up first to maximise income this season?"
    - "Give me a full 28-day Winter plan to prepare for Year 3"
    - "What's the optimal farming strategy given my current tools and budget?"

    Args:
        task: Optional specific question or goal to focus the subagent on.
              If omitted, the subagent produces a full daily walkthrough.

    Returns the subagent's full analysis as text.

    Requires: pip install anthropic
    Environment: ANTHROPIC_API_KEY must be set.
    """
    try:
        import anthropic  # type: ignore[import]
    except ImportError:
        return (
            "anthropic package not installed. Run: pip install anthropic\n"
            "Also set ANTHROPIC_API_KEY in your environment."
        )

    state  = _get_live_state()
    brief  = MorningBrief(state)
    prompt = build_llm_prompt(brief, diff=None)

    if task:
        prompt += f"\n\n---\n## Specific Task\n{task}\n"

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# PROMPTS
# ─────────────────────────────────────────────────────────────────────────────

@mcp.prompt()
def start_coaching() -> str:
    """Start a Stardew Valley coaching session. Checks your live game
    state and gives you a personalised daily plan."""
    return (
        "I just started playing Stardew Valley. Check my live game state "
        "and give me a full coaching briefing for today — what should I "
        "focus on, what fish can I catch, how are my bundles looking, "
        "and any tips based on the current weather and luck."
    )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
