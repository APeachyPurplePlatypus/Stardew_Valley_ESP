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
       cd stardew-mcp
       dotnet build StardewMod
       # Copy compiled mod folder to %APPDATA%\\StardewValley\\Mods\\
    3. Launch Stardew Valley through SMAPI (not directly).
       The mod broadcasts game state to ws://localhost:8765/game every 1 second.

CLAUDE DESKTOP SETUP:
    Add this to %APPDATA%\\Claude\\claude_desktop_config.json:

    {
      "mcpServers": {
        "stardew-esp": {
          "command": "python",
          "args": ["C:/path/to/Stardew_Valley_ESP/agents/stardew_mcp_server.py"],
          "env": {}
        }
      }
    }

    Then restart Claude Desktop. The stardew-esp tools will appear in the
    tool picker when you start a new conversation.

SAVE FILE (OPTIONAL):
    Set STARDEW_SAVES_DIR to read bundle / fish-collection data from your
    save files (the WebSocket does not include historical progress data):

    "env": {
      "STARDEW_SAVES_DIR": "C:/Users/<you>/AppData/Roaming/StardewValley/Saves"
    }
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional

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
    SaveParser,
    LiveAdapter,
    from_live_json,
    get_catchable_fish,
    build_llm_prompt,
    DEFAULT_SAVES_DIR,
)

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

WS_URL          = os.environ.get("STARDEW_WS_URL", "ws://localhost:8765/game")
SAVES_DIR       = Path(os.environ.get("STARDEW_SAVES_DIR", str(DEFAULT_SAVES_DIR)))
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
        "- Use get_bundle_status when discussing Community Center progress.\n"
        "- Use get_fish_collection when the player asks about their fish collection.\n"
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


def _get_save_state() -> Optional[GameState]:
    """Parse the most recent save file (for historical data)."""
    if not SAVES_DIR.exists():
        return None
    try:
        folders = [f for f in SAVES_DIR.iterdir() if f.is_dir()]
        if not folders:
            return None
        save_folder = max(folders, key=lambda f: f.stat().st_mtime)
        return SaveParser(save_folder, use_old=False).parse()
    except Exception as exc:
        log.warning(f"Could not parse save file: {exc}")
        return None


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
    adapter = LiveAdapter(WS_URL)

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
    fish  = get_catchable_fish(state.season, state.is_raining, state.fishing_level)
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
def get_bundle_status() -> str:
    """
    Return Community Center bundle progress read from the most recent save
    file. Shows which bundles are complete, how many items have been donated
    per bundle, and what items are still needed.

    Note: bundle data comes from the save file (written when you sleep), not
    the live WebSocket, so it reflects your state as of last sleep.
    """
    state = _get_save_state()
    if state is None:
        return json.dumps({
            "error": (
                f"Save directory not found or unreadable: {SAVES_DIR}. "
                "Set the STARDEW_SAVES_DIR environment variable in "
                "claude_desktop_config.json."
            )
        })

    cc = {
        "rooms_complete": state.cc_rooms_complete,
        "rooms_done":     sum(state.cc_rooms_complete) if state.cc_rooms_complete else 0,
        "rooms_total":    len(state.cc_rooms_complete) if state.cc_rooms_complete else 6,
        "all_complete":   all(state.cc_rooms_complete) if state.cc_rooms_complete else False,
        "bundles": [
            {
                "id":          b.id,
                "name":        b.name,
                "room":        b.room,
                "donated":     b.items_donated,
                "required":    b.required,
                "total":       b.items_total,
                "is_complete": b.is_done(),
                "missing_items": [
                    {"name": it.item_name, "qty": it.quantity, "quality": it.quality}
                    for it in b.missing_items()
                ],
            }
            for b in state.cc_bundles
        ],
    }
    return json.dumps(cc, indent=2, ensure_ascii=False)


@mcp.tool()
def get_fish_collection() -> str:
    """
    Return the player's fish collection — all species caught so far with catch
    counts, read from the most recent save file.

    Note: fish collection data comes from the save file (written when you
    sleep), not the live WebSocket.
    """
    state = _get_save_state()
    if state is None:
        return json.dumps({"error": f"Save directory not found: {SAVES_DIR}"})

    result = {
        "total_species": len(state.fish_caught),
        "species":       sorted(
            [{"name": name, "caught": count} for name, count in state.fish_caught.items()],
            key=lambda x: x["name"],
        ),
    }
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def generate_coaching_prompt() -> str:
    """
    Generate a structured coaching prompt that summarises the player's
    current game state — combining live WebSocket data (if the game is
    running) with save-file data (fish collection, bundles).

    The returned text is the same prompt used by the CLI agent. You can
    read it, summarise it, or use it as context for planning the player's day.
    """
    # Prefer live state; fall back to save-file state
    try:
        state = _get_live_state()
    except Exception:
        state = _get_save_state()
        if state is None:
            return "Error: neither the SMAPI WebSocket nor a save file is accessible."

    # Overlay save-file data (bundles, fish) if available
    save_state = _get_save_state()
    if save_state is not None:
        state.fish_caught      = save_state.fish_caught
        state.cc_bundles       = save_state.cc_bundles
        state.cc_rooms_complete = save_state.cc_rooms_complete
        state.daily_luck       = save_state.daily_luck

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

    # Build the base coaching prompt (live + save-file data combined)
    try:
        state = _get_live_state()
    except Exception:
        state = _get_save_state()
        if state is None:
            return "Error: neither the SMAPI WebSocket nor a save file is accessible."

    save_state = _get_save_state()
    if save_state is not None:
        state.fish_caught       = save_state.fish_caught
        state.cc_bundles        = save_state.cc_bundles
        state.cc_rooms_complete = save_state.cc_rooms_complete
        state.daily_luck        = save_state.daily_luck

    brief  = MorningBrief(state)
    prompt = build_llm_prompt(brief, diff=None)

    # Append the specific task if provided
    if task:
        prompt += f"\n\n---\n## Specific Task\n{task}\n"

    # Call the Claude subagent
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
