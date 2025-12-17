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
from app.services.us_parser import get_us_parser


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

    
    def analyze_page_structure(self, image: np.ndarray) -> Dict[str, Any]:
        """
        Analizza la struttura della pagina usando PPStructureV3.
        Restituisce l'output JSON completo con layout, tabelle e testo.
        
        Args:
            image: numpy array BGR (da OpenCV)
            
        Returns:
            Dict con struttura completa della pagina secondo API PPStructureV3:
            {
                'parsing_res_list': [...],  # Elementi layout con block_label, block_content, block_bbox
                'tables': [...],            # Tabelle con pred_html, cell_box_list, table_ocr_pred
                'overall_ocr_res': {...},   # Risultati OCR globali: rec_texts, rec_polys, rec_scores
                'raw_json': {...}           # Output JSON completo da res.json
            }
        """
        if not self._ensure_table_engine_loaded():
            return {'parsing_res_list': [], 'tables': [], 'overall_ocr_res': {}, 'raw_json': {}}
        
        try:
            # Esegui PPStructureV3 sulla pagina
            # predict() restituisce un generatore, convertiamo in lista
            results = list(self._table_engine.predict(image))
            
            if not results:
                logger.warning("PPStructureV3 returned empty results")
                return {'parsing_res_list': [], 'tables': [], 'overall_ocr_res': {}, 'raw_json': {}}
            
            # Prendi il primo risultato (per immagine singola)
            res = results[0]
            
            # Estrai dati strutturati secondo API PPStructureV3
            output = {
                'parsing_res_list': [],
                'tables': [],
                'overall_ocr_res': {},
                'raw_json': {}
            }
            
            # Estrai JSON completo tramite attributo .json
            if hasattr(res, 'json'):
                raw_json = res.json
                output['raw_json'] = raw_json if isinstance(raw_json, dict) else {}
                logger.info(f"PPStructureV3 raw_json keys: {list(output['raw_json'].keys())[:10]}")
                
                # DEBUG: Log attributi disponibili sul risultato
                res_attrs = [attr for attr in dir(res) if not attr.startswith('_')]
                logger.info(f"PPStructureV3 result attributes: {res_attrs[:15]}")
            
            # Estrai parsing_res_list (layout blocks con contenuto)
            parsing_res_list = None
            if hasattr(res, 'parsing_res_list') and res.parsing_res_list:
                parsing_res_list = res.parsing_res_list
            elif output['raw_json'].get('res') and isinstance(output['raw_json']['res'], dict):
                # Fallback: estrai da raw_json['res']
                parsing_res_list = output['raw_json']['res'].get('parsing_res_list', [])
            
            if parsing_res_list:
                for block in parsing_res_list:
                    if isinstance(block, dict):
                        block_bbox = block.get('block_bbox')
                        if block_bbox is not None:
                            if hasattr(block_bbox, 'tolist'):
                                block_bbox = block_bbox.tolist()
                            else:
                                block_bbox = list(block_bbox) if block_bbox else []
                        
                        output['parsing_res_list'].append({
                            'block_label': block.get('block_label', ''),
                            'block_content': block.get('block_content', ''),
                            'block_bbox': block_bbox,
                            'block_id': block.get('block_id', 0),
                            'block_order': block.get('block_order')
                        })
                logger.info(f"PPStructureV3 found {len(output['parsing_res_list'])} layout blocks")
            
            # Estrai tabelle tramite table_res_list
            table_res_list = None
            if hasattr(res, 'table_res_list') and res.table_res_list:
                table_res_list = res.table_res_list
            elif output['raw_json'].get('res') and isinstance(output['raw_json']['res'], dict):
                # Fallback: estrai da raw_json['res']
                table_res_list = output['raw_json']['res'].get('table_res_list', [])
            
            if table_res_list:
                for table in table_res_list:
                    if isinstance(table, dict):
                        table_data = {
                            'pred_html': table.get('pred_html', ''),
                            'cell_box_list': [],
                            'table_ocr_pred': {}
                        }
                        
                        # Estrai celle
                        cell_boxes = table.get('cell_box_list', [])
                        for cell_box in cell_boxes:
                            if hasattr(cell_box, 'tolist'):
                                table_data['cell_box_list'].append(cell_box.tolist())
                            elif cell_box is not None:
                                table_data['cell_box_list'].append(list(cell_box))
                        
                        # Estrai OCR delle celle
                        table_ocr = table.get('table_ocr_pred', {})
                        if isinstance(table_ocr, dict):
                            table_data['table_ocr_pred'] = {
                                'rec_texts': list(table_ocr.get('rec_texts', [])) if table_ocr.get('rec_texts') else [],
                                'rec_scores': [float(s) for s in table_ocr.get('rec_scores', [])] if table_ocr.get('rec_scores') else [],
                                'rec_polys': [p.tolist() if hasattr(p, 'tolist') else list(p) for p in table_ocr.get('rec_polys', [])] if table_ocr.get('rec_polys') else []
                            }
                        
                        output['tables'].append(table_data)
                        logger.info(f"Table found: {len(table_data['cell_box_list'])} cells, HTML len: {len(table_data['pred_html'])}")
            
            # Estrai OCR globale tramite overall_ocr_res
            overall_ocr_res = None
            if hasattr(res, 'overall_ocr_res') and res.overall_ocr_res:
                overall_ocr_res = res.overall_ocr_res
            elif output['raw_json'].get('res') and isinstance(output['raw_json']['res'], dict):
                # Fallback: estrai da raw_json['res']
                overall_ocr_res = output['raw_json']['res'].get('overall_ocr_res', {})
            
            if overall_ocr_res and isinstance(overall_ocr_res, dict):
                output['overall_ocr_res'] = {
                    'rec_texts': list(overall_ocr_res.get('rec_texts', [])) if overall_ocr_res.get('rec_texts') else [],
                    'rec_scores': [float(s) for s in overall_ocr_res.get('rec_scores', [])] if overall_ocr_res.get('rec_scores') else [],
                    'rec_polys': [p.tolist() if hasattr(p, 'tolist') else list(p) for p in overall_ocr_res.get('rec_polys', [])] if overall_ocr_res.get('rec_polys') else []
                }
                logger.info(f"OCR found {len(output['overall_ocr_res']['rec_texts'])} text regions")
            
            logger.info(f"PPStructureV3 analysis complete: {len(output['parsing_res_list'])} blocks, {len(output['tables'])} tables")
            
            return output

            
        except Exception as e:
            logger.error(f"Error in PPStructureV3 page analysis: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {'parsing_res_list': [], 'tables': [], 'overall_ocr_res': {}, 'raw_json': {}}

    
    def detect_table_structure(self, image: np.ndarray) -> List[Dict[str, Any]]:
        """
        Rileva la struttura delle tabelle nell'immagine usando PPStructure.
        Wrapper per retrocompatibilità - usa analyze_page_structure internamente.
        
        Args:
            image: numpy array BGR (da OpenCV)
            
        Returns:
            Lista di celle con coordinate {x1, y1, x2, y2, cell_index}
        """
        page_struct = self.analyze_page_structure(image)
        cells = []
        
        for table in page_struct.get('tables', []):
            for i, cell_box in enumerate(table.get('cell_box_list', [])):
                if len(cell_box) >= 4:
                    cells.append({
                        'x1': float(cell_box[0]),
                        'y1': float(cell_box[1]),
                        'x2': float(cell_box[2]),
                        'y2': float(cell_box[3]),
                        'cell_index': i
                    })
        
        return cells


    
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
    
    async def _run_ocr(self, image: np.ndarray) -> List:
        """
        Esegue OCR in background thread per non bloccare l'event loop
        
        Args:
            image: numpy array BGR
            
        Returns:
            Risultati OCR raw
        """
        loop = asyncio.get_event_loop()
        # PaddleOCR 3.x: usa .predict() invece di .ocr()
        results = await loop.run_in_executor(
            None,
            lambda: self.ocr_model.predict(image)
        )
        return results
    
    def _extract_text_from_results(self, results: List, save_debug: bool = True, page_num: int = 0) -> Dict:
        """
        Estrae testo e confidenza dai risultati PaddleOCR 3.x
        
        PaddleOCR 3.x restituisce una lista di OCRResult objects con:
        - rec_texts: lista di testi riconosciuti
        - rec_scores: lista di confidenze
        - rec_boxes: lista di bounding boxes (opzionale)
        
        Args:
            results: output raw da PaddleOCR.predict()
            save_debug: salva output OCR in file markdown per debug
            page_num: numero pagina per naming file debug
            
        Returns:
            Dict con text, confidence, bounding_boxes
        """
        extracted_text = []
        confidences = []
        bounding_boxes = []
        
        try:
            if results and len(results) > 0:
                ocr_result = results[0]  # OCRResult object
                
                # PaddleOCR 3.x: OCRResult è un dict-like object
                if hasattr(ocr_result, 'get') or hasattr(ocr_result, 'keys'):
                    # Nuova API PaddleOCR 3.x
                    rec_texts = ocr_result.get('rec_texts', None)
                    rec_scores = ocr_result.get('rec_scores', None)
                    rec_boxes = ocr_result.get('rec_boxes', None)
                    
                    # Converti a lista Python se necessario
                    if rec_texts is not None:
                        if hasattr(rec_texts, 'tolist'):
                            rec_texts = rec_texts.tolist()
                        elif not isinstance(rec_texts, list):
                            rec_texts = list(rec_texts)
                    else:
                        rec_texts = []
                    
                    if rec_scores is not None:
                        if hasattr(rec_scores, 'tolist'):
                            rec_scores = rec_scores.tolist()
                        elif not isinstance(rec_scores, list):
                            rec_scores = list(rec_scores)
                    else:
                        rec_scores = []
                    
                    logger.debug(f"OCRResult 3.x format: {len(rec_texts)} texts, {len(rec_scores)} scores")
                    
                    # Estrai testi
                    for i, text_val in enumerate(rec_texts):
                        # Converti a stringa
                        if text_val is None:
                            continue
                        text_str = str(text_val).strip()
                        if not text_str:
                            continue
                        
                        extracted_text.append(text_str)
                        
                        # Confidence
                        if i < len(rec_scores):
                            try:
                                score_val = rec_scores[i]
                                if hasattr(score_val, 'item'):
                                    conf = float(score_val.item())
                                elif score_val is not None:
                                    conf = float(score_val)
                                else:
                                    conf = 0.9
                                confidences.append(conf)
                            except:
                                confidences.append(0.9)
                        else:
                            confidences.append(0.9)
                        
                        # Bounding box
                        bbox = []
                        if rec_boxes is not None and i < len(rec_boxes):
                            try:
                                box_val = rec_boxes[i]
                                if box_val is not None:
                                    if hasattr(box_val, 'tolist'):
                                        box_val = box_val.tolist()
                                    if len(box_val) > 0:
                                        bbox = [[float(x), float(y)] for x, y in box_val]
                            except:
                                pass
                        
                        bounding_boxes.append({
                            'text': text_str,
                            'confidence': confidences[-1] if confidences else 0.0,
                            'bbox': bbox
                        })
                
                # Fallback: vecchio formato lista di liste
                elif isinstance(ocr_result, list):
                    for line in ocr_result:
                        if len(line) >= 2:
                            bbox = line[0]
                            text_info = line[1]
                            
                            if isinstance(text_info, tuple) and len(text_info) >= 2:
                                text = str(text_info[0])
                                confidence = float(text_info[1])
                                
                                extracted_text.append(text)
                                confidences.append(confidence)
                                bounding_boxes.append({
                                    'text': text,
                                    'confidence': confidence,
                                    'bbox': [[float(x), float(y)] for x, y in bbox] if bbox else []
                                })
        except Exception as e:
            logger.error(f"Error extracting text from OCR results: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Costruisci testo completo mettendo ogni elemento su riga separata (come nella scheda)
        full_text = '\n'.join(extracted_text)
        avg_confidence = float(np.mean(confidences)) if confidences else 0.0
        
        # SALVA DEBUG IN MARKDOWN
        if save_debug and extracted_text:
            self._save_debug_markdown(extracted_text, confidences, page_num)
        
        return {
            'text': full_text,
            'confidence': avg_confidence,
            'bounding_boxes': bounding_boxes,
            'word_count': len(extracted_text)
        }
    
    def _save_debug_markdown(self, texts: List[str], confidences: List[float], page_num: int):
        """Salva output OCR in file markdown per debug"""
        import os
        from datetime import datetime
        
        # Crea cartella debug se non esiste
        debug_dir = Path("ocr_debug_output")
        debug_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = debug_dir / f"ocr_page_{page_num}_{timestamp}.md"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# OCR Output - Page {page_num}\n\n")
            f.write(f"**Timestamp:** {datetime.now().isoformat()}\n\n")
            f.write(f"**Total words extracted:** {len(texts)}\n\n")
            f.write(f"**Average confidence:** {np.mean(confidences) if confidences else 0:.2f}\n\n")
            f.write("---\n\n")
            f.write("## Raw Text (line by line)\n\n")
            f.write("```\n")
            for i, (text, conf) in enumerate(zip(texts, confidences)):
                f.write(f"{text}\n")
            f.write("```\n\n")
            f.write("---\n\n")
            f.write("## Text with Confidence\n\n")
            f.write("| # | Text | Confidence |\n")
            f.write("|---|------|------------|\n")
            for i, (text, conf) in enumerate(zip(texts, confidences)):
                f.write(f"| {i+1} | {text[:50]}{'...' if len(text)>50 else ''} | {conf:.2f} |\n")
        
        logger.info(f"OCR debug saved to: {filename}")
    
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
        Estrae UNA singola US da PDF multi-pagina (tutte le pagine = 1 US)
        Include dati debug per visualizzazione
        
        Args:
            pdf_bytes: Contenuto PDF
            filename: Nome file
            site_id: ID del cantiere
            include_debug: Se includere immagini/boxes per debug
            
        Returns:
            Dict con:
            - us_data: dati US parsati (o None)
            - debug: {pages: [{image_base64, text_lines, bounding_boxes}...]}
        """
        import base64
        
        if not PDF2IMAGE_AVAILABLE:
            raise RuntimeError("PyMuPDF non installato")
        
        self._ensure_model_loaded()
        
        result = {
            'us_data': None,
            'debug': {
                'pages': [],
                'combined_text': '',
                'total_words': 0
            }
        }
        
        try:
            logger.info(f"Converting PDF {filename} to images (combined mode)...")
            
            pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
            all_page_texts = []
            
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                zoom = 2.5  # Lower for faster processing
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat)
                
                pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                
                # Preprocess
                processed_cv = self.preprocess_image(pil_image)
                
                # OCR
                results = await self._run_ocr(processed_cv)
                
                # Extract text and boxes
                page_texts = []
                page_boxes = []
                page_confidences = []
                
                if results and len(results) > 0:
                    ocr_result = results[0]
                    
                    if hasattr(ocr_result, 'get'):
                        rec_texts = ocr_result.get('rec_texts', None)
                        rec_scores = ocr_result.get('rec_scores', None)
                        rec_polys = ocr_result.get('rec_polys', None)
                        
                        # Convert to lists
                        if rec_texts is not None:
                            if hasattr(rec_texts, 'tolist'):
                                rec_texts = rec_texts.tolist()
                            elif not isinstance(rec_texts, list):
                                rec_texts = list(rec_texts)
                        else:
                            rec_texts = []
                        
                        if rec_scores is not None:
                            if hasattr(rec_scores, 'tolist'):
                                rec_scores = rec_scores.tolist()
                            elif not isinstance(rec_scores, list):
                                rec_scores = list(rec_scores)
                        else:
                            rec_scores = []
                        
                        if rec_polys is not None:
                            if hasattr(rec_polys, 'tolist'):
                                rec_polys = rec_polys.tolist()
                            elif not isinstance(rec_polys, list):
                                rec_polys = list(rec_polys)
                        else:
                            rec_polys = []
                        
                        for i, text_val in enumerate(rec_texts):
                            if text_val is None:
                                continue
                            text_str = str(text_val).strip()
                            if not text_str:
                                continue
                            
                            page_texts.append(text_str)
                            
                            conf = 0.9
                            if i < len(rec_scores):
                                try:
                                    sv = rec_scores[i]
                                    if hasattr(sv, 'item'):
                                        conf = float(sv.item())
                                    elif sv is not None:
                                        conf = float(sv)
                                except:
                                    pass
                            page_confidences.append(conf)
                            
                            poly = []
                            if i < len(rec_polys) and rec_polys[i] is not None:
                                try:
                                    p = rec_polys[i]
                                    if hasattr(p, 'tolist'):
                                        p = p.tolist()
                                    poly = [[float(pt[0]), float(pt[1])] for pt in p]
                                except:
                                    pass
                            
                            page_boxes.append({
                                'text': text_str,
                                'confidence': conf,
                                'polygon': poly
                            })
                
                all_page_texts.extend(page_texts)
                
                # --- PPStructure LAYOUT ANALYSIS ---
                # Esegui PPStructure per ottenere JSON struttura pagina
                page_structure = self.analyze_page_structure(processed_cv)
                
                # Include debug data with CLEAN image (boxes rendered as SVG overlay in frontend)
                if include_debug:
                    # Convert clean image to base64 (no boxes drawn - interactive SVG overlay in frontend)
                    _, buffer = cv2.imencode('.png', processed_cv)
                    img_b64 = base64.b64encode(buffer).decode('utf-8')
                    
                    result['debug']['pages'].append({
                        'page_number': page_num + 1,
                        'image_base64': f"data:image/png;base64,{img_b64}",
                        'text_lines': page_texts,
                        'bounding_boxes': page_boxes,
                        'word_count': len(page_texts),
                        'avg_confidence': sum(page_confidences)/len(page_confidences) if page_confidences else 0,
                        'page_size': (pix.width, pix.height),  # Store page size for layout parser
                        # PPStructureV3 JSON output per pagina
                        'layout_json': {
                            'parsing_res_list': page_structure.get('parsing_res_list', []),
                            'tables': page_structure.get('tables', []),
                            'overall_ocr_res': page_structure.get('overall_ocr_res', {}),
                            'raw_json': page_structure.get('raw_json', {})
                        }
                    })
                
                logger.info(f"Page {page_num + 1}: extracted {len(page_texts)} text blocks, {len(page_structure.get('parsing_res_list', []))} layout blocks")


            
            pdf_document.close()
            
            # Combine all text and parse as single US
            combined_text = '\n'.join(all_page_texts)
            result['debug']['combined_text'] = combined_text
            result['debug']['total_words'] = len(all_page_texts)
            
            logger.info(f"Combined text from {len(result['debug']['pages'])} pages: {len(all_page_texts)} words")
            
            # --- LAYOUT-AWARE PARSING ---
            # Combine all bounding boxes from all pages (with y-offset for multi-page)
            from app.services.us_layout_parser import get_us_layout_parser
            from app.services.table_grid_detector import get_table_grid_detector
            
            all_boxes = []
            y_offset = 0
            total_height = 0
            max_width = 0
            all_cells = []  # Grid cells from all pages
            
            for page_info in result['debug']['pages']:
                page_w, page_h = page_info.get('page_size', (1000, 1400))
                max_width = max(max_width, page_w)
                
                for box in page_info.get('bounding_boxes', []):
                    # Adjust y coordinates for page offset
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
                
                y_offset += page_h
                total_height += page_h
            
            # --- TABLE GRID DETECTION ---
            # Usa l'output layout_json già calcolato da PPStructure per ogni pagina
            # Raccogli tutte le celle dalle tabelle trovate
            all_pp_cells = []
            all_tables_html = []
            
            for page_info in result['debug']['pages']:
                layout_json = page_info.get('layout_json', {})
                tables = layout_json.get('tables', [])
                
                for table in tables:
                    # Salva HTML tabella per debug (PPStructureV3 usa pred_html)
                    if table.get('pred_html'):
                        all_tables_html.append(table['pred_html'])
                    
                    # Estrai celle (PPStructureV3 usa cell_box_list)
                    for i, cell_box in enumerate(table.get('cell_box_list', [])):
                        if len(cell_box) >= 4:
                            all_pp_cells.append({
                                'x1': float(cell_box[0]),
                                'y1': float(cell_box[1]),
                                'x2': float(cell_box[2]),
                                'y2': float(cell_box[3]),
                                'cell_index': i
                            })

            
            if all_pp_cells:
                logger.info(f"PPStructure extracted {len(all_pp_cells)} cells from {len(all_tables_html)} tables")
                result['debug']['table_detection_method'] = 'ppstructure'
                result['debug']['pp_structure_cells'] = all_pp_cells
                result['debug']['tables_html'] = all_tables_html
            else:
                # FALLBACK: Grid detector Hough-based se PPStructure non trova tabelle
                logger.info("PPStructure found no tables, falling back to Hough grid detector")
                try:
                    if result['debug']['pages']:
                        first_page = result['debug']['pages'][0]
                        first_page_img_b64 = first_page.get('image_base64', '')
                        
                        if first_page_img_b64:
                            img_data = first_page_img_b64.split(',')[1] if ',' in first_page_img_b64 else first_page_img_b64
                            img_bytes = base64.b64decode(img_data)
                            img_array = np.frombuffer(img_bytes, np.uint8)
                            page_image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
                            
                            if page_image is not None:
                                from app.services.table_grid_detector import get_table_grid_detector
                                grid_detector = get_table_grid_detector()
                                detected_cells, debug_grid_img = grid_detector.detect_grid(page_image, debug=include_debug)
                                logger.info(f"Grid detection: found {len(detected_cells)} cells")
                                result['debug']['table_detection_method'] = 'hough_grid'
                                
                                if detected_cells:
                                    first_page_boxes = first_page.get('bounding_boxes', [])
                                    cell_contents = grid_detector.associate_text_to_cells(detected_cells, first_page_boxes)
                                    result['debug']['grid_cells'] = [
                                        {
                                            'row': c.row, 'col': c.col,
                                            'x1': c.x1, 'y1': c.y1, 'x2': c.x2, 'y2': c.y2,
                                            'text': grid_detector.get_cell_text(cell_contents, i)
                                        }
                                        for i, c in enumerate(detected_cells)
                                    ]
                                    all_pp_cells = result['debug']['grid_cells']
                except Exception as e:
                    logger.warning(f"Grid detection fallback failed: {e}")
            
            # Collect cells for layout parser
            cells_for_parser = all_pp_cells
            
            # Use layout parser for core fields (with PPStructure cell grid info)
            layout_parser = get_us_layout_parser()
            us_data = layout_parser.parse_core(
                all_boxes,
                site_id=site_id,
                page_size=(max_width, total_height),
                detected_cells=cells_for_parser
            )

            
            # Always run text parser to fill non-core fields
            # Layout parser handles: us_code, area_edificio, ambiente, quote, tipo (checkbox)
            # Text parser fills: descrizione, osservazioni, interpretazione, datazione, reperti, etc.
            text_parser = get_us_parser()
            text_data = text_parser.parse_us_sheet(
                text=combined_text,
                site_id=site_id,
                filename=filename
            )
            
            # Merge: layout parser "wins" on core fields, text parser fills the rest
            if text_data:
                for key, value in text_data.items():
                    # Don't overwrite existing values from layout parser
                    if key not in us_data or not us_data.get(key):
                        us_data[key] = value
                logger.info(f"Merged {len(text_data)} fields from text parser")
            
            if us_data and us_data.get('us_code'):
                us_data['_pdf_source'] = filename
                us_data['_total_pages'] = len(result['debug']['pages'])
                us_data['_raw_ocr_text'] = combined_text  # Keep for debug/QA
                result['us_data'] = us_data
                logger.info(f"✓ Parsed US: {us_data.get('us_code', 'unknown')} (layout parser + text parser merge)")
            else:
                logger.warning("No US data could be parsed from combined pages")
            
            return result
            
        except Exception as e:
            logger.error(f"Error in extract_from_pdf_combined: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    async def extract_from_image(
        self,
        image_bytes: bytes,
        filename: str,
        site_id: str
    ) -> Optional[Dict]:
        """
        Estrae scheda US da singola immagine
        
        Args:
            image_bytes: Contenuto immagine
            filename: Nome file
            site_id: ID del cantiere
            
        Returns:
            Dict mappato su UnitaStratigrafica o None
        """
        self._ensure_model_loaded()
        
        try:
            # Carica immagine
            image = Image.open(io.BytesIO(image_bytes))
            
            # Preprocessa
            processed_image = self.preprocess_image(image)
            
            # Esegui OCR
            results = await self._run_ocr(processed_image)
            
            # Estrai testo
            ocr_result = self._extract_text_from_results(results)
            
            # DEBUG: Log extracted text
            logger.info(f"Image OCR - Extracted text (first 500 chars): {ocr_result['text'][:500] if ocr_result['text'] else 'EMPTY'}")
            logger.info(f"Image OCR - Word count: {ocr_result['word_count']}, Confidence: {ocr_result['confidence']:.2f}")
            
            # Usa il parser avanzato per schede US MiC
            us_parser = get_us_parser()
            us_data = us_parser.parse_us_sheet(
                text=ocr_result['text'],
                site_id=site_id,
                filename=filename
            )
            
            # Aggiungi metadata OCR
            if us_data:
                us_data['_extraction_confidence'] = ocr_result['confidence']
                us_data['_page_number'] = 1
            
            return us_data
            
        except Exception as e:
            logger.error(f"Error extracting from image: {e}")
            raise
    
    def _map_to_unita_stratigrafica(
        self, 
        ocr_data: Dict,
        site_id: str,
        filename: str
    ) -> Optional[Dict]:
        """
        Mappa output OCR al modello UnitaStratigrafica
        Rispetta struttura scheda US-3.doc standard MiC 2021
        
        Returns:
            Dict pronto per creare UnitaStratigrafica o None
        """
        text = ocr_data.get('text', '')
        
        # ===== IDENTIFICAZIONE US (OBBLIGATORIO) =====
        us_match = re.search(
            r'(?:US|U\.S\.|Unità\s+Stratigrafic[oa])[\s:]*(\\d+)',
            text,
            re.IGNORECASE
        )
        if not us_match:
            return None
        
        us_code = f"US{us_match.group(1).zfill(3)}"  # US003
        
        # Inizializza dict mappato
        us_data: Dict[str, Any] = {
            'site_id': site_id,
            'us_code': us_code,
        }
        
        # ===== TIPOLOGIA US =====
        tipo = TipoUSEnum.POSITIVA.value  # Default
        tipo_patterns = {
            TipoUSEnum.NEGATIVA.value: r'\b(?:negativa|taglio|asporto|fossa)\b',
            TipoUSEnum.POSITIVA.value: r'\b(?:positiva|accumulo|deposito|strato)\b'
        }
        for tipo_val, pattern in tipo_patterns.items():
            if re.search(pattern, text, re.IGNORECASE):
                tipo = tipo_val
                break
        us_data['tipo'] = tipo
        
        # ===== INTESTAZIONE =====
        # Ente responsabile
        ente_match = re.search(
            r'(?:ente|responsabile|soprintendenza)[\s:]*([^\n]{10,200})',
            text,
            re.IGNORECASE
        )
        if ente_match:
            us_data['ente_responsabile'] = ente_match.group(1).strip()
        
        # Anno
        anno_match = re.search(r'(?:anno|year)[\s:]*(\d{4})', text, re.IGNORECASE)
        if anno_match:
            us_data['anno'] = int(anno_match.group(1))
        
        # Ufficio MiC
        ufficio_match = re.search(
            r'(?:ufficio\s+mic|ufficio)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if ufficio_match:
            us_data['ufficio_mic'] = ufficio_match.group(1).strip()
        
        # Identificativo riferimento
        rif_match = re.search(
            r'(?:identificativo|riferimento|id)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if rif_match:
            us_data['identificativo_rif'] = rif_match.group(1).strip()
        
        # ===== LOCALIZZAZIONE =====
        # Località
        loc_patterns = [
            r'(?:località|localita|location)[\s:]*([^\n]{5,200})',
            r'(?:comune|municipality)[\s:]*([^\n]{5,200})'
        ]
        for pattern in loc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['localita'] = match.group(1).strip()
                break
        
        # Area/Struttura
        area_match = re.search(
            r'(?:area|struttura|settore)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if area_match:
            us_data['area_struttura'] = area_match.group(1).strip()
        
        # Saggio
        saggio_match = re.search(r'(?:saggio|trench)[\s:]*([^\n]{3,100})', text, re.IGNORECASE)
        if saggio_match:
            us_data['saggio'] = saggio_match.group(1).strip()
        
        # Ambiente/Unità/Funzione
        amb_match = re.search(
            r'(?:ambiente|unità|funzione)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if amb_match:
            us_data['ambiente_unita_funzione'] = amb_match.group(1).strip()
        
        # Posizione
        pos_match = re.search(r'(?:posizione|position)[\s:]*([^\n]{5,200})', text, re.IGNORECASE)
        if pos_match:
            us_data['posizione'] = pos_match.group(1).strip()
        
        # Settori
        settori_match = re.search(
            r'(?:settori?|grid)[\s:]*([A-Z0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if settori_match:
            us_data['settori'] = settori_match.group(1).strip()
        
        # ===== DOCUMENTAZIONE (riferimenti testuali) =====
        # Piante
        piante_match = re.search(
            r'(?:piante?|plan)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if piante_match:
            us_data['piante_riferimenti'] = f"TAV. {piante_match.group(1)}"
        
        # Sezioni
        sezioni_match = re.search(
            r'(?:sezioni?|section)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if sezioni_match:
            us_data['sezioni_riferimenti'] = f"TAV. {sezioni_match.group(1)}"
        
        # Prospetti
        prospetti_match = re.search(
            r'(?:prospetti?|elevation)[\s:]*(?:TAV\.?\s*)?([0-9, -]+)',
            text,
            re.IGNORECASE
        )
        if prospetti_match:
            us_data['prospetti_riferimenti'] = f"TAV. {prospetti_match.group(1)}"
        
        # ===== DEFINIZIONE E CARATTERIZZAZIONE =====
        # Definizione
        def_patterns = [
            r'(?:definizione|definition)[\s:]*([^\n]{20,500})',
            r'(?:tipo\s+di\s+us|us\s+type)[\s:]*([^\n]{20,500})'
        ]
        for pattern in def_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['definizione'] = match.group(1).strip()
                break
        
        # Criteri di distinzione
        criteri_match = re.search(
            r'(?:criteri?\s+di\s+distinzione|criteria)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if criteri_match:
            us_data['criteri_distinzione'] = criteri_match.group(1).strip()
        
        # Modo di formazione
        formazione_match = re.search(
            r'(?:modo\s+di\s+formazione|formation)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if formazione_match:
            us_data['modo_formazione'] = formazione_match.group(1).strip()
        
        # ===== COMPONENTI =====
        # Componenti inorganici
        inorg_patterns = [
            r'(?:componenti?\s+inorganic[oi]|elementi?\s+fittil[oi]|elementi?\s+lapide[oi])[\s:]*([^\n]{20,500})',
            r'(?:materiale?\s+ceramic[oa]|framment[oi]\s+ceramic[oi])[\s:]*([^\n]{20,500})'
        ]
        for pattern in inorg_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['componenti_inorganici'] = match.group(1).strip()
                break
        
        # Componenti organici
        org_match = re.search(
            r'(?:componenti?\s+organic[oi]|ossa|ossei)[\s:]*([^\n]{20,500})',
            text,
            re.IGNORECASE
        )
        if org_match:
            us_data['componenti_organici'] = org_match.group(1).strip()
        
        # ===== PROPRIETÀ FISICHE =====
        # Consistenza (Enum)
        consistenza_map = {
            ConsistenzaEnum.COMPATTA.value: r'\bcompatt[oa]\b',
            ConsistenzaEnum.MEDIA.value: r'\bmedi[oa]\b',
            ConsistenzaEnum.FRIABILE.value: r'\bfriabile\b',
            ConsistenzaEnum.MOLTO_FRIABILE.value: r'\bmolto\s+friabile\b',
            ConsistenzaEnum.SCIOLTA.value: r'\bscioltt?[oa]\b'
        }
        for cons_val, pattern in consistenza_map.items():
            if re.search(pattern, text, re.IGNORECASE):
                us_data['consistenza'] = cons_val
                break
        
        # Colore
        colori = [
            'grigio', 'marrone', 'bruno', 'rosso', 'nero', 'giallo',
            'arancione', 'bianco', 'beige', 'rossastro', 'grigiastro',
            'scuro', 'chiaro'
        ]
        colore_text = []
        for colore in colori:
            if re.search(rf'\b{colore}\b', text, re.IGNORECASE):
                colore_text.append(colore)
        if colore_text:
            us_data['colore'] = ' '.join(colore_text[:3])  # Max 3 colori
        
        # Misure
        misure_patterns = [
            r'(?:misure|dimensioni|dimensions)[\s:]*([0-9x,. m]+)',
            r'(\d+(?:\.\d+)?\s*x\s*\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?)?\s*m)'
        ]
        for pattern in misure_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['misure'] = match.group(1).strip()
                break
        
        # Stato di conservazione
        cons_patterns = [
            r'(?:stato\s+di\s+conservazione|conservation)[\s:]*([^\n]{10,200})',
            r'(?:conservazione)[\s:]*([^\n]{10,200})'
        ]
        for pattern in cons_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['stato_conservazione'] = match.group(1).strip()
                break
        
        # ===== SEQUENZA FISICA (MATRIX HARRIS) =====
        sequenza_fisica: Dict[str, List[str]] = {
            "uguale_a": [],
            "si_lega_a": [],
            "gli_si_appoggia": [],
            "si_appoggia_a": [],
            "coperto_da": [],
            "copre": [],
            "tagliato_da": [],
            "taglia": [],
            "riempito_da": [],
            "riempie": []
        }
        
        # Estrai relazioni
        relations_map = {
            "copre": [
                r'(?:copre|covers|sta\s+sopra\s+a)[\s:]*(?:US\s*)?([0-9, ]+)',
                r'(?:above)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "coperto_da": [
                r'(?:coperto\s+da|covered\s+by|è\s+sotto\s+a)[\s:]*(?:US\s*)?([0-9, ]+)',
                r'(?:below)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "taglia": [
                r'(?:taglia|cuts)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "tagliato_da": [
                r'(?:tagliato\s+da|cut\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "riempie": [
                r'(?:riempie|fills)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "riempito_da": [
                r'(?:riempito\s+da|filled\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "uguale_a": [
                r'(?:uguale\s+a|equals|same\s+as)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "si_lega_a": [
                r'(?:si\s+lega\s+a|bonds\s+to)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "si_appoggia_a": [
                r'(?:si\s+appoggia\s+a|leans\s+on)[\s:]*(?:US\s*)?([0-9, ]+)'
            ],
            "gli_si_appoggia": [
                r'(?:gli\s+si\s+appoggia|is\s+leaned\s+on\s+by)[\s:]*(?:US\s*)?([0-9, ]+)'
            ]
        }
        
        for rel_type, patterns in relations_map.items():
            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    # Estrai numeri US
                    us_numbers = re.findall(r'\d+', match)
                    for num in us_numbers:
                        us_ref = f"US{num.zfill(3)}"
                        if us_ref not in sequenza_fisica[rel_type]:
                            sequenza_fisica[rel_type].append(us_ref)
        
        us_data['sequenza_fisica'] = sequenza_fisica
        
        # ===== DESCRIZIONE E INTERPRETAZIONE =====
        # Descrizione completa
        desc_patterns = [
            r'(?:descrizione|description)[\s:]*([^\n]{50,2000})',
            r'(?:caratteristiche)[\s:]*([^\n]{50,2000})'
        ]
        for pattern in desc_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['descrizione'] = match.group(1).strip()
                break
        
        # Osservazioni
        oss_match = re.search(
            r'(?:osservazioni|observations|note)[\s:]*([^\n]{20,1000})',
            text,
            re.IGNORECASE
        )
        if oss_match:
            us_data['osservazioni'] = oss_match.group(1).strip()
        
        # Interpretazione
        interp_match = re.search(
            r'(?:interpretazione|interpretation)[\s:]*([^\n]{20,1000})',
            text,
            re.IGNORECASE
        )
        if interp_match:
            us_data['interpretazione'] = interp_match.group(1).strip()
        
        # ===== DATAZIONE E REPERTI =====
        # Datazione
        dat_patterns = [
            r'(?:datazione|dating|cronologia)[\s:]*([^\n]{10,200})',
            r'(?:secolo|century)\s+([IVX]+(?:\s*[-–]\s*[IVX]+)?)',
            r'(\d{1,4}\s*[aA]\.?[cC]\.?\s*[-–]\s*\d{1,4}\s*[dD]\.?[cC]\.?)',
            r'(\d{1,4}\s*[aA]\.?[cC]\.?|\d{1,4}\s*[dD]\.?[cC]\.?)'
        ]
        for pattern in dat_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                us_data['datazione'] = match.group(1).strip()
                break
        
        # Periodo
        periodo_match = re.search(
            r'(?:periodo|period)[\s:]*([^\n]{5,100})',
            text,
            re.IGNORECASE
        )
        if periodo_match:
            us_data['periodo'] = periodo_match.group(1).strip()
        
        # Fase
        fase_match = re.search(r'(?:fase|phase)[\s:]*([^\n]{3,50})', text, re.IGNORECASE)
        if fase_match:
            us_data['fase'] = fase_match.group(1).strip()
        
        # Elementi datanti
        elem_match = re.search(
            r'(?:elementi?\s+datant[ei]|dating\s+elements?)[\s:]*([^\n]{10,500})',
            text,
            re.IGNORECASE
        )
        if elem_match:
            us_data['elementi_datanti'] = elem_match.group(1).strip()
        
        # Dati quantitativi reperti
        reperti_patterns = [
            r'(?:reperti|finds)[\s:]*([^\n]{10,500})',
            r'(\d+\s+(?:frammenti?|fragments?).*?(?:ceramic[ao]|pottery))',
            r'(\d+\s+(?:ossa|bones?))'
        ]
        reperti_text = []
        for pattern in reperti_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            reperti_text.extend(matches)
        if reperti_text:
            us_data['dati_quantitativi_reperti'] = '; '.join(reperti_text[:5])
        
        # ===== CAMPIONATURE =====
        campionature = {
            "flottazione": bool(re.search(r'\bflottazione\b', text, re.IGNORECASE)),
            "setacciatura": bool(re.search(r'\bsetacciatur[ao]\b', text, re.IGNORECASE))
        }
        us_data['campionature'] = campionature
        
        # ===== AFFIDABILITÀ E RESPONSABILITÀ =====
        # Affidabilità
        aff_map = {
            AffidabilitaEnum.ALTA.value: r'\balta\b',
            AffidabilitaEnum.MEDIA.value: r'\bmedi[ao]\b',
            AffidabilitaEnum.BASSA.value: r'\bbassa\b'
        }
        for aff_val, pattern in aff_map.items():
            if re.search(pattern, text, re.IGNORECASE):
                us_data['affidabilita_stratigrafica'] = aff_val
                break
        
        # Responsabile scientifico
        resp_sci_match = re.search(
            r'(?:responsabile\s+scientifico|director)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if resp_sci_match:
            us_data['responsabile_scientifico'] = resp_sci_match.group(1).strip()
        
        # Data rilevamento
        data_ril_match = re.search(
            r'(?:data\s+rilevamento)[\s:]*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
            text,
            re.IGNORECASE
        )
        if data_ril_match:
            try:
                date_str = data_ril_match.group(1)
                parsed = self._parse_date(date_str)
                if parsed:
                    us_data['data_rilevamento'] = parsed.isoformat()
            except Exception:
                pass
        
        # Responsabile compilazione
        resp_comp_match = re.search(
            r'(?:responsabile\s+compilazione|compiled\s+by)[\s:]*([^\n]{5,200})',
            text,
            re.IGNORECASE
        )
        if resp_comp_match:
            us_data['responsabile_compilazione'] = resp_comp_match.group(1).strip()
        
        # Store raw OCR text for reference
        us_data['_raw_ocr_text'] = text[:2000]  # First 2000 chars
        us_data['_extraction_confidence'] = ocr_data.get('confidence', 0.0)
        us_data['_pdf_source'] = filename
        us_data['_page_number'] = ocr_data.get('page_number', 1)
        
        return us_data
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats"""
        formats = ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except Exception:
                continue
        return None
    
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
