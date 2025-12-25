# app/routes/api/v1/ocr_debug.py
"""
API endpoint per debug visuale OCR (legacy - ora usa DeepSeek-OCR)

DEPRECATO: Questo endpoint usava PaddleOCR per il debug visuale.
Ora il sistema usa DeepSeek-OCR via Ollama.
Per debug, usa il tab "DeepSeek-OCR Raw" nel Debug Viewer.
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

# Note: PaddleOCR è stato rimosso - questo endpoint è deprecato
# from app.services.paddle_ocr_service import get_paddle_ocr_service, is_paddle_ocr_available
from app.services.deepseek_ocr_service import get_deepseek_ocr_service, is_deepseek_ocr_available

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
    summary="Debug OCR Visuale (DEPRECATO)",
    description="DEPRECATO: Ora usa DeepSeek-OCR. Per debug, usa il tab 'DeepSeek-OCR Raw' nel Debug Viewer."
)
async def debug_ocr(
    file: UploadFile = File(...),
    page_number: int = 0
):
    """
    Endpoint per debug visuale OCR.
    
    DEPRECATO: Questo endpoint usava PaddleOCR.
    Ora restituisce un messaggio di deprecazione.
    Usa il Debug Viewer nel frontend per debug DeepSeek-OCR.
    """
    return OCRDebugResult(
        success=False,
        error="DEPRECATO: Questo endpoint non è più disponibile. Usa il tab 'DeepSeek-OCR Raw' nel Debug Viewer per visualizzare l'output OCR."
    )

