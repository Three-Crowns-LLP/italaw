@echo off
title italaw Downloader

:: ---------------------------------------------------------------
:: Check Python is installed
:: ---------------------------------------------------------------
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Python was not found on this computer.
    echo.
    echo  Please ask IT to install Python from:
    echo    https://www.python.org/downloads/
    echo  or from the Microsoft Store (search "Python").
    echo.
    echo  After installing Python, run this file again.
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------
:: Install / upgrade required libraries (once-off, silent)
:: ---------------------------------------------------------------
echo Installing required libraries (first run only, may take a moment)...
python -m pip install --quiet --upgrade requests beautifulsoup4 lxml 2>nul
if errorlevel 1 (
    echo.
    echo  Could not install libraries automatically.
    echo  Please ask IT to run:  pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------
:: Launch the GUI
:: ---------------------------------------------------------------
echo Starting italaw Downloader...
python "%~dp0italaw_gui.py"
