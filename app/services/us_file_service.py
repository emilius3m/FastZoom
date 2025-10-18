# app/services/us_file_service.py
"""
Service per gestione file US/USM integrato con sistema MinIO FastZoom
Riutilizza l'infrastruttura esistente di upload/storage foto
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from loguru import logger

from app.models.stratigraphy import USFile, UnitaStratigrafica, UnitaStratigraficaMuraria
from app.models.stratigraphy import us_files_association, usm_files_association
from app.services.storage_service import storage_service
from app.services.deep_zoom_minio_service import deep_zoom_minio_service


class USFileService:
    """Service per gestione file US/USM con integrazione MinIO"""
    
    # Tipi file supportati per US/USM
    SUPPORTED_FILE_TYPES = {
        'pianta': {
            'mimetypes': ['image/jpeg', 'image/png', 'image/tiff', 'application/pdf'],
            'max_size_mb': 50,
            'description': 'Piante archeologiche'
        },
        'sezione': {
            'mimetypes': ['image/jpeg', 'image/png', 'image/tiff', 'application/pdf'],
            'max_size_mb': 50,
            'description': 'Sezioni stratigrafiche'
        },
        'prospetto': {
            'mimetypes': ['image/jpeg', 'image/png', 'image/tiff', 'application/pdf'],
            'max_size_mb': 50,
            'description': 'Prospetti architettonici'
        },
        'fotografia': {
            'mimetypes': ['image/jpeg', 'image/png', 'image/tiff'],
            'max_size_mb': 20,
            'description': 'Fotografie documentarie'
        },
        'documento': {
            'mimetypes': ['application/pdf', 'application/msword', 
                         'application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
            'max_size_mb': 30,
            'description': 'Documenti allegati'
        }
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = storage_service
    
    async def upload_us_file(
        self,
        us_id: UUID,
        file: UploadFile,
        file_type: str,
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None
    ) -> USFile:
        """Upload file per US con validazione e storage MinIO"""
        
        # Validazione tipo file
        if file_type not in self.SUPPORTED_FILE_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Tipo file non supportato: {file_type}"
            )
        
        # Validazione mimetype
        file_config = self.SUPPORTED_FILE_TYPES[file_type]
        if file.content_type not in file_config['mimetypes']:
            raise HTTPException(
                status_code=400,
                detail=f"Formato non supportato per {file_type}: {file.content_type}"
            )
        
        # Validazione dimensione
        file_size = 0
        await file.seek(0)
        content = await file.read()
        file_size = len(content)
        await file.seek(0)  # Reset per upload
        
        max_size = file_config['max_size_mb'] * 1024 * 1024
        if file_size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File troppo grande. Max {file_config['max_size_mb']}MB per {file_type}"
            )
        
        # Verifica esistenza US
        us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == us_id)
        us_result = await self.db.execute(us_query)
        us = us_result.scalar_one_or_none()
        
        if not us:
            raise HTTPException(status_code=404, detail="US non trovata")
        
        try:
            # Upload file su MinIO (riutilizza sistema esistente)
            filename, filepath, actual_filesize = await self.storage.save_upload_file(
                file, str(us.site_id), str(user_id), subfolder="us_files"
            )
            
            # Prepara metadati file
            file_metadata = metadata or {}
            
            # Estrai metadati immagine se applicabile
            if file.content_type.startswith('image/'):
                try:
                    from PIL import Image
                    import io
                    await file.seek(0)
                    image_content = await file.read()
                    image = Image.open(io.BytesIO(image_content))
                    file_metadata.update({
                        'width': image.width,
                        'height': image.height,
                        'format': image.format
                    })
                    await file.seek(0)
                except Exception as e:
                    logger.warning(f"Impossibile estrarre metadati immagine: {e}")
            
            # Crea record USFile
            us_file = USFile(
                site_id=us.site_id,
                filename=filename,
                original_filename=file.filename,
                filepath=filepath,
                filesize=actual_filesize,
                mimetype=file.content_type,
                file_category='disegno' if file_type in ['pianta', 'sezione', 'prospetto'] else file_type,
                title=file_metadata.get('title', ''),
                description=file_metadata.get('description', ''),
                scale_ratio=file_metadata.get('scale_ratio', ''),
                drawing_type=file_type if file_type in ['pianta', 'sezione', 'prospetto'] else None,
                tavola_number=file_metadata.get('tavola_number', ''),
                photo_date=file_metadata.get('photo_date'),
                photographer=file_metadata.get('photographer', ''),
                camera_info=file_metadata.get('camera_info', ''),
                width=file_metadata.get('width'),
                height=file_metadata.get('height'),
                uploaded_by=user_id,
                is_published=file_metadata.get('is_published', False)
            )
            
            self.db.add(us_file)
            await self.db.flush()  # Per ottenere ID
            
            # Crea associazione US-File
            association_stmt = us_files_association.insert().values(
                us_id=us_id,
                file_id=us_file.id,
                file_type=file_type,
                ordine=file_metadata.get('ordine', 0)
            )
            await self.db.execute(association_stmt)
            
            await self.db.commit()
            
            # Avvia deep zoom per immagini grandi
            if (file.content_type.startswith('image/') and 
                file_metadata.get('width', 0) > 2000 and 
                file_metadata.get('height', 0) > 2000):
                
                us_file.is_deepzoom_enabled = True
                us_file.deepzoom_status = 'scheduled'
                await self.db.commit()
                
                # Avvia processing deep zoom in background
                asyncio.create_task(
                    deep_zoom_minio_service.process_single_image(
                        str(us_file.id), filepath, str(us.site_id)
                    )
                )
                logger.info(f"Deep zoom schedulato per US file {us_file.id}")
            
            logger.info(f"File {file_type} caricato per US {us.us_code}: {filename}")
            return us_file
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Errore upload file US: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Errore nel caricamento del file: {str(e)}"
            )
    
    async def upload_usm_file(
        self,
        usm_id: UUID,
        file: UploadFile,
        file_type: str,
        user_id: UUID,
        metadata: Optional[Dict[str, Any]] = None
    ) -> USFile:
        """Upload file per USM - logica simile a US"""
        
        # Validazioni identiche a US
        if file_type not in self.SUPPORTED_FILE_TYPES:
            raise HTTPException(status_code=400, detail=f"Tipo file non supportato: {file_type}")
        
        # Verifica esistenza USM
        usm_query = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == usm_id)
        usm_result = await self.db.execute(usm_query)
        usm = usm_result.scalar_one_or_none()
        
        if not usm:
            raise HTTPException(status_code=404, detail="USM non trovata")
        
        # Processo upload identico, ma con associazione USM
        try:
            filename, filepath, actual_filesize = await self.storage.save_upload_file(
                file, str(usm.site_id), str(user_id), subfolder="us_files"
            )
            
            file_metadata = metadata or {}
            
            # Estrai metadati immagine
            if file.content_type.startswith('image/'):
                try:
                    from PIL import Image
                    import io
                    await file.seek(0)
                    image_content = await file.read()
                    image = Image.open(io.BytesIO(image_content))
                    file_metadata.update({
                        'width': image.width,
                        'height': image.height,
                        'format': image.format
                    })
                except Exception as e:
                    logger.warning(f"Errore metadati immagine USM: {e}")
            
            # Crea USFile
            us_file = USFile(
                site_id=usm.site_id,
                filename=filename,
                original_filename=file.filename,
                filepath=filepath,
                filesize=actual_filesize,
                mimetype=file.content_type,
                file_category='disegno' if file_type in ['pianta', 'sezione', 'prospetto'] else file_type,
                title=file_metadata.get('title', ''),
                description=file_metadata.get('description', ''),
                scale_ratio=file_metadata.get('scale_ratio', ''),
                drawing_type=file_type if file_type in ['pianta', 'sezione', 'prospetto'] else None,
                tavola_number=file_metadata.get('tavola_number', ''),
                photo_date=file_metadata.get('photo_date'),
                photographer=file_metadata.get('photographer', ''),
                width=file_metadata.get('width'),
                height=file_metadata.get('height'),
                uploaded_by=user_id
            )
            
            self.db.add(us_file)
            await self.db.flush()
            
            # Associazione USM-File
            association_stmt = usm_files_association.insert().values(
                usm_id=usm_id,
                file_id=us_file.id,
                file_type=file_type,
                ordine=file_metadata.get('ordine', 0)
            )
            await self.db.execute(association_stmt)
            
            await self.db.commit()
            
            logger.info(f"File {file_type} caricato per USM {usm.usm_code}: {filename}")
            return us_file
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Errore upload file USM: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Errore caricamento: {str(e)}")
    
    async def get_us_files(self, us_id: UUID, file_type: Optional[str] = None) -> List[USFile]:
        """Ottieni file di una US, opzionalmente filtrati per tipo"""
        
        query = select(USFile).join(
            us_files_association, USFile.id == us_files_association.c.file_id
        ).where(us_files_association.c.us_id == us_id)
        
        if file_type:
            query = query.where(us_files_association.c.file_type == file_type)
        
        query = query.order_by(us_files_association.c.ordine, USFile.created_at)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_usm_files(self, usm_id: UUID, file_type: Optional[str] = None) -> List[USFile]:
        """Ottieni file di una USM"""
        
        query = select(USFile).join(
            usm_files_association, USFile.id == usm_files_association.c.file_id
        ).where(usm_files_association.c.usm_id == usm_id)
        
        if file_type:
            query = query.where(usm_files_association.c.file_type == file_type)
        
        query = query.order_by(usm_files_association.c.ordine, USFile.created_at)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def delete_us_file(self, us_id: UUID, file_id: UUID, user_id: UUID) -> bool:
        """Elimina file US con cleanup storage"""
        
        try:
            # Trova file
            file_query = select(USFile).where(USFile.id == file_id)
            file_result = await self.db.execute(file_query)
            us_file = file_result.scalar_one_or_none()
            
            if not us_file:
                raise HTTPException(status_code=404, detail="File non trovato")
            
            # Verifica associazione US
            assoc_query = select(us_files_association).where(
                and_(
                    us_files_association.c.us_id == us_id,
                    us_files_association.c.file_id == file_id
                )
            )
            assoc_result = await self.db.execute(assoc_query)
            if not assoc_result.first():
                raise HTTPException(status_code=404, detail="Associazione file-US non trovata")
            
            # Elimina file da storage
            if us_file.filepath:
                try:
                    await self.storage.delete_file(us_file.filepath)
                    logger.info(f"File eliminato da storage: {us_file.filepath}")
                except Exception as e:
                    logger.warning(f"Errore eliminazione storage: {e}")
            
            # Elimina thumbnail se esiste
            if us_file.thumbnail_path:
                try:
                    await self.storage.delete_file(us_file.thumbnail_path)
                except Exception as e:
                    logger.warning(f"Errore eliminazione thumbnail: {e}")
            
            # Elimina associazione
            delete_assoc = us_files_association.delete().where(
                and_(
                    us_files_association.c.us_id == us_id,
                    us_files_association.c.file_id == file_id
                )
            )
            await self.db.execute(delete_assoc)
            
            # Elimina record file se non ha altre associazioni
            other_assoc_query = select(us_files_association).where(
                us_files_association.c.file_id == file_id
            )
            other_assoc = await self.db.execute(other_assoc_query)
            
            usm_assoc_query = select(usm_files_association).where(
                usm_files_association.c.file_id == file_id
            )
            usm_assoc = await self.db.execute(usm_assoc_query)
            
            if not other_assoc.first() and not usm_assoc.first():
                await self.db.delete(us_file)
            
            await self.db.commit()
            logger.info(f"File US {file_id} eliminato da US {us_id}")
            return True
            
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Errore eliminazione file US: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")
    
    async def update_file_metadata(
        self, 
        file_id: UUID, 
        metadata: Dict[str, Any], 
        user_id: UUID
    ) -> USFile:
        """Aggiorna metadati file US/USM"""
        
        file_query = select(USFile).where(USFile.id == file_id)
        file_result = await self.db.execute(file_query)
        us_file = file_result.scalar_one_or_none()
        
        if not us_file:
            raise HTTPException(status_code=404, detail="File non trovato")
        
        # Campi aggiornabili
        updatable_fields = [
            'title', 'description', 'scale_ratio', 'tavola_number',
            'photo_date', 'photographer', 'camera_info', 'is_published'
        ]
        
        for field in updatable_fields:
            if field in metadata:
                setattr(us_file, field, metadata[field])
        
        from datetime import datetime
        us_file.updated_at = datetime.utcnow()
        await self.db.commit()
        
        logger.info(f"Metadati file {file_id} aggiornati da user {user_id}")
        return us_file
    
    async def get_files_summary_for_us(self, us_id: UUID) -> Dict[str, Any]:
        """Riassunto file per US con conteggi per tipo"""
        
        files = await self.get_us_files(us_id)
        
        # Raggruppa per tipo
        files_by_type = {}
        for file_obj in files:
            # Trova tipo dal join association
            file_type_query = select(us_files_association.c.file_type).where(
                and_(
                    us_files_association.c.us_id == us_id,
                    us_files_association.c.file_id == file_obj.id
                )
            )
            type_result = await self.db.execute(file_type_query)
            file_type = type_result.scalar_one_or_none()
            
            if file_type not in files_by_type:
                files_by_type[file_type] = []
            files_by_type[file_type].append(file_obj.to_dict())
        
        return {
            'piante': files_by_type.get('pianta', []),
            'sezioni': files_by_type.get('sezione', []),
            'prospetti': files_by_type.get('prospetto', []),
            'fotografie': files_by_type.get('fotografia', []),
            'documenti': files_by_type.get('documento', []),
            'counts': {
                'piante': len(files_by_type.get('pianta', [])),
                'sezioni': len(files_by_type.get('sezione', [])),
                'prospetti': len(files_by_type.get('prospetto', [])),
                'fotografie': len(files_by_type.get('fotografia', [])),
                'documenti': len(files_by_type.get('documento', [])),
                'total': len(files)
            }
        }