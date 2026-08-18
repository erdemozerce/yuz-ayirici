@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Yuz Ayirici - Kurulum
cd /d "%~dp0"

echo ================================================================
echo    YUZ AYIRICI - KURULUM
echo ================================================================
echo.

set "PY="
py -3 --version >nul 2>&1
if %errorlevel%==0 set "PY=py -3"
if not defined PY (
    python --version >nul 2>&1
    if !errorlevel!==0 set "PY=python"
)
if not defined PY (
    echo Python bulunamadi, otomatik kuruluyor...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)
if not defined PY (
    echo.
    echo !! Python kurulamadi. https://www.python.org/downloads/ adresinden kurun.
    echo !! Kurulumda "Add python.exe to PATH" kutusunu ISARETLEYIN.
    echo.
    pause
    exit /b 1
)

%PY% "%~dp0kur.py"
