from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.database.session import get_async_session
from app.services.database_pool_monitor import get_pool_monitor
from app.core.security import get_current_user_id
from loguru import logger

router = APIRouter(prefix="", tags=["database_monitoring"])

@router.get("/pool/status")
async def get_pool_status(
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Ottiene lo stato attuale del connection pool.
    
    Requires authentication.
    """
    try:
        monitor = get_pool_monitor()
        if not monitor:
            raise HTTPException(
                status_code=503,
                detail="Pool monitor non disponibile"
            )
        
        status = monitor.get_pool_status()
        return {
            "success": True,
            "data": status
        }
        
    except Exception as e:
        logger.error(f"Errore ottenimento status pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno: {str(e)}"
        )

@router.get("/pool/health")
async def get_pool_health(
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Ottiene lo stato di salute del connection pool con raccomandazioni.
    
    Requires authentication.
    """
    try:
        monitor = get_pool_monitor()
        if not monitor:
            raise HTTPException(
                status_code=503,
                detail="Pool monitor non disponibile"
            )
        
        health = monitor.get_pool_health_status()
        return {
            "success": True,
            "data": health
        }
        
    except Exception as e:
        logger.error(f"Errore valutazione salute pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno: {str(e)}"
        )

@router.get("/pool/trends")
async def get_pool_trends(
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Ottiene l'analisi dei trend del connection pool.
    
    Requires authentication.
    """
    try:
        monitor = get_pool_monitor()
        if not monitor:
            raise HTTPException(
                status_code=503,
                detail="Pool monitor non disponibile"
            )
        
        trends = monitor.get_trend_analysis()
        return {
            "success": True,
            "data": trends
        }
        
    except Exception as e:
        logger.error(f"Errore analisi trend pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno: {str(e)}"
        )

@router.post("/pool/log-status")
async def log_pool_status(
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Forza il logging dello stato attuale del pool.
    
    Requires authentication.
    """
    try:
        monitor = get_pool_monitor()
        if not monitor:
            raise HTTPException(
                status_code=503,
                detail="Pool monitor non disponibile"
            )
        
        monitor.log_pool_status()
        
        return {
            "success": True,
            "message": "Stato pool loggato con successo"
        }
        
    except Exception as e:
        logger.error(f"Errore logging status pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno: {str(e)}"
        )

@router.get("/pool/metrics")
async def get_pool_metrics(
    current_user_id: str = Depends(get_current_user_id)
) -> Dict[str, Any]:
    """
    Ottiene metriche complete del pool per dashboard di monitoring.
    
    Requires authentication.
    """
    try:
        monitor = get_pool_monitor()
        if not monitor:
            raise HTTPException(
                status_code=503,
                detail="Pool monitor non disponibile"
            )
        
        # Raccoglie tutte le metriche
        status = monitor.get_pool_status()
        health = monitor.get_pool_health_status()
        trends = monitor.get_trend_analysis()
        
        return {
            "success": True,
            "data": {
                "current_status": status,
                "health_assessment": health,
                "trend_analysis": trends,
                "timestamp": status.get("timestamp")
            }
        }
        
    except Exception as e:
        logger.error(f"Errore raccolta metriche pool: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Errore interno: {str(e)}"
        )