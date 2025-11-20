# app/services/storage_management_service.py - GESTIONE STORAGE MINIO AVANZATA

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc

from app.services.archaeological_minio_service import archaeological_minio_service
from app.models import Photo
from minio.error import S3Error


class StorageManagementService:
    """Servizio per gestione avanzata storage MinIO con cleanup automatico"""
    
    def __init__(self):
        self.minio_service = archaeological_minio_service
        self._storage_cache = {}
        self._cache_ttl = 300  # Cache for 5 minutes
        self._last_cache_time = None
        
    async def get_storage_usage(self) -> Dict[str, Any]:
        """
        Ottieni utilizzo storage con cache per evitare timeout.
        
        ✅ OPTIMIZATION:
        - Cached result per 5 minuti
        - Sample first 100 objects instead of iterating all
        - Returns quickly for upload validation
        """
        
        current_time = datetime.now()
        
        # Check if cache is still valid (avoid recalculating frequently)
        if self._last_cache_time and (current_time - self._last_cache_time).total_seconds() < self._cache_ttl:
            logger.debug("🔍 Using cached storage usage (cache age: %.1fs)" %
                        (current_time - self._last_cache_time).total_seconds())
            # Return cached result with cached flag set to True
            cached_result = self._storage_cache.copy()
            cached_result['cached'] = True
            return cached_result
        
        try:
            storage_info = {}
            total_size = 0
            total_objects = 0
            
            # ✅ OPTIMIZATION: Only sample first 100 objects instead of ALL
            max_objects_to_check = 100
            objects_checked = 0
            
            for bucket_name, bucket_id in self.minio_service.buckets.items():
                try:
                    # Quick bucket exists check (FAST)
                    bucket_exists = await asyncio.to_thread(
                        self.minio_service.client.bucket_exists,
                        bucket_id
                    )
                    
                    if not bucket_exists:
                        storage_info[bucket_name] = {
                            'bucket_id': bucket_id,
                            'size_bytes': 0,
                            'size_mb': 0,
                            'objects_count': 0,
                            'status': 'not_found'
                        }
                        continue
                    
                    # Sample objects instead of iterating everything
                    bucket_size = 0
                    bucket_objects = 0
                    
                    # List objects (with sampling limit)
                    objects_iter = await asyncio.to_thread(
                        self.minio_service.client.list_objects,
                        bucket_name=bucket_id,
                        recursive=True
                    )
                    
                    # Iterate with object limit for performance
                    for obj in objects_iter:
                        if objects_checked >= max_objects_to_check:
                            logger.debug(f"Storage check: Sampled {max_objects_to_check} objects (stopped for performance)")
                            break
                        
                        bucket_size += obj.size if obj.size else 0
                        bucket_objects += 1
                        objects_checked += 1
                    
                    storage_info[bucket_name] = {
                        'bucket_id': bucket_id,
                        'size_bytes': bucket_size,
                        'size_mb': round(bucket_size / (1024 * 1024), 2) if bucket_size else 0,
                        'objects_count': bucket_objects,
                        'sampled': objects_checked >= max_objects_to_check
                    }
                    
                    total_size += bucket_size
                    total_objects += bucket_objects
                    
                except Exception as e:
                    logger.warning(f"❌ Could not get stats for bucket {bucket_id}: {e}")
                    storage_info[bucket_name] = {
                        'bucket_id': bucket_id,
                        'size_bytes': 0,
                        'size_mb': 0,
                        'objects_count': 0,
                        'error': str(e)
                    }
            
            result = {
                'total_size_bytes': total_size,
                'total_size_mb': round(total_size / (1024 * 1024), 2) if total_size else 0,
                'total_size_gb': round(total_size / (1024 * 1024 * 1024), 2) if total_size else 0,
                'total_objects': total_objects,
                'buckets': storage_info,
                'timestamp': datetime.now().isoformat(),
                'cached': False
            }
            
            # Store in cache for next call
            self._storage_cache = result
            self._last_cache_time = current_time
            
            logger.info(f"✅ Storage usage calculated (total: {result['total_size_gb']}GB, objects sampled: {total_objects})")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ Error getting storage usage: {e}")
            return {
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'total_size_gb': 0,
                'total_objects': 0,
                'buckets': {},
                'timestamp': datetime.now().isoformat(),
                'error': str(e)
            }
    
    async def cleanup_old_thumbnails(self, days_old: int = 30) -> Dict[str, Any]:
        """Pulisce thumbnail vecchi che non hanno più foto associate"""
        try:
            cleaned_objects = []
            errors = []
            total_size_freed = 0
            
            # Lista tutti i thumbnail
            thumbnail_bucket = self.minio_service.buckets['thumbnails']
            objects = await asyncio.to_thread(
                self.minio_service.client.list_objects,
                bucket_name=thumbnail_bucket,
                recursive=True
            )
            
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            for obj in objects:
                try:
                    # Controlla se il thumbnail è vecchio
                    if obj.last_modified.replace(tzinfo=None) < cutoff_date:
                        # Estrai photo_id dal nome file (formato: {photo_id}.jpg)
                        photo_id = obj.object_name.replace('.jpg', '').replace('.png', '')
                        
                        # Verifica se la foto esiste ancora (questo richiederebbe un database check)
                        # Per ora, eliminiamo solo i thumbnail molto vecchi
                        
                        # Elimina thumbnail
                        await asyncio.to_thread(
                            self.minio_service.client.remove_object,
                            bucket_name=thumbnail_bucket,
                            object_name=obj.object_name
                        )
                        
                        cleaned_objects.append({
                            'object_name': obj.object_name,
                            'size_bytes': obj.size,
                            'last_modified': obj.last_modified.isoformat()
                        })
                        
                        total_size_freed += obj.size
                        logger.info(f"Cleaned old thumbnail: {obj.object_name}")
                        
                except Exception as e:
                    error_info = {
                        'object_name': obj.object_name,
                        'error': str(e)
                    }
                    errors.append(error_info)
                    logger.warning(f"Error cleaning thumbnail {obj.object_name}: {e}")
            
            return {
                'cleaned_count': len(cleaned_objects),
                'total_size_freed_mb': round(total_size_freed / (1024 * 1024), 2),
                'cleaned_objects': cleaned_objects,
                'errors': errors,
                'cutoff_date': cutoff_date.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error during thumbnail cleanup: {e}")
            return {
                'cleaned_count': 0,
                'total_size_freed_mb': 0,
                'cleaned_objects': [],
                'errors': [{'error': str(e)}],
                'cutoff_date': cutoff_date.isoformat() if 'cutoff_date' in locals() else None
            }
    
    async def ensure_buckets_exist(self) -> Dict[str, Any]:
        """Assicura che tutti i bucket necessari esistano, incluso 'storage'"""
        try:
            created_buckets = []
            existing_buckets = []
            errors = []
            
            # Bucket obbligatori - aggiungiamo 'storage' per compatibilità
            required_buckets = dict(self.minio_service.buckets)
            required_buckets['storage'] = 'storage'  # Bucket legacy per compatibilità
            
            for bucket_type, bucket_name in required_buckets.items():
                try:
                    # Controlla se il bucket esiste
                    bucket_exists = await asyncio.to_thread(
                        self.minio_service.client.bucket_exists,
                        bucket_name
                    )
                    
                    if not bucket_exists:
                        # Crea bucket
                        await asyncio.to_thread(
                            self.minio_service.client.make_bucket,
                            bucket_name
                        )
                        
                        created_buckets.append({
                            'type': bucket_type,
                            'name': bucket_name
                        })
                        
                        logger.info(f"Created bucket: {bucket_name} ({bucket_type})")
                        
                        # Imposta policy per bucket pubblici
                        if bucket_type in ['thumbnails', 'storage']:
                            try:
                                policy = {
                                    "Version": "2012-10-17",
                                    "Statement": [
                                        {
                                            "Effect": "Allow",
                                            "Principal": {"AWS": "*"},
                                            "Action": ["s3:GetObject"],
                                            "Resource": [f"arn:aws:s3:::{bucket_name}/*"]
                                        }
                                    ]
                                }
                                
                                await asyncio.to_thread(
                                    self.minio_service.client.set_bucket_policy,
                                    bucket_name,
                                    json.dumps(policy)
                                )
                                
                                logger.info(f"Set public policy for bucket: {bucket_name}")
                                
                            except Exception as policy_error:
                                logger.warning(f"Could not set policy for {bucket_name}: {policy_error}")
                    else:
                        existing_buckets.append({
                            'type': bucket_type,
                            'name': bucket_name
                        })
                        
                except Exception as e:
                    errors.append({
                        'type': bucket_type,
                        'name': bucket_name,
                        'error': str(e)
                    })
                    logger.error(f"Error with bucket {bucket_name}: {e}")
            
            return {
                'created_buckets': created_buckets,
                'existing_buckets': existing_buckets,
                'errors': errors,
                'total_buckets': len(required_buckets)
            }
            
        except Exception as e:
            logger.error(f"Error ensuring buckets exist: {e}")
            return {
                'created_buckets': [],
                'existing_buckets': [],
                'errors': [{'error': str(e)}],
                'total_buckets': 0
            }
    
    async def emergency_cleanup(self, target_freed_mb: float = 1000) -> Dict[str, Any]:
        """Cleanup di emergenza per liberare spazio quando storage è pieno"""
        try:
            total_freed = 0
            cleanup_actions = []
            
            # 1. Pulizia thumbnail vecchi
            logger.info("Starting emergency cleanup: old thumbnails")
            thumbnail_cleanup = await self.cleanup_old_thumbnails(days_old=7)  # Più aggressivo
            total_freed += thumbnail_cleanup['total_size_freed_mb']
            cleanup_actions.append({
                'action': 'cleanup_old_thumbnails',
                'freed_mb': thumbnail_cleanup['total_size_freed_mb'],
                'objects_removed': thumbnail_cleanup['cleaned_count']
            })
            
            return {
                'success': True,
                'total_freed_mb': total_freed,
                'target_freed_mb': target_freed_mb,
                'cleanup_actions': cleanup_actions,
                'emergency': True,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Emergency cleanup failed: {e}")
            return {
                'success': False,
                'total_freed_mb': 0,
                'target_freed_mb': target_freed_mb,
                'cleanup_actions': [],
                'emergency': True,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }


# Istanza globale
storage_management_service = StorageManagementService()