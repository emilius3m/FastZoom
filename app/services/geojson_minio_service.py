"""Servizio per la gestione di file GeoJSON su MinIO anziché nel database."""

import io
import json
import asyncio
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from loguru import logger
from fastapi import HTTPException

from app.services.archaeological_minio_service import archaeological_minio_service


class GeoJSONMinIOService:
    """Servizio per gestire file GeoJSON su MinIO anziché nel database."""
    
    def __init__(self):
        self.bucket_name = archaeological_minio_service.buckets['documents']  # Usa bucket documenti per GeoJSON
        self.base_path = "geojson_layers" # Percorso base per i file GeoJSON
        
    async def save_geojson_layer(
        self, 
        geojson_data: Dict[str, Any], 
        layer_id: str, 
        site_id: str,
        map_id: str,
        layer_name: str = None
    ) -> str:
        """
        Salva un file GeoJSON su MinIO.
        
        Args:
            geojson_data: Dati GeoJSON da salvare
            layer_id: ID univoco del layer
            site_id: ID del sito archeologico
            map_id: ID della mappa a cui appartiene il layer
            layer_name: Nome opzionale del layer (per metadati)
            
        Returns:
            str: URL MinIO del file salvato
        """
        try:
            # Validazione base del formato GeoJSON
            if not isinstance(geojson_data, dict) or 'type' not in geojson_data:
                raise HTTPException(status_code=400, detail="Dati GeoJSON non validi")
            
            # Serializza i dati GeoJSON in formato JSON
            geojson_json = json.dumps(geojson_data, indent=2, ensure_ascii=False)
            geojson_bytes = geojson_json.encode('utf-8')
            
            # Crea il percorso MinIO: geojson_layers/{site_id}/{map_id}/{layer_id}.geojson
            object_name = f"{self.base_path}/{site_id}/{map_id}/{layer_id}.geojson"
            
            # Prepara metadati per il file GeoJSON
            metadata = {
                'x-amz-meta-site-id': site_id,
                'x-amz-meta-map-id': map_id,
                'x-amz-meta-layer-id': layer_id,
                'x-amz-meta-layer-name': layer_name or f"GeoJSON Layer {layer_id}",
                'x-amz-meta-file-type': 'geojson',
                'x-amz-meta-content-type': 'application/geo+json',
                'x-amz-meta-created': datetime.now().isoformat(),
                'x-amz-meta-features-count': str(len(geojson_data.get('features', [])))
            }
            
            # Upload del file su MinIO
            result = await asyncio.to_thread(
                archaeological_minio_service.client.put_object,
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(geojson_bytes),
                length=len(geojson_bytes),
                content_type='application/geo+json',
                metadata=metadata
            )
            
            logger.info(f"GeoJSON layer saved to MinIO: {object_name} ({len(geojson_bytes)} bytes)")
            
            # Restituisce l'URL MinIO del file salvato
            return f"minio://{self.bucket_name}/{object_name}"
            
        except Exception as e:
            logger.error(f"Error saving GeoJSON layer to MinIO: {e}")
            raise HTTPException(status_code=500, detail=f"Errore salvataggio GeoJSON: {str(e)}")
    
    async def get_geojson_layer(self, layer_id: str, site_id: str, map_id: str, db_session: Optional[Any] = None) -> Optional[Dict[str, Any]]:
        """
        Recupera un file GeoJSON da MinIO, checking database for the actual MinIO URL first.

        Args:
            layer_id: ID del layer da recuperare
            site_id: ID del sito archeologico
            map_id: ID della mappa a cui appartiene il layer

        Returns:
            Dict: Dati GeoJSON o None se non trovato
        """
        # First, check if we can get the MinIO URL from the database
        minio_url = None
        if db_session is not None:
            try:
                from sqlalchemy import select, and_
                from app.models.geographic_maps import GeographicMapLayer
                from uuid import UUID

                # Query the database for the layer
                stmt = select(GeographicMapLayer).where(
                    and_(
                        GeographicMapLayer.id == UUID(layer_id),
                        GeographicMapLayer.site_id == UUID(site_id),
                        GeographicMapLayer.map_id == UUID(map_id)
                    )
                )
                result = await db_session.execute(stmt)
                layer = result.scalar_one_or_none()

                if layer and layer.geojson_data:
                    # Check if the geojson_data contains a MinIO URL reference
                    if isinstance(layer.geojson_data, dict) and 'minio_url' in layer.geojson_data:
                        minio_url = layer.geojson_data['minio_url']
                        logger.debug(f"Found MinIO URL in database for layer {layer_id}: {minio_url}")
                    elif isinstance(layer.geojson_data, dict) and 'minio_url' not in layer.geojson_data:
                        # The database contains the actual GeoJSON data, not a reference
                        logger.debug(f"GeoJSON layer retrieved directly from database: {layer_id}")
                        return layer.geojson_data

            except Exception as e:
                logger.debug(f"Could not query database for layer {layer_id}: {e}")

        # If we have a MinIO URL from the database, try to use it directly
        if minio_url:
            try:
                geojson_content = await archaeological_minio_service.get_file(minio_url)

                if isinstance(geojson_content, bytes):
                    geojson_content = geojson_content.decode('utf-8')

                # Parse del JSON
                geojson_data = json.loads(geojson_content)

                logger.debug(f"GeoJSON layer retrieved from MinIO using database URL: {minio_url}")
                return geojson_data

            except Exception as e:
                logger.debug(f"Failed to retrieve from database MinIO URL {minio_url}: {e}")

        # Fallback: try standard path (for newly created layers with consistent IDs)
        object_name = f"{self.base_path}/{site_id}/{map_id}/{layer_id}.geojson"

        try:
            # Recupera il contenuto del file da MinIO
            geojson_content = await archaeological_minio_service.get_file(
                f"minio://{self.bucket_name}/{object_name}"
            )

            if isinstance(geojson_content, bytes):
                geojson_content = geojson_content.decode('utf-8')

            # Parse del JSON
            geojson_data = json.loads(geojson_content)

            logger.debug(f"GeoJSON layer retrieved from MinIO: {object_name}")
            return geojson_data

        except Exception as e:
            logger.debug(f"Standard path not found: {object_name} - {e}")

            # Try legacy path without map_id
            legacy_object_name = f"{self.base_path}/{site_id}/{layer_id}.geojson"

            try:
                logger.debug(f"Trying legacy path: {legacy_object_name}")
                # Recupera il contenuto del file da MinIO con percorso legacy
                geojson_content = await archaeological_minio_service.get_file(
                    f"minio://{self.bucket_name}/{legacy_object_name}"
                )

                if isinstance(geojson_content, bytes):
                    geojson_content = geojson_content.decode('utf-8')

                # Parse del JSON
                geojson_data = json.loads(geojson_content)

                logger.debug(f"GeoJSON layer retrieved from MinIO (legacy path): {legacy_object_name}")
                return geojson_data

            except Exception as e2:
                logger.debug(f"Legacy path not found: {legacy_object_name} - {e2}")
                logger.debug(f"GeoJSON layer not found in MinIO or database for layer_id: {layer_id}, site_id: {site_id}, map_id: {map_id}")
                return None
    
    
    async def delete_geojson_layer(self, layer_id: str, site_id: str, map_id: str) -> bool:
        """
        Elimina un file GeoJSON da MinIO.
        
        Args:
            layer_id: ID del layer da eliminare
            site_id: ID del sito archeologico
            map_id: ID della mappa a cui appartiene il layer
            
        Returns:
            bool: True se eliminato con successo, False altrimenti
        """
        try:
            # Costruisce il percorso del file
            object_name = f"{self.base_path}/{site_id}/{map_id}/{layer_id}.geojson"
            
            # Elimina il file da MinIO
            success = await archaeological_minio_service.remove_file(
                f"minio://{self.bucket_name}/{object_name}"
            )
            
            if success:
                logger.info(f"GeoJSON layer deleted from MinIO: {object_name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error deleting GeoJSON layer from MinIO: {e}")
            return False
    
    async def get_geojson_layer_url(self, layer_id: str, site_id: str, map_id: str, expires_hours: int = 24) -> Optional[str]:
        """
        Genera un URL presigned per accedere al file GeoJSON su MinIO.
        
        Args:
            layer_id: ID del layer
            site_id: ID del sito archeologico
            map_id: ID della mappa a cui appartiene il layer
            expires_hours: Ore di validità dell'URL (default 24)
            
        Returns:
            str: URL presigned o None se non trovato
        """
        try:
            # Costruisce il percorso del file
            object_name = f"{self.base_path}/{site_id}/{map_id}/{layer_id}.geojson"
            
            # Genera URL presigned
            url = await asyncio.to_thread(
                archaeological_minio_service.client.presigned_get_object,
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=timedelta(hours=expires_hours)
            )
            
            logger.debug(f"Presigned URL generated for GeoJSON: {object_name}")
            return url
            
        except Exception as e:
            logger.error(f"Error generating presigned URL for GeoJSON: {e}")
            return None
    
    async def list_site_geojson_layers(self, site_id: str) -> List[Dict[str, Any]]:
        """
        Elenca tutti i layer GeoJSON per un sito specifico usando solo il percorso standard.
        
        Args:
            site_id: ID del sito archeologico
            
        Returns:
            List[Dict]: Lista di informazioni sui layer GeoJSON
        """
        try:
            # Cerca solo nel percorso standard: geojson_layers/{site_id}/
            prefix = f"{self.base_path}/{site_id}/"
            
            layers = []
            
            # Usa il client MinIO direttamente per elencare gli oggetti
            objects = await asyncio.to_thread(
                archaeological_minio_service.client.list_objects,
                bucket_name=self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            
            for obj in objects:
                # Controlla se è un file GeoJSON
                if obj.object_name.endswith('.geojson'):
                    
                    # Ottieni metadati dell'oggetto
                    try:
                        stat = await asyncio.to_thread(
                            archaeological_minio_service.client.stat_object,
                            bucket_name=self.bucket_name,
                            object_name=obj.object_name
                        )
                        
                        # Estrai informazioni dai metadati
                        metadata = stat.metadata
                        layer_info = {
                            'layer_id': metadata.get('x-amz-meta-layer-id', ''),
                            'map_id': metadata.get('x-amz-meta-map-id', ''),
                            'layer_name': metadata.get('x-amz-meta-layer-name', ''),
                            'object_name': obj.object_name,
                            'size': obj.size,
                            'last_modified': obj.last_modified,
                            'features_count': int(metadata.get('x-amz-meta-features-count', 0)),
                            'url': f"minio://{self.bucket_name}/{obj.object_name}"
                        }
                        layers.append(layer_info)
                    except Exception as e:
                        logger.warning(f"Could not get metadata for {obj.object_name}: {e}")
                        # In caso di errore con i metadati, aggiungi comunque informazioni base
                        layer_info = {
                            'layer_id': '',
                            'map_id': '',
                            'layer_name': '',
                            'object_name': obj.object_name,
                            'size': obj.size,
                            'last_modified': obj.last_modified,
                            'features_count': 0,
                            'url': f"minio://{self.bucket_name}/{obj.object_name}"
                        }
                        layers.append(layer_info)
        
            logger.info(f"Found {len(layers)} GeoJSON layers for site {site_id}")
            return layers
            
        except Exception as e:
            logger.error(f"Error listing GeoJSON layers for site {site_id}: {e}")
            return []


# Istanza globale del servizio
geojson_minio_service = GeoJSONMinIOService()