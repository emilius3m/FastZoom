# app/services/pdfplumber_extractor.py
"""
Servizio per estrazione tabelle e celle da PDF usando pdfplumber.
pdfplumber usa le linee native del PDF per rilevamento preciso delle celle.

Vantaggi rispetto a PPStructure:
- Coordinate celle precise (non basate su OCR)
- Supporto celle annidate
- Estrazione testo nativo (senza OCR)

Limitazioni:
- Non funziona bene con PDF scansionati (immagini)
- Richiede linee/bordi visibili nel PDF
"""

from typing import List, Dict, Any, Optional, Tuple
from loguru import logger

# Import condizionale per pdfplumber
try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False
    logger.warning("pdfplumber non disponibile. Installa con: pip install pdfplumber")


class PdfPlumberExtractor:
    """
    Estrae tabelle e celle da PDF usando pdfplumber.
    Fornisce coordinate precise basate sulle linee native del PDF.
    """
    
    def __init__(self):
        if not PDFPLUMBER_AVAILABLE:
            raise RuntimeError(
                "pdfplumber non installato. "
                "Installa con: pip install pdfplumber"
            )
    
    def extract_cells_from_pdf(
        self, 
        pdf_bytes: bytes,
        dpi: int = 150
    ) -> Dict[str, Any]:
        """
        Estrae celle da tutte le pagine del PDF.
        
        Args:
            pdf_bytes: Contenuto PDF come bytes
            dpi: DPI per calcolo scala (pdfplumber usa 72 DPI internamente)
            
        Returns:
            Dict con:
            - cells: lista di celle con coordinate
            - tables: lista di tabelle rilevate
            - pages: info per pagina
            - success: bool
            - method: 'pdfplumber'
        """
        import io
        
        result = {
            'cells': [],
            'tables': [],
            'pages': [],
            'success': False,
            'method': 'pdfplumber',
            'error': None
        }
        
        try:
            # Scala per convertire da 72 DPI (pdfplumber) a DPI target
            # Se usiamo zoom=2.5 in PyMuPDF, l'immagine è 2.5x più grande
            # pdfplumber usa coordinate a 72 DPI, quindi scala = DPI / 72
            scale = dpi / 72.0
            
            pdf_file = io.BytesIO(pdf_bytes)
            
            with pdfplumber.open(pdf_file) as pdf:
                y_offset = 0  # Offset Y cumulativo per multi-page
                
                for page_num, page in enumerate(pdf.pages):
                    page_width = page.width * scale
                    page_height = page.height * scale
                    
                    page_info = {
                        'page_number': page_num + 1,
                        'width': page_width,
                        'height': page_height,
                        'tables_count': 0,
                        'cells_count': 0,
                        'text_chars': len(page.chars) if hasattr(page, 'chars') else 0
                    }
                    
                    # Costruisci lista di linee esplicite da curves ed edges
                    explicit_lines = []
                    if hasattr(page, 'curves') and page.curves:
                        explicit_lines.extend(page.curves)
                    if hasattr(page, 'edges') and page.edges:
                        explicit_lines.extend(page.edges)
                    
                    # IMPOSTAZIONI CONSERVATIVE PER EVITARE OVER-SEGMENTAZIONE
                    # Usiamo "lines" per forzare pdfplumber a usare solo le linee di disegno
                    # e non a inferire tabelle dall'allineamento del testo.
                    table_settings = {
                        "vertical_strategy": "lines",      # SOLO linee di disegno reali
                        "horizontal_strategy": "lines",    # SOLO linee di disegno reali
                        "explicit_vertical_lines": explicit_lines,
                        "explicit_horizontal_lines": explicit_lines,
                        "snap_tolerance": 3,
                        "join_tolerance": 3,
                        "text_tolerance": 3,
                        "intersection_tolerance": 3,
                        "edge_min_length": 3,
                    }
                    
                    # Trova tabelle nella pagina con impostazioni conservative
                    tables = page.find_tables(table_settings=table_settings)
                    page_info['tables_count'] = len(tables)
                    
                    for table_idx, table in enumerate(tables):
                        # Aggiungi info tabella
                        table_bbox = tuple(c * scale for c in table.bbox)
                        result['tables'].append({
                            'table_index': table_idx,
                            'page': page_num,
                            'bbox': table_bbox,  # (x0, y0, x1, y1)
                            'rows_count': len(table.rows) if hasattr(table, 'rows') else 0,
                            'cells_count': len(table.cells) if hasattr(table, 'cells') else 0
                        })
                        
                        # Estrai celle della tabella
                        if hasattr(table, 'cells') and table.cells:
                            for cell_idx, cell_bbox in enumerate(table.cells):
                                # cell_bbox è (x0, y0, x1, y1)
                                if cell_bbox and len(cell_bbox) >= 4:
                                    # Scala e applica offset Y per multi-page
                                    scaled_cell = {
                                        'x1': cell_bbox[0] * scale,
                                        'y1': cell_bbox[1] * scale + y_offset,
                                        'x2': cell_bbox[2] * scale,
                                        'y2': cell_bbox[3] * scale + y_offset,
                                        'cell_index': cell_idx,
                                        'table_index': table_idx,
                                        'page': page_num,
                                        'source': 'pdfplumber'
                                    }
                                    result['cells'].append(scaled_cell)
                                    page_info['cells_count'] += 1
                    
                    result['pages'].append(page_info)
                    y_offset += page_height
                
                result['success'] = len(result['cells']) > 0
                
                if result['success']:
                    logger.info(
                        f"pdfplumber: rilevate {len(result['tables'])} tabelle, "
                        f"{len(result['cells'])} celle in {len(pdf.pages)} pagine (metodo conservativo)"
                    )
                    # Log per verificare se il numero di celle è ragionevole
                    if len(result['cells']) > 200:
                        logger.warning(
                            f"pdfplumber: rilevato un numero anomalo di celle ({len(result['cells'])}). "
                            "Potrebbero esserci ancora problemi di segmentazione."
                        )
                else:
                    logger.warning("pdfplumber: nessuna cella rilevata (PDF scansionato o layout non standard?)")
                    
        except Exception as e:
            logger.error(f"Errore pdfplumber: {e}")
            result['error'] = str(e)
            result['success'] = False
        
        return result
    
    def extract_text_in_region(
        self,
        pdf_bytes: bytes,
        page_num: int,
        bbox: Tuple[float, float, float, float],
        dpi: int = 150
    ) -> str:
        """
        Estrae testo nativo da una regione specifica del PDF.
        
        Args:
            pdf_bytes: Contenuto PDF
            page_num: Numero pagina (0-based)
            bbox: Bounding box (x0, y0, x1, y1) in coordinate scalate
            dpi: DPI usato per le coordinate
            
        Returns:
            Testo estratto dalla regione
        """
        import io
        
        scale = dpi / 72.0
        
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            
            with pdfplumber.open(pdf_file) as pdf:
                if page_num >= len(pdf.pages):
                    return ""
                
                page = pdf.pages[page_num]
                
                # Converti bbox da coordinate scalate a coordinate pdfplumber (72 DPI)
                x0 = bbox[0] / scale
                y0 = bbox[1] / scale
                x1 = bbox[2] / scale
                y1 = bbox[3] / scale
                
                # Crop e estrai testo
                cropped = page.within_bbox((x0, y0, x1, y1))
                text = cropped.extract_text() or ""
                
                return text.strip()
                
        except Exception as e:
            logger.error(f"Errore estrazione testo pdfplumber: {e}")
            return ""
    
    def get_all_chars_with_positions(
        self,
        pdf_bytes: bytes,
        dpi: int = 150
    ) -> List[Dict[str, Any]]:
        """
        Estrae tutti i caratteri con le loro posizioni.
        Utile per debug e visualizzazione.
        
        Args:
            pdf_bytes: Contenuto PDF
            dpi: DPI per scaling
            
        Returns:
            Lista di dict con 'text', 'x0', 'y0', 'x1', 'y1', 'page'
        """
        import io
        
        chars = []
        scale = dpi / 72.0
        
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            
            with pdfplumber.open(pdf_file) as pdf:
                y_offset = 0
                
                for page_num, page in enumerate(pdf.pages):
                    page_height = page.height * scale
                    
                    for char in page.chars:
                        chars.append({
                            'text': char.get('text', ''),
                            'x0': char.get('x0', 0) * scale,
                            'y0': char.get('top', 0) * scale + y_offset,
                            'x1': char.get('x1', 0) * scale,
                            'y1': char.get('bottom', 0) * scale + y_offset,
                            'page': page_num,
                            'fontname': char.get('fontname', ''),
                            'size': char.get('size', 0)
                        })
                    
                    y_offset += page_height
                    
        except Exception as e:
            logger.error(f"Errore lettura caratteri pdfplumber: {e}")
        
        return chars


# Singleton
_pdfplumber_extractor: Optional[PdfPlumberExtractor] = None


def get_pdfplumber_extractor() -> Optional[PdfPlumberExtractor]:
    """
    Factory per PdfPlumberExtractor.
    Ritorna None se pdfplumber non è disponibile.
    """
    global _pdfplumber_extractor
    
    if not PDFPLUMBER_AVAILABLE:
        return None
    
    if _pdfplumber_extractor is None:
        try:
            _pdfplumber_extractor = PdfPlumberExtractor()
        except Exception as e:
            logger.error(f"Impossibile inizializzare PdfPlumberExtractor: {e}")
            return None
    
    return _pdfplumber_extractor


def is_pdfplumber_available() -> bool:
    """Verifica se pdfplumber è disponibile."""
    return PDFPLUMBER_AVAILABLE
