# app/services/deepseek_ocr_service.py
"""
Servizio OCR con DeepSeek-OCR via Ollama
Sostituisce PaddleOCR per importazione PDF schede US

Pipeline:
    PDF → PyMuPDF (render) → DeepSeek-OCR → Markdown → llama3.2:3b → JSON
"""

import base64
import json
import logging
import re
from io import BytesIO
from typing import Dict, List, Any, Optional
from datetime import datetime

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from app.models.stratigraphy import TipoUSEnum

logger = logging.getLogger(__name__)


class DeepSeekOCRService:
    """
    Servizio OCR per schede US con DeepSeek-OCR via Ollama.
    
    Modelli utilizzati:
    - deepseek-ocr:3b - per estrazione OCR (VLM)
    - llama3.2:3b - per conversione Markdown → JSON strutturato
    """
    
    def __init__(self):
        """Inizializza il servizio."""
        self.ocr_model = "deepseek-ocr:3b"
        self.llm_model = "llama3.2:3b"
        self.render_zoom = 2.0  # Fattore zoom per rendering PDF
        
    def is_available(self) -> bool:
        """Verifica se il servizio è disponibile."""
        return OLLAMA_AVAILABLE and PYMUPDF_AVAILABLE and PIL_AVAILABLE
    
    def _pdf_to_images(self, pdf_bytes: bytes, zoom: float = None) -> List[Dict[str, Any]]:
        """
        Converte PDF in lista di immagini.
        
        Returns:
            Lista di dict con:
            - image: PIL Image
            - image_b64: base64 string
            - page_number: numero pagina (1-indexed)
            - size: (width, height)
        """
        if zoom is None:
            zoom = self.render_zoom
            
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = []
        
        for page_num, page in enumerate(doc):
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            if pix.n == 4:
                img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
                img = img.convert("RGB")
            else:
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            
            # Converti in base64
            buffer = BytesIO()
            img.save(buffer, format="JPEG", quality=90)
            img_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
            
            pages.append({
                "image": img,
                "image_b64": img_b64,
                "page_number": page_num + 1,
                "size": (pix.width, pix.height)
            })
        
        doc.close()
        return pages
    
    def _extract_markdown(self, image_b64: str) -> str:
        """
        Estrae testo OCR come Markdown usando DeepSeek-OCR.
        
        Usa il prompt "Convert to Markdown" raccomandato per preservare
        la struttura di tabelle, intestazioni e layout complessi.
        
        Args:
            image_b64: immagine in base64
            
        Returns:
            Testo estratto in formato Markdown strutturato
        """
        try:
            # Prompt ottimizzato per struttura tabellare (best practice)
            # Ref: https://deepseek-ocr.io, datacamp.com guides
            response = ollama.chat(
                model=self.ocr_model,
                messages=[{
                    "role": "user",
                    "content": "<image>\nConvert to Markdown. Preserve all table structures, headers, and field values exactly as shown.",
                    "images": [image_b64]
                }],
                options={
                    "temperature": 0.1,
                    "num_predict": 6000  # Aumentato per documenti complessi
                }
            )
            return response.get("message", {}).get("content", "")
        except Exception as e:
            logger.error(f"DeepSeek-OCR extraction failed: {e}")
            return ""
    
    def _markdown_to_json(self, markdown_text: str) -> Dict[str, Any]:
        """
        Converte Markdown estratto in JSON strutturato per US.
        
        Args:
            markdown_text: testo Markdown da DeepSeek-OCR
            
        Returns:
            Dict con campi strutturati per UnitaStratigrafica
        """
        prompt = f"""Sei un esperto di schede archeologiche italiane. Converti questo OCR in JSON.

STRUTTURA JSON RICHIESTA:
{{
  "us": "numero US (SOLO numero, es. 14)",
  "anno": 2023,
  "ente_responsabile": "nome ente (es. PARCO ARCHEOLOGICO DI SEPINO)",
  "localita": "località (es. SEPINO (CB), ALTILIA)",
  "area": "nome area/struttura (es. TERME PORTA BOJANO)",
  "saggio": "identificativo saggio (lascia vuoto se non c'è)",
  "ambiente": "unità funzionale (es. AMB. 02)",
  "posizione": "posizione strato",
  "definizione": "definizione US",
  "criteri_distinzione": "criteri distinzione",
  "modo_formazione": "modo formazione",
  "tipo": "positiva o negativa (quale ha la X)",
  "quote": {{"quota_max": 547.99, "quota_min": 0}},
  "sequenza_stratigrafica": {{
    "copre": ["12", "13"],
    "coperto_da": ["1"],
    "si_appoggia_a": [],
    "gli_si_appoggia": [],
    "taglia": [],
    "tagliato_da": [],
    "riempie": ["87"],
    "riempito_da": [],
    "uguale_a": [],
    "anteriore_a": ["1"],
    "posteriore_a": ["87"]
  }},
  "descrizione": "testo descrizione completa",
  "interpretazione": "interpretazione",
  "stato_conservazione": "ottimo/buono/cattivo",
  "colore": "colore",
  "consistenza": "compatta/friabile/etc",
  "misure": "dimensioni",
  "componenti": {{
    "inorganici": "elementi fittili, lapidei (NON ossei)",
    "organici": "apparati radicali, frammenti ossei"
  }},
  "documentazione": {{
    "piante": ["TAV. 17"],
    "sezioni": [],
    "prospetti": [],
    "fotografie": ["DSCF0918", "DSCF0919"]
  }},
  "cassetta_materiali": "numero cassetta",
  "dati_quantitativi_reperti": "totale frammenti",
  "periodo": "periodo",
  "fase": "fase",
  "data_rilievo": "DD/MM/YYYY",
  "responsabile_rilievo": "nome responsabile"
}}

REGOLE CRITICHE:
1. US = SOLO il numero (es. "14" NON "US 14")
2. TIPO = "positiva" se POSITIVA ha X, "negativa" se NEGATIVA ha X
3. ENTE RESPONSABILE = cerca dopo "ENTE RESPONSABILE" nella tabella intestazione
4. AREA = cerca dopo "AREA/EDIFICIO/STRUTTURA" (rimuovi prefissi come "/")
5. AMBIENTE = valore dopo "AMBIENTE/UNITÀ FUNZIONALE" (rimuovi prefissi)
6. COMPONENTI: INORGANICI = elementi fittili, lapidei | ORGANICI = ossei, radicali
7. SEQUENZA: estrai SOLO i numeri US dalle relazioni (separa USM se presente)
8. COPERTO DA = numeri dopo "COPERTO DA" | COPRE = numeri dopo "COPRE"
9. PIANTE = valori TAV. dopo "PIANTE" | SEZIONI = dopo "SEZIONI"
10. POSTERIORE A = numeri dopo "POSTERIORE A" nella sequenza fisica/stratigrafica

TESTO OCR:
{markdown_text}

Rispondi SOLO con JSON valido senza commenti."""

        try:
            response = ollama.generate(
                model=self.llm_model,
                prompt=prompt,
                format="json",
                options={
                    "temperature": 0.1,
                    "num_predict": 2500
                }
            )
            
            json_str = response.get("response", "")
            return json.loads(json_str)
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            return {}
        except Exception as e:
            logger.error(f"LLM conversion failed: {e}")
            return {}
    
    def _map_to_us_model(self, extracted: Dict[str, Any], site_id: str) -> Dict[str, Any]:
        """
        Mappa i dati estratti al modello UnitaStratigrafica.
        
        I nomi campi sono allineati allo schema form_fields_schema.json
        per permettere la corretta visualizzazione nel tab "Revisione OCR".
        
        Args:
            extracted: dati JSON estratti
            site_id: ID del sito
            
        Returns:
            Dict compatibile con UnitaStratigrafica model e form schema
        """
        # Mappa tipo
        tipo_str = str(extracted.get("tipo", "")).lower()
        if "positiva" in tipo_str:
            tipo = TipoUSEnum.POSITIVA
        elif "negativa" in tipo_str:
            tipo = TipoUSEnum.NEGATIVA
        else:
            tipo = None
        
        # Mappa sequenza stratigrafica
        seq = extracted.get("sequenza_stratigrafica", {})
        
        # Helper per convertire lista in stringa CSV (per form compatibility)
        def list_to_csv(lst):
            if isinstance(lst, list):
                return ", ".join(str(x) for x in lst if x)
            return lst or ""
        
        # Costruisci US code
        us_num = extracted.get("us", "")
        if us_num:
            us_code = f"US{us_num}"
        else:
            us_code = "US???"
        
        # Documentazione
        doc = extracted.get("documentazione", {})
        
        return {
            "site_id": site_id,
            "us_code": us_code,
            "numero_us": str(us_num),
            "anno": extracted.get("anno"),
            
            # Localizzazione (nomi allineati a form schema)
            "localita": extracted.get("localita"),
            "ente_responsabile": extracted.get("ente_responsabile"),
            "area_struttura": extracted.get("area") or extracted.get("area_struttura"),
            "saggio": extracted.get("saggio"),
            "ambiente_unita_funzione": extracted.get("ambiente") or extracted.get("ambiente_unita_funzione"),
            "posizione": extracted.get("posizione"),
            
            # Caratteristiche (nomi allineati a form schema)
            "definizione": extracted.get("definizione"),
            "criteri_distinzione": extracted.get("criteri_distinzione"),
            "modo_formazione": extracted.get("modo_formazione"),
            "descrizione": extracted.get("descrizione"),
            "interpretazione": extracted.get("interpretazione"),
            "tipo": tipo.value if tipo else None,
            
            # Proprietà fisiche
            "stato_conservazione": extracted.get("stato_conservazione"),
            "colore": extracted.get("colore"),
            "consistenza": extracted.get("consistenza"),
            "misure": extracted.get("misure"),
            
            # Componenti (nomi allineati a form schema)
            "componenti_inorganici": extracted.get("componenti", {}).get("inorganici"),
            "componenti_organici": extracted.get("componenti", {}).get("organici"),
            
            # Sequenza stratigrafica (nomi con prefisso seq_ per form schema)
            "seq_copre": list_to_csv(seq.get("copre", [])),
            "seq_coperto_da": list_to_csv(seq.get("coperto_da", [])),
            "seq_si_appoggia_a": list_to_csv(seq.get("si_appoggia_a", [])),
            "seq_gli_si_appoggia": list_to_csv(seq.get("gli_si_appoggia", [])),
            "seq_taglia": list_to_csv(seq.get("taglia", [])),
            "seq_tagliato_da": list_to_csv(seq.get("tagliato_da", [])),
            "seq_riempie": list_to_csv(seq.get("riempie", [])),
            "seq_riempito_da": list_to_csv(seq.get("riempito_da", [])),
            "seq_uguale_a": list_to_csv(seq.get("uguale_a", [])),
            "seq_anteriore_a": list_to_csv(seq.get("anteriore_a", [])),
            "seq_posteriore_a": list_to_csv(seq.get("posteriore_a", [])),
            
            # Documentazione (nomi allineati a form schema)
            "piante_riferimenti": list_to_csv(doc.get("piante", [])),
            "prospetti_riferimenti": list_to_csv(doc.get("prospetti", [])),
            "sezioni_riferimenti": list_to_csv(doc.get("sezioni", [])),
            "fotografie_riferimenti": list_to_csv(doc.get("fotografie", [])),
            
            # Materiali
            "riferimenti_tabelle_materiali": extracted.get("cassetta_materiali"),
            "dati_quantitativi_reperti": extracted.get("dati_quantitativi_reperti"),
            
            # Datazione
            "periodo": extracted.get("periodo"),
            "fase": extracted.get("fase"),
            
            # Responsabili (nomi allineati a form schema)
            "data_rilevamento": extracted.get("data_rilievo"),
            "responsabile_scientifico": extracted.get("responsabile_rilievo"),
        }
    
    def extract_from_pdf(
        self,
        pdf_bytes: bytes,
        filename: str,
        site_id: str,
        include_debug: bool = True
    ) -> Dict[str, Any]:
        """
        Estrae scheda US da PDF usando DeepSeek-OCR.
        
        Args:
            pdf_bytes: contenuto PDF
            filename: nome file
            site_id: ID sito
            include_debug: include dati debug
            
        Returns:
            Dict con risultati estrazione compatibile con API esistente
        """
        start_time = datetime.now()
        
        if not self.is_available():
            return {
                "filename": filename,
                "error": "DeepSeek-OCR service not available",
                "results": [],
                "debug_pages": []
            }
        
        try:
            # Step 1: Render PDF to images
            logger.info(f"Rendering PDF: {filename}")
            pages = self._pdf_to_images(pdf_bytes)
            
            if not pages:
                return {
                    "filename": filename,
                    "error": "No pages in PDF",
                    "results": [],
                    "debug_pages": []
                }
            
            # Step 2: Extract markdown from all pages
            all_markdown = []
            debug_pages = []
            
            for page_data in pages:
                logger.info(f"OCR page {page_data['page_number']}")
                markdown = self._extract_markdown(page_data["image_b64"])
                all_markdown.append(markdown)
                
                if include_debug:
                    debug_pages.append({
                        "page_number": page_data["page_number"],
                        "image_base64": f"data:image/jpeg;base64,{page_data['image_b64']}",
                        "text_lines": markdown.split("\n"),
                        "word_count": len(markdown.split()),
                        "page_size": page_data["size"],
                        "markdown_raw": markdown
                    })
            
            # Step 3: Combine markdown and convert to JSON
            combined_markdown = "\n\n---\n\n".join(all_markdown)
            logger.info("Converting markdown to JSON")
            extracted_json = self._markdown_to_json(combined_markdown)
            
            # Step 4: Map to US model
            us_data = self._map_to_us_model(extracted_json, site_id)
            
            # Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Validate result
            is_valid = bool(us_data.get("numero_us")) and bool(us_data.get("definizione"))
            issues = []
            warnings = []
            
            if not us_data.get("numero_us"):
                issues.append("Numero US non trovato")
            if not us_data.get("definizione"):
                warnings.append("Definizione non trovata")
            if not us_data.get("tipo"):
                warnings.append("Tipo (positiva/negativa) non determinato")
            
            result = {
                "us_code": us_data.get("us_code", "US???"),
                "page_number": 1,
                "confidence": 0.85 if is_valid else 0.5,
                "is_valid": is_valid,
                "issues": issues,
                "warnings": warnings,
                "extracted_fields_count": len([v for v in us_data.values() if v]),
                "data": us_data
            }
            
            return {
                "filename": filename,
                "total_pages": len(pages),
                "successful_extractions": 1 if is_valid else 0,
                "failed_extractions": 0 if is_valid else 1,
                "results": [result],
                "processing_time_seconds": processing_time,
                "debug_pages": debug_pages if include_debug else None,
                "combined_text": combined_markdown,
                "debug": {
                    "ocr_model": self.ocr_model,
                    "llm_model": self.llm_model,
                    "extraction_method": "deepseek-ocr",
                    "raw_json": extracted_json
                }
            }
            
        except Exception as e:
            logger.exception(f"DeepSeek-OCR extraction failed: {e}")
            return {
                "filename": filename,
                "error": str(e),
                "results": [],
                "debug_pages": []
            }


# Singleton
_deepseek_ocr_service: Optional[DeepSeekOCRService] = None


def get_deepseek_ocr_service() -> DeepSeekOCRService:
    """Factory per servizio DeepSeek-OCR."""
    global _deepseek_ocr_service
    if _deepseek_ocr_service is None:
        _deepseek_ocr_service = DeepSeekOCRService()
    return _deepseek_ocr_service


def is_deepseek_ocr_available() -> bool:
    """Verifica se DeepSeek-OCR è disponibile."""
    return OLLAMA_AVAILABLE and PYMUPDF_AVAILABLE and PIL_AVAILABLE
