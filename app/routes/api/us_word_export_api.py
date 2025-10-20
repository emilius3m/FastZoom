# app/routes/api/us_word_export.py
"""
API per esportazione schede US/USM in formato Word
Genera documenti identici al modello MiC 2021 allegato (US-3.doc)
"""

from typing import List, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger
import io

from app.database.db import get_async_session
from app.core.security import get_current_user_id_with_blacklist, get_current_user_sites_with_blacklist
from app.services.us_word_generator import USWordGenerator, USMWordGenerator
from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria

router = APIRouter(prefix="/api/us-export", tags=["us-export"])

async def verify_site_access(site_id: UUID, user_sites: List[Dict[str, Any]]) -> bool:
    """Verifica accesso utente al sito"""
    return any(s["id"] == str(site_id) for s in user_sites)

# ===== EXPORT SINGOLA US =====

@router.get("/us/{us_id}/word")
async def export_us_word(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Esporta singola scheda US in formato Word identico al modello MiC 2021
    Replica ESATTAMENTE la struttura di US-3.doc
    """
    
    try:
        logger.info(f"→ Inizio export Word US {us_id}")
        
        # Carica US con relazioni
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
        us_result = await db.execute(us_query)
        us = us_result.scalar_one_or_none()
        
        logger.debug(f"US caricata: {us is not None}")
        
        if not us:
            raise HTTPException(status_code=404, detail="US non trovata")
        
        logger.debug(f"US trovata - code: {us.us_code}, site_id: {us.site_id}")
        
        # Verifica accesso sito
        if not await verify_site_access(us.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        logger.debug(f"Accesso verificato, inizio generazione documento")
        
        # Genera documento Word
        generator = USWordGenerator()
        logger.debug(f"Generator creato, chiamata generate_us_bytes")
        doc_bytes = generator.generate_us_bytes(us)
        
        logger.debug(f"Bytes generati: {len(doc_bytes)} bytes")
        logger.info(f"filename Word US ")
        # Nome file: US003_Sepino_2023.docx
        logger.debug(f"Preparazione filename - us_code: {us.us_code}")
        us_number_str = us.us_code.replace('US', '').replace('us', '').lstrip('0') if us.us_code else '0'
        logger.debug(f"us_number_str dopo processing: '{us_number_str}'")
        us_number_int = int(us_number_str) if us_number_str else 0
        localita_clean = (us.localita or '').replace(' ', '_').replace(',', '') or 'Sito'
        anno = us.anno or 2025
        filename = f"US{us_number_int:03d}_{localita_clean}_{anno}.docx"
        logger.info(f"✓ Export completato: {filename}")
        logger.info(f"filename Word US {filename}")
        # Response streaming
        return StreamingResponse(
            io.BytesIO(doc_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore export Word US {us_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore nella generazione del documento Word: {str(e)}"
        )

# ===== EXPORT SINGOLA USM =====

@router.get("/usm/{usm_id}/word")
async def export_usm_word(
    usm_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """Esporta singola scheda USM in formato Word"""
    
    try:
        usm_query = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
        usm_result = await db.execute(usm_query)
        usm = usm_result.scalar_one_or_none()
        
        if not usm:
            raise HTTPException(status_code=404, detail="USM non trovata")
        
        if not await verify_site_access(usm.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        generator = USMWordGenerator()
        doc_bytes = generator.generate_usm_bytes(usm)
        
        usm_number = usm.usm_code.replace('USM', '').replace('usm', '').lstrip('0') if usm.usm_code else 'X'
        localita_clean = (usm.localita or '').replace(' ', '_').replace(',', '') or 'Sito'
        anno = usm.anno or 2025
        filename = f"USM{usm_number:03d}_{localita_clean}_{anno}.docx"
        
        return StreamingResponse(
            io.BytesIO(doc_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore export Word USM {usm_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore generazione USM: {str(e)}")

# ===== EXPORT MULTIPLO US =====

@router.post("/us/bulk-word")
async def export_multiple_us_word(
    us_ids: List[UUID],
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Esporta multiple US come ZIP di documenti Word
    Ogni US genera un file Word separato identico al modello MiC
    """
    
    if len(us_ids) > 50:  # Limite ragionevole
        raise HTTPException(status_code=400, detail="Troppi US selezionati (max 50)")
    
    try:
        import zipfile
        from datetime import datetime
        
        # Carica tutte le US
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id.in_(us_ids))
        us_result = await db.execute(us_query)
        us_list = us_result.scalars().all()
        
        if not us_list:
            raise HTTPException(status_code=404, detail="Nessuna US trovata")
        
        # Verifica accessi
        for us in us_list:
            if not await verify_site_access(us.site_id, user_sites):
                raise HTTPException(status_code=403, detail=f"Accesso negato per US {us.us_code}")
        
        # Crea ZIP in memoria
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            generator = USWordGenerator()
            
            for us in us_list:
                try:
                    # Genera documento per ogni US
                    doc_bytes = generator.generate_us_bytes(us)
                    
                    # Nome file univoco
                    us_number_str = us.us_code.replace('US', '').replace('us', '').lstrip('0') if us.us_code else '0'
                    us_number_int = int(us_number_str) if us_number_str else 0
                    localita_clean = (us.localita or '').replace(' ', '_')[:10] or 'Sito'
                    filename = f"US{us_number_int:03d}_{localita_clean}.docx"
                    
                    # Aggiungi a ZIP
                    zip_file.writestr(filename, doc_bytes)
                    
                    logger.info(f"US {us.us_code} aggiunta al ZIP")
                    
                except Exception as e:
                    logger.error(f"Errore generazione US {us.us_code}: {str(e)}")
                    # Continua con le altre US
                    
        zip_buffer.seek(0)
        
        # Nome ZIP
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"SchediUS_Export_{timestamp}.zip"
        
        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore export bulk US: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore export multiplo: {str(e)}")

# ===== EXPORT SITO COMPLETO =====

@router.get("/site/{site_id}/us/word-zip")
async def export_site_us_word(
    site_id: UUID,
    validated_only: bool = False,
    db: AsyncSession = Depends(get_async_session),
    current_user_id: UUID = Depends(get_current_user_id_with_blacklist),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Esporta tutte le US di un sito come ZIP di documenti Word
    Opzione per esportare solo US validate
    """
    
    try:
        if not await verify_site_access(site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato al sito")
        
        # Query US del sito
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == site_id)
        
        if validated_only:
            us_query = us_query.where(UnitaStratigrafica.is_validated == True)
        
        us_query = us_query.order_by(UnitaStratigrafica.us_code)
        
        us_result = await db.execute(us_query)
        us_list = us_result.scalars().all()
        
        if not us_list:
            raise HTTPException(status_code=404, detail="Nessuna US trovata per questo sito")
        
        if len(us_list) > 200:  # Limite ragionevole per sito
            raise HTTPException(status_code=400, detail=f"Troppe US nel sito ({len(us_list)}). Contattare amministratore.")
        
        # Genera ZIP
        import zipfile
        from datetime import datetime
        
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            generator = USWordGenerator()
            success_count = 0
            
            for us in us_list:
                try:
                    doc_bytes = generator.generate_us_bytes(us)
                    
                    us_number_str = us.us_code.replace('US', '').replace('us', '').lstrip('0') if us.us_code else '0'
                    us_number_int = int(us_number_str) if us_number_str else 0
                    filename = f"US{us_number_int:03d}_{us.us_code}.docx"
                    
                    zip_file.writestr(filename, doc_bytes)
                    success_count += 1
                    
                except Exception as e:
                    logger.error(f"Errore US {us.us_code}: {str(e)}")
                    continue
        
        zip_buffer.seek(0)
        
        # Nome descrittivo ZIP
        site_name = "Sito"  # Potresti caricare il nome sito dalla DB
        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        validated_suffix = "_Validate" if validated_only else "_Tutte"
        zip_filename = f"SchediUS_{site_name}{validated_suffix}_{timestamp}.zip"
        
        logger.info(f"Export sito {site_id}: {success_count}/{len(us_list)} US generate")
        
        return StreamingResponse(
            io.BytesIO(zip_buffer.read()),
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore export sito {site_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore export sito: {str(e)}")

# ===== UTILITY ENDPOINTS =====

@router.get("/us/{us_id}/preview")
async def preview_us_word_structure(
    us_id: UUID,
    db: AsyncSession = Depends(get_async_session),
    user_sites: List[Dict[str, Any]] = Depends(get_current_user_sites_with_blacklist)
):
    """
    Preview struttura dati US per generazione Word
    Utile per debug e controllo dati prima export
    """
    
    try:
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
        us_result = await db.execute(us_query)
        us = us_result.scalar_one_or_none()
        
        if not us:
            raise HTTPException(status_code=404, detail="US non trovata")
        
        if not await verify_site_access(us.site_id, user_sites):
            raise HTTPException(status_code=403, detail="Accesso negato")
        
        # Struttura dati per Word
        us_number_str = us.us_code.replace('US', '').replace('us', '').lstrip('0') if us.us_code else '0'
        word_data = {
            'us_code': us.us_code,
            'us_number': us_number_str,
            'ente_responsabile': us.ente_responsabile or '',
            'anno': us.anno or '',
            'identificativo_rif': us.identificativo_rif or '',
            'localita': us.localita or '',
            'area_struttura': us.area_struttura or '',
            'saggio': us.saggio or '',
            'ambiente_unita_funzione': us.ambiente_unita_funzione or '',
            'posizione': us.posizione or '',
            'settori': us.settori or '',
            'piante_riferimenti': us.piante_riferimenti or '',
            'prospetti_riferimenti': us.prospetti_riferimenti or '',
            'sezioni_riferimenti': us.sezioni_riferimenti or '',
            'definizione': us.definizione or '',
            'criteri_distinzione': us.criteri_distinzione or '',
            'modo_formazione': us.modo_formazione or '',
            'componenti_inorganici': us.componenti_inorganici or '',
            'componenti_organici': us.componenti_organici or '',
            'consistenza': us.consistenza or '',
            'colore': us.colore or '',
            'misure': us.misure or '',
            'stato_conservazione': us.stato_conservazione or '',
            'sequenza_fisica': us.sequenza_fisica or {},
            'descrizione': us.descrizione or '',
            'osservazioni': us.osservazioni or '',
            'interpretazione': us.interpretazione or '',
            'datazione': us.datazione or '',
            'periodo': us.periodo or '',
            'fase': us.fase or '',
            'elementi_datanti': us.elementi_datanti or '',
            'dati_quantitativi_reperti': us.dati_quantitativi_reperti or '',
            'campionature': us.campionature or {},
            'affidabilita_stratigrafica': us.affidabilita_stratigrafica or '',
            'responsabile_scientifico': us.responsabile_scientifico or '',
            'data_rilevamento': us.data_rilevamento.isoformat() if us.data_rilevamento else '',
            'responsabile_compilazione': us.responsabile_compilazione or '',
            'data_rielaborazione': us.data_rielaborazione.isoformat() if us.data_rielaborazione else '',
            'responsabile_rielaborazione': us.responsabile_rielaborazione or ''
        }
        
        # Aggiungi informazioni file se disponibili
        files_summary = {}
        # ... logica per caricare file associati
        
        return {
            'us_id': str(us_id),
            'word_data': word_data,
            'files_summary': files_summary,
            'export_ready': True,
            'estimated_filename': f"US{int(word_data['us_number']) if word_data['us_number'] else 0:03d}_{word_data['localita'].replace(' ', '_')}_{word_data['anno']}.docx"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore preview US {us_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Errore preview: {str(e)}")
        

@router.get("/supported-formats")
async def get_supported_export_formats():
    """Formati export supportati"""
    
    return {
        'formats': {
            'word': {
                'extension': '.docx',
                'mime_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'description': 'Documento Word identico al modello MiC 2021',
                'template_based': True
            }
        },
        'export_options': {
            'single_us': '/api/us-export/us/{id}/word',
            'single_usm': '/api/us-export/usm/{id}/word', 
            'bulk_us': '/api/us-export/us/bulk-word',
            'site_export': '/api/us-export/site/{site_id}/us/word-zip'
        },
        'template_info': {
            'based_on': 'US-3.doc - Parco Archeologico di Sepino 2023',
            'compliance': 'MiC Standard 2021',
            'table_structure': '3 columns, merged cells, identical layout'
        }
    }