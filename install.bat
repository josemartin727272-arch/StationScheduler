@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set REPO_URL=https://github.com/josemartin727272-arch/StationScheduler.git
set INSTALL_DIR=%USERPROFILE%\StationScheduler
set DESKTOP=%USERPROFILE%\Desktop

echo.
echo  ==========================================
echo   StationScheduler - Installing...
echo  ==========================================
echo.

:: ── Check Python ──────────────────────────────
set PYTHON=
python --version >nul 2>&1
if %errorlevel% equ 0 set PYTHON=python

if "!PYTHON!"=="" (
    py --version >nul 2>&1
    if %errorlevel% equ 0 set PYTHON=py
)

if "!PYTHON!"=="" (
    echo  [ERROR] Python is not installed.
    echo.
    echo  Please download and install Python from:
    echo  https://www.python.org/downloads/
    echo.
    echo  IMPORTANT: Check "Add Python to PATH" during install!
    echo.
    pause
    exit /b 1
)
echo  [OK] Python found

:: ── Check Git ─────────────────────────────────
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Git is not installed.
    echo.
    echo  Please download and install Git from:
    echo  https://git-scm.com/download/win
    echo.
    echo  Then run this installer again.
    echo.
    pause
    exit /b 1
)
echo  [OK] Git found

:: ── Clone or update repo ──────────────────────
echo.
if exist "%INSTALL_DIR%\.git" (
    echo  [INFO] App folder found - updating...
    cd /d "%INSTALL_DIR%"
    git pull
) else (
    echo  [INFO] Downloading app...
    git clone %REPO_URL% "%INSTALL_DIR%"
)

if %errorlevel% neq 0 (
    echo.
    echo  [ERROR] Download failed. Check your internet connection.
    pause
    exit /b 1
)
echo  [OK] App downloaded

:: ── Install Python dependencies ───────────────
echo.
echo  [INFO] Installing Python packages...
cd /d "%INSTALL_DIR%"
!PYTHON! -m pip install -r requirements.txt --quiet --disable-pip-version-check
echo  [OK] Packages installed

:: ── Create desktop launcher ───────────────────
echo.
echo  [INFO] Creating desktop shortcuts...

set LAUNCHER=%DESKTOP%\StationScheduler.bat
(
    echo @echo off
    echo cd /d "%INSTALL_DIR%"
    echo echo Starting StationScheduler...
    echo taskkill /F /FI "WINDOWTITLE eq streamlit*" >nul 2>&1
    echo start "" /MIN %PYTHON% -m streamlit run app.py --server.headless true --server.port 8501 --browser.gatherUsageStats false
    echo timeout /t 5 /nobreak >nul
    echo start http://localhost:8501
    echo exit
) > "%LAUNCHER%"

:: ── Create desktop updater ────────────────────
set UPDATER=%DESKTOP%\Update_StationScheduler.bat
(
    echo @echo off
    echo chcp 65001 >nul
    echo echo.
    echo echo  Updating StationScheduler...
    echo echo.
    echo cd /d "%INSTALL_DIR%"
    echo git pull
    echo echo.
    echo echo  Updating packages...
    echo %PYTHON% -m pip install -r requirements.txt --quiet --disable-pip-version-check
    echo echo.
    echo echo  ==========================================
    echo echo   Update complete^^!
    echo echo   Close this window and restart the app.
    echo echo  ==========================================
    echo echo.
    echo pause
) > "%UPDATER%"

:: ── Create shortcut with taxi icon (PowerShell) ────
set ICON=%INSTALL_DIR%\assets\taxi.ico
if not exist "%ICON%" set ICON=shell32.dll,13
powershell -Command ^
  "$ws = New-Object -ComObject WScript.Shell; ^
   $s = $ws.CreateShortcut('%DESKTOP%\StationScheduler.lnk'); ^
   $s.TargetPath = '%LAUNCHER%'; ^
   $s.WorkingDirectory = '%INSTALL_DIR%'; ^
   $s.Description = 'StationScheduler'; ^
   $s.IconLocation = '%ICON%'; ^
   $s.Save()" >nul 2>&1

:: ── Done ──────────────────────────────────────
echo.
echo  ==========================================
echo   Installation complete!
echo.
echo   On your Desktop:
echo   - StationScheduler      (launch app)
echo   - Update_StationScheduler  (get updates)
echo  ==========================================
echo.
set /p LAUNCH=Open the app now? (y/n):
if /i "!LAUNCH!"=="y" (
    call "%LAUNCHER%"
)
endlocal
