# app/routes/api/notifications_ws.py - WebSocket per notifiche tiles in tempo reale

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from loguru import logger
from typing import Dict, Set
from uuid import UUID
import json
import asyncio

from app.core.security import get_current_user_id, get_current_user_token, SecurityService

notifications_router = APIRouter()

# Manager per connessioni WebSocket attive
class NotificationManager:
    def __init__(self):
        # Dict[site_id, Set[WebSocket]]
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.connection_states: Dict[WebSocket, bool] = {}  # Track if connection is alive
        self.closing_states: Dict[WebSocket, bool] = {}  # Track if connection is being closed
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, site_id: str):
        """Connetti un client WebSocket per un sito specifico"""
        # Note: websocket.accept() is called in the main handler, not here

        async with self.lock:
            if site_id not in self.active_connections:
                self.active_connections[site_id] = set()
            self.active_connections[site_id].add(websocket)
            self.connection_states[websocket] = True  # Mark as alive
            self.closing_states[websocket] = False  # Not closing

        # Check for potential frontend reconnect issues
        rapid_reconnect = self.detect_rapid_reconnect(site_id, websocket)

        logger.info(f"WebSocket connected for site {site_id}. Total connections: {len(self.active_connections.get(site_id, []))}")
        if rapid_reconnect:
            logger.warning(f"Possible rapid reconnect detected for site {site_id}")

        # Log connection statistics for debugging
        stats = self.get_connection_stats()
        logger.debug(f"WebSocket stats - Total: {stats['total_active_connections']}, Alive: {stats['alive_connections']}, Dead: {stats['dead_connections']}, Closing: {stats['closing_connections']}")
    
    def is_connection_alive(self, websocket: WebSocket) -> bool:
        """Verifica se una connessione WebSocket è ancora attiva"""
        # First check our internal state tracking
        if websocket in self.connection_states:
            if not self.connection_states[websocket]:
                return False  # We marked it as dead

        # Then check the actual WebSocket state
        try:
            # Check if websocket is in connected state - WebSocketState.CONNECTED is typically value 1
            return websocket.client_state.value == 1  # WebSocketState.CONNECTED is 1
        except Exception:
            # If we can't check the state, mark it as dead
            self.connection_states[websocket] = False
            return False

    def mark_connection_dead(self, websocket: WebSocket):
        """Mark a connection as dead to prevent further operations"""
        self.connection_states[websocket] = False
        self.closing_states[websocket] = True  # Also mark as closing to prevent double-close

    def get_connection_stats(self) -> dict:
        """Get statistics about WebSocket connections for debugging"""
        total_connections = sum(len(conns) for conns in self.active_connections.values())
        alive_connections = len([ws for ws in self.connection_states.values() if ws])
        dead_connections = len([ws for ws in self.connection_states.values() if not ws])
        closing_connections = len([ws for ws in self.closing_states.values() if ws])

        return {
            'total_active_connections': total_connections,
            'alive_connections': alive_connections,
            'dead_connections': dead_connections,
            'closing_connections': closing_connections,
            'sites_with_connections': list(self.active_connections.keys())
        }

    def detect_rapid_reconnect(self, site_id: str, websocket: WebSocket) -> bool:
        """Detect if this might be a rapid reconnect from the frontend"""
        # Check if we recently had connections for this site that died quickly
        # This could indicate frontend connection issues
        if site_id in self.active_connections:
            connection_count = len(self.active_connections[site_id])
            if connection_count > 3:  # More than 3 connections for same site
                logger.warning(f"High connection count ({connection_count}) for site {site_id}, possible frontend reconnect loop")
                return True
        return False

    async def disconnect(self, websocket: WebSocket, site_id: str):
        """Disconnetti un client WebSocket"""
        # Check if we're already closing this connection
        if websocket in self.closing_states and self.closing_states[websocket]:
            logger.debug(f"WebSocket already being closed for site {site_id}")
            return

        # Mark connection as dead and closing
        self.connection_states[websocket] = False
        self.closing_states[websocket] = True

        try:
            # Check if WebSocket is already closed before attempting to close
            if self.is_connection_alive(websocket):
                await websocket.close()
                logger.debug(f"WebSocket closed successfully for site {site_id}")
            else:
                logger.debug(f"WebSocket was already closed for site {site_id}")
        except Exception as e:
            error_str = str(e).lower()
            if any(err in error_str for err in ['closed', 'disconnect', 'connection', 'unexpected asgi message']):
                logger.debug(f"WebSocket already closed for site {site_id}: {e}")
            else:
                logger.warning(f"Error closing WebSocket for site {site_id}: {e}")

        async with self.lock:
            if site_id in self.active_connections:
                self.active_connections[site_id].discard(websocket)
                if not self.active_connections[site_id]:
                    del self.active_connections[site_id]

        # Clean up the state tracking
        if websocket in self.connection_states:
            del self.connection_states[websocket]
        if websocket in self.closing_states:
            del self.closing_states[websocket]

        logger.info(f"WebSocket disconnected for site {site_id}")
        logger.debug(f"Remaining connections for site {site_id}: {len(self.active_connections.get(site_id, []))}")
        logger.debug(f"Total active WebSocket connections: {sum(len(conns) for conns in self.active_connections.values())}")
    
    async def send_notification(self, site_id: str, notification: dict):
        """Invia notifica a tutti i client connessi per un sito"""
        if site_id not in self.active_connections:
            logger.debug(f"No active connections for site {site_id}")
            return

        disconnected = set()

        # Get connections under lock to prevent race conditions
        async with self.lock:
            connections = self.active_connections.get(site_id, set()).copy()

        for connection in connections:
            try:
                # Double-check if WebSocket is still alive before sending
                if not self.is_connection_alive(connection):
                    logger.warning(f"WebSocket not alive for site {site_id}, removing from active connections")
                    disconnected.add(connection)
                    continue

                # Send with timeout to prevent hanging
                await asyncio.wait_for(connection.send_json(notification), timeout=5.0)
                logger.debug(f"Notification sent to site {site_id}: {notification.get('type')}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout sending notification to WebSocket for site {site_id}")
                disconnected.add(connection)
            except Exception as e:
                # Handle specific WebSocket closed errors
                error_str = str(e).lower()
                if any(err in error_str for err in ['closed', 'disconnect', 'connection', 'response already completed', 'unexpected asgi message']):
                    logger.warning(f"WebSocket connection lost for site {site_id}: {e}")
                else:
                    logger.error(f"Unexpected error sending notification to site {site_id}: {e}")
                disconnected.add(connection)

        # Remove dead connections under lock
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

    async def broadcast_photo_filters_applied(
        self,
        site_id: str,
        filters: dict,
        total_results: int,
        search_query: str = None,
        applied_filters_count: int = 0
    ):
        """Invia notifica applicazione filtri foto"""
        notification = {
            'type': 'photo_filters_applied',
            'site_id': site_id,
            'filters': filters,
            'total_results': total_results,
            'search_query': search_query,
            'applied_filters_count': applied_filters_count,
            'timestamp': str(asyncio.get_event_loop().time())
        }

        await self.send_notification(site_id, notification)

    async def cleanup_dead_connections(self):
        """Periodically clean up dead connections to prevent memory leaks"""
        dead_connections = []

        for site_id in list(self.active_connections.keys()):
            site_connections = self.active_connections[site_id]
            for connection in list(site_connections):
                if not self.is_connection_alive(connection):
                    dead_connections.append((connection, site_id))

        for connection, site_id in dead_connections:
            logger.info(f"Cleaning up dead connection for site {site_id}")
            await self.disconnect(connection, site_id)

    def get_health_status(self) -> dict:
        """Get health status of WebSocket connections"""
        stats = self.get_connection_stats()
        return {
            'status': 'healthy' if stats['dead_connections'] == 0 else 'degraded',
            'stats': stats,
            'recommendations': self._get_health_recommendations(stats)
        }

    def _get_health_recommendations(self, stats: dict) -> list:
        """Get recommendations based on connection stats"""
        recommendations = []

        if stats['dead_connections'] > 0:
            recommendations.append(f"Found {stats['dead_connections']} dead connections that should be cleaned up")

        if stats['total_active_connections'] > 50:
            recommendations.append("High number of active connections, consider load balancing")

        if len(stats['sites_with_connections']) > 20:
            recommendations.append("Many sites with active connections, monitor memory usage")

        return recommendations

    async def broadcast_photo_updated(
        self,
        site_id: str,
        photo_id: str,
        updated_fields: list,
        photo_filename: str,
        user_id: str
    ):
        """Invia notifica aggiornamento foto"""
        notification = {
            'type': 'photo_updated',
            'site_id': site_id,
            'photo_id': photo_id,
            'updated_fields': updated_fields,
            'photo_filename': photo_filename,
            'user_id': user_id,
            'timestamp': str(asyncio.get_event_loop().time())
        }

        await self.send_notification(site_id, notification)

    async def broadcast_photo_deleted(
        self,
        site_id: str,
        photo_id: str,
        photo_filename: str = None,
        user_id: str = None
    ):
        """Invia notifica eliminazione foto"""
        notification = {
            'type': 'photo_deleted',
            'site_id': site_id,
            'photo_id': photo_id,
            'photo_filename': photo_filename,
            'user_id': user_id,
            'timestamp': str(asyncio.get_event_loop().time())
        }

        await self.send_notification(site_id, notification)

# Istanza globale del manager
notification_manager = NotificationManager()


@notifications_router.websocket("/site/{site_id}/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    site_id: UUID
):
    """
    WebSocket endpoint per notifiche in tempo reale

    Messaggi inviati dal server:

    1. Notifiche progresso tiles:
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

    2. Notifiche filtri foto applicati:
    {
        "type": "photo_filters_applied",
        "site_id": "xxx",
        "filters": {...},
        "total_results": 12,
        "search_query": "test",
        "applied_filters_count": 2
    }

    3. Notifiche aggiornamento foto:
    {
        "type": "photo_updated",
        "site_id": "xxx",
        "photo_id": "xxx",
        "updated_fields": ["description", "inventory_number", "material"],
        "photo_filename": "foto.jpg",
        "user_id": "xxx",
        "timestamp": "1234567890.123"
    }
    """
    site_id_str = str(site_id)

    try:
        # Verifica autenticazione e autorizzazione al sito
        # Per WebSocket, dobbiamo gestire l'autenticazione manualmente
        # poiché i WebSocket non supportano le dipendenze FastAPI direttamente

        # Accetta prima la connessione WebSocket
        await websocket.accept()

        # For cookie-based authentication, WebSocket inherits cookies automatically
        # No need to receive auth token from client - use cookie authentication
        print(f"WebSocket connection established for site {site_id_str} - using cookie authentication")

        # Verifica autenticazione tramite cookie
        try:
            from fastapi import Request
            from app.database.db import get_async_session, async_session_maker
            from sqlalchemy.ext.asyncio import AsyncSession
            from app.services.auth_service import AuthService

            # Crea un request fittizio usando i cookie del WebSocket
            # WebSocket eredita automaticamente i cookie dal browser
            class FakeRequest:
                def __init__(self, websocket):
                    # In FastAPI, WebSocket cookies are available via websocket.cookies
                    self.cookies = websocket.cookies or {}

            fake_request = FakeRequest(websocket)

            # Verifica autenticazione usando le dipendenze esistenti
            user_id = await get_current_user_id(fake_request)
            
            # Get token payload to check for superuser status
            token_payload = await get_current_user_token(fake_request)
            is_superuser = token_payload.get("su", False)
            
            # SUPERUSER BYPASS: superusers have automatic access to all sites
            if is_superuser:
                logger.debug(f"Superuser accessing site {site_id_str} via WebSocket - BYPASS granted")
            else:
                # For regular users, verify site access from DATABASE
                # Fetch user sites from database instead of token (sites no longer in JWT)
                async with async_session_maker() as db:
                    user_sites = await AuthService.get_user_sites_with_permissions(db, user_id)

                    # Verifica accesso al sito specifico
                    site_info = next(
                        (site for site in user_sites if site.get("site_id") == site_id_str),
                        None
                    )

                    if not site_info:
                        try:
                            await websocket.send_json({
                                "type": "error",
                                "message": f"Accesso negato al sito {site_id_str}"
                            })
                        except Exception:
                            pass  # WebSocket might already be closed
                        finally:
                            await notification_manager.disconnect(websocket, site_id_str)
                        return

        except Exception as e:
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Errore autenticazione: {str(e)}"
                })
            except Exception:
                pass  # WebSocket might already be closed
            finally:
                notification_manager.mark_connection_dead(websocket)
                await notification_manager.disconnect(websocket, site_id_str)
            return


        # Connetti WebSocket dopo autenticazione
        await notification_manager.connect(websocket, site_id_str)

        # Invia messaggio di benvenuto dopo autenticazione
        try:
            await websocket.send_json({
                'type': 'connected',
                'site_id': site_id_str,
                'message': 'WebSocket connesso - autenticazione completata - riceverai notifiche tiles in tempo reale'
            })
        except Exception as e:
            logger.error(f"Failed to send welcome message for site {site_id_str}: {e}")
            notification_manager.mark_connection_dead(websocket)
            await notification_manager.disconnect(websocket, site_id_str)
            return

        # Mantieni connessione attiva (senza gestione heartbeat per semplicità)
        while True:
            try:
                # Ricevi eventuali messaggi dal client
                data = await websocket.receive_text()
                
                # Gestisci messaggi specifici se necessario
                if data == 'ping':
                    await websocket.send_text('pong')
                    
            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected by client for site {site_id_str}")
                break
            except Exception as e:
                error_str = str(e).lower()
                if any(err in error_str for err in ['closed', 'disconnect', 'connection']):
                    logger.warning(f"WebSocket connection error for site {site_id_str}: {e}")
                else:
                    logger.error(f"Unexpected error in WebSocket loop for site {site_id_str}: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for site {site_id_str}")
    except Exception as e:
        error_str = str(e).lower()
        if any(err in error_str for err in ['closed', 'disconnect', 'connection', 'response already completed', 'unexpected asgi message']):
            logger.warning(f"WebSocket connection error for site {site_id_str}: {e}")
        else:
            logger.error(f"WebSocket error for site {site_id_str}: {e}")
        # Mark connection as dead to prevent further operations
        notification_manager.mark_connection_dead(websocket)
    finally:
        # Ensure WebSocket is properly disconnected and removed from active connections
        await notification_manager.disconnect(websocket, site_id_str)


# Health check endpoint for WebSocket connections
@notifications_router.get("/ws/health")
async def websocket_health():
    """Get health status of WebSocket connections"""
    health_status = notification_manager.get_health_status()

    return {
        "status": health_status['status'],
        "stats": health_status['stats'],
        "recommendations": health_status['recommendations'],
        "timestamp": str(asyncio.get_event_loop().time())
    }

# Cleanup endpoint for manual cleanup of dead connections
@notifications_router.post("/ws/cleanup")
async def cleanup_websockets():
    """Manually trigger cleanup of dead WebSocket connections"""
    await notification_manager.cleanup_dead_connections()

    stats = notification_manager.get_connection_stats()
    return {
        "message": "Cleanup completed",
        "stats": stats,
        "timestamp": str(asyncio.get_event_loop().time())
    }

# Export per uso nei servizi
__all__ = ['notifications_router', 'notification_manager']