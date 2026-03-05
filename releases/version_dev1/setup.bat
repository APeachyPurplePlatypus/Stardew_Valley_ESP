@echo off
setlocal enabledelayedexpansion

:: Navigate to project root (two levels up from releases/version_dev1/)
cd /d "%~dp0..\.."

echo.
echo ============================================================
echo   Stardew Valley ESP — One-Click Setup  [DEV1]
echo ============================================================
echo.

:: ── Step 1: Check Python ──────────────────────────────────────
echo [1/6] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   ERROR: Python is not installed or not in PATH.
    echo   Please install Python 3.10+ from https://www.python.org/downloads/
    echo   Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo   Found Python %PYVER%

:: ── Step 2: Create virtual environment + install deps ─────────
echo.
echo [2/6] Setting up Python virtual environment...
if not exist ".venv" (
    python -m venv .venv
    echo   Created .venv
) else (
    echo   .venv already exists
)
call .venv\Scripts\activate.bat
echo   Installing dependencies...
pip install -r releases\version_dev1\requirements.txt --quiet
echo   Dependencies installed.

:: ── Step 3: Claude Desktop ────────────────────────────────────
echo.
echo [3/6] Checking Claude Desktop...
set "CLAUDE_EXE=%LOCALAPPDATA%\AnthropicClaude\claude.exe"
if not exist "!CLAUDE_EXE!" (
    set "CLAUDE_EXE=%LOCALAPPDATA%\Programs\claude-desktop\claude.exe"
)
if exist "!CLAUDE_EXE!" (
    echo   Claude Desktop found.
) else (
    echo   Claude Desktop not found. Installing via winget...
    winget install Anthropic.Claude --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo   WARNING: winget install failed. Please install Claude Desktop manually:
        echo   https://claude.ai/download
    ) else (
        echo   Claude Desktop installed successfully.
    )
)

:: ── Step 4: Configure MCP ─────────────────────────────────────
echo.
echo [4/6] Configuring Claude Desktop MCP server...
python scripts\configure_mcp.py

:: ── Step 5: Stardew Valley + SMAPI ────────────────────────────
echo.
echo [5/6] Checking Stardew Valley and SMAPI...

:: Try common Steam install paths
set "SV_DIR="
for %%d in (
    "C:\Program Files (x86)\Steam\steamapps\common\Stardew Valley"
    "C:\Program Files\Steam\steamapps\common\Stardew Valley"
    "D:\Steam\steamapps\common\Stardew Valley"
    "D:\SteamLibrary\steamapps\common\Stardew Valley"
    "E:\Steam\steamapps\common\Stardew Valley"
    "E:\SteamLibrary\steamapps\common\Stardew Valley"
    "G:\SteamLibrary\steamapps\common\Stardew Valley"
) do (
    if exist "%%~d\Stardew Valley.exe" (
        set "SV_DIR=%%~d"
    )
)

if not "!SV_DIR!"=="" goto :sv_found

echo   Could not auto-detect Stardew Valley install path.
set /p SV_DIR="  Enter your Stardew Valley install folder: "
:: Strip surrounding quotes if user included them
set "SV_DIR=!SV_DIR:"=!"

:sv_found
if not exist "!SV_DIR!\Stardew Valley.exe" (
    echo   WARNING: Stardew Valley not found at: !SV_DIR!
    echo   Skipping SMAPI and mod installation.
    goto :skip_smapi
)

echo   Stardew Valley found at: !SV_DIR!

:: Check SMAPI
if exist "!SV_DIR!\StardewModdingAPI.exe" (
    echo   SMAPI is already installed.
    goto :install_mod
)

echo   SMAPI not found. Downloading latest installer...

:: Download latest SMAPI release from GitHub
set "SMAPI_ZIP=%TEMP%\SMAPI-latest.zip"
set "SMAPI_DIR=%TEMP%\SMAPI-install"

powershell -Command ^
    "$release = Invoke-RestMethod -Uri 'https://api.github.com/repos/Pathoschild/SMAPI/releases/latest'; " ^
    "$asset = $release.assets | Where-Object { $_.name -like '*installer*.zip' } | Select-Object -First 1; " ^
    "if ($asset) { " ^
    "  Write-Host \"  Downloading $($asset.name)...\"; " ^
    "  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile '%SMAPI_ZIP%'; " ^
    "  Write-Host '  Download complete.'" ^
    "} else { " ^
    "  Write-Host '  ERROR: Could not find SMAPI installer in latest release.'; " ^
    "  exit 1 " ^
    "}"

if errorlevel 1 (
    echo   WARNING: Failed to download SMAPI.
    echo   Please install SMAPI manually from: https://smapi.io
    goto :skip_smapi
)

:: Extract and run installer
if exist "!SMAPI_DIR!" rmdir /s /q "!SMAPI_DIR!"
powershell -Command "Expand-Archive -Path '%SMAPI_ZIP%' -DestinationPath '%SMAPI_DIR%' -Force"

echo.
echo   SMAPI installer downloaded and extracted.
echo   Running SMAPI installer — follow the prompts:
echo.

:: Find and run the installer
for /r "!SMAPI_DIR!" %%f in (install*.exe) do (
    "%%f"
    goto :smapi_installed
)
:: If no exe found, try the bat
for /r "!SMAPI_DIR!" %%f in (install*.bat) do (
    call "%%f"
    goto :smapi_installed
)
echo   WARNING: Could not find SMAPI installer executable.
echo   Please install SMAPI manually from: https://smapi.io
goto :skip_smapi

:smapi_installed
echo   SMAPI installation complete.
:: Clean up
del "!SMAPI_ZIP!" 2>nul
rmdir /s /q "!SMAPI_DIR!" 2>nul

:: ── Step 6: Install StardewMCP mod ───────────────────────────
:install_mod
echo.
echo [6/6] Installing StardewMCP mod...
set "MODS_DIR=!SV_DIR!\Mods\StardewMCP"
if exist "!MODS_DIR!\StardewMCP.dll" (
    echo   StardewMCP mod already installed.
) else (
    if not exist "!SV_DIR!\Mods" mkdir "!SV_DIR!\Mods"
    xcopy /s /i /y "mods\StardewMCP" "!MODS_DIR!" >nul
    echo   StardewMCP mod copied to: !MODS_DIR!
)
goto :done

:skip_smapi
echo.
echo   Skipped SMAPI/mod installation. You can set these up later.
echo   See README.md for manual instructions.

:done

:: ── Launch Claude Desktop ─────────────────────────────────────
echo.
echo   Launching Claude Desktop...
set "CLAUDE_LAUNCH="
if exist "%LOCALAPPDATA%\AnthropicClaude\claude.exe" (
    set "CLAUDE_LAUNCH=%LOCALAPPDATA%\AnthropicClaude\claude.exe"
) else if exist "%LOCALAPPDATA%\Programs\claude-desktop\claude.exe" (
    set "CLAUDE_LAUNCH=%LOCALAPPDATA%\Programs\claude-desktop\claude.exe"
)
if defined CLAUDE_LAUNCH (
    start "" "!CLAUDE_LAUNCH!"
    echo   Claude Desktop started: !CLAUDE_LAUNCH!
) else (
    echo   Could not find Claude Desktop executable.
    echo   Please launch it manually after setup.
)

echo.
echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo   Quick start:
echo     1. Launch Stardew Valley through SMAPI (StardewModdingAPI.exe)
echo     2. In Claude Desktop, click "+" and select "Start Coaching"
echo.
echo   Save-file mode (no game running):
echo     .venv\Scripts\activate
echo     python agents\game_state_agent.py --saves-dir saves --once
echo.
echo   Optional: Set ANTHROPIC_API_KEY environment variable to enable
echo   the run_coaching_agent tool in Claude Desktop.
echo.
pause
