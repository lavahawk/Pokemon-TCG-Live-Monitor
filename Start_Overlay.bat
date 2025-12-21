@echo off
echo Starting TCG Live Monitor Overlay (Standalone)...
echo.
echo NOTE: The overlay now auto-starts with the main monitor.
echo       Use this only if you want the overlay without monitoring.
echo.
echo The overlay will:
echo - Follow Pokemon TCG Live window (bottom-right corner)
echo - Show Elo with league pokeball icon
echo - Display max Elo and today's W/L record
echo - Allow click-through (won't block gameplay)
echo.
python OverlayUI.py
