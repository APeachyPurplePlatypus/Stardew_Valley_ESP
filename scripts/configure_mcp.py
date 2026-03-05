#!/usr/bin/env python3
"""
Configure Claude Desktop MCP — Stardew Valley ESP
====================================================
Merges the stardew-esp MCP server entry into Claude Desktop's config file.
Preserves any existing MCP servers already configured.

Called automatically by setup.bat / setup.sh.
Can also be run standalone: python scripts/configure_mcp.py
"""

import json
import os
import platform
import sys
from pathlib import Path


def get_config_path() -> Path:
    """Return the platform-specific Claude Desktop config path."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", "")
        return Path(base) / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_python_path() -> str:
    """Return the full path to the current Python executable."""
    return sys.executable


def get_saves_dir() -> str:
    """Return the default Stardew Valley saves directory for this platform."""
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        return str(Path(appdata) / "StardewValley" / "Saves")
    elif system == "Darwin":
        return str(Path.home() / ".config" / "StardewValley" / "Saves")
    else:  # Linux
        return str(Path.home() / ".config" / "StardewValley" / "Saves")


def configure():
    config_path = get_config_path()
    project_dir = Path(__file__).resolve().parent.parent
    mcp_server_script = str(project_dir / "agents" / "stardew_mcp_server.py")
    python_path = get_python_path()
    saves_dir = get_saves_dir()

    # Read existing config or start fresh
    config = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
            print(f"  Read existing config: {config_path}")
        except (json.JSONDecodeError, OSError) as e:
            print(f"  Warning: could not parse existing config ({e}), starting fresh")

    # Ensure mcpServers key exists
    if "mcpServers" not in config:
        config["mcpServers"] = {}

    # Merge the stardew-esp entry
    config["mcpServers"]["stardew-esp"] = {
        "command": python_path.replace("\\", "/"),
        "args": [mcp_server_script.replace("\\", "/")],
        "env": {
            "STARDEW_SAVES_DIR": saves_dir.replace("\\", "/")
        }
    }

    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write back
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8"
    )

    print(f"  Claude Desktop MCP configured:")
    print(f"    Config file:  {config_path}")
    print(f"    Python:       {python_path}")
    print(f"    MCP server:   {mcp_server_script}")
    print(f"    Saves dir:    {saves_dir}")
    print()
    print("  Restart Claude Desktop fully (quit from system tray, relaunch)")
    print("  to pick up the new stardew-esp MCP server.")


if __name__ == "__main__":
    print()
    print("=== Configuring Claude Desktop MCP for Stardew Valley ESP ===")
    print()
    configure()
