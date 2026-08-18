@echo off
chcp 65001 >nul
title Yuz Ayirici
cd /d "%~dp0"
set "PY=py -3"
if exist python_yolu.txt set /p PY=<python_yolu.txt
%PY% pencere.py
if errorlevel 1 pause
