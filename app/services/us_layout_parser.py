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
            "UFFICIO MIC", "UFFICIO MiC", "UFFICIO MIC COMPETENTE",
            "UFFICIO MIC COMPETENTE PER TUTELA", "UFFICIO MiC COMPETENTE PER TUTELA",
            "UFFICIO COMPETENTE", "MIC COMPETENTE", "COMPETENTE PER TUTELA"
        ],
        "ANNO": ["ANNO"],
        "IDENTIFICATIVO": [
            "IDENTIFICATIVO", 
            "IDENTIFICATIVO DEL SAGGIO STRATIGRAFICO",
            "IDENTIFICATIVO DEL SAGGIO STRATIGRAFICO/DELL'EDIFICIO/DELLA",
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
        self._detected_cells = detected_cells or []
        if self._detected_cells:
            logger.info(f"Using {len(self._detected_cells)} PPStructure cells for extraction")

        # Trova label rect per campo
        label_rects: Dict[str, Rect] = {}
        for key, aliases in self.LABELS.items():
            found = self._find_label(tokens, aliases)
            if found:
                label_rects[key] = found

        out: Dict[str, Any] = {"site_id": site_id}

        # 1) US (us_code)
        us_num = self._extract_us_number(tokens, label_rects.get("US"), page_w=w, page_h=h)
        if us_num:
            out["us_code"] = f"US{us_num.zfill(3)}"

        # 2) ENTE RESPONSABILE - valore a destra/sotto
        v = self._extract_value(tokens, label_rects.get("ENTE RESPONSABILE"), page_w=w, page_h=h)
        if v:
            out["ente_responsabile"] = v

        # 2b) UFFICIO MIC COMPETENTE PER TUTELA
        v = self._extract_value(tokens, label_rects.get("UFFICIO MIC"), page_w=w, page_h=h)
        if v:
            out["ufficio_mic"] = v

        # 3) ANNO (int)
        v = self._extract_value(tokens, label_rects.get("ANNO"), page_w=w, page_h=h, value_regex=r"\b(19|20)\d{2}\b")
        if v:
            match = re.search(r"\b(19|20)\d{2}\b", v)
            if match:
                out["anno"] = int(match.group(0))

        # 4) IDENTIFICATIVO
        v = self._extract_value(tokens, label_rects.get("IDENTIFICATIVO"), page_w=w, page_h=h)
        if v:
            out["identificativo_rif"] = v

        # 5) LOCALITA' - cell-based (ha AREA/EDIFICIO/STRUTTURA sotto)
        v = self._extract_value_in_cell(tokens, "LOCALITA", label_rects, page_w=w, page_h=h)
        if v:
            out["localita"] = v

        # 6) AREA/EDIFICIO/STRUTTURA - cell-based (ha SAGGIO a destra, AMBIENTE sotto)
        v = self._extract_value_in_cell(tokens, "AREA/EDIFICIO/STRUTTURA", label_rects, page_w=w, page_h=h)
        if v:
            out["area_struttura"] = v

        # 7) SAGGIO - estrazione rigorosa solo sotto la label (non a destra)
        # per evitare di catturare il valore di AREA/EDIFICIO/STRUTTURA
        v = self._extract_value_below_only(tokens, label_rects.get("SAGGIO"), page_w=w, page_h=h)
        if v:
            out["saggio"] = v

        # 8) AMBIENTE/UNITA FUNZIONALE - cell-based
        v = self._extract_value_in_cell(tokens, "AMBIENTE/UNITA FUNZIONALE", label_rects, page_w=w, page_h=h)
        if v:
            out["ambiente_unita_funzione"] = v

        # 9) POSIZIONE - cell-based
        v = self._extract_value_in_cell(tokens, "POSIZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["posizione"] = v

        # 10) DEFINIZIONE - cell-based
        v = self._extract_value_in_cell(tokens, "DEFINIZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["definizione"] = v

        # 11) TIPO (checkbox POSITIVA/NEGATIVA)
        tipo = self._extract_tipo_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if tipo:
            out["tipo"] = tipo

        # 12) NATURALE/ARTIFICIALE (checkbox)
        nat_art = self._extract_nat_art_from_checkboxes(tokens, label_rects, page_w=w, page_h=h)
        if nat_art:
            out["formazione"] = nat_art  # 'naturale' o 'artificiale'

        # 13) QUOTE - estrai valori numerici
        v = self._extract_value_in_cell(tokens, "QUOTE", label_rects, page_w=w, page_h=h)
        if v:
            out["quote"] = v
            # Prova a estrarre quote numeriche separate
            quote_nums = re.findall(r"\d+[,.]?\d*", v)
            if quote_nums:
                out["quote_list"] = [float(q.replace(",", ".")) for q in quote_nums[:3]]

        # 14) DOCUMENTAZIONE
        # PIANTE
        v = self._extract_value_in_cell(tokens, "PIANTE", label_rects, page_w=w, page_h=h)
        if v:
            out["piante_riferimenti"] = v

        # PROSPETTI
        v = self._extract_value_in_cell(tokens, "PROSPETTI", label_rects, page_w=w, page_h=h)
        if v:
            out["prospetti_riferimenti"] = v

        # SEZIONI
        v = self._extract_value_in_cell(tokens, "SEZIONI", label_rects, page_w=w, page_h=h)
        if v:
            out["sezioni_riferimenti"] = v

        # FOTOGRAFIE
        v = self._extract_value_in_cell(tokens, "FOTOGRAFIE", label_rects, page_w=w, page_h=h)
        if v:
            out["fotografie"] = v

        # RIFERIMENTI TABELLE MATERIALI
        v = self._extract_value_in_cell(tokens, "RIFERIMENTI TABELLE MATERIALI", label_rects, page_w=w, page_h=h)
        if v:
            out["riferimenti_tabelle_materiali"] = v

        # 15) PROPRIETÀ FISICHE
        v = self._extract_value_in_cell(tokens, "CONSISTENZA", label_rects, page_w=w, page_h=h)
        if v:
            out["consistenza"] = v.lower()

        v = self._extract_value_in_cell(tokens, "COLORE", label_rects, page_w=w, page_h=h)
        if v:
            out["colore"] = v

        v = self._extract_value_in_cell(tokens, "MISURE", label_rects, page_w=w, page_h=h)
        if v:
            out["misure"] = v

        v = self._extract_value_in_cell(tokens, "STATO DI CONSERVAZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["stato_conservazione"] = v

        # 16) COMPONENTI
        v = self._extract_value_in_cell(tokens, "COMPONENTI INORGANICI", label_rects, page_w=w, page_h=h)
        if v:
            out["componenti_inorganici"] = v

        v = self._extract_value_in_cell(tokens, "COMPONENTI ORGANICI", label_rects, page_w=w, page_h=h)
        if v:
            out["componenti_organici"] = v

        # 17) CRITERI DISTINZIONE - cell-based
        v = self._extract_value_in_cell(tokens, "CRITERI DISTINZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["criteri_distinzione"] = v

        # 18) MODO FORMAZIONE - cell-based
        v = self._extract_value_in_cell(tokens, "MODO FORMAZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["modo_formazione"] = v

        # 19) DESCRIZIONE - cell-based (può essere multilinea)
        v = self._extract_value_in_cell(tokens, "DESCRIZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["descrizione"] = v

        # 20) OSSERVAZIONI
        v = self._extract_value_in_cell(tokens, "OSSERVAZIONI", label_rects, page_w=w, page_h=h)
        if v:
            out["osservazioni"] = v

        # 21) INTERPRETAZIONE - cell-based
        v = self._extract_value_in_cell(tokens, "INTERPRETAZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["interpretazione"] = v

        # 22) DATAZIONE
        v = self._extract_value_in_cell(tokens, "DATAZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["datazione"] = v

        # 23) PERIODO
        v = self._extract_value_in_cell(tokens, "PERIODO", label_rects, page_w=w, page_h=h)
        if v:
            out["periodo"] = v

        # 24) FASE
        v = self._extract_value_in_cell(tokens, "FASE", label_rects, page_w=w, page_h=h)
        if v:
            out["fase"] = v

        # 25) ATTIVITA
        v = self._extract_value_in_cell(tokens, "ATTIVITA", label_rects, page_w=w, page_h=h)
        if v:
            out["attivita"] = v

        # 26) ELEMENTI DATANTI
        v = self._extract_value_in_cell(tokens, "ELEMENTI DATANTI", label_rects, page_w=w, page_h=h)
        if v:
            out["elementi_datanti"] = v

        # 27) DATI QUANTITATIVI REPERTI
        v = self._extract_value_in_cell(tokens, "DATI QUANTITATIVI DEI REPERTI", label_rects, page_w=w, page_h=h)
        if v:
            out["dati_quantitativi_reperti"] = v

        # 28) CAMPIONATURE, FLOTTAZIONE, SETACCIATURA
        v = self._extract_value_in_cell(tokens, "CAMPIONATURE", label_rects, page_w=w, page_h=h)
        if v:
            out["campionature"] = v

        v = self._extract_value_in_cell(tokens, "FLOTTAZIONE", label_rects, page_w=w, page_h=h)
        if v:
            out["flottazione"] = v

        v = self._extract_value_in_cell(tokens, "SETACCIATURA", label_rects, page_w=w, page_h=h)
        if v:
            out["setacciatura"] = v

        # 29) AFFIDABILITA STRATIGRAFICA
        v = self._extract_value_in_cell(tokens, "AFFIDABILITA STRATIGRAFICA", label_rects, page_w=w, page_h=h)
        if v:
            out["affidabilita_stratigrafica"] = v.lower()

        # 30) RESPONSABILE SCIENTIFICO
        v = self._extract_value(tokens, label_rects.get("RESPONSABILE SCIENTIFICO"), page_w=w, page_h=h)
        if v:
            out["responsabile_scientifico"] = v

        # 31) DATA RILEVAMENTO
        v = self._extract_value(tokens, label_rects.get("DATA RILEVAMENTO"), page_w=w, page_h=h, 
                                value_regex=r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
        if v:
            # Converti in formato ISO per API
            iso_date = self._parse_date_to_iso(v)
            if iso_date:
                out["data_rilevamento"] = iso_date

        # 32) RESPONSABILE COMPILAZIONE
        v = self._extract_value(tokens, label_rects.get("RESPONSABILE COMPILAZIONE"), page_w=w, page_h=h)
        if v:
            out["responsabile_compilazione"] = v

        # 33) DATA RIELABORAZIONE
        v = self._extract_value(tokens, label_rects.get("DATA RIELABORAZIONE"), page_w=w, page_h=h,
                                value_regex=r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
        if v:
            # Converti in formato ISO per API
            iso_date = self._parse_date_to_iso(v)
            if iso_date:
                out["data_rielaborazione"] = iso_date

        # 34) RESPONSABILE RIELABORAZIONE
        v = self._extract_value(tokens, label_rects.get("RESPONSABILE RIELABORAZIONE"), page_w=w, page_h=h)
        if v:
            out["responsabile_rielaborazione"] = v

        # 35) Sequenza stratigrafica
        for label_key, field_name in [
            ("SI LEGA A", "si_lega_a"),
            ("UGUALE A", "uguale_a"),
            ("COPRE", "copre"),
            ("COPERTO DA", "coperto_da"),
            ("RIEMPIE", "riempie"),
            ("RIEMPITO DA", "riempito_da"),
            ("TAGLIA", "taglia"),
            ("TAGLIATO DA", "tagliato_da"),
            ("SI APPOGGIA A", "si_appoggia_a"),
            ("GLI SI APPOGGIA", "gli_si_appoggia"),
            ("POSTERIORE A", "posteriore_a"),
            ("ANTERIORE A", "anteriore_a"),
        ]:
            v = self._extract_value_in_cell(tokens, label_key, label_rects, page_w=w, page_h=h)
            if v:
                out[field_name] = v

        return out

    # ---------- CELL-BASED EXTRACTION METHODS ----------

    def _nearest_label_right(self, label_rect: Rect, label_rects: Dict[str, Rect]) -> Optional[Rect]:
        """Trova la label più vicina a destra sulla stessa riga."""
        best = None
        best_dx = None
        for r in label_rects.values():
            # Deve essere a destra
            if r.x1 <= label_rect.x2 + 3:
                continue
            # Stessa banda verticale (overlap significativo)
            if label_rect.y_overlap_ratio(r) < 0.25:
                continue
            dx = r.x1 - label_rect.x2
            if best_dx is None or dx < best_dx:
                best_dx = dx
                best = r
        return best

    def _nearest_label_below(self, label_rect: Rect, label_rects: Dict[str, Rect]) -> Optional[Rect]:
        """Trova la label più vicina sotto nella stessa colonna."""
        best = None
        best_dy = None
        for r in label_rects.values():
            # Deve essere sotto
            if r.y1 <= label_rect.y2 + 3:
                continue
            # Stessa colonna (overlap orizzontale)
            x_overlap_val = min(label_rect.x2, r.x2) - max(label_rect.x1, r.x1)
            x_overlap = x_overlap_val / max(label_rect.w, 1e-6)
            if x_overlap < 0.20:
                continue
            dy = r.y1 - label_rect.y2
            if best_dy is None or dy < best_dy:
                best_dy = dy
                best = r
        return best

    def _cell_rect_from_label(
        self,
        label_rect: Rect,
        label_rects: Dict[str, Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Rect:
        """Calcola il rettangolo della cella usando le label vicine come confini."""
        r_right = self._nearest_label_right(label_rect, label_rects)
        r_below = self._nearest_label_below(label_rect, label_rects)

        # Confine destro: a metà tra label e label vicina (non invadere la cella accanto)
        right = (r_right.x1 + label_rect.x2) / 2.0 if r_right else page_w * 0.98
        # Confine inferiore: a metà tra label e label sotto
        bottom = (r_below.y1 + label_rect.y2) / 2.0 if r_below else page_h * 0.98

        return Rect(label_rect.x1, label_rect.y1, right, bottom)

    def _find_cell_for_label(self, label_rect: Rect) -> Optional[Dict[str, Any]]:
        """
        Trova la cella PPStructure che contiene la label.
        Restituisce la cella come dict {x1, y1, x2, y2} o None.
        """
        if not self._detected_cells:
            return None
        
        label_center_x = label_rect.cx
        label_center_y = label_rect.cy
        
        for cell in self._detected_cells:
            x1, y1 = cell.get('x1', 0), cell.get('y1', 0)
            x2, y2 = cell.get('x2', 0), cell.get('y2', 0)
            
            # La label è dentro la cella?
            if x1 <= label_center_x <= x2 and y1 <= label_center_y <= y2:
                return cell
        
        return None

    def _extract_from_ppstructure_cell(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Rect,
    ) -> Optional[str]:
        """
        Estrae valore usando le celle rilevate da PPStructure.
        Cerca token sotto la label ma nella stessa cella.
        """
        cell = self._find_cell_for_label(label_rect)
        if not cell:
            return None
        
        cell_rect = Rect(
            cell['x1'], cell['y1'],
            cell['x2'], cell['y2']
        )
        
        # Cerca token sotto la label ma dentro la cella
        value_tokens = []
        for t in tokens:
            tok_rect = t["rect"]
            
            # Deve essere sotto la label
            if tok_rect.cy <= label_rect.y2:
                continue
            
            # Deve essere nella cella
            if not cell_rect.contains_point(tok_rect.cx, tok_rect.cy):
                continue
            
            # Escludi altre label
            if self._is_probably_label(t["norm"]):
                continue
            
            value_tokens.append(t)
        
        if value_tokens:
            value_tokens.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
            return self._join_tokens(value_tokens).strip()
        
        return None

    def _extract_value_in_cell(
        self,
        tokens: List[Dict[str, Any]],
        label_key: str,
        label_rects: Dict[str, Rect],
        *,
        page_w: int,
        page_h: int,
    ) -> Optional[str]:
        """
        Estrae il valore da una cella definita dalla label e dalle label vicine.
        PRIMA prova con celle PPStructure (più precise), poi fallback a euristico.
        """
        label_rect = label_rects.get(label_key)
        if not label_rect:
            return None

        # PRIMO TENTATIVO: usa celle PPStructure se disponibili
        if self._detected_cells:
            pp_result = self._extract_from_ppstructure_cell(tokens, label_rect)
            if pp_result:
                return pp_result

        # FALLBACK: usa metodo euristico basato su label vicine
        cell = self._cell_rect_from_label(label_rect, label_rects, page_w=page_w, page_h=page_h)

        # Regione valore = cella meno la "striscia" della label (valore tipicamente sotto/a destra)
        value_region = Rect(
            cell.x1 + 2,
            label_rect.y2 + 2,  # Inizia sotto la label
            cell.x2 - 2,
            cell.y2 - 2,
        )

        captured = []
        for t in tokens:
            r = t["rect"]
            # Il centro del token deve essere dentro la regione valore
            if not value_region.contains_point(r.cx, r.cy):
                continue
            # Escludi token che sono label note
            if self._is_probably_label(t["norm"]):
                continue
            captured.append(t)

        captured.sort(key=lambda t: (t["rect"].cy, t["rect"].cx))
        val = self._join_tokens(captured).strip()
        return val or None

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
        # match esatto su token singolo
        for t in tokens:
            if t["norm"] in alias_norm:
                return t["rect"]

        # match "starts with" utile per label lunghe (IDENTIFICATIVO...)
        for t in tokens:
            for a in alias_norm:
                if a and t["norm"].startswith(a):
                    return t["rect"]

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
