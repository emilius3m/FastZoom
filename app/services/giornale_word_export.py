# app/services/giornale_word_export.py
"""
Export Giornale di Cantiere compilando direttamente template Word esistente
Mantiene layout IDENTICO al documento MiC originale
"""

from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from datetime import datetime, date
from typing import Optional, Dict, Any, List
import os
from pathlib import Path
import re


class GiornaleWordExporter:
    """
    Compila template Word esistente con dati Giornale di Cantiere
    NON crea nuovo template - modifica l'originale mantenendo il layout
    """

    def __init__(self, template_path: str):
        """
        Args:
            template_path: Path al file .docx template originale
        """
        self.template_path = template_path

    def export_giornali_list(self, export_data: Dict[str, Any], output_path: str) -> str:
        """
        Compila template Giornale con dati database

        Args:
            export_data: Dizionario con dati di export dal database
            output_path: Path dove salvare il documento compilato

        Returns:
            Path del file generato
        """
        # Carica template originale
        doc = Document(self.template_path)

        # COMPILA TUTTI I CAMPI DEL TEMPLATE
        # Cerca e sostituisci placeholder in tutto il documento

        # 1. INTESTAZIONE SITO
        site_info = export_data.get('site_info', {})
        self._replace_text(doc, '{{sito_nome}}', site_info.get('name', ''))
        self._replace_text(doc, '{{sito_codice}}', site_info.get('code', ''))
        self._replace_text(doc, '{{sito_localita}}', site_info.get('location', ''))

        # 2. METADATI EXPORT
        export_metadata = export_data.get('export_metadata', {})
        self._replace_text(doc, '{{data_export}}', self._format_date(export_metadata.get('export_date')))
        self._replace_text(doc, '{{utente_export}}', export_metadata.get('user', ''))
        self._replace_text(doc, '{{filtri_applicati}}', export_metadata.get('filters', ''))

        # 3. STATISTICHE
        stats = export_data.get('stats', {})
        self._replace_text(doc, '{{totale_giornali}}', str(stats.get('total_giornali', 0)))
        self._replace_text(doc, '{{giornali_validati}}', str(stats.get('validated_giornali', 0)))
        self._replace_text(doc, '{{giornali_pendenti}}', str(stats.get('pending_giornali', 0)))
        self._replace_text(doc, '{{operatori_attivi}}', str(stats.get('operatori_attivi', 0)))
        self._replace_text(doc, '{{percentuale_completamento}}', f"{stats.get('validation_percentage', 0)}%")

        # 4. COMPILA TABELLA GIORNALI
        self._compile_giornali_table(doc, export_data.get('giornali', []))

        # Salva documento compilato
        doc.save(output_path)
        return output_path

    def export_single_giornale(self, giornale_data: Dict[str, Any], output_path: str) -> str:
        """
        Compila template per singolo giornale di cantiere

        Args:
            giornale_data: Dizionario con dati del singolo giornale
            output_path: Path dove salvare il documento compilato

        Returns:
            Path del file generato
        """
        # Carica template originale
        doc = Document(self.template_path)

        # 1. INTESTAZIONE SITO
        site_info = giornale_data.get('site_info', {})
        self._replace_text(doc, '{{sito_nome}}', site_info.get('name', ''))
        self._replace_text(doc, '{{sito_codice}}', site_info.get('code', ''))
        self._replace_text(doc, '{{sito_localita}}', site_info.get('location', ''))

        # 2. INFORMAZIONI GIORNALE
        self._replace_text(doc, '{{giornale_data}}', self._format_date(giornale_data.get('data')))
        self._replace_text(doc, '{{giornale_ora_inizio}}', self._format_time(giornale_data.get('ora_inizio')))
        self._replace_text(doc, '{{giornale_ora_fine}}', self._format_time(giornale_data.get('ora_fine')))
        self._replace_text(doc, '{{giornale_compilatore}}', giornale_data.get('compilatore', ''))
        self._replace_text(doc, '{{giornale_responsabile}}', giornale_data.get('responsabile_scavo', ''))

        # 3. CONDIZIONI OPERATIVE
        self._replace_text(doc, '{{condizioni_meteo}}', giornale_data.get('condizioni_meteo', ''))
        self._replace_text(doc, '{{temperatura_min}}', str(giornale_data.get('temperatura_min', '')))
        self._replace_text(doc, '{{temperatura_max}}', str(giornale_data.get('temperatura_max', '')))
        self._replace_text(doc, '{{note_meteo}}', giornale_data.get('note_meteo', ''))

        # 4. DESCRIZIONE LAVORI
        self._replace_text(doc, '{{descrizione_lavori}}', giornale_data.get('descrizione_lavori', ''))
        self._replace_text(doc, '{{modalita_lavorazioni}}', giornale_data.get('modalita_lavorazioni', ''))
        self._replace_text(doc, '{{attrezzatura_utilizzata}}', giornale_data.get('attrezzatura_utilizzata', ''))
        self._replace_text(doc, '{{mezzi_utilizzati}}', giornale_data.get('mezzi_utilizzati', ''))

        # 5. DOCUMENTAZIONE ARCHEOLOGICA
        us_elaborate = giornale_data.get('us_elaborate', [])
        self._replace_text(doc, '{{us_elaborate}}', ', '.join(us_elaborate) if us_elaborate else '')
        
        usm_elaborate = giornale_data.get('usm_elaborate', [])
        self._replace_text(doc, '{{usm_elaborate}}', ', '.join(usm_elaborate) if usm_elaborate else '')
        
        usr_elaborate = giornale_data.get('usr_elaborate', [])
        self._replace_text(doc, '{{usr_elaborate}}', ', '.join(usr_elaborate) if usr_elaborate else '')
        
        self._replace_text(doc, '{{materiali_rinvenuti}}', giornale_data.get('materiali_rinvenuti', ''))
        self._replace_text(doc, '{{documentazione_prodotta}}', giornale_data.get('documentazione_prodotta', ''))

        # 6. OPERATORI PRESENTI
        operatori = giornale_data.get('operatori_presenti', [])
        self._compile_operatori_table(doc, operatori)

        # 7. SOPRALLUOGHI E DISPOSIZIONI
        self._replace_text(doc, '{{sopralluoghi}}', giornale_data.get('sopralluoghi', ''))
        self._replace_text(doc, '{{disposizioni_rup}}', giornale_data.get('disposizioni_rup', ''))
        self._replace_text(doc, '{{disposizioni_direttore}}', giornale_data.get('disposizioni_direttore', ''))

        # 8. EVENTI PARTICOLARI
        self._replace_text(doc, '{{contestazioni}}', giornale_data.get('contestazioni', ''))
        self._replace_text(doc, '{{sospensioni}}', giornale_data.get('sospensioni', ''))
        self._replace_text(doc, '{{incidenti}}', giornale_data.get('incidenti', ''))
        self._replace_text(doc, '{{forniture}}', giornale_data.get('forniture', ''))

        # 9. NOTE E PROBLEMATICHE
        self._replace_text(doc, '{{note_generali}}', giornale_data.get('note_generali', ''))
        self._replace_text(doc, '{{problematiche}}', giornale_data.get('problematiche', ''))

        # 10. VALIDAZIONE
        self._replace_text(doc, '{{stato_validazione}}', 'Validato' if giornale_data.get('validato') else 'In Attesa')
        self._replace_text(doc, '{{data_validazione}}', self._format_datetime(giornale_data.get('data_validazione')))

        # Salva documento compilato
        doc.save(output_path)
        return output_path

    # ===== METODI HELPER PER MANIPOLAZIONE DOCUMENTO =====

    def _replace_text(self, doc: Document, placeholder: str, value: str):
        """
        Sostituisce placeholder in TUTTO il documento (paragrafi, tabelle, header, footer)
        Mantiene formattazione originale
        """
        value = str(value) if value is not None else ''

        # Sostituisci in paragrafi
        for paragraph in doc.paragraphs:
            if placeholder in paragraph.text:
                self._replace_in_paragraph(paragraph, placeholder, value)

        # Sostituisci in tabelle
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        if placeholder in paragraph.text:
                            self._replace_in_paragraph(paragraph, placeholder, value)

        # Sostituisci in header/footer
        for section in doc.sections:
            # Header
            for paragraph in section.header.paragraphs:
                if placeholder in paragraph.text:
                    self._replace_in_paragraph(paragraph, placeholder, value)

            # Footer
            for paragraph in section.footer.paragraphs:
                if placeholder in paragraph.text:
                    self._replace_in_paragraph(paragraph, placeholder, value)

    def _replace_in_paragraph(self, paragraph, placeholder: str, value: str):
        """
        Sostituisce testo nel paragrafo mantenendo TUTTA la formattazione originale
        """
        # IMPORTANTE: Sostituisci nel testo completo mantenendo i run
        if placeholder not in paragraph.text:
            return

        # Trova tutti i run che contengono parte del placeholder
        full_text = ''
        run_texts = []

        for run in paragraph.runs:
            run_texts.append(run.text)
            full_text += run.text

        # Se il placeholder è presente, sostituisci
        if placeholder in full_text:
            new_text = full_text.replace(placeholder, value)

            # Cancella tutti i run esistenti tranne il primo
            for _ in range(len(paragraph.runs) - 1):
                paragraph._element.remove(paragraph.runs[-1]._element)

            # Aggiorna il primo run con il testo nuovo
            if paragraph.runs:
                paragraph.runs[0].text = new_text

    def _compile_giornali_table(self, doc: Document, giornali: List[Dict[str, Any]]):
        """
        Compila tabella con elenco giornali
        """
        # Trova tabella giornali nel documento (cerca placeholder specifico)
        for table in doc.tables:
            # Cerca prima cella con "GIORNALE" o simile
            if self._is_giornali_table(table):
                self._fill_giornali_table(table, giornali)
                break

    def _is_giornali_table(self, table) -> bool:
        """Identifica se è la tabella giornali"""
        # Controlla se prima riga contiene intestazioni giornali
        if len(table.rows) > 0:
            first_row_text = ' '.join([cell.text for cell in table.rows[0].cells])
            return 'DATA' in first_row_text.upper() or 'GIORNALE' in first_row_text.upper()
        return False

    def _fill_giornali_table(self, table, giornali: List[Dict[str, Any]]):
        """
        Compila celle tabella giornali con dati
        """
        # Se non ci sono giornali, aggiungi riga vuota
        if not giornali:
            if len(table.rows) > 1:
                # Mantieni solo header
                for _ in range(len(table.rows) - 1):
                    table._tbl.remove(table.rows[-1]._tr)
            return

        # Rimuovi righe esistenti tranne header
        while len(table.rows) > 1:
            table._tbl.remove(table.rows[-1]._tr)

        # Aggiungi riga per ogni giornale
        for giornale in giornali:
            row = table.add_row()
            
            # Data
            row.cells[0].text = self._format_date(giornale.get('data'))
            
            # Orari
            ora_inizio = self._format_time(giornale.get('ora_inizio'))
            ora_fine = self._format_time(giornale.get('ora_fine'))
            row.cells[1].text = f"{ora_inizio} - {ora_fine}" if ora_inizio and ora_fine else ""
            
            # Responsabile
            row.cells[2].text = giornale.get('responsabile_scavo', '')
            
            # Condizioni meteo
            row.cells[3].text = giornale.get('condizioni_meteo', '')
            
            # Stato
            row.cells[4].text = 'Validato' if giornale.get('validato') else 'In Attesa'
            
            # Note (troncate)
            note = giornale.get('note_generali', '')
            if note and len(note) > 50:
                note = note[:50] + "..."
            row.cells[5].text = note

    def _compile_operatori_table(self, doc: Document, operatori: List[Dict[str, Any]]):
        """
        Compila tabella con elenco operatori presenti
        """
        # Trova tabella operatori nel documento
        for table in doc.tables:
            # Cerca prima cella con "OPERATORI" o simile
            if self._is_operatori_table(table):
                self._fill_operatori_table(table, operatori)
                break

    def _is_operatori_table(self, table) -> bool:
        """Identifica se è la tabella operatori"""
        if len(table.rows) > 0:
            first_row_text = ' '.join([cell.text for cell in table.rows[0].cells])
            return 'OPERATORI' in first_row_text.upper() or 'NOME' in first_row_text.upper()
        return False

    def _fill_operatori_table(self, table, operatori: List[Dict[str, Any]]):
        """
        Compila celle tabella operatori con dati
        """
        # Se non ci sono operatori, aggiungi riga vuota
        if not operatori:
            if len(table.rows) > 1:
                # Mantieni solo header
                for _ in range(len(table.rows) - 1):
                    table._tbl.remove(table.rows[-1]._tr)
            return

        # Rimuovi righe esistenti tranne header
        while len(table.rows) > 1:
            table._tbl.remove(table.rows[-1]._tr)

        # Aggiungi riga per ogni operatore
        for operatore in operatori:
            row = table.add_row()
            
            # Nome completo
            row.cells[0].text = f"{operatore.get('nome', '')} {operatore.get('cognome', '')}"
            
            # Qualifica
            row.cells[1].text = operatore.get('qualifica', '')
            
            # Ruolo
            row.cells[2].text = operatore.get('ruolo', '')

    def _format_date(self, date_value) -> str:
        """Formatta data in formato italiano"""
        if not date_value:
            return ''

        if isinstance(date_value, str):
            try:
                date_obj = datetime.fromisoformat(date_value.replace('Z', '+00:00')).date()
                return date_obj.strftime('%d/%m/%Y')
            except:
                return date_value

        try:
            return date_value.strftime('%d/%m/%Y')
        except:
            return str(date_value)

    def _format_time(self, time_value) -> str:
        """Formatta ora"""
        if not time_value:
            return ''

        if isinstance(time_value, str):
            return time_value

        try:
            return time_value.strftime('%H:%M')
        except:
            return str(time_value)

    def _format_datetime(self, datetime_value) -> str:
        """Formatta data e ora"""
        if not datetime_value:
            return ''

        if isinstance(datetime_value, str):
            try:
                dt_obj = datetime.fromisoformat(datetime_value.replace('Z', '+00:00'))
                return dt_obj.strftime('%d/%m/%Y %H:%M')
            except:
                return datetime_value

        try:
            return datetime_value.strftime('%d/%m/%Y %H:%M')
        except:
            return str(datetime_value)


# ===== FUNZIONE HELPER PER FASTAPI =====

def create_giornale_word_from_template(export_data: Dict[str, Any], template_docx_path: str, output_dir: str) -> str:
    """
    Crea documento Word compilato da dati giornale

    Args:
        export_data: Dizionario con dati di export
        template_docx_path: Path al template .docx originale
        output_dir: Directory dove salvare output

    Returns:
        Path del file generato
    """
    exporter = GiornaleWordExporter(template_docx_path)

    # Genera nome file output
    site_info = export_data.get('site_info', {})
    site_name = site_info.get('name', 'Sito').replace(' ', '_').replace(',', '')
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if export_data.get('single_giornale'):
        # Export singolo giornale
        giornale_data = export_data.get('giornale', {})
        data_giornale = exporter._format_date(giornale_data.get('data'))
        filename = f"Giornale_{site_name}_{data_giornale}_{timestamp}.docx"
    else:
        # Export lista giornali
        filename = f"Giornali_{site_name}_{timestamp}.docx"
    
    output_path = os.path.join(output_dir, filename)

    # Compila template
    if export_data.get('single_giornale'):
        return exporter.export_single_giornale(export_data.get('giornale', {}), output_path)
    else:
        return exporter.export_giornali_list(export_data, output_path)