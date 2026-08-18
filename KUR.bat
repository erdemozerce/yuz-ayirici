@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title Yuz Ayirici - Kurulum
cd /d "%~dp0"

echo ================================================================
echo    YUZ AYIRICI - KURULUM
echo ================================================================
echo.
echo Bu pencereyi kapatmayin. Kurulum 10-20 dakika surebilir.
echo.

rem ---------------------------------------------------------------- Python
set "PY="
py -3 --version >nul 2>&1
if %errorlevel%==0 set "PY=py -3"

if not defined PY (
    python --version >nul 2>&1
    if !errorlevel!==0 set "PY=python"
)

if not defined PY (
    echo [1/5] Python bulunamadi, otomatik kuruluyor...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    )
)

if not defined PY (
    echo.
    echo !! Python kurulamadi.
    echo !! Lutfen https://www.python.org/downloads/ adresinden Python 3.12 kurun.
    echo !! Kurulum ekraninda "Add python.exe to PATH" kutusunu ISARETLEYIN.
    echo !! Sonra bu dosyayi tekrar calistirin.
    echo.
    pause
    exit /b 1
)

echo [1/5] Python bulundu:
%PY% --version
echo %PY%> python_yolu.txt

rem ---------------------------------------------------------------- paketler
echo.
echo [2/5] Temel araclar guncelleniyor...
%PY% -m pip install --upgrade pip setuptools wheel --quiet --disable-pip-version-check

echo.
echo [3/5] Gerekli paketler kuruluyor (buyuk indirme, sabir)...
%PY% -m pip install -r gereksinimler.txt --disable-pip-version-check
if !errorlevel! neq 0 (
    echo.
    echo !! Paket kurulumu basarisiz. Internet baglantinizi kontrol edip tekrar deneyin.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------- GPU
echo.
echo [4/5] Ekran karti kontrol ediliyor...
where nvidia-smi >nul 2>&1
if !errorlevel!==0 (
    echo     NVIDIA ekran karti bulundu - hizlandirilmis surum kuruluyor.
    %PY% -m pip uninstall -y onnxruntime --quiet >nul 2>&1
    %PY% -m pip install onnxruntime-gpu --quiet --disable-pip-version-check
    echo gpu> gpu_var.txt
) else (
    echo     NVIDIA ekran karti yok - islemci modunda calisacak ^(daha yavas ama sorunsuz^).
    if exist gpu_var.txt del gpu_var.txt
)

rem ---------------------------------------------------------------- test
echo.
echo [5/5] Yuz tanima modeli indiriliyor ve test ediliyor (~300 MB)...
%PY% kurulum_testi.py
if !errorlevel! neq 0 (
    echo.
    echo !! Test basarisiz oldu. Ekran goruntusu alip gonderin.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------- kisayol
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\Yuz Ayirici.lnk'); $s.TargetPath='%~dp0BASLAT.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\system32\imageres.dll,109'; $s.Save()" >nul 2>&1

echo.
echo ================================================================
echo    KURULUM TAMAM
echo ================================================================
echo.
echo    Masaustunde "Yuz Ayirici" kisayolu olusturuldu.
echo    Programi calistirmak icin ona cift tiklayin.
echo.
pause
