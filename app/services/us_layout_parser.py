# app/services/us_layout_parser.py
"""
Parser layout-aware per schede US: usa bounding boxes per estrarre i campi
in modo più stabile del parsing "a righe".
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


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
        "ANNO": ["ANNO"],
        "IDENTIFICATIVO": ["IDENTIFICATIVO", "IDENTIFICATIVO DEL SAGGIO STRATIGRAFICO"],
        "LOCALITA": ["LOCALITA", "LOCALITÀ"],
        "AREA/EDIFICIO/STRUTTURA": ["AREA/EDIFICIO/STRUTTURA"],
        "AMBIENTE/UNITA FUNZIONALE": ["AMBIENTE/UNITA FUNZIONALE", "AMBIENTE/UNITÀ FUNZIONALE"],
        "DEFINIZIONE": ["DEFINIZIONE"],
        # Additional labels for extended parsing
        "CRITERI DISTINZIONE": ["CRITERI DISTINZIONE", "CRITERI DI DISTINZIONE"],
        "MODO FORMAZIONE": ["MODO FORMAZIONE", "MODO DI FORMAZIONE"],
        "DESCRIZIONE": ["DESCRIZIONE"],
        "INTERPRETAZIONE": ["INTERPRETAZIONE"],
        "DATAZIONE": ["DATAZIONE"],
        "PERIODO": ["PERIODO"],
        "FASE": ["FASE"],
        "RESPONSABILE SCIENTIFICO": ["RESPONSABILE SCIENTIFICO"],
        "DATA RILEVAMENTO": ["DATA RILEVAMENTO", "DATA"],
    }

    def parse_core(
        self,
        items: List[Dict[str, Any]],
        *,
        site_id: str,
        page_size: Tuple[int, int],
    ) -> Dict[str, Any]:
        """
        items: lista come prodotta dal PaddleOCRService.bounding_boxes:
               [{'text': str, 'confidence': float, 'polygon': [[x,y]...]}]
        page_size: (width, height) dell'immagine renderizzata.
        """
        tokens = self._to_tokens(items)
        w, h = page_size

        # Trova label rect per campo
        label_rects = {}
        for key, aliases in self.LABELS.items():
            found = self._find_label(tokens, aliases)
            if found:
                label_rects[key] = found

        out: Dict[str, Any] = {"site_id": site_id}

        # 1) US (us_code)
        us_num = self._extract_us_number(tokens, label_rects.get("US"), page_w=w, page_h=h)
        if us_num:
            out["us_code"] = f"US{us_num.zfill(3)}"

        # 2) ENTE RESPONSABILE
        v = self._extract_value(tokens, label_rects.get("ENTE RESPONSABILE"), page_w=w, page_h=h)
        if v:
            out["ente_responsabile"] = v

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

        # 5) LOCALITA'
        v = self._extract_value(tokens, label_rects.get("LOCALITA"), page_w=w, page_h=h)
        if v:
            out["localita"] = v

        # 6) AREA/EDIFICIO/STRUTTURA
        v = self._extract_value(tokens, label_rects.get("AREA/EDIFICIO/STRUTTURA"), page_w=w, page_h=h)
        if v:
            out["area_struttura"] = v

        # 7) AMBIENTE/UNITA FUNZIONALE
        v = self._extract_value(tokens, label_rects.get("AMBIENTE/UNITA FUNZIONALE"), page_w=w, page_h=h)
        if v:
            out["ambiente_unita_funzione"] = v

        # 8) DEFINIZIONE
        v = self._extract_value(tokens, label_rects.get("DEFINIZIONE"), page_w=w, page_h=h)
        if v:
            out["definizione"] = v

        # 9) CRITERI DISTINZIONE
        v = self._extract_value(tokens, label_rects.get("CRITERI DISTINZIONE"), page_w=w, page_h=h)
        if v:
            out["criteri_distinzione"] = v

        # 10) MODO FORMAZIONE
        v = self._extract_value(tokens, label_rects.get("MODO FORMAZIONE"), page_w=w, page_h=h)
        if v:
            out["modo_formazione"] = v

        # 11) DESCRIZIONE
        v = self._extract_value(tokens, label_rects.get("DESCRIZIONE"), page_w=w, page_h=h)
        if v:
            out["descrizione"] = v

        # 12) INTERPRETAZIONE
        v = self._extract_value(tokens, label_rects.get("INTERPRETAZIONE"), page_w=w, page_h=h)
        if v:
            out["interpretazione"] = v

        # 13) DATAZIONE
        v = self._extract_value(tokens, label_rects.get("DATAZIONE"), page_w=w, page_h=h)
        if v:
            out["datazione"] = v

        # 14) PERIODO
        v = self._extract_value(tokens, label_rects.get("PERIODO"), page_w=w, page_h=h)
        if v:
            out["periodo"] = v

        # 15) FASE
        v = self._extract_value(tokens, label_rects.get("FASE"), page_w=w, page_h=h)
        if v:
            out["fase"] = v

        # 16) RESPONSABILE SCIENTIFICO
        v = self._extract_value(tokens, label_rects.get("RESPONSABILE SCIENTIFICO"), page_w=w, page_h=h)
        if v:
            out["responsabile_scientifico"] = v

        # 17) DATA RILEVAMENTO
        v = self._extract_value(tokens, label_rects.get("DATA RILEVAMENTO"), page_w=w, page_h=h, 
                                value_regex=r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}")
        if v:
            out["data_rilevamento"] = v

        return out

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

    def _extract_value(
        self,
        tokens: List[Dict[str, Any]],
        label_rect: Optional[Rect],
        *,
        page_w: int,
        page_h: int,
        value_regex: Optional[str] = None,
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

        if val and (value_regex is None or re.search(value_regex, val)):
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

        if val and (value_regex is None or re.search(value_regex, val)):
            return val.strip()

        return None

    def _join_tokens(self, toks: List[Dict[str, Any]]) -> str:
        if not toks:
            return ""
        parts = [t["text"] for t in toks]
        s = " ".join(parts)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def _is_probably_label(self, norm_text: str) -> bool:
        # se il token coincide con una label nota (o un alias), trattalo come label
        for aliases in self.LABELS.values():
            for a in aliases:
                if norm_text == _norm(a) or norm_text.startswith(_norm(a)):
                    return True
        return False


_layout_parser_singleton: Optional[USLayoutParser] = None


def get_us_layout_parser() -> USLayoutParser:
    global _layout_parser_singleton
    if _layout_parser_singleton is None:
        _layout_parser_singleton = USLayoutParser()
    return _layout_parser_singleton
