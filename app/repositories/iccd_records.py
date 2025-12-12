"""Repository for ICCD record operations."""

from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import joinedload
from app.models.iccd_records import ICCDRecord, ICCDSchemaTemplate
from app.models import User
from app.repositories.base import BaseRepository


class ICCDRecordRepository:
    """Repository for ICCD record operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def get_site_records(
        self, 
        site_id: UUID, 
        schema_type: Optional[str] = None,
        level: Optional[str] = None,
        status: Optional[str] = None,
        is_validated: Optional[bool] = None,
        skip: int = 0,
        limit: int = 20
    ) -> tuple[List[ICCDRecord], int]:
        """Get ICCD records for a site with optional filters and pagination."""
        query = select(ICCDRecord).options(
            joinedload(ICCDRecord.creator).joinedload(User.profile),
            joinedload(ICCDRecord.validator).joinedload(User.profile)
        ).where(ICCDRecord.site_id == str(site_id))
        
        # Apply filters
        if schema_type:
            query = query.where(ICCDRecord.schema_type == schema_type)
        if level:
            query = query.where(ICCDRecord.level == level)
        if status:
            query = query.where(ICCDRecord.status == status)
        if is_validated is not None:
            query = query.where(ICCDRecord.is_validated == is_validated)
        
        # Count total records
        count_query = select(func.count(ICCDRecord.id)).where(ICCDRecord.site_id == str(site_id))
        if schema_type:
            count_query = count_query.where(ICCDRecord.schema_type == schema_type)
        if level:
            count_query = count_query.where(ICCDRecord.level == level)
        if status:
            count_query = count_query.where(ICCDRecord.status == status)
        if is_validated is not None:
            count_query = count_query.where(ICCDRecord.is_validated == is_validated)
        
        total_result = await self.db_session.execute(count_query)
        total = total_result.scalar()
        
        # Apply pagination and ordering
        query = query.order_by(desc(ICCDRecord.updated_at))
        query = query.offset(skip).limit(limit)
        
        result = await self.db_session.execute(query)
        records = result.scalars().all()
        
        return records, total

    async def get_record_by_id(self, record_id: UUID, site_id: UUID) -> Optional[ICCDRecord]:
        """Get a specific ICCD record by ID and site ID."""
        # Normalize record_id - try both with and without dashes
        record_id_str = str(record_id)
        record_id_no_dashes = record_id_str.replace("-", "")
        
        query = select(ICCDRecord).options(
            joinedload(ICCDRecord.creator).joinedload(User.profile),
            joinedload(ICCDRecord.validator).joinedload(User.profile)
        ).where(
            and_(
                or_(
                    ICCDRecord.id == record_id_str,
                    ICCDRecord.id == record_id_no_dashes
                ),
                ICCDRecord.site_id == str(site_id)
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def create_record(self, record_data: Dict[str, Any]) -> ICCDRecord:
        """Create a new ICCD record."""
        from loguru import logger
        
        try:
            logger.info("Repository: Creating ICCDRecord object...")
            record = ICCDRecord(**record_data)
            logger.info(f"Repository: ICCDRecord object created with id: {record.id}")
        except Exception as e:
            logger.error(f"Repository: Error creating ICCDRecord object: {e}", exc_info=True)
            raise
        
        try:
            logger.info("Repository: Adding record to session...")
            self.db_session.add(record)
            logger.info("Repository: Record added to session")
        except Exception as e:
            logger.error(f"Repository: Error adding to session: {e}", exc_info=True)
            raise
        
        try:
            logger.info("Repository: Flushing session...")
            await self.db_session.flush()
            logger.info(f"Repository: Flush completed, id: {record.id}")
        except Exception as e:
            logger.error(f"Repository: Error flushing: {e}", exc_info=True)
            raise
        
        try:
            logger.info("Repository: Refreshing record...")
            await self.db_session.refresh(record)
            logger.info("Repository: Refresh completed")
        except Exception as e:
            logger.error(f"Repository: Error refreshing: {e}", exc_info=True)
            raise
        
        return record

    async def update_record(self, record: ICCDRecord, record_data: Dict[str, Any]) -> ICCDRecord:
        """Update an existing ICCD record."""
        updatable_fields = [
            'level', 'iccd_data', 'status', 'validation_notes',
            'validation_date', 'validated_by', 'is_validated'
        ]
        
        for field in updatable_fields:
            if field in record_data:
                value = record_data[field]
                setattr(record, field, value)
        
        await self.db_session.flush()
        return record

    async def delete_record(self, record: ICCDRecord) -> None:
        """Delete an ICCD record."""
        await self.db_session.delete(record)
        await self.db_session.flush()

    async def check_nct_exists(self, nct_region: str, nct_number: str, nct_suffix: Optional[str] = None) -> bool:
        """Check if an NCT code already exists."""
        query = select(ICCDRecord).where(
            and_(
                ICCDRecord.nct_region == nct_region,
                ICCDRecord.nct_number == nct_number,
                ICCDRecord.nct_suffix == nct_suffix
            )
        )
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_schema_templates(
        self, 
        schema_type: Optional[str] = None, 
        category: Optional[str] = None
    ) -> List[ICCDSchemaTemplate]:
        """Get ICCD schemas templates with optional filters."""
        query = select(ICCDSchemaTemplate).where(ICCDSchemaTemplate.is_active == True)
        
        if schema_type:
            query = query.where(ICCDSchemaTemplate.schema_type == schema_type)
        if category:
            query = query.where(ICCDSchemaTemplate.category == category)
        
        query = query.order_by(ICCDSchemaTemplate.schema_type, ICCDSchemaTemplate.name)
        
        result = await self.db_session.execute(query)
        return result.scalars().all()

    async def get_schema_template_by_type(self, schema_type: str) -> Optional[ICCDSchemaTemplate]:
        """Get a specific schemas template by type."""
        query = select(ICCDSchemaTemplate).where(
            and_(
                ICCDSchemaTemplate.schema_type == schema_type,
                ICCDSchemaTemplate.is_active == True
            )
        )
        
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def get_record_statistics(self, site_id: UUID) -> Dict[str, Any]:
        """Get statistics for ICCD records in a site."""
        # Total records
        total_result = await self.db_session.execute(
            select(func.count(ICCDRecord.id)).where(ICCDRecord.site_id == str(site_id))
        )
        total_records = total_result.scalar() or 0
        
        # By schemas type
        by_schema_result = await self.db_session.execute(
            select(ICCDRecord.schema_type, func.count(ICCDRecord.id))
            .where(ICCDRecord.site_id == str(site_id))
            .group_by(ICCDRecord.schema_type)
        )
        by_schema = {row[0]: row[1] for row in by_schema_result.fetchall()}
        
        # By level
        by_level_result = await self.db_session.execute(
            select(ICCDRecord.level, func.count(ICCDRecord.id))
            .where(ICCDRecord.site_id == str(site_id))
            .group_by(ICCDRecord.level)
        )
        by_level = {row[0]: row[1] for row in by_level_result.fetchall()}
        
        # By status
        by_status_result = await self.db_session.execute(
            select(ICCDRecord.status, func.count(ICCDRecord.id))
            .where(ICCDRecord.site_id == str(site_id))
            .group_by(ICCDRecord.status)
        )
        by_status = {row[0]: row[1] for row in by_status_result.fetchall()}
        
        # Validated records
        validated_result = await self.db_session.execute(
            select(func.count(ICCDRecord.id))
            .where(and_(ICCDRecord.site_id == str(site_id), ICCDRecord.status.in_(['validated', 'published'])))
        )
        validated_count = validated_result.scalar() or 0
        
        return {
            "total_records": total_records,
            "validated_records": validated_count,
            "validation_percentage": round((validated_count / total_records * 100) if total_records > 0 else 0, 2),
            "by_schema_type": by_schema,
            "by_level": by_level,
            "by_status": by_status
        }