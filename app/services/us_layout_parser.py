# app/services/us_layout_parser.py
"""
Parser layout-aware per schede US: usa bounding boxes per estrarre i campi
in modo più stabile del parsing "a righe".
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
        # Nessuna sovrapposizione se uno è completamente a sinistra/destra/sopra/sotto dell'altro
        if self.x2 < other.x1 or self.x1 > other.x2:
            return False
        if self.y2 < other.y1 or self.y1 > other.y2:
            return False
        return True


def _norm(s: str) -> str:
    """Normalizza per confronti label: uppercase, no accenti, spazi compressi, punteggiatura ridotta."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper()
    s = s.replace("'", "'").replace(""", '"').replace(""", '"')
    # Tieni / e . perché utili in label e sigle, rimuovi il resto
    s = re.sub(r"[^A-Z0-9/.\s'-]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
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
        # Handle 'polygon' key if present
        if isinstance(bbox, dict):
            bbox = bbox.get('polygon', bbox)
        
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and isinstance(bbox[0], (list, tuple)):
            xs = [float(p[0]) for p in bbox]
            ys = [float(p[1]) for p in bbox]
            return Rect(min(xs), min(ys), max(xs), max(ys))
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 4 and all(isinstance(v, (int, float)) for v in bbox[:4]):
            # Non perfetto, ma meglio di niente
            x1, y1, x2, y2 = map(float, bbox[:4])
            return Rect(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    except Exception:
        return None
    return None


class USLayoutParser:
    """
    Parser layout-aware: trova la bbox della label e poi legge il valore
    dalla zona a destra (preferita) o sotto (fallback).
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
        # Checkbox per tipo US
        "POSITIVA": ["POSITIVA"],
        "NEGATIVA": ["NEGATIVA"],
        "NATURALE": ["NATURALE"],
        "ARTIFICIALE": ["ARTIFICIALE"],
        # Quote
        "QUOTE": ["QUOTE"],
        # Documentazione
        "PIANTE": ["PIANTE"],
        "PROSPETTI": ["PROSPETTI"],
        "SEZIONI": ["SEZIONI"],
        "FOTOGRAFIE": ["FOTOGRAFIE"],
        "RIFERIMENTI TABELLE MATERIALI": [
            "RIFERIMENTI TABELLE MATERIALI", "RIFERIMENTITABELLEMATERIALI",
            "RIFERIMENTI TABELLE", "TABELLE MATERIALI", "RIF TABELLE MATERIALI"
        ],
        # Proprietà fisiche
        "CONSISTENZA": ["CONSISTENZA"],
        "COLORE": ["COLORE"],
        "MISURE": ["MISURE"],
        "STATO DI CONSERVAZIONE": ["STATO DI CONSERVAZIONE"],
        # Estese
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
        # Sequenza stratigrafica labels
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
        # Sequenza stratigrafica (ICCD)
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
        items: lista come prodotta dal PaddleOCRService.bounding_boxes:
               [{'text': str, 'confidence': float, 'polygon': [[x,y]...]}]
        page_size: (width, height) dell'immagine renderizzata.
        detected_cells: celle rilevate da PPStructure (opzionale)
                       [{'x1': float, 'y1': float, 'x2': float, 'y2': float}]
        """
        tokens = self._to_tokens(items)
        w, h = page_size
        
        # Store detected cells for use in extraction methods
        self._detected_cells: List[Rect] = []
        if detected_cells:
            for c in detected_cells:
                self._detected_cells.append(Rect(
                    float(c.get('x1', 0)),
                    float(c.get('y1', 0)),
                    float(c.get('x2', 0)),
                    float(c.get('y2', 0))
                ))
            logger.info(f"Using {len(self._detected_cells)} PPStructure cells for extraction")

        # Trova label rect per campo
        label_rects: Dict[str, Rect] = {}
        for key, aliases in self.LABELS.items():
            found = self._find_label(tokens, aliases)
            if found:
                label_rects[key] = found

        out: Dict[str, Any] = {"site_id": site_id}
        _bboxes: Dict[str, Dict[str, float]] = {}  # Track bounding boxes for each field

        # 1) US (us_code)
        us_num = self._extract_us_number(tokens, label_rects.get("US"), page_w=w, page_h=h)
        if us_num:
            out["us_code"] = f"US{us_num.zfill(3)}"

        # 2) ENTE RESPONSABILE - cell-based per evitare confini sporchi
        result = self._extract_value_in_cell(tokens, "ENTE RESPONSABILE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ente_responsabile"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ente_responsabile"] = bbox

        # 2b) UFFICIO MIC COMPETENTE PER TUTELA
        result = self._extract_value_in_cell(tokens, "UFFICIO MIC", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ufficio_mic"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ufficio_mic"] = bbox

        # 3) ANNO (int)
        result = self._extract_value_in_cell(tokens, "ANNO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            # Estrai anno se presente
            match = re.search(r"\b(19|20)\d{2}\b", val)
            if match:
                out["anno"] = int(match.group(0))
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["anno"] = bbox

        # 4) IDENTIFICATIVO
        result = self._extract_value_in_cell(tokens, "IDENTIFICATIVO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["identificativo_rif"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["identificativo_rif"] = bbox

        # 5) LOCALITA' - cell-based (ha AREA/EDIFICIO/STRUTTURA sotto)
        result = self._extract_value_in_cell(tokens, "LOCALITA", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["localita"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["localita"] = bbox

        # 6) AREA/EDIFICIO/STRUTTURA - cell-based (ha SAGGIO a destra, AMBIENTE sotto)
        result = self._extract_value_in_cell(tokens, "AREA/EDIFICIO/STRUTTURA", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["area_struttura"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["area_struttura"] = bbox

        # 7) SAGGIO - usa celle PPStructure se disponibili, altrimenti estrazione in cell
        # Il metodo _extract_value_below_only era troppo fragile e catturava valori sbagliati
        result = self._extract_value_in_cell(tokens, "SAGGIO", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            # Validazione: SAGGIO dovrebbe essere breve (nome saggio, non lunghe descrizioni)
            if len(val) < 100:  # Limite ragionevole per un nome saggio
                out["saggio"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["saggio"] = bbox
                logger.info(f"SAGGIO extracted: '{val}'")
            else:
                logger.warning(f"SAGGIO: rejected too long value ({len(val)} chars)")
        else:
            logger.debug("SAGGIO: no value found")

        # 8) AMBIENTE/UNITA FUNZIONALE - cell-based
        result = self._extract_value_in_cell(tokens, "AMBIENTE/UNITA FUNZIONALE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["ambiente_unita_funzione"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["ambiente_unita_funzione"] = bbox

        # 9) POSIZIONE - usa metodo semplificato per catturare tutto il testo multi-riga
        if "POSIZIONE" in label_rects:
            result = self._extract_value_in_cell(tokens, "POSIZIONE", label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out["posizione"] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes["posizione"] = bbox

        # 10) DEFINIZIONE - cell-based
        result = self._extract_value_in_cell(tokens, "DEFINIZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["definizione"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["definizione"] = bbox

        # 11) TIPO (checkbox POSITIVA/NEGATIVA)
        tipo = self._extract_tipo_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if tipo:
            out["tipo"] = tipo

        # 12) NATURALE/ARTIFICIALE (checkbox)
        nat_art = self._extract_nat_art_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if nat_art:
            out["formazione"] = nat_art  # 'naturale' o 'artificiale'

        # 13) QUOTE - estrai valori numerici
        result = self._extract_value_in_cell(tokens, "QUOTE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["quote"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["quote"] = bbox
            # Prova a estrarre quote numeriche separate
            quote_nums = re.findall(r"\d+[,.]?\d*", val)
            if quote_nums:
                out["quote_list"] = [float(q.replace(",", ".")) for q in quote_nums[:3]]

        # 14) DOCUMENTAZIONE
        # PIANTE
        result = self._extract_value_in_cell(tokens, "PIANTE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["piante_riferimenti"] = val

        # PROSPETTI
        result = self._extract_value_in_cell(tokens, "PROSPETTI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["prospetti_riferimenti"] = val

        # SEZIONI
        result = self._extract_value_in_cell(tokens, "SEZIONI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["sezioni_riferimenti"] = val

        # FOTOGRAFIE
        result = self._extract_value_in_cell(tokens, "FOTOGRAFIE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["fotografie"] = val

        # RIFERIMENTI TABELLE MATERIALI
        result = self._extract_value_in_cell(tokens, "RIFERIMENTI TABELLE MATERIALI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["riferimenti_tabelle_materiali"] = val

        # 15) PROPRIETÀ FISICHE (duplicate - already handled above, removing)
        # Skip: CONSISTENZA, COLORE, MISURE already tracked with bbox above

        # STATO DI CONSERVAZIONE
        result = self._extract_value_in_cell(tokens, "STATO DI CONSERVAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["stato_conservazione"] = val

        # 16) COMPONENTI
        result = self._extract_value_in_cell(tokens, "COMPONENTI INORGANICI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["componenti_inorganici"] = val

        result = self._extract_value_in_cell(tokens, "COMPONENTI ORGANICI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["componenti_organici"] = val

        # 17) CRITERI DISTINZIONE - cell-based
        result = self._extract_value_in_cell(tokens, "CRITERI DISTINZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["criteri_distinzione"] = val

        # 18) MODO FORMAZIONE - cell-based
        result = self._extract_value_in_cell(tokens, "MODO FORMAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["modo_formazione"] = val

        # 19) DESCRIZIONE - cell-based (può essere multilinea)
        result = self._extract_value_in_cell(tokens, "DESCRIZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["descrizione"] = val

        # 20) OSSERVAZIONI
        result = self._extract_value_in_cell(tokens, "OSSERVAZIONI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["osservazioni"] = val

        # 21) INTERPRETAZIONE - cell-based
        result = self._extract_value_in_cell(tokens, "INTERPRETAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["interpretazione"] = val

        # 22) DATAZIONE
        result = self._extract_value_in_cell(tokens, "DATAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["datazione"] = val

        # 23) PERIODO
        result = self._extract_value_in_cell(tokens, "PERIODO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["periodo"] = val

        # 24) FASE
        result = self._extract_value_in_cell(tokens, "FASE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["fase"] = val

        # 25) ATTIVITA
        result = self._extract_value_in_cell(tokens, "ATTIVITA", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["attivita"] = val

        # 26) ELEMENTI DATANTI
        result = self._extract_value_in_cell(tokens, "ELEMENTI DATANTI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["elementi_datanti"] = val

        # 27) DATI QUANTITATIVI REPERTI
        result = self._extract_value_in_cell(tokens, "DATI QUANTITATIVI DEI REPERTI", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["dati_quantitativi_reperti"] = val

        # 28) CAMPIONATURE, FLOTTAZIONE, SETACCIATURA
        result = self._extract_value_in_cell(tokens, "CAMPIONATURE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["campionature"] = val

        result = self._extract_value_in_cell(tokens, "FLOTTAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["flottazione"] = val

        result = self._extract_value_in_cell(tokens, "SETACCIATURA", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["setacciatura"] = val

        # 29) AFFIDABILITA STRATIGRAFICA
        result = self._extract_value_in_cell(tokens, "AFFIDABILITA STRATIGRAFICA", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["affidabilita_stratigrafica"] = val.lower()

        # 30) RESPONSABILE SCIENTIFICO
        result = self._extract_value_in_cell(tokens, "RESPONSABILE SCIENTIFICO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_scientifico"] = val

        # 31) DATA RILEVAMENTO
        result = self._extract_value_in_cell(tokens, "DATA RILEVAMENTO", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            # Estrai solo la data con regex
            match = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", val)
            if match:
                iso_date = self._parse_date_to_iso(match.group(0))
                if iso_date:
                    out["data_rilevamento"] = iso_date

        # 32) RESPONSABILE COMPILAZIONE
        result = self._extract_value_in_cell(tokens, "RESPONSABILE COMPILAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_compilazione"] = val

        # 33) DATA RIELABORAZIONE
        result = self._extract_value_in_cell(tokens, "DATA RIELABORAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            # Estrai solo la data con regex
            match = re.search(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}", val)
            if match:
                iso_date = self._parse_date_to_iso(match.group(0))
                if iso_date:
                    out["data_rielaborazione"] = iso_date

        # 34) RESPONSABILE RIELABORAZIONE
        result = self._extract_value_in_cell(tokens, "RESPONSABILE RIELABORAZIONE", label_rects, page_w=w, page_h=h)
        if result:
            val, _ = result
            out["responsabile_rielaborazione"] = val

        # 35) Sequenza stratigrafica
        for label_key, field_name in [
            ("SI LEGA A", "seq_si_lega_a"),
            ("UGUALE A", "seq_uguale_a"),
            ("COPRE", "seq_copre"),
            ("COPERTO DA", "seq_coperto_da"),
            ("RIEMPIE", "seq_riempie"),
            ("RIEMPITO DA", "seq_riempito_da"),
            ("TAGLIA", "seq_taglia"),
            ("TAGLIATO DA", "seq_tagliato_da"),
            ("SI APPOGGIA A", "seq_si_appoggia_a"),
            ("GLI SI APPOGGIA", "seq_gli_si_appoggia"),
            ("POSTERIORE A", "posteriore_a"),
            ("ANTERIORE A", "anteriore_a"),
        ]:
            result = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if result:
                val, val_tokens = result
                out[field_name] = val
                bbox = self._compute_union_bbox(val_tokens)
                if bbox:
                    _bboxes[field_name] = bbox

        # 37) Proprietà fisiche
        result = self._extract_value_in_cell(tokens, "CONSISTENZA", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["consistenza"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["consistenza"] = bbox

        result = self._extract_value_in_cell(tokens, "COLORE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["colore"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["colore"] = bbox

        result = self._extract_value_in_cell(tokens, "MISURE", label_rects, page_w=w, page_h=h)
        if result:
            val, val_tokens = result
            out["misure"] = val
            bbox = self._compute_union_bbox(val_tokens)
            if bbox:
                _bboxes["misure"] = bbox

        # Add bounding box data to output
        if _bboxes:
            out["_field_bboxes"] = _bboxes

        return out

    # ---------- CELL-BASED EXTRACTION METHODS ----------

    def _find_cell_for_label(self, label_rect: Rect) -> Optional[Rect]:
        """
        Trova la cella PPStructure che contiene la label.
        Restituisce la cella come Rect o None.
        """
        if not self._detected_cells:
            return None
        
        cx, cy = label_rect.cx, label_rect.cy
        
        for cell in self._detected_cells:
            if cell.contains_point(cx, cy):
                return cell
        
        return None

    
    def _extract_from_ppstructure_cell(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Rect,
    ) -> Optional[Tuple[str, List[Dict[str, Any]]]]:
        """
        Estrae valore usando le celle rilevate da PPStructure.
        Cerca token sotto la label ma nella stessa cella.
        
        Ritorna: (valore, tokens) o None
        """
        cell_rect = self._find_cell_for_label(label_rect)
        if not cell_rect:
            return None
        
        # Cerca token sotto la label ma dentro la cella
        value_tokens = []
        for t in tokens:
            tok_rect = t["rect"]
            
            # Deve essere sotto la label
            if tok_rect.cy <= label_rect.y2:
                continue
            
            # Deve sovrapporsi con la cella
            if not cell_rect.overlaps(tok_rect):
                continue
            
            # Escludi altre label
            if self._is_probably_label(t["norm"]):
                continue
            
            value_tokens.append(t)
        
        if value_tokens:
            value_tokens.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
            val = self._join_tokens(value_tokens).strip()
            return (val, value_tokens)
        
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
        Estrae il valore da una cella.
        
        MODALITÀ STRICT PPSTRUCTURE:
        Se sono state passate detected_cells (da PPStructure), usiamo SOLO quelle.
        Se non troviamo una cella per la label, ritorniamo None.
        Nessun fallback euristico.
        
        Se detected_cells non è presente (vecchio metodo), si potrebbe usare il fallback,
        ma qui assumiamo che il contesto sia ormai PPStructure-first.
        
        Ritorna: (valore_estratto, lista_token_usati) o None
        """
        label_rect = label_rects.get(label_key)
        if not label_rect:
            return None

        # STRICT PPSTRUCTURE MODE
        if self._detected_cells:
            return self._extract_from_ppstructure_cell(tokens, label_rect)
            
        # NESSUNA CELLA RILEVATA O DISPONIBILE
        # Se vogliamo essere strict:
        return None



    def _compute_union_bbox(self, tokens: List[Dict[str, Any]]) -> Optional[Dict[str, float]]:
        """
        Calcola il bounding box unione di una lista di token.
        Ritorna un dict con {x1, y1, x2, y2} o None se la lista è vuota.
        """
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
        toks = []
        for it in items:
            text = (it.get("text") or "").strip()
            if not text:
                continue
            conf = float(it.get("confidence") or 0.0)
            # Filtra rumore evidente
            if conf < 0.25 and len(text) <= 2:
                continue

            # Get bbox from 'polygon' key or 'bbox' key
            bbox_data = it.get("polygon") or it.get("bbox")
            rect = _bbox_to_rect(bbox_data)
            if not rect or rect.w <= 0 or rect.h <= 0:
                continue

            toks.append({
                "text": text,
                "norm": _norm(text),
                "conf": conf,
                "rect": rect,
            })

        # Ordina top-down, left-right
        toks.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
        return toks

    def _find_label(self, tokens: List[Dict[str, Any]], aliases: List[str]) -> Optional[Rect]:
        alias_norm = [_norm(a) for a in aliases]
        
        # Match esatto su token singolo
        for t in tokens:
            if t["norm"] in alias_norm:
                return t["rect"]

        # Match "starts with" per label lunghe
        for t in tokens:
            for a in alias_norm:
                if a and t["norm"].startswith(a):
                    return t["rect"]

        # APPROCCIO EURISTICO PER GESTIRE ERRORI OCR
        # Per label specifiche come UFFICIO MIC, usiamo similarity score
        if any("UFFICIO" in a for a in aliases):
            best_match = self._find_label_with_similarity(tokens, aliases, target_keywords=["UFFICIO", "COMPETENTE"])
            if best_match:
                return best_match

        return None
    
    def _find_label_with_similarity(
        self,
        tokens: List[Dict[str, Any]],
        aliases: List[str],
        target_keywords: List[str] = None
    ) -> Optional[Rect]:
        """
        Trova label usando similarity score invece di match esatto.
        Utile per gestire errori di riconoscimento OCR.
        
        Args:
            tokens: Lista token con testo e coordinate
            aliases: Alias normalizzati della label target
            target_keywords: Parole chiave che devono essere presenti
        
        Returns:
            Rect della label migliore o None
        """
        target_keywords = target_keywords or []
        
        # Prepara keyword normalizzate
        target_norm = [_norm(kw) for kw in target_keywords]
        
        candidates = []
        
        for t in tokens:
            norm_text = t["norm"]
            
            # Skip token troppo corti o troppo lunghi
            if len(norm_text) < 3 or len(norm_text) > 50:
                continue
            
            # Calcola similarity score
            score = 0.0
            
            # 1. Presenza delle keyword target
            for kw in target_norm:
                if kw in norm_text:
                    score += len(kw) / len(norm_text)
            
            # 2. Lunghezza appropriata per label UFFICIO
            if any("UFFICIO" in a for a in aliases):
                # UFFICIO MIC labels di solito sono tra 10 e 30 caratteri
                if 10 <= len(norm_text) <= 30:
                    score += 0.3
                elif 30 <= len(norm_text) <= 50:
                    score += 0.2
            
            # 3. Contiene "UFFICIO" o "COMPETENTE"
            if "UFFICIO" in norm_text:
                score += 0.5
            if "COMPETENTE" in norm_text:
                score += 0.4
            if "TUTELA" in norm_text:
                score += 0.3
            if "MIC" in norm_text:
                score += 0.3
            
            # 4. Evita token che sono solo numeri o simboli
            if re.match(r'^[0-9\s\-\._/]+$', norm_text):
                score -= 0.8
            
            # 5. Penalty per testo troppo generico
            generic_words = ["TITOLO", "SEZIONE", "CAPITOLO", "PARTE"]
            for gw in generic_words:
                if gw in norm_text:
                    score -= 0.5
            
            if score > 0.3:  # Threshold minimo
                candidates.append((score, t["rect"], norm_text))
        
        # Ritorna il migliore
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            best_score, best_rect, best_text = candidates[0]
            logger.debug(f"Found UFFICIO label with similarity: {best_score:.2f} = '{best_text}'")
            return best_rect
        
        return None

    def _extract_us_number(self, tokens: List[Dict[str, Any]], us_label: Optional[Rect], *, page_w: int, page_h: int) -> Optional[str]:
        """
        Cerca un numero vicino alla label "US" (distanza minima).
        Fallback: primo numero "piccolo" in alto pagina, ma evita anni (4 cifre).
        """
        digit_tokens = []
        for t in tokens:
            m = re.fullmatch(r"\d{1,4}", t["text"])
            if not m:
                continue
            # evita prendere 2023 come US
            if len(t["text"]) == 4 and t["text"].startswith(("19", "20")):
                continue
            digit_tokens.append(t)

        if us_label and digit_tokens:
            best = None
            for t in digit_tokens:
                # penalizza se molto lontano in verticale
                dy = abs(t["rect"].cy - us_label.cy)
                dx = abs(t["rect"].cx - us_label.cx)
                dist = dx + 2.0 * dy
                if best is None or dist < best[0]:
                    best = (dist, t)
            return best[1]["text"] if best else None

        # fallback: numero 1-3 cifre nella parte alta del foglio
        top_limit = page_h * 0.35
        for t in digit_tokens:
            if t["rect"].cy <= top_limit and 1 <= len(t["text"]) <= 3:
                return t["text"]

        return None

    def _extract_value_below_only(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Optional[Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Optional[str]:
        """
        Estrae il valore SOLO dalla zona direttamente sotto la label.
        Non cerca a destra - utile per campi piccoli come SAGGIO
        che potrebbero catturare valori da campi adiacenti.
        """
        if not label_rect:
            return None

        # Cerchiamo solo sotto la label, in una colonna stretta
        y_min = label_rect.y2 + 2
        y_max = min(page_h, label_rect.y2 + page_h * 0.08)  # Poco sotto
        
        # Colonna stretta: dalla x della label alla sua larghezza + un po'
        col_x1 = label_rect.x1 - 5
        col_x2 = label_rect.x2 + label_rect.w * 0.5  # Solo un po' più largo della label
        
        below_candidates = []
        for t in tokens:
            # Deve essere sotto la label
            if t["rect"].cy < y_min or t["rect"].cy > y_max:
                continue
            # Deve essere nella colonna della label
            if t["rect"].cx < col_x1 or t["rect"].cx > col_x2:
                continue
            # Escludi label
            if self._is_probably_label(t["norm"]):
                continue
            below_candidates.append(t)

        below_candidates.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
        val = self._join_tokens(below_candidates).strip()
        return val or None

    def _extract_value(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Optional[Rect],
        *,
        page_w: int,
        page_h: int,
        value_regex: Optional[str] = None,
        extract_match: bool = True,  # Se True, ritorna solo la corrispondenza regex
    ) -> Optional[str]:
        if not label_rect:
            return None

        # 1) Preferenza: valore a destra della label (stessa riga/banda)
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
                    # Ritorna solo la corrispondenza, non tutto il testo
                    return match.group(0).strip() if extract_match else val.strip()
            else:
                return val.strip()

        # 2) Fallback: valore sotto la label (box verticale)
        below_candidates = []
        y_min = label_rect.y2 + 6
        y_max = min(page_h, label_rect.y2 + page_h * 0.12)  # "poco sotto"
        # Colonna: dalla x della label verso destra
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
        if not toks:
            return ""
        parts = [t["text"] for t in toks]
        s = " ".join(parts)
        s = re.sub(r"\s+", " ", s).strip()
        # Separa parole maiuscole concatenate
        s = self._split_concatenated_words(s)
        return s

    def _split_concatenated_words(self, text: str) -> str:
        """
        Separa parole maiuscole concatenate come 'RESPONSABILECOMPILAZIONE'
        in 'RESPONSABILE COMPILAZIONE'.
        
        Usa un dizionario di parole comuni nelle schede US per riconoscere i confini.
        """
        if not text or len(text) < 10:
            return text
        
        # Parole comuni nelle schede US da cercare e separare
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
            # Pattern: parola seguita da lettera maiuscola (senza spazio)
            pattern = f"({word})([A-ZÀÈÉÌÒÙ])"
            result = re.sub(pattern, r"\1 \2", result)
            # Pattern: lettera minuscola/maiuscola seguita da parola (senza spazio)
            pattern = f"([a-zàèéìòù0-9])({word})"
            result = re.sub(pattern, r"\1 \2", result, flags=re.IGNORECASE)
        
        # Pulisci spazi multipli
        result = re.sub(r"\s+", " ", result).strip()
        return result

    def _parse_date_to_iso(self, date_str: str) -> Optional[str]:
        """
        Converte una data in formato italiano (DD/MM/YYYY o DD-MM-YYYY)
        in formato ISO (YYYY-MM-DD) per compatibilità API.
        
        Returns:
            Stringa ISO o None se parsing fallisce
        """
        if not date_str:
            return None
        
        # Formati supportati
        formats = [
            '%d/%m/%Y',  # 24/08/2023
            '%d-%m-%Y',  # 24-08-2023
            '%d.%m.%Y',  # 24.08.2023
            '%d/%m/%y',  # 24/08/23
            '%d-%m-%y',  # 24-08-23
        ]
        
        for fmt in formats:
            try:
                parsed = datetime.strptime(date_str.strip(), fmt)
                return parsed.strftime('%Y-%m-%d')  # ISO format
            except ValueError:
                continue
        
        return None

    def _is_probably_label(self, norm_text: str) -> bool:
        # se il token coincide con una label nota (o un alias), trattalo come label
        for aliases in self.LABELS.values():
            for a in aliases:
                if norm_text == _norm(a) or norm_text.startswith(_norm(a)):
                    return True
        return False

    # ---------- CHECKBOX DETECTION ----------

    def _is_checkmark(self, text: str) -> bool:
        """Verifica se un token è un checkmark (X, x, ✓, ✔)."""
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
        """
        Verifica se c'è un checkmark (X, ✓) vicino alla label.
        Cerca in una finestra stretta a destra della label.
        """
        if not label_rect:
            return False

        # Finestra a destra della label, stessa banda verticale
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
        """
        Estrae il tipo US (positiva/negativa) cercando checkbox marcati.
        """
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
        """
        Estrae naturale/artificiale cercando checkbox marcati.
        """
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
