# app/routes/api/v1/ocr_us_import.py
"""
API v1 - OCR Import US Sheets
Endpoints per importazione schede US da PDF tramite DeepSeek-OCR (via Ollama)
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
from app.services.deepseek_ocr_service import (
    get_deepseek_ocr_service, 
    is_deepseek_ocr_available,
    DeepSeekOCRService
)


router = APIRouter()


# ===== PYDANTIC MODELS =====

class OCRStatusResponse(BaseModel):
    """Stato del servizio OCR"""
    available: bool
    deepseek_ocr_available: bool
    ollama_available: bool
    pymupdf_available: bool
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
    # Markdown raw output from DeepSeek-OCR
    markdown_raw: Optional[str] = None


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
    # Additional debug info
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
    description="Verifica disponibilità del servizio DeepSeek-OCR via Ollama"
)
async def get_ocr_status():
    """
    Verifica lo stato del servizio OCR per l'importazione PDF.
    
    Controlla:
    - Disponibilità Ollama
    - Disponibilità PyMuPDF
    - Modelli DeepSeek-OCR e llama3.2
    """
    try:
        from app.services.deepseek_ocr_service import OLLAMA_AVAILABLE, PYMUPDF_AVAILABLE
        
        available = OLLAMA_AVAILABLE and PYMUPDF_AVAILABLE
        
        if available:
            message = "Servizio OCR disponibile (DeepSeek-OCR via Ollama)"
        elif not OLLAMA_AVAILABLE:
            message = "Ollama non installato. Installa con: pip install ollama"
        elif not PYMUPDF_AVAILABLE:
            message = "PyMuPDF non installato. Installa con: pip install pymupdf"
        else:
            message = "Servizio OCR non disponibile"
        
        return OCRStatusResponse(
            available=available,
            deepseek_ocr_available=available,
            ollama_available=OLLAMA_AVAILABLE,
            pymupdf_available=PYMUPDF_AVAILABLE,
            message=message
        )
    
    except Exception as e:
        logger.error(f"Error checking OCR status: {e}")
        return OCRStatusResponse(
            available=False,
            deepseek_ocr_available=False,
            ollama_available=False,
            pymupdf_available=False,
            message=f"Errore verifica servizio: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/ocr/extract",
    response_model=OCRBatchResult,
    summary="Estrai schede US da PDF",
    description="Estrae schede US da un PDF utilizzando DeepSeek-OCR via Ollama"
)
async def extract_us_from_pdf(
    site_id: UUID,
    file: UploadFile = File(..., description="File PDF da processare"),
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Estrae schede US da un file PDF utilizzando DeepSeek-OCR.
    
    Pipeline:
    1. PDF → Immagini (PyMuPDF)
    2. Immagini → Markdown (DeepSeek-OCR via Ollama)
    3. Markdown → JSON strutturato (llama3.2:3b)
    
    Returns:
        OCRBatchResult con i risultati dell'estrazione
    """
    import time
    start_time = time.time()
    
    # Verifica accesso al sito
    verify_site_access(site_id, user_sites)
    
    # Verifica disponibilità OCR
    if not is_deepseek_ocr_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Servizio OCR non disponibile. Assicurati che Ollama e PyMuPDF siano installati."
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
        
        logger.info(f"Processing PDF {file.filename} ({len(pdf_bytes)} bytes) with DeepSeek-OCR for site {site_id}")
        
        # Inizializza servizio DeepSeek-OCR
        service = get_deepseek_ocr_service()
        
        # Estrai con DeepSeek-OCR
        extraction_result = service.extract_from_pdf(
            pdf_bytes=pdf_bytes,
            filename=file.filename,
            site_id=str(site_id),
            include_debug=True
        )
        
        # Check for errors
        if extraction_result.get('error'):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=extraction_result.get('error')
            )
        
        # Build results from extraction
        results = []
        for result_data in extraction_result.get('results', []):
            results.append(OCRExtractionResult(
                us_code=result_data.get('us_code', 'UNKNOWN'),
                page_number=result_data.get('page_number', 1),
                confidence=result_data.get('confidence', 0.0),
                is_valid=result_data.get('is_valid', False),
                issues=result_data.get('issues', []),
                warnings=result_data.get('warnings', []),
                extracted_fields_count=result_data.get('extracted_fields_count', 0),
                data=result_data.get('data', {})
            ))
        
        # Build debug pages
        debug_pages = []
        for page_data in extraction_result.get('debug_pages', []):
            debug_pages.append(OCRPageDebug(
                page_number=page_data.get('page_number', 0),
                image_base64=page_data.get('image_base64'),
                text_lines=page_data.get('text_lines', []),
                word_count=page_data.get('word_count', 0),
                page_size=page_data.get('page_size'),
                markdown_raw=page_data.get('markdown_raw')
            ))
        
        processing_time = time.time() - start_time
        
        return OCRBatchResult(
            filename=file.filename,
            total_pages=extraction_result.get('total_pages', 1),
            successful_extractions=extraction_result.get('successful_extractions', 0),
            failed_extractions=extraction_result.get('failed_extractions', 0),
            results=results,
            processing_time_seconds=round(processing_time, 2),
            debug_pages=debug_pages,
            combined_text=extraction_result.get('combined_text', ''),
            debug=extraction_result.get('debug', {})
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error extracting US from PDF: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante l'estrazione: {str(e)}"
        )







# ===== LLM OCR IMPORT ENDPOINT =====

@router.post(
    "/sites/{site_id}/ocr/import-llm-json",
    status_code=status.HTTP_201_CREATED,
    summary="Importa US da JSON generato da LLM",
    description="Importa una scheda US dal JSON strutturato prodotto da un modello VLM (Qwen3-VL, etc.)"
)
async def import_us_from_llm_json(
    site_id: UUID,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_async_session),
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Importa una scheda US dal JSON prodotto da un modello VLM.
    
    Il JSON deve seguire lo schema LLMUSDocument con:
    - schema_version: "fz.us.llm.v1"
    - document_type: "US"
    - pages: array con dati estratti per pagina
    - mapped: oggetto con campi normalizzati pronti per il DB
    
    Returns:
        Dict con success, us_code e id del record creato
    """
    from app.schemas.llm_ocr import LLMUSDocument
    from pydantic import ValidationError
    
    # Verifica accesso al sito
    verify_site_access(site_id, user_sites)
    
    try:
        # Valida payload con Pydantic
        doc = LLMUSDocument(**payload)
        
        # Converti in dict pronto per DB
        us_data = doc.to_db_dict(str(site_id))
        
        # Rimuovi campi metadata che non appartengono al modello DB
        llm_metadata = {
            '_llm_source': us_data.pop('_llm_source', None),
            '_llm_confidence': us_data.pop('_llm_confidence', None),
            '_llm_issues': us_data.pop('_llm_issues', None),
        }
        
        # Verifica che us_code non esista già per questo sito
        existing = await db.execute(
            select(UnitaStratigrafica).where(
                UnitaStratigrafica.site_id == str(site_id),
                UnitaStratigrafica.us_code == us_data.get('us_code')
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"US {us_data.get('us_code')} esiste già per questo sito"
            )
        
        # Crea record US
        new_us = UnitaStratigrafica(**us_data)
        db.add(new_us)
        await db.commit()
        await db.refresh(new_us)
        
        logger.info(f"LLM Import: Created US {new_us.us_code} (id={new_us.id}) for site {site_id}")
        
        return {
            "success": True,
            "us_code": new_us.us_code,
            "id": str(new_us.id),
            "llm_metadata": llm_metadata,
            "fields_imported": len([k for k, v in us_data.items() if v is not None and not k.startswith('_')])
        }
    
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Validazione JSON fallita: {e.errors()}"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error importing LLM JSON: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Errore durante l'import: {str(e)}"
        )


@router.post(
    "/sites/{site_id}/ocr/validate-llm-json",
    summary="Valida JSON LLM senza importare",
    description="Valida il JSON prodotto da un modello VLM senza salvarlo nel DB"
)
async def validate_llm_json(
    site_id: UUID,
    payload: Dict[str, Any],
    user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Valida un JSON LLM OCR senza importarlo.
    
    Utile per verificare che l'output del modello sia corretto
    prima di procedere con l'import.
    """
    from app.schemas.llm_ocr import LLMUSDocument
    from pydantic import ValidationError
    
    verify_site_access(site_id, user_sites)
    
    try:
        doc = LLMUSDocument(**payload)
        
        # Verifica campi mappati
        mapped = doc.mapped
        issues = []
        warnings = []
        
        if not mapped.us_code:
            issues.append("us_code mancante")
        
        if not mapped.definizione:
            warnings.append("definizione mancante")
        
        if not mapped.descrizione:
            warnings.append("descrizione mancante")
        
        # Verifica date
        if mapped.data_rilevamento and mapped.data_rilevamento.count('-') != 2:
            warnings.append("data_rilevamento non in formato YYYY-MM-DD")
        
        return {
            "valid": len(issues) == 0,
            "schema_version": doc.schema_version,
            "us_code": mapped.us_code,
            "confidence": doc.confidence,
            "pages_count": len(doc.pages),
            "fields_count": len([k for k, v in mapped.model_dump().items() if v is not None]),
            "issues": issues,
            "warnings": warnings,
            "global_issues": doc.global_issues
        }
    
    except ValidationError as e:
        return {
            "valid": False,
            "issues": [err['msg'] for err in e.errors()],
            "validation_errors": e.errors()
        }
    except Exception as e:
        return {
            "valid": False,
            "issues": [str(e)]
        }
