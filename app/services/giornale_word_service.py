# app/services/giornale_word_service.py
"""
Servizio per generazione Word Document Giornale di Cantiere conforme al formato standard italiano
Basato sulla stessa struttura del servizio PDF ma genera documenti .docx editabili
"""

import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from loguru import logger

# Try to import docx library
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
    from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
    from docx.oxml.shared import OxmlElement, qn
    DOCX_AVAILABLE = True
except ImportError:
    logger.warning("python-docx library not available. Install with: pip install python-docx")
    DOCX_AVAILABLE = False


class GiornaleWordGenerator:
    """Generatore Word per Giornale di Cantiere secondo formato standard italiano."""
    
    def __init__(self):
        if not DOCX_AVAILABLE:
            raise ImportError("python-docx library is required for Word export. Install with: pip install python-docx")
    
    def generate_giornale_word(self, 
                                giornali: List[Dict[str, Any]], 
                                cantiere_info: Dict[str, Any], 
                                site_info: Dict[str, Any]) -> bytes:
        """
        Genera documento Word del Giornale di Cantiere secondo formato standard.
        
        Args:
            giornali: Lista di giornali da includere nel documento
            cantiere_info: Informazioni sul cantiere
            site_info: Informazioni sul sito archeologico
            
        Returns:
            bytes: Contenuto del documento Word generato
        """
        try:
            # Crea nuovo documento Word
            doc = Document()
            
            # Imposta margini del documento
            sections = doc.sections
            for section in sections:
                section.top_margin = Inches(1.18)  # 3 cm
                section.bottom_margin = Inches(1.18)  # 3 cm
                section.left_margin = Inches(0.79)    # 2 cm
                section.right_margin = Inches(0.79)   # 2 cm
            
            # Prima pagina: Header e informazioni generali
            self._add_first_page_header(doc, cantiere_info, site_info)
            self._add_giornale_number(doc, 1)
            doc.add_page_break()
            
            # Pagine con i giornali
            for i, giornale in enumerate(giornali):
                self._add_giornale_entry(doc, giornale, i + 2)
                
                # Aggiungi page break tranne che per l'ultimo
                if i < len(giornali) - 1:
                    doc.add_page_break()
            
            # Salva documento in buffer
            buffer = io.BytesIO()
            doc.save(buffer)
            buffer.seek(0)
            
            word_content = buffer.getvalue()
            buffer.close()
            
            logger.info(f"Generated Giornale Word for cantiere {cantiere_info.get('nome')}: {len(word_content)} bytes")
            
            return word_content
            
        except Exception as e:
            logger.error(f"Error generating Giornale Word: {e}")
            raise
    
    def _add_first_page_header(self, doc, cantiere_info: Dict[str, Any], site_info: Dict[str, Any]):
        """Aggiunge intestazione della prima pagina."""
        
        # Header information
        header_data = [
            ("OGGETTO:", cantiere_info.get('oggetto_appalto', '')),
            ("COMMITTENTE:", cantiere_info.get('committente', site_info.get('name', ''))),
            ("IMPRESA:", cantiere_info.get('impresa_esecutrice', '')),
        ]
        
        # Aggiungi header con tabella
        table = doc.add_table(rows=0, cols=2)
        table.autofit = True
        
        for label, value in header_data:
            row = table.add_row()
            row.cells[0].text = label
            row.cells[1].text = value or ""
            
            # Stile per la cella dell'etichetta
            label_paragraph = row.cells[0].paragraphs[0]
            label_run = label_paragraph.runs[0]
            label_run.font.bold = True
            label_run.font.size = Pt(10)
            
            # Stile per la cella del valore
            value_paragraph = row.cells[1].paragraphs[0]
            if value:
                value_run = value_paragraph.runs[0]
                value_run.font.size = Pt(10)
        
        # Spaziatura
        for _ in range(5):
            doc.add_paragraph()
        
        # Titolo principale
        title = doc.add_paragraph("GIORNALE DEI LAVORI")
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title_run = title.runs[0]
        title_run.font.size = Pt(16)
        title_run.font.bold = True
        
        # Numero pagina
        page_num = doc.add_paragraph("pag. 1")
        page_num.alignment = WD_ALIGN_PARAGRAPH.CENTER
        page_run = page_num.runs[0]
        page_run.font.size = Pt(8)
        page_run.font.italic = True
        
        doc.add_paragraph()
        
        # Descrizione cantiere
        descrizione = cantiere_info.get('descrizione', cantiere_info.get('nome', ''))
        if descrizione:
            desc_paragraph = doc.add_paragraph(descrizione)
            desc_run = desc_paragraph.runs[0]
            desc_run.font.size = Pt(10)
        
        # Informazioni sito
        if site_info.get('name'):
            site_paragraph = doc.add_paragraph(site_info['name'])
            site_run = site_paragraph.runs[0]
            site_run.font.size = Pt(10)
        
        doc.add_paragraph()
        
        # Informazioni responsabili
        responsabili_data = [
            ("IL DIRETTORE DEI LAVORI", cantiere_info.get('direttore_lavori', '')),
            ("IL RESPONSABILE DEL PROCEDIMENTO", cantiere_info.get('responsabile_procedimento', '')),
            ("L'IMPRESA", cantiere_info.get('impresa_esecutrice', '')),
        ]
        
        responsabili_table = doc.add_table(rows=0, cols=2)
        responsabili_table.autofit = True
        
        for label, value in responsabili_data:
            row = responsabili_table.add_row()
            row.cells[0].text = label
            row.cells[1].text = value or ""
            
            # Stile per la cella dell'etichetta
            label_paragraph = row.cells[0].paragraphs[0]
            label_run = label_paragraph.runs[0]
            label_run.font.bold = True
            label_run.font.size = Pt(10)
            
            # Stile per la cella del valore
            if value:
                value_paragraph = row.cells[1].paragraphs[0]
                value_run = value_paragraph.runs[0]
                value_run.font.size = Pt(10)
        
        doc.add_paragraph()
    
    def _add_giornale_number(self, doc, giornale_number: int):
        """Aggiunge numero del giornale."""
        num_paragraph = doc.add_paragraph(f"Giornale dei Lavori n. {giornale_number}")
        num_run = num_paragraph.runs[0]
        num_run.font.bold = True
        num_run.font.size = Pt(11)
        doc.add_paragraph()
    
    def _add_giornale_entry(self, doc, giornale: Dict[str, Any], page_number: int):
        """Aggiunge una voce di giornale completo."""
        
        # Numero pagina
        page_paragraph = doc.add_paragraph(f"Pag.{page_number}")
        page_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        page_run = page_paragraph.runs[0]
        page_run.font.size = Pt(8)
        page_run.font.italic = True
        doc.add_paragraph()
        
        # Tabella per DATA e METEO
        data_giornale = self._format_date(giornale.get('data'))
        meteo = self._format_meteo(giornale.get('condizioni_meteo'), giornale.get('temperatura'))
        
        meteo_table = doc.add_table(rows=2, cols=3)
        meteo_table.autofit = True
        
        # Intestazione tabella
        header_row = meteo_table.rows[0]
        header_row.cells[0].text = "DATA"
        header_row.cells[1].text = "e"
        header_row.cells[2].text = "METEO"
        
        # Dati tabella
        data_row = meteo_table.rows[1]
        data_row.cells[0].text = data_giornale
        data_row.cells[1].text = ""
        data_row.cells[2].text = meteo
        
        # Formatta tabella
        for i, row in enumerate(meteo_table.rows):
            for j, cell in enumerate(row.cells):
                paragraph = cell.paragraphs[0]
                run = paragraph.runs[0]
                run.font.size = Pt(9)
                
                if i == 0:  # Header row
                    run.font.bold = True
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        doc.add_paragraph()
        
        # Titolo sezione annotazioni
        annotazioni_title = doc.add_paragraph("ANNOTAZIONI GENERALI E SPECIALI")
        annotazioni_title_run = annotazioni_title.runs[0]
        annotazioni_title_run.font.bold = True
        annotazioni_title_run.font.size = Pt(9)
        
        doc.add_paragraph("SULL'ANDAMENTO E MODO DI ESECUZIONE DEI LAVORI,")
        doc.add_paragraph("AVVENIMENTI STRAORDINARI E TEMPO IMPIEGATO")
        doc.add_paragraph()
        
        # Descrizione lavori
        descrizione = giornale.get('descrizione_lavori', '')
        if descrizione:
            desc_paragraph = doc.add_paragraph(descrizione)
            desc_run = desc_paragraph.runs[0]
            desc_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Altre informazioni
        modalita = giornale.get('modalita_lavorazioni', '')
        if modalita:
            mod_paragraph = doc.add_paragraph(modalita)
            mod_run = mod_paragraph.runs[0]
            mod_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Materiali rinvenuti
        materiali = giornale.get('materiali_rinvenuti', '')
        if materiali:
            mat_paragraph = doc.add_paragraph(f"Materiali rinvenuti: {materiali}")
            mat_run = mat_paragraph.runs[0]
            mat_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Documentazione prodotta
        documentazione = giornale.get('documentazione_prodotta', '')
        if documentazione:
            doc_paragraph = doc.add_paragraph(f"Documentazione prodotta: {documentazione}")
            doc_run = doc_paragraph.runs[0]
            doc_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Operatori presenti
        operatori = giornale.get('operatori_presenti', [])
        if operatori:
            self._add_operatori_section(doc, operatori)
        
        # Note e problematiche
        note = giornale.get('note_generali', '')
        if note:
            note_paragraph = doc.add_paragraph(f"Note: {note}")
            note_run = note_paragraph.runs[0]
            note_run.font.size = Pt(9)
            doc.add_paragraph()
        
        problematiche = giornale.get('problematiche', '')
        if problematiche:
            prob_paragraph = doc.add_paragraph(f"Problematiche: {problematiche}")
            prob_run = prob_paragraph.runs[0]
            prob_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Eventi speciali
        self._add_eventi_speciali(doc, giornale)
        
        # Firme
        self._add_firme_section(doc)
    
    def _add_operatori_section(self, doc, operatori: List[Dict[str, Any]]):
        """Aggiunge sezione operatori."""
        
        operatori_title = doc.add_paragraph("OPERAI e MEZZI:")
        title_run = operatori_title.runs[0]
        title_run.font.bold = True
        title_run.font.size = Pt(9)
        
        # Formatta operatori in formato richiesto
        operatori_text = []
        for operatore in operatori:
            nome_completo = f"{operatore.get('nome', '')} {operatore.get('cognome', '')}".strip()
            qualifica = operatore.get('qualifica', operatore.get('ruolo', 'Operatore'))
            ore = operatore.get('ore_lavorate', 1)
            
            operatori_text.append(f"{nome_completo}_{qualifica} = {ore}")
        
        # Aggiungi mezzi utilizzati se presenti
        mezzi = self._get_mezzi_from_attrezzatura([])
        for mezzo in mezzi:
            operatori_text.append(f"{mezzo} = 1")
        
        # Unisci operatori con separatori
        full_text = ";  ".join(operatori_text)
        
        op_paragraph = doc.add_paragraph(full_text)
        op_run = op_paragraph.runs[0]
        op_run.font.size = Pt(8)
        doc.add_paragraph()
    
    def _get_mezzi_from_attrezzatura(self, story) -> List[str]:
        """Estrae mezzi meccanici dalle attrezzature."""
        mezzi = []
        # Questa funzione potrebbe essere implementata per estrarre mezzi specifici
        # dalle attrezzature utilizzate nel giornale
        return mezzi
    
    def _add_eventi_speciali(self, doc, giornale: Dict[str, Any]):
        """Aggiunge sezione eventi speciali e foto."""
        
        # Sopralluoghi
        sopralluoghi = giornale.get('sopralluoghi', '')
        if sopralluoghi:
            sopro_paragraph = doc.add_paragraph(f"Sopralluoghi: {sopralluoghi}")
            sopro_run = sopro_paragraph.runs[0]
            sopro_run.font.size = Pt(9)
            doc.add_paragraph()
        
        # Disposizioni
        disposizioni = []
        if giornale.get('disposizioni_rup'):
            disposizioni.append(f"RUP: {giornale['disposizioni_rup']}")
        if giornale.get('disposizioni_direttore'):
            disposizioni.append(f"DL: {giornale['disposizioni_direttore']}")
        
        if disposizioni:
            disp_title = doc.add_paragraph("Disposizioni:")
            disp_title_run = disp_title.runs[0]
            disp_title_run.font.bold = True
            disp_title_run.font.size = Pt(9)
            
            for disposizione in disposizioni:
                disp_paragraph = doc.add_paragraph(f"- {disposizione}")
                disp_run = disp_paragraph.runs[0]
                disp_run.font.size = Pt(9)
            doc.add_paragraph()
    
    def _add_firme_section(self, doc):
        """Aggiunge sezione firme."""
        
        doc.add_paragraph()
        
        # Linea separatoria (usiamo una tabella con bordo)
        separator_table = doc.add_table(rows=1, cols=1)
        separator_cell = separator_table.cell(0, 0)
        separator_cell.text = ""
        
        # Aggiungi bordo alla tabella per simulare linea
        for border in ['BOTTOM']:
            setattr(separator_cell._element.xpath('.//w:tcBorders')[0],
                       f'{border}',
                       self._create_border_element('single', '000000', 6))
        
        doc.add_paragraph()
        
        # Tabella firme
        firme_data = [
            ["COMMITTENTE:", ""],
            ["GIORNALE DEI LAVORI N. 1", ""],
            ["", ""],
            ["L'IMPRESA", "IL DIRETTORE DEI LAVORI"]
        ]
        
        firme_table = doc.add_table(rows=0, cols=2)
        firme_table.autofit = True
        
        for label, value in firme_data:
            row = firme_table.add_row()
            row.cells[0].text = label
            row.cells[1].text = value or ""
            
            # Formattazione celle
            for i, cell in enumerate(row.cells):
                paragraph = cell.paragraphs[0]
                run = paragraph.runs[0]
                run.font.size = Pt(9)
                
                if i == 0:  # Colonna sinistra
                    if "COMMITTENTE" in label:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
                    elif "IMPRESA" in label:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run.font.bold = True
                else:  # Colonna destra
                    if "DIRETTORE" in value:
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        run.font.bold = True
        
        doc.add_paragraph()
    
    def _create_border_element(self, border_type, color_hex, size_pt):
        """Crea elemento bordo per tabella."""
        border = OxmlElement(f'w:bd')
        border.set(qn('w:val'), border_type)
        border.set(qn('w:color'), color_hex)
        border.set(qn('w:sz'), str(size_pt))
        return border
    
    def _format_date(self, date_value) -> str:
        """Formatta data in formato italiano."""
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
    
    def _format_meteo(self, condizioni: str, temperatura: Any) -> str:
        """Formatta informazioni meteo."""
        meteo_parts = []
        
        if condizioni:
            # Converte le condizioni meteo in maiuscolo
            meteo_parts.append(condizioni.upper())
        
        if temperatura:
            meteo_parts.append(f"{temperatura} °C")
        
        return ' '.join(meteo_parts) if meteo_parts else ''

# Istanza globale del generatore
if DOCX_AVAILABLE:
    giornale_word_generator = GiornaleWordGenerator()
    
    def generate_giornale_word_quick(giornali: List[Dict[str, Any]], 
                                     cantiere_info: Dict[str, Any], 
                                     site_info: Dict[str, Any]) -> bytes:
        """Funzione di utilità per generazione rapida Word Giornale."""
        return giornale_word_generator.generate_giornale_word(giornali, cantiere_info, site_info)
else:
    def generate_giornale_word_quick(giornali: List[Dict[str, Any]], 
                                     cantiere_info: Dict[str, Any], 
                                     site_info: Dict[str, Any]) -> bytes:
        """Funzione di stub quando python-docx non è disponibile."""
        raise ImportError("python-docx library is required for Word export. Install with: pip install python-docx")