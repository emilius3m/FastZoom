"""
app/services/tma_export_service.py

Servizio export Schede TMA ICCD 3.00
- PDF (reportlab) conforme al layout ministeriale ICCD
- Word (.docx, python-docx) conforme al layout ministeriale ICCD
"""

import io
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable
from loguru import logger

try:
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False
    logger.warning("python-docx non disponibile per export Word TMA")


# ═══════════════════════════════════════════════
#  COLORI CONDIVISI
# ═══════════════════════════════════════════════
_PDF_COLORS = {
    'header_bg': colors.HexColor('#1a3a52'),
    'accent': colors.HexColor('#2c5aa0'),
    'accent_light': colors.HexColor('#e8eef5'),
    'border': colors.HexColor('#4a7ba7'),
    'text': colors.HexColor('#1a1a1a'),
    'grey': colors.HexColor('#666666'),
    'light_grey': colors.HexColor('#f5f5f5'),
    'section_bg': colors.HexColor('#edf2f7'),
}

_WORD_COLORS = {
    'header_bg': RGBColor(26, 58, 82),
    'accent': RGBColor(44, 90, 160),
    'text': RGBColor(26, 26, 26),
    'grey': RGBColor(100, 100, 100),
}


# ═══════════════════════════════════════════════
#  HELPER – sezioni ICCD dal dict
# ═══════════════════════════════════════════════

def _iccd_sections(s: Dict[str, Any]) -> List[dict]:
    """
    Restituisce la lista ordinata di sezioni ICCD,
    ciascuna con titolo + lista di (etichetta, valore).
    """
    sections: List[dict] = []

    # --- CD - CODICI ---
    sections.append({
        'title': 'CD - CODICI',
        'fields': [
            ('TSK - Tipo Scheda', s.get('tsk', 'TMA')),
            ('LIR - Livello ricerca', s.get('lir', 'I')),
        ],
        'subsections': [{
            'title': 'NCT - CODICE UNIVOCO',
            'fields': [
                ('NCTR - Codice regione', s.get('nctr', '')),
                ('NCTN - Numero catalogo generale', s.get('nctn', '')),
            ],
        }],
        'extra_fields': [
            ('ESC - Ente schedatore', s.get('esc', '')),
            ('ECP - Ente competente', s.get('ecp', '')),
        ],
    })

    # --- OG - OGGETTO ---
    sections.append({
        'title': 'OG - OGGETTO',
        'subsections': [{
            'title': 'OGT - OGGETTO',
            'fields': [
                ('OGTD - Definizione', s.get('ogtd', '')),
                ('OGTM - Definizione materiale componente', s.get('ogtm', '')),
            ],
        }],
    })

    # --- LC - LOCALIZZAZIONE ---
    sections.append({
        'title': 'LC - LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA',
        'subsections': [{
            'title': 'PVC - LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA ATTUALE',
            'fields': [
                ('PVCS - Stato', s.get('pvcs', 'ITALIA')),
                ('PVCR - Regione', s.get('pvcr', '')),
                ('PVCP - Provincia', s.get('pvcp', '')),
                ('PVCC - Comune', s.get('pvcc', '')),
            ],
        }],
    })

    # --- LDC - COLLOCAZIONE SPECIFICA ---
    ldc_fields = []
    if s.get('ldct'): ldc_fields.append(('LDCT - Tipologia', s['ldct']))
    if s.get('ldcn'): ldc_fields.append(('LDCN - Denominazione attuale', s['ldcn']))
    if s.get('ldcu'): ldc_fields.append(('LDCU - Indirizzo', s['ldcu']))
    if s.get('ldcs'): ldc_fields.append(('LDCS - Specifiche e note', s['ldcs']))
    if ldc_fields:
        sections.append({
            'title': 'LDC - COLLOCAZIONE SPECIFICA',
            'fields': ldc_fields,
        })

    # --- LA - ALTRE LOCALIZZAZIONI ---
    altre_loc = s.get('altre_localizzazioni') or []
    for loc in altre_loc:
        la_fields = []
        if loc.get('tcl'):  la_fields.append(('TCL - Tipo di localizzazione', loc['tcl']))
        la_sub_fields = []
        for k, lbl in [('prvs', 'PRVS - Stato'), ('prvr', 'PRVR - Regione'),
                        ('prvp', 'PRVP - Provincia'), ('prvc', 'PRVC - Comune')]:
            v = loc.get(k)
            if v: la_sub_fields.append((lbl, v))
        prc_fields = []
        if loc.get('prcu'): prc_fields.append(('PRCU - Denominazione', loc['prcu']))

        sec = {'title': 'LA - ALTRE LOCALIZZAZIONI GEOGRAFICO-AMMINISTRATIVE', 'fields': la_fields}
        subs = []
        if la_sub_fields:
            subs.append({'title': 'PRV - LOCALIZZAZIONE GEOGRAFICO-AMMINISTRATIVA', 'fields': la_sub_fields})
        if prc_fields:
            subs.append({'title': 'PRC - COLLOCAZIONE SPECIFICA', 'fields': prc_fields})
        if subs:
            sec['subsections'] = subs
        sections.append(sec)

    # --- RE / DSC - DATI DI SCAVO ---
    dsc_fields = []
    for k, lbl in [('scan', 'SCAN - Denominazione dello scavo'),
                    ('dscf', 'DSCF - Ente responsabile'),
                    ('dsca', 'DSCA - Responsabile scientifico'),
                    ('dsct', 'DSCT - Motivo'),
                    ('dscm', 'DSCM - Metodo'),
                    ('dscd', 'DSCD - Data'),
                    ('dscu', 'DSCU - Unità Stratigrafica'),
                    ('dscn', 'DSCN - Specifiche')]:
        v = s.get(k)
        if v: dsc_fields.append((lbl, v))
    if dsc_fields:
        sections.append({
            'title': "RE - MODALITA' DI REPERIMENTO",
            'subsections': [{
                'title': 'DSC - DATI DI SCAVO',
                'fields': dsc_fields,
            }],
        })

    # --- DT - CRONOLOGIA ---
    dt_fields = [('DTZG - Fascia cronologica di riferimento', s.get('dtzg', ''))]
    dtm = s.get('dtm') or []
    if dtm:
        dt_fields.append(('DTM - Motivazione cronologia', ', '.join(dtm)))
    sections.append({
        'title': 'DT - CRONOLOGIA',
        'subsections': [{
            'title': 'DTZ - CRONOLOGIA GENERICA',
            'fields': dt_fields,
        }],
    })

    # --- DA - DATI ANALITICI ---
    if s.get('nsc'):
        sections.append({
            'title': 'DA - DATI ANALITICI',
            'fields': [('NSC - Notizie storico-critiche', s['nsc'])],
        })

    # --- MA - MATERIALE (repeating) ---
    materiali = s.get('materiali') or []
    for mat in materiali:
        ma_fields = []
        for k, lbl in [('macc', 'MACC - Categoria'), ('macl', 'MACL - Classe'),
                        ('macd', 'MACD - Definizione'), ('macp', 'MACP - Precisazione tipologica'),
                        ('macq', 'MACQ - Quantità'), ('mas', 'MAS - Specifiche')]:
            v = mat.get(k)
            if v is not None and str(v).strip():
                ma_fields.append((lbl, str(v)))
        sections.append({
            'title': 'MA - MATERIALE',
            'subsections': [{
                'title': 'MAC - MATERIALE COMPONENTE',
                'fields': ma_fields,
            }],
        })

    # --- TU - CONDIZIONE GIURIDICA ---
    sections.append({
        'title': 'TU - CONDIZIONE GIURIDICA E VINCOLI',
        'subsections': [{
            'title': 'CDG - CONDIZIONE GIURIDICA',
            'fields': [('CDGG - Indicazione generica', s.get('cdgg', ''))],
        }],
    })

    # --- DO - FONTI E DOCUMENTI ---
    fotografie = s.get('fotografie') or []
    if fotografie:
        fta_subs = []
        for foto in fotografie:
            fta_fields = []
            if foto.get('ftax'): fta_fields.append(('FTAX - Genere', foto['ftax']))
            if foto.get('ftap'): fta_fields.append(('FTAP - Tipo', foto['ftap']))
            if foto.get('ftan'): fta_fields.append(('FTAN - Codice identificativo', foto['ftan']))
            if fta_fields:
                fta_subs.append({'title': 'FTA - DOCUMENTAZIONE FOTOGRAFICA', 'fields': fta_fields})
        if fta_subs:
            sections.append({
                'title': 'DO - FONTI E DOCUMENTI DI RIFERIMENTO',
                'subsections': fta_subs,
            })

    # --- AD - ACCESSO AI DATI ---
    ad_fields = [('ADSP - Profilo di accesso', str(s.get('adsp', 2)))]
    if s.get('adsm'):
        ad_fields.append(('ADSM - Motivazione', s['adsm']))
    sections.append({
        'title': 'AD - ACCESSO AI DATI',
        'subsections': [{
            'title': 'ADS - SPECIFICHE DI ACCESSO AI DATI',
            'fields': ad_fields,
        }],
    })

    # --- CM - COMPILAZIONE ---
    cm_fields = [('CMPD - Data', s.get('cmpd', ''))]
    cmpn = s.get('cmpn') or []
    for nome in cmpn:
        cm_fields.append(('CMPN - Nome', nome))
    fur = s.get('fur') or []
    for nome in fur:
        cm_fields.append(('FUR - Funzionario responsabile', nome))
    sections.append({
        'title': 'CM - COMPILAZIONE',
        'subsections': [{
            'title': 'CMP - COMPILAZIONE',
            'fields': cm_fields,
        }],
    })

    return sections


# ═══════════════════════════════════════════════
#  PDF EXPORT (reportlab)
# ═══════════════════════════════════════════════

def _setup_pdf_styles():
    styles = getSampleStyleSheet()

    def add_or_update(name, **kw):
        if name in styles.byName:
            for k, v in kw.items():
                setattr(styles[name], k, v)
        else:
            styles.add(ParagraphStyle(name=name, **kw))

    add_or_update('TmaTitle', parent=styles['Heading1'],
                  fontSize=16, textColor=_PDF_COLORS['header_bg'],
                  alignment=TA_CENTER, fontName='Helvetica-Bold',
                  spaceAfter=4, spaceBefore=4)

    add_or_update('TmaSubtitle', parent=styles['Normal'],
                  fontSize=10, textColor=_PDF_COLORS['grey'],
                  alignment=TA_CENTER, fontName='Helvetica-Oblique',
                  spaceAfter=8)

    add_or_update('TmaSectionHeading', parent=styles['Normal'],
                  fontSize=10, textColor=colors.white,
                  fontName='Helvetica-Bold', spaceAfter=2, spaceBefore=8,
                  backColor=_PDF_COLORS['accent'], leftIndent=4,
                  rightIndent=4, leading=14)

    add_or_update('TmaSubsection', parent=styles['Normal'],
                  fontSize=9, textColor=_PDF_COLORS['header_bg'],
                  fontName='Helvetica-Bold', spaceAfter=2, spaceBefore=4,
                  leftIndent=8, leading=12)

    add_or_update('TmaLabel', parent=styles['Normal'],
                  fontSize=8, fontName='Helvetica-Bold',
                  textColor=_PDF_COLORS['header_bg'], spaceAfter=1, leading=10)

    add_or_update('TmaValue', parent=styles['Normal'],
                  fontSize=9, fontName='Helvetica',
                  textColor=_PDF_COLORS['text'], spaceAfter=3,
                  alignment=TA_JUSTIFY, leading=11, leftIndent=8)

    add_or_update('TmaPageNum', parent=styles['Normal'],
                  fontSize=7, textColor=_PDF_COLORS['grey'],
                  alignment=TA_CENTER, fontName='Helvetica-Oblique')

    add_or_update('TmaFooter', parent=styles['Normal'],
                  fontSize=7, textColor=_PDF_COLORS['grey'],
                  alignment=TA_CENTER, fontName='Helvetica-Oblique',
                  spaceBefore=12)

    return styles


def _add_pdf_header_footer(canvas, doc):
    """Aggiunge header e footer su ogni pagina."""
    canvas.saveState()
    # Footer
    canvas.setFont('Helvetica-Oblique', 7)
    canvas.setFillColor(_PDF_COLORS['grey'])
    canvas.drawCentredString(
        doc.pagesize[0] / 2, 1 * cm,
        f"Pagina {canvas.getPageNumber()} — Scheda TMA ICCD 3.00 — FastZoom Archaeological System"
    )
    canvas.restoreState()


def generate_tma_pdf(scheda: Dict[str, Any]) -> bytes:
    """
    Genera PDF conforme ICCD per una scheda TMA.
    Riceve il dict serializzato (SchedaTMARead-like).
    """
    styles = _setup_pdf_styles()
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Scheda TMA — NCT {scheda.get('nctr', '')}{scheda.get('nctn', '')}",
    )

    story: list = []

    # Titolo
    story.append(Paragraph("SCHEDA TMA", styles['TmaTitle']))
    story.append(Paragraph("Tabella Materiali Archeologici — ICCD 3.00", styles['TmaSubtitle']))
    story.append(HRFlowable(width="100%", thickness=1.5, color=_PDF_COLORS['accent']))
    story.append(Spacer(1, 0.4 * cm))

    # Sezioni ICCD
    for sec in _iccd_sections(scheda):
        # Intestazione sezione
        story.append(Paragraph(sec['title'], styles['TmaSectionHeading']))

        # Campi diretti della sezione
        for label, value in sec.get('fields', []):
            story.append(Paragraph(label, styles['TmaLabel']))
            story.append(Paragraph(str(value), styles['TmaValue']))

        # Extra fields (usati per ESC/ECP dopo NCT)
        for label, value in sec.get('extra_fields', []):
            story.append(Paragraph(label, styles['TmaLabel']))
            story.append(Paragraph(str(value), styles['TmaValue']))

        # Sottosezioni
        for sub in sec.get('subsections', []):
            story.append(Paragraph(sub['title'], styles['TmaSubsection']))
            for label, value in sub.get('fields', []):
                story.append(Paragraph(label, styles['TmaLabel']))
                story.append(Paragraph(str(value), styles['TmaValue']))

        story.append(Spacer(1, 0.15 * cm))

    # Footer / Firma
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=_PDF_COLORS['border']))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph("Firma", styles['TmaLabel']))
    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        f"Documento generato da FastZoom Archaeological System — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        styles['TmaFooter'],
    ))

    doc.build(story, onFirstPage=_add_pdf_header_footer, onLaterPages=_add_pdf_header_footer)
    buffer.seek(0)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    logger.info(f"✓ TMA PDF generato: NCT {scheda.get('nctr','')}{scheda.get('nctn','')} ({len(pdf_bytes)} bytes)")
    return pdf_bytes


# ═══════════════════════════════════════════════
#  WORD EXPORT (python-docx)
# ═══════════════════════════════════════════════

def _add_word_section_heading(doc, text: str):
    """Sezione principale con sfondo blu per Word."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(10)
    run.font.bold = True
    run.font.color.rgb = _WORD_COLORS['accent']
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)


def _add_word_subsection_heading(doc, text: str):
    """Sotto-sezione ICCD."""
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.font.size = Pt(9)
    run.font.bold = True
    run.font.color.rgb = _WORD_COLORS['header_bg']
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Cm(0.5)


def _add_word_field(doc, label: str, value: str):
    """Un campo etichetta+valore su due righe."""
    p = doc.add_paragraph()
    label_run = p.add_run(label)
    label_run.font.size = Pt(8)
    label_run.font.bold = True
    label_run.font.color.rgb = _WORD_COLORS['header_bg']

    p2 = doc.add_paragraph()
    val_run = p2.add_run(str(value))
    val_run.font.size = Pt(9)
    val_run.font.color.rgb = _WORD_COLORS['text']
    p2.paragraph_format.left_indent = Cm(0.5)
    p2.paragraph_format.space_after = Pt(2)


def generate_tma_word(scheda: Dict[str, Any]) -> bytes:
    """
    Genera documento Word (.docx) conforme ICCD per una scheda TMA.
    Riceve il dict serializzato (SchedaTMARead-like).
    """
    if not DOCX_AVAILABLE:
        raise ImportError("python-docx non installato")

    doc = Document()

    # Margini
    for section in doc.sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2)
        section.right_margin = Cm(2)

    # Titolo
    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = title.add_run("SCHEDA TMA")
    run.font.size = Pt(18)
    run.font.bold = True
    run.font.color.rgb = _WORD_COLORS['header_bg']

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub_run = subtitle.add_run("Tabella Materiali Archeologici — ICCD 3.00")
    sub_run.font.size = Pt(10)
    sub_run.font.italic = True
    sub_run.font.color.rgb = _WORD_COLORS['grey']

    doc.add_paragraph()  # spacer

    # Sezioni ICCD
    for sec in _iccd_sections(scheda):
        _add_word_section_heading(doc, sec['title'])

        for label, value in sec.get('fields', []):
            _add_word_field(doc, label, value)

        for label, value in sec.get('extra_fields', []):
            _add_word_field(doc, label, value)

        for sub in sec.get('subsections', []):
            _add_word_subsection_heading(doc, sub['title'])
            for label, value in sub.get('fields', []):
                _add_word_field(doc, label, value)

    # Firma
    doc.add_paragraph()
    firma = doc.add_paragraph()
    firma_run = firma.add_run("Firma")
    firma_run.font.size = Pt(9)
    firma_run.font.bold = True

    doc.add_paragraph()
    doc.add_paragraph()

    # Footer
    footer = doc.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run(
        f"Documento generato da FastZoom Archaeological System — {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    footer_run.font.size = Pt(7)
    footer_run.font.italic = True
    footer_run.font.color.rgb = _WORD_COLORS['grey']

    # Salva
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    word_bytes = buf.getvalue()
    buf.close()
    logger.info(f"✓ TMA Word generato: NCT {scheda.get('nctr','')}{scheda.get('nctn','')} ({len(word_bytes)} bytes)")
    return word_bytes
