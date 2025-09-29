# app/services/photo_service.py - GESTIONE METADATI FOTO CORRETTA

import json
import io
import os
import tempfile
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union
from pathlib import Path
from uuid import uuid4

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import piexif
from loguru import logger
from fastapi import UploadFile

# 🔧 CORREZIONE: Import del modello Photo corretto
from app.models.photos import Photo, PhotoType, MaterialType, ConservationStatus

# 🔧 CORREZIONE: Import condizionale di storage_service (se esiste)
try:
    from app.services.storage_service import storage_service

    HAS_STORAGE_SERVICE = True
except ImportError:
    HAS_STORAGE_SERVICE = False
    logger.warning("storage_service not available, using local file storage")

# 🔧 CORREZIONE: Import MinIO per thumbnail upload diretto
try:
    from app.services.archaeological_minio_service import archaeological_minio_service
    from app.services.deep_zoom_minio_service import deep_zoom_minio_service
    HAS_MINIO = True
except ImportError:
    HAS_MINIO = False
    logger.warning("minio not available")


class PhotoMetadataService:
    """Servizio per estrazione metadati da immagini"""

    def __init__(self):
        self.supported_formats = {'.jpg', '.jpeg', '.tiff', '.tif', '.png', '.bmp', '.webp'}

        # 🔧 FIX: Configure PIL/Pillow for large image handling
        self._configure_pil_limits()

    def _configure_pil_limits(self):
        """Configure PIL/Pillow limits for handling large images safely"""
        try:
            # Increase maximum image pixels to handle large images
            # Default is ~179M pixels, we increase to 400M pixels
            old_limit = getattr(Image, 'MAX_IMAGE_PIXELS', None)
            Image.MAX_IMAGE_PIXELS = 400000000  # 400M pixels

            # Also increase the decompression bomb check limit
            # This prevents false positives for legitimate large images
            if hasattr(Image, 'preinit'):
                Image.preinit()

            logger.info(f"PIL limits configured: MAX_IMAGE_PIXELS increased from {old_limit} to {Image.MAX_IMAGE_PIXELS}")

        except Exception as e:
            logger.warning(f"Could not configure PIL limits: {e}")

    async def extract_metadata(
            self,
            file_path: str,
            filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Estrae metadati tecnici e archeologici da immagine
        Returns: Tuple[exif_data, photo_metadata]
        """
        try:
            image_path = Path(file_path)

            # Metadati tecnici di base
            technical_metadata = await self._extract_technical_metadata(image_path, filename)

            # Metadati EXIF
            exif_data = await self._extract_exif_data(image_path)

            # Combina metadati
            photo_metadata = {
                **technical_metadata,
                **exif_data
            }

            logger.info(f"Metadata extracted for {filename}")
            return exif_data, photo_metadata

        except Exception as e:
            logger.error(f"Error extracting metadata from {filename}: {e}")
            return {}, {}

    async def extract_metadata_from_file(
            self,
            file: UploadFile,
            filename: str
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Estrae metadati direttamente da file UploadFile
        Returns: Tuple[exif_data, photo_metadata]
        """
        try:
            # Salva temporaneamente il file per l'analisi
            # 🔧 CORREZIONE: Creazione file temporaneo corretto
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp_file:
                content = await file.read()
                tmp_file.write(content)
                tmp_file_path = tmp_file.name

            try:
                # Estrai metadati dal file temporaneo
                exif_data, metadata = await self.extract_metadata(tmp_file_path, filename)
                return exif_data, metadata
            finally:
                # Pulisce file temporaneo
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)

        except Exception as e:
            logger.error(f"Error extracting metadata from file {filename}: {e}")
            return {}, {}

    async def _extract_technical_metadata(
            self,
            image_path: Path,
            filename: str
    ) -> Dict[str, Any]:
        """Estrae metadati tecnici di base"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size

                # Determina DPI
                dpi = None
                if hasattr(img, 'info') and 'dpi' in img.info:
                    dpi = img.info['dpi'][0] if isinstance(img.info['dpi'], tuple) else img.info['dpi']

                # Profilo colore
                color_profile = None
                if img.mode in ['RGB', 'CMYK', 'LAB']:
                    color_profile = img.mode

                return {
                    "width": width,
                    "height": height,
                    "dpi": dpi,
                    "color_profile": color_profile,
                    "image_format": img.format,
                    "image_mode": img.mode
                }

        except Exception as e:
            logger.warning(f"Could not extract technical metadata: {e}")
            return {}

    async def _extract_exif_data(self, image_path: Path) -> Dict[str, Any]:
        """Estrae metadati EXIF"""
        try:
            # 🔧 CORREZIONE: Metodo EXIF più robusto
            with Image.open(image_path) as img:
                exif_dict = {}
                extracted_data = {}

                # Prova con getexif() (più moderno)
                try:
                    exif_data = img.getexif()
                    if exif_data:
                        for tag_id, value in exif_data.items():
                            tag = TAGS.get(tag_id, tag_id)

                            # Gestione tipi diversi
                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-8')
                                except UnicodeDecodeError:
                                    value = str(value)

                            exif_dict[tag] = value
                except Exception:
                    # Fallback al metodo legacy
                    if hasattr(img, '_getexif') and img._getexif() is not None:
                        exif_info = img._getexif()
                        for tag_id, value in exif_info.items():
                            tag = TAGS.get(tag_id, tag_id)

                            if isinstance(value, bytes):
                                try:
                                    value = value.decode('utf-8')
                                except UnicodeDecodeError:
                                    value = str(value)

                            exif_dict[tag] = value

                # Estrai informazioni specifiche
                # Data e ora scatto
                for date_field in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
                    if date_field in exif_dict:
                        try:
                            photo_date = datetime.strptime(exif_dict[date_field], '%Y:%m:%d %H:%M:%S')
                            extracted_data['photo_date'] = photo_date
                            break
                        except (ValueError, TypeError):
                            continue

                # Modello fotocamera
                if 'Model' in exif_dict:
                    extracted_data['camera_model'] = str(exif_dict['Model']).strip()

                # Marca fotocamera
                if 'Make' in exif_dict:
                    extracted_data['camera_make'] = str(exif_dict['Make']).strip()

                # Obiettivo
                if 'LensModel' in exif_dict:
                    extracted_data['lens'] = str(exif_dict['LensModel']).strip()

                # Software
                if 'Software' in exif_dict:
                    extracted_data['software'] = str(exif_dict['Software']).strip()

                # Orientamento
                if 'Orientation' in exif_dict:
                    extracted_data['orientation'] = exif_dict['Orientation']

                # GPS
                gps_data = await self._extract_gps_data(exif_dict)
                if gps_data:
                    extracted_data['gps_data'] = gps_data

                # Crea EXIF JSON serializzabile
                serializable_exif = {}
                for key, value in exif_dict.items():
                    try:
                        json.dumps(value)  # Test serializzazione
                        serializable_exif[key] = value
                    except (TypeError, ValueError):
                        serializable_exif[key] = str(value)

                extracted_data['exif_data'] = serializable_exif

                return extracted_data

        except Exception as e:
            logger.warning(f"Could not extract EXIF data: {e}")
            return {}

    async def _extract_gps_data(self, exif_dict: Dict) -> Optional[Dict[str, Any]]:
        """Estrae dati GPS da EXIF"""
        try:
            gps_info = {}

            # Cerca GPS info in diversi modi
            if 'GPSInfo' in exif_dict:
                gps_raw = exif_dict['GPSInfo']
                if isinstance(gps_raw, dict):
                    for tag_id, value in gps_raw.items():
                        gps_tag = GPSTAGS.get(tag_id, tag_id)
                        gps_info[gps_tag] = value

            # Cerca tag GPS individuali
            for tag_id, value in exif_dict.items():
                tag = TAGS.get(tag_id, tag_id)
                if isinstance(tag, str) and tag.startswith('GPS'):
                    gps_tag = GPSTAGS.get(tag_id, tag_id)
                    gps_info[gps_tag] = value

            if gps_info:
                return gps_info
            return None

        except Exception as e:
            logger.warning(f"Could not extract GPS data: {e}")
            return None

    async def create_photo_record(
            self,
            filename: str,
            original_filename: str,
            file_path: str,
            file_size: int,
            site_id: Union[str, 'UUID'],  # 🔧 CORREZIONE: Supporto UUID
            uploaded_by: Union[str, 'UUID'],  # 🔧 CORREZIONE: Supporto UUID
            metadata: Dict[str, Any] = None,
            archaeological_metadata: Dict[str, Any] = None  # 🔧 AGGIUNTA: Metadati archeologici separati
    ) -> Photo:
        """
        Crea record Photo con metadati estratti

        Args:
            filename: Nome file univoco
            original_filename: Nome file originale
            file_path: Path relativo file
            file_size: Dimensione in bytes
            site_id: ID sito archeologico
            uploaded_by: ID utente che ha caricato
            metadata: Metadati estratti dall'immagine
            archaeological_metadata: Metadati archeologici dal form
        """
        if metadata is None:
            metadata = {}
        if archaeological_metadata is None:
            archaeological_metadata = {}

        # 🔧 CORREZIONE: Conversione UUID se necessario
        from uuid import UUID
        if isinstance(site_id, str):
            try:
                site_id = UUID(site_id)
            except ValueError:
                pass
        if isinstance(uploaded_by, str):
            try:
                uploaded_by = UUID(uploaded_by)
            except ValueError:
                pass

        # Crea record foto
        photo_data = {
            "filename": filename,
            "original_filename": original_filename,
            "file_path": file_path,
            "file_size": file_size,
            "mime_type": self._guess_mime_type(filename),
            "site_id": site_id,
            "uploaded_by": uploaded_by,

            # Metadati tecnici
            "width": metadata.get('width'),
            "height": metadata.get('height'),
            "dpi": metadata.get('dpi'),
            "color_profile": metadata.get('color_profile'),

            # Metadati EXIF
            "photo_date": metadata.get('photo_date'),
            "camera_model": metadata.get('camera_model'),
            "lens": metadata.get('lens'),
            "photographer": archaeological_metadata.get('photographer') or metadata.get('photographer'),

            # 🔧 AGGIUNTA: Metadati archeologici
            "inventory_number": archaeological_metadata.get('inventory_number'),
            "excavation_area": archaeological_metadata.get('excavation_area'),
            "stratigraphic_unit": archaeological_metadata.get('stratigraphic_unit'),
            "find_date": archaeological_metadata.get('find_date'),
            "material": archaeological_metadata.get('material'),
            "object_type": archaeological_metadata.get('object_type'),
            "chronology_period": archaeological_metadata.get('chronology_period'),
            "conservation_status": archaeological_metadata.get('conservation_status'),
            "photo_type": archaeological_metadata.get('photo_type'),
            "description": archaeological_metadata.get('description'),
            "keywords": archaeological_metadata.get('keywords'),

            # EXIF completo
            "exif_data": json.dumps(metadata.get('exif_data', {})) if metadata.get('exif_data') else None,

            # Stato iniziale
            "is_published": False,
            "is_validated": False
        }

        # Rimuovi campi None per evitare errori
        photo_data = {k: v for k, v in photo_data.items() if v is not None}

        photo = Photo(**photo_data)
        return photo

    def _guess_mime_type(self, filename: str) -> str:
        """Determina MIME type da estensione file"""
        extension = Path(filename).suffix.lower()
        mime_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.tiff': 'image/tiff',
            '.tif': 'image/tiff',
            '.bmp': 'image/bmp',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.raw': 'image/x-raw',
            '.cr2': 'image/x-canon-cr2',
            '.nef': 'image/x-nikon-nef',
            '.arw': 'image/x-sony-arw',
            '.dng': 'image/x-adobe-dng'
        }

        return mime_types.get(extension, 'application/octet-stream')

    async def generate_thumbnail(
            self,
            original_path: str,
            photo_id: str,
            max_size: int = 800
    ) -> Optional[str]:
        """
        Genera thumbnail per l'immagine

        Args:
            original_path: Path file originale
            photo_id: ID foto per nome thumbnail
            max_size: Dimensione massima thumbnail (default 800px)

        Returns:
            Path thumbnail generato o None se errore
        """
        try:
            with Image.open(original_path) as img:
                # 🔧 CORREZIONE: Correggi orientamento se presente
                try:
                    from PIL.ExifTags import ORIENTATION

                    exif = img.getexif()
                    if exif and ORIENTATION in exif:
                        orientation = exif[ORIENTATION]
                        if orientation == 3:
                            img = img.rotate(180, expand=True)
                        elif orientation == 6:
                            img = img.rotate(270, expand=True)
                        elif orientation == 8:
                            img = img.rotate(90, expand=True)
                except Exception:
                    pass  # Ignora errori orientamento

                # Converti in RGB se necessario
                if img.mode in ("RGBA", "P", "LA"):
                    img = img.convert("RGB")

                # Calcola dimensioni mantenendo aspect ratio
                width, height = img.size
                if width > height:
                    new_width = max_size
                    new_height = int((height * max_size) / width)
                else:
                    new_height = max_size
                    new_width = int((width * max_size) / height)

                # Crea thumbnail
                thumbnail = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # 🔧 CORREZIONE: Gestione storage con fallback
                try:
                    # Salva thumbnail in memoria
                    thumbnail_buffer = io.BytesIO()
                    thumbnail.save(thumbnail_buffer, 'JPEG', quality=85, optimize=True)
                    thumbnail_buffer.seek(0)

                    # Crea file UploadFile
                    thumbnail_file = UploadFile(
                        filename=f"{photo_id}.jpg",
                        file=thumbnail_buffer
                    )

                    # Use archaeological MinIO service for thumbnails
                    if HAS_MINIO:
                        # Usa il nuovo servizio archeologico per thumbnail
                        thumbnail_buffer.seek(0)
                        thumbnail_data = thumbnail_buffer.read()

                        try:
                            # Upload con servizio archeologico
                            thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                                thumbnail_data, photo_id
                            )

                            logger.info(f"Thumbnail uploaded with archaeological service: {photo_id}")
                            return thumbnail_url
                            
                        except Exception as upload_error:
                            error_msg = str(upload_error)
                            
                            # Check if it's a storage full error
                            if "XMinioStorageFull" in error_msg or "minimum free drive threshold" in error_msg:
                                logger.error(f"MinIO storage full - triggering emergency cleanup for thumbnail: {photo_id}")
                                
                                # Try emergency cleanup
                                try:
                                    from app.services.storage_management_service import storage_management_service
                                    cleanup_result = await storage_management_service.emergency_cleanup(target_freed_mb=100)
                                    
                                    if cleanup_result['success'] and cleanup_result['total_freed_mb'] > 50:
                                        logger.info(f"Emergency cleanup freed {cleanup_result['total_freed_mb']}MB, retrying thumbnail upload")
                                        
                                        # Retry upload after cleanup
                                        thumbnail_buffer.seek(0)
                                        thumbnail_data = thumbnail_buffer.read()
                                        thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                                            thumbnail_data, photo_id
                                        )
                                        logger.info(f"Thumbnail uploaded after emergency cleanup: {photo_id}")
                                        return thumbnail_url
                                    else:
                                        logger.warning(f"Emergency cleanup insufficient, falling back to local storage for thumbnail: {photo_id}")
                                        raise Exception("Storage full after cleanup attempt")
                                        
                                except Exception as cleanup_error:
                                    logger.error(f"Emergency cleanup failed: {cleanup_error}")
                                    raise Exception("Storage full and cleanup failed")
                            else:
                                # Other MinIO error, fallback to local
                                raise upload_error
                    else:
                        raise Exception("MinIO not available")

                except Exception as e:
                    logger.warning(f"MinIO upload failed for thumbnail: {e}, using local storage")
                    # Fallback a storage locale
                    thumbnail_dir = Path("storage/thumbnails")
                    thumbnail_dir.mkdir(parents=True, exist_ok=True)

                    thumbnail_path = thumbnail_dir / f"{photo_id}.jpg"
                    thumbnail.save(thumbnail_path, 'JPEG', quality=85, optimize=True)

                    logger.info(f"Thumbnail saved locally: {thumbnail_path}")
                    return str(thumbnail_path)

        except Exception as e:
            logger.error(f"Error generating thumbnail for {photo_id}: {e}")
            return None

    async def generate_thumbnail_from_file(
            self,
            file: UploadFile,
            photo_id: str,
            max_size: int = 800
    ) -> Optional[str]:
        """
        Genera thumbnail direttamente da file UploadFile

        Args:
            file: File UploadFile originale
            photo_id: ID foto per nome thumbnail
            max_size: Dimensione massima thumbnail (default 800px)

        Returns:
            Path/object name thumbnail o None se errore
        """
        try:
            # 🔧 CORREZIONE: Gestione file temporaneo migliorata
            with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename or "temp.jpg").suffix) as tmp_file:
                # Legge contenuto file una volta sola
                content = await file.read()
                if len(content) == 0:
                    logger.warning(f"Empty file content for thumbnail generation: {photo_id}")
                    return None

                tmp_file.write(content)
                tmp_file_path = tmp_file.name

            try:
                # Genera thumbnail dal file temporaneo
                thumbnail_path = await self.generate_thumbnail(tmp_file_path, photo_id, max_size)
                return thumbnail_path
            finally:
                # Pulisce file temporaneo
                if os.path.exists(tmp_file_path):
                    os.unlink(tmp_file_path)

        except Exception as e:
            logger.error(f"Error generating thumbnail from file for {photo_id}: {e}")
            return None

    # 🔧 AGGIUNTA: Metodi di utilità
    async def validate_image_file(self, file: UploadFile) -> Tuple[bool, str]:
        """Valida se il file è un'immagine supportata"""
        try:
            if not file.filename:
                return False, "Nome file mancante"

            extension = Path(file.filename).suffix.lower()
            if extension not in self.supported_formats:
                return False, f"Formato {extension} non supportato"

            # Verifica che sia effettivamente un'immagine
            content = await file.read()
            await file.seek(0)  # Reset file pointer

            try:
                with tempfile.NamedTemporaryFile() as tmp_file:
                    tmp_file.write(content)
                    tmp_file.flush()

                    with Image.open(tmp_file.name) as img:
                        # Se arriviamo qui, è un'immagine valida
                        width, height = img.size
                        if width < 1 or height < 1:
                            return False, "Dimensioni immagine non valide"

                        return True, "OK"

            except Exception as e:
                return False, f"File corrotto o non valido: {str(e)}"

        except Exception as e:
            return False, f"Errore validazione: {str(e)}"


    async def process_photo_with_deep_zoom(
        self,
        file: UploadFile,
        photo_id: str,
        site_id: str,
        archaeological_metadata: Dict[str, Any] = None,
        generate_deep_zoom: bool = True
    ) -> Dict[str, Any]:
        """
        Processa foto con deep zoom se richiesto

        Args:
            file: File UploadFile originale
            photo_id: ID della foto
            site_id: ID del sito archeologico
            archaeological_metadata: Metadati archeologici
            generate_deep_zoom: Se generare deep zoom

        Returns:
            Dict con informazioni processamento
        """
        try:
            # Determina se generare deep zoom (immagini grandi)
            should_generate_deep_zoom = generate_deep_zoom

            if should_generate_deep_zoom:
                # Controlla dimensione immagine
                content = await file.read()
                await file.seek(0)  # Reset file pointer

                # Carica immagine in memoria per controllare dimensione
                try:
                    with Image.open(io.BytesIO(content)) as img:
                        width, height = img.size
                        max_dimension = max(width, height)

                        # Genera deep zoom solo per immagini > 2000px
                        should_generate_deep_zoom = max_dimension > 2000
                except Exception as e:
                    logger.warning(f"Could not determine image dimensions: {e}")
                    should_generate_deep_zoom = False

                if should_generate_deep_zoom:
                    logger.info(f"Generating deep zoom for large image: {width}x{height}")

                    try:
                        # Processa con deep zoom
                        result = await archaeological_minio_service.process_photo_with_deep_zoom(
                            photo_data=content,
                            photo_id=photo_id,
                            site_id=site_id,
                            archaeological_metadata=archaeological_metadata,
                            generate_deep_zoom=True
                        )

                        logger.info(f"Deep zoom processing completed successfully for {photo_id}")
                        return {
                            'photo_url': result['photo_url'],
                            'deep_zoom_available': result['deep_zoom_available'],
                            'tile_count': result.get('tile_count', 0),
                            'levels': result.get('levels', 0),
                            'metadata_url': result.get('metadata_url')
                        }
                    except Exception as e:
                        logger.error(f"Deep zoom processing failed for {photo_id}: {e}")
                        # Non bloccare l'upload se deep zoom fallisce
                        return {
                            'photo_url': None,
                            'deep_zoom_available': False,
                            'tile_count': 0,
                            'levels': 0,
                            'metadata_url': None,
                            'deep_zoom_error': str(e)
                        }

            # Upload normale senza deep zoom
            return {
                'photo_url': None,  # Verrà impostato dall'upload normale
                'deep_zoom_available': False,
                'tile_count': 0,
                'levels': 0,
                'metadata_url': None
            }

        except Exception as e:
            logger.error(f"Deep zoom processing failed: {e}")
            # Non bloccare l'upload se deep zoom fallisce
            return {
                'photo_url': None,
                'deep_zoom_available': False,
                'tile_count': 0,
                'levels': 0,
                'metadata_url': None,
                'deep_zoom_error': str(e)
            }


# Istanza globale
photo_metadata_service = PhotoMetadataService()
