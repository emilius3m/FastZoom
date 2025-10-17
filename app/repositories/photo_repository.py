# app/repositories/photo_repository.py - Repository Pattern per Foto
"""
Photo Repository - Implementazione repository pattern per operazioni sui dati fotografici

Questo file implementa la tecnica #3 (Repository Pattern) per centralizzare
tutte le operazioni di accesso ai dati delle foto.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.base import BaseRepository
from app.models.documentation_and_field import Photo
from app.models.archaeological_enums import PhotoType, MaterialType, ConservationStatus


class PhotoRepository(BaseRepository[Photo]):
    """
    Repository per operazioni sui dati fotografici

    Centralizza tutte le query e operazioni CRUD per il modello Photo,
    implementando il repository pattern per migliore testabilità e manutenibilità.
    """

    def __init__(self, db_session: AsyncSession):
        super().__init__(db_session, Photo)

    async def get_site_photos(
        self,
        site_id: UUID,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[Dict[str, Any]] = None,
        order_by: Optional[str] = "created_desc"
    ) -> List[Photo]:
        """
        Recupera foto del sito con filtri e paginazione

        Args:
            site_id: ID del sito
            skip: Offset per paginazione
            limit: Limite risultati
            filters: Dizionario filtri applicabili
            order_by: Ordinamento (created_desc, filename_asc, etc.)

        Returns:
            Lista foto filtrate e ordinate
        """
        query = select(Photo).where(Photo.site_id == site_id)

        # Applica filtri dinamici
        if filters:
            conditions = []

            # Filtro ricerca testuale
            if 'search' in filters and filters['search']:
                search_term = f"%{filters['search']}%"
                conditions.append(
                    or_(
                        Photo.filename.ilike(search_term),
                        Photo.title.ilike(search_term),
                        Photo.description.ilike(search_term),
                        Photo.inventory_number.ilike(search_term),
                        Photo.keywords.ilike(search_term)
                    )
                )

            # Filtri per tipo foto
            if 'photo_type' in filters and filters['photo_type']:
                try:
                    photo_type_enum = PhotoType(filters['photo_type'])
                    conditions.append(Photo.photo_type == photo_type_enum)
                except ValueError:
                    pass  # Ignora valori enum non validi

            # Filtri per materiale
            if 'material' in filters and filters['material']:
                try:
                    material_enum = MaterialType(filters['material'])
                    conditions.append(Photo.material == material_enum)
                except ValueError:
                    pass

            # Altri filtri diretti
            direct_filters = {
                'is_published': 'is_published',
                'is_validated': 'is_validated',
                'has_deep_zoom': 'has_deep_zoom',
                'excavation_area': 'excavation_area',
                'stratigraphic_unit': 'stratigraphic_unit',
                'chronology_period': 'chronology_period',
                'object_type': 'object_type'
            }

            for filter_key, field_name in direct_filters.items():
                if filter_key in filters and filters[filter_key] is not None:
                    value = filters[filter_key]
                    if isinstance(value, str):
                        conditions.append(getattr(Photo, field_name).ilike(f"%{value}%"))
                    else:
                        conditions.append(getattr(Photo, field_name) == value)

            # Filtri dimensionali
            dimension_filters = {
                'min_width': lambda x: Photo.width >= x,
                'max_width': lambda x: Photo.width <= x,
                'min_height': lambda x: Photo.height >= x,
                'max_height': lambda x: Photo.height <= x,
                'min_file_size': lambda x: Photo.file_size >= x,
                'max_file_size': lambda x: Photo.file_size <= x
            }

            for filter_key, condition_func in dimension_filters.items():
                if filter_key in filters and filters[filter_key] is not None:
                    value = filters[filter_key]
                    if 'file_size' in filter_key:
                        # Converti MB in bytes per filtri dimensione file
                        value = int(value * 1024 * 1024)
                    conditions.append(condition_func(value))

            # Filtri presenza metadati
            presence_filters = {
                'has_inventory': Photo.inventory_number.isnot(None),
                'has_description': Photo.description.isnot(None),
                'has_photographer': Photo.photographer.isnot(None)
            }

            for filter_key, condition in presence_filters.items():
                if filter_key in filters and filters[filter_key] is not None:
                    has_value = filters[filter_key]
                    if has_value:
                        conditions.append(condition)
                    else:
                        conditions.append(~condition)

            # Applica tutte le condizioni
            if conditions:
                query = query.where(and_(*conditions))

        # Ordinamento
        order_mappings = {
            "created_desc": Photo.created_at.desc(),
            "created_asc": Photo.created_at.asc(),
            "filename_asc": Photo.filename.asc(),
            "filename_desc": Photo.filename.desc(),
            "size_desc": Photo.file_size.desc(),
            "size_asc": Photo.file_size.asc(),
            "photo_date_desc": Photo.photo_date.desc().nullslast(),
            "photo_date_asc": Photo.photo_date.asc().nullslast(),
            "inventory_asc": Photo.inventory_number.asc().nullslast(),
            "inventory_desc": Photo.inventory_number.desc().nullslast(),
            "material_asc": Photo.material.asc().nullslast()
        }

        if order_by and order_by in order_mappings:
            query = query.order_by(order_mappings[order_by])
        else:
            query = query.order_by(Photo.created_at.desc())

        # Paginazione
        query = query.offset(skip).limit(limit)

        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_photo_with_relations(self, photo_id: UUID) -> Optional[Photo]:
        """
        Recupera foto con relazioni caricate (site, uploader)

        Args:
            photo_id: ID della foto

        Returns:
            Foto con relazioni o None
        """
        query = select(Photo).options(
            joinedload(Photo.site),
            joinedload(Photo.uploader)
        ).where(Photo.id == photo_id)

        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_photos_by_ids(self, photo_ids: List[UUID], site_id: UUID) -> List[Photo]:
        """
        Recupera multiple foto per ID con verifica sito

        Args:
            photo_ids: Lista ID foto
            site_id: ID sito per sicurezza

        Returns:
            Lista foto trovate
        """
        query = select(Photo).where(
            and_(
                Photo.id.in_(photo_ids),
                Photo.site_id == site_id
            )
        )

        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def update_photo_metadata(
        self,
        photo_id: UUID,
        metadata: Dict[str, Any]
    ) -> Optional[Photo]:
        """
        Aggiorna metadati foto

        Args:
            photo_id: ID della foto
            metadata: Dizionario metadati da aggiornare

        Returns:
            Foto aggiornata o None se non trovata
        """
        photo = await self.get(photo_id)
        if not photo:
            return None

        # Campi aggiornabili
        updatable_fields = {
            'title', 'description', 'keywords', 'photo_type', 'photographer',
            'inventory_number', 'old_inventory_number', 'catalog_number',
            'excavation_area', 'stratigraphic_unit', 'grid_square', 'depth_level',
            'find_date', 'finder', 'excavation_campaign',
            'material', 'material_details', 'object_type', 'object_function',
            'length_cm', 'width_cm', 'height_cm', 'diameter_cm', 'weight_grams',
            'chronology_period', 'chronology_culture',
            'dating_from', 'dating_to', 'dating_notes',
            'conservation_status', 'conservation_notes', 'restoration_history',
            'bibliography', 'comparative_references', 'external_links',
            'copyright_holder', 'license_type', 'usage_rights',
            'validation_notes'
        }

        # Applica aggiornamenti
        for field, value in metadata.items():
            if field in updatable_fields and hasattr(photo, field):
                setattr(photo, field, value)

        await self.db_session.commit()
        return photo

    async def bulk_update_photos(
        self,
        photo_ids: List[UUID],
        site_id: UUID,
        updates: Dict[str, Any]
    ) -> int:
        """
        Aggiornamento bulk di multiple foto

        Args:
            photo_ids: Lista ID foto da aggiornare
            site_id: ID sito per sicurezza
            updates: Dizionario aggiornamenti

        Returns:
            Numero foto aggiornate
        """
        # Verifica che le foto esistano e appartengano al sito
        existing_photos = await self.get_photos_by_ids(photo_ids, site_id)
        if not existing_photos:
            return 0

        # Filtra campi aggiornabili
        updatable_fields = {
            'title', 'description', 'keywords', 'photo_type', 'photographer',
            'inventory_number', 'excavation_area', 'material', 'chronology_period',
            'conservation_status', 'is_published', 'is_validated'
        }

        filtered_updates = {
            k: v for k, v in updates.items()
            if k in updatable_fields and v is not None
        }

        if not filtered_updates:
            return 0

        # Applica aggiornamenti
        updated_count = 0
        for photo in existing_photos:
            for field, value in filtered_updates.items():
                if hasattr(photo, field):
                    setattr(photo, field, value)
            updated_count += 1

        await self.db_session.commit()
        return updated_count

    async def delete_photos(self, photo_ids: List[UUID], site_id: UUID) -> int:
        """
        Eliminazione bulk foto

        Args:
            photo_ids: Lista ID foto da eliminare
            site_id: ID sito per sicurezza

        Returns:
            Numero foto eliminate
        """
        photos = await self.get_photos_by_ids(photo_ids, site_id)
        if not photos:
            return 0

        for photo in photos:
            await self.db_session.delete(photo)

        await self.db_session.commit()
        return len(photos)

    async def get_site_photos_statistics(self, site_id: UUID) -> Dict[str, Any]:
        """
        Statistiche foto del sito

        Args:
            site_id: ID del sito

        Returns:
            Dizionario statistiche
        """
        # Conteggio totale
        total_query = select(func.count(Photo.id)).where(Photo.site_id == site_id)
        total_result = await self.db_session.execute(total_query)
        total = total_result.scalar() or 0

        # Conteggio per tipo
        type_query = select(
            Photo.photo_type,
            func.count(Photo.id)
        ).where(
            and_(Photo.site_id == site_id, Photo.photo_type.isnot(None))
        ).group_by(Photo.photo_type)

        type_result = await self.db_session.execute(type_query)
        photos_by_type = {row[0]: row[1] for row in type_result.fetchall()}

        # Conteggio per stato pubblicazione
        published_query = select(
            Photo.is_published,
            func.count(Photo.id)
        ).where(Photo.site_id == site_id).group_by(Photo.is_published)

        published_result = await self.db_session.execute(published_query)
        publication_stats = {}
        for row in published_result.fetchall():
            status = "published" if row[0] else "unpublished"
            publication_stats[status] = row[1]

        # Storage utilizzato
        storage_query = select(func.sum(Photo.file_size)).where(Photo.site_id == site_id)
        storage_result = await self.db_session.execute(storage_query)
        total_size_bytes = storage_result.scalar() or 0
        total_size_mb = round(total_size_bytes / (1024 * 1024), 2)

        return {
            "total_photos": total,
            "photos_by_type": photos_by_type,
            "publication_stats": publication_stats,
            "total_storage_mb": total_size_mb,
            "average_photo_size_mb": round(total_size_mb / total, 2) if total > 0 else 0
        }

    async def search_photos_by_metadata(
        self,
        site_id: UUID,
        search_criteria: Dict[str, Any],
        limit: int = 50
    ) -> List[Photo]:
        """
        Ricerca avanzata foto per metadati archeologici

        Args:
            site_id: ID sito
            search_criteria: Criteri ricerca
            limit: Limite risultati

        Returns:
            Lista foto corrispondenti
        """
        query = select(Photo).where(Photo.site_id == site_id)

        conditions = []

        # Ricerca per campi specifici
        search_mappings = {
            'inventory_number': ('ilike', Photo.inventory_number),
            'excavation_area': ('ilike', Photo.excavation_area),
            'stratigraphic_unit': ('ilike', Photo.stratigraphic_unit),
            'chronology_period': ('ilike', Photo.chronology_period),
            'object_type': ('ilike', Photo.object_type),
            'material': ('exact', Photo.material),
            'photographer': ('ilike', Photo.photographer),
            'description': ('ilike', Photo.description)
        }

        for criteria, search_config in search_mappings.items():
            if criteria in search_criteria and search_criteria[criteria]:
                search_type, field = search_config
                value = search_criteria[criteria]
                if search_type == 'ilike':
                    conditions.append(field.ilike(f"%{value}%"))
                elif search_type == 'exact':
                    # Handle enum conversion for material
                    if criteria == 'material':
                        try:
                            enum_value = MaterialType(value)
                            conditions.append(field == enum_value)
                        except ValueError:
                            pass  # Skip invalid enum values
                    else:
                        conditions.append(field == value)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.order_by(Photo.created_at.desc()).limit(limit)

        result = await self.db_session.execute(query)
        return result.scalars().all()