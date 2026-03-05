@echo off
setlocal enabledelayedexpansion

:: Navigate to project root (two levels up from releases/version_dev1/)
cd /d "%~dp0..\.."

echo.
echo ============================================================
echo   Stardew Valley ESP — MCP Server
echo ============================================================
echo.

:: Activate virtual environment
if not exist ".venv\Scripts\activate.bat" (
    echo   ERROR: Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
call .venv\Scripts\activate.bat

echo   Starting MCP server...
echo   Claude Desktop will connect to this server automatically.
echo.
echo   Close this window or press Ctrl+C to stop the server.
echo.
mcp run agents\stardew_mcp_server.py
