# app/services/paddle_ocr_service.py
"""
Servizio OCR con PaddleOCR per importazione PDF schede US
Integrazione con modello UnitaStratigrafica esistente (MiC 2021)

Sostituisce Chandra OCR con PaddleOCR per maggiore compatibilità e supporto multilingua
"""

import asyncio
import logging
import re
import io
import os
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime, date

import cv2
import numpy as np
from PIL import Image
from loguru import logger

# GPU mode is now enabled by default since CUDA is properly configured
# Set FASTZOOM_OCR_USE_GPU=0 to force CPU mode if needed
_GPU_MODE_ENABLED = os.environ.get('FASTZOOM_OCR_USE_GPU', '1') == '1'
if not _GPU_MODE_ENABLED:
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    logger.info("PaddleOCR: CUDA disabled (CPU mode forced via FASTZOOM_OCR_USE_GPU=0)")
else:
    logger.info("PaddleOCR: GPU mode enabled")

# Import condizionali per PaddleOCR
try:
    from paddleocr import PaddleOCR
    PADDLE_OCR_AVAILABLE = True
except ImportError:
    PADDLE_OCR_AVAILABLE = False
    logger.warning("PaddleOCR non disponibile. Installa con: pip install paddleocr")

# Import PPStructure per table recognition (nuovo API: PPStructureV3)
try:
    from paddleocr import PPStructureV3 as PPStructure
    PP_STRUCTURE_AVAILABLE = True
except ImportError:
    try:
        from paddleocr import PPStructure
        PP_STRUCTURE_AVAILABLE = True
    except ImportError:
        PP_STRUCTURE_AVAILABLE = False
        logger.warning("PPStructure non disponibile per table recognition")

# Import PyMuPDF per conversione PDF
try:
    import fitz  # PyMuPDF
    PDF2IMAGE_AVAILABLE = True
except ImportError:
    PDF2IMAGE_AVAILABLE = False
    logger.warning("PyMuPDF non disponibile. Installa con: pip install pymupdf")

from app.models.stratigraphy import TipoUSEnum, ConsistenzaEnum, AffidabilitaEnum



class PaddleOCRService:
    """Servizio OCR per schede US con PaddleOCR - integrato con FastZoom"""
    
    def __init__(self, use_gpu: bool = False, languages: List[str] = None):
        """
        Inizializza il servizio OCR
        
        Args:
            use_gpu: Utilizzare GPU (se disponibile)
            languages: Lingue da supportare (default: italiano + inglese)
        """
        self.languages = languages or ['it', 'en']
        self.use_gpu = use_gpu
        
        # Inizializza il modello PaddleOCR (lazy loading)
        self.ocr_model = None
        self._model_loaded = False
        
        # PPStructure per table detection (lazy loading)
        self._table_engine = None
        self._table_engine_loaded = False
        
        device_name = "GPU" if self.use_gpu else "CPU"
        logger.info(f"PaddleOCRService initialized (Device: {device_name}, Languages: {self.languages})")
    
    @property
    def is_available(self) -> bool:
        """Verifica se il servizio è disponibile"""
        return PADDLE_OCR_AVAILABLE and PDF2IMAGE_AVAILABLE
    
    def _ensure_model_loaded(self):
        """Carica il modello al primo utilizzo (lazy loading)"""
        if not PADDLE_OCR_AVAILABLE:
            raise RuntimeError(
                "PaddleOCR non installato. "
                "Installa con: pip install paddleocr paddlepaddle"
            )
        
        if self.ocr_model is None:
            # Note: GPU mode is controlled at module import time via FASTZOOM_OCR_USE_GPU env var
            # Once the module is loaded, the device is fixed (CUDA disabled = CPU only)
            device_mode = "GPU (if available)" if _GPU_MODE_ENABLED else "CPU"
            logger.info(f"Loading PaddleOCR model ({device_mode})...")
            
            try:
                self.ocr_model = PaddleOCR(
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False
                )
                self._model_loaded = True
                logger.info(f"PaddleOCR model loaded successfully ({device_mode})")
            except Exception as e:
                logger.error(f"Error loading PaddleOCR model: {e}")
                raise
    
    def _ensure_table_engine_loaded(self):
        """Carica PPStructureV3 per document structure analysis al primo utilizzo."""
        if not PP_STRUCTURE_AVAILABLE:
            logger.warning("PPStructureV3 non disponibile per document analysis")
            return False
        
        if self._table_engine is None:
            device_mode = "GPU" if self.use_gpu else "CPU"
            logger.info(f"Loading PPStructureV3 pipeline ({device_mode})...")
            
            try:
                # PPStructureV3 API corretta secondo documentazione ufficiale:
                # https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PP-StructureV3.html
                device = "gpu" if self.use_gpu else "cpu"
                self._table_engine = PPStructure(
                    device=device,
                    use_doc_orientation_classify=True,  # Abilita classificazione orientamento
                    use_doc_unwarping=False,            # Disabilita unwarping per velocità
                    use_textline_orientation=False      # Disabilita orientamento righe testo
                )
                self._table_engine_loaded = True
                logger.info(f"PPStructureV3 pipeline loaded successfully ({device_mode})")
                return True
            except Exception as e:
                logger.error(f"Error loading PPStructureV3: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return False
        return True

    


    



    
    def preprocess_image(self, image: Image.Image) -> np.ndarray:
        """
        Preprocessa l'immagine per migliorare l'OCR
        
        Passi:
        - Conversione a scala di grigi
        - Ridimensionamento (evita problemi di memoria)
        - Miglioramento contrasto con CLAHE
        - Riduzione rumore con bilateral filter
        
        Args:
            image: PIL Image
            
        Returns:
            numpy array preprocessato (BGR per compatibilità OpenCV)
        """
        # Converti PIL a OpenCV (BGR)
        cv_image = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
        
        # Scala di grigi
        gray = cv2.cvtColor(cv_image, cv2.COLOR_BGR2GRAY)
        
        # Ridimensiona se troppo grande (max 4096px di larghezza)
        height, width = gray.shape
        if width > 4096:
            scale = 4096 / width
            new_height = int(height * scale)
            gray = cv2.resize(gray, (4096, new_height), interpolation=cv2.INTER_AREA)
        
        # Migliora contrasto con CLAHE (Contrast Limited Adaptive Histogram Equalization)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
        
        # Riduzione rumore (bilateral filter preserva i bordi)
        denoised = cv2.bilateralFilter(gray, 9, 75, 75)
        
        # Converti di nuovo a BGR per PaddleOCR
        bgr_image = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
        
        return bgr_image
    

    
    async def extract_from_pdf(
        self, 
        pdf_bytes: bytes, 
        filename: str,
        site_id: str
    ) -> List[Dict]:
        """
        Estrae UNA sola US da un PDF multi-pagina (scheda completa).
        Compatibile con la firma precedente (ritorna List[Dict]).
        
        Un PDF multi-pagina (es. scheda US a 2 pagine) produce UN SOLO record.
        Usa extract_from_pdf_combined() internamente per:
        - OCR di tutte le pagine
        - Merge bounding boxes con y-offset
        - Layout parser per campi core/checkbox
        - Text parser per campi aggiuntivi
        
        Args:
            pdf_bytes: Contenuto PDF
            filename: Nome file
            site_id: ID del cantiere archeologico
            
        Returns:
            Lista con UN SOLO dict mappato su UnitaStratigrafica (o lista vuota)
        """
        combined = await self.extract_from_pdf_combined(
            pdf_bytes=pdf_bytes,
            filename=filename,
            site_id=site_id,
            include_debug=False,
        )
        us_data = combined.get("us_data")
        return [us_data] if us_data else []
    

    


    async def extract_from_pdf_combined(
        self, 
        pdf_bytes: bytes, 
        filename: str,
        site_id: str,
        include_debug: bool = True
    ) -> Dict:
        """
        Estrae UNA singola US da PDF multi-pagina.
        
        Strategy Update (Fix Scaling): 
        Renderizza le pagine in immagini (zoom 2.5) e passa quelle a PPStructure.
        Questo garantisce che le coordinate OCR siano 1:1 con l'immagine di debug.
        
        Args:
            pdf_bytes: Contenuto PDF
            filename: Nome file
            site_id: ID del cantiere
            include_debug: Se includere immagini/boxes per debug viewer
            
        Returns:
            Dict con:
            - us_data: dati US parsati (o None)
            - debug: {pages: [{image_base64, text_lines, bounding_boxes, layout_json}...]}
        """
        import base64
        import tempfile
        import numpy as np
        import cv2
        
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError("PyMuPDF (fitz) required for rendering")
            
        # Ensure PPStructure engine is loaded
        if not self._ensure_table_engine_loaded():
            raise RuntimeError("Impossibile caricare PPStructureV3")
        
        result = {
            'us_data': None,
            'debug': {
                'pages': [],
                'combined_text': '',
                'total_words': 0
            }
        }
        
        try:
            logger.info(f"Processing PDF {filename} via Rendered Images (zoom=2.5) for precise alignment...")
            
            # Open PDF with PyMuPDF
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            all_page_texts = []
            all_boxes = []
            all_pp_cells = []
            all_tables_html = []
            
            y_offset = 0
            total_height = 0
            max_width = 0
            
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                
                # 1. RENDER IMAGE (Controlled Zoom)
                zoom = 2.5
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                # Convert to numpy for PPStructure
                img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                # Ensure RGB (PPStructure expects RGB or BGR, usually robust)
                if pix.n == 4: # RGBA
                    img_data = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
                elif pix.n == 3: # RGB
                    img_data = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR) # OpenCV uses BGR
                
                # 2. PREDICT ON IMAGE
                # input can be ndarray
                pp_results = list(self._table_engine.predict(img_data))
                
                # Extract page results (usually just 1 result per image)
                page_texts = []
                page_boxes = []
                layout_json = {
                    'parsing_res_list': [],
                    'tables': [],
                    'overall_ocr_res': {},
                    'raw_json': {}
                }
                
                if pp_results:
                    page_result = pp_results[0]
                    
                    # Extract JSON
                    page_json = {}
                    if hasattr(page_result, 'json'):
                        page_json = page_result.json if isinstance(page_result.json, dict) else {}
                    
                    layout_json['raw_json'] = page_json
                    
                    if page_json.get('res') and isinstance(page_json['res'], dict):
                        overall_ocr = page_json['res'].get('overall_ocr_res', {})
                        layout_json['overall_ocr_res'] = overall_ocr
                        
                        # Texts & Boxes
                        rec_texts = overall_ocr.get('rec_texts', [])
                        rec_polys = overall_ocr.get('rec_polys', [])
                        rec_scores = overall_ocr.get('rec_scores', [])
                        
                        # Normalize to list
                        if hasattr(rec_texts, 'tolist'): rec_texts = rec_texts.tolist()
                        if hasattr(rec_polys, 'tolist'): rec_polys = rec_polys.tolist()
                        if hasattr(rec_scores, 'tolist'): rec_scores = rec_scores.tolist()
                        
                        for i, text in enumerate(rec_texts):
                            if not text or not str(text).strip(): continue
                            text_str = str(text).strip()
                            page_texts.append(text_str)
                            all_page_texts.append(text_str)
                            
                            conf = 0.9
                            if i < len(rec_scores) and rec_scores[i] is not None:
                                try: conf = float(rec_scores[i])
                                except: pass
                            
                            poly = []
                            if i < len(rec_polys) and rec_polys[i] is not None:
                                try:
                                    p = rec_polys[i]
                                    if hasattr(p, 'tolist'): p = p.tolist()
                                    # Coordinates are already in image space (1:1)
                                    poly = [[float(pt[0]), float(pt[1])] for pt in p]
                                except: pass
                            
                            page_boxes.append({
                                'text': text_str,
                                'confidence': conf,
                                'polygon': poly
                            })
                            
                        # Tables
                        page_cells = []
                        table_res_list = page_json['res'].get('table_res_list', [])
                        for table in table_res_list:
                            if isinstance(table, dict):
                                if table.get('pred_html'):
                                    all_tables_html.append(table['pred_html'])
                                for i, cell_box in enumerate(table.get('cell_box_list', [])):
                                    if len(cell_box) >= 4:
                                        # Global cells (for layout parser)
                                        all_pp_cells.append({
                                            'x1': float(cell_box[0]),
                                            'y1': float(cell_box[1]) + y_offset,
                                            'x2': float(cell_box[2]),
                                            'y2': float(cell_box[3]) + y_offset,
                                            'cell_index': i,
                                            'page': page_num,
                                            'bbox': [float(cell_box[0]), float(cell_box[1]), float(cell_box[2]), float(cell_box[3])]
                                        })
                                        # Page-local cells (for debug viewer)
                                        page_cells.append({
                                            'x1': float(cell_box[0]),
                                            'y1': float(cell_box[1]),
                                            'x2': float(cell_box[2]),
                                            'y2': float(cell_box[3]),
                                            'cell_index': i
                                        })

                                layout_json['tables'].append({
                                    'pred_html': table.get('pred_html', ''),
                                    'cell_box_list': table.get('cell_box_list', []),
                                    'table_ocr_pred': table.get('table_ocr_pred', {})
                                })
                
                # 3. DEBUG INFO
                debug_info = {}
                if include_debug:
                    # Use the same pixmap -> exact match
                    img_bytes = pix.tobytes("png")
                    img_b64 = base64.b64encode(img_bytes).decode('utf-8')
                    
                    debug_info = {
                        'page_number': page_num + 1,
                        'image_base64': f"data:image/png;base64,{img_b64}",
                        'text_lines': page_texts,
                        'bounding_boxes': page_boxes, # 1:1 coordinates
                        'cells': page_cells, # PPStructure cells (local coordinates)
                        'word_count': len(page_texts),
                        'avg_confidence': 0.9, # simplified
                        'page_size': (pix.width, pix.height),
                        'layout_json': layout_json
                    }
                    result['debug']['pages'].append(debug_info)
                
                # Update global offsets
                max_width = max(max_width, pix.width)
                
                # Add boxes to global list (with Y offset)
                for box in page_boxes:
                    adjusted_box = {
                        'text': box['text'],
                        'confidence': box['confidence'],
                        'polygon': []
                    }
                    if box.get('polygon'):
                        adjusted_box['polygon'] = [
                            [pt[0], pt[1] + y_offset] for pt in box['polygon']
                        ]
                    all_boxes.append(adjusted_box)
                
                y_offset += pix.height
                total_height += pix.height
                logger.info(f"Page {page_num+1} processed. Size: {pix.width}x{pix.height}, Text blocks: {len(page_boxes)}")
            
            pdf_document.close()
            
            # STEP 5: COMBINE & PARSE
            combined_text = '\n'.join(all_page_texts)
            result['debug']['combined_text'] = combined_text
            result['debug']['total_words'] = len(all_page_texts)
            
            # Table detection summary
            if all_pp_cells:
                logger.info(f"✓ PPStructure detected {len(all_pp_cells)} cells")
                logger.debug(f"Cell coordinates: {all_pp_cells[:3]}...")  # Log first 3 cells
                result['debug']['table_detection_method'] = 'ppstructure'
                result['debug']['pp_structure_cells'] = all_pp_cells
                result['debug']['tables_html'] = all_tables_html
            else:
                logger.warning("⚠ PPStructure did not detect any table cells")
                result['debug']['table_detection_method'] = 'none'
            
            # Layout Parser
            from app.services.us_layout_parser import get_us_layout_parser
            
            layout_parser = get_us_layout_parser()
            us_data = layout_parser.parse_core(
                all_boxes,
                site_id=site_id,
                page_size=(max_width, total_height),
                detected_cells=all_pp_cells
            )
            
            # Expose PPStructure cells for debug viewer
            result['debug']['pp_structure_cells'] = all_pp_cells

            if us_data and us_data.get('us_code'):
                us_data['_pdf_source'] = filename
                us_data['_total_pages'] = len(result['debug']['pages'])
                us_data['_raw_ocr_text'] = combined_text
                
                # Expose cell mapping for highlighting
                result['debug']['cell_mapping'] = us_data.get('_cell_mapping', {})
                
                result['us_data'] = us_data
                logger.info(f"✓ Parsed US: {us_data.get('us_code', 'unknown')} (Image-based PPStructure)")
            else:
                logger.warning("No US data could be parsed from combined pages")
            
            return result
        
        except Exception as e:
            logger.error(f"Error in extract_from_pdf_combined: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
    def validate_extraction_result(self, us_data: Dict) -> Dict[str, Any]:
        """
        Valida il risultato dell'estrazione OCR
        
        Returns:
            Dict con info di validazione
        """
        issues = []
        warnings = []
        
        # Campo obbligatorio
        if not us_data.get('us_code'):
            issues.append("Codice US mancante")
        
        # Campi raccomandati
        recommended_fields = [
            'definizione', 'descrizione', 'datazione', 
            'responsabile_scientifico', 'data_rilevamento'
        ]
        for field in recommended_fields:
            if not us_data.get(field):
                warnings.append(f"Campo raccomandato mancante: {field}")
        
        # Sequenza fisica
        sequenza = us_data.get('sequenza_fisica', {})
        has_relations = any(v for v in sequenza.values() if v)
        if not has_relations:
            warnings.append("Nessuna relazione stratigrafica rilevata")
        
        # Confidence
        confidence = us_data.get('_extraction_confidence', 0)
        if confidence < 0.7:
            warnings.append(f"Confidence OCR bassa: {confidence:.1%}")
        
        return {
            'is_valid': len(issues) == 0,
            'issues': issues,
            'warnings': warnings,
            'confidence': confidence,
            'us_code': us_data.get('us_code'),
            'extracted_fields_count': len([k for k, v in us_data.items() if v and not k.startswith('_')])
        }

# Singleton
# Separate singletons for CPU and GPU modes
_paddle_ocr_service_cpu: Optional[PaddleOCRService] = None
_paddle_ocr_service_gpu: Optional[PaddleOCRService] = None


def get_paddle_ocr_service(use_gpu: bool = False) -> PaddleOCRService:
    """
    Factory per servizio PaddleOCR US
    
    Args:
        use_gpu: True=forza GPU, False=forza CPU (default CPU per compatibilità)
    
    Returns:
        PaddleOCRService instance (cached per mode)
    """
    global _paddle_ocr_service_cpu, _paddle_ocr_service_gpu
    
    if use_gpu:
        if _paddle_ocr_service_gpu is None:
            _paddle_ocr_service_gpu = PaddleOCRService(use_gpu=True)
        return _paddle_ocr_service_gpu
    else:
        if _paddle_ocr_service_cpu is None:
            _paddle_ocr_service_cpu = PaddleOCRService(use_gpu=False)
        return _paddle_ocr_service_cpu


def is_paddle_ocr_available() -> bool:
    """Verifica se PaddleOCR è disponibile"""
    return PADDLE_OCR_AVAILABLE and PDF2IMAGE_AVAILABLE
