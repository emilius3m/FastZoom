#!/bin/bash
# Script di avvio per FastZoom in modalità produzione (Linux/Mac)
# Configura uvicorn con multi-worker per supportare 15-20 richieste concorrenti

set -e  # Esci immediatamente se un comando fallisce

echo "========================================"
echo "FastZoom Production Server Launcher"
echo "========================================"
echo

# Imposta la variabile d'ambiente per produzione
export FASTZOOM_ENV=production

# Verifica se Python è installato
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python3 non trovato. Installare Python prima di continuare."
    exit 1
fi

# Verifica se le dipendenze sono installate
echo "Verifica delle dipendenze..."
python3 -c "import uvicorn, fastapi, loguru" 2>/dev/null || {
    echo "ERROR: Dipendenze mancanti. Eseguire: pip3 install -r requirements.txt"
    exit 1
}

# Verifica se uvloop e httptools sono installati (dipendenze produzione)
echo "Verifica delle dipendenze di produzione..."
python3 -c "import uvloop, httptools" 2>/dev/null || {
    echo "WARNING: Dipendenze di produzione mancanti. Installazione in corso..."
    pip3 install uvloop httptools
}

# Avvia il server di produzione
echo "Avvio del server di produzione in modalità multi-worker..."
echo
echo "Target: Support 15-20 concurrent requests as per FASTZOOM_CONCURRENCY_ANALYSIS_REPORT.md"
echo
echo "Per fermare il server, premere CTRL+C"
echo

# Esegui lo script di produzione
python3 start_production.py

echo
echo "Server fermato."