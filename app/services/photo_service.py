# app/services/photo_service.py - GESTIONE METADATI FOTO CORRETTA - REFACTORED

import json
import io
import os
import tempfile
import functools
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, Union, Callable
from pathlib import Path
from uuid import uuid4

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import piexif
from loguru import logger
from fastapi import UploadFile, HTTPException

# ORIENTATION constant - handle different PIL versions
try:
    from PIL.ExifTags import ORIENTATION
except ImportError:
    # Fallback for older PIL versions
    ORIENTATION = 274

# 🔧 CORREZIONE: Import del modello Photo corretto
from app.models import Photo, PhotoType, MaterialType, ConservationStatus

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
    from app.services.deep_zoom_minio_service import get_deep_zoom_minio_service
    from app.core.exceptions import StorageFullError, StorageError
    HAS_MINIO = True
except ImportError:
    HAS_MINIO = False
    logger.warning("minio not available")


class PhotoServiceError(Exception):
    """Eccezione base per errori del servizio foto"""
    pass


class ImageProcessingError(PhotoServiceError):
    """Errore durante l'elaborazione dell'immagine"""
    pass


class StorageError(PhotoServiceError):
    """Errore durante le operazioni di storage"""
    pass


def handle_photo_service_errors(operation_name: str) -> Callable:
    """
    Decorator per gestire errori centralizzati nei metodi del servizio foto

    Args:
        operation_name: Nome dell'operazione per logging
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except ImageProcessingError:
                raise  # Rilancia errori di processamento immagine
            except StorageError:
                raise  # Rilancia errori di storage
            except Exception as e:
                logger.error(f"Errore in {operation_name}: {e}")
                raise PhotoServiceError(f"Errore durante {operation_name}: {e}")
        return wrapper
    return decorator


class ImageUtils:
    """Utility class per operazioni comuni di processamento immagini"""

    @staticmethod
    def calculate_thumbnail_dimensions(original_size: Tuple[int, int], max_size: int) -> Tuple[int, int]:
        """Calcola dimensioni thumbnail mantenendo aspect ratio"""
        width, height = original_size

        if width > height:
            new_width = max_size
            new_height = int((height * max_size) / width)
        else:
            new_height = max_size
            new_width = int((width * max_size) / height)

        return new_width, new_height

    @staticmethod
    def correct_image_orientation(image: Image.Image) -> Image.Image:
        """Corregge orientamento immagine basato su EXIF"""
        try:
            exif = image.getexif()
            if exif and ORIENTATION in exif:
                orientation = exif[ORIENTATION]

                if orientation == 3:
                    return image.rotate(180, expand=True)
                elif orientation == 6:
                    return image.rotate(270, expand=True)
                elif orientation == 8:
                    return image.rotate(90, expand=True)
        except Exception as e:
            logger.warning(f"Errore correzione orientamento: {e}")

        return image

    @staticmethod
    def prepare_image_for_thumbnail(image: Image.Image) -> Image.Image:
        """Prepara immagine per generazione thumbnail"""
        # Correggi orientamento
        image = ImageUtils.correct_image_orientation(image)

        # Converti in RGB se necessario
        if image.mode in ("RGBA", "P", "LA"):
            image = image.convert("RGB")

        return image

    @staticmethod
    def create_thumbnail(image: Image.Image, max_size: int) -> Image.Image:
        """Crea thumbnail da immagine"""
        original_size = image.size
        new_size = ImageUtils.calculate_thumbnail_dimensions(original_size, max_size)
        return image.resize(new_size, Image.Resampling.LANCZOS)


class FileUtils:
    """Utility class per operazioni comuni sui file"""

    @staticmethod
    async def create_temp_file_from_upload(file: UploadFile) -> str:
        """Crea file temporaneo da UploadFile"""
        if not file.filename:
            raise ImageProcessingError("Nome file mancante")

        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp_file:
            content = await file.read()
            if len(content) == 0:
                raise ImageProcessingError("Contenuto file vuoto")

            tmp_file.write(content)
            return tmp_file.name

    @staticmethod
    def cleanup_temp_file(file_path: str):
        """Pulisce file temporaneo"""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            logger.warning(f"Errore pulizia file temporaneo {file_path}: {e}")


class PhotoService:
    """Servizio per gestione foto con storage centralizzato"""

    def __init__(self, archaeological_minio_service):
        self.storage = archaeological_minio_service


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

            logger.debug(f"PIL limits configured: MAX_IMAGE_PIXELS increased from {old_limit} to {Image.MAX_IMAGE_PIXELS}")

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

        except ImageProcessingError as e:
            logger.error(f"Errore processamento metadati per {filename}: {e}")
            return {}, {}
        except Exception as e:
            logger.error(f"Errore estrazione metadati da {filename}: {e}")
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
        temp_file_path = None
        try:
            # Crea file temporaneo
            temp_file_path = await FileUtils.create_temp_file_from_upload(file)

            # Estrai metadati dal file temporaneo
            exif_data, metadata = await self.extract_metadata(temp_file_path, filename)
            return exif_data, metadata

        except ImageProcessingError as e:
            logger.error(f"Errore processamento metadati da file {filename}: {e}")
            return {}, {}
        except Exception as e:
            logger.error(f"Errore estrazione metadati da file {filename}: {e}")
            return {}, {}
        finally:
            # Pulisce file temporaneo
            if temp_file_path:
                FileUtils.cleanup_temp_file(temp_file_path)

    async def _extract_technical_metadata(
            self,
            image_path: Path,
            filename: str
    ) -> Dict[str, Any]:
        """Estrae metadati tecnici di base"""
        try:
            with Image.open(image_path) as img:
                width, height = img.size

                return {
                    "width": width,
                    "height": height,
                    "dpi": self._extract_dpi(img),
                    "color_profile": self._extract_color_profile(img),
                    "image_format": img.format,
                    "image_mode": img.mode
                }

        except Exception as e:
            logger.warning(f"Could not extract technical metadata for {filename}: {e}")
            return {}

    def _extract_dpi(self, image: Image.Image) -> Optional[float]:
        """Estrae DPI dall'immagine"""
        try:
            if hasattr(image, 'info') and 'dpi' in image.info:
                return image.info['dpi'][0] if isinstance(image.info['dpi'], tuple) else image.info['dpi']
        except Exception as e:
            logger.warning(f"Errore estrazione DPI: {e}")
        return None

    def _extract_color_profile(self, image: Image.Image) -> Optional[str]:
        """Estrae profilo colore dall'immagine"""
        try:
            if image.mode in ['RGB', 'CMYK', 'LAB']:
                return image.mode
        except Exception as e:
            logger.warning(f"Errore estrazione profilo colore: {e}")
        return None

    async def _extract_exif_data(self, image_path: Path) -> Dict[str, Any]:
        """Estrae metadati EXIF"""
        try:
            with Image.open(image_path) as img:
                exif_dict = await self._extract_exif_dictionary(img)
                extracted_data = await self._extract_specific_exif_data(exif_dict)

                # Crea EXIF JSON serializzabile
                extracted_data['exif_data'] = self._make_exif_serializable(exif_dict)

                return extracted_data

        except Exception as e:
            logger.warning(f"Could not extract EXIF data: {e}")
            return {}

    async def _extract_exif_dictionary(self, image: Image.Image) -> Dict[str, Any]:
        """Estrae dizionario EXIF dall'immagine"""
        exif_dict = {}

        # Prova con getexif() (più moderno)
        try:
            exif_data = image.getexif()
            if exif_data:
                exif_dict = await self._process_exif_tags(exif_data)
        except Exception:
            # Fallback al metodo legacy
            if hasattr(image, '_getexif') and image._getexif() is not None:
                exif_info = image._getexif()
                exif_dict = await self._process_exif_tags(exif_info)

        return exif_dict

    async def _process_exif_tags(self, exif_data) -> Dict[str, Any]:
        """Processa tag EXIF e gestisce tipi diversi"""
        processed_dict = {}

        for tag_id, value in exif_data.items():
            tag = TAGS.get(tag_id, tag_id)

            # Gestione tipi diversi
            if isinstance(value, bytes):
                try:
                    value = value.decode('utf-8')
                except UnicodeDecodeError:
                    value = str(value)

            processed_dict[tag] = value

        return processed_dict

    async def _extract_specific_exif_data(self, exif_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Estrae informazioni specifiche da dizionario EXIF"""
        extracted_data = {}

        # Data e ora scatto
        extracted_data['photo_date'] = self._extract_photo_date(exif_dict)

        # Informazioni fotocamera
        if 'Model' in exif_dict:
            extracted_data['camera_model'] = str(exif_dict['Model']).strip()

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

        return extracted_data

    def _extract_photo_date(self, exif_dict: Dict[str, Any]) -> Optional[datetime]:
        """Estrae data foto da dizionario EXIF"""
        for date_field in ['DateTime', 'DateTimeOriginal', 'DateTimeDigitized']:
            if date_field in exif_dict:
                try:
                    return datetime.strptime(exif_dict[date_field], '%Y:%m:%d %H:%M:%S')
                except (ValueError, TypeError):
                    continue
        return None

    def _make_exif_serializable(self, exif_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Rende EXIF serializzabile in JSON"""
        serializable_exif = {}

        for key, value in exif_dict.items():
            try:
                # Gestione speciale per IFDRational di PIL
                if hasattr(value, '__class__') and 'IFDRational' in value.__class__.__name__:
                    # Converti IFDRational in float o stringa
                    try:
                        serializable_exif[key] = float(value)
                    except (ValueError, TypeError):
                        serializable_exif[key] = str(value)
                else:
                    # Test serializzazione normale
                    json.dumps(value)
                    serializable_exif[key] = value
            except (TypeError, ValueError):
                # Fallback a stringa per qualsiasi altro tipo non serializzabile
                serializable_exif[key] = str(value)

        return serializable_exif

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

        # 🔧 CORREZIONE: Keep UUIDs as strings for SQLite compatibility
        # The Photo model uses String(36) for UUID fields, so we must pass strings
        # not UUID objects to avoid "type 'UUID' is not supported" error
        from uuid import UUID
        if isinstance(site_id, (UUID, object)):
            site_id = str(site_id)
        if isinstance(uploaded_by, (UUID, object)):
            uploaded_by = str(uploaded_by)

        # Crea record foto
        photo_data = {
            "filename": filename,
            "original_filename": original_filename,
            "filepath": file_path,  # Fixed: use 'filepath' instead of 'file_path'
            "file_size": file_size,
            "mime_type": self._guess_mime_type(filename),
            "site_id": site_id,
            "uploaded_by": uploaded_by,
            "created_by": uploaded_by,

            # Metadati tecnici
            "width": metadata.get('width'),
            "height": metadata.get('height'),
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
            "material": self._convert_to_enum(MaterialType, archaeological_metadata.get('material')),
            "object_type": archaeological_metadata.get('object_type'),
            "chronology_period": archaeological_metadata.get('chronology_period'),
            "conservation_status": self._convert_to_enum(ConservationStatus, archaeological_metadata.get('conservation_status')),
            "photo_type": self._convert_to_enum(PhotoType, archaeological_metadata.get('photo_type')),
            "description": archaeological_metadata.get('description'),
            "keywords": self._convert_keywords_to_string(archaeological_metadata.get('keywords')),

            # 🔧 FIX: Exif completo removed - exif_data field doesn't exist in Photo model
            # The exif_data is stored internally but not passed to the Photo model

            # Stato iniziale
            "is_published": False,
            "is_validated": False
        }

        # 🔧 FIX: Remove problematic fields that don't exist in Photo model
        # This prevents "invalid keyword argument" errors
        problematic_fields = ['dpi', 'exif_data', 'color_profile']  # Fields that might be in metadata but not in Photo model
        for field in problematic_fields:
            if field in metadata:
                logger.debug(f"Excluding '{field}' field from Photo model (not supported)")
                # Remove from metadata to prevent passing to Photo constructor
                del metadata[field]

        # 🔧 FIX: Also check for any other fields that might cause issues
        # Get valid Photo model fields by checking the model's __table__.columns
        valid_photo_fields = {col.name for col in Photo.__table__.columns}
        
        # Filter photo_data to only include valid fields
        filtered_photo_data = {}
        for key, value in photo_data.items():
            if key in valid_photo_fields:
                filtered_photo_data[key] = value
            else:
                logger.debug(f"Excluding '{key}' field from Photo model (not in model)")

        # Rimuovi campi None per evitare errori
        filtered_photo_data = {k: v for k, v in filtered_photo_data.items() if v is not None}

        try:
            photo = Photo(**filtered_photo_data)
            logger.debug(f"Photo record created successfully with {len(filtered_photo_data)} fields")
            return photo
        except Exception as e:
            logger.error(f"Error creating Photo record: {e}")
            logger.error(f"Photo data fields: {list(filtered_photo_data.keys())}")
            # Try with minimal fields as fallback
            try:
                minimal_data = {
                    "filename": filename,
                    "original_filename": original_filename,
                    "filepath": file_path,
                    "file_size": file_size,
                    "site_id": site_id,
                    "uploaded_by": uploaded_by,
                    "created_by": uploaded_by,
                    "mime_type": self._guess_mime_type(filename),
                }
                photo = Photo(**minimal_data)
                logger.warning(f"Photo record created with minimal fields due to error")
                return photo
            except Exception as fallback_error:
                logger.error(f"Even minimal Photo creation failed: {fallback_error}")
                raise PhotoServiceError(f"Failed to create Photo record: {fallback_error}")

    def _convert_to_enum(self, enum_class, value):
        """
        Converte stringa in enum se possibile usando il sistema di conversione centralizzato
        
        Args:
            enum_class: La classe enum a cui convertire
            value: Il valore da convertire (italiano o inglese)
            
        Returns:
            Istanza dell'enum o None se la conversione fallisce
        """
        if value is None:
            return None
            
        if isinstance(value, enum_class):
            return value
            
        # Import the centralized enum converter
        try:
            from app.utils.enum_mappings import enum_converter, log_conversion_attempt
            
            # Use the centralized converter
            converted_value = enum_converter.convert_to_enum(enum_class, value)
            
            # Log the conversion attempt
            success = converted_value is not None
            log_conversion_attempt(enum_class, str(value), converted_value, success)
            
            return converted_value
            
        except ImportError:
            # Fallback to basic conversion if enum_mappings is not available
            logger.warning("enum_mappings not available, using basic conversion")
            try:
                return enum_class(value)
            except ValueError:
                logger.warning(f"Invalid value for {enum_class.__name__}: {value}")
                return None
        except Exception as e:
            logger.error(f"Error converting value '{value}' to {enum_class.__name__}: {e}")
            return None

    def _convert_keywords_to_string(self, keywords) -> Optional[str]:
        """
        Converte keywords da list a string per il database SQLite
        
        Args:
            keywords: Keywords che possono essere lista, string, o None
            
        Returns:
            Stringa con keywords separati da virgola o None
        """
        if keywords is None:
            return None
        
        if isinstance(keywords, str):
            # Return None for empty or whitespace-only strings
            return keywords.strip() if keywords.strip() else None
        
        if isinstance(keywords, list):
            # Filtra valori None o vuoti e converte a stringhe
            valid_keywords = [str(k).strip() for k in keywords if k and str(k).strip()]
            if not valid_keywords:
                return None
            return ", ".join(valid_keywords)
        
        # Se è un altro tipo, converti a stringa
        try:
            keyword_str = str(keywords)
            return keyword_str if keyword_str.strip() else None
        except Exception:
            return None

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
            # Carica e prepara immagine
            thumbnail = await self._prepare_thumbnail_image(original_path, max_size)

            # Salva thumbnail con gestione storage
            return await self._save_thumbnail(thumbnail, photo_id)

        except Exception as e:
            logger.error(f"Error generating thumbnail for {photo_id}: {e}")
            return None

    async def _prepare_thumbnail_image(self, original_path: str, max_size: int) -> Image.Image:
        """Prepara immagine per generazione thumbnail"""
        try:
            with Image.open(original_path) as img:
                # Prepara immagine (orientamento e conversione)
                prepared_image = ImageUtils.prepare_image_for_thumbnail(img)

                # Crea thumbnail
                return ImageUtils.create_thumbnail(prepared_image, max_size)

        except Exception as e:
            raise ImageProcessingError(f"Errore preparazione thumbnail: {e}")

    async def _save_thumbnail(self, thumbnail: Image.Image, photo_id: str) -> str:
        """
        Salva thumbnail su MinIO storage
        
        Args:
            thumbnail: Immagine thumbnail PIL
            photo_id: ID foto
            
        Returns:
            URL del thumbnail salvato
        """
        try:
            # Converti thumbnail in bytes
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, 'JPEG', quality=85, optimize=True)
            thumbnail_bytes = thumbnail_buffer.getvalue()
            
            # Usa il servizio archeologico per upload thumbnail
            if HAS_MINIO:
                thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                    thumbnail_bytes, photo_id
                )
                logger.info(f"Thumbnail uploaded successfully: {photo_id}")
                return thumbnail_url
            else:
                # Fallback se MinIO non disponibile
                logger.warning("MinIO not available, thumbnail upload skipped")
                return f"temp_thumbnail_{photo_id}.jpg"
                
        except Exception as e:
            logger.error(f"Error saving thumbnail for {photo_id}: {e}")
            raise ImageProcessingError(f"Errore salvataggio thumbnail: {e}")

    async def create_and_upload_thumbnail(
        self,
        photo_id: str,
        image_data: bytes,
        site_id: Optional[str] = None
    ) -> str:
        """Crea thumbnail e uploada su MinIO"""
        try:
            # Genera thumbnail
            thumbnail_bytes = await self._generate_thumbnail(image_data)

            # Upload via servizio archeologico (gestisce tutto lui)
            if HAS_MINIO:
                thumbnail_url = await archaeological_minio_service.upload_thumbnail(
                    thumbnail_bytes=thumbnail_bytes,
                    photo_id=photo_id,
                    site_id=site_id
                )
            else:
                logger.warning("MinIO not available, thumbnail upload skipped")
                return f"temp_thumbnail_{photo_id}.jpg"

            logger.info(f"Thumbnail uploaded: {photo_id}")
            return thumbnail_url

        except StorageFullError as e:
            # Storage full anche dopo cleanup automatico
            logger.error(f"Cannot upload thumbnail, storage full: {e}")
            raise HTTPException(
                status_code=507,
                detail=f"Storage insufficient. Freed {e.freed_space_mb}MB but not enough"
            )
        except StorageError as e:
            logger.error(f"Storage error uploading thumbnail: {e}")
            raise HTTPException(
                status_code=500,
                detail="Storage error during thumbnail upload"
            )

    async def _generate_thumbnail(self, image_data: bytes) -> bytes:
        """Genera thumbnail da dati immagine"""
        try:
            # Carica immagine da bytes
            image = Image.open(io.BytesIO(image_data))
            
            # Prepara immagine per thumbnail
            image = ImageUtils.prepare_image_for_thumbnail(image)
            
            # Crea thumbnail
            thumbnail = ImageUtils.create_thumbnail(image, 800)
            
            # Salva in memoria
            thumbnail_buffer = io.BytesIO()
            thumbnail.save(thumbnail_buffer, 'JPEG', quality=85, optimize=True)
            thumbnail_buffer.seek(0)
            
            return thumbnail_buffer.read()
            
        except Exception as e:
            logger.error(f"Error generating thumbnail: {e}")
            raise ImageProcessingError(f"Thumbnail generation failed: {e}")

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
        temp_file_path = None
        try:
            # Crea file temporaneo
            temp_file_path = await FileUtils.create_temp_file_from_upload(file)

            # Genera thumbnail dal file temporaneo
            return await self.generate_thumbnail(temp_file_path, photo_id, max_size)

        except ImageProcessingError as e:
            logger.error(f"Errore processamento immagine per thumbnail {photo_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Errore generazione thumbnail da file per {photo_id}: {e}")
            return None
        finally:
            # Pulisce file temporaneo
            if temp_file_path:
                FileUtils.cleanup_temp_file(temp_file_path)

    async def validate_image_file(self, file: UploadFile) -> Tuple[bool, str]:
        """Valida se il file è un'immagine supportata"""
        try:
            if not file.filename:
                return False, "Nome file mancante"

            extension = Path(file.filename).suffix.lower()
            if extension not in self.supported_formats:
                return False, f"Formato {extension} non supportato"

            # Verifica che sia effettivamente un'immagine
            temp_file_path = None
            try:
                temp_file_path = await FileUtils.create_temp_file_from_upload(file)

                with Image.open(temp_file_path) as img:
                    # Se arriviamo qui, è un'immagine valida
                    width, height = img.size
                    if width < 1 or height < 1:
                        return False, "Dimensioni immagine non valide"

                    return True, "OK"

            except ImageProcessingError as e:
                return False, f"File corrotto o non valido: {str(e)}"
            finally:
                if temp_file_path:
                    FileUtils.cleanup_temp_file(temp_file_path)

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
                        # Processa con deep zoom usando servizio centralizzato
                        if HAS_MINIO:
                            result = await archaeological_minio_service.process_photo_with_deep_zoom(
                                photo_data=content,
                                photo_id=photo_id,
                                site_id=site_id,
                                archaeological_metadata=archaeological_metadata,
                                generate_deep_zoom=True
                            )
                        else:
                            logger.warning("MinIO not available, deep zoom processing skipped")

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
