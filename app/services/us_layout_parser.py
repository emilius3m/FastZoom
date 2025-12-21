# app/services/us_layout_parser.py
"""
Parser layout-aware per schede US: usa SOLO bounding boxes PPStructure per estrarre i campi.
Nessun fallback euristico.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


@dataclass(frozen=True)
class Rect:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def h(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def cx(self) -> float:
        return (self.x1 + self.x2) / 2.0

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2.0

    def expand(self, px: float) -> "Rect":
        return Rect(self.x1 - px, self.y1 - px, self.x2 + px, self.y2 + px)

    def contains_point(self, x: float, y: float) -> bool:
        return self.x1 <= x <= self.x2 and self.y1 <= y <= self.y2

    def y_overlap_ratio(self, other: "Rect") -> float:
        inter = max(0.0, min(self.y2, other.y2) - max(self.y1, other.y1))
        denom = max(self.h, other.h, 1e-6)
        return inter / denom

    def overlaps(self, other: "Rect") -> bool:
        """Verifica se questo rettangolo si sovrappone con un altro."""
        if self.x2 < other.x1 or self.x1 > other.x2:
            return False
        if self.y2 < other.y1 or self.y1 > other.y2:
            return False
        return True


def _norm(s: str) -> str:
    """Normalizza per confronti label: uppercase, no accenti, spazi compressi, punteggiatura ridotta."""
    if not s:
        return ""
    s = ''.join(ch for ch in s if unicodedata.category(ch)[0] != 'C')
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = s.replace("'", "'").replace(""", '"').replace(""", '"')
    s = re.sub(r"[^A-Z0-9/.\\s'\\-]+", " ", s)
    s = re.sub(r"\\s+", " ", s).strip()
    return s


def _bbox_to_rect(bbox: Any) -> Optional[Rect]:
    """
    bbox può essere:
    - lista di 4 punti [[x,y], [x,y], [x,y], [x,y]] (polygon from PaddleOCR)
    - lista piatta [x1,y1,x2,y2,...] (fallback)
    """
    if bbox is None:
        return None
    try:
        if isinstance(bbox, dict):
            bbox = bbox.get('polygon', bbox)
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and isinstance(bbox[0], (list, tuple)):
            xs = [float(p[0]) for p in bbox]
            ys = [float(p[1]) for p in bbox]
            return Rect(min(xs), min(ys), max(xs), max(ys))
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4 and all(isinstance(v, (int, float)) for v in bbox[:4]):
            x1, y1, x2, y2 = map(float, bbox[:4])
            return Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    except Exception:
        return None
    return None


class USLayoutParser:
    """
    Parser layout-aware: usa SOLO PPStructure cells per estrarre i campi.
    Nessun fallback euristico. Se mancano celle PPStructure, il campo sarà None.
    """

    # Label "core" (normalizzate) + alias tipici OCR
    LABELS = {
        "US": ["US"],
        "ENTE RESPONSABILE": ["ENTE RESPONSABILE"],
        "UFFICIO MIC": [
            "UFFICIO MIC COMPETENTE PER TUTELA", "UFFICIO MiC COMPETENTE PER TUTELA",
            "UFFICIO MIC COMPETENTE", "UFFICIO MiC COMPETENTE",
            "COMPETENTE PER TUTELA", "UFFICIO COMPETENTE"
        ],
        "ANNO": ["ANNO"],
        "IDENTIFICATIVO": [
            "IDENTIFICATIVO DEL SAGGIO STRATIGRAFICO/DELL'EDIFICIO/DELLA STRUTTURA/DELLA DEPOSIZIONE FUNERARIA DI RIFERIMENTO",
        ],
        "LOCALITA": ["LOCALITA", "LOCALITÀ"],
        "AREA/EDIFICIO/STRUTTURA": ["AREA/EDIFICIO/STRUTTURA"],
        "SAGGIO": ["SAGGIO"],
        "AMBIENTE/UNITA FUNZIONALE": ["AMBIENTE/UNITA FUNZIONALE", "AMBIENTE/UNITÀ FUNZIONALE"],
        "POSIZIONE": ["POSIZIONE"],
        "SETTORE/I": ["SETTORE/I", "SETTORI", "SETTORE"],
        "QUADRATO/I": ["QUADRATO/I", "QUADRATI", "QUADRATO"],
        "DEFINIZIONE": ["DEFINIZIONE"],
        "POSITIVA": ["POSITIVA"],
        "NEGATIVA": ["NEGATIVA"],
        "NATURALE": ["NATURALE"],
        "ARTIFICIALE": ["ARTIFICIALE"],
        "QUOTE": ["QUOTE"],
        "PIANTE": ["PIANTE"],
        "PROSPETTI": ["PROSPETTI"],
        "SEZIONI": ["SEZIONI"],
        "FOTOGRAFIE": ["FOTOGRAFIE"],
        "RIFERIMENTI TABELLE MATERIALI": [
            "RIFERIMENTI TABELLE MATERIALI", "RIFERIMENTITABELLEMATERIALI",
            "RIFERIMENTI TABELLE", "TABELLE MATERIALI", "RIF TABELLE MATERIALI"
        ],
        "CONSISTENZA": ["CONSISTENZA"],
        "COLORE": ["COLORE"],
        "MISURE": ["MISURE"],
        "STATO DI CONSERVAZIONE": ["STATO DI CONSERVAZIONE"],
        "CRITERI DISTINZIONE": ["CRITERI DISTINZIONE", "CRITERI DI DISTINZIONE"],
        "MODO FORMAZIONE": ["MODO FORMAZIONE", "MODO DI FORMAZIONE"],
        "COMPONENTI INORGANICI": ["INORGANICI", "COMPONENTI INORGANICI"],
        "COMPONENTI ORGANICI": ["ORGANICI", "COMPONENTI ORGANICI"],
        "DESCRIZIONE": ["DESCRIZIONE"],
        "OSSERVAZIONI": ["OSSERVAZIONI"],
        "INTERPRETAZIONE": ["INTERPRETAZIONE"],
        "DATAZIONE": ["DATAZIONE"],
        "PERIODO": ["PERIODO"],
        "FASE": ["FASE"],
        "ATTIVITA": ["ATTIVITA", "ATTIVITÀ"],
        "ELEMENTI DATANTI": ["ELEMENTI DATANTI"],
        "DATI QUANTITATIVI DEI REPERTI": ["DATI QUANTITATIVI DEI REPERTI", "DATI QUANTITATIVI REPERTI"],
        "CAMPIONATURE": ["CAMPIONATURE"],
        "FLOTTAZIONE": ["FLOTTAZIONE"],
        "SETACCIATURA": ["SETACCIATURA"],
        "AFFIDABILITA STRATIGRAFICA": ["AFFIDABILITA STRATIGRAFICA", "AFFIDABILITÀ STRATIGRAFICA"],
        "RESPONSABILE SCIENTIFICO": [
            "RESPONSABILE SCIENTIFICO", "RESPONSABILE SCIENTIFICO DELLE INDAGINI",
            "RESPONSABILE SCIENTIFICO INDAGINI", "RESP SCIENTIFICO",
            "RESPONSABILESCIENTIFICO", "RESPONSABILE SCIENTIFICODELLE INDAGINI",
            "RESPONSABILE SCIENTIFICODELLEINDAGINI", "SCIENTIFICO DELLE INDAGINI"
        ],
        "DATA RILEVAMENTO": ["DATA RILEVAMENTO", "DATA RILEVAMENTO SUL CAMPO", "DATA DEL RILEVAMENTO"],
        "RESPONSABILE COMPILAZIONE": [
            "RESPONSABILE COMPILAZIONE", "RESPONSABILE COMPILAZIONE SUL CAMPO",
            "RESPONSABILE COMPILAZIONESUL CAMPO", "RESPONSABILECOMPILAZIONE",
            "RESP COMPILAZIONE", "COMPILAZIONE SUL CAMPO"
        ],
        "DATA RIELABORAZIONE": ["DATA RIELABORAZIONE", "DATA DELLA RIELABORAZIONE"],
        "RESPONSABILE RIELABORAZIONE": [
            "RESPONSABILE RIELABORAZIONE", "RESPONSABILERIELABORAZIONE",
            "RESP RIELABORAZIONE", "RESPONSABILE DELLA RIELABORAZIONE"
        ],
        "SI LEGA A": ["SI LEGA A"],
        "UGUALE A": ["UGUALE A"],
        "COPRE": ["COPRE"],
        "COPERTO DA": ["COPERTO DA"],
        "RIEMPIE": ["RIEMPIE"],
        "RIEMPITO DA": ["RIEMPITO DA"],
        "TAGLIA": ["TAGLIA"],
        "TAGLIATO DA": ["TAGLIATO DA"],
        "SI APPOGGIA A": ["SI APPOGGIA A"],
        "GLI SI APPOGGIA": ["GLI SI APPOGGIA"],
        "POSTERIORE A": ["POSTERIORE A"],
        "ANTERIORE A": ["ANTERIORE A"],
    }

    def parse_core(
        self,
        items: List[Dict[str, Any]],
        *,
        site_id: str,
        page_size: Tuple[int, int],
        detected_cells: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        items: lista come prodotta dal PaddleOCRService.bounding_boxes
        page_size: (width, height) dell'immagine renderizzata
        detected_cells: celle rilevate da PPStructure
        """
        tokens = self._to_tokens(items)
        w, h = page_size

        # Valida che PPStructure cells siano presenti
        self._detected_cells: List[Rect] = []
        self._cell_metadata: List[Dict[str, Any]] = []

        if not detected_cells:
            logger.warning("No PPStructure cells provided. Fields will be None.")
            # Prosegui comunque ma i campi cell-based saranno vuoti
        else:
            for c in detected_cells:
                self._detected_cells.append(Rect(
                    float(c.get('x1', 0)),
                    float(c.get('y1', 0)),
                    float(c.get('x2', 0)),
                    float(c.get('y2', 0))
                ))
                self._cell_metadata.append({
                    'cell_index': c.get('cell_index'),
                    'table_index': c.get('table_index'),
                    'page': c.get('page'),
                })

            # Filtra celle annidate
            original_count = len(self._detected_cells)
            self._detected_cells = self._filter_nested_cells(self._detected_cells)
            filtered_count = original_count - len(self._detected_cells)
            if filtered_count > 0:
                logger.info(f"Filtered {filtered_count} nested cells (kept {len(self._detected_cells)} of {original_count})")
            else:
                logger.info(f"Using {len(self._detected_cells)} PPStructure cells for extraction")

        # Trova label rect per campo
        label_rects: Dict[str, Rect] = {}
        for key, aliases in self.LABELS.items():
            found = self._find_label(tokens, aliases)
            if found:
                label_rects[key] = found

        out: Dict[str, Any] = {"site_id": site_id}
        _bboxes: Dict[str, Dict[str, float]] = {}

        # 1) US (us_code)
        us_num = self._extract_us_number(tokens, label_rects.get("US"), page_w=w, page_h=h)
        if us_num:
            out["us_code"] = f"US{us_num.zfill(3)}"

        # 2) ENTE RESPONSABILE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "ENTE RESPONSABILE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ente_responsabile"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ente_responsabile"] = bbox

        # 2b) UFFICIO MIC - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "UFFICIO MIC", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ufficio_mic"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ufficio_mic"] = bbox

        # 3) ANNO - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "ANNO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            match = re.search(r"\b(19|20)\d{2}\b", val)
            if match:
                out["anno"] = int(match.group(0))
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["anno"] = bbox

        # 4) IDENTIFICATIVO - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "IDENTIFICATIVO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["identificativo_rif"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["identificativo_rif"] = bbox

        # 5) LOCALITA - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "LOCALITA", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["localita"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["localita"] = bbox

        # 6) AREA/EDIFICIO/STRUTTURA - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "AREA/EDIFICIO/STRUTTURA", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["area_struttura"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["area_struttura"] = bbox

        # 7) SAGGIO - PPStructure ONLY con validazione lunghezza
        result = self._extract_value_in_cell(tokens, "SAGGIO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            if len(val) < 100:
                out["saggio"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["saggio"] = bbox
                logger.info(f"SAGGIO extracted: '{val}'")
            else:
                logger.warning(f"SAGGIO: rejected too long value ({len(val)} chars)")
        else:
            logger.debug("SAGGIO: no value found (no PPStructure cell or empty)")

        # 8) AMBIENTE/UNITA FUNZIONALE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "AMBIENTE/UNITA FUNZIONALE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ambiente_unita_funzione"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ambiente_unita_funzione"] = bbox

        # 9) POSIZIONE - PPStructure ONLY
        if "POSIZIONE" in label_rects:
            result = self._extract_value_in_cell(tokens, "POSIZIONE", label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out["posizione"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["posizione"] = bbox

        # 10) DEFINIZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DEFINIZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["definizione"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["definizione"] = bbox

        # SETTORE/I - PPStructure ONLY
        if "SETTORE/I" in label_rects:
            result = self._extract_value_in_cell(tokens, "SETTORE/I", label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out["settori"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["settori"] = bbox

        # QUADRATO/I - PPStructure ONLY
        if "QUADRATO/I" in label_rects:
            result = self._extract_value_in_cell(tokens, "QUADRATO/I", label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out["quadrati"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["quadrati"] = bbox

        # 11) TIPO (checkbox POSITIVA/NEGATIVA)
        tipo = self._extract_tipo_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if tipo:
            out["tipo"] = tipo

        # 12) NATURALE/ARTIFICIALE (checkbox)
        nat_art = self._extract_nat_art_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if nat_art:
            out["formazione"] = nat_art

        # 13) QUOTE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "QUOTE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["quote"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["quote"] = bbox
            quote_nums = re.findall(r"\d+[,.]?\d*", val)
            if quote_nums:
                out["quote_list"] = [float(q.replace(",", ".")) for q in quote_nums[:3]]

        # 14) DOCUMENTAZIONE - PPStructure ONLY
        for label_key, field_key in [("PIANTE", "piante_riferimenti"), ("PROSPETTI", "prospetti_riferimenti"),
                                     ("SEZIONI", "sezioni_riferimenti"), ("FOTOGRAFIE", "fotografie"),
                                     ("RIFERIMENTI TABELLE MATERIALI", "riferimenti_tabelle_materiali")]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, _ = result
                out[field_key] = val

        # 15) STATO DI CONSERVAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "STATO DI CONSERVAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["stato_conservazione"] = val

        # 16) COMPONENTI - PPStructure ONLY
        for label_key, field_key in [("COMPONENTI INORGANICI", "componenti_inorganici"),
                                     ("COMPONENTI ORGANICI", "componenti_organici")]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, _ = result
                out[field_key] = val

        # 17) CRITERI DISTINZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "CRITERI DISTINZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["criteri_distinzione"] = val

        # 18) MODO FORMAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "MODO FORMAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["modo_formazione"] = val

        # 19) DESCRIZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DESCRIZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["descrizione"] = val

        # 20) OSSERVAZIONI - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "OSSERVAZIONI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["osservazioni"] = val

        # 21) INTERPRETAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "INTERPRETAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["interpretazione"] = val

        # 22) DATAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DATAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["datazione"] = val

        # 23) PERIODO - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "PERIODO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["periodo"] = val

        # 24) FASE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "FASE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["fase"] = val

        # 25) ATTIVITA - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "ATTIVITA", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["attivita"] = val

        # 26) ELEMENTI DATANTI - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "ELEMENTI DATANTI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["elementi_datanti"] = val

        # 27) DATI QUANTITATIVI REPERTI - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DATI QUANTITATIVI DEI REPERTI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["dati_quantitativi_reperti"] = val

        # 28) CAMPIONATURE, FLOTTAZIONE, SETACCIATURA - PPStructure ONLY
        for label_key, field_key in [("CAMPIONATURE", "campionature"), ("FLOTTAZIONE", "flottazione"),
                                     ("SETACCIATURA", "setacciatura")]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, _ = result
                out[field_key] = val

        # 29) AFFIDABILITA STRATIGRAFICA - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "AFFIDABILITA STRATIGRAFICA", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["affidabilita_stratigrafica"] = val.lower()

        # 30) RESPONSABILE SCIENTIFICO - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "RESPONSABILE SCIENTIFICO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_scientifico"] = val

        # 31) DATA RILEVAMENTO - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DATA RILEVAMENTO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            match = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", val)
            if match:
                iso_date = self._parse_date_to_iso(match.group(0))
                if iso_date:
                    out["data_rilevamento"] = iso_date

        # 32) RESPONSABILE COMPILAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "RESPONSABILE COMPILAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_compilazione"] = val

        # 33) DATA RIELABORAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "DATA RIELABORAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            match = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", val)
            if match:
                iso_date = self._parse_date_to_iso(match.group(0))
                if iso_date:
                    out["data_rielaborazione"] = iso_date

        # 34) RESPONSABILE RIELABORAZIONE - PPStructure ONLY
        result = self._extract_value_in_cell(tokens, "RESPONSABILE RIELABORAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_rielaborazione"] = val

        # 35) Sequenza stratigrafica - PPStructure ONLY
        for label_key, field_name in [
            ("SI LEGA A", "seq_si_lega_a"), ("UGUALE A", "seq_uguale_a"), ("COPRE", "seq_copre"),
            ("COPERTO DA", "seq_coperto_da"), ("RIEMPIE", "seq_riempie"), ("RIEMPITO DA", "seq_riempito_da"),
            ("TAGLIA", "seq_taglia"), ("TAGLIATO DA", "seq_tagliato_da"), ("SI APPOGGIA A", "seq_si_appoggia_a"),
            ("GLI SI APPOGGIA", "seq_gli_si_appoggia"), ("POSTERIORE A", "posteriore_a"), ("ANTERIORE A", "anteriore_a"),
        ]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out[field_name] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes[field_name] = bbox

        # 37) Proprietà fisiche - PPStructure ONLY
        for label_key, field_key in [("CONSISTENZA", "consistenza"), ("COLORE", "colore"), ("MISURE", "misure")]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out[field_key] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes[field_key] = bbox

        # Aggiungi bounding box data
        if _bboxes:
            out["_field_bboxes"] = _bboxes

        return out

    # ---------- PPStructure-based extraction (ONLY METHOD) ----------

    def _filter_nested_cells(self, cells: List[Rect]) -> List[Rect]:
        """Rimuove celle annidate (contenute completamente in altre)."""
        if not cells or len(cells) <= 1:
            return cells

        cells_with_area = [(cell, cell.w * cell.h) for cell in cells]
        cells_with_area.sort(key=lambda x: x[1])

        result = []
        filtered_count = 0

        for i, (cell, cell_area) in enumerate(cells_with_area):
            is_nested = False
            for j in range(i + 1, len(cells_with_area)):
                other, other_area = cells_with_area[j]
                if other_area <= cell_area * 1.1:
                    continue
                tolerance = 2.0
                if (other.x1 - tolerance <= cell.x1 and
                    other.y1 - tolerance <= cell.y1 and
                    other.x2 + tolerance >= cell.x2 and
                    other.y2 + tolerance >= cell.y2):
                    is_nested = True
                    filtered_count += 1
                    break
            if not is_nested:
                result.append(cell)

        if filtered_count > 0:
            logger.debug(f"Filtered {filtered_count} nested cells, kept {len(result)} of {len(cells)}")
        return result

    def _find_cell_for_label(self, label_rect: Rect) -> Optional[Rect]:
        """Trova la cella PPStructure che contiene il centro della label."""
        if not self._detected_cells or not label_rect:
            return None

        label_points = [
            (label_rect.x1, label_rect.y1), (label_rect.x2, label_rect.y1),
            (label_rect.x1, label_rect.y2), (label_rect.x2, label_rect.y2),
            (label_rect.cx, label_rect.cy)
        ]

        candidates = []
        for cell in self._detected_cells:
            score = 0.0
            contained_points = sum(1 for px, py in label_points if cell.contains_point(px, py))

            if contained_points == 5:
                score = 1.0
            elif contained_points >= 4:
                score = 0.9
            elif contained_points >= 2:
                score = 0.7
            elif contained_points == 1:
                score = 0.5
            else:
                continue

            cell_area = cell.w * cell.h
            label_area = label_rect.w * label_rect.h

            if cell_area > label_area * 10:
                score *= 0.7
            elif cell_area <= label_area * 3:
                score *= 1.1
            if cell_area >= label_area * 0.5:
                score *= 1.05

            candidates.append((score, cell))

        if not candidates:
            logger.debug(f"No PPStructure cell found for label at {label_rect}")
            return None

        candidates.sort(key=lambda x: (-x[0], x[1].w * x[1].h))
        best_score, best_cell = candidates[0]

        if best_score > 0.4:
            logger.debug(f"Found cell with score {best_score:.2f} for label")
            return best_cell
        else:
            logger.debug(f"Best cell score below threshold: {best_score:.2f}")
            return None

    def _extract_from_ppstructure_cell(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Rect,
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """Estrae il valore SOLO dalla cella PPStructure. Nessun fallback."""
        if not tokens or not label_rect:
            return None

        cell_rect = self._find_cell_for_label(label_rect)
        if not cell_rect:
            logger.debug(f"No PPStructure cell found for label at {label_rect}")
            return None

        search_y_min = label_rect.y2 + 1
        search_y_max = cell_rect.y2

        value_tokens = []
        for t in tokens:
            tok_rect = t["rect"]

            if (tok_rect.cy <= search_y_min or tok_rect.cy > search_y_max or
                not cell_rect.contains_point(tok_rect.cx, tok_rect.cy) or 
                self._is_probably_label(t["norm"])):
                continue

            if t.get("conf", 0) < 0.3:
                continue

            value_tokens.append(t)

        if value_tokens:
            value_tokens.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
            val = self._join_tokens(value_tokens).strip()
            if val and len(val) > 0:
                logger.debug(f"Extracted value '{val}' from {len(value_tokens)} tokens")
                return (val, value_tokens)
            else:
                logger.debug("Empty value after joining tokens")
                return None

        return None

    def _extract_value_in_cell(
        self,
        tokens: List[Dict[str, Any]],
        label_key: str,
        label_rects: Dict[str, Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """
        Estrae il valore SOLO tramite PPStructure.
        Nessun fallback euristico. Se non ci sono celle, ritorna None.
        """
        if not tokens or not label_rects:
            return None

        label_rect = label_rects.get(label_key)
        if not label_rect:
            logger.debug(f"No label rectangle found for key: {label_key}")
            return None

        # UNICA MODALITA': PPStructure
        if not self._detected_cells:
            logger.debug(f"No PPStructure cells available for {label_key}")
            return None

        result = self._extract_from_ppstructure_cell(tokens, label_rect)
        if result:
            val, val_tokens = result
            logger.debug(f"PPStructure extraction successful for {label_key}: '{val}'")
            return result
        else:
            logger.debug(f"PPStructure extraction failed for {label_key} (empty cell or no tokens)")
            return None

    def _compute_union_bbox(self, tokens: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """Calcola il bounding box unione di una lista di token."""
        if not tokens:
            return None

        xs = []
        ys = []
        for t in tokens:
            r = t["rect"]
            xs.extend([r.x1, r.x2])
            ys.extend([r.y1, r.y2])

        return {
            "x1": min(xs),
            "y1": min(ys),
            "x2": max(xs),
            "y2": max(ys)
        }

    # ---------- internals ----------

    def _to_tokens(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Converte gli item OCR in token normalizzati."""
        if not items:
            return []

        toks = []
        for it in items:
            text = (it.get("text") or "").strip()
            if not text or len(text.strip()) == 0:
                continue

            conf = float(it.get("confidence") or 0.0)
            if conf < 0.15:
                continue

            bbox_data = it.get("polygon") or it.get("bbox")
            rect = _bbox_to_rect(bbox_data)
            if not rect or rect.w <= 0 or rect.h <= 0:
                continue

            norm_text = _norm(text)
            if not norm_text:
                continue

            toks.append({
                "text": text,
                "norm": norm_text,
                "conf": conf,
                "rect": rect,
            })

        toks.sort(key=lambda t: (t["rect"].cy, t["rect"].cx, t["text"]))
        return toks

    def _find_label(self, tokens: List[Dict[str, Any]], aliases: List[str]) -> Optional[Rect]:
        """Trova la label tra i token."""
        alias_norm = [_norm(a) for a in aliases]

        for t in tokens:
            if t["norm"] in alias_norm:
                return t["rect"]

        for t in tokens:
            for a in alias_norm:
                if a and t["norm"].startswith(a):
                    return t["rect"]

        if any("UFFICIO" in a for a in aliases):
            best_match = self._find_label_with_similarity(tokens, aliases, target_keywords=["UFFICIO", "COMPETENTE"])
            if best_match:
                return best_match

        if any("CRITERI" in a for a in aliases):
            for t in tokens:
                nt = t["norm"]
                if "CRITERI" in nt and "DISTINZIONE" in nt:
                    return t["rect"]

        return None

    def _find_label_with_similarity(
        self,
        tokens: List[Dict[str, Any]],
        aliases: List[str],
        target_keywords: List[str] = None
    ) -> Optional[Rect]:
        """Trova label usando similarity score."""
        if not tokens or not aliases:
            return None

        target_keywords = target_keywords or []
        target_norm = [_norm(kw) for kw in target_keywords if kw]
        aliases_norm = [_norm(a) for a in aliases]

        candidates = []

        for t in tokens:
            norm_text = t["norm"]
            text_len = len(norm_text)

            if text_len < 3 or text_len > 60:
                continue
            if t.get("conf", 0) < 0.4:
                continue

            score = 0.0

            best_alias_score = 0.0
            for alias in aliases_norm:
                if not alias:
                    continue
                if norm_text == alias:
                    best_alias_score = 1.0
                    break
                elif alias in norm_text or norm_text in alias:
                    best_alias_score = max(best_alias_score, 0.8)
                else:
                    common_chars = set(alias) & set(norm_text)
                    similarity = len(common_chars) / max(len(alias), len(norm_text))
                    best_alias_score = max(best_alias_score, similarity * 0.5)

            score += best_alias_score * 0.6

            keyword_score = 0.0
            for kw in target_norm:
                if kw and kw in norm_text:
                    keyword_score += len(kw) / text_len
            score += min(keyword_score, 1.0) * 0.2

            pattern_score = 0.0
            if any("UFFICIO" in a for a in aliases):
                if 8 <= text_len <= 35:
                    pattern_score += 0.3
                if "UFFICIO" in norm_text:
                    pattern_score += 0.4
                if "COMPETENTE" in norm_text:
                    pattern_score += 0.3
                if "TUTELA" in norm_text:
                    pattern_score += 0.2
                if "MIC" in norm_text:
                    pattern_score += 0.2
            score += min(pattern_score, 1.0) * 0.2

            if re.match(r'^[0-9\s\-\._/]+$', norm_text):
                score -= 0.9
            elif any(generic in norm_text for generic in ["TITOLO", "SEZIONE", "CAPITOLO", "PARTE", "NUMERO"]):
                score -= 0.6
            elif text_len < 5 and norm_text.isupper():
                score -= 0.3

            ocr_confidence = t.get("conf", 0)
            if ocr_confidence > 0.9:
                score += 0.1
            elif ocr_confidence < 0.6:
                score -= 0.1

            if score > 0.4:
                candidates.append((score, t["rect"], norm_text, ocr_confidence))

        if candidates:
            candidates.sort(key=lambda x: (x[0], x[3]), reverse=True)
            best_score, best_rect, best_text, best_conf = candidates[0]

            if best_score > 0.6:
                logger.debug(f"Found label with similarity: score={best_score:.2f}, text='{best_text}', conf={best_conf:.2f}")
                return best_rect
            else:
                logger.debug(f"Best candidate below threshold: {best_score:.2f} = '{best_text}'")
                return None

        return None

    def _extract_us_number(self, tokens: List[Dict[str, Any]], us_label: Optional[Rect], *, page_w: int, page_h: int) -> Optional[str]:
        """Estrae il numero US vicino alla label."""
        digit_tokens = []
        for t in tokens:
            m = re.fullmatch(r"\d{1,4}", t["text"])
            if not m:
                continue
            if len(t["text"]) == 4 and t["text"].startswith(("19", "20")):
                continue
            digit_tokens.append(t)

        if us_label and digit_tokens:
            best = None
            for t in digit_tokens:
                dy = abs(t["rect"].cy - us_label.cy)
                dx = abs(t["rect"].cx - us_label.cx)
                dist = dx + 2.0 * dy
                if best is None or dist < best[0]:
                    best = (dist, t)
            return best[1]["text"] if best else None

        top_limit = page_h * 0.35
        for t in digit_tokens:
            if t["rect"].cy <= top_limit and 1 <= len(t["text"]) <= 3:
                return t["text"]

        return None

    def _extract_value(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Optional[Rect],
        *,
        page_w: int,
        page_h: int,
        value_regex: Optional[str] = None,
        extract_match: bool = True,
    ) -> Optional[str]:
        """Metodo legacy (non usato in modalità PPStructure-only)."""
        if not label_rect:
            return None

        band = Rect(0, label_rect.y1 - label_rect.h * 0.6, page_w, label_rect.y2 + label_rect.h * 0.6)
        right_candidates = []

        for t in tokens:
            if t["rect"].x1 <= label_rect.x2 + 8:
                continue
            if band.y_overlap_ratio(t["rect"]) < 0.30:
                continue
            if t["rect"].x1 > page_w * 0.98:
                continue
            if self._is_probably_label(t["norm"]):
                continue
            right_candidates.append(t)

        right_candidates.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
        val = self._join_tokens(right_candidates)

        if val:
            if value_regex:
                match = re.search(value_regex, val)
                if match:
                    return match.group(0).strip() if extract_match else val.strip()
            else:
                return val.strip()

        below_candidates = []
        y_min = label_rect.y2 + 6
        y_max = min(page_h, label_rect.y2 + page_h * 0.12)
        col = Rect(label_rect.x1 - 5, y_min, page_w * 0.98, y_max)

        for t in tokens:
            if t["rect"].cy < col.y1 or t["rect"].cy > col.y2:
                continue
            if t["rect"].cx < col.x1 or t["rect"].cx > col.x2:
                continue
            if self._is_probably_label(t["norm"]):
                continue
            below_candidates.append(t)

        below_candidates.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
        val = self._join_tokens(below_candidates)

        if val:
            if value_regex:
                match = re.search(value_regex, val)
                if match:
                    return match.group(0).strip() if extract_match else val.strip()
            else:
                return val.strip()

        return None

    def _join_tokens(self, toks: List[Dict[str, Any]]) -> str:
        """Unisce token in una stringa."""
        if not toks:
            return ""
        parts = [t["text"] for t in toks]
        s = " ".join(parts)
        s = re.sub(r"\s+", " ", s).strip()
        s = self._split_concatenated_words(s)
        return s

    def _split_concatenated_words(self, text: str) -> str:
        """Separa parole maiuscole concatenate."""
        if not text or len(text) < 10:
            return text

        common_words = [
            "RESPONSABILE", "COMPILAZIONE", "RILEVAMENTO", "RIELABORAZIONE",
            "SCIENTIFICO", "STRATIGRAFICA", "AFFIDABILITA", "AFFIDABILITÀ",
            "INDAGINI", "CAMPO", "DATI", "QUANTITATIVI", "REPERTI",
            "ELEMENTI", "DATANTI", "CAMPIONATURE", "FLOTTAZIONE", "SETACCIATURA",
            "COMPONENTI", "INORGANICI", "ORGANICI", "CONSISTENZA", "CONSERVAZIONE",
            "FORMAZIONE", "DISTINZIONE", "DEFINIZIONE", "DESCRIZIONE",
            "INTERPRETAZIONE", "OSSERVAZIONI", "DATAZIONE", "PERIODO", "FASE",
            "ATTIVITA", "ATTIVITÀ", "LOCALITA", "LOCALITÀ", "EDIFICIO", "STRUTTURA",
            "AMBIENTE", "FUNZIONALE", "UNITA", "UNITÀ", "POSIZIONE", "SETTORE",
            "QUADRATO", "QUOTE", "PIANTE", "PROSPETTI", "SEZIONI", "FOTOGRAFIE",
            "RIFERIMENTI", "TABELLE", "MATERIALI", "ANTERIORE", "POSTERIORE",
            "SEQUENZA", "FISICA", "NATURALE", "ARTIFICIALE", "POSITIVA", "NEGATIVA",
            "COPRE", "COPERTO", "TAGLIA", "TAGLIATO", "RIEMPIE", "RIEMPITO",
            "UGUALE", "LEGA", "APPOGGIA", "DELLE", "DELLA", "DEL", "SUL"
        ]

        result = text
        for word in common_words:
            pattern = f"({word})([A-ZÀÈÉÌÒÙ])"
            result = re.sub(pattern, r"\1 \2", result)
            pattern = f"([a-zàèéìòù0-9])({word})"
            result = re.sub(pattern, r"\1 \2", result, flags=re.IGNORECASE)

        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _parse_date_to_iso(self, date_str: str) -> Optional[str]:
        """Converte data italiana a ISO."""
        if not date_str:
            return None

        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y', '%d-%m-%y']

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                return parsed.strftime('%Y-%m-%d')
            except ValueError:
                continue

        return None

    def _is_probably_label(self, norm_text: str) -> bool:
        """Controlla se il token è una label."""
        for aliases in self.LABELS.values():
            for a in aliases:
                norm_alias = _norm(a)
                # Stricter check: exact match OR starts with alias followed by space
                # This prevents "USM" from matching "US"
                if norm_text == norm_alias:
                    return True
                if norm_text.startswith(norm_alias + " "):
                    return True
        return False

    # ---------- CHECKBOX DETECTION ----------

    def _is_checkmark(self, text: str) -> bool:
        """Verifica se il token è un checkmark."""
        s = (text or "").strip()
        return s in {"X", "x", "✓", "✔", "V", "v", "×", "*"}

    def _checkbox_checked_near_label(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Optional[Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> bool:
        """Verifica se c'è un checkmark vicino alla label."""
        if not label_rect:
            return False

        x1 = label_rect.x2 + 3
        x2 = min(page_w, label_rect.x2 + page_w * 0.15)
        y1 = max(0.0, label_rect.y1 - label_rect.h * 0.50)
        y2 = min(page_h, label_rect.y2 + label_rect.h * 0.50)
        win = Rect(x1, y1, x2, y2)

        for t in tokens:
            r = t["rect"]
            if not win.contains_point(r.cx, r.cy):
                continue
            if self._is_checkmark(t["text"]):
                return True

        return False

    def _extract_tipo_from_checkboxes(
        self,
        tokens: List[Dict[str, Any]],
        label_rects: Dict[str, Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Optional[str]:
        """Estrae tipo US da checkbox."""
        pos = self._checkbox_checked_near_label(tokens, label_rects.get("POSITIVA"), page_w=page_w, page_h=page_h)
        neg = self._checkbox_checked_near_label(tokens, label_rects.get("NEGATIVA"), page_w=page_w, page_h=page_h)

        if pos and not neg:
            return "positiva"
        if neg and not pos:
            return "negativa"
        return None

    def _extract_nat_art_from_checkboxes(
        self,
        tokens: List[Dict[str, Any]],
        label_rects: Dict[str, Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Optional[str]:
        """Estrae naturale/artificiale da checkbox."""
        nat = self._checkbox_checked_near_label(tokens, label_rects.get("NATURALE"), page_w=page_w, page_h=page_h)
        art = self._checkbox_checked_near_label(tokens, label_rects.get("ARTIFICIALE"), page_w=page_w, page_h=page_h)

        if nat and not art:
            return "naturale"
        if art and not nat:
            return "artificiale"
        return None


_layout_parser_singleton: Optional[USLayoutParser] = None


def get_us_layout_parser() -> USLayoutParser:
    global _layout_parser_singleton
    if _layout_parser_singleton is None:
        _layout_parser_singleton = USLayoutParser()
    return _layout_parser_singleton
