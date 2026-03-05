#!/usr/bin/env bash
set -euo pipefail

# Navigate to project root (two levels up from releases/version_dev1/)
cd "$(dirname "$0")/../.."

echo ""
echo "============================================================"
echo "  Stardew Valley ESP — One-Click Setup  [DEV1]"
echo "============================================================"
echo ""

# ── Step 1: Check Python ──────────────────────────────────────
echo "[1/6] Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "  ERROR: Python 3 is not installed."
    echo "  Install it with your package manager:"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "    macOS:         brew install python"
    exit 1
fi
PYVER=$(python3 --version 2>&1)
echo "  Found $PYVER"

# ── Step 2: Create virtual environment + install deps ─────────
echo ""
echo "[2/6] Setting up Python virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "  Created .venv"
else
    echo "  .venv already exists"
fi
source .venv/bin/activate
echo "  Installing dependencies..."
pip install -r releases/version_dev1/requirements.txt --quiet
echo "  Dependencies installed."

# ── Step 3: Claude Desktop ────────────────────────────────────
echo ""
echo "[3/6] Checking Claude Desktop..."
CLAUDE_INSTALLED=false

if [[ "$(uname)" == "Darwin" ]]; then
    # macOS
    if [ -d "/Applications/Claude.app" ]; then
        CLAUDE_INSTALLED=true
        echo "  Claude Desktop found."
    else
        echo "  Claude Desktop not found. Installing via Homebrew..."
        if command -v brew &>/dev/null; then
            brew install --cask claude
            CLAUDE_INSTALLED=true
            echo "  Claude Desktop installed."
        else
            echo "  WARNING: Homebrew not found. Install Claude Desktop manually:"
            echo "  https://claude.ai/download"
        fi
    fi
else
    # Linux
    if command -v claude &>/dev/null || [ -f "/usr/bin/claude" ] || dpkg -l claude-desktop &>/dev/null 2>&1; then
        CLAUDE_INSTALLED=true
        echo "  Claude Desktop found."
    else
        echo "  Claude Desktop not found. Installing..."
        # Download and install the .deb package
        CLAUDE_DEB="/tmp/claude-desktop.deb"
        echo "  Downloading Claude Desktop .deb package..."
        curl -fSL "https://storage.googleapis.com/anthropic-desktop/claude-desktop-debian.deb" -o "$CLAUDE_DEB" 2>/dev/null || true

        if [ -f "$CLAUDE_DEB" ]; then
            echo "  Installing Claude Desktop (requires sudo)..."
            sudo dpkg -i "$CLAUDE_DEB" || sudo apt-get install -f -y
            rm -f "$CLAUDE_DEB"
            echo "  Claude Desktop installed."
            CLAUDE_INSTALLED=true
        else
            echo "  WARNING: Could not download Claude Desktop."
            echo "  Install manually: https://claude.ai/download"
        fi
    fi
fi

# ── Step 4: Configure MCP ─────────────────────────────────────
echo ""
echo "[4/6] Configuring Claude Desktop MCP server..."
python3 scripts/configure_mcp.py

# ── Step 5: Stardew Valley + SMAPI ────────────────────────────
echo ""
echo "[5/6] Checking Stardew Valley and SMAPI..."

SV_DIR=""
# Common Steam install paths
for dir in \
    "$HOME/.steam/steam/steamapps/common/Stardew Valley" \
    "$HOME/.local/share/Steam/steamapps/common/Stardew Valley" \
    "/Applications/Stardew Valley.app/Contents/MacOS" \
    "$HOME/Library/Application Support/Steam/steamapps/common/Stardew Valley/Contents/MacOS"; do
    if [ -f "$dir/Stardew Valley" ] || [ -f "$dir/StardewValley" ] || [ -f "$dir/Stardew Valley.exe" ]; then
        SV_DIR="$dir"
        break
    fi
done

if [ -z "$SV_DIR" ]; then
    echo "  Could not auto-detect Stardew Valley install path."
    read -rp "  Enter your Stardew Valley install folder (or press Enter to skip): " SV_DIR
fi

if [ -z "$SV_DIR" ] || [ ! -d "$SV_DIR" ]; then
    echo "  Skipping SMAPI and mod installation."
    echo "  See README.md for manual setup instructions."
else
    echo "  Stardew Valley found at: $SV_DIR"

    # Check SMAPI
    if [ -f "$SV_DIR/StardewModdingAPI" ] || [ -f "$SV_DIR/StardewModdingAPI.exe" ]; then
        echo "  SMAPI is already installed."
    else
        echo "  SMAPI not found. Downloading latest installer..."

        SMAPI_ZIP="/tmp/SMAPI-latest.zip"
        SMAPI_DIR="/tmp/SMAPI-install"

        # Get latest release download URL from GitHub API
        DOWNLOAD_URL=$(curl -s "https://api.github.com/repos/Pathoschild/SMAPI/releases/latest" \
            | python3 -c "import sys,json; r=json.load(sys.stdin); assets=[a for a in r.get('assets',[]) if 'installer' in a['name'].lower()]; print(assets[0]['browser_download_url'] if assets else '')" 2>/dev/null)

        if [ -n "$DOWNLOAD_URL" ]; then
            echo "  Downloading from: $DOWNLOAD_URL"
            curl -fSL "$DOWNLOAD_URL" -o "$SMAPI_ZIP"
            rm -rf "$SMAPI_DIR"
            mkdir -p "$SMAPI_DIR"
            unzip -q "$SMAPI_ZIP" -d "$SMAPI_DIR"

            echo ""
            echo "  SMAPI installer downloaded and extracted to: $SMAPI_DIR"
            echo "  Please run the SMAPI installer manually:"
            echo "    cd $SMAPI_DIR && find . -name 'install*' -type f"
            echo ""
            echo "  After installing SMAPI, re-run this setup script to install the StardewMCP mod."
        else
            echo "  WARNING: Could not download SMAPI."
            echo "  Please install SMAPI manually from: https://smapi.io"
        fi

        rm -f "$SMAPI_ZIP"
    fi

    # ── Step 6: Install StardewMCP mod ───────────────────────────
    echo ""
    echo "[6/6] Installing StardewMCP mod..."
    MODS_DIR="$SV_DIR/Mods/StardewMCP"
    if [ -f "$MODS_DIR/StardewMCP.dll" ]; then
        echo "  StardewMCP mod already installed."
    else
        mkdir -p "$MODS_DIR"
        cp -r mods/StardewMCP/* "$MODS_DIR/"
        echo "  StardewMCP mod copied to: $MODS_DIR"
    fi
fi

# ── Launch Claude Desktop ─────────────────────────────────────
echo ""
echo "  Launching Claude Desktop..."
if [[ "$(uname)" == "Darwin" ]]; then
    if [ -d "/Applications/Claude.app" ]; then
        open -a Claude
        echo "  Claude Desktop started."
    else
        echo "  Could not find Claude Desktop. Please launch it manually."
    fi
else
    if command -v claude-desktop &>/dev/null; then
        claude-desktop &
        echo "  Claude Desktop started."
    elif [ -f "/usr/bin/claude-desktop" ]; then
        /usr/bin/claude-desktop &
        echo "  Claude Desktop started."
    else
        echo "  Could not find Claude Desktop. Please launch it manually."
    fi
fi

echo ""
echo "============================================================"
echo "  Setup complete!"
echo "============================================================"
echo ""
echo "  Quick start:"
echo "    1. Launch Stardew Valley through SMAPI"
echo "    2. In Claude Desktop, click \"+\" and select \"Start Coaching\""
echo ""
echo "  Save-file mode (no game running):"
echo "    source .venv/bin/activate"
echo "    python3 agents/game_state_agent.py --saves-dir saves --once"
echo ""
echo "  Optional: Set ANTHROPIC_API_KEY environment variable to enable"
echo "  the run_coaching_agent tool in Claude Desktop."
echo ""
