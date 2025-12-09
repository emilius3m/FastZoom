# app/services/harris_matrix_mapping_service.py
"""
Service for managing persistent ID mappings in Harris Matrix system.

This service handles the lifecycle of temporary-to-database ID mappings,
providing transaction tracking, session management, and recovery mechanisms
for interrupted operations.
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, text
from loguru import logger

from app.models.harris_matrix_mapping import (
    HarrisMatrixMapping,
    MappingStatusEnum
)
from app.exceptions import HarrisMatrixServiceError


class HarrisMatrixMappingService:
    """
    Service for managing persistent ID mappings in Harris Matrix operations.
    
    This service provides database-backed storage for temporary-to-database ID
    relationships, enabling recovery scenarios and supporting multi-user
    concurrent editing sessions with transaction boundaries.
    """
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the mapping service with database session.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db

    async def create_mapping_session(
        self, 
        site_id: UUID, 
        session_id: str, 
        user_id: Optional[UUID] = None
    ) -> str:
        """
        Initialize a new mapping session.
        
        Creates a session identifier and cleans up any expired mappings
        for the same site and session.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            user_id: Optional user identifier for audit trail
            
        Returns:
            Session transaction ID for tracking
            
        Raises:
            HarrisMatrixServiceError: If session creation fails
        """
        try:
            logger.info(f"Creating mapping session for site {site_id}, session {session_id}")
            
            # Generate transaction ID for this session
            transaction_id = str(uuid.uuid4())
            
            # Clean up any expired mappings for this session
            await self.cleanup_expired_session_mappings(site_id, session_id)
            
            logger.success(f"Mapping session created: {transaction_id}")
            return transaction_id
            
        except Exception as e:
            logger.error(f"Error creating mapping session for site {site_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "create_mapping_session")

    async def save_temp_to_db_mapping(
        self, 
        site_id: UUID, 
        session_id: str, 
        temp_id: str, 
        db_id: UUID, 
        unit_code: str,
        user_id: Optional[UUID] = None
    ) -> bool:
        """
        Persist a temporary-to-database ID mapping.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            temp_id: Temporary ID from frontend
            db_id: Database UUID identifier
            unit_code: Human-readable unit code
            user_id: Optional user identifier for audit trail
            
        Returns:
            True if mapping was saved successfully
            
        Raises:
            HarrisMatrixServiceError: If mapping save fails
        """
        try:
            logger.debug(f"Saving mapping: {temp_id} -> {db_id} ({unit_code})")
            
            # Check if mapping already exists
            existing_query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.temp_id == temp_id
                )
            )
            existing_result = await self.db.execute(existing_query)
            existing_mapping = existing_result.scalar_one_or_none()
            
            if existing_mapping:
                # Update existing mapping
                existing_mapping.db_id = db_id
                existing_mapping.unit_code = unit_code
                existing_mapping.status = MappingStatusEnum.ACTIVE
                existing_mapping.updated_at = datetime.utcnow()
                existing_mapping.touch()
                
                logger.debug(f"Updated existing mapping for temp_id: {temp_id}")
            else:
                # Create new mapping
                mapping = HarrisMatrixMapping.create_mapping(
                    site_id=site_id,
                    session_id=session_id,
                    temp_id=temp_id,
                    db_id=db_id,
                    unit_code=unit_code,
                    user_id=user_id
                )
                
                self.db.add(mapping)
                await self.db.flush()
                
                logger.debug(f"Created new mapping for temp_id: {temp_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error saving mapping {temp_id} -> {db_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "save_temp_to_db_mapping")

    async def get_mapping_by_temp_id(
        self, 
        site_id: UUID, 
        session_id: str, 
        temp_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve database ID for a temporary ID.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            temp_id: Temporary ID from frontend
            
        Returns:
            Mapping dictionary or None if not found
            
        Raises:
            HarrisMatrixServiceError: If mapping retrieval fails
        """
        try:
            logger.debug(f"Looking up mapping for temp_id: {temp_id}")
            
            query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.temp_id == temp_id,
                    HarrisMatrixMapping.status.in_([
                        MappingStatusEnum.ACTIVE,
                        MappingStatusEnum.COMMITTED
                    ])
                )
            )
            
            result = await self.db.execute(query)
            mapping = result.scalar_one_or_none()
            
            if mapping:
                # Update last accessed timestamp
                mapping.touch()
                await self.db.flush()
                
                return mapping.to_compact_dict()
            
            logger.debug(f"No mapping found for temp_id: {temp_id}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving mapping for temp_id {temp_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "get_mapping_by_temp_id")

    async def get_all_mappings_for_session(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all mappings for a session.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            List of mapping dictionaries
            
        Raises:
            HarrisMatrixServiceError: If mapping retrieval fails
        """
        try:
            logger.debug(f"Retrieving all mappings for session: {session_id}")
            
            query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.status.in_([
                        MappingStatusEnum.ACTIVE,
                        MappingStatusEnum.COMMITTED
                    ])
                )
            )
            
            result = await self.db.execute(query)
            mappings = result.scalars().all()
            
            mapping_list = []
            for mapping in mappings:
                mapping.touch()
                mapping_list.append(mapping.to_compact_dict())
            
            await self.db.flush()
            
            logger.debug(f"Retrieved {len(mapping_list)} mappings for session: {session_id}")
            return mapping_list
            
        except Exception as e:
            logger.error(f"Error retrieving mappings for session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "get_all_mappings_for_session")

    async def commit_mappings(
        self, 
        site_id: UUID, 
        session_id: str, 
        transaction_id: str
    ) -> Dict[str, Any]:
        """
        Commit all mappings for a transaction.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            transaction_id: Transaction identifier for audit trail
            
        Returns:
            Dictionary with commit statistics
            
        Raises:
            HarrisMatrixServiceError: If commit operation fails
        """
        try:
            logger.info(f"Committing mappings for session {session_id}, transaction {transaction_id}")
            
            # Get all active mappings for the session
            query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.status == MappingStatusEnum.ACTIVE
                )
            )
            
            result = await self.db.execute(query)
            mappings = result.scalars().all()
            
            committed_count = 0
            for mapping in mappings:
                mapping.commit(transaction_id)
                committed_count += 1
            
            await self.db.flush()
            
            commit_result = {
                'transaction_id': transaction_id,
                'session_id': session_id,
                'committed_count': committed_count,
                'commit_time': datetime.utcnow().isoformat()
            }
            
            logger.success(f"Committed {committed_count} mappings for transaction {transaction_id}")
            return commit_result
            
        except Exception as e:
            logger.error(f"Error committing mappings for transaction {transaction_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "commit_mappings")

    async def rollback_mappings(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Rollback all mappings for a failed transaction.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            Dictionary with rollback statistics
            
        Raises:
            HarrisMatrixServiceError: If rollback operation fails
        """
        try:
            logger.info(f"Rolling back mappings for session: {session_id}")
            
            # Get all active mappings for the session
            query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.status == MappingStatusEnum.ACTIVE
                )
            )
            
            result = await self.db.execute(query)
            mappings = result.scalars().all()
            
            rolled_back_count = 0
            for mapping in mappings:
                mapping.rollback()
                rolled_back_count += 1
            
            await self.db.flush()
            
            rollback_result = {
                'session_id': session_id,
                'rolled_back_count': rolled_back_count,
                'rollback_time': datetime.utcnow().isoformat()
            }
            
            logger.success(f"Rolled back {rolled_back_count} mappings for session {session_id}")
            return rollback_result
            
        except Exception as e:
            logger.error(f"Error rolling back mappings for session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "rollback_mappings")

    async def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """
        Clean up old mapping sessions.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
            
        Returns:
            Number of cleaned up sessions
            
        Raises:
            HarrisMatrixServiceError: If cleanup operation fails
        """
        try:
            logger.info(f"Cleaning up expired mapping sessions older than {max_age_hours} hours")
            
            cutoff_time = datetime.utcnow() - timedelta(hours=max_age_hours)
            
            # Find expired mappings
            expired_query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.expires_at < cutoff_time,
                    HarrisMatrixMapping.status == MappingStatusEnum.ACTIVE
                )
            )
            
            result = await self.db.execute(expired_query)
            expired_mappings = result.scalars().all()
            
            cleaned_count = 0
            for mapping in expired_mappings:
                mapping.expire()
                cleaned_count += 1
            
            await self.db.flush()
            
            logger.success(f"Cleaned up {cleaned_count} expired mappings")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired sessions: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "cleanup_expired_sessions")

    async def cleanup_expired_session_mappings(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> int:
        """
        Clean up expired mappings for a specific session.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            Number of cleaned up mappings
            
        Raises:
            HarrisMatrixServiceError: If cleanup operation fails
        """
        try:
            logger.debug(f"Cleaning up expired mappings for session: {session_id}")
            
            # Find expired mappings for this session
            expired_query = select(HarrisMatrixMapping).where(
                and_(
                    HarrisMatrixMapping.site_id == site_id,
                    HarrisMatrixMapping.session_id == session_id,
                    HarrisMatrixMapping.status == MappingStatusEnum.ACTIVE,
                    HarrisMatrixMapping.is_expired == True
                )
            )
            
            result = await self.db.execute(expired_query)
            expired_mappings = result.scalars().all()
            
            cleaned_count = 0
            for mapping in expired_mappings:
                mapping.expire()
                cleaned_count += 1
            
            await self.db.flush()
            
            logger.debug(f"Cleaned up {cleaned_count} expired mappings for session {session_id}")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"Error cleaning up expired mappings for session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "cleanup_expired_session_mappings")

    async def get_session_statistics(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get statistics for a mapping session.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            Dictionary with session statistics
            
        Raises:
            HarrisMatrixServiceError: If statistics retrieval fails
        """
        try:
            logger.debug(f"Getting statistics for session: {session_id}")
            
            # Count mappings by status
            stats_query = text("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    MIN(created_at) as first_created,
                    MAX(created_at) as last_created,
                    MAX(updated_at) as last_updated
                FROM harris_matrix_mappings
                WHERE site_id = :site_id AND session_id = :session_id
                GROUP BY status
            """)
            
            result = await self.db.execute(stats_query, {
                "site_id": str(site_id),
                "session_id": session_id
            })
            
            status_counts = {}
            first_created = None
            last_created = None
            last_updated = None
            
            for row in result:
                status_counts[row.status] = row.count
                if not first_created or (row.first_created and row.first_created < first_created):
                    first_created = row.first_created
                if not last_created or (row.last_created and row.last_created > last_created):
                    last_created = row.last_created
                if not last_updated or (row.last_updated and row.last_updated > last_updated):
                    last_updated = row.last_updated
            
            statistics = {
                'site_id': str(site_id),
                'session_id': session_id,
                'status_counts': status_counts,
                'total_mappings': sum(status_counts.values()),
                'first_created': first_created.isoformat() if first_created else None,
                'last_created': last_created.isoformat() if last_created else None,
                'last_updated': last_updated.isoformat() if last_updated else None
            }
            
            logger.debug(f"Retrieved statistics for session {session_id}: {statistics}")
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting statistics for session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "get_session_statistics")

    async def validate_session_integrity(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Validate the integrity of mappings in a session.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            Dictionary with validation results
            
        Raises:
            HarrisMatrixServiceError: If validation operation fails
        """
        try:
            logger.debug(f"Validating integrity for session: {session_id}")
            
            # Get all mappings for the session
            mappings = await self.get_all_mappings_for_session(site_id, session_id)
            
            validation_results = {
                'site_id': str(site_id),
                'session_id': session_id,
                'total_mappings': len(mappings),
                'valid_mappings': 0,
                'invalid_mappings': 0,
                'issues': [],
                'is_valid': True
            }
            
            for mapping in mappings:
                temp_id = mapping.get('temp_id')
                db_id = mapping.get('db_id')
                unit_code = mapping.get('unit_code')
                
                # Validate mapping structure
                issues = []
                
                if not temp_id:
                    issues.append("Missing temp_id")
                if not db_id:
                    issues.append("Missing db_id")
                if not unit_code:
                    issues.append("Missing unit_code")
                
                # Validate UUID format for db_id
                if db_id:
                    try:
                        UUID(db_id)
                    except ValueError:
                        issues.append("Invalid db_id UUID format")
                
                if issues:
                    validation_results['invalid_mappings'] += 1
                    validation_results['issues'].append({
                        'temp_id': temp_id,
                        'issues': issues
                    })
                    validation_results['is_valid'] = False
                else:
                    validation_results['valid_mappings'] += 1
            
            logger.debug(f"Session validation completed: {validation_results}")
            return validation_results
            
        except Exception as e:
            logger.error(f"Error validating session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "validate_session_integrity")

    async def recover_session(
        self, 
        site_id: UUID, 
        session_id: str
    ) -> Dict[str, Any]:
        """
        Attempt to recover a session's mappings for interrupted operations.
        
        Args:
            site_id: UUID of the archaeological site
            session_id: User session identifier
            
        Returns:
            Dictionary with recovery results
            
        Raises:
            HarrisMatrixServiceError: If recovery operation fails
        """
        try:
            logger.info(f"Attempting to recover session: {session_id}")
            
            # Get session statistics
            stats = await self.get_session_statistics(site_id, session_id)
            
            # Validate session integrity
            validation = await self.validate_session_integrity(site_id, session_id)
            
            # Get all valid mappings
            mappings = await self.get_all_mappings_for_session(site_id, session_id)
            
            recovery_result = {
                'site_id': str(site_id),
                'session_id': session_id,
                'recoverable': validation['is_valid'],
                'statistics': stats,
                'validation': validation,
                'mappings': mappings,
                'recovery_time': datetime.utcnow().isoformat()
            }
            
            if validation['is_valid']:
                logger.success(f"Session {session_id} is recoverable with {len(mappings)} mappings")
            else:
                logger.warning(f"Session {session_id} has integrity issues: {len(validation['issues'])} problems found")
            
            return recovery_result
            
        except Exception as e:
            logger.error(f"Error recovering session {session_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "recover_session")

    async def get_site_mapping_statistics(self, site_id: UUID) -> Dict[str, Any]:
        """
        Get comprehensive mapping statistics for a site.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary with site-wide statistics
            
        Raises:
            HarrisMatrixServiceError: If statistics retrieval fails
        """
        try:
            logger.debug(f"Getting site mapping statistics for: {site_id}")
            
            # Get site-wide statistics
            stats_query = text("""
                SELECT 
                    status,
                    COUNT(*) as count,
                    COUNT(DISTINCT session_id) as unique_sessions,
                    COUNT(DISTINCT user_id) as unique_users
                FROM harris_matrix_mappings
                WHERE site_id = :site_id
                GROUP BY status
            """)
            
            result = await self.db.execute(stats_query, {"site_id": str(site_id)})
            
            status_counts = {}
            total_sessions = set()
            total_users = set()
            
            for row in result:
                status_counts[row.status] = {
                    'count': row.count,
                    'sessions': row.unique_sessions,
                    'users': row.unique_users
                }
                total_sessions.add(row.unique_sessions)
                total_users.add(row.unique_users)
            
            # Get total counts
            total_query = text("""
                SELECT 
                    COUNT(*) as total_mappings,
                    COUNT(DISTINCT session_id) as total_sessions,
                    COUNT(DISTINCT user_id) as total_users,
                    MIN(created_at) as earliest_created,
                    MAX(created_at) as latest_created
                FROM harris_matrix_mappings
                WHERE site_id = :site_id
            """)
            
            total_result = await self.db.execute(total_query, {"site_id": str(site_id)})
            total_stats = total_result.fetchone()
            
            statistics = {
                'site_id': str(site_id),
                'total_mappings': total_stats.total_mappings or 0,
                'total_sessions': total_stats.total_sessions or 0,
                'total_users': total_stats.total_users or 0,
                'status_breakdown': status_counts,
                'earliest_created': total_stats.earliest_created.isoformat() if total_stats.earliest_created else None,
                'latest_created': total_stats.latest_created.isoformat() if total_stats.latest_created else None
            }
            
            logger.debug(f"Site statistics retrieved: {statistics}")
            return statistics
            
        except Exception as e:
            logger.error(f"Error getting site statistics for {site_id}: {str(e)}", exc_info=True)
            raise HarrisMatrixServiceError(str(e), "get_site_mapping_statistics")