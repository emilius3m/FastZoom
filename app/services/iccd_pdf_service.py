
"""Servizio per generazione PDF schede ICCD conformi agli standard ministeriali."""

import io
import json
from datetime import datetime
from typing import Dict, Any, Optional
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import black, blue, grey
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.platypus.flowables import HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from loguru import logger

from app.models.iccd_records import ICCDRecord


class ICCDPDFGenerator:
    """Generatore PDF per schede ICCD secondo layout standard ministeriale."""
    
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Configura stili personalizzati per PDF ICCD."""
        
        # Stile intestazione principale
        self.styles.add(ParagraphStyle(
            name='ICCDTitle',
            parent=self.styles['Title'],
            fontSize=16,
            spaceAfter=12,
            textColor=black,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        # Stile sezioni ICCD
        self.styles.add(ParagraphStyle(
            name='ICCDSection',
            parent=self.styles['Heading2'],
            fontSize=12,
            spaceAfter=6,
            spaceBefore=12,
            textColor=blue,
            fontName='Helvetica-Bold',
            leftIndent=0
        ))
        
        # Stile campi ICCD
        self.styles.add(ParagraphStyle(
            name='ICCDField',
            parent=self.styles['Normal'],
            fontSize=9,
            spaceAfter=3,
            fontName='Helvetica',
            leftIndent=5*mm
        ))
        
        # Stile valori ICCD
        self.styles.add(ParagraphStyle(
            name='ICCDValue',
            parent=self.styles['Normal'],
            fontSize=10,
            spaceAfter=6,
            fontName='Helvetica-Bold',
            leftIndent=5*mm
        ))
        
        # Stile codice NCT
        self.styles.add(ParagraphStyle(
            name='NCTCode',
            parent=self.styles['Normal'],
            fontSize=14,
            spaceAfter=12,
            spaceBefore=6,
            fontName='Helvetica-Bold',
            alignment=TA_CENTER,
            borderWidth=1,
            borderColor=black
        ))
        
        # Stile note piccole
        self.styles.add(ParagraphStyle(
            name='ICCDFootnote',
            parent=self.styles['Normal'],
            fontSize=8,
            textColor=grey,
            fontName='Helvetica-Oblique'
        ))
    
    def generate_iccd_pdf(self, iccd_record: ICCDRecord, site_name: str = "") -> bytes:
        """
        Genera PDF scheda ICCD secondo standard ministeriale.
        
        Args:
            iccd_record: Record ICCD da convertire in PDF
            site_name: Nome del sito archeologico
            
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
                topMargin=2*cm,
                bottomMargin=2*cm,
                leftMargin=2*cm,
                rightMargin=2*cm,
                title=f"Scheda ICCD {iccd_record.schema_type} - {iccd_record.get_nct()}"
            )
            
            # Contenuto PDF
            story = []
            
            # Intestazione ministeriale
            self._add_header(story, iccd_record, site_name)
            
            # Codice NCT prominente
            self._add_nct_section(story, iccd_record)
            
            # Sezioni ICCD
            self._add_iccd_sections(story, iccd_record)
            
            # Footer con validazione
            self._add_footer(story, iccd_record)
            
            # Genera PDF
            doc.build(story)
            
            # Ritorna contenuto
            buffer.seek(0)
            pdf_content = buffer.getvalue()
            buffer.close()
            
            logger.info(f"Generated ICCD PDF for record {iccd_record.get_nct()}: {len(pdf_content)} bytes")
            
            return pdf_content
            
        except Exception as e:
            logger.error(f"Error generating ICCD PDF: {e}")
            raise
    
    def _add_header(self, story, iccd_record: ICCDRecord, site_name: str):
        """Aggiunge intestazione ministeriale al PDF."""
        
        # Logo/Header ministeriale
        header_data = [
            ["MINISTERO DELLA CULTURA", ""],
            ["Direzione Generale Archeologia, Belle Arti e Paesaggio", ""],
            ["Soprintendenza Speciale per i Beni Archeologici di Roma", ""],
            ["", f"Scheda {iccd_record.schema_type} - {iccd_record.get_level_display()}"]
        ]
        
        header_table = Table(header_data, colWidths=[12*cm, 6*cm])
        header_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (0, 2), 10),
            ('FONTSIZE', (1, 3), (1, 3), 12),
            ('FONTNAME', (1, 3), (1, 3), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ]))
        
        story.append(header_table)
        story.append(Spacer(1, 12))
        
        # Titolo scheda
        schema_names = {
            'RA': 'REPERTO ARCHEOLOGICO',
            'CA': 'COMPLESSO ARCHEOLOGICO', 
            'SI': 'SITO ARCHEOLOGICO'
        }
        title = f"SCHEDA {iccd_record.schema_type} - {schema_names.get(iccd_record.schema_type, 'BENE CULTURALE')}"
        story.append(Paragraph(title, self.styles['ICCDTitle']))
        
        # Informazioni sito
        if site_name:
            story.append(Paragraph(f"<b>Sito:</b> {site_name}", self.styles['ICCDField']))
        
        story.append(Spacer(1, 12))
        story.append(HRFlowable(width="100%", thickness=1, color=black))
        story.append(Spacer(1, 12))
    
    def _add_nct_section(self, story, iccd_record: ICCDRecord):
        """Aggiunge sezione codice NCT prominente."""
        
        nct_data = [
            ["CODICE UNIVOCO NAZIONALE (NCT)", iccd_record.get_nct()],
            ["Ente Schedatore", iccd_record.cataloging_institution],
            ["Data Creazione", iccd_record.creation_date.strftime("%d/%m/%Y") if iccd_record.creation_date else ""],
            ["Status", iccd_record.get_status_display()]
        ]
        
        nct_table = Table(nct_data, colWidths=[8*cm, 10*cm])
        nct_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), grey),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (1, 0), (1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 1, black),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))

        story.append(nct_table)
        story.append(Spacer(1, 12))
    
    def _add_iccd_sections(self, story, iccd_record: ICCDRecord):
        """Aggiunge sezioni ICCD strutturate al PDF."""
        
        iccd_data = iccd_record.iccd_data
        
        # Sezioni in ordine standard ICCD
        sections_order = ["CD", "OG", "LC", "DT", "MT", "DA", "AU", "NS", "RS"]
        section_names = {
            "CD": "CODICI",
            "OG": "OGGETTO",
            "LC": "LOCALIZZAZIONE",
            "DT": "CRONOLOGIA", 
            "MT": "DATI TECNICI",
            "DA": "DATI ANALITICI",
            "AU": "DEFINIZIONE CULTURALE",
            "NS": "NOTIZIE STORICHE",
            "RS": "FONTI E DOCUMENTI"
        }
        
        for section_code in sections_order:
            if section_code in iccd_data and iccd_data[section_code]:
                section_data = iccd_data[section_code]
                section_name = section_names.get(section_code, section_code)
                
                # Intestazione sezione
                story.append(Paragraph(f"{section_code} - {section_name}", self.styles['ICCDSection']))
                
                # Contenuto sezione
                self._add_section_content(story, section_code, section_data)
                
                story.append(Spacer(1, 8))
    
    def _add_section_content(self, story, section_code: str, section_data: Dict[str, Any]):
        """Aggiunge contenuto di una specifica sezione ICCD."""
        
        if section_code == "CD":
            self._add_cd_content(story, section_data)
        elif section_code == "OG":
            self._add_og_content(story, section_data)
        elif section_code == "LC":
            self._add_lc_content(story, section_data)
        elif section_code == "DT":
            self._add_dt_content(story, section_data)
        elif section_code == "MT":
            self._add_mt_content(story, section_data)
        elif section_code == "DA":
            self._add_da_content(story, section_data)
        else:
            # Sezione generica
            self._add_generic_section_content(story, section_data)
    
    def _add_cd_content(self, story, cd_data: Dict[str, Any]):
        """Aggiunge contenuto sezione CD - CODICI."""
        
        if "NCT" in cd_data:
            nct = cd_data["NCT"]
            story.append(Paragraph("<b>Codice Univoco NCT:</b>", self.styles['ICCDField']))
            story.append(Paragraph(f"NCTR: {nct.get('NCTR', '')} | NCTN: {nct.get('NCTN', '')} | NCTS: {nct.get('NCTS', '')}", self.styles['ICCDValue']))
        
        if "ESC" in cd_data:
            story.append(Paragraph("<b>Ente Schedatore:</b>", self.styles['ICCDField']))
            story.append(Paragraph(cd_data["ESC"], self.styles['ICCDValue']))
    
    def _add_og_content(self, story, og_data: Dict[str, Any]):
        """Aggiunge contenuto sezione OG - OGGETTO."""
        
        if "OGT" in og_data:
            ogt = og_data["OGT"]
            
            if "OGTD" in ogt:
                story.append(Paragraph("<b>Definizione:</b>", self.styles['ICCDField']))
                story.append(Paragraph(ogt["OGTD"], self.styles['ICCDValue']))
            
            if "OGTT" in ogt:
                story.append(Paragraph("<b>Tipologia:</b>", self.styles['ICCDField']))
                story.append(Paragraph(ogt["OGTT"], self.styles['ICCDValue']))
    
    def _add_lc_content(self, story, lc_data: Dict[str, Any]):
        """Aggiunge contenuto sezione LC - LOCALIZZAZIONE."""
        
        if "PVC" in lc_data:
            pvc = lc_data["PVC"]
            location_parts = []
            
            if pvc.get("PVCC"): location_parts.append(pvc["PVCC"])
            if pvc.get("PVCP"): location_parts.append(f"({pvc['PVCP']})")
            if pvc.get("PVCR"): location_parts.append(pvc["PVCR"])
            if pvc.get("PVCS"): location_parts.append(pvc["PVCS"])
            
            if location_parts:
                story.append(Paragraph("<b>Localizzazione:</b>", self.styles['ICCDField']))
                story.append(Paragraph(", ".join(location_parts), self.styles['ICCDValue']))
        
        if "PVL" in lc_data and "PVLN" in lc_data["PVL"]:
            story.append(Paragraph("<b>Denominazione Specifica:</b>", self.styles['ICCDField']))
            story.append(Paragraph(lc_data["PVL"]["PVLN"], self.styles['ICCDValue']))
    
    def _add_dt_content(self, story, dt_data: Dict[str, Any]):
        """Aggiunge contenuto sezione DT - CRONOLOGIA."""
        
        if "DTS" in dt_data:
            dts = dt_data["DTS"]
            chronology_parts = []
            
            if dts.get("DTSI"): chronology_parts.append(dts["DTSI"])
            if dts.get("DTSF") and dts["DTSF"] != dts.get("DTSI"):
                chronology_parts.append(f"- {dts['DTSF']}")
            if dts.get("DTSV"): chronology_parts.append(f"({dts['DTSV']})")
            
            if chronology_parts:
                story.append(Paragraph("<b>Cronologia:</b>", self.styles['ICCDField']))
                story.append(Paragraph(" ".join(chronology_parts), self.styles['ICCDValue']))
    
    def _add_mt_content(self, story, mt_data: Dict[str, Any]):
        """Aggiunge contenuto sezione MT - DATI TECNICI."""
        
        if "MTC" in mt_data:
            mtc = mt_data["MTC"]
            
            if "MTCM" in mtc:
                story.append(Paragraph("<b>Materia:</b>", self.styles['ICCDField']))
                materials = mtc["MTCM"]
                if isinstance(materials, list):
                    story.append(Paragraph(", ".join(materials), self.styles['ICCDValue']))
                else:
                    story.append(Paragraph(str(materials), self.styles['ICCDValue']))
        
        if "MIS" in mt_data:
            mis = mt_data["MIS"]
            measurements = []
            
            if mis.get("MISA"): measurements.append(f"Alt: {mis['MISA']} cm")
            if mis.get("MISL"): measurements.append(f"Larg: {mis['MISL']} cm")
            if mis.get("MISP"): measurements.append(f"Prof: {mis['MISP']} cm")
            if mis.get("MISD"): measurements.append(f"Diam: {mis['MISD']} cm")
            
            if measurements:
                story.append(Paragraph("<b>Misure:</b>", self.styles['ICCDField']))
                story.append(Paragraph(" | ".join(measurements), self.styles['ICCDValue']))
    
    def _add_da_content(self, story, da_data: Dict[str, Any]):
        """Aggiunge contenuto sezione DA - DATI ANALITICI."""
        
        if "DES" in da_data and "DESO" in da_data["DES"]:
            story.append(Paragraph("<b>Descrizione Oggetto:</b>", self.styles['ICCDField']))
            story.append(Paragraph(da_data["DES"]["DESO"], self.styles['ICCDValue']))
        
        if "STC" in da_data and "STCC" in da_data["STC"]:
            story.append(Paragraph("<b>Stato di Conservazione:</b>", self.styles['ICCDField']))
            story.append(Paragraph(da_data["STC"]["STCC"].title(), self.styles['ICCDValue']))
    
    def _add_generic_section_content(self, story, section_data: Dict[str, Any]):
        """Aggiunge contenuto generico per sezioni non specificamente gestite."""
        
        for key, value in section_data.items():
            if isinstance(value, dict):
                story.append(Paragraph(f"<b>{key}:</b>", self.styles['ICCDField']))
                for subkey, subvalue in value.items():
                    if subvalue:
                        story.append(Paragraph(f"  {subkey}: {subvalue}", self.styles['ICCDValue']))
            elif value:
                story.append(Paragraph(f"<b>{key}:</b> {value}", self.styles['ICCDField']))
    
    def _add_footer(self, story, iccd_record: ICCDRecord):
        """Aggiunge footer con informazioni di validazione."""
        
        story.append(Spacer(1, 24))
        story.append(HRFlowable(width="100%", thickness=1, color=grey))
        story.append(Spacer(1, 12))
        
        # Informazioni validazione
        validation_data = [
            ["Status Scheda:", iccd_record.get_status_display()],
            ["Validata:", "Sì" if iccd_record.is_validated else "No"],
            ["Data Validazione:", iccd_record.validation_date.strftime("%d/%m/%Y %H:%M") if iccd_record.validation_date else "N/D"],
            ["Ultima Modifica:", iccd_record.updated_at.strftime("%d/%m/%Y %H:%M") if iccd_record.updated_at else "N/D"]
        ]
        
        validation_table = Table(validation_data, colWidths=[4*cm, 6*cm])
        validation_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        
        story.append(validation_table)
        story.append(Spacer(1, 12))
        
        # Footer ministeriale
        footer_text = f"Scheda generata dal Sistema Archeologico FastZoom - Conforme Standard ICCD 4.00 - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        story.append(Paragraph(footer_text, self.styles['ICCDFootnote']))


# Istanza globale del generatore
iccd_pdf_generator = ICCDPDFGenerator()

# Funzione di utilità per generazione rapida
def generate_iccd_pdf_quick(iccd_record: ICCDRecord, site_name: str = "") -> bytes:
    """Funzione di utilità per generazione rapida PDF ICCD."""
    return iccd_pdf_generator.generate_iccd_pdf(iccd_record, site_name)