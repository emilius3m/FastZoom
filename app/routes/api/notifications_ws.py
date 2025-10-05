# app/routes/api/notifications_ws.py - WebSocket per notifiche tiles in tempo reale

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from loguru import logger
from typing import Dict, Set
from uuid import UUID
import json
import asyncio

from app.core.security import get_current_user_id, get_current_user_sites, SecurityService

notifications_router = APIRouter()

# Manager per connessioni WebSocket attive
class NotificationManager:
    def __init__(self):
        # Dict[site_id, Set[WebSocket]]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, site_id: str):
        """Connetti un client WebSocket per un sito specifico"""
        await websocket.accept()
        
        async with self.lock:
            if site_id not in self.active_connections:
                self.active_connections[site_id] = set()
            self.active_connections[site_id].add(websocket)
        
        logger.info(f"WebSocket connected for site {site_id}. Total connections: {len(self.active_connections.get(site_id, []))}")
    
    async def disconnect(self, websocket: WebSocket, site_id: str):
        """Disconnetti un client WebSocket"""
        async with self.lock:
            if site_id in self.active_connections:
                self.active_connections[site_id].discard(websocket)
                if not self.active_connections[site_id]:
                    del self.active_connections[site_id]
        
        logger.info(f"WebSocket disconnected for site {site_id}")
    
    async def send_notification(self, site_id: str, notification: dict):
        """Invia notifica a tutti i client connessi per un sito"""
        if site_id not in self.active_connections:
            logger.debug(f"No active connections for site {site_id}")
            return
        
        disconnected = set()
        
        for connection in self.active_connections.get(site_id, set()).copy():
            try:
                await connection.send_json(notification)
                logger.debug(f"Notification sent to site {site_id}: {notification.get('type')}")
            except Exception as e:
                logger.warning(f"Failed to send notification: {e}")
                disconnected.add(connection)
        
        # Rimuovi connessioni morte
        if disconnected:
            async with self.lock:
                if site_id in self.active_connections:
                    self.active_connections[site_id] -= disconnected
                    if not self.active_connections[site_id]:
                        del self.active_connections[site_id]
    
    async def broadcast_tiles_progress(
        self,
        site_id: str,
        photo_id: str,
        status: str,
        progress: int = 0,
        photo_filename: str = None,
        tile_count: int = None,
        levels: int = None,
        current_photo: int = None,
        total_photos: int = None,
        error: str = None
    ):
        """Invia notifica progresso tiles"""
        notification = {
            'type': 'tiles_progress',
            'site_id': site_id,
            'photo_id': photo_id,
            'status': status,
            'progress': progress,
            'photo_filename': photo_filename,
            'tile_count': tile_count,
            'levels': levels,
            'current_photo': current_photo,
            'total_photos': total_photos,
            'error': error,
            'timestamp': str(asyncio.get_event_loop().time())
        }
        
        await self.send_notification(site_id, notification)

# Istanza globale del manager
notification_manager = NotificationManager()


@notifications_router.websocket("/sites/{site_id}/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    site_id: UUID
):
    """
    WebSocket endpoint per notifiche in tempo reale

    Messaggi inviati dal server:
    {
        "type": "tiles_progress",
        "photo_id": "xxx",
        "status": "processing|completed|failed",
        "progress": 0-100,
        "photo_filename": "foto.jpg",
        "tile_count": 1024,
        "levels": 8,
        "current_photo": 1,
        "total_photos": 5
    }
    """
    site_id_str = str(site_id)

    try:
        # Verifica autenticazione e autorizzazione al sito
        # Per WebSocket, dobbiamo gestire l'autenticazione manualmente
        # poiché i WebSocket non supportano le dipendenze FastAPI direttamente

        # Accetta prima la connessione WebSocket
        await websocket.accept()

        # Ottieni token dal client (inviato come primo messaggio)
        try:
            auth_data = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
            if auth_data.get("type") != "auth":
                await websocket.send_json({
                    "type": "error",
                    "message": "Autenticazione richiesta"
                })
                await websocket.close()
                return

            token = auth_data.get("token")
            if not token:
                await websocket.send_json({
                    "type": "error",
                    "message": "Token mancante"
                })
                await websocket.close()
                return

        except asyncio.TimeoutError:
            await websocket.send_json({
                "type": "error",
                "message": "Timeout autenticazione"
            })
            await websocket.close()
            return
        except Exception:
            await websocket.send_json({
                "type": "error",
                "message": "Errore durante autenticazione"
            })
            await websocket.close()
            return

        # Verifica token e ottieni informazioni utente
        try:
            from fastapi import Request
            from app.database.db import get_async_session
            from sqlalchemy.ext.asyncio import AsyncSession

            # Crea un request fittizio per usare le funzioni di sicurezza esistenti
            class FakeRequest:
                def __init__(self, token):
                    self.cookies = {"access_token": token}

            fake_request = FakeRequest(token)

            # Verifica token e ottieni payload
            token_payload = await SecurityService.verify_token(token, None)
            user_id = token_payload.get("sub")
            user_sites = SecurityService.get_sites_from_token(token_payload)

            # Verifica accesso al sito specifico
            site_info = next(
                (site for site in user_sites if site.get("id") == site_id_str),
                None
            )

            if not site_info:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Accesso negato al sito {site_id_str}"
                })
                await websocket.close()
                return

        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": f"Errore autenticazione: {str(e)}"
            })
            await websocket.close()
            return

        # Connetti WebSocket dopo autenticazione
        await notification_manager.connect(websocket, site_id_str)
        
        # Invia messaggio di benvenuto dopo autenticazione
        await websocket.send_json({
            'type': 'connected',
            'site_id': site_id_str,
            'message': 'WebSocket connesso - autenticazione completata - riceverai notifiche tiles in tempo reale'
        })

        # Mantieni connessione attiva (senza gestione heartbeat per semplicità)
        while True:
            try:
                # Ricevi eventuali messaggi dal client
                data = await websocket.receive_text()

                # Gestisci messaggi specifici se necessario
                if data == 'ping':
                    await websocket.send_text('pong')

            except WebSocketDisconnect:
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for site {site_id_str}")
    except Exception as e:
        logger.error(f"WebSocket error for site {site_id_str}: {e}")
    finally:
        await notification_manager.disconnect(websocket, site_id_str)


# Export per uso nei servizi
__all__ = ['notifications_router', 'notification_manager']