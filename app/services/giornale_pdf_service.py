# app/services/giornale_pdf_service.py
"""
Servizio per generazione PDF Giornale di Cantiere conforme al formato standard italiano
Basato sull'esempio fornito: "Settimana 10 giornale lavori.pdf"
"""

import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import black, blue, grey
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from loguru import logger


class GiornalePDFGenerator:
    """Generatore PDF per Giornale di Cantiere secondo formato standard italiano."""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
        self.page_count = 0
    
    def _setup_custom_styles(self):
        """Configura stili personalizzati per PDF Giornale di Cantiere."""
        
        # Stile titolo principale
        self.styles.add(ParagraphStyle(
            name='GiornaleTitle',
            parent=self.styles['Title'],
            fontSize=16,
            spaceAfter=12,
            textColor=black,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Stile per header informazioni
        self.styles.add(ParagraphStyle(
            name='HeaderInfo',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=3,
            fontName='Helvetica',
            alignment=TA_LEFT
        ))
        
        # Stile per dati giornale
        self.styles.add(ParagraphStyle(
            name='GiornaleData',
            parent=self.styles['Normal'],
            fontSize=11,
            spaceAfter=2,
            fontName='Helvetica-Bold'
        ))
        
        # Stile per annotazioni generali
        self.styles.add(ParagraphStyle(
            name='Annotazioni',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=6,
            fontName='Helvetica',
            alignment=TA_JUSTIFY,
            leading=12
        ))
        
        # Stile per meteo
        self.styles.add(ParagraphStyle(
            name='MeteoInfo',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=3,
            fontName='Helvetica-Bold',
            alignment=TA_LEFT
        ))
        
        # Stile per operatori
        self.styles.add(ParagraphStyle(
            name='OperatoriInfo',
            parent=self.styles['Normal'],
            fontSize=8,
            spaceAfter=2,
            fontName='Helvetica',
            alignment=TA_LEFT
        ))
        
        # Stile per firme
        self.styles.add(ParagraphStyle(
            name='FirmeStyle',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=6,
            fontName='Helvetica',
            alignment=TA_CENTER
        ))
        
        # Stile per pagina
        self.styles.add(ParagraphStyle(
            name='PageNumber',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=grey,
            fontName='Helvetica-Oblique',
            alignment=TA_CENTER
        ))
    
    def generate_giornale_pdf(self, 
                              giornali: List[Dict[str, Any]], 
                              cantiere_info: Dict[str, Any], 
                              site_info: Dict[str, Any]) -> bytes:
        """
        Genera PDF del Giornale di Cantiere secondo formato standard.
        
        Args:
            giornali: Lista di giornali da includere nel PDF
            cantiere_info: Informazioni sul cantiere
            site_info: Informazioni sul sito archeologico
            
        Returns:
            bytes: Contenuto PDF generato
        """
        try:
            # Buffer per PDF
            buffer = io.BytesIO()
            
            # Configurazione documento
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=1.5*cm,
                bottomMargin=1.5*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
                title=f"Giornale dei Lavori - {cantiere_info.get('nome', 'Cantiere')}"
            )
            
            # Contenuto PDF
            story = []
            
            # Prima pagina: Header e informazioni generali
            self._add_first_page_header(story, cantiere_info, site_info)
            self._add_giornale_number(story, 1)
            self._add_page_break(story)
            
            # Pagine con i giornali
            for i, giornale in enumerate(giornali):
                self.page_count = i + 2  # Inizia da pagina 2 (prima pagina è l'header)
                self._add_giornale_entry(story, giornale, self.page_count, cantiere_info)
                
                # Aggiungi page break tranne che per l'ultimo
                if i < len(giornali) - 1:
                    self._add_page_break(story)
            
            # Genera PDF
            doc.build(story)
            
            # Ritorna contenuto
            buffer.seek(0)
            pdf_content = buffer.getvalue()
            buffer.close()
            
            logger.info(f"Generated Giornale PDF for cantiere {cantiere_info.get('nome')}: {len(pdf_content)} bytes")
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"Error generating Giornale PDF: {e}")
            raise
    
    def _add_first_page_header(self, story, cantiere_info: Dict[str, Any], site_info: Dict[str, Any]):
        """Aggiunge intestazione della prima pagina."""
        
        # Header information
        header_data = [
            ["OGGETTO:", cantiere_info.get('oggetto_appalto', '')],
            ["COMMITTENTE:", cantiere_info.get('committente', site_info.get('name', ''))],
            ["IMPRESA:", cantiere_info.get('impresa_esecutrice', '')],
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
            ["", ""],  # Spazio vuoto
        ]
        
        header_table = Table(header_data, colWidths=[4*cm, 14*cm])
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 2), (0, 2), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 12))
        
        # Titolo principale
        story.append(Paragraph("GIORNALE DEI LAVORI", self.styles['GiornaleTitle']))
        story.append(Paragraph("pag. 1", self.styles['PageNumber']))
        story.append(Spacer(1, 6))
        
        # Descrizione cantiere
        descrizione = cantiere_info.get('descrizione', cantiere_info.get('nome', ''))
        if descrizione:
            story.append(Paragraph(descrizione, self.styles['HeaderInfo']))
        
        # Informazioni sito
        if site_info.get('name'):
            story.append(Paragraph(site_info['name'], self.styles['HeaderInfo']))
        
        story.append(Spacer(1, 12))
        
        # Informazioni responsabili
        responsabili_data = [
            ["IL DIRETTORE DEI LAVORI", cantiere_info.get('direttore_lavori', '')],
            ["IL RESPONSABILE DEL PROCEDIMENTO", cantiere_info.get('responsabile_procedimento', '')],
            ["L'IMPRESA", cantiere_info.get('impresa_esecutrice', '')],
        ]
        
        responsabili_table = Table(responsabili_data, colWidths=[8*cm, 10*cm])
        responsabili_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        story.append(responsabili_table)
        story.append(Spacer(1, 12))
    
    def _add_giornale_number(self, story, giornale_number: int):
        """Aggiunge numero del giornale."""
        story.append(Paragraph(f"Giornale dei Lavori n. {giornale_number}", self.styles['GiornaleData']))
        story.append(Spacer(1, 12))
    
    def _add_page_break(self, story):
        """Aggiunge page break."""
        story.append(PageBreak())
    
    def _add_giornale_entry(self, story, giornale: Dict[str, Any], page_number: int, cantiere_info: Dict[str, Any]):
        """Aggiunge una voce di giornale completo."""
        
        # Numero pagina
        story.append(Paragraph(f"Pag.{page_number}", self.styles['PageNumber']))
        story.append(Spacer(1, 8))
        
        # Tabella per DATA e METEO
        data_giornale = self._format_date(giornale.get('data'))
        meteo = self._format_meteo(giornale.get('condizioni_meteo'), giornale.get('temperatura'))
        
        header_table_data = [
            ["DATA", "e", "METEO"],
            [data_giornale, "", meteo]
        ]
        
        header_table = Table(header_table_data, colWidths=[3*cm, 1*cm, 4*cm])
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 1), (2, 1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, 1), 9),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (0, 1), 'CENTER'),
            ('ALIGN', (2, 1), (2, 1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 8))
        
        # Titolo sezione annotazioni
        story.append(Paragraph("ANNOTAZIONI GENERALI E SPECIALI", self.styles['MeteoInfo']))
        story.append(Paragraph("SULL'ANDAMENTO E MODO DI ESECUZIONE DEI LAVORI,", self.styles['MeteoInfo']))
        story.append(Paragraph("AVVENIMENTI STRAORDINARI E TEMPO IMPIEGATO", self.styles['MeteoInfo']))
        story.append(Spacer(1, 8))
        
        # Descrizione lavori
        descrizione = giornale.get('descrizione_lavori', '')
        if descrizione:
            story.append(Paragraph(descrizione, self.styles['Annotazioni']))
            story.append(Spacer(1, 8))
        
        # Altre informazioni
        modalita = giornale.get('modalita_lavorazioni', '')
        if modalita:
            story.append(Paragraph(modalita, self.styles['Annotazioni']))
            story.append(Spacer(1, 8))
        
        # Materiali rinvenuti
        materiali = giornale.get('materiali_rinvenuti', '')
        if materiali:
            story.append(Paragraph(f"Materiali rinvenuti: {materiali}", self.styles['Annotazioni']))
            story.append(Spacer(1, 8))
        
        # Documentazione prodotta
        documentazione = giornale.get('documentazione_prodotta', '')
        if documentazione:
            story.append(Paragraph(f"Documentazione prodotta: {documentazione}", self.styles['Annotazioni']))
            story.append(Spacer(1, 8))
        
        # Operatori presenti
        operatori = giornale.get('operatori_presenti', [])
        if operatori:
            self._add_operatori_section(story, operatori)
        
        # Note e problematiche
        note = giornale.get('note_generali', '')
        if note:
            story.append(Paragraph(f"Note: {note}", self.styles['Annotazioni']))
            story.append(Spacer(1, 6))
        
        problematiche = giornale.get('problematiche', '')
        if problematiche:
            story.append(Paragraph(f"Problematiche: {problematiche}", self.styles['Annotazioni']))
            story.append(Spacer(1, 6))
        
        # Eventi speciali
        self._add_eventi_speciali(story, giornale)
        
        # Firme
        self._add_firme_section(story, cantiere_info)
    
    def _add_operatori_section(self, story, operatori: List[Dict[str, Any]]):
        """Aggiunge sezione operatori."""
        
        story.append(Paragraph("OPERAI e MEZZI:", self.styles['MeteoInfo']))
        
        # Formatta operatori in formato richiesto
        operatori_text = ""
        for i, operatore in enumerate(operatori):
            nome_completo = f"{operatore.get('nome', '')} {operatore.get('cognome', '')}".strip()
            qualifica = operatore.get('qualifica', operatore.get('ruolo', 'Operatore'))
            ore = operatore.get('ore_lavorate', 1)
            
            operatore_text = f"{nome_completo}_{qualifica} = {ore}"
            
            if i > 0 and i % 3 == 0:  # Va a capo ogni 3 operatori
                operatori_text += ";<br/>"
            elif i < len(operatori) - 1:
                operatori_text += ";  "
            
            operatori_text += operatore_text
        
        # Aggiungi mezzi utilizzati se presenti
        mezzi_text = ""
        mezzi_utilizzati = []
        
        # Controlla se ci sono mezzi nelle attrezzature
        attrezzatura = self._get_mezzi_from_attrezzatura(story)  # Passa story per l'accesso
        
        if attrezzatura:
            for mezzo in attrezzatura:
                mezzi_utilizzati.append(f"{mezzo} = 1")
        
        if mezzi_utilizzati:
            operatori_text += ";  " + ";  ".join(mezzi_utilizzati)
        
        story.append(Paragraph(operatori_text, self.styles['OperatoriInfo']))
        story.append(Spacer(1, 12))
    
    def _get_mezzi_from_attrezzatura(self, story) -> List[str]:
        """Estrae mezzi meccanici dalle attrezzature."""
        mezzi = []
        # Questa funzione potrebbe essere implementata per estrarre mezzi specifici
        # dalle attrezzature utilizzate nel giornale
        return mezzi
    
    def _add_eventi_speciali(self, story, giornale: Dict[str, Any]):
        """Aggiunge sezione eventi speciali e foto."""
        
        # Sopralluoghi
        sopralluoghi = giornale.get('sopralluoghi', '')
        if sopralluoghi:
            story.append(Paragraph(f"Sopralluoghi: {sopralluoghi}", self.styles['Annotazioni']))
            story.append(Spacer(1, 6))
        
        # Disposizioni
        disposizioni = []
        if giornale.get('disposizioni_rup'):
            disposizioni.append(f"RUP: {giornale['disposizioni_rup']}")
        if giornale.get('disposizioni_direttore'):
            disposizioni.append(f"DL: {giornale['disposizioni_direttore']}")
        
        if disposizioni:
            story.append(Paragraph("Disposizioni:", self.styles['MeteoInfo']))
            for disposizione in disposizioni:
                story.append(Paragraph(f"- {disposizione}", self.styles['Annotazioni']))
            story.append(Spacer(1, 6))
    
    def _add_firme_section(self, story, cantiere_info: Dict[str, Any]):
        """Aggiunge sezione firme."""
        
        story.append(Spacer(1, 12))
        
        # Linea separatoria
        story.append(HRFlowable(width="100%", thickness=1, color=black))
        story.append(Spacer(1, 8))
        
        # Tabella firme
        firme_data = [
            ["COMMITTENTE:", cantiere_info.get('committente', '')],
            ["GIORNALE DEI LAVORI N. 1", ""],
            ["", ""],
            ["L'IMPRESA", "IL DIRETTORE DEI LAVORI"]
        ]
        
        firme_table = Table(firme_data, colWidths=[9*cm, 9*cm])
        firme_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica'),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 3), (0, 3), 'Helvetica'),
            ('FONTNAME', (1, 3), (1, 3), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (0, 1), (0, 1), 'CENTER'),
            ('ALIGN', (0, 3), (0, 3), 'CENTER'),
            ('ALIGN', (1, 3), (1, 3), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        
        story.append(firme_table)
        story.append(Spacer(1, 8))
    
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
giornale_pdf_generator = GiornalePDFGenerator()

# Funzione di utilità per generazione rapida
def generate_giornale_pdf_quick(giornali: List[Dict[str, Any]], 
                                cantiere_info: Dict[str, Any], 
                                site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilità per generazione rapida PDF Giornale."""
    return giornale_pdf_generator.generate_giornale_pdf(giornali, cantiere_info, site_info)