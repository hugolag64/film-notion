@echo off
setlocal
cd /d "%~dp0"

set "PORT=8090"

if not exist ".venv\Scripts\python.exe" (
    echo [ERREUR] Environnement Python introuvable : .venv\Scripts\python.exe
    pause
    exit /b 1
)

echo Arret du serveur existant sur le port %PORT%...
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
    taskkill /PID %%P /F >nul 2>&1
)

if exist "proto-ui\package.json" (
    echo Compilation du frontend React...
    call npm --prefix proto-ui run build
    if errorlevel 1 (
        echo [ERREUR] La compilation du frontend a echoue.
        pause
        exit /b 1
    )
)

echo Demarrage de Backstage sur http://localhost:%PORT%
start "Backstage server" /D "%CD%" cmd /k "set PORT=%PORT%&& .venv\Scripts\python.exe main.py"
timeout /t 2 /nobreak >nul
start "" "http://localhost:%PORT%"

endlocal
