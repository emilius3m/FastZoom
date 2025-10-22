@echo off
echo === Inizializzazione Database FastZoom ===
echo.
echo Questo script eseguirà lo script Python per l'inizializzazione del database.
echo.

REM Verifica se Python è installato
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Errore: Python non è installato o non è nel PATH del sistema.
    echo Per favore, installa Python e aggiungilo al PATH del sistema.
    pause
    exit /b 1
)

echo Esecuzione dello script di inizializzazione...
echo.

REM Esegui lo script Python
python initialize_database.py

if %errorlevel% equ 0 (
    echo.
    echo === Inizializzazione completata con successo! ===
    echo.
    echo Ora puoi accedere al sistema con:
    echo   Email: user@user.com
    echo   Password: user@user.com
    echo   Username: user
    echo.
    echo L'utente ha permessi di amministratore per entrambi i siti archeologici.
) else (
    echo.
    echo === Si è verificato un errore durante l'inizializzazione ===
    echo Controlla i messaggi di errore sopra per maggiori dettagli.
)

echo.
pause