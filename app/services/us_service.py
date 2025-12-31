"""
US/USM Service - Business logic for Unità Stratigrafiche and Murarie
Handles all CRUD operations, validation, and data transformations for US/USM units.
"""

from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, date
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, or_, func
from sqlalchemy.orm import selectinload
from loguru import logger
import re

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria
from app.schemas.us import USCreate, USUpdate, USMCreate, USMUpdate
from app.core.domain_exceptions import (
    SiteNotFoundError,
    InsufficientPermissionsError,
    ValidationError as DomainValidationError,
    ResourceNotFoundError
)


class USService:
    """Service for US/USM (Unità Stratigrafiche/Murarie) management"""
    
    # Validation patterns
    US_CODE_PATTERN = re.compile(r'^US\d{3,4}$')
    USM_CODE_PATTERN = re.compile(r'^USM\d{3,4}$')
    
    @staticmethod
    def normalize_uuid(uuid_str: str) -> str:
        """
        Normalize UUID string from 32-char hex to standard UUID format with hyphens.
        
        Args:
            uuid_str: UUID string (with or without hyphens)
            
        Returns:
            Normalized UUID string with hyphens
            
        Raises:
            DomainValidationError: If UUID format is invalid
        """
        try:
            if '-' not in uuid_str and len(uuid_str) == 32:
                # Format: 209a6c63f1f1483cac15c81041c03149 -> 209a6c63-f1f1-483c-ac15-c81041c03149
                normalized = f"{uuid_str[0:8]}-{uuid_str[8:12]}-{uuid_str[12:16]}-{uuid_str[16:20]}-{uuid_str[20:32]}"
                UUID(normalized)  # Validate format
                return normalized
            else:
                # Validate and return as-is
                uuid_obj = UUID(uuid_str)
                return str(uuid_obj)
        except (ValueError, TypeError) as e:
            raise DomainValidationError(
                f"UUID '{uuid_str}' non è valido",
                details={"uuid": uuid_str, "error": str(e)}
            )
    
    @staticmethod
    def validate_us_code(code: str) -> None:
        """
        Validate US code format (US followed by 3-4 digits).
        
        Args:
            code: US code to validate
            
        Raises:
            DomainValidationError: If code format is invalid
        """
        if not USService.US_CODE_PATTERN.match(code):
            raise DomainValidationError(
                f"us_code '{code}' non è valido. Deve essere nel formato US seguito da 3-4 cifre (es: US001, US0001)",
                details={"us_code": code, "pattern": "US###"}
            )
    
    @staticmethod
    def validate_usm_code(code: str) -> None:
        """
        Validate USM code format (USM followed by 3-4 digits).
        
        Args:
            code: USM code to validate
            
        Raises:
            DomainValidationError: If code format is invalid
        """
        if not USService.USM_CODE_PATTERN.match(code):
            raise DomainValidationError(
                f"usm_code '{code}' non è valido. Deve essere nel formato USM seguito da 3-4 cifre (es: USM001, USM0001)",
                details={"usm_code": code, "pattern": "USM###"}
            )
    
    @staticmethod
    def process_date_field(value: Any, field_name: str) -> Optional[date]:
        """
        Process date field from string to date object.
        
        Args:
            value: Date value (string or date object)
            field_name: Field name for error messages
            
        Returns:
            Date object or None
            
        Raises:
            DomainValidationError: If date format is invalid
        """
        if value is None:
            return None
        
        if isinstance(value, date):
            return value
        
        if isinstance(value, str):
            if not value.strip():
                return None
            try:
                return datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                raise DomainValidationError(
                    f"Campo '{field_name}': '{value}' non è una data valida. Usare formato YYYY-MM-DD (es: 2025-01-15)",
                    details={"field": field_name, "value": value, "expected_format": "YYYY-MM-DD"}
                )
        
        return value
    
    @staticmethod
    def process_us_payload(payload_dict: Dict[str, Any], site_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """
        Process and validate US payload data.
        
        Args:
            payload_dict: Raw payload dictionary
            site_id: Site ID from URL
            user_id: Current user ID
            
        Returns:
            Processed payload dictionary
            
        Raises:
            DomainValidationError: If validation fails
        """
        # Override site_id from URL parameter
        payload_dict['site_id'] = str(site_id)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                payload_dict[field] = USService.process_date_field(payload_dict[field], field)
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass  # Keep original value if conversion fails
        
        # Validate us_code format
        if 'us_code' in payload_dict and payload_dict['us_code']:
            USService.validate_us_code(payload_dict['us_code'])
        
        # Add audit fields
        payload_dict['created_by'] = str(user_id)
        payload_dict['updated_by'] = str(user_id)
        
        return payload_dict
    
    @staticmethod
    def process_usm_payload(payload_dict: Dict[str, Any], site_id: UUID, user_id: UUID) -> Dict[str, Any]:
        """
        Process and validate USM payload data.
        
        Args:
            payload_dict: Raw payload dictionary
            site_id: Site ID from URL
            user_id: Current user ID
            
        Returns:
            Processed payload dictionary
            
        Raises:
            DomainValidationError: If validation fails
        """
        # Override site_id from URL parameter
        payload_dict['site_id'] = str(site_id)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                payload_dict[field] = USService.process_date_field(payload_dict[field], field)
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        if 'superficie_analizzata' in payload_dict and payload_dict['superficie_analizzata'] is not None:
            try:
                payload_dict['superficie_analizzata'] = float(payload_dict['superficie_analizzata'])
            except (ValueError, TypeError):
                pass
        
        # Validate usm_code format
        if 'usm_code' in payload_dict and payload_dict['usm_code']:
            USService.validate_usm_code(payload_dict['usm_code'])
        
        # Add audit fields
        payload_dict['created_by'] = str(user_id)
        payload_dict['updated_by'] = str(user_id)
        
        return payload_dict
    
    @staticmethod
    async def create_us(
        db: AsyncSession,
        payload: USCreate,
        site_id: UUID,
        user_id: UUID
    ) -> UnitaStratigrafica:
        """
        Create a new US (Unità Stratigrafica).
        
        Args:
            db: Database session
            payload: US creation data
            site_id: Site ID
            user_id: Current user ID
            
        Returns:
            Created US entity
            
        Raises:
            DomainValidationError: If validation fails
        """
        logger.info(f"Creating US with payload: {payload.model_dump()}")
        
        payload_dict = payload.model_dump(exclude_unset=True)
        payload_dict = USService.process_us_payload(payload_dict, site_id, user_id)
        
        us = UnitaStratigrafica(**payload_dict)
        db.add(us)
        await db.commit()
        await db.refresh(us)
        
        logger.success(f"US created successfully: {us.id}")
        return us
    
    @staticmethod
    async def get_us(
        db: AsyncSession,
        us_id: str,
        site_id: UUID
    ) -> UnitaStratigrafica:
        """
        Get a specific US by ID.
        
        Args:
            db: Database session
            us_id: US ID (will be normalized)
            site_id: Site ID for validation
            
        Returns:
            US entity
            
        Raises:
            ResourceNotFoundError: If US not found
            DomainValidationError: If US belongs to different site
        """
        normalized_id = USService.normalize_uuid(us_id)
        logger.info(f"Getting US {normalized_id} from site {site_id}")
        
        result = await db.execute(
            select(UnitaStratigrafica).where(UnitaStratigrafica.id == normalized_id)
        )
        us = result.scalar_one_or_none()
        
        if not us:
            raise ResourceNotFoundError(
                f"US {normalized_id} non trovata",
                details={"us_id": normalized_id}
            )
        
        if us.site_id != str(site_id):
            raise ResourceNotFoundError(
                f"US {normalized_id} appartiene al sito {us.site_id}, non al sito {site_id}",
                details={
                    "us_id": normalized_id,
                    "requested_site": str(site_id),
                    "actual_site": us.site_id
                }
            )
        
        logger.success(f"US {normalized_id} retrieved successfully")
        return us
    
    @staticmethod
    async def list_us(
        db: AsyncSession,
        site_id: UUID,
        search: Optional[str] = None,
        da: Optional[str] = None,
        a: Optional[str] = None,
        us_code: Optional[str] = None,
        tipo: Optional[str] = None,
        periodo: Optional[str] = None,
        fase: Optional[str] = None,
        definizione: Optional[str] = None,
        localita: Optional[str] = None,
        area_struttura: Optional[str] = None,
        affidabilita: Optional[str] = None,
        responsabile: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[UnitaStratigrafica]:
        """
        List US units for a site with optional filtering.
        
        Args:
            db: Database session
            site_id: Site ID
            search: Generic text search
            da: Date from (YYYY-MM-DD)
            a: Date to (YYYY-MM-DD)
            us_code: US code filter
            tipo: Type filter (positiva/negativa)
            periodo: Period filter
            fase: Phase filter
            definizione: Definition filter
            localita: Locality filter
            area_struttura: Area/structure filter
            affidabilita: Reliability filter
            responsabile: Responsible person filter
            skip: Pagination offset
            limit: Pagination limit
            
        Returns:
            List of US entities
        """
        q = select(UnitaStratigrafica).where(UnitaStratigrafica.site_id == str(site_id))
        
        # Generic text search
        if search:
            like = f"%{search}%"
            q = q.where(or_(
                UnitaStratigrafica.descrizione.ilike(like),
                UnitaStratigrafica.us_code.ilike(like),
                UnitaStratigrafica.definizione.ilike(like),
                UnitaStratigrafica.localita.ilike(like)
            ))
        
        # Advanced filters
        if us_code:
            q = q.where(UnitaStratigrafica.us_code.ilike(f"%{us_code}%"))
        
        if tipo:
            q = q.where(UnitaStratigrafica.tipo == tipo)
        
        if periodo:
            q = q.where(UnitaStratigrafica.periodo.ilike(f"%{periodo}%"))
        
        if fase:
            q = q.where(UnitaStratigrafica.fase.ilike(f"%{fase}%"))
        
        if definizione:
            q = q.where(UnitaStratigrafica.definizione.ilike(f"%{definizione}%"))
        
        if localita:
            q = q.where(UnitaStratigrafica.localita.ilike(f"%{localita}%"))
        
        if area_struttura:
            q = q.where(UnitaStratigrafica.area_struttura.ilike(f"%{area_struttura}%"))
        
        if affidabilita:
            q = q.where(UnitaStratigrafica.affidabilita_stratigrafica == affidabilita)
        
        if responsabile:
            q = q.where(UnitaStratigrafica.responsabile_compilazione.ilike(f"%{responsabile}%"))
        
        # Date range filters
        if da:
            try:
                date_from = datetime.strptime(da, "%Y-%m-%d").date()
                q = q.where(UnitaStratigrafica.data_rilevamento >= date_from)
            except ValueError:
                pass  # Invalid date format, skip filter
        
        if a:
            try:
                date_to = datetime.strptime(a, "%Y-%m-%d").date()
                q = q.where(UnitaStratigrafica.data_rilevamento <= date_to)
            except ValueError:
                pass  # Invalid date format, skip filter
        
        q = q.order_by(desc(UnitaStratigrafica.created_at)).offset(skip).limit(limit)
        rows = (await db.execute(q)).scalars().all()
        
        logger.info(f"Listed {len(rows)} US units for site {site_id}")
        return list(rows)
    
    @staticmethod
    async def update_us(
        db: AsyncSession,
        us_id: str,
        payload: USUpdate,
        site_id: UUID
    ) -> UnitaStratigrafica:
        """
        Update an existing US.
        
        Args:
            db: Database session
            us_id: US ID
            payload: Update data
            site_id: Site ID for validation
            
        Returns:
            Updated US entity
            
        Raises:
            ResourceNotFoundError: If US not found
        """
        normalized_id = USService.normalize_uuid(us_id)
        logger.info(f"Updating US {normalized_id}")
        
        # Get existing US
        us = await USService.get_us(db, normalized_id, site_id)
        
        # Process payload
        payload_dict = payload.model_dump(exclude_unset=True)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                payload_dict[field] = USService.process_date_field(payload_dict[field], field)
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        # Update fields
        for k, v in payload_dict.items():
            setattr(us, k, v)
        
        await db.commit()
        await db.refresh(us)
        
        logger.success(f"US {normalized_id} updated successfully")
        return us
    
    @staticmethod
    async def delete_us(
        db: AsyncSession,
        us_id: str,
        site_id: UUID
    ) -> None:
        """
        Delete a US.
        
        Args:
            db: Database session
            us_id: US ID
            site_id: Site ID for validation
            
        Raises:
            ResourceNotFoundError: If US not found
        """
        normalized_id = USService.normalize_uuid(us_id)
        logger.info(f"Deleting US {normalized_id}")
        
        # Get existing US
        us = await USService.get_us(db, normalized_id, site_id)
        
        await db.delete(us)
        await db.commit()
        
        logger.success(f"US {normalized_id} deleted successfully")
    
    # USM methods follow similar pattern
    
    @staticmethod
    async def create_usm(
        db: AsyncSession,
        payload: USMCreate,
        site_id: UUID,
        user_id: UUID
    ) -> UnitaStratigraficaMuraria:
        """Create a new USM (Unità Stratigrafica Muraria)."""
        logger.info(f"Creating USM with payload: {payload.model_dump()}")
        
        payload_dict = payload.model_dump(exclude_unset=True)
        payload_dict = USService.process_usm_payload(payload_dict, site_id, user_id)
        
        usm = UnitaStratigraficaMuraria(**payload_dict)
        db.add(usm)
        await db.commit()
        await db.refresh(usm)
        
        logger.success(f"USM created successfully: {usm.id}")
        return usm
    
    @staticmethod
    async def get_usm(
        db: AsyncSession,
        usm_id: str,
        site_id: UUID
    ) -> UnitaStratigraficaMuraria:
        """Get a specific USM by ID."""
        normalized_id = USService.normalize_uuid(usm_id)
        logger.info(f"Getting USM {normalized_id}")
        
        result = await db.execute(
            select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.id == normalized_id)
        )
        usm = result.scalar_one_or_none()
        
        if not usm:
            raise ResourceNotFoundError(
                f"USM {normalized_id} non trovata",
                details={"usm_id": normalized_id}
            )
        
        if usm.site_id != str(site_id):
            raise ResourceNotFoundError(
                f"USM {normalized_id} appartiene al sito {usm.site_id}, non al sito {site_id}",
                details={
                    "usm_id": normalized_id,
                    "requested_site": str(site_id),
                    "actual_site": usm.site_id
                }
            )
        
        logger.success(f"USM {normalized_id} retrieved successfully")
        return usm
    
    @staticmethod
    async def list_usm(
        db: AsyncSession,
        site_id: UUID,
        search: Optional[str] = None,
        usm_code: Optional[str] = None,
        periodo: Optional[str] = None,
        fase: Optional[str] = None,
        definizione: Optional[str] = None,
        localita: Optional[str] = None,
        area_struttura: Optional[str] = None,
        tecnica_costruttiva: Optional[str] = None,
        affidabilita: Optional[str] = None,
        responsabile: Optional[str] = None,
        da: Optional[str] = None,
        a: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[UnitaStratigraficaMuraria]:
        """List USM units for a site with optional filtering."""
        q = select(UnitaStratigraficaMuraria).where(UnitaStratigraficaMuraria.site_id == str(site_id))
        
        # Generic text search
        if search:
            like = f"%{search}%"
            q = q.where(or_(
                UnitaStratigraficaMuraria.descrizione.ilike(like),
                UnitaStratigraficaMuraria.usm_code.ilike(like),
                UnitaStratigraficaMuraria.definizione.ilike(like),
                UnitaStratigraficaMuraria.localita.ilike(like)
            ))
        
        # Advanced filters
        if usm_code:
            q = q.where(UnitaStratigraficaMuraria.usm_code.ilike(f"%{usm_code}%"))
        
        if periodo:
            q = q.where(UnitaStratigraficaMuraria.periodo.ilike(f"%{periodo}%"))
        
        if fase:
            q = q.where(UnitaStratigraficaMuraria.fase.ilike(f"%{fase}%"))
        
        if definizione:
            q = q.where(UnitaStratigraficaMuraria.definizione.ilike(f"%{definizione}%"))
        
        if localita:
            q = q.where(UnitaStratigraficaMuraria.localita.ilike(f"%{localita}%"))
        
        if area_struttura:
            q = q.where(UnitaStratigraficaMuraria.area_struttura.ilike(f"%{area_struttura}%"))
        
        if tecnica_costruttiva:
            q = q.where(UnitaStratigraficaMuraria.tecnica_costruttiva.ilike(f"%{tecnica_costruttiva}%"))
        
        if affidabilita:
            q = q.where(UnitaStratigraficaMuraria.affidabilita_stratigrafica == affidabilita)
        
        if responsabile:
            q = q.where(UnitaStratigraficaMuraria.responsabile_compilazione.ilike(f"%{responsabile}%"))
        
        # Date range filters
        if da:
            try:
                date_from = datetime.strptime(da, "%Y-%m-%d").date()
                q = q.where(UnitaStratigraficaMuraria.data_rilevamento >= date_from)
            except ValueError:
                pass
        
        if a:
            try:
                date_to = datetime.strptime(a, "%Y-%m-%d").date()
                q = q.where(UnitaStratigraficaMuraria.data_rilevamento <= date_to)
            except ValueError:
                pass
        
        q = q.order_by(desc(UnitaStratigraficaMuraria.created_at)).offset(skip).limit(limit)
        rows = (await db.execute(q)).scalars().all()
        
        logger.info(f"Listed {len(rows)} USM units for site {site_id}")
        return list(rows)
    
    @staticmethod
    async def update_usm(
        db: AsyncSession,
        usm_id: str,
        payload: USMUpdate,
        site_id: UUID
    ) -> UnitaStratigraficaMuraria:
        """Update an existing USM."""
        normalized_id = USService.normalize_uuid(usm_id)
        logger.info(f"Updating USM {normalized_id}")
        
        # Get existing USM
        usm = await USService.get_usm(db, normalized_id, site_id)
        
        # Process payload
        payload_dict = payload.model_dump(exclude_unset=True)
        
        # Handle date fields
        date_fields = ['data_rilevamento', 'data_rielaborazione']
        for field in date_fields:
            if field in payload_dict and payload_dict[field] is not None:
                payload_dict[field] = USService.process_date_field(payload_dict[field], field)
        
        # Handle numeric fields
        if 'anno' in payload_dict and payload_dict['anno'] is not None:
            try:
                payload_dict['anno'] = int(payload_dict['anno'])
            except (ValueError, TypeError):
                pass
        
        if 'superficie_analizzata' in payload_dict and payload_dict['superficie_analizzata'] is not None:
            try:
                payload_dict['superficie_analizzata'] = float(payload_dict['superficie_analizzata'])
            except (ValueError, TypeError):
                pass
        
        # Update fields
        for k, v in payload_dict.items():
            setattr(usm, k, v)
        
        await db.commit()
        await db.refresh(usm)
        
        logger.success(f"USM {normalized_id} updated successfully")
        return usm
    
    @staticmethod
    async def delete_usm(
        db: AsyncSession,
        usm_id: str,
        site_id: UUID
    ) -> None:
        """Delete a USM."""
        normalized_id = USService.normalize_uuid(usm_id)
        logger.info(f"Deleting USM {normalized_id}")
        
        # Get existing USM
        usm = await USService.get_usm(db, normalized_id, site_id)
        
        await db.delete(usm)
        await db.commit()
        
        logger.success(f"USM {normalized_id} deleted successfully")
