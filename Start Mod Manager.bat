@echo off
rem Double-click to start Mod Manager (needs Python 3.8+ from python.org, with "Add to PATH" ticked).
cd /d "%~dp0"
py -3 -m modmanager 2>nul || python -m modmanager
if errorlevel 1 (echo.& echo Could not start. Install Python from https://www.python.org/downloads/ and try again.& pause)
