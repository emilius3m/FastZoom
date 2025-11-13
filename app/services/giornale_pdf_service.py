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
        """Pagina titolo professionale"""
        
        story.append(Spacer(1, 1*cm))
        
        # Logo/Header
        story.append(Paragraph("GIORNALE DEI LAVORI DI CANTIERE", self.styles['MainTitle']))
        story.append(Paragraph("Documentazione Archeologica Conforme agli Standard ICCD", 
                              self.styles['Subtitle']))
        story.append(Spacer(1, 0.5*cm))
        
        # Linea decorativa
        story.append(HRFlowable(width="100%", thickness=2, color=self.COLORS['accent']))
        story.append(Spacer(1, 0.8*cm))

        # Informazioni intestazione
        header_data = [
            ["OGGETTO:", cantiere_info.get('oggetto_appalto', cantiere_info.get('nome', 'N/D'))],
            ["COMMITTENTE:", cantiere_info.get('committente', 'N/D')],
            ["IMPRESA ESECUTRICE:", cantiere_info.get('impresa_esecutrice', 'N/D')],
            ["DIRETTORE DEI LAVORI:", cantiere_info.get('direttore_lavori', 'N/D')],
            ["RESPONSABILE PROCEDIMENTO:", cantiere_info.get('responsabile_procedimento', 'N/D')],
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
        story.append(Spacer(1, 1.5*cm))

        # Nota informativa
        nota = ("Questo documento contiene la documentazione completa delle attività di scavo "
               "conforme agli standard ICCD del Ministero della Cultura italiano. "
               "Tutti i dati sono tracciati e validabili.")
        story.append(Paragraph(nota, self.styles['BodyText']))

    def _add_index(self, story, giornali):
        """Aggiunge indice dei giornali"""
        story.append(Paragraph("INDICE", self.styles['MainTitle']))
        story.append(Spacer(1, 0.3*cm))

        for i, g in enumerate(giornali, 1):
            data = self._format_date(g.get('data', 'N/D'))
            story.append(Paragraph(f"<b>Giornale {i}:</b> {data}", self.styles['BodyText']))
            story.append(Spacer(1, 0.2*cm))

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
            f"Cantiere: {cantiere_info.get('nome', 'N/D')}</i>"
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


# Istanza globale
_pdf_generator = GiornalePDFGeneratorV2()


def generate_giornale_pdf_quick(giornali: List[Dict[str, Any]],
                                cantiere_info: Dict[str, Any],
                                site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilità - Genera PDF rapidamente"""
    return _pdf_generator.generate_giornale_pdf(giornali, cantiere_info, site_info)
