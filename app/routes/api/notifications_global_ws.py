# app/routes/api/notifications_global_ws.py - WebSocket globale per notifiche in tempo reale

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from loguru import logger
from typing import Dict, Set, Optional
from uuid import UUID
import json
import asyncio

from app.core.security import SecurityService

# Import the existing notification manager
from app.routes.api.notifications_ws import NotificationManager, notification_manager

# Router for global WebSocket notifications
global_notifications_router = APIRouter()


@global_notifications_router.websocket("/ws/notifications")
async def websocket_global_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(None, description="JWT authentication token")
):
    """
    WebSocket endpoint globale per notifiche in tempo reale
    
    Questo endpoint supporta connessioni senza site_id specifico e permette
    al client di specificare il token come query parameter.
    
    URL: ws://localhost:8000/ws/notifications?token={jwt_token}
    
    Dopo l'autenticazione, il client può inviare un messaggio per specificare il sito:
    {"action": "join_site", "site_id": "uuid-del-sito"}
    """
    try:
        # Accetta la connessione WebSocket
        await websocket.accept()
        logger.info("Global WebSocket connection established")
        
        # Verifica autenticazione tramite token
        if not token:
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": "Token di autenticazione mancante"
                })
            except Exception:
                pass
            await websocket.close(code=4001, reason="Missing authentication token")
            return
        
        # Rimuovi "Bearer " se presente
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Verifica il token
        try:
            from app.core.config import get_settings
            settings = get_settings()
            
            # Crea un fake request per validare il token
            class FakeRequest:
                def __init__(self, auth_token):
                    self._token = auth_token
                
                @property
                def cookies(self):
                    return {"access_token": f"Bearer {self._token}"}
            
            fake_request = FakeRequest(token)
            
            # Ottieni database session usando la funzione corretta
            from app.database.db import async_session_maker
            from app.services.auth_service import AuthService
            async with async_session_maker() as db:
                # Verifica il token e ottieni informazioni utente
                payload = await SecurityService.verify_token(token, db)
                user_id = payload.get("sub")
                
                # Fetch user sites from database (not from token - sites no longer in JWT)
                if not user_id:
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Autenticazione fallita"
                        })
                    except Exception:
                        pass
                    await websocket.close(code=4003, reason="Authentication failed")
                    return
                
                try:
                    from uuid import UUID
                    user_uuid = UUID(user_id)
                    user_sites = await AuthService.get_user_sites_with_permissions(db, user_uuid)
                except Exception as e:
                    logger.error(f"Error fetching user sites: {e}")
                    user_sites = []
                
                if not user_sites:
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "message": "Autenticazione fallita o nessun sito accessibile"
                        })
                    except Exception:
                        pass
                    await websocket.close(code=4003, reason="Authentication failed")
                    return
                
                logger.info(f"User {user_id} authenticated with access to {len(user_sites)} sites")
                
                # Invia lista siti accessibili al client
                await websocket.send_json({
                    "type": "authenticated",
                    "user_id": user_id,
                    "sites": user_sites,
                    "message": "Autenticazione completata. Invia {'action': 'join_site', 'site_id': 'uuid'} per unirti a un sito specifico."
                })
                
                # Mantieni la connessione attiva e gestisci messaggi
                current_site_id = None
                
                while True:
                    try:
                        # Ricevi messaggi dal client
                        message = await websocket.receive_text()
                        
                        try:
                            data = json.loads(message)
                            
                            if data.get("action") == "join_site":
                                site_id = data.get("site_id")
                                
                                if not site_id:
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": "site_id mancante"
                                    })
                                    continue
                                
                                # Verifica accesso al sito
                                site_info = next(
                                    (site for site in user_sites if site.get("site_id") == site_id),
                                    None
                                )
                                
                                if not site_info:
                                    await websocket.send_json({
                                        "type": "error",
                                        "message": f"Accesso negato al sito {site_id}"
                                    })
                                    continue
                                
                                # Disconnetti dal sito precedente se connesso
                                if current_site_id:
                                    await notification_manager.disconnect(websocket, current_site_id)
                                
                                # Connetti al nuovo sito
                                await notification_manager.connect(websocket, site_id)
                                current_site_id = site_id
                                
                                await websocket.send_json({
                                    "type": "site_joined",
                                    "site_id": site_id,
                                    "site_name": site_info.get("name", "Sito Sconosciuto"),
                                    "message": f"Connesso al sito {site_info.get('name', site_id)}"
                                })
                                
                                logger.info(f"User {user_id} joined site {site_id}")
                            
                            elif data.get("action") == "ping":
                                await websocket.send_json({"type": "pong"})
                            
                            else:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": f"Azione non valida: {data.get('action')}"
                                })
                        
                        except json.JSONDecodeError:
                            await websocket.send_json({
                                "type": "error",
                                "message": "Formato JSON non valido"
                            })
                    
                    except WebSocketDisconnect:
                        logger.info(f"Global WebSocket disconnected by client (user: {user_id})")
                        break
                    except Exception as e:
                        error_str = str(e).lower()
                        if any(err in error_str for err in ['closed', 'disconnect', 'connection']):
                            logger.warning(f"Global WebSocket connection error: {e}")
                        else:
                            logger.error(f"Unexpected error in global WebSocket loop: {e}")
                        break
        
        except Exception as e:
            logger.error(f"Authentication error in global WebSocket: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Errore autenticazione: {str(e)}"
                })
            except Exception:
                pass
            await websocket.close(code=4003, reason="Authentication failed")
            return
    
    except WebSocketDisconnect:
        logger.info("Global WebSocket disconnected during handshake")
    except Exception as e:
        error_str = str(e).lower()
        if any(err in error_str for err in ['closed', 'disconnect', 'connection']):
            logger.warning(f"Global WebSocket connection error: {e}")
        else:
            logger.error(f"Global WebSocket error: {e}")
    finally:
        # Cleanup se connesso a un sito
        if 'current_site_id' in locals() and current_site_id:
            try:
                await notification_manager.disconnect(websocket, current_site_id)
            except Exception as e:
                logger.debug(f"Error during cleanup: {e}")


# Health check endpoint for global WebSocket connections
@global_notifications_router.get("/ws/global/health")
async def global_websocket_health():
    """Get health status of global WebSocket connections"""
    health_status = notification_manager.get_health_status()
    
    return {
        "endpoint": "/ws/notifications",
        "status": health_status['status'],
        "stats": health_status['stats'],
        "recommendations": health_status['recommendations'],
        "timestamp": str(asyncio.get_event_loop().time()),
        "description": "Global WebSocket endpoint for notifications with token-based authentication"
    }


# Export per uso nell'app principale
__all__ = ['global_notifications_router']