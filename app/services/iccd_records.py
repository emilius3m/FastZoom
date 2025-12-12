"""Service for ICCD record operations."""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import ArchaeologicalSite, UserSitePermission, User
from app.repositories.iccd_records import ICCDRecordRepository
from app.exceptions import BusinessLogicError


class ICCDRecordService:
    """Service for ICCD record operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
        self.repository = ICCDRecordRepository(db_session)

    async def check_site_access(self, site_id: UUID, current_user_id: UUID) -> tuple[ArchaeologicalSite, UserSitePermission]:
        """Check if user has access to the site for ICCD operations."""
        from sqlalchemy import select, and_, or_, func
        from app.models.sites import ArchaeologicalSite
        from app.models import UserSitePermission
        
        # Check site existence - Convert UUID to string for DB comparison
        site_query = select(ArchaeologicalSite).where(ArchaeologicalSite.id == str(site_id))
        site_result = await self.db_session.execute(site_query)
        site = site_result.scalar_one_or_none()
        
        if not site:
            raise BusinessLogicError("Sito archeologico non trovato", 404)
        
        # Check user permissions - Convert UUIDs to strings for DB comparison
        permission_query = select(UserSitePermission).where(
            and_(
                UserSitePermission.user_id == str(current_user_id),
                UserSitePermission.site_id == str(site_id),
                UserSitePermission.is_active == True,
                or_(
                    UserSitePermission.expires_at.is_(None),
                    UserSitePermission.expires_at > func.now()
                )
            )
        )
        
        permission = await self.db_session.execute(permission_query)
        permission = permission.scalar_one_or_none()
        
        if not permission:
            raise BusinessLogicError("Non hai i permessi per accedere a questo sito archeologico", 403)
        
        return site, permission

    async def get_site_records(
        self, 
        site_id: UUID, 
        current_user_id: UUID,
        schema_type: Optional[str] = None,
        level: Optional[str] = None,
        status: Optional[str] = None,
        is_validated: Optional[bool] = None,
        page: int = 1,
        size: int = 20
    ) -> Dict[str, Any]:
        """Get all ICCD records for a site with optional filters."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        skip = (page - 1) * size
        records, total = await self.repository.get_site_records(
            site_id, schema_type, level, status, is_validated, skip, size
        )
        
        # Prepare records data
        records_data = []
        for record in records:
            record_dict = record.to_dict()
            # Add user information
            if record.creator:
                record_dict["creator_name"] = record.creator.display_name
            if record.validator:
                record_dict["validator_name"] = record.validator.display_name
            records_data.append(record_dict)
        
        return {
            "site_id": str(site_id),
            "records": records_data,
            "pagination": {
                "page": page,
                "size": size,
                "total": total,
                "pages": (total + size - 1) // size
            },
            "filters": {
                "schema_type": schema_type,
                "level": level,
                "status": status,
                "is_validated": is_validated
            }
        }

    async def create_record(self, site_id: UUID, record_data: Dict[str, Any], current_user_id: UUID) -> Dict[str, Any]:
        """Create a new ICCD record."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        try:
            # Log the data received for debugging
            logger.info(f"Creating ICCD record for site {site_id} by user {current_user_id}")
            logger.info(f"Record data keys: {list(record_data.keys())}")
            logger.info(f"Full record data: {record_data}")

            # Validate required fields
            required_fields = ['schema_type', 'level', 'iccd_data']
            for field in required_fields:
                if field not in record_data:
                    logger.error(f"Missing required field: {field}")
                    logger.error(f"Available fields: {list(record_data.keys())}")
                    raise BusinessLogicError(f"Campo obbligatorio mancante: {field}", 400)
            
            # HIERARCHY VALIDATION - Check if card can be created according to ICCD rules
            from app.services.iccd_hierarchy_service import ICCDHierarchyService
            hierarchy_service = ICCDHierarchyService(self.db_session)
            
            schema_type = record_data['schema_type']
            parent_id_str = record_data.get('parent_id')
            
            # Convert parent_id to UUID if provided
            parent_id = None
            if parent_id_str:
                try:
                    parent_id = UUID(parent_id_str)
                    logger.info(f"Parent ID parsed: {parent_id}")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid parent_id format: {parent_id_str}, error: {e}")
                    raise BusinessLogicError(f"Formato parent_id non valido: {parent_id_str}", 400)
            
            is_valid, error_message = await hierarchy_service.validate_card_creation(
                site_id, schema_type, parent_id
            )
            
            if not is_valid:
                raise BusinessLogicError(error_message, 400)
            
            # Extract cataloging_institution from ICCD data if not provided separately
            cataloging_institution = record_data.get('cataloging_institution')
            if not cataloging_institution:
                cataloging_institution = record_data.get('iccd_data', {}).get('CD', {}).get('ESC')
                if not cataloging_institution:
                    cataloging_institution = 'SSABAP-RM'  # Default fallback
                    logger.info(f"Using default cataloging institution: {cataloging_institution}")

            # Additional validation of ICCD data
            if not isinstance(record_data['iccd_data'], dict):
                raise BusinessLogicError("iccd_data deve essere un oggetto JSON", 400)
            
            # Generate NCT if not provided
            nct_data = record_data.get('iccd_data', {}).get('CD', {}).get('NCT', {})
            
            if not nct_data.get('NCTR'):
                nct_data['NCTR'] = '12'  # Default Lazio for Domus Flavia
            
            if not nct_data.get('NCTN'):
                # Generate sequential number based on timestamp
                now = datetime.utcnow()
                year = now.year % 100  # Last 2 digits of year
                sequence = now.microsecond % 1000000  # Microseconds for uniqueness
                nct_data['NCTN'] = f"{year:02d}{sequence:06d}"
            
            # Check NCT uniqueness
            nct_exists = await self.repository.check_nct_exists(
                nct_data['NCTR'], 
                nct_data['NCTN'], 
                nct_data.get('NCTS')
            )
            
            if nct_exists:
                raise BusinessLogicError("Codice NCT già esistente", 400)
            
            # Update ICCD data with generated NCT
            record_data['iccd_data']['CD']['NCT'] = nct_data
            
            # Update ICCD data with cataloging institution, cataloger name and survey date
            iccd_data = record_data['iccd_data'].copy()
            if 'CD' not in iccd_data:
                iccd_data['CD'] = {}
            if 'ESC' not in iccd_data['CD']:
                iccd_data['CD']['ESC'] = cataloging_institution
            
            # Add cataloger and survey date if provided (either as separate fields or in ICCD data)
            cataloger_name = record_data.get('cataloger_name') or iccd_data.get('CD', {}).get('RCG', {}).get('RCGR')
            survey_date = record_data.get('survey_date') or iccd_data.get('CD', {}).get('RCG', {}).get('RCGD')
            
            if cataloger_name or survey_date:
                if 'RCG' not in iccd_data['CD']:
                    iccd_data['CD']['RCG'] = {}
                if cataloger_name:
                    iccd_data['CD']['RCG']['RCGR'] = cataloger_name
                if survey_date:
                    # Convert datetime to ISO format string for storage
                    if isinstance(survey_date, str):
                        iccd_data['CD']['RCG']['RCGD'] = survey_date
                    else:
                        iccd_data['CD']['RCG']['RCGD'] = survey_date.isoformat()
            
            # Prepare record data for creation - convert UUIDs to strings for SQLite compatibility
            record = {
                "nct_region": nct_data['NCTR'],
                "nct_number": nct_data['NCTN'],
                "nct_suffix": nct_data.get('NCTS'),
                "schema_type": record_data['schema_type'],
                "level": record_data['level'],
                "iccd_data": iccd_data,
                "site_id": str(site_id),
                "created_by": str(current_user_id),
                "parent_id": str(parent_id) if parent_id else None
            }
            
            logger.info(f"Step 1: Prepared record data: {record.keys()}")
            
            try:
                new_record = await self.repository.create_record(record)
                logger.info(f"Step 2: Record created in repository, id: {new_record.id}")
            except Exception as repo_err:
                logger.error(f"Error in repository.create_record: {repo_err}", exc_info=True)
                raise
            
            try:
                await self.db_session.commit()
                logger.info(f"Step 3: Session committed successfully")
            except Exception as commit_err:
                logger.error(f"Error in session.commit: {commit_err}", exc_info=True)
                raise
            
            try:
                nct_str = new_record.get_nct()
                logger.info(f"Step 4: Got NCT: {nct_str}")
            except Exception as nct_err:
                logger.error(f"Error getting NCT: {nct_err}", exc_info=True)
                nct_str = "ERROR"
            
            logger.info(f"ICCD record created: {nct_str} for site {site_id}")
            
            try:
                record_dict = new_record.to_dict()
                logger.info(f"Step 5: to_dict() successful")
            except Exception as dict_err:
                logger.error(f"Error in to_dict(): {dict_err}", exc_info=True)
                raise
            
            return {
                "message": "Scheda ICCD creata con successo",
                "record_id": str(new_record.id),
                "nct": nct_str,
                "record": record_dict
            }
            
        except BusinessLogicError:
            raise
        except Exception as e:
            logger.error(f"Error creating ICCD record: {e}", exc_info=True)
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore creazione scheda ICCD: {str(e)}", 500)

    async def get_record_by_id(self, site_id: UUID, record_id: UUID, current_user_id: UUID) -> Dict[str, Any]:
        """Get a specific ICCD record by ID."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        record = await self.repository.get_record_by_id(record_id, site_id)
        
        if not record:
            raise BusinessLogicError("Scheda ICCD non trovata", 404)
        
        record_data = record.to_dict()
        
        # Add user information
        if record.creator:
            record_data["creator_name"] = record.creator.display_name
        if record.validator:
            record_data["validator_name"] = record.validator.display_name
        
        return record_data

    async def update_record(self, site_id: UUID, record_id: UUID, record_data: Dict[str, Any], current_user_id: UUID) -> Dict[str, Any]:
        """Update an existing ICCD record."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_write():
            raise BusinessLogicError("Permessi di scrittura richiesti", 403)
        
        # Get the record
        record = await self.repository.get_record_by_id(record_id, site_id)
        
        if not record:
            raise BusinessLogicError("Scheda ICCD non trovata", 404)
        
        try:
            # Updatable fields
            updatable_fields = [
                'level', 'iccd_data',
                'status', 'validation_notes'
            ]
            
            for field in updatable_fields:
                if field in record_data:
                    value = record_data[field]
                    
                    # Handle special fields
                    if field == 'cataloger_name':
                        # Update cataloger in ICCD data
                        if 'CD' not in record.iccd_data:
                            record.iccd_data['CD'] = {}
                        if 'RCG' not in record.iccd_data['CD']:
                            record.iccd_data['CD']['RCG'] = {}
                        record.iccd_data['CD']['RCG']['RCGR'] = value
                    elif field == 'cataloging_institution':
                        # Update cataloging institution in ICCD data
                        if 'CD' not in record.iccd_data:
                            record.iccd_data['CD'] = {}
                        record.iccd_data['CD']['ESC'] = value
                    elif field == 'survey_date':
                        # Update survey date in ICCD data
                        if 'CD' not in record.iccd_data:
                            record.iccd_data['CD'] = {}
                        if 'RCG' not in record.iccd_data['CD']:
                            record.iccd_data['CD']['RCG'] = {}
                        
                        if value:
                            # Convert datetime to ISO format string for storage
                            if isinstance(value, str):
                                record.iccd_data['CD']['RCG']['RCGD'] = value
                            else:
                                record.iccd_data['CD']['RCG']['RCGD'] = value.isoformat()
                        else:
                            # Remove date if None
                            if 'RCGD' in record.iccd_data['CD']['RCG']:
                                del record.iccd_data['CD']['RCG']['RCGD']
                    else:
                        setattr(record, field, value)
            
            record.updated_at = datetime.utcnow()
            
            await self.db_session.commit()
            
            return {
                "message": "Scheda ICCD aggiornata con successo",
                "record": record.to_dict()
            }
            
        except Exception as e:
            logger.error(f"Error updating ICCD record: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore aggiornamento scheda: {str(e)}", 500)

    async def delete_record(self, site_id: UUID, record_id: UUID, current_user_id: UUID) -> Dict[str, Any]:
        """Delete an ICCD record."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_admin():  # Only admin can delete
            raise BusinessLogicError("Permessi di amministratore richiesti per eliminare schede", 403)
        
        # Get the record
        record = await self.repository.get_record_by_id(record_id, site_id)
        
        if not record:
            raise BusinessLogicError("Scheda ICCD non trovata", 404)
        
        try:
            # Store record info for response
            nct = record.get_nct()
            object_name = record.get_object_name()
            
            # Delete the record
            await self.repository.delete_record(record)
            await self.db_session.commit()
            
            logger.info(f"ICCD record deleted: {nct} from site {site_id} by user {current_user_id}")
            
            return {
                "message": f"Scheda ICCD {nct} eliminata con successo",
                "deleted_record": {
                    "id": str(record_id),
                    "nct": nct,
                    "object_name": object_name
                }
            }
            
        except Exception as e:
            logger.error(f"Error deleting ICCD record: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore eliminazione scheda: {str(e)}", 500)

    async def validate_record(self, site_id: UUID, record_id: UUID, validation_data: Dict[str, Any],
                            current_user_id: UUID) -> Dict[str, Any]:
        """Validate an ICCD record."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_admin():  # Only admin can validate
            raise BusinessLogicError("Permessi di amministratore richiesti per validazione", 403)
        
        # Get the record
        record = await self.repository.get_record_by_id(record_id, site_id)
        
        if not record:
            raise BusinessLogicError("Scheda ICCD non trovata", 404)
        
        try:
            # Check completeness for level
            is_complete, missing_sections = record.is_complete_for_level()
            
            if not is_complete:
                raise BusinessLogicError(
                    f"Scheda incompleta per livello {record.level}. Sezioni mancanti: {', '.join(missing_sections)}", 
                    400
                )
            
            # Update validation
            is_valid = validation_data.get('is_valid', True)
            record.validation_date = datetime.utcnow()
            record.validated_by = current_user_id
            record.validation_notes = validation_data.get('notes')
            
            # Set appropriate status based on validation
            record.status = 'validated' if is_valid else 'draft'
            
            await self.db_session.commit()
            
            logger.info(f"ICCD record validated: {record.get_nct()} by user {current_user_id}")
            
            return {
                "message": "Scheda ICCD validata con successo",
                "record": record.to_dict()
            }
            
        except BusinessLogicError:
            raise
        except Exception as e:
            logger.error(f"Error validating ICCD record: {e}")
            await self.db_session.rollback()
            raise BusinessLogicError(f"Errore validazione scheda: {str(e)}", 500)

    async def get_schema_templates(self, current_user_id: UUID,
                                 schema_type: Optional[str] = None,
                                 category: Optional[str] = None) -> Dict[str, Any]:
        """Get available ICCD schemas templates from Python code."""
        # Verify user exists - convert UUID to string for DB comparison
        from sqlalchemy import select
        from app.models import User
        user_query = select(User).where(User.id == str(current_user_id))
        user_result = await self.db_session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise BusinessLogicError("Utente non trovato", 404)
        
        # Get templates from Python code
        from app.services.iccd_integration_service import ICCD_TEMPLATES
        
        templates_data = []
        for schema_key, template_data in ICCD_TEMPLATES.items():
            # Apply filters if provided
            if schema_type and schema_key != schema_type.upper():
                continue
            if category and template_data.get("category") != category:
                continue
                
            templates_data.append({
                "id": f"iccd_{schema_key.lower()}",
                "schema_type": schema_key,
                "name": template_data["name"],
                "description": template_data["description"],
                "version": "3.00",
                "category": template_data["category"],
                "icon": template_data["icon"],
                "is_active": True,
                "standard_compliant": True,
                "json_schema": template_data["schemas"],
                "ui_schema": template_data["ui_schema"]
            })
        
        return {
            "templates": templates_data,
            "total": len(templates_data)
        }

    async def get_schema_template_by_type(self, current_user_id: UUID, schema_type: str) -> Dict[str, Any]:
        """Get a specific ICCD schemas template by type from Python code."""
        # Verify user exists - convert UUID to string for DB comparison
        from sqlalchemy import select
        from app.models import User
        user_query = select(User).where(User.id == str(current_user_id))
        user_result = await self.db_session.execute(user_query)
        user = user_result.scalar_one_or_none()
        
        if not user:
            raise BusinessLogicError("Utente non trovato", 404)
        
        # Get template from Python code
        from app.services.iccd_integration_service import get_template_by_type
        
        template_data = get_template_by_type(schema_type)
        
        if not template_data:
            raise BusinessLogicError("Template schemas ICCD non trovato", 404)
        
        return {
            "id": f"iccd_{schema_type.lower()}",
            "schema_type": schema_type,
            "name": template_data["name"],
            "description": template_data["description"],
            "version": "3.00",
            "category": template_data["category"],
            "icon": template_data["icon"],
            "is_active": True,
            "standard_compliant": True,
            "json_schema": template_data["schemas"],
            "ui_schema": template_data["ui_schema"]
        }

    async def get_record_statistics(self, site_id: UUID, current_user_id: UUID) -> Dict[str, Any]:
        """Get statistics for ICCD records in a site."""
        site, permission = await self.check_site_access(site_id, current_user_id)
        
        if not permission.can_read():
            raise BusinessLogicError("Permessi di lettura richiesti", 403)
        
        stats = await self.repository.get_record_statistics(site_id)
        
        return {
            "site_id": str(site_id),
            "statistics": stats
        }