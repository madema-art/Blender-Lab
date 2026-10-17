@echo off
setlocal EnableExtensions
title Blender Lab Launcher

pushd "%~dp0"
if errorlevel 1 (
  echo [ERROR] Could not open the Blender-Lab folder:
  echo "%~dp0"
  goto :fail
)

where git >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Git was not found. Install Git for Windows, then double-click this file again.
  goto :fail
)
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Node.js was not found. Install Node.js 22 or newer, then double-click again.
  goto :fail
)
where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm was not found. Repair your Node.js installation, then double-click again.
  goto :fail
)

for /f "delims=" %%B in ('git branch --show-current 2^>nul') do set "CURRENT_BRANCH=%%B"
if not "%CURRENT_BRANCH%"=="main" (
  echo [ERROR] This folder is not on the main branch. Switch it to main, then retry.
  goto :fail
)
echo Updating Blender Lab from GitHub main...
git pull --ff-only origin main
if errorlevel 1 (
  echo [ERROR] Git could not update main. Check your internet connection and local changes, then retry.
  goto :fail
)

for /f "delims=" %%H in ('node -e "const fs=require('fs'),c=require('crypto');process.stdout.write(c.createHash('sha256').update(fs.readFileSync('package.json')).update(fs.readFileSync('package-lock.json')).digest('hex'))" 2^>nul') do set "DEPS_HASH=%%H"
if not defined DEPS_HASH (
  echo [ERROR] Could not calculate the dependency version. Check that package.json and package-lock.json are present.
  goto :fail
)
set "DEPS_MARKER=node_modules\.blender-lab-deps.sha256"
set "INSTALL_DEPS=1"
if exist "%DEPS_MARKER%" (
  set /p INSTALLED_HASH=<"%DEPS_MARKER%"
  if "%INSTALLED_HASH%"=="%DEPS_HASH%" set "INSTALL_DEPS=0"
)
if "%INSTALL_DEPS%"=="1" (
  echo Installing or updating Blender Lab dependencies...
  call npm ci
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Check your internet connection and try again.
    goto :fail
  )
  >"%DEPS_MARKER%" echo %DEPS_HASH%
)

if "%BLENDER_LAB_SMOKE_TEST%"=="1" goto :smoke_start

echo Checking for an existing Blender Lab server...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $m=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/models/manifest.json -TimeoutSec 2; if ($m.StatusCode -eq 200 -and $m.Content -match 'Alien Flying Saucer') { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto :open_browser
echo Starting Blender Lab...
start "Blender Lab Server" cmd.exe /k "npm run dev -- --host 127.0.0.1 --strictPort"
set "READY="
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/ -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 set "READY=1"
  if defined READY goto :open_browser
  timeout /t 1 /nobreak >nul
)
echo [ERROR] Blender Lab did not start at http://127.0.0.1:5173 within 60 seconds.
echo Check the separate Blender Lab Server window for details.
goto :fail

:open_browser
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined CHROME for /f "delims=" %%C in ('where chrome.exe 2^>nul') do if not defined CHROME set "CHROME=%%C"
if not defined CHROME (
  echo [ERROR] Google Chrome was not found. Install Chrome and double-click again.
  goto :fail
)
echo Blender Lab is ready. Opening it in Chrome...
start "" "%CHROME%" --new-window http://127.0.0.1:5173/
popd
exit /b 0

:smoke_start
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $m=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/models/manifest.json -TimeoutSec 2; $model=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/models/Alien-Flying-Saucer.glb -TimeoutSec 5; if ($m.StatusCode -eq 200 -and $m.Content -match 'Alien Flying Saucer' -and $model.StatusCode -eq 200 -and $model.RawContentLength -gt 100) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
if not errorlevel 1 goto :smoke_ok
start "Blender Lab Server" cmd.exe /k "npm run dev -- --host 127.0.0.1 --strictPort"
set "READY="
for /l %%I in (1,1,60) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $m=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/models/manifest.json -TimeoutSec 2; $model=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/models/Alien-Flying-Saucer.glb -TimeoutSec 5; if ($m.StatusCode -eq 200 -and $m.Content -match 'Alien Flying Saucer' -and $model.StatusCode -eq 200 -and $model.RawContentLength -gt 100) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
  if not errorlevel 1 set "READY=1"
  if defined READY goto :smoke_ok
  timeout /t 1 /nobreak >nul
)
echo [ERROR] Windows smoke test could not load the model manifest and saucer from the local server.
goto :fail

:smoke_ok
set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe" set "CHROME=%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
if not defined CHROME for /f "delims=" %%C in ('where chrome.exe 2^>nul') do if not defined CHROME set "CHROME=%%C"
if not defined CHROME (
  echo [ERROR] Google Chrome was not found. Install Chrome and double-click again.
  goto :fail
)
start "" "%CHROME%" --new-window http://127.0.0.1:5173/
echo Windows launcher smoke test passed: manifest, saucer, and Chrome launch verified.
popd
exit /b 0

:fail
echo.
echo Blender Lab could not be started. Fix the message above, then double-click Start-Blender-Lab.bat again.
echo This window will stay open so you can read the error.
pause
popd
exit /b 1
