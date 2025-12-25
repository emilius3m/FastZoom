# run_extraction.py

import asyncio
import os
import json
import sys
from loguru import logger

# Aggiunge la directory principale al path di Python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.paddle_ocr_service import get_paddle_ocr_service, is_paddle_ocr_available

# --- Configurazione ---
PDF_FILENAME = "us11.pdf"
SITE_ID = "PARCO_SEPINO"


def print_extracted_data(us_data: dict, debug_info: dict):
    """Formatta e stampa i dati estratti e le informazioni di debug."""

    print("\n" + "=" * 50)
    print("✅ ESTRAZIONE COMPLETATA CON SUCCESSO!")
    print("=" * 50)

    # Stampa i dati principali della scheda US
    print(f"\n📋 Scheda US Estratta: {us_data.get('us_code', 'N/A')}")
    print("-" * 50)

    # Stampa i campi principali in modo ordinato
    campi_principali = [
        "ente_responsabile", "ufficio_mic", "anno", "identificativo_rif", "localita",
        "area_struttura", "saggio", "ambiente_unita_funzione", "posizione", "definizione",
        "tipo", "formazione", "quote", "stato_conservazione", "descrizione", "interpretazione",
        "datazione", "periodo", "fase", "responsabile_scientifico", "data_rilevamento"
    ]

    for campo in campi_principali:
        if us_data.get(campo):
            # Formatta il nome del campo in modo più leggibile
            nome_campo = campo.replace('_', ' ').title()
            print(f"🔹 {nome_campo:.<35} {us_data.get(campo)}")

    # Stampa le relazioni stratigrafiche
    print("\n🔗 Relazioni Stratigrafiche (Harris Matrix):")
    relazioni = {k: v for k, v in us_data.items() if k.startswith('seq_') or k in ['posteriore_a', 'anteriore_a']}
    if relazioni:
        for rel, val in relazioni.items():
            if val:
                print(f"   - {rel.replace('seq_', '').replace('_', ' ').title()}: {val}")
    else:
        print("   - Nessuna relazione rilevata.")

    # Stampa le informazioni di debug
    print("\n" + "=" * 50)
    print("🛠️  INFORMAZIONI DI DEBUG")
    print("=" * 50)
    print(f"Origine celle rilevate: {debug_info.get('cell_source', 'N/A')}")
    print(f"Metodo di rilevamento tabelle: {debug_info.get('table_detection_method', 'N/A')}")
    print(f"Numero di pagine processate: {len(debug_info.get('pages', []))}")
    print(f"Totale blocchi di testo OCR: {debug_info.get('total_words', 0)}")
    print(f"Numero di celle tabella rilevate: {len(debug_info.get('pp_structure_cells', []))}")


async def main():
    """Funzione principale che esegue l'intero processo di estrazione."""

    # 1. Controlla la disponibilità delle librerie
    if not is_paddle_ocr_available():
        print("ERRORE: PaddleOCR o le sue dipendenze non sono disponibili.")
        print("Assicurati di aver installato: pip install paddleocr pymupdf pdfplumber loguru")
        return

    # 2. Controlla che il file PDF esista
    if not os.path.exists(PDF_FILENAME):
        print(f"ERRORE: File PDF non trovato: {PDF_FILENAME}")
        print("Assicurati che il file 'us11.pdf' sia nella stessa cartella dello script.")
        return

    print(f"🚀 Avvio elaborazione del file: {PDF_FILENAME}")

    try:
        # 3. Ottieni l'istanza del servizio OCR
        ocr_service = get_paddle_ocr_service()

        # 4. Leggi il contenuto del PDF
        with open(PDF_FILENAME, "rb") as f:
            pdf_bytes = f.read()

        # 5. Esegui l'estrazione dei dati
        result = await ocr_service.extract_from_pdf_combined(
            pdf_bytes=pdf_bytes,
            filename=PDF_FILENAME,
            site_id=SITE_ID,
            include_debug=True
        )

        us_data = result.get('us_data')
        debug_info = result.get('debug', {})

        # 6. Mostra i risultati
        if us_data:
            print_extracted_data(us_data, debug_info)

            # Salva i risultati in un file JSON
            with open(f"{PDF_FILENAME}_results.json", "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n💾 Risultati salvati in: {PDF_FILENAME}_results.json")
        else:
            print("\n" + "=" * 50)
            print("❌ ESTRAZIONE FALLITA")
            print("=" * 50)
            print("Impossibile estrarre i dati della scheda US.")
            print("Il PDF potrebbe essere illeggibile o non conforme al modello atteso.")

    except Exception as e:
        logger.exception("Si è verificato un errore critico durante l'elaborazione.")
        print(f"\nERRORE CRITICO: {e}")


if __name__ == "__main__":
    # Configura il logger
    logger.remove()
    logger.add(sys.stderr, level="INFO")
    logger.add("extraction.log", level="DEBUG", rotation="10 MB")

    # Esegui la funzione principale asincrona
    asyncio.run(main())