#!/bin/bash

echo "=== Inizializzazione Database FastZoom ==="
echo
echo "Questo script eseguirà lo script Python per l'inizializzazione del database."
echo

# Verifica se Python è installato
if ! command -v python3 &> /dev/null; then
    echo "Errore: Python3 non è installato o non è nel PATH del sistema."
    echo "Per favore, installa Python3 e aggiungilo al PATH del sistema."
    exit 1
fi

echo "Esecuzione dello script di inizializzazione..."
echo

# Esegui lo script Python
python3 initialize_database.py

if [ $? -eq 0 ]; then
    echo
    echo "=== Inizializzazione completata con successo! ==="
    echo
    echo "Ora puoi accedere al sistema con:"
    echo "  Email: user@user.com"
    echo "  Password: user@user.com"
    echo "  Username: user"
    echo
    echo "L'utente ha permessi di amministratore per entrambi i siti archeologici."
else
    echo
    echo "=== Si è verificato un errore durante l'inizializzazione ==="
    echo "Controlla i messaggi di errore sopra per maggiori dettagli."
fi

echo
read -p "Premi Invio per continuare..."