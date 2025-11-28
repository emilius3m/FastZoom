# app/services/us_file_service.py
"""
Service per gestione file US/USM integrato con sistema MinIO FastZoom
Riutilizza l'infrastruttura esistente di upload/storage foto
"""

import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple
import uuid
from uuid import UUID, uuid4
from pathlib import Path
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_
from loguru import logger

from app.models.stratigraphy import USFile, UnitaStratigrafica, UnitaStratigraficaMuraria
from app.models.stratigraphy import us_files_association, usm_files_association
from app.models.documentation_and_field import Photo
from app.services.storage_service import storage_service
from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service


def safe_uuid_str(uuid_input) -> str:
    """
    Safely convert UUID to string for database operations.
    
    This helper function ensures UUID objects are always converted to strings
    before being passed to database operations, preventing SQLite binding errors.
    
    Args:
        uuid_input: UUID object or string
        
    Returns:
        String representation of UUID
    """
    if uuid_input is None:
        return ""
    
    # If it's already a string, handle different formats
    if isinstance(uuid_input, str):
        # If it's a 32-char hex string, convert to standard UUID format
        if len(uuid_input) == 32 and '-' not in uuid_input:
            try:
                uuid_obj = UUID(uuid_input)
                return str(uuid_obj)
            except:
                return uuid_input  # Return as-is if conversion fails
        return uuid_input
    
    # Convert UUID object to string
    return str(uuid_input)


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
        
        # Verifica esistenza US con normalizzazione UUID per compatibilità
        # Prova prima con l'UUID normalizzato, poi con fallback multi-livello
        us_id_str = str(us_id)
        normalized_us_id = self._normalize_us_id(us_id)
        
        us_query = select(UnitaStratigrafica).where(
            or_(
                UnitaStratigrafica.id == us_id,
                UnitaStratigrafica.id == normalized_us_id,
                UnitaStratigrafica.id == us_id_str.replace('-', '')
            )
        )
        us_result = await self.db.execute(us_query)
        us = us_result.scalar_one_or_none()
        
        if not us:
            logger.error(f"US non trovata con ID: {us_id} (normalizzato: {normalized_us_id}, senza trattini: {us_id_str.replace('-', '')})")
            raise HTTPException(status_code=404, detail="US non trovata")
        
        try:
            # Read file content once
            await file.seek(0)
            file_content = await file.read()
            actual_filesize = len(file_content)
            await file.seek(0)  # Reset for potential re-read

            # Prepara metadati file
            file_metadata = metadata or {}

            # Estrai metadati immagine se applicabile
            if file.content_type.startswith('image/'):
                try:
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(file_content))
                    file_metadata.update({
                        'width': image.width,
                        'height': image.height,
                        'format': image.format
                    })
                except Exception as e:
                    logger.warning(f"Impossibile estrarre metadati immagine: {e}")

            # Generate unique filename
            from uuid import uuid4
            file_extension = Path(file.filename).suffix.lower()
            unique_filename = f"{str(us.site_id)}_{str(user_id)}_{uuid4().hex[:8]}{file_extension}"

            # Upload file to appropriate MinIO bucket based on file type
            from app.services.archaeological_minio_service import archaeological_minio_service

            if file_type == 'documento' or file.content_type == 'application/pdf':
                # Upload document to documents bucket
                document_metadata = {
                    'document_type': file_type,
                    'title': file_metadata.get('title', ''),
                    'author': file_metadata.get('photographer', ''),
                    'date': str(file_metadata.get('photo_date')) if file_metadata.get('photo_date') else None,
                    'file_size': actual_filesize,
                    'original_filename': file.filename,
                    'content_type': file.content_type
                }
                upload_url = await archaeological_minio_service.upload_document(
                    file_content,
                    unique_filename,
                    str(us.site_id),
                    document_metadata
                )
                # Parse filepath from URL: minio://bucket/path -> bucket/path
                if upload_url.startswith("minio://"):
                    filepath = upload_url[8:]  # Remove "minio://"
                else:
                    filepath = f"{archaeological_minio_service.buckets['documents']}/{str(us.site_id)}/{unique_filename}"
            else:
                # Upload photo/image to photos bucket
                photo_metadata = {
                    'inventory_number': file_metadata.get('tavola_number', ''),
                    'excavation_area': '',
                    'stratigraphic_unit': '',
                    'material': '',
                    'object_type': file_type,
                    'chronology_period': '',
                    'photo_type': file_type,
                    'photographer': file_metadata.get('photographer', ''),
                    'description': file_metadata.get('description', ''),
                    'keywords': '',
                    'find_date': str(file_metadata.get('photo_date')) if file_metadata.get('photo_date') else None,
                    'conservation_status': '',
                    'catalog_number': '',
                    'grid_square': '',
                    'depth_level': '',
                    'finder': '',
                    'excavation_campaign': '',
                    'material_details': '',
                    'object_function': '',
                    'length_cm': None,
                    'width_cm': file_metadata.get('width'),
                    'height_cm': file_metadata.get('height'),
                    'diameter_cm': None,
                    'weight_grams': None,
                    'chronology_culture': '',
                    'dating_from': None,
                    'dating_to': None,
                    'dating_notes': '',
                    'conservation_notes': '',
                    'restoration_history': '',
                    'bibliography': '',
                    'comparative_references': '',
                    'external_links': '',
                    'copyright_holder': '',
                    'license_type': '',
                    'usage_rights': '',
                    'validation_notes': '',
                    'file_size': actual_filesize,
                    'original_filename': file.filename,
                    'content_type': file.content_type
                }
                upload_url = await archaeological_minio_service.upload_photo_with_metadata(
                    file_content,
                    unique_filename,
                    str(us.site_id),
                    photo_metadata
                )
                # Parse filepath from URL: minio://bucket/path -> bucket/path
                if upload_url.startswith("minio://"):
                    filepath = upload_url[8:]  # Remove "minio://"
                else:
                    filepath = f"{archaeological_minio_service.buckets['photos']}/{str(us.site_id)}/{unique_filename}"

            # Crea record USFile
            us_file = USFile(
                id=safe_uuid_str(uuid.uuid4()),  # Generate and convert UUID to string
                site_id=safe_uuid_str(us.site_id),  # Convert site_id to string
                filename=unique_filename,
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
                uploaded_by=safe_uuid_str(user_id),
                created_by=safe_uuid_str(user_id),
                updated_by=safe_uuid_str(user_id),
                validated_by=safe_uuid_str(file_metadata.get('validated_by')) if file_metadata.get('validated_by') else None,
                is_published=file_metadata.get('is_published', False)
            )
           
            self.db.add(us_file)
            await self.db.flush()  # Per ottenere ID
           
            # Crea associazione US-File
            association_stmt = us_files_association.insert().values(
                us_id=safe_uuid_str(us_id),
                file_id=safe_uuid_str(us_file.id),  # Convert file_id to string
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
                try:
                    # Carica il contenuto del file per il deep zoom
                    from app.services.archaeological_minio_service import archaeological_minio_service
                    file_content = await archaeological_minio_service.get_file(f"minio://{archaeological_minio_service.buckets['photos']}/{filepath}")
                   
                    # Schedula generazione tiles in background
                    deep_zoom_service = get_deep_zoom_minio_service()
                    await deep_zoom_service.schedule_tiles_generation_async(
                        str(us_file.id), file_content, str(us.site_id)
                    )
                    logger.info(f"Deep zoom schedulato per US file {us_file.id}")
                except Exception as e:
                    logger.warning(f"Impossibile schedulare deep zoom per US file {us_file.id}: {e}")
                    # Non bloccare l'upload se il deep zoom fallisce
           
            logger.info(f"File {file_type} caricato per US {us.us_code}: {unique_filename}")
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
        
        # Verifica esistenza USM con normalizzazione UUID per compatibilità
        # Prova prima con l'UUID normalizzato, poi con fallback multi-livello
        usm_id_str = str(usm_id)
        normalized_usm_id = self._normalize_us_id(usm_id)
        
        usm_query = select(UnitaStratigraficaMuraria).where(
            or_(
                UnitaStratigraficaMuraria.id == usm_id,
                UnitaStratigraficaMuraria.id == normalized_usm_id,
                UnitaStratigraficaMuraria.id == usm_id_str.replace('-', '')
            )
        )
        usm_result = await self.db.execute(usm_query)
        usm = usm_result.scalar_one_or_none()
        
        if not usm:
            logger.error(f"USM non trovata con ID: {usm_id} (normalizzato: {normalized_usm_id}, senza trattini: {usm_id_str.replace('-', '')})")
            raise HTTPException(status_code=404, detail="USM non trovata")
        
        # Processo upload identico, ma con associazione USM
        try:
            # Read file content once
            await file.seek(0)
            file_content = await file.read()
            actual_filesize = len(file_content)
            await file.seek(0)  # Reset for potential re-read

            file_metadata = metadata or {}

            # Estrai metadati immagine
            if file.content_type.startswith('image/'):
                try:
                    from PIL import Image
                    import io
                    image = Image.open(io.BytesIO(file_content))
                    file_metadata.update({
                        'width': image.width,
                        'height': image.height,
                        'format': image.format
                    })
                except Exception as e:
                    logger.warning(f"Errore metadati immagine USM: {e}")

            # Generate unique filename
            from uuid import uuid4
            file_extension = Path(file.filename).suffix.lower()
            unique_filename = f"{str(usm.site_id)}_{str(user_id)}_{uuid4().hex[:8]}{file_extension}"

            # Upload file to appropriate MinIO bucket based on file type
            from app.services.archaeological_minio_service import archaeological_minio_service

            if file_type == 'documento' or file.content_type == 'application/pdf':
                # Upload document to documents bucket
                document_metadata = {
                    'document_type': file_type,
                    'title': file_metadata.get('title', ''),
                    'author': file_metadata.get('photographer', ''),
                    'date': str(file_metadata.get('photo_date')) if file_metadata.get('photo_date') else None,
                    'file_size': actual_filesize,
                    'original_filename': file.filename,
                    'content_type': file.content_type
                }
                upload_url = await archaeological_minio_service.upload_document(
                    file_content,
                    unique_filename,
                    str(usm.site_id),
                    document_metadata
                )
                # Parse filepath from URL: minio://bucket/path -> bucket/path
                if upload_url.startswith("minio://"):
                    filepath = upload_url[8:]  # Remove "minio://"
                else:
                    filepath = f"{archaeological_minio_service.buckets['documents']}/{str(usm.site_id)}/{unique_filename}"
            else:
                # Upload photo/image to photos bucket
                photo_metadata = {
                    'inventory_number': file_metadata.get('tavola_number', ''),
                    'excavation_area': '',
                    'stratigraphic_unit': '',
                    'material': '',
                    'object_type': file_type,
                    'chronology_period': '',
                    'photo_type': file_type,
                    'photographer': file_metadata.get('photographer', ''),
                    'description': file_metadata.get('description', ''),
                    'keywords': '',
                    'find_date': str(file_metadata.get('photo_date')) if file_metadata.get('photo_date') else None,
                    'conservation_status': '',
                    'catalog_number': '',
                    'grid_square': '',
                    'depth_level': '',
                    'finder': '',
                    'excavation_campaign': '',
                    'material_details': '',
                    'object_function': '',
                    'length_cm': None,
                    'width_cm': file_metadata.get('width'),
                    'height_cm': file_metadata.get('height'),
                    'diameter_cm': None,
                    'weight_grams': None,
                    'chronology_culture': '',
                    'dating_from': None,
                    'dating_to': None,
                    'dating_notes': '',
                    'conservation_notes': '',
                    'restoration_history': '',
                    'bibliography': '',
                    'comparative_references': '',
                    'external_links': '',
                    'copyright_holder': '',
                    'license_type': '',
                    'usage_rights': '',
                    'validation_notes': '',
                    'file_size': actual_filesize,
                    'original_filename': file.filename,
                    'content_type': file.content_type
                }
                upload_url = await archaeological_minio_service.upload_photo_with_metadata(
                    file_content,
                    unique_filename,
                    str(usm.site_id),
                    photo_metadata
                )
                # Parse filepath from URL: minio://bucket/path -> bucket/path
                if upload_url.startswith("minio://"):
                    filepath = upload_url[8:]  # Remove "minio://"
                else:
                    filepath = f"{archaeological_minio_service.buckets['photos']}/{str(usm.site_id)}/{unique_filename}"

            # Crea USFile
            us_file = USFile(
                id=safe_uuid_str(uuid4()),  # Generate and convert UUID to string
                site_id=safe_uuid_str(usm.site_id),  # Convert site_id to string
                filename=unique_filename,
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
                uploaded_by=safe_uuid_str(user_id),
                created_by=safe_uuid_str(user_id),
                updated_by=safe_uuid_str(user_id),
                validated_by=safe_uuid_str(file_metadata.get('validated_by')) if file_metadata.get('validated_by') else None
            )
           
            self.db.add(us_file)
            await self.db.flush()
           
            # Associazione USM-File
            association_stmt = usm_files_association.insert().values(
                usm_id=safe_uuid_str(usm_id),
                file_id=safe_uuid_str(us_file.id),  # Convert file_id to string
                file_type=file_type,
                ordine=file_metadata.get('ordine', 0)
            )
            await self.db.execute(association_stmt)
           
            await self.db.commit()
           
            logger.info(f"File {file_type} caricato per USM {usm.usm_code}: {unique_filename}")
            return us_file
           
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Errore upload file USM: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Errore caricamento: {str(e)}")
    
    async def get_us_files(self, us_id: UUID, file_type: Optional[str] = None) -> List[USFile]:
        """Ottieni file di una US, opzionalmente filtrati per tipo"""
        
        # Normalizza UUID per compatibilità con fallback multi-livello
        us_id_str = str(us_id)
        normalized_us_id = self._normalize_us_id(us_id)
        
        query = select(USFile).join(
            us_files_association, USFile.id == us_files_association.c.file_id
        ).where(
            or_(
                us_files_association.c.us_id == safe_uuid_str(us_id),
                us_files_association.c.us_id == normalized_us_id,
                us_files_association.c.us_id == us_id_str.replace('-', '')
            )
        )
        
        if file_type:
            query = query.where(us_files_association.c.file_type == file_type)
        
        query = query.order_by(us_files_association.c.ordine, USFile.created_at)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def get_usm_files(self, usm_id: UUID, file_type: Optional[str] = None) -> List[USFile]:
        """Ottieni file di una USM"""
        
        # Normalizza UUID per compatibilità con fallback multi-livello
        usm_id_str = str(usm_id)
        normalized_usm_id = self._normalize_us_id(usm_id)
        
        query = select(USFile).join(
            usm_files_association, USFile.id == usm_files_association.c.file_id
        ).where(
            or_(
                usm_files_association.c.usm_id == safe_uuid_str(usm_id),
                usm_files_association.c.usm_id == normalized_usm_id,
                usm_files_association.c.usm_id == usm_id_str.replace('-', '')
            )
        )
        
        if file_type:
            query = query.where(usm_files_association.c.file_type == file_type)
        
        query = query.order_by(usm_files_association.c.ordine, USFile.created_at)
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def delete_us_file(self, us_id: UUID, file_id: UUID, user_id: UUID) -> bool:
        """Elimina file US con cleanup storage e gestione StaleDataError - supporta sia USFile che Photo"""
        
        try:
            # Primo tentativo: cerca file nella tabella USFile con fallback multi-livello per UUID
            us_file = await self._find_file_with_uuid_fallback(file_id)
            
            if us_file:
                # File trovato nella tabella USFile - procedi con eliminazione standard
                logger.info(f"File US trovato nella tabella USFile: id={us_file.id}, filename={us_file.filename}")
                return await self._delete_us_file_logic(us_id, us_file, user_id)
            
            # Secondo tentativo: cerca nella tabella Photo (foto archeologiche)
            photo = await self._find_photo_with_uuid_fallback(file_id)
            
            if photo:
                # Foto trovata nella tabella Photo - procedi con eliminazione specifica per foto
                logger.info(f"Foto trovata nella tabella Photo: id={photo.id}, filename={photo.filename}")
                return await self._delete_photo_logic(photo)
            
            # Terzo tentativo: fallback - ricerca esplicita per compatibilità con formati UUID diversi
            file_id_str = str(file_id)
            file_id_no_dashes = file_id_str.replace('-', '')
            
            # Ultimo tentativo USFile con fallback diretto
            us_file_query = select(USFile).where(
                or_(
                    USFile.id == file_id_str,
                    USFile.id == file_id_no_dashes,
                    USFile.id == self._normalize_us_id(file_id)
                )
            )
            us_result = await self.db.execute(us_file_query)
            us_file = us_result.scalar_one_or_none()
            
            if us_file:
                logger.info(f"File US trovato con fallback diretto: id={us_file.id}")
                return await self._delete_us_file_logic(us_id, us_file, user_id)
            
            # Ultimo tentativo Photo con fallback diretto
            photo_query = select(Photo).where(
                or_(
                    Photo.id == file_id_str,
                    Photo.id == file_id_no_dashes,
                    Photo.id == self._normalize_us_id(file_id)
                )
            )
            photo_result = await self.db.execute(photo_query)
            photo = photo_result.scalar_one_or_none()
            
            if photo:
                logger.info(f"Foto trovata con fallback diretto: id={photo.id}")
                return await self._delete_photo_logic(photo)
            
            # File non trovato in nessuna tabella
            logger.error(f"File/foto non trovato in nessuna tabella con ID: {file_id} (formati provati: {file_id_str}, {file_id_no_dashes}, {self._normalize_us_id(file_id)})")
            raise HTTPException(status_code=404, detail="File non trovato con nessun formato UUID")
        
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ Errore critico eliminazione file US {file_id}: {str(e)}")
            logger.exception(f"Full traceback per eliminazione file US {file_id}")
            raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")
    
    async def delete_usm_file(self, usm_id: UUID, file_id: UUID, user_id: UUID) -> bool:
        """Elimina file USM con cleanup storage e gestione errori migliorata"""
        
        try:
            # Trova file con fallback multi-livello per UUID
            us_file = await self._find_file_with_uuid_fallback(file_id)
            if not us_file:
                logger.error(f"File USM non trovato per ID: {file_id} (formato originale)")
                raise HTTPException(status_code=404, detail="File non trovato")
            
            # Log dettagli per debugging
            logger.info(f"Trovato file USM per eliminazione: id={us_file.id}, filename={us_file.filename}, filepath={us_file.filepath}")
            
            # Verifica associazione USM con fallback multi-livello
            usm_id_str = str(usm_id)
            normalized_usm_id = self._normalize_us_id(usm_id)
            usm_id_no_dashes = usm_id_str.replace('-', '')
            
            logger.info(f"Ricerca associazione USM-File con ID originali: usm_id={usm_id}, normalized={normalized_usm_id}, no_dashes={usm_id_no_dashes}")
            logger.info(f"Ricerca associazione USM-File con file_id: {safe_uuid_str(file_id)}")
            
            # Trova associazione con fallback multi-livello
            assoc_query = select(usm_files_association).where(
                and_(
                    or_(
                        usm_files_association.c.usm_id == usm_id_str,
                        usm_files_association.c.usm_id == normalized_usm_id,
                        usm_files_association.c.usm_id == usm_id_no_dashes
                    ),
                    usm_files_association.c.file_id == safe_uuid_str(file_id)
                )
            )
            assoc_result = await self.db.execute(assoc_query)
            association = assoc_result.first()
            
            if not association:
                logger.error(f"Associazione USM-File non trovata: usm_id={usm_id}, file_id={file_id}")
                # Tenta comunque di eliminare il file dal database se non ha più associazioni
                await self._try_orphan_file_cleanup(file_id)
                raise HTTPException(status_code=404, detail="Associazione file-USM non trovata")
            
            logger.info(f"Associazione USM-File trovata: usm_id={association.usm_id}, file_id={association.file_id}")
            
            # Elimina file da storage con retry
            storage_deleted = False
            if us_file.filepath:
                try:
                    await self.storage.delete_file(us_file.filepath)
                    storage_deleted = True
                    logger.info(f"✅ File eliminato da storage: {us_file.filepath}")
                except Exception as e:
                    logger.error(f"❌ Errore eliminazione storage: {e}")
                    # Continua con l'eliminazione del database anche se storage fallisce
            
            # Elimina thumbnail se esiste
            if us_file.thumbnail_path:
                try:
                    await self.storage.delete_file(us_file.thumbnail_path)
                    logger.info(f"✅ Thumbnail eliminato da storage: {us_file.thumbnail_path}")
                except Exception as e:
                    logger.warning(f"❌ Errore eliminazione thumbnail: {e}")
            
            # PRIMA: Elimina l'associazione USM-File
            delete_assoc = usm_files_association.delete().where(
                and_(
                    or_(
                        usm_files_association.c.usm_id == usm_id_str,
                        usm_files_association.c.usm_id == normalized_usm_id,
                        usm_files_association.c.usm_id == usm_id_no_dashes
                    ),
                    usm_files_association.c.file_id == safe_uuid_str(file_id)
                )
            )
            assoc_result = await self.db.execute(delete_assoc)
            logger.info(f"Associazione USM-File eliminata: {assoc_result.rowcount} righe")
            
            # DOPO: Verifica se il file ha altre associazioni ed elimina se orfano
            await self._cleanup_file_if_orphaned(file_id)
            
            await self.db.commit()
            
            # Log finale con stato completo
            status = "completato con successo" if storage_deleted else "completato (storage error)"
            logger.info(f"🗑️ Eliminazione file USM {file_id} {status}: storage={storage_deleted}, db=True")
            return True
           
        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            logger.error(f"❌ Errore critico eliminazione file USM {file_id}: {str(e)}")
            logger.exception(f"Full traceback per eliminazione file USM {file_id}")
            raise HTTPException(status_code=500, detail=f"Errore eliminazione: {str(e)}")
    
    async def update_file_metadata(
        self, 
        file_id: UUID, 
        metadata: Dict[str, Any], 
        user_id: UUID
    ) -> USFile:
        """Aggiorna metadati file US/USM"""
        
        file_query = select(USFile).where(USFile.id == safe_uuid_str(file_id))
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
    
    def _photo_to_usfile_dict(self, photo: Photo) -> Dict[str, Any]:
        """
        Converte un oggetto Photo in un dizionario compatibile con USFile
        per l'unificazione della visualizzazione delle fotografie documentarie
        """
        try:
            # Safely handle all attributes to avoid any potential async context issues
            return {
                'id': str(photo.id) if photo.id else '',
                'filename': getattr(photo, 'filename', ''),
                'original_filename': getattr(photo, 'original_filename', ''),
                'filepath': getattr(photo, 'filepath', ''),
                'filesize': getattr(photo, 'file_size', 0) or 0,
                'mimetype': getattr(photo, 'mime_type', 'image/jpeg') or 'image/jpeg',
                'file_category': 'fotografia',
                'title': getattr(photo, 'title', '') or '',
                'description': getattr(photo, 'description', '') or '',
                'scale_ratio': None,
                'drawing_type': None,
                'tavola_number': None,
                'photo_date': photo.photo_date.isoformat() if getattr(photo, 'photo_date', None) else None,
                'photographer': getattr(photo, 'photographer', '') or '',
                'camera_info': f"{getattr(photo, 'camera_make', '') or ''} {getattr(photo, 'camera_model', '') or ''}".strip(),
                'width': getattr(photo, 'width', None),
                'height': getattr(photo, 'height', None),
                'is_deepzoom_enabled': getattr(photo, 'has_deep_zoom', False),
                'thumbnail_url': f"/api/v1/photos/{photo.id}/thumbnail" if getattr(photo, 'thumbnail_path', None) else None,
                'download_url': f"/api/v1/photos/{photo.id}/download" if photo.id else None,
                'view_url': f"/api/v1/photos/{photo.id}/full" if photo.id else None,
                'is_published': getattr(photo, 'is_published', False),
                'is_validated': getattr(photo, 'is_validated', False),
                'created_at': photo.created_at.isoformat() if getattr(photo, 'created_at', None) else None,
                'updated_at': photo.updated_at.isoformat() if getattr(photo, 'updated_at', None) else None,
                'source': 'photo_table',  # Campo aggiuntivo per identificare la provenienza
                'deepzoom_status': getattr(photo, 'deepzoom_status', None),
                'is_deepzoom_ready': getattr(photo, 'is_deepzoom_ready', False)
            }
        except Exception as e:
            logger.error(f"Error converting photo to USFile dict: {e}")
            # Return a minimal safe dict if conversion fails
            return {
                'id': str(photo.id) if photo.id else '',
                'filename': getattr(photo, 'filename', 'error'),
                'file_category': 'fotografia',
                'source': 'photo_table',
                'error': True
            }

    async def _find_file_with_uuid_fallback(self, file_id: UUID) -> Optional[USFile]:
        """Trova file con fallback multi-livello per differenti formati UUID"""
        
        file_id_str = str(file_id)
        file_id_no_dashes = file_id_str.replace('-', '')
        
        logger.info(f"Ricerca file con fallback: original={file_id_str}, no_dashes={file_id_no_dashes}")
        
        # Primo tentativo: UUID standard con trattini
        file_query = select(USFile).where(USFile.id == file_id_str)
        result = await self.db.execute(file_query)
        us_file = result.scalar_one_or_none()
        
        if us_file:
            logger.info(f"File trovato con UUID standard: {file_id_str}")
            return us_file
        
        # Secondo tentativo: UUID senza trattini
        file_query = select(USFile).where(USFile.id == file_id_no_dashes)
        result = await self.db.execute(file_query)
        us_file = result.scalar_one_or_none()
        
        if us_file:
            logger.info(f"File trovato con UUID senza trattini: {file_id_no_dashes}")
            return us_file
        
        # Terzo tentativo: formato normalizzato
        normalized_id = self._normalize_us_id(file_id)
        file_query = select(USFile).where(USFile.id == normalized_id)
        result = await self.db.execute(file_query)
        us_file = result.scalar_one_or_none()
        
        if us_file:
            logger.info(f"File trovato con UUID normalizzato: {normalized_id}")
            return us_file
        
        logger.error(f"File non trovato con nessun formato UUID: {file_id_str}")
        return None
    
    async def _check_file_has_us_associations(self, file_id: UUID) -> bool:
        """Verifica se il file ha altre associazioni US (escluso l'US corrente)"""
        try:
            file_id_str = safe_uuid_str(file_id)
            
            # Conta tutte le associazioni US per questo file
            assoc_query = select(us_files_association).where(
                us_files_association.c.file_id == file_id_str
            )
            assoc_result = await self.db.execute(assoc_query)
            associations = assoc_result.all()
            
            # Se ci sono più di 0 associazioni, il file è ancora utilizzato
            has_associations = len(associations) > 0
            
            logger.info(f"File {file_id} ha {len(associations)} associazioni US: {has_associations}")
            
            return has_associations
            
        except Exception as e:
            logger.error(f"Errore verifica associazioni US per file {file_id}: {e}")
            # In caso di errore, assumi che ci siano associazioni per sicurezza
            return True
    
    async def _check_file_has_usm_associations(self, file_id: UUID) -> bool:
        """Verifica se il file ha associazioni USM"""
        try:
            file_id_str = safe_uuid_str(file_id)
            
            # Conta tutte le associazioni USM per questo file
            assoc_query = select(usm_files_association).where(
                usm_files_association.c.file_id == file_id_str
            )
            assoc_result = await self.db.execute(assoc_query)
            associations = assoc_result.all()
            
            # Se ci sono più di 0 associazioni, il file è utilizzato da USM
            has_associations = len(associations) > 0
            
            logger.info(f"File {file_id} ha {len(associations)} associazioni USM: {has_associations}")
            
            return has_associations
            
        except Exception as e:
            logger.error(f"Errore verifica associazioni USM per file {file_id}: {e}")
            # In caso di errore, assumi che non ci siano associazioni USM
            return False
    
    async def _fallback_delete_all_associations(self, file_id: UUID) -> None:
        """Elimina tutte le associazioni di un file come fallback per gestire StaleDataError"""
        try:
            file_id_str = safe_uuid_str(file_id)
            
            # Elimina tutte le associazioni US
            delete_us_assoc = us_files_association.delete().where(
                us_files_association.c.file_id == file_id_str
            )
            us_result = await self.db.execute(delete_us_assoc)
            logger.info(f"Eliminate {us_result.rowcount} associazioni US per file {file_id}")
            
            # Elimina tutte le associazioni USM
            delete_usm_assoc = usm_files_association.delete().where(
                usm_files_association.c.file_id == file_id_str
            )
            usm_result = await self.db.execute(delete_usm_assoc)
            logger.info(f"Eliminate {usm_result.rowcount} associazioni USM per file {file_id}")
            
        except Exception as e:
            logger.error(f"Errore eliminazione associazioni fallback per file {file_id}: {e}")
            # Non sollevare eccezione per non bloccare il processo principale

    async def _try_orphan_file_cleanup(self, file_id: UUID) -> bool:
        """Tenta di eliminare file orfano dal database"""
        try:
            # Controlla se il file esiste nel database
            file_id_str = safe_uuid_str(file_id)
            file_query = select(USFile).where(USFile.id == file_id_str)
            result = await self.db.execute(file_query)
            us_file = result.scalar_one_or_none()
            
            if not us_file:
                logger.info(f"File {file_id} non trovato nel database (già eliminato)")
                return True
            
            # Controlla se ha ancora associazioni
            us_assoc_query = select(us_files_association).where(
                us_files_association.c.file_id == file_id_str
            )
            us_assoc_result = await self.db.execute(us_assoc_query)
            
            usm_assoc_query = select(usm_files_association).where(
                usm_files_association.c.file_id == file_id_str
            )
            usm_assoc_result = await self.db.execute(usm_assoc_query)
            
            if not us_assoc_result.first() and not usm_assoc_result.first():
                # Il file è orfano, eliminalo
                await self.db.delete(us_file)
                logger.info(f"🗑️ File orfano {file_id} eliminato dal database")
                return True
            else:
                logger.info(f"File {file_id} ha ancora associazioni, non eliminato")
                return False
                
        except Exception as e:
            logger.error(f"Errore cleanup file orfano {file_id}: {e}")
            return False
    
    async def _cleanup_file_if_orphaned(self, file_id: UUID) -> bool:
        """Elimina file dal database se non ha più associazioni"""
        try:
            file_id_str = safe_uuid_str(file_id)
            
            # Controlla associazioni US
            us_assoc_query = select(us_files_association).where(
                us_files_association.c.file_id == file_id_str
            )
            us_assoc_result = await self.db.execute(us_assoc_query)
            
            # Controlla associazioni USM
            usm_assoc_query = select(usm_files_association).where(
                usm_files_association.c.file_id == file_id_str
            )
            usm_assoc_result = await self.db.execute(usm_assoc_query)
            
            us_has_assoc = us_assoc_result.first() is not None
            usm_has_assoc = usm_assoc_result.first() is not None
            
            logger.info(f"Verifica associazioni file {file_id}: US={us_has_assoc}, USM={usm_has_assoc}")
            
            if not us_has_assoc and not usm_has_assoc:
                # Il file è orfano, eliminalo dal database
                file_query = select(USFile).where(USFile.id == file_id_str)
                result = await self.db.execute(file_query)
                us_file = result.scalar_one_or_none()
                
                if us_file:
                    await self.db.delete(us_file)
                    logger.info(f"🗑️ File orfano {file_id} eliminato dal database: {us_file.filename}")
                    return True
                else:
                    logger.warning(f"File {file_id} da eliminare non trovato nel database")
                    return False
            else:
                logger.info(f"File {file_id} mantiene associazioni, non eliminato dal database")
                return False
                
        except Exception as e:
            logger.error(f"Errore verifica cleanup file {file_id}: {e}")
            return False
    
    def _normalize_us_id(self, us_id: UUID) -> str:
        """Normalizza ID US per compatibilità con diversi formati nel database"""
        us_id_str = str(us_id)
        
        # Se è già un UUID standard con trattini (formato atteso nel DB), restituiscilo
        if '-' in us_id_str and len(us_id_str) == 36:
            return us_id_str
        
        # Se è un hash esadecimale senza trattini (32 caratteri), converti in formato UUID
        if len(us_id_str) == 32:
            return f"{us_id_str[:8]}-{us_id_str[8:12]}-{us_id_str[12:16]}-{us_id_str[16:20]}-{us_id_str[20:]}"
        
        # Altri formati, restituisci come sono
        return us_id_str
    
    async def _find_photo_with_uuid_fallback(self, file_id: UUID) -> Optional[Photo]:
        """Trova foto con fallback multi-livello per differenti formati UUID"""
        
        file_id_str = str(file_id)
        file_id_no_dashes = file_id_str.replace('-', '')
        
        logger.info(f"Ricerca foto con fallback: original={file_id_str}, no_dashes={file_id_no_dashes}")
        
        # Primo tentativo: UUID standard con trattini
        photo_query = select(Photo).where(Photo.id == file_id_str)
        result = await self.db.execute(photo_query)
        photo = result.scalar_one_or_none()
        
        if photo:
            logger.info(f"Foto trovata con UUID standard: {file_id_str}")
            return photo
        
        # Secondo tentativo: UUID senza trattini
        photo_query = select(Photo).where(Photo.id == file_id_no_dashes)
        result = await self.db.execute(photo_query)
        photo = result.scalar_one_or_none()
        
        if photo:
            logger.info(f"Foto trovata con UUID senza trattini: {file_id_no_dashes}")
            return photo
        
        # Terzo tentativo: formato normalizzato
        normalized_id = self._normalize_us_id(file_id)
        photo_query = select(Photo).where(Photo.id == normalized_id)
        result = await self.db.execute(photo_query)
        photo = result.scalar_one_or_none()
        
        if photo:
            logger.info(f"Foto trovata con UUID normalizzato: {normalized_id}")
            return photo
        
        logger.error(f"Foto non trovata con nessun formato UUID: {file_id_str}")
        return None
    async def _delete_us_file_logic(self, us_id: UUID, us_file: USFile, user_id: UUID) -> bool:
        """Logica di eliminazione specifica per i file US dalla tabella USFile"""
        
        # Log dettagli per debugging
        logger.info(f"Trovato file US per eliminazione: id={us_file.id}, filename={us_file.filename}, filepath={us_file.filepath}")
        
        # Verifica se il file ha altre associazioni PRIMA di eliminare
        has_other_us_assoc = await self._check_file_has_us_associations(us_file.id)
        has_usm_assoc = await self._check_file_has_usm_associations(us_file.id)
        
        logger.info(f"Verifica associazioni file {us_file.id}: US-other={has_other_us_assoc}, USM={has_usm_assoc}")
        
        # Elimina file da storage con retry
        storage_deleted = False
        if us_file.filepath:
            try:
                await self.storage.delete_file(us_file.filepath)
                storage_deleted = True
                logger.info(f"✅ File eliminato da storage: {us_file.filepath}")
            except Exception as e:
                logger.error(f"❌ Errore eliminazione storage: {e}")
                # Continua con l'eliminazione del database anche se storage fallisce
        
        # Elimina thumbnail se esiste
        if us_file.thumbnail_path:
            try:
                await self.storage.delete_file(us_file.thumbnail_path)
                logger.info(f"✅ Thumbnail eliminato da storage: {us_file.thumbnail_path}")
            except Exception as e:
                logger.warning(f"❌ Errore eliminazione thumbnail: {e}")
        
        # STRATEGIA: Usa SQLAlchemy cascade per evitare StaleDataError
        # Rimuovi il file dalla collezione delle associazioni US per il suo specifico us_id
        if has_other_us_assoc:
            logger.info(f"File {us_file.id} ha altre associazioni US, elimino solo questa associazione")
            
            # Trova e rimuovi solo l'associazione specifica
            us_id_str = str(us_id)
            normalized_us_id = self._normalize_us_id(us_id)
            us_id_no_dashes = us_id_str.replace('-', '')
            
            # Rimuovi dalla collezione usando query diretta per evitare cascade
            delete_assoc = us_files_association.delete().where(
                and_(
                    or_(
                        us_files_association.c.us_id == us_id_str,
                        us_files_association.c.us_id == normalized_us_id,
                        us_files_association.c.us_id == us_id_no_dashes
                    ),
                    us_files_association.c.file_id == safe_uuid_str(us_file.id)
                )
            )
            
            try:
                result = await self.db.execute(delete_assoc)
                logger.info(f"Associazione US-File eliminata: {result.rowcount} righe")
            except Exception as e:
                if "expected to delete" in str(e) and "Only 0 were matched" in str(e):
                    logger.warning(f"Associazione US-File non trovata (già eliminata): us_id={us_id}, file_id={us_file.id}")
                else:
                    raise
        else:
            logger.info(f"File {us_file.id} non ha altre associazioni US, provo eliminazione tramite SQLAlchemy cascade")
            
            # Lascia che SQLAlchemy gestisca l'eliminazione tramite cascade
            # Questo evita StaleDataError perché SQLAlchemy gestisce l'ordine di eliminazione
            try:
                # Aggiorna il file per forzarne il rilevamento da SQLAlchemy
                await self.db.flush()
                
                # Elimina il file - SQLAlchemy gestirà automaticamente le associazioni
                await self.db.delete(us_file)
                logger.info(f"File {us_file.id} eliminato dal database con cascade")
            except Exception as e:
                if "is not bound" in str(e) or "detached" in str(e).lower():
                    logger.info(f"File {us_file.id} già eliminato dal database (cascade)")
                else:
                    logger.warning(f"Errore eliminazione file cascade: {e}")
                    # Fallback: eliminazione manuale delle associazioni rimanenti
                    await self._fallback_delete_all_associations(us_file.id)
        
        await self.db.commit()
        
        # Log finale con stato completo
        status = "completato con successo" if storage_deleted else "completato (storage error)"
        logger.info(f"🗑️ Eliminazione file US {us_file.id} {status}: storage={storage_deleted}, db=True")
        return True

    
    async def _delete_photo_logic(self, photo: Photo) -> bool:
        """Logica di eliminazione specifica per le foto dal Photo service"""
        try:
            # Elimina da storage
            if photo.filepath:
                try:
                    await self.storage.delete_file(photo.filepath)
                    logger.info(f"✅ File foto eliminato da storage: {photo.filepath}")
                except Exception as storage_e:
                    logger.warning(f"❌ Errore eliminazione storage foto: {storage_e}")
            
            # Elimina thumbnail se esiste
            if photo.thumbnail_path:
                try:
                    await self.storage.delete_file(photo.thumbnail_path)
                    logger.info(f"✅ Thumbnail foto eliminato da storage: {photo.thumbnail_path}")
                except Exception as thumb_e:
                    logger.warning(f"❌ Errore eliminazione thumbnail foto: {thumb_e}")
            
            # Elimina dal database
            await self.db.delete(photo)
            logger.info(f"✅ Foto {photo.id} eliminata dal database")
            return True
                
        except Exception as e:
            logger.error(f"❌ Errore eliminazione foto {photo.id}: {e}")
            return False
    
    async def get_files_summary_for_us(self, us_id: UUID) -> Dict[str, Any]:
        """Riassunto file per US con conteggi per tipo, includendo foto dalla tabella Photo"""
        
        # DEBUG: Log input parameters
        us_id_str = str(us_id)
        logger.info(f"[DEBUG] get_files_summary_for_us called with us_id: {us_id_str}")
        
        try:
            # 1. Ottieni i file US esistenti direttamente con query invece di chiamare get_us_files()
            # Questo evita il problema di contesto async/await
            files_query = select(USFile).join(
                us_files_association, USFile.id == us_files_association.c.file_id
            ).where(
                or_(
                    us_files_association.c.us_id == safe_uuid_str(us_id),
                    us_files_association.c.us_id == self._normalize_us_id(us_id),
                    us_files_association.c.us_id == us_id_str.replace('-', '')
                )
            ).order_by(us_files_association.c.ordine, USFile.created_at)
            
            files_result = await self.db.execute(files_query)
            files = files_result.scalars().all()
            logger.info(f"[DEBUG] Found {len(files)} US files for US {us_id_str}")
            
            # 2. Raggruppa per tipo i file US esistenti
            files_by_type = {}
            
            # Collect all file IDs to batch query their types
            file_ids = [safe_uuid_str(file_obj.id) for file_obj in files]
            
            # Batch query for all file types at once to reduce context switches
            if file_ids:
                file_types_query = select(
                    us_files_association.c.file_id,
                    us_files_association.c.file_type
                ).where(
                    and_(
                        us_files_association.c.us_id == safe_uuid_str(us_id),
                        us_files_association.c.file_id.in_(file_ids)
                    )
                )
                file_types_result = await self.db.execute(file_types_query)
                file_types = {row[0]: row[1] for row in file_types_result.all()}
            else:
                file_types = {}
            
            # Group files by type using the batched results
            for file_obj in files:
                file_type = file_types.get(safe_uuid_str(file_obj.id))
                logger.info(f"[DEBUG] File {file_obj.id} has type: {file_type}")
                
                if file_type not in files_by_type:
                    files_by_type[file_type] = []
                files_by_type[file_type].append(file_obj.to_dict())
            
            # 3. Recupera le foto dalla tabella Photo dove stratigraphic_unit == us_id
            # Prima ottieni l'US per ottenere il codice US
            us_query = select(UnitaStratigrafica).where(UnitaStratigrafica.id == safe_uuid_str(us_id))
            us_result = await self.db.execute(us_query)
            us = us_result.scalar_one_or_none()
            
            logger.info(f"[DEBUG] US query result: id={us.id if us else None}, us_code={us.us_code if us else None}")
            
            if us:
                logger.info(f"[DEBUG] US found: id={us.id}, us_code={us.us_code}, site_id={us.site_id}")
                
                # Normalizza l'ID US per la ricerca
                normalized_us_id = self._normalize_us_id(us_id)
                logger.info(f"[DEBUG] Normalized US ID: {normalized_us_id}")
                logger.info(f"[DEBUG] Original US ID string: {us_id_str}")
                logger.info(f"[DEBUG] US ID without dashes: {us_id_str.replace('-', '')}")
                
                # Cerca foto dove stratigraphic_unit corrisponde al codice US (fallback multi-livello)
                photos_query = select(Photo).where(
                    and_(
                        Photo.site_id == us.site_id,
                        # Fallback: prova prima ID normalizzato, poi ID originale, poi hash senza trattini
                        or_(
                            Photo.stratigraphic_unit == normalized_us_id,
                            Photo.stratigraphic_unit == us_id_str,
                            Photo.stratigraphic_unit == us_id_str.replace('-', '')
                        )
                    )
                )
                
                # DEBUG: Log the query details
                logger.info(f"[DEBUG] Photo query - site_id: {us.site_id}")
                logger.info(f"[DEBUG] Photo query - normalized_us_id: {normalized_us_id}")
                logger.info(f"[DEBUG] Photo query - us_id_str: {us_id_str}")
                logger.info(f"[DEBUG] Photo query - us_id_str_no_dashes: {us_id_str.replace('-', '')}")
                
                photos_result = await self.db.execute(photos_query)
                photos = photos_result.scalars().all()
                
                logger.info(f"[DEBUG] Found {len(photos)} photos for US {us_id_str}")
                
                # Converti le foto in formato compatibile e aggiungile alle fotografie
                existing_fotografie = files_by_type.get('fotografia', [])
                logger.info(f"[DEBUG] Existing fotografie count: {len(existing_fotografie)}")
                
                for photo in photos:
                    logger.info(f"[DEBUG] Processing photo: id={photo.id}, stratigraphic_unit={photo.stratigraphic_unit}")
                    photo_dict = self._photo_to_usfile_dict(photo)
                    existing_fotografie.append(photo_dict)
                
                files_by_type['fotografia'] = existing_fotografie
                logger.info(f"[DEBUG] Final fotografie count: {len(existing_fotografie)}")
            else:
                logger.warning(f"[DEBUG] US not found for ID: {us_id_str}")
                
                # FALLBACK: Cerca le foto direttamente usando l'ID US quando la query US fallisce
                logger.info(f"[FALLBACK] Attempting to find photos using US ID directly: {us_id_str}")
                
                # Normalizza l'ID US per la ricerca nel fallback
                normalized_us_id = self._normalize_us_id(us_id)
                logger.info(f"[FALLBACK] Normalized US ID: {normalized_us_id}")
                logger.info(f"[FALLBACK] Original US ID string: {us_id_str}")
                logger.info(f"[FALLBACK] US ID without dashes: {us_id_str.replace('-', '')}")
                
                # Cerca foto senza filtrare per site_id (fallback più ampio)
                # Prova tutti i formati possibili dell'ID US
                fallback_photos_query = select(Photo).where(
                    or_(
                        Photo.stratigraphic_unit == normalized_us_id,
                        Photo.stratigraphic_unit == us_id_str,
                        Photo.stratigraphic_unit == us_id_str.replace('-', '')
                    )
                )
                
                # DEBUG: Log the fallback query details
                logger.info(f"[FALLBACK] Photo query - normalized_us_id: {normalized_us_id}")
                logger.info(f"[FALLBACK] Photo query - us_id_str: {us_id_str}")
                logger.info(f"[FALLBACK] Photo query - us_id_str_no_dashes: {us_id_str.replace('-', '')}")
                
                fallback_photos_result = await self.db.execute(fallback_photos_query)
                fallback_photos = fallback_photos_result.scalars().all()
                
                logger.info(f"[FALLBACK] Found {len(fallback_photos)} photos for US {us_id_str} using fallback")
                
                # Converti le foto in formato compatibile e aggiungile alle fotografie
                existing_fotografie = files_by_type.get('fotografia', [])
                logger.info(f"[FALLBACK] Existing fotografie count: {len(existing_fotografie)}")
                
                for photo in fallback_photos:
                    logger.info(f"[FALLBACK] Processing photo: id={photo.id}, stratigraphic_unit={photo.stratigraphic_unit}, site_id={photo.site_id}")
                    photo_dict = self._photo_to_usfile_dict(photo)
                    existing_fotografie.append(photo_dict)
                
                files_by_type['fotografia'] = existing_fotografie
                logger.info(f"[FALLBACK] Final fotografie count after fallback: {len(existing_fotografie)}")
            
            # 4. Calcola i conteggi totali
            fotografie_list = files_by_type.get('fotografia', [])
            total_files = len(files) + len([f for f in fotografie_list if f.get('source') == 'photo_table'])
            
            result = {
                'piante': files_by_type.get('pianta', []),
                'sezioni': files_by_type.get('sezione', []),
                'prospetti': files_by_type.get('prospetto', []),
                'fotografie': fotografie_list,
                'documenti': files_by_type.get('documento', []),
                'counts': {
                    'piante': len(files_by_type.get('pianta', [])),
                    'sezioni': len(files_by_type.get('sezione', [])),
                    'prospetti': len(files_by_type.get('prospetto', [])),
                    'fotografie': len(fotografie_list),
                    'documenti': len(files_by_type.get('documento', [])),
                    'total': total_files
                }
            }
            
            logger.info(f"[DEBUG] Final result counts: {result['counts']}")
            return result
            
        except Exception as e:
            logger.error(f"Error in get_files_summary_for_us: {str(e)}")
            raise

    async def get_files_summary_for_usm(self, usm_id: UUID) -> Dict[str, Any]:
        """Riassunto file per USM con conteggi per tipo, includendo foto dalla tabella Photo"""
        
        try:
                # 1. Ottieni i file USM esistenti
                files = await self.get_usm_files(usm_id)
                
                # 2. Raggruppa per tipo i file USM esistenti
                files_by_type = {}
                
                # Collect all file IDs to batch query their types
                file_ids = [safe_uuid_str(file_obj.id) for file_obj in files]
                
                # Batch query for all file types at once to reduce context switches
                if file_ids:
                    file_types_query = select(
                        usm_files_association.c.file_id,
                        usm_files_association.c.file_type
                    ).where(
                        and_(
                            usm_files_association.c.usm_id == safe_uuid_str(usm_id),
                            usm_files_association.c.file_id.in_(file_ids)
                        )
                    )
                    file_types_result = await self.db.execute(file_types_query)
                    file_types = {row[0]: row[1] for row in file_types_result.all()}
                else:
                    file_types = {}
                
                # Group files by type using the batched results
                for file_obj in files:
                    file_type = file_types.get(safe_uuid_str(file_obj.id))
                    
                    if file_type not in files_by_type:
                        files_by_type[file_type] = []
                    files_by_type[file_type].append(file_obj.to_dict())
                
                # 3. Recupera le foto dalla tabella Photo dove usm_reference == usm_id
                # Prima ottieni l'USM per ottenere il codice USM
                usm_query = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == safe_uuid_str(usm_id))
                usm_result = await self.db.execute(usm_query)
                usm = usm_result.scalar_one_or_none()
                
                if usm:
                    # Cerca foto dove usm_reference corrisponde al codice USM
                    photos_query = select(Photo).where(
                        and_(
                            Photo.usm_reference == safe_uuid_str(usm_id),
                            Photo.site_id == safe_uuid_str(usm.site_id)
                        )
                    )
                    photos_result = await self.db.execute(photos_query)
                    photos = photos_result.scalars().all()
                    
                    # Converti le foto in formato compatibile e aggiungile alle fotografie
                    existing_fotografie = files_by_type.get('fotografia', [])
                    
                    for photo in photos:
                        photo_dict = self._photo_to_usfile_dict(photo)
                        existing_fotografie.append(photo_dict)
                    
                    files_by_type['fotografia'] = existing_fotografie
                
                # 4. Calcola i conteggi totali
                fotografie_list = files_by_type.get('fotografia', [])
                total_files = len(files) + len([f for f in fotografie_list if f.get('source') == 'photo_table'])
                
                result = {
                    'piante': files_by_type.get('pianta', []),
                    'sezioni': files_by_type.get('sezione', []),
                    'prospetti': files_by_type.get('prospetto', []),
                    'fotografie': fotografie_list,
                    'documenti': files_by_type.get('documento', []),
                    'counts': {
                        'piante': len(files_by_type.get('pianta', [])),
                        'sezioni': len(files_by_type.get('sezione', [])),
                        'prospetti': len(files_by_type.get('prospetto', [])),
                        'fotografie': len(fotografie_list),
                        'documenti': len(files_by_type.get('documento', [])),
                        'total': total_files
                    }
                }
                
                return result
                
        except Exception as e:
            logger.error(f"Error in get_files_summary_for_usm: {str(e)}")
            raise