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
from collections import Counter
from datetime import datetime, date
from html import escape
from typing import Dict, Any, List, Optional
from reportlab.lib.pagesizes import A4, landscape
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

from app.services.giornale_export_builder import build_giornale_export_model


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
        6. UnitÃ  stratigrafiche
        7. Materiali rinvenuti
        8. Documentazione
        9. Disposizioni
        10. Eventi particolari
        11. Note e validazione
        """
        try:
            model = build_giornale_export_model(giornali, cantiere_info, site_info)
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=A4,
                topMargin=1.4*cm,
                bottomMargin=1.4*cm,
                leftMargin=1.6*cm,
                rightMargin=1.6*cm,
                title=f"Giornale dei Lavori - {model['cantiere_name']}"
            )

            story = []
            self._render_giornale_export_pdf(story, model)

            doc.build(story)

            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            buffer.close()

            logger.info(f"âœ“ PDF generato: {cantiere_info.get('nome')} ({len(pdf_bytes)} bytes)")
            return pdf_bytes

        except Exception as e:
            logger.error(f"âœ— Errore generazione PDF: {e}")
            raise

    def _render_giornale_export_pdf(self, story, model: Dict[str, Any]) -> None:
        story.append(Paragraph(model["title"], self.styles['MainTitle']))
        story.append(Paragraph(model["subtitle"], self.styles['Subtitle']))
        story.append(Spacer(1, 0.3 * cm))
        story.append(HRFlowable(width="100%", thickness=1.5, color=self.COLORS['accent']))
        story.append(Spacer(1, 0.5 * cm))
        story.append(self._pdf_key_value_table(model["cover_rows"]))

        story.append(PageBreak())
        story.append(Paragraph("SCHEDA CANTIERE", self.styles['MainTitle']))
        for section in model["summary_sections"]:
            self._pdf_add_section(story, section)

        for entry in model["giornali"]:
            story.append(PageBreak())
            story.append(Paragraph(entry["heading"].upper(), self.styles['MainTitle']))
            for section in entry["sections"]:
                self._pdf_add_section(story, section)

        story.append(PageBreak())
        story.append(Paragraph("FIRME E VALIDAZIONI", self.styles['MainTitle']))
        story.append(Paragraph(
            "Le firme sotto riportate attestano la presa visione del registro esportato.",
            self.styles['BodyText']
        ))
        signature_rows = [[label, "Firma ______________________________    Data __________"] for label, _ in model["signature_rows"]]
        story.append(self._pdf_key_value_table(signature_rows, col_widths=[6 * cm, 10 * cm]))
        story.append(Spacer(1, 0.6 * cm))
        story.append(Paragraph(
            f"Documento generato da FastZoom il {model['generated_at'].strftime('%d/%m/%Y alle %H:%M')}",
            self.styles['PageNum']
        ))

    def _pdf_add_section(self, story, section: Dict[str, Any]) -> None:
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph(self._pdf_escape(section["title"]), self.styles['SectionHeading']))
        kind = section.get("kind")

        if kind == "table":
            story.append(self._pdf_key_value_table(section.get("rows", [])))
        elif kind == "text":
            items = section.get("items", [])
            if items:
                for label, text in items:
                    story.append(Paragraph(f"<b>{self._pdf_escape(label)}:</b> {self._pdf_escape(text)}", self.styles['BodyText']))
            else:
                story.append(Paragraph("N/D", self.styles['BodyText']))
        elif kind == "mixed":
            items = section.get("items", [])
            for label, text in items:
                story.append(Paragraph(f"<b>{self._pdf_escape(label)}:</b> {self._pdf_escape(text)}", self.styles['BodyText']))
            for table in section.get("tables", []):
                story.append(Paragraph(self._pdf_escape(table["title"]), self.styles['SubsectionHeading']))
                story.append(self._pdf_plain_table(table.get("headers", []), table.get("rows", [])))
            if section.get("photos"):
                story.append(Spacer(1, 0.2 * cm))
                story.append(Paragraph("Immagini", self.styles['SubsectionHeading']))
                story.append(self._pdf_photo_grid(section["photos"]))

    def _pdf_key_value_table(self, rows, col_widths=None) -> Table:
        if col_widths is None:
            col_widths = [5 * cm, 11 * cm]
        table_data = [
            [Paragraph(f"<b>{self._pdf_escape(label)}</b>", self.styles['BodyText']),
             Paragraph(self._pdf_escape(value), self.styles['BodyText'])]
            for label, value in rows
        ]
        table = Table(table_data or [["", ""]], colWidths=col_widths)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), self.COLORS['accent_light']),
            ('TEXTCOLOR', (0, 0), (0, -1), self.COLORS['header_bg']),
            ('GRID', (0, 0), (-1, -1), 0.4, self.COLORS['border']),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        return table

    def _pdf_plain_table(self, headers: List[str], rows: List[List[str]]) -> Table:
        table_data = [[Paragraph(f"<b>{self._pdf_escape(cell)}</b>", self.styles['BodyText']) for cell in headers]]
        for row in rows:
            table_data.append([Paragraph(self._pdf_escape(cell), self.styles['BodyText']) for cell in row])
        table = Table(table_data, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.4, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table

    def _pdf_photo_grid(self, photos: List[Dict[str, Any]]) -> Table:
        cells = [self._pdf_photo_cell(photo) for photo in photos]
        rows = []
        for idx in range(0, len(cells), 2):
            row = cells[idx:idx + 2]
            if len(row) == 1:
                row.append("")
            rows.append(row)

        table = Table(rows, colWidths=[8 * cm, 8 * cm])
        table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.3, self.COLORS['border']),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ]))
        return table

    def _pdf_photo_cell(self, photo: Dict[str, Any]) -> List[Any]:
        content = []
        image_bytes = photo.get("image_bytes")
        if image_bytes:
            try:
                image = Image(io.BytesIO(image_bytes))
                image._restrictSize(7.2 * cm, 5.0 * cm)
                image.hAlign = 'CENTER'
                content.append(image)
            except Exception as exc:
                logger.warning(f"Errore inserimento immagine PDF: {exc}")
                content.append(Paragraph("[Immagine non leggibile]", self.styles['BodyText']))
        else:
            content.append(Paragraph("[Immagine non disponibile nell'export]", self.styles['BodyText']))

        caption = self._pdf_escape(f"Foto {photo.get('index')}: {photo.get('title')}")
        if photo.get("description") and photo.get("description") != "N/D":
            caption += f"<br/>{self._pdf_escape(photo.get('description'))}"
        content.append(Paragraph(caption, self.styles['BodyText']))
        return content

    def _pdf_escape(self, value: Any) -> str:
        return escape(str(value or "")).replace("\n", "<br/>")

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

        # Blocco informazioni stato e prioritÃ 
        status_data = [
            ["STATO CANTIERE:", cantiere_info.get('stato_formattato', 'N/D')],
            ["PRIORITÃ€:", self._get_priority_level(cantiere_info.get('priorita'))],
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
            ["IMPORTO LAVORI:", f"â‚¬{cantiere_info.get('importo_lavori', 'N/D'):,.2f}" if cantiere_info.get('importo_lavori') else "N/D"],
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
        nota = ("Questo documento contiene la documentazione completa delle attivitÃ  di scavo "
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
            ["PRIORITÃ€ INTERVENTO:", self._get_priority_level(cantiere_info.get('priorita'))],
            ["DURATA GIORNALIERA:", f"{cantiere_info.get('durata_giorni', 'N/D')} giorni" if cantiere_info.get('durata_giorni') else "In corso"],
            ["CANTIERE IN CORSO:", "SÃŒ" if cantiere_info.get('e_in_corso') else "NO"],
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
        story.append(Paragraph("CONFRONTO TEMPORALE: PROGRAMMAZIONE VS REALTÃ€", self.styles['SectionHeading']))
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

        # ===== SEZIONE 3: LOCALIZZAZIONE E AREA DI INTERVENTO =====
        if giornale.get('area_intervento') or giornale.get('saggio'):
            story.append(Paragraph("3. LOCALIZZAZIONE E AREA DI INTERVENTO", self.styles['SectionHeading']))
            
            if giornale.get('area_intervento'):
                story.append(Paragraph(f"<b>Area di Intervento:</b> {giornale['area_intervento']}",
                                      self.styles['BodyText']))
            if giornale.get('saggio'):
                story.append(Paragraph(f"<b>Saggio:</b> {giornale['saggio']}",
                                      self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 4: OBIETTIVI E STRATEGIA =====
        if giornale.get('obiettivi'):
            story.append(Paragraph("4. OBIETTIVI E STRATEGIA", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['obiettivi'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 5: DESCRIZIONE LAVORI =====
        story.append(Paragraph("5. DESCRIZIONE LAVORI", self.styles['SectionHeading']))
        
        if giornale.get('descrizione_lavori'):
            story.append(Paragraph(giornale['descrizione_lavori'], self.styles['BodyText']))
        
        if giornale.get('modalita_lavorazioni'):
            story.append(Paragraph("<b>ModalitÃ  di lavorazione:</b> " + giornale['modalita_lavorazioni'],
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

        # ===== SEZIONE 5: UNITÃ€ STRATIGRAFICHE =====
        us_list = giornale.get('us_elaborate', []) or []
        usm_list = giornale.get('usm_elaborate', []) or []
        usr_list = giornale.get('usr_elaborate', []) or []
        
        if us_list or usm_list or usr_list:
            story.append(Paragraph("7. UNITÃ€ STRATIGRAFICHE ELABORATE", self.styles['SectionHeading']))
            
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

        # ===== SEZIONE 8: INTERPRETAZIONE E RISULTATI SCIENTIFICI =====
        if giornale.get('interpretazione') or giornale.get('campioni_prelevati') or giornale.get('strutture'):
            story.append(Paragraph("8. RISULTATI SCIENTIFICI", self.styles['SectionHeading']))
            
            if giornale.get('interpretazione'):
                story.append(Paragraph(f"<b>Interpretazione:</b> {giornale['interpretazione']}",
                                      self.styles['BodyText']))
            if giornale.get('campioni_prelevati'):
                story.append(Paragraph(f"<b>Campioni Prelevati:</b> {giornale['campioni_prelevati']}",
                                      self.styles['BodyText']))
            if giornale.get('strutture'):
                story.append(Paragraph(f"<b>Strutture:</b> {giornale['strutture']}",
                                      self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 9: MATERIALI RINVENUTI =====
        if giornale.get('materiali_rinvenuti'):
            story.append(Paragraph("9. MATERIALI RINVENUTI", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['materiali_rinvenuti'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 10: DOCUMENTAZIONE PRODOTTA =====
        if giornale.get('documentazione_prodotta'):
            story.append(Paragraph("10. DOCUMENTAZIONE PRODOTTA", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['documentazione_prodotta'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 11: FOTO COLLEGATE =====
        foto_list = giornale.get('foto', [])
        if foto_list:
            story.append(Paragraph("11. DOCUMENTAZIONE FOTOGRAFICA", self.styles['SectionHeading']))
            story.append(Paragraph(f"<b>Foto collegate:</b> {len(foto_list)}", self.styles['BodyText']))
            story.append(Spacer(1, 0.2*cm))
            
            # Create a grid of photos
            photo_items = []
            for foto in foto_list:
                try:
                    # Get photo bytes from pre-loaded data if available
                    photo_bytes = foto.get('_image_bytes')
                    
                    if photo_bytes:
                        # Create image from bytes
                        img_buffer = io.BytesIO(photo_bytes)
                        img = Image(img_buffer, width=4*cm, height=3*cm)
                        img.hAlign = 'CENTER'
                        
                        # Caption
                        caption = foto.get('title') or foto.get('description') or foto.get('original_filename', 'Foto')
                        caption_para = Paragraph(f"<font size='7'>{caption[:30]}{'...' if len(caption) > 30 else ''}</font>", 
                                                self.styles['BodyText'])
                        
                        photo_items.append([img, caption_para])
                    else:
                        # Fallback: just show the filename/title
                        title = foto.get('title') or foto.get('original_filename') or 'Foto'
                        photo_items.append([Paragraph(f"ðŸ“· {title}", self.styles['BodyText']), Paragraph("", self.styles['BodyText'])])
                        
                except Exception as e:
                    logger.warning(f"Errore caricamento foto per PDF: {e}")
                    title = foto.get('title') or foto.get('original_filename') or 'Foto'
                    photo_items.append([Paragraph(f"ðŸ“· {title}", self.styles['BodyText']), Paragraph("", self.styles['BodyText'])])
            
            # Display photos in table grid (3 columns)
            if photo_items:
                # Organize into rows of 3
                rows = []
                for i in range(0, len(photo_items), 3):
                    row = []
                    for j in range(3):
                        if i + j < len(photo_items):
                            row.append(photo_items[i + j])
                        else:
                            row.append([Paragraph("", self.styles['BodyText']), Paragraph("", self.styles['BodyText'])])
                    rows.append([item[0] for item in row])  # Images row
                    rows.append([item[1] for item in row])  # Captions row
                
                if rows:
                    photo_table = Table(rows, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
                    photo_table.setStyle(TableStyle([
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    story.append(photo_table)
            
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 12: FORNITURE =====
        if giornale.get('forniture'):
            story.append(Paragraph("12. FORNITURE E MATERIALI", self.styles['SectionHeading']))
            story.append(Paragraph(giornale['forniture'], self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 13: DISPOSIZIONI E ORDINI =====
        disposizioni = []
        if giornale.get('disposizioni_rup'):
            disposizioni.append(("RUP", giornale['disposizioni_rup']))
        if giornale.get('disposizioni_direttore'):
            disposizioni.append(("Direttore Lavori", giornale['disposizioni_direttore']))
        
        if disposizioni:
            story.append(Paragraph("13. DISPOSIZIONI E ORDINI", self.styles['SectionHeading']))
            for label, val in disposizioni:
                story.append(Paragraph(f"<b>{label}:</b> {val}", self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 14: EVENTI PARTICOLARI =====
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
            story.append(Paragraph("14. EVENTI PARTICOLARI", self.styles['SectionHeading']))
            for label, val in eventi:
                story.append(Paragraph(f"<b>{label}:</b> {val}", self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 15: NOTE E OSSERVAZIONI =====
        if giornale.get('note_generali') or giornale.get('sopralluoghi'):
            story.append(Paragraph("15. NOTE E OSSERVAZIONI", self.styles['SectionHeading']))
            
            if giornale.get('note_generali'):
                story.append(Paragraph(giornale['note_generali'], self.styles['BodyText']))
            
            if giornale.get('sopralluoghi'):
                story.append(Paragraph(f"<b>Sopralluoghi:</b> {giornale['sopralluoghi']}", 
                                      self.styles['BodyText']))
            story.append(Spacer(1, 0.3*cm))

        # ===== SEZIONE 16: VALIDAZIONE =====
        story.append(Paragraph("16. STATO VALIDAZIONE", self.styles['SectionHeading']))
        
        val_data = [
            ["Validato:", "âœ“ SI" if giornale.get('validato') else "âœ— NO"],
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
            f"PrioritÃ : {cantiere_info.get('priorita', 'N/D')}/5</i>"
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
            temps.append(f"Attuale: {giornale['temperatura']}Â°C")
        if giornale.get('temperatura_min'):
            temps.append(f"Min: {giornale['temperatura_min']}Â°C")
        if giornale.get('temperatura_max'):
            temps.append(f"Max: {giornale['temperatura_max']}Â°C")
        
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
            return f"{lat_formatted}Â°N, {lon_formatted}Â°E"
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
        """Converte prioritÃ  numerica in livello testuale"""
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
        Genera un registro operativo degli operatori del sito.

        Il documento e pensato per l'uso pratico: copertura dei ruoli,
        specializzazioni disponibili, contatti, presenze e dati da completare.
        """
        try:
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(
                buffer,
                pagesize=landscape(A4),
                topMargin=1.2 * cm,
                bottomMargin=1.2 * cm,
                leftMargin=1.2 * cm,
                rightMargin=1.2 * cm,
                title=f"Registro Operatori - {site_info.get('name', 'Sito Archeologico')}"
            )

            story = []
            generated_at = datetime.now()
            sorted_operatori = sorted(
                operatori or [],
                key=lambda op: (
                    0 if op.get('stato') == 'attivo' else 1,
                    (op.get('cognome') or '').lower(),
                    (op.get('nome') or '').lower(),
                )
            )

            story.append(Paragraph("REGISTRO OPERATIVO OPERATORI", self.styles['MainTitle']))
            story.append(Paragraph(f"Sito: {self._pdf_text(site_info.get('name', 'N/D'))}", self.styles['Subtitle']))
            story.append(Paragraph(
                "Sintesi per coordinamento del personale, verifica contatti e copertura competenze.",
                self.styles['PageNum']
            ))
            story.append(Spacer(1, 0.35 * cm))
            story.append(HRFlowable(width="100%", thickness=1, color=self.COLORS['accent']))
            story.append(Spacer(1, 0.35 * cm))

            total_operatori = len(sorted_operatori)
            active_operatori = [op for op in sorted_operatori if op.get('stato') == 'attivo']
            inactive_operatori = [op for op in sorted_operatori if op.get('stato') != 'attivo']
            total_hours = sum(self._safe_number(op.get('ore_totali')) for op in sorted_operatori)
            total_giornali = sum(int(self._safe_number(op.get('giornali_count'))) for op in sorted_operatori)
            missing_contacts = [
                op for op in sorted_operatori
                if not (op.get('email') or '').strip() and not (op.get('telefono') or '').strip()
            ]
            missing_role = [op for op in sorted_operatori if not (op.get('ruolo') or '').strip()]
            missing_specialization = [op for op in sorted_operatori if not (op.get('specializzazione') or '').strip()]

            summary_data = [
                ["Totale operatori", "Attivi", "Inattivi", "Ore registrate", "Giornali con presenze"],
                [
                    str(total_operatori),
                    str(len(active_operatori)),
                    str(len(inactive_operatori)),
                    self._format_number(total_hours),
                    str(total_giornali),
                ],
            ]
            summary_table = Table(summary_data, colWidths=[5 * cm, 4 * cm, 4 * cm, 5 * cm, 6 * cm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['header_bg']),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 8),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('BACKGROUND', (0, 1), (-1, 1), self.COLORS['accent_light']),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, 1), 13),
                ('TEXTCOLOR', (0, 1), (-1, 1), self.COLORS['header_bg']),
                ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 0.45 * cm))

            role_counts = Counter(
                self._format_operator_choice(op.get('ruolo'))
                for op in sorted_operatori
                if op.get('ruolo')
            )
            spec_counts = Counter(
                self._format_operator_choice(op.get('specializzazione'))
                for op in sorted_operatori
                if op.get('specializzazione')
            )

            coverage_table = Table([[
                self._build_distribution_table("Copertura ruoli", role_counts, "Nessun ruolo valorizzato"),
                self._build_distribution_table("Specializzazioni", spec_counts, "Nessuna specializzazione valorizzata"),
                self._build_alert_table(missing_contacts, missing_role, missing_specialization),
            ]], colWidths=[8.2 * cm, 8.2 * cm, 8.2 * cm])
            coverage_table.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 0),
                ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ]))
            story.append(coverage_table)
            story.append(Spacer(1, 0.5 * cm))

            if sorted_operatori:
                story.append(Paragraph("Elenco operativo", self.styles['SectionHeading']))
                table_data = [["Operatore", "Ruolo", "Qualifica", "Specializzazione", "Contatti", "Presenze", "Stato"]]

                for op in sorted_operatori:
                    contatti = []
                    if op.get('email'):
                        contatti.append(self._pdf_text(op.get('email')))
                    if op.get('telefono'):
                        contatti.append(self._pdf_text(op.get('telefono')))
                    contatti_text = "<br/>".join(contatti) if contatti else "Contatti mancanti"
                    presenze_text = (
                        f"Ore: {self._format_number(self._safe_number(op.get('ore_totali')))}"
                        f"<br/>Giornali: {int(self._safe_number(op.get('giornali_count')))}"
                    )
                    codice_fiscale = self._pdf_text(op.get('codice_fiscale') or '-')

                    table_data.append([
                        Paragraph(
                            f"<b>{self._format_operator_name(op)}</b><br/><font size='7'>CF: {codice_fiscale}</font>",
                            self.styles['BodyText']
                        ),
                        Paragraph(self._format_operator_choice(op.get('ruolo')) or '-', self.styles['BodyText']),
                        Paragraph(self._pdf_text(op.get('qualifica') or '-'), self.styles['BodyText']),
                        Paragraph(self._format_operator_choice(op.get('specializzazione')) or '-', self.styles['BodyText']),
                        Paragraph(contatti_text, self.styles['BodyText']),
                        Paragraph(presenze_text, self.styles['BodyText']),
                        op.get('stato', 'N/D').upper(),
                    ])

                table = Table(
                    table_data,
                    colWidths=[4.4 * cm, 3.1 * cm, 4.1 * cm, 4.1 * cm, 5.1 * cm, 2.5 * cm, 2.1 * cm],
                    repeatRows=1
                )
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, 0), 8),
                    ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
                    ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
                    ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                    ('ALIGN', (0, 1), (4, -1), 'LEFT'),
                    ('ALIGN', (5, 1), (6, -1), 'CENTER'),
                    ('VALIGN', (0, 1), (-1, -1), 'TOP'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
                    ('TOPPADDING', (0, 0), (-1, -1), 5),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(table)

                note_rows = [
                    [
                        Paragraph(self._format_operator_name(op), self.styles['BodyText']),
                        Paragraph(self._pdf_text(op.get('note')), self.styles['BodyText']),
                    ]
                    for op in sorted_operatori
                    if (op.get('note') or '').strip()
                ]
                if note_rows:
                    story.append(Spacer(1, 0.45 * cm))
                    story.append(Paragraph("Note operative", self.styles['SectionHeading']))
                    notes_table = Table([["Operatore", "Nota"]] + note_rows, colWidths=[6 * cm, 18.8 * cm], repeatRows=1)
                    notes_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('TOPPADDING', (0, 0), (-1, -1), 5),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ]))
                    story.append(notes_table)
            else:
                story.append(Paragraph("Nessun operatore trovato per il sito selezionato.", self.styles['BodyText']))

            story.append(Spacer(1, 0.7 * cm))
            footer_text = f"Documento generato il {generated_at.strftime('%d/%m/%Y alle %H:%M')}"
            story.append(Paragraph(footer_text, self.styles['PageNum']))

            doc.build(story)

            buffer.seek(0)
            pdf_bytes = buffer.getvalue()
            buffer.close()
            return pdf_bytes

        except Exception as e:
            logger.error(f"Errore generazione PDF operatori: {e}")
            raise

    def _build_distribution_table(self, title: str, counts: Counter, empty_text: str) -> Table:
        rows = [[title, "N."]]
        if counts:
            rows.extend([[label, str(count)] for label, count in counts.most_common()])
        else:
            rows.append([empty_text, "-"])

        table = Table(rows, colWidths=[6.3 * cm, 1.5 * cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['accent']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['light_grey']]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table

    def _build_alert_table(self,
                           missing_contacts: List[Dict[str, Any]],
                           missing_role: List[Dict[str, Any]],
                           missing_specialization: List[Dict[str, Any]]) -> Table:
        rows = [
            ["Verifiche rapide", "N."],
            ["Senza contatto email/telefono", str(len(missing_contacts))],
            ["Senza ruolo", str(len(missing_role))],
            ["Senza specializzazione", str(len(missing_specialization))],
        ]

        if missing_contacts:
            names = ", ".join(self._format_operator_name(op) for op in missing_contacts[:4])
            if len(missing_contacts) > 4:
                names += f" +{len(missing_contacts) - 4}"
            rows.append([Paragraph(f"<font size='7'>Contatti da completare: {names}</font>", self.styles['BodyText']), ""])

        table = Table(rows, colWidths=[6.3 * cm, 1.5 * cm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), self.COLORS['header_bg']),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, self.COLORS['border']),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, self.COLORS['accent_light']]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        return table

    def _format_operator_choice(self, value: Optional[str]) -> str:
        if not value:
            return ""
        labels = {
            "responsabile_scavo": "Responsabile scavo",
            "assistente": "Assistente",
            "operatore": "Operatore",
            "specialista": "Specialista",
            "tecnico": "Tecnico",
            "ceramica": "Ceramica",
            "numismatica": "Numismatica",
            "antropologia": "Antropologia",
            "archeozoologia": "Archeozoologia",
            "topografia": "Topografia",
            "disegno": "Disegno",
            "fotografia": "Fotografia",
        }
        label = labels.get(value, str(value).replace("_", " ").capitalize())
        return self._pdf_text(label)

    def _format_operator_name(self, op: Dict[str, Any]) -> str:
        name = f"{op.get('cognome', '')} {op.get('nome', '')}".strip()
        return self._pdf_text(name or "Operatore senza nome")

    def _pdf_text(self, value: Any) -> str:
        return escape(str(value or "").strip()).replace("\n", "<br/>")

    def _safe_number(self, value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0

    def _format_number(self, value: float) -> str:
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.1f}"


# Istanza globale
_pdf_generator = GiornalePDFGeneratorV2()


def generate_giornale_pdf_quick(giornali: List[Dict[str, Any]],
                                cantiere_info: Dict[str, Any],
                                site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilitÃ  - Genera PDF rapidamente"""
    return _pdf_generator.generate_giornale_pdf(giornali, cantiere_info, site_info)

def generate_operatori_pdf_quick(operatori: List[Dict[str, Any]],
                               site_info: Dict[str, Any]) -> bytes:
    """Funzione di utilitÃ  - Genera PDF operatori rapidamente"""
    return _pdf_generator.generate_operatori_pdf(operatori, site_info)

