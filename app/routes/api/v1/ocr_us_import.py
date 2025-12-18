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


class USImportPreviewItem(BaseModel):
    """Anteprima singola US da importare"""
    us_code: str
    tipo: str
    confidence: float
    is_valid: bool
    issues: List[str]
    warnings: List[str]
    preview_data: Dict[str, Any]


class USImportPreviewResponse(BaseModel):
    """Risposta anteprima importazione"""
    filename: str
    site_id: str
    total_sheets: int
    valid_sheets: int
    invalid_sheets: int
    items: List[USImportPreviewItem]


class USImportConfirmRequest(BaseModel):
    """Richiesta conferma importazione"""
    items_to_import: List[str] = Field(
        ..., 
        description="Lista di us_code da importare"
    )
    overwrite_existing: bool = Field(
        False,
        description="Sovrascrivi US esistenti con stesso codice"
    )


class USImportConfirmResponse(BaseModel):
    """Risposta conferma importazione"""
    imported_count: int
    skipped_count: int
    error_count: int
    imported_us: List[str]
    skipped_us: List[str]
    errors: List[Dict[str, str]]


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
    "/sites/{site_id}/ocr/preview",
    response_model=USImportPreviewResponse,
    summary="Anteprima importazione US da PDF",
    description="Analizza PDF e mostra anteprima delle schede US da importare"
)
async def preview_us_import(
    site_id: UUID,
    file: UploadFile = File(..., description="File PDF da analizzare"),
    use_gpu: bool = Query(True, description="Utilizza GPU se disponibile"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Analizza un PDF e restituisce un'anteprima delle schede US estratte.
    
    L'anteprima include:
    - Validazione preliminare
    - Verifica duplicati nel database
    - Dati estratti con confidence
    
    Utile per revisione prima dell'importazione effettiva.
    """
    # Verifica accesso al sito
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
        
        service = get_paddle_ocr_service(use_gpu=use_gpu)
        extracted_sheets = await service.extract_from_pdf(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            site_id=str(site_id)
        )
        
        # Verifica US esistenti nel sito
        existing_us_codes = set()
        result = await db.execute(
            select(UnitaStratigrafica.us_code)
            .where(UnitaStratigrafica.site_id == str(site_id))
        )
        existing_us_codes = {row[0] for row in result.fetchall()}
        
        items = []
        for sheet in extracted_sheets:
            validation = service.validate_extraction_result(sheet)
            us_code = sheet.get('us_code', 'UNKNOWN')
            
            # Aggiungi warning per duplicati
            if us_code in existing_us_codes:
                validation['warnings'].append(
                    f"US {us_code} già esistente nel sito"
                )
            
            # Crea anteprima con campi principali
            preview_data = {
                'us_code': us_code,
                'tipo': sheet.get('tipo'),
                'definizione': sheet.get('definizione', '')[:200] if sheet.get('definizione') else None,
                'localita': sheet.get('localita'),
                'datazione': sheet.get('datazione'),
                'responsabile_scientifico': sheet.get('responsabile_scientifico'),
                'sequenza_fisica_count': sum(
                    len(v) for v in sheet.get('sequenza_fisica', {}).values() if v
                )
            }
            
            items.append(USImportPreviewItem(
                us_code=us_code,
                tipo=sheet.get('tipo', 'positiva'),
                confidence=validation['confidence'],
                is_valid=validation['is_valid'],
                issues=validation['issues'],
                warnings=validation['warnings'],
                preview_data=preview_data
            ))
        
        valid_count = len([i for i in items if i.is_valid])
        
        return USImportPreviewResponse(
            filename=file.filename,
            site_id=str(site_id),
            total_sheets=len(items),
            valid_sheets=valid_count,
            invalid_sheets=len(items) - valid_count,
            items=items
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in preview import: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'anteprima: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/ocr/import",
    response_model=USImportConfirmResponse,
    summary="Importa schede US da dati OCR",
    description="Importa schede US precedentemente estratte da PDF"
)
async def import_us_from_ocr(
    site_id: UUID,
    file: UploadFile = File(..., description="File PDF da importare"),
    items_to_import: str = Form(
        default="all",
        description="Lista US da importare (JSON array) o 'all' per tutte"
    ),
    overwrite_existing: bool = Form(
        default=False,
        description="Sovrascrivi US esistenti"
    ),
    use_gpu: bool = Query(True, description="Utilizza GPU"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Importa schede US estratte da PDF nel database.
    
    Workflow:
    1. Estrae schede dal PDF
    2. Valida ogni scheda
    3. Importa solo quelle specificate (o tutte se 'all')
    4. Opzionalmente sovrascrive US esistenti
    """
    import json
    
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
        
        service = get_paddle_ocr_service(use_gpu=use_gpu)
        extracted_sheets = await service.extract_from_pdf(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            site_id=str(site_id)
        )
        
        # Parse items to import
        if items_to_import == "all":
            codes_to_import = None  # Import all valid
        else:
            try:
                codes_to_import = set(json.loads(items_to_import))
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="items_to_import deve essere 'all' o un JSON array valido"
                )
        
        # Get existing US
        result = await db.execute(
            select(UnitaStratigrafica)
            .where(UnitaStratigrafica.site_id == str(site_id))
        )
        existing_us = {us.us_code: us for us in result.scalars().all()}
        
        imported_us = []
        skipped_us = []
        errors = []
        
        for sheet in extracted_sheets:
            us_code = sheet.get('us_code')
            
            # Skip if not in import list
            if codes_to_import is not None and us_code not in codes_to_import:
                skipped_us.append(us_code)
                continue
            
            # Validate
            validation = service.validate_extraction_result(sheet)
            if not validation['is_valid']:
                errors.append({
                    'us_code': us_code,
                    'error': '; '.join(validation['issues'])
                })
                continue
            
            try:
                # Check if exists
                if us_code in existing_us:
                    if overwrite_existing:
                        # Update existing
                        existing = existing_us[us_code]
                        for key, value in sheet.items():
                            if not key.startswith('_') and hasattr(existing, key):
                                setattr(existing, key, value)
                        imported_us.append(us_code)
                    else:
                        skipped_us.append(us_code)
                else:
                    # Create new
                    # Remove internal fields
                    us_data = {
                        k: v for k, v in sheet.items() 
                        if not k.startswith('_')
                    }
                    
                    new_us = UnitaStratigrafica(**us_data)
                    db.add(new_us)
                    imported_us.append(us_code)
            
            except Exception as e:
                errors.append({
                    'us_code': us_code,
                    'error': str(e)
                })
        
        await db.commit()
        
        logger.info(
            f"OCR Import completed for site {site_id}: "
            f"imported={len(imported_us)}, skipped={len(skipped_us)}, errors={len(errors)}"
        )
        
        return USImportConfirmResponse(
            imported_count=len(imported_us),
            skipped_count=len(skipped_us),
            error_count=len(errors),
            imported_us=imported_us,
            skipped_us=skipped_us,
            errors=errors
        )
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing US from OCR: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'importazione: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/ocr/extract-image",
    response_model=OCRExtractionResult,
    summary="Estrai scheda US da immagine singola",
    description="Estrae una scheda US da un'immagine (JPG, PNG, TIFF)"
)
async def extract_us_from_image(
    site_id: UUID,
    file: UploadFile = File(..., description="File immagine da processare"),
    use_gpu: bool = Query(True, description="Utilizza GPU se disponibile"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Estrae una scheda US da un'immagine singola (scan, foto).
    
    Formati supportati: JPG, PNG, TIFF, BMP
    """
    verify_site_access(site_id, user_sites)
    
    if not is_paddle_ocr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servizio OCR non disponibile"
        )
    
    allowed_extensions = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome file mancante"
        )
    
    ext = '.' + file.filename.lower().split('.')[-1] if '.' in file.filename else ''
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato non supportato. Usa: {', '.join(allowed_extensions)}"
        )
    
    try:
        image_bytes = await file.read()
        
        service = get_paddle_ocr_service(use_gpu=use_gpu)
        extracted_data = await service.extract_from_image(
            image_bytes=image_bytes,
            filename=file.filename,
            site_id=str(site_id)
        )
        
        if not extracted_data:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Nessuna scheda US rilevata nell'immagine"
            )
        
        validation = service.validate_extraction_result(extracted_data)
        
        return OCRExtractionResult(
            us_code=validation['us_code'] or 'UNKNOWN',
            page_number=1,
            confidence=validation['confidence'],
            is_valid=validation['is_valid'],
            issues=validation['issues'],
            warnings=validation['warnings'],
            extracted_fields_count=validation['extracted_fields_count'],
            data=extracted_data
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting from image: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'estrazione: {str(e)}"
        )


@router.post(
    "/test-pp-structure-v3",
    summary="Test PP-StructureV3 cell extraction",
    description="Endpoint di test per verificare l'estrazione celle con PP-StructureV3"
)
async def test_pp_structure_v3(
    file: UploadFile = File(..., description="File PDF da testare"),
    use_gpu: bool = Query(False, description="Utilizza GPU"),
):
    """
    Endpoint per testare PP-StructureV3 extraction.
    
    Ritorna:
    - Tutte le celle estratte con coordinate
    - Info tabelle rilevate
    - Debug dettagliato
    """
    import base64
    from io import BytesIO
    
    try:
        from app.services.pp_structure_v3_extractor import (
            get_pp_structure_extractor,
            create_mic_us_label_mapping,
            PP_STRUCTURE_AVAILABLE
        )
    except ImportError as e:
        return {
            "error": f"PP-StructureV3 extractor not available: {e}",
            "suggestion": "Install with: pip install -U paddleocr"
        }
    
    if not PP_STRUCTURE_AVAILABLE:
        return {
            "error": "PP-Structure module not available",
            "suggestion": "Install with: pip install -U paddleocr"
        }
    
    try:
        import fitz
        import cv2
        import numpy as np
        from PIL import Image
        
        pdf_bytes = await file.read()
        
        # Open PDF and render first page
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = pdf_document[0]
        
        zoom = 2.5
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        
        # Convert to numpy
        img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img_data = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
        
        pdf_document.close()
        
        # Extract with PP-StructureV3
        extractor = get_pp_structure_extractor(use_gpu=use_gpu)
        tables = extractor.extract_tables_from_image(img_data)
        
        if not tables:
            return {
                "success": False,
                "error": "No tables detected in PDF",
                "page_size": (pix.width, pix.height)
            }
        
        main_table = tables[0]
        
        # Visualize
        vis_image = extractor.visualize_table(img_data, main_table)
        
        # Convert visualization to base64
        pil_vis = Image.fromarray(vis_image)
        bio = BytesIO()
        pil_vis.save(bio, format='PNG')
        bio.seek(0)
        vis_b64 = base64.b64encode(bio.getvalue()).decode()
        
        # Collect cells data
        cells_data = []
        for cell in main_table.cells:
            cells_data.append({
                "row": cell.row,
                "col": cell.col,
                "text": cell.text,
                "bbox": list(cell.bbox),
                "rowspan": cell.rowspan,
                "colspan": cell.colspan,
                "confidence": cell.confidence,
                "width": cell.width,
                "height": cell.height
            })
        
        # Test field extraction
        label_mapping = create_mic_us_label_mapping()
        extracted_fields = extractor.extract_fields_by_label(tables, label_mapping)
        
        return {
            "success": True,
            "page_size": (pix.width, pix.height),
            "tables_count": len(tables),
            "table": {
                "rows": main_table.rows,
                "cols": main_table.cols,
                "cells_count": len(main_table.cells),
                "bbox": list(main_table.bbox),
            },
            "cells": cells_data,
            "extracted_fields": extracted_fields,
            "visualization": f"data:image/png;base64,{vis_b64}"
        }
    
    except Exception as e:
        logger.error(f"Test PP-StructureV3 failed: {e}")
        import traceback
        return {
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }


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

