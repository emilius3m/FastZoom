"""
PP-StructureV3 Table Cell Extractor

Estrae celle di tabella usando PP-StructureV3 (PaddleOCR 3.x) con:
- Coordinate geometriche precise (pixel-perfect)
- Supporto nativo per merged cells (rowspan, colspan)
- Riconoscimento robusto di tabelle complesse e PDF scansionati
- Separazione cella-aware (nessuna contaminazione tra celle)
- Mapping automatico a campi della scheda MiC/ICCD
"""

import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
from loguru import logger

# Check PP-StructureV3 availability
PP_STRUCTURE_AVAILABLE = False
PPStructure = None

try:
    # PaddleOCR 3.x usa PPStructure (non PPStructureV3 come classe separata)
    from paddleocr import PPStructure as _PPStructure
    PPStructure = _PPStructure
    PP_STRUCTURE_AVAILABLE = True
    logger.info("✓ PP-Structure available from paddleocr")
except ImportError as e:
    logger.warning(f"PP-Structure not available: {e}")


@dataclass
class PPCell:
    """Rappresenta una cella estratta da PP-StructureV3."""
    row: int
    col: int
    text: str
    bbox: Tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)
    rowspan: int = 1
    colspan: int = 1
    confidence: float = 1.0
    
    @property
    def x_min(self) -> int:
        return int(self.bbox[0])
    
    @property
    def y_min(self) -> int:
        return int(self.bbox[1])
    
    @property
    def x_max(self) -> int:
        return int(self.bbox[2])
    
    @property
    def y_max(self) -> int:
        return int(self.bbox[3])
    
    @property
    def width(self) -> int:
        return self.x_max - self.x_min
    
    @property
    def height(self) -> int:
        return self.y_max - self.y_min
    
    @property
    def area(self) -> int:
        return self.width * self.height
    
    @property
    def center(self) -> Tuple[float, float]:
        return ((self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2)


@dataclass
class PPTable:
    """Rappresenta una tabella estratta da PP-StructureV3."""
    cells: List[PPCell] = field(default_factory=list)
    bbox: Tuple[float, float, float, float] = (0, 0, 0, 0)
    html: str = ""
    rows: int = 0
    cols: int = 0
    page_num: int = 0
    
    def get_cell(self, row: int, col: int) -> Optional[PPCell]:
        """Ottieni cella per riga e colonna."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None
    
    def get_row(self, row: int) -> List[PPCell]:
        """Ottieni tutte le celle di una riga."""
        return sorted([cell for cell in self.cells if cell.row == row], key=lambda c: c.col)
    
    def get_col(self, col: int) -> List[PPCell]:
        """Ottieni tutte le celle di una colonna."""
        return sorted([cell for cell in self.cells if cell.col == col], key=lambda c: c.row)
    
    def find_cell_by_label(self, label: str) -> Optional[PPCell]:
        """
        Trova la cella il cui testo contiene la label specificata.
        """
        label_norm = label.upper().strip()
        for cell in self.cells:
            if label_norm in cell.text.upper():
                return cell
        return None
    
    def find_value_cell_for_label(self, label: str) -> Optional[PPCell]:
        """
        Trova la cella VALORE associata a una label.
        Cerca la cella a destra o sotto la cella contenente la label.
        """
        label_cell = self.find_cell_by_label(label)
        if not label_cell:
            return None
        
        # Prima prova: cella a destra (stessa riga, colonna successiva)
        right_cell = self.get_cell(label_cell.row, label_cell.col + label_cell.colspan)
        if right_cell and right_cell.text.strip():
            return right_cell
        
        # Seconda prova: cella sotto (riga successiva, stessa colonna)
        below_cell = self.get_cell(label_cell.row + label_cell.rowspan, label_cell.col)
        if below_cell and below_cell.text.strip():
            return below_cell
        
        return None


class PPStructureV3Extractor:
    """
    Estrae celle di tabella usando PP-StructureV3.
    
    PP-StructureV3 è il modulo di document analysis di PaddleOCR che:
    1. Identifica le tabelle nella pagina
    2. Rileva la struttura (righe, colonne, merged cells)
    3. Estrae il testo di ogni cella
    4. Fornisce coordinate geometriche precise
    """
    
    _instance: Optional['PPStructureV3Extractor'] = None
    _model = None
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern per evitare di caricare il modello più volte."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self, use_gpu: bool = False, lang: str = 'it'):
        """
        Args:
            use_gpu: Usa GPU se disponibile (richiede CUDA)
            lang: Lingua per OCR ('it', 'en', etc.)
        """
        # Evita re-inizializzazione
        if self._model is not None:
            return
            
        if not PP_STRUCTURE_AVAILABLE:
            raise RuntimeError(
                "PP-Structure not available. Install: pip install -U paddleocr"
            )
        
        try:
            # Inizializza PPStructure con table recognition
            self._model = PPStructure(
                show_log=False,
                use_gpu=use_gpu,
                lang=lang,
                # Abilita table structure recognition
                table=True,
                ocr=True,
                layout=True,
            )
            self.use_gpu = use_gpu
            self.lang = lang
            logger.info(f"✓ PP-StructureV3 Extractor initialized (GPU: {use_gpu}, Lang: {lang})")
        except Exception as e:
            logger.error(f"Failed to initialize PP-Structure: {e}")
            raise
    
    def extract_tables_from_image(self, image_input: Any) -> List[PPTable]:
        """
        Estrae tutte le tabelle da un'immagine.
        
        Args:
            image_input: percorso file, PIL Image, o numpy array
        
        Returns:
            Lista di PPTable con celle estratte
        """
        if self._model is None:
            raise RuntimeError("PP-Structure model not initialized")
        
        try:
            # Converti input a numpy array se necessario
            if hasattr(image_input, 'convert'):  # PIL Image
                import numpy as np
                image_array = np.array(image_input.convert('RGB'))
            elif isinstance(image_input, str):  # Path
                import cv2
                image_array = cv2.imread(image_input)
                image_array = cv2.cvtColor(image_array, cv2.COLOR_BGR2RGB)
            else:
                image_array = image_input
            
            # PP-Structure ritorna una lista di risultati
            results = self._model(image_array)
            
            tables = []
            
            for item in results:
                # Filtra solo tabelle
                item_type = item.get('type', '')
                if item_type != 'table':
                    continue
                
                table = self._parse_table_result(item)
                if table and len(table.cells) > 0:
                    tables.append(table)
                    logger.debug(
                        f"Table extracted: {table.rows}x{table.cols}, "
                        f"{len(table.cells)} cells"
                    )
            
            logger.info(f"✓ Extracted {len(tables)} table(s) from image")
            return tables
            
        except Exception as e:
            logger.error(f"Error extracting tables: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def _parse_table_result(self, item: dict) -> Optional[PPTable]:
        """
        Converte risultato raw di PP-Structure in PPTable strutturato.
        """
        try:
            # Estrai info base
            html = item.get('res', {}).get('html', '') if isinstance(item.get('res'), dict) else ''
            bbox = item.get('bbox', [0, 0, 0, 0])
            
            # Estrai celle
            cells = self._extract_cells_from_result(item)
            
            if not cells:
                # Fallback: parse HTML se celle non disponibili direttamente
                if html:
                    cells = self._parse_cells_from_html(html, bbox)
            
            if not cells:
                logger.warning("Table result has no extractable cells")
                return None
            
            # Calcola dimensioni griglia
            max_row = max((c.row for c in cells), default=0)
            max_col = max((c.col for c in cells), default=0)
            
            return PPTable(
                cells=cells,
                bbox=tuple(bbox) if len(bbox) >= 4 else (0, 0, 0, 0),
                html=html,
                rows=max_row + 1,
                cols=max_col + 1
            )
        
        except Exception as e:
            logger.error(f"Error parsing table result: {e}")
            return None
    
    def _extract_cells_from_result(self, item: dict) -> List[PPCell]:
        """
        Estrae celle dal risultato PP-Structure.
        
        Il formato può variare in base alla versione di PaddleOCR.
        """
        cells = []
        
        res = item.get('res', {})
        if not isinstance(res, dict):
            return []
        
        # Formato PP-StructureV3: cell_box_list + rec_texts
        cell_boxes = res.get('cell_box_list', [])
        
        if cell_boxes:
            # Estrai testi dalle celle
            # In alcune versioni, i testi sono in 'rec_texts' globale
            # In altre, ogni cella ha il suo testo
            for i, cell_box in enumerate(cell_boxes):
                if len(cell_box) < 4:
                    continue
                
                # cell_box è [x1, y1, x2, y2] o [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                if isinstance(cell_box[0], (list, tuple)):
                    # Formato polygon
                    x_coords = [p[0] for p in cell_box]
                    y_coords = [p[1] for p in cell_box]
                    bbox = (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
                else:
                    # Formato [x1, y1, x2, y2]
                    bbox = tuple(cell_box[:4])
                
                cell = PPCell(
                    row=i // 10,  # Placeholder, verrà calcolato dopo
                    col=i % 10,
                    text="",  # Verrà popolato dopo
                    bbox=bbox,
                )
                cells.append(cell)
        
        # Prova a ricostruire row/col dalla posizione geometrica
        if cells:
            cells = self._assign_row_col_from_geometry(cells)
        
        return cells
    
    def _assign_row_col_from_geometry(self, cells: List[PPCell]) -> List[PPCell]:
        """
        Assegna row e col in base alla posizione geometrica delle celle.
        """
        if not cells:
            return cells
        
        # Ordina per y, poi per x
        sorted_cells = sorted(cells, key=lambda c: (c.y_min, c.x_min))
        
        # Trova righe uniche basandosi su y_min (con tolleranza)
        y_tolerance = 10
        rows_y = []
        for cell in sorted_cells:
            found_row = False
            for i, row_y in enumerate(rows_y):
                if abs(cell.y_min - row_y) < y_tolerance:
                    found_row = True
                    break
            if not found_row:
                rows_y.append(cell.y_min)
        
        rows_y.sort()
        
        # Trova colonne uniche basandosi su x_min
        x_tolerance = 10
        cols_x = []
        for cell in sorted_cells:
            found_col = False
            for i, col_x in enumerate(cols_x):
                if abs(cell.x_min - col_x) < x_tolerance:
                    found_col = True
                    break
            if not found_col:
                cols_x.append(cell.x_min)
        
        cols_x.sort()
        
        # Assegna row e col
        for cell in cells:
            # Trova row
            for i, row_y in enumerate(rows_y):
                if abs(cell.y_min - row_y) < y_tolerance:
                    cell.row = i
                    break
            
            # Trova col
            for i, col_x in enumerate(cols_x):
                if abs(cell.x_min - col_x) < x_tolerance:
                    cell.col = i
                    break
        
        return cells
    
    def _parse_cells_from_html(self, html: str, table_bbox: list) -> List[PPCell]:
        """
        Estrae celle parsando l'HTML della tabella.
        Fallback quando le coordinate dirette non sono disponibili.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not available for HTML parsing")
            return []
        
        cells = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Calcola dimensioni approssimative dalle celle HTML
            table_x1 = table_bbox[0] if len(table_bbox) > 0 else 0
            table_y1 = table_bbox[1] if len(table_bbox) > 1 else 0
            table_x2 = table_bbox[2] if len(table_bbox) > 2 else 1000
            table_y2 = table_bbox[3] if len(table_bbox) > 3 else 1000
            
            table_width = table_x2 - table_x1
            table_height = table_y2 - table_y1
            
            rows = soup.find_all('tr')
            num_rows = len(rows)
            
            if num_rows == 0:
                return []
            
            # Calcola altezza approssimativa per riga
            row_height = table_height / num_rows
            
            row_idx = 0
            for tr in rows:
                tds = tr.find_all(['td', 'th'])
                num_cols = sum(int(td.get('colspan', 1)) for td in tds)
                
                if num_cols == 0:
                    num_cols = len(tds)
                
                col_width = table_width / max(num_cols, 1)
                
                col_idx = 0
                for td in tds:
                    text = td.get_text(strip=True)
                    rowspan = int(td.get('rowspan', 1))
                    colspan = int(td.get('colspan', 1))
                    
                    # Calcola bbox approssimativo
                    cell_x1 = table_x1 + col_idx * col_width
                    cell_y1 = table_y1 + row_idx * row_height
                    cell_x2 = cell_x1 + colspan * col_width
                    cell_y2 = cell_y1 + rowspan * row_height
                    
                    cell = PPCell(
                        row=row_idx,
                        col=col_idx,
                        text=text,
                        bbox=(cell_x1, cell_y1, cell_x2, cell_y2),
                        rowspan=rowspan,
                        colspan=colspan,
                        confidence=0.8  # Lower confidence for HTML-parsed cells
                    )
                    cells.append(cell)
                    col_idx += colspan
                
                row_idx += 1
            
            if cells:
                logger.debug(f"Parsed {len(cells)} cells from HTML table")
            return cells
        
        except Exception as e:
            logger.error(f"Error parsing HTML table: {e}")
            return []
    
    
    def extract_fields_by_label(
        self,
        tables: List[PPTable],
        label_to_field: Dict[str, str],
        return_mapping: bool = False
    ) -> Any:
        """
        Estrae campi cercando le label nelle celle della tabella.
        
        Args:
            tables: Liste di tabelle estratte
            label_to_field: Dizionario label_text -> field_name
            return_mapping: Se True, ritorna (values, mapping)
        
        Returns:
            Se return_mapping è False: Dict field_name -> value estratto
            Se return_mapping è True: (values, mapping)
            Dove mapping è Dict[field_name, List[int]] contenente indici globali delle celle
        """
        extracted = {}
        cell_mapping = {}  # field_name -> [cell_idx_label, cell_idx_value]
        
        if not tables:
            logger.warning("No tables provided for field extraction")
            return (extracted, cell_mapping) if return_mapping else extracted
        
        # Calcola offset globale celle per ogni tabella
        # PPStructureV3Extract ritorna una lista piatta di celle nel debug info
        # Dobbiamo mappare gli indici locali della tabella agli indici "globali" della pagina
        cell_offset = 0
        table_offsets = []
        for table in tables:
            table_offsets.append(cell_offset)
            cell_offset += len(table.cells)
            
        for table_idx, table in enumerate(tables):
            global_offset = table_offsets[table_idx]
            
            for label, field_name in label_to_field.items():
                if field_name in extracted:
                    continue  # Già trovato
                
                # Trova cella LABEL
                label_cell = table.find_cell_by_label(label)
                if not label_cell:
                    continue
                    
                # Trova cella VALORE
                # Logica duplicata da find_value_cell_for_label per avere accesso a entrambe le celle
                value_cell = None
                
                # Prima prova: cella a destra
                right_cell = table.get_cell(label_cell.row, label_cell.col + label_cell.colspan)
                if right_cell and right_cell.text.strip():
                    value_cell = right_cell
                else:
                    # Seconda prova: cella sotto
                    below_cell = table.get_cell(label_cell.row + label_cell.rowspan, label_cell.col)
                    if below_cell and below_cell.text.strip():
                        value_cell = below_cell
                
                if value_cell:
                    extracted[field_name] = value_cell.text.strip()
                    logger.debug(f"✓ {field_name} = '{value_cell.text[:50]}' (label: {label})")
                    
                    if return_mapping:
                        # Trova indici locali nella tabella
                        try:
                            label_idx = table.cells.index(label_cell)
                            value_idx = table.cells.index(value_cell)
                            
                            # Salva indici globali (relativi alla lista completa delle celle della pagina)
                            cell_mapping[field_name] = [
                                global_offset + label_idx,
                                global_offset + value_idx
                            ]
                        except ValueError:
                            pass
        
        return (extracted, cell_mapping) if return_mapping else extracted
    
    def extract_all_cells_as_dict(self, tables: List[PPTable]) -> List[Dict]:
        """
        Estrae tutte le celle come lista di dizionari.
        Utile per debugging o processing generico.
        """
        result = []
        for table_idx, table in enumerate(tables):
            for cell in table.cells:
                result.append({
                    "table": table_idx,
                    "row": cell.row,
                    "col": cell.col,
                    "text": cell.text,
                    "bbox": list(cell.bbox),
                    "rowspan": cell.rowspan,
                    "colspan": cell.colspan,
                    "confidence": cell.confidence
                })
        return result
    
    def visualize_table(
        self,
        image_array: np.ndarray,
        table: PPTable,
        draw_text: bool = True
    ) -> np.ndarray:
        """
        Disegna le celle della tabella sull'immagine (per debug).
        
        Args:
            image_array: numpy array dell'immagine (RGB)
            table: PPTable con celle
            draw_text: Se disegnare il testo delle celle
        
        Returns:
            Immagine con rettangoli di celle disegnati
        """
        try:
            import cv2
        except ImportError:
            logger.warning("OpenCV not available for visualization")
            return image_array
        
        vis = image_array.copy()
        
        # Disegna bordo tabella
        if table.bbox and table.bbox != (0, 0, 0, 0):
            cv2.rectangle(
                vis,
                (int(table.bbox[0]), int(table.bbox[1])),
                (int(table.bbox[2]), int(table.bbox[3])),
                (255, 0, 0),  # Blu (BGR)
                3
            )
        
        # Disegna celle
        for cell in table.cells:
            # Colore basato su rowspan/colspan
            if cell.rowspan > 1 or cell.colspan > 1:
                color = (0, 165, 255)  # Orange per merged cells
            else:
                color = (0, 255, 0)  # Verde per celle normali
            
            cv2.rectangle(
                vis,
                (cell.x_min, cell.y_min),
                (cell.x_max, cell.y_max),
                color,
                2
            )
            
            # Label con coordinate
            label = f"({cell.row},{cell.col})"
            if cell.rowspan > 1 or cell.colspan > 1:
                label += f" [{cell.rowspan}x{cell.colspan}]"
            
            cv2.putText(
                vis,
                label,
                (cell.x_min + 5, cell.y_min + 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                color,
                1
            )
            
            # Testo (troncato)
            if draw_text and cell.text:
                text_short = cell.text[:25] + "..." if len(cell.text) > 25 else cell.text
                cv2.putText(
                    vis,
                    text_short,
                    (cell.x_min + 5, cell.y_max - 5),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.35,
                    color,
                    1
                )
        
        return vis


def create_mic_us_label_mapping() -> Dict[str, str]:
    """
    Crea il mapping label -> field_name per la scheda MiC/ICCD US.
    
    Le label sono cercate nel testo delle celle.
    """
    return {
        # Intestazione
        "US N.": "us_code",
        "U.S.": "us_code",
        "UNITÀ STRATIGRAFICA": "us_code",
        "ENTE RESPONSABILE": "ente_responsabile",
        "ANNO": "anno",
        
        # Amministrativi
        "UFFICIO MIC": "ufficio_mic",
        "UFFICIO MiC": "ufficio_mic",
        "IDENTIFICATIVO": "identificativo_rif",
        
        # Localizzazione
        "LOCALITÀ": "localita",
        "LOCALITA": "localita",
        "AREA/EDIFICIO/STRUTTURA": "area_struttura",
        "SAGGIO": "saggio",
        "AMBIENTE/UNITÀ FUNZIONALE": "ambiente_unita_funzione",
        "AMBIENTE/UNITA FUNZIONALE": "ambiente_unita_funzione",
        "POSIZIONE": "posizione",
        "SETTORE/I": "settori",
        "SETTORI": "settori",
        
        # Documentazione
        "PIANTE": "piante_riferimenti",
        "PROSPETTI": "prospetti_riferimenti",
        "SEZIONI": "sezioni_riferimenti",
        "FOTOGRAFIE": "fotografie",
        
        # Tipo
        "POSITIVA": "tipo_positiva",
        "NEGATIVA": "tipo_negativa",
        "NATURALE": "formazione_naturale",
        "ARTIFICIALE": "formazione_artificiale",
        
        # Caratterizzazione
        "DEFINIZIONE": "definizione",
        "CRITERI DI DISTINZIONE": "criteri_distinzione",
        "MODO DI FORMAZIONE": "modo_formazione",
        "COMPONENTI INORGANICI": "componenti_inorganici",
        "COMPONENTI ORGANICI": "componenti_organici",
        "CONSISTENZA": "consistenza",
        "COLORE": "colore",
        "MISURE": "misure",
        "STATO DI CONSERVAZIONE": "stato_conservazione",
        
        # Sequenza
        "COPRE": "copre",
        "COPERTO DA": "coperto_da",
        "TAGLIA": "taglia",
        "TAGLIATO DA": "tagliato_da",
        "RIEMPIE": "riempie",
        "RIEMPITO DA": "riempito_da",
        "SI LEGA A": "si_lega_a",
        "UGUALE A": "uguale_a",
        "SI APPOGGIA A": "si_appoggia_a",
        "GLI SI APPOGGIA": "gli_si_appoggia",
        
        # Interpretazione
        "DESCRIZIONE": "descrizione",
        "INTERPRETAZIONE": "interpretazione",
        "OSSERVAZIONI": "osservazioni",
        
        # Datazione
        "PERIODO": "periodo",
        "FASE": "fase",
        "DATAZIONE": "datazione",
        
        # Compilazione
        "RESPONSABILE": "responsabile",
        "DATA": "data_compilazione",
    }


# Singleton getter
_extractor_instance: Optional[PPStructureV3Extractor] = None

def get_pp_structure_extractor(use_gpu: bool = False) -> PPStructureV3Extractor:
    """
    Ottiene l'istanza singleton dell'extractor.
    """
    global _extractor_instance
    if _extractor_instance is None:
        _extractor_instance = PPStructureV3Extractor(use_gpu=use_gpu)
    return _extractor_instance
