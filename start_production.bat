@echo off
REM Script di avvio per FastZoom in modalità produzione (Windows)
REM Configura uvicorn con multi-worker per supportare 15-20 richieste concorrenti

echo ========================================
echo FastZoom Production Server Launcher
echo ========================================
echo.

REM Imposta la variabile d'ambiente per produzione
set FASTZOOM_ENV=production

REM Verifica se Python è installato
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python non trovato. Installare Python prima di continuare.
    pause
    exit /b 1
)

REM Verifica se le dipendenze sono installate
echo Verifica delle dipendenze...
python -c "import uvicorn, fastapi, loguru" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Dipendenze mancanti. Eseguire: pip install -r requirements.txt
    pause
    exit /b 1
)

REM Avvia il server di produzione
echo Avvio del server di produzione in modalità multi-worker...
echo.
echo Target: Support 15-20 concurrent requests as per FASTZOOM_CONCURRENCY_ANALYSIS_REPORT.md
echo.
echo Per fermare il server, premere CTRL+C
echo.

python start_production.py

REM Se il server si ferma, attendi l'input dell'utente
echo.
echo Server fermato. Premere un tasto per chiudere...
pause >nul