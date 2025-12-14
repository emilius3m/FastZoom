# app/routes/api/v1/ocr_debug.py
"""
API endpoint per debug visuale OCR con PaddleOCR
"""

import base64
import io
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, UploadFile, File, HTTPException, status, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from loguru import logger

import cv2
import numpy as np
from PIL import Image

from app.services.paddle_ocr_service import get_paddle_ocr_service, is_paddle_ocr_available
from app.services.us_parser import get_us_parser

# Template setup
templates = Jinja2Templates(directory="app/templates")

router = APIRouter(prefix="/ocr", tags=["OCR Debug"])


@router.get(
    "/debug",
    response_class=HTMLResponse,
    summary="Pagina Debug OCR",
    description="Interfaccia web per debug visuale PaddleOCR"
)
async def debug_page(request: Request):
    """Serve la pagina HTML del debug viewer"""
    return templates.TemplateResponse("ocr_debug.html", {"request": request})


class OCRDebugResult(BaseModel):
    """Risultato debug OCR"""
    success: bool
    image_base64: Optional[str] = None
    image_width: int = 0
    image_height: int = 0
    raw_text: str = ""
    text_lines: list = []
    bounding_boxes: list = []
    parsed_data: Optional[dict] = None
    error: Optional[str] = None


@router.post(
    "/debug",
    response_model=OCRDebugResult,
    summary="Debug OCR Visuale",
    description="Elabora immagine/PDF e ritorna risultati con bounding boxes per visualizzazione"
)
async def debug_ocr(
    file: UploadFile = File(...),
    page_number: int = 0
):
    """
    Endpoint per debug visuale OCR.
    
    Ritorna:
    - Immagine base64 con overlay bounding boxes
    - Testo estratto (raw e linee separate)
    - Bounding boxes con coordinate
    - Dati US parsati (se trovati)
    """
    if not is_paddle_ocr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servizio OCR non disponibile"
        )
    
    try:
        # Leggi file
        file_bytes = await file.read()
        filename = file.filename or "unknown"
        
        service = get_paddle_ocr_service()
        
        # Determina tipo file
        is_pdf = filename.lower().endswith('.pdf')
        
        if is_pdf:
            # Converti PDF in immagine
            import fitz
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            
            if page_number >= len(pdf_doc):
                page_number = 0
            
            page = pdf_doc[page_number]
            zoom = 2.0  # 144 DPI
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pdf_doc.close()
        else:
            # Carica immagine
            pil_image = Image.open(io.BytesIO(file_bytes))
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
        
        # Preprocessing
        processed_cv = service.preprocess_image(pil_image)
        
        # OCR
        service._ensure_model_loaded()
        import asyncio
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: service.ocr_model.predict(processed_cv)
        )
        
        # Estrai dati
        extracted_text = []
        confidences = []
        bounding_boxes = []
        
        if results and len(results) > 0:
            ocr_result = results[0]
            
            if hasattr(ocr_result, 'get'):
                rec_texts = ocr_result.get('rec_texts', None)
                rec_scores = ocr_result.get('rec_scores', None)
                rec_polys = ocr_result.get('rec_polys', None)
                
                # Converti a lista
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
                    
                    extracted_text.append(text_str)
                    
                    # Confidence
                    conf = 0.9
                    if i < len(rec_scores):
                        try:
                            score_val = rec_scores[i]
                            if hasattr(score_val, 'item'):
                                conf = float(score_val.item())
                            elif score_val is not None:
                                conf = float(score_val)
                        except:
                            pass
                    confidences.append(conf)
                    
                    # Polygon/Box
                    poly = []
                    if i < len(rec_polys) and rec_polys[i] is not None:
                        try:
                            p = rec_polys[i]
                            if hasattr(p, 'tolist'):
                                p = p.tolist()
                            poly = [[float(pt[0]), float(pt[1])] for pt in p]
                        except:
                            pass
                    
                    bounding_boxes.append({
                        'text': text_str,
                        'confidence': conf,
                        'polygon': poly
                    })
        
        # Crea immagine con overlay
        overlay_cv = processed_cv.copy()
        
        # Colori per i box
        colors = [
            (0, 255, 0),    # Verde
            (255, 0, 0),    # Blu
            (0, 0, 255),    # Rosso
            (255, 255, 0),  # Cyan
            (255, 0, 255),  # Magenta
            (0, 255, 255),  # Giallo
        ]
        
        for i, box in enumerate(bounding_boxes):
            if box['polygon']:
                pts = np.array(box['polygon'], dtype=np.int32)
                color = colors[i % len(colors)]
                cv2.polylines(overlay_cv, [pts], True, color, 2)
                
                # Label
                if len(pts) > 0:
                    x, y = int(pts[0][0]), int(pts[0][1])
                    label = f"{i+1}"
                    cv2.putText(overlay_cv, label, (x, y-5), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # Converti a base64
        _, buffer = cv2.imencode('.png', overlay_cv)
        img_base64 = base64.b64encode(buffer).decode('utf-8')
        img_base64 = f"data:image/png;base64,{img_base64}"
        
        # Parse US data
        full_text = '\n'.join(extracted_text)
        us_parser = get_us_parser()
        parsed_data = us_parser.parse_us_sheet(
            text=full_text,
            site_id="debug",
            filename=filename
        )
        
        # Rimuovi campo raw_ocr_text dal parsed (troppo lungo)
        if parsed_data and '_raw_ocr_text' in parsed_data:
            del parsed_data['_raw_ocr_text']
        
        return OCRDebugResult(
            success=True,
            image_base64=img_base64,
            image_width=overlay_cv.shape[1],
            image_height=overlay_cv.shape[0],
            raw_text=full_text,
            text_lines=extracted_text,
            bounding_boxes=bounding_boxes,
            parsed_data=parsed_data
        )
        
    except Exception as e:
        logger.error(f"OCR Debug error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return OCRDebugResult(
            success=False,
            error=str(e)
        )
