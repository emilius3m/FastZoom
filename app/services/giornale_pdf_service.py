"""
app/services/giornale_pdf_service_v2.py

Servizio PDF per Giornale di Cantiere - VERSIONE 2.0 COMPLETA
- Design professionale e accattivante
- Tutte le 11 sezioni documentate
- Zero perdita di dati
- Conforme agli standard ICCD

Autore: FastZoom Archaeological System
Data: 13 Novembre 2025
"""

import io
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, 
    KeepTogether, PageBreak, Image
)
from reportlab.platypus.flowables import HRFlowable
from loguru import logger


class GiornalePDFGeneratorV2:
    """Generatore PDF professionali per Giornale di Cantiere - Versione 2.0"""

    # Colori professionali
    COLORS = {
        'header_bg': colors.HexColor('#1a3a52'),
        'header_text': colors.white,
        'accent': colors.HexColor('#2c5aa0'),
        'accent_light': colors.HexColor('#e8eef5'),
        'border': colors.HexColor('#4a7ba7'),
        'text': colors.HexColor('#1a1a1a'),
        'grey': colors.HexColor('#666666'),
        'light_grey': colors.HexColor('#f5f5f5'),
    }

    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()

    def _setup_custom_styles(self):
        """Configura stili personalizzati professionali"""
        
        # Helper function to safely add or update styles
        def add_or_update_style(name, **kwargs):
            if name in self.styles.byName:
                # Update existing style
                style = self.styles[name]
                for key, value in kwargs.items():
                    setattr(style, key, value)
                logger.debug(f"Updated existing style: {name}")
            else:
                # Add new style
                self.styles.add(ParagraphStyle(name=name, **kwargs))
                logger.debug(f"Added new style: {name}")
        
        # Titolo principale
        add_or_update_style(
            'MainTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            textColor=self.COLORS['header_bg'],
            spaceAfter=6,
            spaceBefore=6,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )

        # Sottotitolo
        add_or_update_style(
            'Subtitle',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=self.COLORS['grey'],
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )

        # Heading sezioni
        add_or_update_style(
            'SectionHeading',
            parent=self.styles['Heading2'],
            fontSize=12,
            textColor=self.COLORS['accent'],
            spaceAfter=8,
            spaceBefore=8,
            fontName='Helvetica-Bold',
            borderColor=self.COLORS['accent'],
            borderWidth=2,
            borderPadding=6,
            borderRadius=3
        )

        # Sottosezione
        add_or_update_style(
            'SubsectionHeading',
            parent=self.styles['Heading3'],
            fontSize=10,
            textColor=self.COLORS['header_bg'],
            spaceAfter=6,
            fontName='Helvetica-Bold'
        )

        # Testo normale giustificato - UPDATE existing BodyText style instead of adding new one
        add_or_update_style(
            'BodyText',
            parent=self.styles['Normal'],
            fontSize=9,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
            leading=11,
            textColor=self.COLORS['text']
        )

        # Etichetta/Label
        add_or_update_style(
            'Label',
            parent=self.styles['Normal'],
            fontSize=9,
            fontName='Helvetica-Bold',
            textColor=self.COLORS['header_bg'],
            spaceAfter=3
        )

        # Numero pagina
        add_or_update_style(
            'PageNum',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=self.COLORS['grey'],
            alignment=TA_CENTER,
            fontName='Helvetica-Oblique'
        )

    def generate_giornale_pdf(self,
                             giornali: List[Dict[str, Any]],
                             cantiere_info: Dict[str, Any],
                             site_info: Dict[str, Any]) -> bytes:
        """
        Genera PDF completo del giornale di cantiere
        
        Include tutte le 11 sezioni:
        1. Intestazione progetto
        2. Informazioni generali
        3. Condizioni meteorologiche
        4. Descrizione lavori
        5. Risorse impiegate
        6. Unità stratigrafiche
        7. Materiali rinvenuti
        8. Documentazione
        9. Disposizioni
        10. Eventi particolari
        11. Note e validazione
        """
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=1.5*cm,
                bottomMargin=1.5*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
                title=f"Giornale dei Lavori - {cantiere_info.get('nome', 'Cantiere')}"
            )

            story = []

            # Pagina titolo
            self._add_title_page(story, cantiere_info, site_info, len(giornali))
            story.append(PageBreak())

            # Indice
            if len(giornali) > 3:
                self._add_index(story, giornali)
                story.append(PageBreak())

            # Sezione stato cantiere
            self._add_stato_cantiere_section(story, cantiere_info)
            story.append(PageBreak())

            # Giornali
            for i, giornale in enumerate(giornali, 1):
                self._add_giornale_page(story, giornale, i, len(giornali), cantiere_info)
                if i < len(giornali):
                    story.append(PageBreak())

            # Pagina finale: Firme
            story.append(PageBreak())
            self._add_signature_page(story, cantiere_info, site_info)

            doc.build(story)

            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            buffer.close()

            logger.info(f"✓ PDF generato: {cantiere_info.get('nome')} ({len(pdf_bytes)} bytes)")
            return pdf_bytes

        except Exception as e:
            logger.error(f"✗ Errore generazione PDF: {e}")
            raise

    def _add_title_page(self, story, cantiere_info, site_info, num_giornali):
        """Pagina titolo professionale con informazioni complete del cantiere"""
        
        story.append(Spacer(1, 1*cm))
        
        # Logo/Header
        story.append(Paragraph("GIORNALE DEI LAVORI DI CANTIERE", self.styles['MainTitle']))
        story.append(Paragraph("Documentazione Archeologica Conforme agli Standard ICCD",
                              self.styles['Subtitle']))
        story.append(Spacer(1, 0.5*cm))
        
        # Linea decorativa
        story.append(HRFlowable(width="100%", thickness=2, color=self.COLORS['accent']))
        story.append(Spacer(1, 0.8*cm))

        # Blocco informazioni stato e priorità
        status_data = [
            ["STATO CANTIERE:", cantiere_info.get('stato_formattato', 'N/D')],
            ["PRIORITÀ:", self._get_priority_level(cantiere_info.get('priorita'))],
            ["DURATA:", f"{cantiere_info.get('durata_giorni', 'N/D')} giorni" if cantiere_info.get('durata_giorni') else "N/D"],
            ["CODICE:", cantiere_info.get('codice', 'N/D')]
        ]

        status_table = Table(status_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['header_bg']),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, self.COLORS['border']),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))

        # Colore speciale per stato
        stato_color = self._get_status_color(cantiere_info.get('stato'))
        status_table.setStyle(TableStyle([
            ('TEXTCOLOR', (1, 0), (1, 0), stato_color),
        ]))
        
        story.append(status_table)
        story.append(Spacer(1, 0.8*cm))

        # Tabella informazioni principali ampliata
        header_data = [
            ["OGGETTO:", cantiere_info.get('oggetto_appalto', cantiere_info.get('nome', 'N/D'))],
            ["COMMITTENTE:", cantiere_info.get('committente', 'N/D')],
            ["IMPRESA ESECUTRICE:", cantiere_info.get('impresa_esecutrice', 'N/D')],
            ["DIRETTORE DEI LAVORI:", cantiere_info.get('direttore_lavori', 'N/D')],
            ["RESPONSABILE PROCEDIMENTO:", cantiere_info.get('responsabile_procedimento', 'N/D')],
            ["RESPONSABILE CANTIERE:", cantiere_info.get('responsabile_cantiere', 'N/D')],
            ["TIPOLOGIA INTERVENTO:", cantiere_info.get('tipologia_intervento', 'N/D')],
            ["SITO ARCHEOLOGICO:", site_info.get('name', 'N/D')],
            ["DATA DOCUMENTO:", datetime.now().strftime('%d/%m/%Y %H:%M')],
            ["GIORNALI INCLUSI:", str(num_giornali)],
        ]

        header_table = Table(header_data, colWidths=[5*cm, 11*cm])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['header_bg']),
            ('TEXTCOLOR', (1, 0), (1, -1), self.COLORS['text']),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 0.8*cm))

        # Sezione aggiuntiva - Informazioni geografiche e codici
        geo_data = [
            ["AREA:", cantiere_info.get('area_descrizione', 'N/D')],
            ["QUOTA:", cantiere_info.get('quota', 'N/D')],
            ["CODICE CUP:", cantiere_info.get('codice_cup', 'N/D')],
            ["CODICE CIG:", cantiere_info.get('codice_cig', 'N/D')],
            ["IMPORTO LAVORI:", f"€{cantiere_info.get('importo_lavori', 'N/D'):,.2f}" if cantiere_info.get('importo_lavori') else "N/D"],
            ["COORDINATE:", self._format_coordinates(cantiere_info.get('coordinate_lat'), cantiere_info.get('coordinate_lon'))]
        ]

        geo_table = Table(geo_data, colWidths=[3*cm, 3*cm, 3*cm, 3*cm, 3*cm, 3*cm])
        geo_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['light_grey']),
            ('BACKGROUND', (0, 1), (-1, 1), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text']),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(geo_table)
        story.append(Spacer(1, 1.5*cm))

        # Nota informativa
        nota = ("Questo documento contiene la documentazione completa delle attività di scavo "
               "conforme agli standard ICCD del Ministero della Cultura italiano. "
               "Tutti i dati sono tracciati e validabili. "
               f"Stato attuale cantiere: {cantiere_info.get('stato_formattato', 'N/D')}.")
        story.append(Paragraph(nota, self.styles['BodyText']))

    def _add_index(self, story, giornali):
        """Aggiunge indice dei giornali"""
        story.append(Paragraph("INDICE", self.styles['MainTitle']))
        story.append(Spacer(1, 0.3*cm))

        for i, g in enumerate(giornali, 1):
            data = self._format_date(g.get('data', 'N/D'))
            story.append(Paragraph(f"<b>Giornale {i}:</b> {data}", self.styles['BodyText']))
            story.append(Spacer(1, 0.2*cm))

    def _add_stato_cantiere_section(self, story, cantiere_info):
        """Aggiunge sezione completa sullo stato del cantiere"""
        
        story.append(Paragraph("STATO DEL CANTIERE E INFORMAZIONI CRITICHE", self.styles['MainTitle']))
        story.append(Spacer(1, 0.5*cm))
        
        # Tabella stato e progressione
        status_data = [
            ["STATO ATTUALE:", cantiere_info.get('stato_formattato', 'N/D')],
            ["PRIORITÀ INTERVENTO:", self._get_priority_level(cantiere_info.get('priorita'))],
            ["DURATA GIORNALIERA:", f"{cantiere_info.get('durata_giorni', 'N/D')} giorni" if cantiere_info.get('durata_giorni') else "In corso"],
            ["CANTIERE IN CORSO:", "SÌ" if cantiere_info.get('e_in_corso') else "NO"],
            ["CODICE IDENTIFICATIVO:", cantiere_info.get('codice', 'N/D')],
            ["RESPONSABILE CANTIERE:", cantiere_info.get('responsabile_cantiere', 'N/D')]
        ]

        status_table = Table(status_data, colWidths=[5*cm, 12*cm])
        status_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['accent']),
            ('TEXTCOLOR', (1, 0), (1, -1), self.COLORS['text']),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        # Colore speciale per stato
        stato_color = self._get_status_color(cantiere_info.get('stato'))
        status_table.setStyle(TableStyle([
            ('TEXTCOLOR', (1, 0), (1, 0), stato_color),
        ]))
        
        story.append(status_table)
        story.append(Spacer(1, 0.8*cm))

        # Tabella timeline - Programmato vs Effettivo
        story.append(Paragraph("CONFRONTO TEMPORALE: PROGRAMMAZIONE VS REALTÀ", self.styles['SectionHeading']))
        story.append(Spacer(1, 0.3*cm))
        
        timeline_data = [
            ["DATA INIZIO PROGRAMMATO:", self._format_date(cantiere_info.get('data_inizio_prevista'))],
            ["DATA INIZIO EFFETTIVO:", self._format_date(cantiere_info.get('data_inizio_effettiva'))],
            ["DATA FINE PROGRAMMATO:", self._format_date(cantiere_info.get('data_fine_prevista'))],
            ["DATA FINE EFFETTIVO:", self._format_date(cantiere_info.get('data_fine_effettiva'))],
            ["STATO AVANZAMENTO:", f"{'CANTIERE ATTIVO' if cantiere_info.get('e_in_corso') else 'CANTIERE TERMINATO'}"]
        ]

        timeline_table = Table(timeline_data, colWidths=[5.5*cm, 5.5*cm])
        timeline_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent_light']),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 0), (-1, -1), self.COLORS['text']),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        # Colori diversi per programmato vs effettivo
        timeline_table.setStyle(TableStyle([
            ('TEXTCOLOR', (0, 0), (0, 0), colors.HexColor('#3b82f6')),  # Blu per programmato
            ('TEXTCOLOR', (1, 0), (1, 0), colors.HexColor('#22c55e')),  # Verde per effettivo
            ('TEXTCOLOR', (0, 1), (0, 2), colors.HexColor('#3b82f6')),  # Blu per programmato
            ('TEXTCOLOR', (1, 1), (1, 2), colors.HexColor('#22c55e')),  # Verde per effettivo
        ]))
        
        story.append(timeline_table)
        story.append(Spacer(1, 0.8*cm))

        # Sezione informazioni aggiuntive
        story.append(Paragraph("INFORMAZIONI TECNICHE E GEOREFERENZIAZIONE", self.styles['SectionHeading']))
        story.append(Spacer(1, 0.3*cm))
        
        info_data = [
            ["TIPOLOGIA INTERVENTO:", cantiere_info.get('tipologia_intervento', 'N/D')],
            ["AREA SPECIFICA:", cantiere_info.get('area_descrizione', 'N/D')],
            ["QUOTA ALTIMETRICA:", cantiere_info.get('quota', 'N/D')],
            ["COORDINATE GPS:", self._format_coordinates(cantiere_info.get('coordinate_lat'), cantiere_info.get('coordinate_lon'))]
        ]

        info_table = Table(info_data, colWidths=[5*cm, 12*cm])
        info_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['accent']),
            ('TEXTCOLOR', (1, 0), (1, -1), self.COLORS['text']),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ]))
        
        story.append(info_table)
        story.append(Spacer(1, 0.5*cm))

    def _add_giornale_page(self, story, giornale, num, total, cantiere_info):
        """Aggiunge una pagina completa di giornale con tutte le 11 sezioni"""
        
        # Header pagina
        data = self._format_date(giornale.get('data', 'N/D'))
        story.append(Paragraph(f"GIORNALE N. {num}/{total} - {data}", self.styles['MainTitle']))
        story.append(Spacer(1, 0.3*cm))
        
        story.append(Paragraph(f"Pag. {num + 1}", self.styles['PageNum']))
        story.append(Spacer(1, 0.5*cm))

        # ===== SEZIONE 1: INFORMAZIONI GENERALI =====
        story.append(Paragraph("1. INFORMAZIONI GENERALI", self.styles['SectionHeading']))
        
        info_data = [
            ["Data:", self._format_date(giornale.get('data'))],
            ["Ora Inizio:", giornale.get('ora_inizio', 'N/D')],
            ["Ora Fine:", giornale.get('ora_fine', 'N/D')],
            ["Responsabile Scavo:", giornale.get('responsabile_scavo', giornale.get('responsabile_nome', 'N/D'))],
            ["Compilatore:", giornale.get('compilatore', 'N/D')],
        ]
        
        info_table = self._create_data_table(info_data)
        story.append(info_table)
        story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 2: CONDIZIONI METEOROLOGICHE =====
        story.append(Paragraph("2. CONDIZIONI METEOROLOGICHE", self.styles['SectionHeading']))
        
        meteo_text = self._format_meteo_detailed(giornale)
        story.append(Paragraph(meteo_text, self.styles['BodyText']))
        story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 3: DESCRIZIONE LAVORI =====
        story.append(Paragraph("3. DESCRIZIONE LAVORI", self.styles['SectionHeading']))
        
        if giornale.get('descrizione_lavori'):
            story.append(Paragraph(giornale['descrizione_lavori'], self.styles['BodyText']))
        
        if giornale.get('modalita_lavorazioni'):
            story.append(Paragraph("<b>Modalità di lavorazione:</b> " + giornale['modalita_lavorazioni'],
                                  self.styles['BodyText']))
        story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 4: RISORSE IMPIEGATE =====
        story.append(Paragraph("4. RISORSE IMPIEGATE", self.styles['SectionHeading']))
        
        # Operatori
        if giornale.get('operatori_presenti'):
            story.append(Paragraph("<b>Operatori:</b>", self.styles['SubsectionHeading']))
            
            op_table_data = [["Nome", "Qualifica", "Ore", "Note"]]
            for op in giornale['operatori_presenti']:
                op_table_data.append([
                    f"{op.get('nome', '')} {op.get('cognome', '')}",
                    op.get('qualifica', 'N/D'),
                    str(op.get('ore_lavorate', '8')),
                    op.get('note_presenza', '')
                ])
            
            op_table = Table(op_table_data, colWidths=[3*cm, 3*cm, 2*cm, 4*cm])
            op_table.setStyle(self._get_table_style())
            story.append(op_table)
            story.append(Spacer(1, 0.2*cm))

        # Attrezzature
        if giornale.get('attrezzatura_utilizzata'):
            story.append(Paragraph("<b>Attrezzature:</b> " + giornale['attrezzatura_utilizzata'],
                                  self.styles['BodyText']))
        
        # Mezzi
        if giornale.get('mezzi_utilizzati'):
            story.append(Paragraph("<b>Mezzi:</b> " + giornale['mezzi_utilizzati'],
                                  self.styles['BodyText']))
        story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 5: UNITÀ STRATIGRAFICHE =====
        us_list = giornale.get('us_elaborate', []) or []
        usm_list = giornale.get('usm_elaborate', []) or []
        usr_list = giornale.get('usr_elaborate', []) or []
        
        if us_list or usm_list or usr_list:
            story.append(Paragraph("5. UNITÀ STRATIGRAFICHE ELABORATE", self.styles['SectionHeading']))
            
            if us_list:
                story.append(Paragraph(f"<b>US:</b> {', '.join(str(u) for u in us_list)}", 
                                      self.styles['BodyText']))
            if usm_list:
                story.append(Paragraph(f"<b>USM:</b> {', '.join(str(u) for u in usm_list)}", 
                                      self.styles['BodyText']))
            if usr_list:
                story.append(Paragraph(f"<b>USR:</b> {', '.join(str(u) for u in usr_list)}", 
                                      self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 6: MATERIALI RINVENUTI =====
        if giornale.get('materiali_rinvenuti'):
            story.append(Paragraph("6. MATERIALI RINVENUTI", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['materiali_rinvenuti'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 7: DOCUMENTAZIONE PRODOTTA =====
        if giornale.get('documentazione_prodotta'):
            story.append(Paragraph("7. DOCUMENTAZIONE PRODOTTA", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['documentazione_prodotta'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 8: DISPOSIZIONI E ORDINI =====
        disposizioni = []
        if giornale.get('disposizioni_rup'):
            disposizioni.append(("RUP", giornale['disposizioni_rup']))
        if giornale.get('disposizioni_direttore'):
            disposizioni.append(("Direttore Lavori", giornale['disposizioni_direttore']))
        
        if disposizioni:
            story.append(Paragraph("8. DISPOSIZIONI E ORDINI", self.styles['SectionHeading']))
            for label, val in disposizioni:
                story.append(Paragraph(f"<b>{label}:</b> {val}", self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 9: EVENTI PARTICOLARI =====
        eventi = []
        if giornale.get('sospensioni'):
            eventi.append(("Sospensioni", giornale['sospensioni']))
        if giornale.get('contestazioni'):
            eventi.append(("Contestazioni", giornale['contestazioni']))
        if giornale.get('incidenti'):
            eventi.append(("Incidenti", giornale['incidenti']))
        if giornale.get('problematiche'):
            eventi.append(("Problematiche", giornale['problematiche']))
        
        if eventi:
            story.append(Paragraph("9. EVENTI PARTICOLARI", self.styles['SectionHeading']))
            for label, val in eventi:
                story.append(Paragraph(f"<b>{label}:</b> {val}", self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 10: NOTE E OSSERVAZIONI =====
        if giornale.get('note_generali') or giornale.get('sopralluoghi'):
            story.append(Paragraph("10. NOTE E OSSERVAZIONI", self.styles['SectionHeading']))
            
            if giornale.get('note_generali'):
                story.append(Paragraph(giornale['note_generali'], self.styles['BodyText']))
            
            if giornale.get('sopralluoghi'):
                story.append(Paragraph(f"<b>Sopralluoghi:</b> {giornale['sopralluoghi']}", 
                                      self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 11: VALIDAZIONE =====
        story.append(Paragraph("11. STATO VALIDAZIONE", self.styles['SectionHeading']))
        
        val_data = [
            ["Validato:", "✓ SI" if giornale.get('validato') else "✗ NO"],
            ["Data Validazione:", giornale.get('data_validazione', 'N/D')],
            ["Data Creazione:", giornale.get('created_at', 'N/D')],
            ["Ultimo Aggiornamento:", giornale.get('updated_at', 'N/D')],
        ]
        
        val_table = self._create_data_table(val_data)
        story.append(val_table)

    def _add_signature_page(self, story, cantiere_info, site_info):
        """Pagina finale con firme"""
        
        story.append(Paragraph("FIRME E VALIDAZIONI", self.styles['MainTitle']))
        story.append(Spacer(1, 0.8*cm))

        firme_text = (
            "Sottoscritti il presente Giornale di Cantiere:<br/><br/>"
            "<b>Il Responsabile di Scavo:</b><br/>"
            "_____________________________________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data: __________<br/>"
            "Nome: _____________________________________________ Qualifica: _______________________<br/><br/><br/>"
            "<b>Il Direttore dei Lavori:</b><br/>"
            "_____________________________________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data: __________<br/>"
            "Nome: _____________________________________________ Qualifica: _______________________<br/><br/><br/>"
            "<b>Il Responsabile del Procedimento:</b><br/>"
            "_____________________________________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data: __________<br/>"
            "Nome: _____________________________________________ Qualifica: _______________________<br/><br/><br/>"
            "<b>Il Rappresentante della Committenza:</b><br/>"
            "_____________________________________________________&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Data: __________<br/>"
            "Nome: _____________________________________________ Qualifica: _______________________"
        )
        
        story.append(Paragraph(firme_text, self.styles['BodyText']))
        story.append(Spacer(1, 1*cm))

        footer = (
            f"<i>Documento generato da FastZoom Archaeological System<br/>"
            f"Data: {datetime.now().strftime('%d/%m/%Y ore %H:%M:%S')}<br/>"
            f"Sito: {site_info.get('name', 'N/D')}<br/>"
            f"Cantiere: {cantiere_info.get('nome_completo', cantiere_info.get('nome', 'N/D'))}<br/>"
            f"Stato: {cantiere_info.get('stato_formattato', 'N/D')} | "
            f"Durata: {cantiere_info.get('durata_giorni', 'N/D')} giorni | "
            f"Priorità: {cantiere_info.get('priorita', 'N/D')}/5</i>"
        )
        
        story.append(Paragraph(footer, self.styles['BodyText']))

    def _create_data_table(self, data, col_widths=None):
        """Crea tabella dati formattata"""
        if col_widths is None:
            col_widths = [4*cm, 12*cm]
        
        table = Table(data, colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['header_bg']),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table

    def _get_table_style(self):
        """Stile per tabelle operatori"""
        return TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
            ('TEXTCOLOR', (0, 0), (-1, 0), self.COLORS['header_text']),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ])

    def _format_date(self, date_value) -> str:
        """Formatta data italiana"""
        if not date_value:
            return 'N/D'
        
        if isinstance(date_value, str):
            try:
                dt = datetime.fromisoformat(date_value.replace('Z', '+00:00'))
                return dt.strftime('%d/%m/%Y')
            except:
                return date_value
        
        try:
            return date_value.strftime('%d/%m/%Y')
        except:
            return str(date_value)

    def _format_meteo_detailed(self, giornale):
        """Formatta dettagli meteo"""
        parts = []
        
        if giornale.get('condizioni_meteo'):
            parts.append(f"<b>Condizioni:</b> {giornale['condizioni_meteo'].upper()}")
        
        temps = []
        if giornale.get('temperatura'):
            temps.append(f"Attuale: {giornale['temperatura']}°C")
        if giornale.get('temperatura_min'):
            temps.append(f"Min: {giornale['temperatura_min']}°C")
        if giornale.get('temperatura_max'):
            temps.append(f"Max: {giornale['temperatura_max']}°C")
        
        if temps:
            parts.append("<b>Temperatura:</b> " + ", ".join(temps))
        
        if giornale.get('note_meteo'):
            parts.append(f"<b>Note:</b> {giornale['note_meteo']}")
        
        return "<br/>".join(parts) if parts else "N/D"

    def _format_coordinates(self, lat, lon) -> str:
        """Formatta coordinate GPS in formato leggibile"""
        if not lat or not lon:
            return 'N/D'
        
        try:
            # Formatta coordinate con precisione decimale
            lat_formatted = f"{float(lat):.6f}"
            lon_formatted = f"{float(lon):.6f}"
            return f"{lat_formatted}°N, {lon_formatted}°E"
        except (ValueError, TypeError):
            return f"{lat}, {lon}" if lat and lon else 'N/D'

    def _get_status_color(self, stato: str) -> colors.Color:
        """Restituisce il colore appropriato per lo stato del cantiere"""
        if stato == 'in_corso':
            return colors.HexColor('#22c55e')  # Verde
        elif stato == 'sospeso':
            return colors.HexColor('#fbbf24')  # Giallo
        elif stato == 'completato':
            return colors.HexColor('#6b7280')  # Grigio
        else:
            return colors.HexColor('#3b82f6')  # Blu

    def _get_priority_level(self, priorita: int) -> str:
        """Converte priorità numerica in livello testuale"""
        if not priorita:
            return 'N/D'
        elif priorita >= 4:
            return f"{priorita}/5 - ALTA"
        elif priorita >= 2:
            return f"{priorita}/5 - MEDIA"
        else:
            return f"{priorita}/5 - BASSA"


    def generate_operatori_pdf(self,
                              operatori: List[Dict[str, Any]],
                              site_info: Dict[str, Any]) -> bytes:
        """
        Genera PDF lista operatori del sito
        """
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=1.5*cm,
                bottomMargin=1.5*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
                title=f"Lista Operatori - {site_info.get('name', 'Sito Archeologico')}"
            )

            story = []

            # --- Header ---
            story.append(Paragraph("LISTA OPERATORI DI CANTIERE", self.styles['MainTitle']))
            story.append(Paragraph(f"Sito: {site_info.get('name', 'N/D')}", self.styles['Subtitle']))
            story.append(Spacer(1, 0.5*cm))
            
            story.append(HRFlowable(width="100%", thickness=1, color=self.COLORS['accent']))
            story.append(Spacer(1, 0.8*cm))

            # --- Info Generali ---
            info_data = [
                ["Data Estrazione:", datetime.now().strftime('%d/%m/%Y %H:%M')],
                ["Totale Operatori:", str(len(operatori))],
                ["Operatori Attivi:", str(len([op for op in operatori if op.get('stato') == 'attivo']))]
            ]
            
            info_table = Table(info_data, colWidths=[4*cm, 8*cm])
            info_table.setStyle(TableStyle([
                ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['header_bg']),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ]))
            story.append(info_table)
            story.append(Spacer(1, 1*cm))

            # --- Tabella Operatori ---
            if operatori:
                headers = ["Cognome e Nome", "Ruolo/Specializzazione", "Ore Tot.", "Stato", "Note"]
                table_data = [headers]
                
                for op in operatori:
                    nome_completo = f"{op.get('cognome', '')} {op.get('nome', '')}".strip()
                    ruolo_spec = f"{op.get('ruolo', '')}"
                    if op.get('specializzazione'):
                        ruolo_spec += f"\n{op.get('specializzazione')}"
                    
                    row = [
                        Paragraph(nome_completo, self.styles['BodyText']),
                        Paragraph(ruolo_spec, self.styles['BodyText']),
                        str(op.get('ore_totali', 0)),
                        op.get('stato', 'N/D').upper(),
                        Paragraph(op.get('note', '') or '-', self.styles['BodyText'])
                    ]
                    table_data.append(row)

                # Calcola larghezze colonne
                col_widths = [5*cm, 5*cm, 2*cm, 2*cm, 3*cm]
                
                table = Table(table_data, colWidths=col_widths, repeatRows=1)
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    
                    # Corpo tabella
                    ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 9),
                    ('ALIGN', (0, 1), (1, -1), 'LEFT'),   # Nomi e Ruoli a sx
                    ('ALIGN', (2, 1), (3, -1), 'CENTER'), # Ore e Stato al centro
                    ('VALIGN', (0, 1), (-1, -1), 'TOP'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
                    ('TOPPADDING', (0, 0), (-1, -1), 6),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                    ('LEFTPADDING', (0, 0), (-1, -1), 6),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ]))
                
                story.append(table)
            else:
                story.append(Paragraph("Nessun operatore trovato.", self.styles['BodyText']))

            # --- Footer ---
            story.append(Spacer(1, 1*cm))
            footer_text = f"Documento generato il {datetime.now().strftime('%d/%m/%Y')}"
            story.append(Paragraph(footer_text, self.styles['PageNum']))

            doc.build(story)

            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            buffer.close()

            return pdf_bytes

        except Exception as e:
            logger.error(f"✗ Errore generazione PDF operatori: {e}")
            raise


# Istanza globale
_pdf_generator = GiornalePDFGeneratorV2()


def generate_giornale_pdf_quick(giornali: List[Dict[str, Any]],
                                cantiere_info: Dict[str, Any],
                                site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilità - Genera PDF rapidamente"""
    return _pdf_generator.generate_giornale_pdf(giornali, cantiere_info, site_info)

def generate_operatori_pdf_quick(operatori: List[Dict[str, Any]],
                               site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilità - Genera PDF operatori rapidamente"""
    return _pdf_generator.generate_operatori_pdf(operatori, site_info)
