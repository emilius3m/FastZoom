# Giornale Word - Note Tecniche

## Stato Attuale

La generazione Word del Giornale usa una pipeline Python (`python-docx`) e non dipende da placeholder testuali fissi nel template.

Riferimento principale:

- `app/services/giornale_word_service.py`

## Come Funziona

1. Recupero dati giornale/cantiere/sito.
2. Composizione documento tramite API `python-docx`.
3. Formattazione sezioni (titolo, indice, dettagli, firme).
4. Output `.docx` in memoria e risposta download.

## Implicazioni

- La precedente convenzione `{{placeholder}}` non e la sorgente di verita operativa.
- Le modifiche al layout vanno implementate nel servizio di generazione.

## Personalizzazioni Consigliate

- Titoli/heading: metodi `_add_*` nel generatore.
- Tabelle e blocchi dati: aggiornare le sezioni dedicate.
- Stili: centralizzare dimensioni/font/colori nelle costanti della classe.

## Checklist Modifica Export

1. aggiornare metodo di rendering nel servizio
2. testare con giornale singolo e multiplo
3. verificare encoding caratteri speciali
4. aggiornare questa documentazione se cambia il flusso
