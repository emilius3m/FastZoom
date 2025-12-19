# app/routes/api/v1/ocr_us_import.py
"""
API v1 - OCR Import US Sheets
Endpoints per importazione schede US da PDF tramite PaddleOCR
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime

from fastapi import (
    APIRouter, 
    Depends, 
    HTTPException, 
    UploadFile, 
    File,
    Form,
    BackgroundTasks,
    Query,
    status
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
from loguru import logger

from app.database.db import get_async_session
from app.core.security import (
    get_current_user_id_with_blacklist,
    get_current_user_sites_with_blacklist,
)
from app.models.stratigraphy import UnitaStratigrafica
from app.services.paddle_ocr_service import (
    get_paddle_ocr_service, 
    is_paddle_ocr_available,
    PaddleOCRService
)


router = APIRouter()


# ===== PYDANTIC MODELS =====

class OCRStatusResponse(BaseModel):
    """Stato del servizio OCR"""
    available: bool
    paddle_ocr_installed: bool
    pdf2image_installed: bool
    gpu_enabled: bool
    message: str


class OCRExtractionResult(BaseModel):
    """Risultato estrazione singola pagina"""
    us_code: str
    page_number: int
    confidence: float
    is_valid: bool
    issues: List[str] = []
    warnings: List[str] = []
    extracted_fields_count: int
    data: Dict[str, Any]


class OCRPageDebug(BaseModel):
    """Debug data per singola pagina OCR"""
    page_number: int
    image_base64: Optional[str] = None
    text_lines: List[str] = []
    bounding_boxes: List[Dict[str, Any]] = []
    word_count: int = 0
    avg_confidence: float = 0.0
    page_size: Optional[tuple] = None
    # PPStructureV3 layout analysis output
    layout_json: Optional[Dict[str, Any]] = None


class OCRBatchResult(BaseModel):
    """Risultato estrazione batch"""
    filename: str
    total_pages: int
    successful_extractions: int
    failed_extractions: int
    results: List[OCRExtractionResult]
    processing_time_seconds: float
    # Debug data for visualization
    debug_pages: Optional[List[OCRPageDebug]] = None
    combined_text: Optional[str] = None
    # Additional debug info (pp_structure_cells, table_detection_method, etc.)
    debug: Optional[Dict[str, Any]] = None





# ===== HELPER FUNCTIONS =====

def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]):
    """Verifica accesso al sito"""
    site_id_str = str(site_id)
    
    # Check using 'site_id' key (standard for user_sites from auth service)
    for site in user_sites:
        user_site_id = str(site.get('site_id', ''))
        if user_site_id == site_id_str:
            return True
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"Non hai accesso al sito {site_id}"
    )


# ===== ENDPOINTS =====

@router.get(
    "/status",
    response_model=OCRStatusResponse,
    summary="Stato servizio OCR",
    description="Verifica disponibilità del servizio OCR PaddleOCR"
)
async def get_ocr_status():
    """
    Verifica lo stato del servizio OCR per l'importazione PDF.
    
    Controlla:
    - Installazione PaddleOCR
    - Installazione PyMuPDF
    - Disponibilità GPU
    """
    try:
        service = get_paddle_ocr_service(use_gpu=False)
        
        from app.services.paddle_ocr_service import PADDLE_OCR_AVAILABLE, PDF2IMAGE_AVAILABLE
        
        available = PADDLE_OCR_AVAILABLE and PDF2IMAGE_AVAILABLE
        
        if available:
            message = "Servizio OCR disponibile (PPStructure mode)"
        elif not PADDLE_OCR_AVAILABLE:
            message = "PaddleOCR non installato. Installa con: pip install paddleocr"
        elif not PDF2IMAGE_AVAILABLE:
            message = "PyMuPDF non installato. Installa con: pip install pymupdf"
        else:
            message = "Servizio OCR non disponibile"
        
        return OCRStatusResponse(
            available=available,
            paddle_ocr_installed=PADDLE_OCR_AVAILABLE,
            pdf2image_installed=PDF2IMAGE_AVAILABLE,
            gpu_enabled=service.use_gpu,
            message=message
        )
    
    except Exception as e:
        logger.error(f"Error checking OCR status: {e}")
        return OCRStatusResponse(
            available=False,
            paddle_ocr_installed=False,
            pdf2image_installed=False,
            gpu_enabled=False,
            message=f"Errore verifica servizio: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/ocr/extract",
    response_model=OCRBatchResult,
    summary="Estrai schede US da PDF",
    description="Estrae schede US da un PDF utilizzando PPStructure per analisi layout"
)
async def extract_us_from_pdf(
    site_id: UUID,
    file: UploadFile = File(..., description="File PDF da processare"),
    use_gpu: bool = Query(True, description="Utilizza GPU se disponibile"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Estrae schede US da un file PDF utilizzando PPStructure.
    
    Il PDF viene analizzato pagina per pagina e i dati vengono estratti
    secondo lo standard MiC 2021 usando PPStructure per l'analisi del layout.
    
    Returns:
        OCRBatchResult con i risultati dell'estrazione
    """
    import time
    start_time = time.time()
    
    # Verifica accesso al sito
    verify_site_access(site_id, user_sites)
    
    # Verifica disponibilità OCR
    if not is_paddle_ocr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servizio OCR non disponibile. Assicurati che PaddleOCR e PyMuPDF siano installati."
        )
    
    # Verifica tipo file
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il file deve essere in formato PDF"
        )
    
    try:
        # Leggi contenuto PDF
        pdf_bytes = await file.read()
        
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Il file PDF è vuoto"
            )
        
        if len(pdf_bytes) > 50 * 1024 * 1024:  # 50MB limit
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Il file PDF è troppo grande (max 50MB)"
            )
        
        logger.info(f"Processing PDF {file.filename} ({len(pdf_bytes)} bytes) for site {site_id}")
        
        # Inizializza servizio OCR
        service = get_paddle_ocr_service(use_gpu=use_gpu)
        
        # Usa PPStructure layout parser
        extraction_result = await service.extract_from_pdf_combined(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            site_id=str(site_id),
            include_debug=True
        )
        us_data = extraction_result.get('us_data')
        debug_info = extraction_result.get('debug', {})
        
        # Build result
        results = []
        debug_pages = []
        
        if us_data:
            validation = service.validate_extraction_result(us_data)
            results.append(OCRExtractionResult(
                us_code=validation['us_code'] or 'UNKNOWN',
                page_number=1,  # Single combined result
                confidence=validation['confidence'],
                is_valid=validation['is_valid'],
                issues=validation['issues'],
                warnings=validation['warnings'],
                extracted_fields_count=validation['extracted_fields_count'],
                data=us_data
            ))
        
        # Build debug pages
        for page_data in debug_info.get('pages', []):
            debug_pages.append(OCRPageDebug(
                page_number=page_data.get('page_number', 0),
                image_base64=page_data.get('image_base64'),
                text_lines=page_data.get('text_lines', []),
                bounding_boxes=page_data.get('bounding_boxes', []),
                word_count=page_data.get('word_count', 0),
                avg_confidence=page_data.get('avg_confidence', 0.0),
                page_size=page_data.get('page_size'),
                layout_json=page_data.get('layout_json')
            ))

        
        processing_time = time.time() - start_time
        total_pages = len(debug_pages) if debug_pages else 1
        
        return OCRBatchResult(
            filename=file.filename,
            total_pages=total_pages,
            successful_extractions=1 if us_data else 0,
            failed_extractions=0 if us_data else 1,
            results=results,
            processing_time_seconds=round(processing_time, 2),
            debug_pages=debug_pages,
            combined_text=debug_info.get('combined_text', ''),
            debug={
                'pp_structure_cells': debug_info.get('pp_structure_cells', []),
                'cell_mapping': debug_info.get('cell_mapping', {}),
                'table_detection_method': debug_info.get('table_detection_method', 'none'),
                'tables_html': debug_info.get('tables_html', []),
                'total_words': debug_info.get('total_words', 0),
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting US from PDF: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'estrazione: {str(e)}"
        )








@router.post(
    "/sites/{site_id}/ocr/extract-v3",
    summary="Estrai schede US con PP-StructureV3",
    description="Estrae usando il nuovo metodo PP-StructureV3 con celle precise"
)
async def extract_us_from_pdf_v3(
    site_id: UUID,
    file: UploadFile = File(..., description="File PDF da processare"),
    use_gpu: bool = Query(False, description="Utilizza GPU se disponibile"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Estrae schede US da PDF utilizzando PP-StructureV3 per estrazione celle.
    
    Metodo alternativo che usa:
    - Coordinate celle precise
    - Supporto merged cells
    - Mapping label -> campo automatico
    """
    import time
    start_time = time.time()
    
    # Verifica accesso
    verify_site_access(site_id, user_sites)
    
    if not is_paddle_ocr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servizio OCR non disponibile"
        )
    
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il file deve essere in formato PDF"
        )
    
    try:
        pdf_bytes = await file.read()
        
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Il file PDF è vuoto"
            )
        
        logger.info(f"Processing PDF {file.filename} via PP-StructureV3 for site {site_id}")
        
        # Use new PP-StructureV3 method
        service = get_paddle_ocr_service(use_gpu=use_gpu)
        result = await service.extract_from_pdf_pp_structure_v3(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            site_id=str(site_id),
            use_gpu=use_gpu,
            include_debug=True
        )
        
        processing_time = time.time() - start_time
        
        # Build response
        us_data = result.get('us_data')
        debug = result.get('debug', {})
        
        return {
            "success": bool(us_data),
            "method": "pp_structure_v3",
            "processing_time_seconds": round(processing_time, 2),
            "us_data": us_data,
            "tables_detected": len(debug.get('tables', [])),
            "cells_extracted": len(debug.get('cells', [])),
            "debug": {
                "tables": debug.get('tables', []),
                "cells": debug.get('cells', [])[:50],  # Limit for response size
                "pages": [
                    {
                        "page_number": p.get('page_number'),
                        "tables_count": p.get('tables_count'),
                        "cells_count": p.get('cells_count'),
                        "page_size": p.get('page_size'),
                        "image_base64": p.get('image_base64'),
                        "visualization": p.get('visualization'),
                    }
                    for p in debug.get('pages', [])
                ]
            },
            "error": result.get('error')
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in PP-StructureV3 extraction: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'estrazione: {str(e)}"
        )

