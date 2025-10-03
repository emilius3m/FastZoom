"""Service for ICCD hierarchy validation and management.

This service enforces the hierarchical rules for ICCD card creation:
- SI (Sito Archeologico): Only one per site, serves as foundation
- CA (Complessi Archeologici) & MA (Monumenti Archeologici): Can only be created if SI exists
- RA (Reperti Archeologici): Can have CA, MA, or SI as parent - must have a parent
"""

from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.models.iccd_records import ICCDBaseRecord
from app.models.sites import ArchaeologicalSite
from app.exceptions import BusinessLogicError


class ICCDHierarchyService:
    """Service for managing ICCD card hierarchy validation and operations."""
    
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session
    
    async def validate_card_creation(
        self, 
        site_id: UUID, 
        schema_type: str, 
        parent_id: Optional[UUID] = None
    ) -> Tuple[bool, str]:
        """
        Validate if a card can be created according to hierarchy rules.
        
        Args:
            site_id: Site where the card will be created
            schema_type: Type of card to create (SI, CA, MA, RA)
            parent_id: Optional parent card ID
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Rule 1: SI can only be created once per site
            if schema_type == 'SI':
                return await self._validate_si_creation(site_id)
            
            # Rule 2: CA and MA require an existing SI
            elif schema_type in ['CA', 'MA']:
                return await self._validate_ca_ma_creation(site_id)
            
            # Rule 3: RA must have a parent (SI, CA, or MA)
            elif schema_type == 'RA':
                return await self._validate_ra_creation(site_id, parent_id)
            
            # Other schema types (SAS, NU, TMA, AT) follow standard rules
            else:
                return await self._validate_other_schema_creation(site_id, schema_type, parent_id)
                
        except Exception as e:
            logger.error(f"Error validating card creation: {e}")
            return False, f"Errore validazione gerarchia: {str(e)}"
    
    async def _validate_si_creation(self, site_id: UUID) -> Tuple[bool, str]:
        """Validate SI card creation - only one per site allowed."""
        
        # Check if SI already exists for this site
        query = select(func.count(ICCDBaseRecord.id)).where(
            and_(
                ICCDBaseRecord.site_id == site_id,
                ICCDBaseRecord.schema_type == 'SI'
            )
        )
        
        result = await self.db_session.execute(query)
        si_count = result.scalar()
        
        if si_count > 0:
            return False, "È possibile creare solo una Scheda SI (Sito Archeologico) per ogni sito"
        
        return True, ""
    
    async def _validate_ca_ma_creation(self, site_id: UUID) -> Tuple[bool, str]:
        """Validate CA/MA card creation - requires existing SI."""
        
        # Check if SI exists for this site
        query = select(func.count(ICCDBaseRecord.id)).where(
            and_(
                ICCDBaseRecord.site_id == site_id,
                ICCDBaseRecord.schema_type == 'SI'
            )
        )
        
        result = await self.db_session.execute(query)
        si_count = result.scalar()
        
        if si_count == 0:
            return False, "È necessario creare prima la Scheda SI (Sito Archeologico)"
        
        return True, ""
    
    async def _validate_ra_creation(self, site_id: UUID, parent_id: Optional[UUID]) -> Tuple[bool, str]:
        """Validate RA card creation - must have a valid parent."""
        
        if not parent_id:
            return False, "Le schede RA (Reperti Archeologici) devono avere un padre (SI, CA o MA)"
        
        # Check if parent exists and is valid type
        query = select(ICCDBaseRecord).where(
            and_(
                ICCDBaseRecord.id == parent_id,
                ICCDBaseRecord.site_id == site_id,
                ICCDBaseRecord.schema_type.in_(['SI', 'CA', 'MA'])
            )
        )
        
        result = await self.db_session.execute(query)
        parent = result.scalar_one_or_none()
        
        if not parent:
            return False, "Padre non trovato o tipo non valido. Le schede RA possono avere come padre solo SI, CA o MA"
        
        return True, ""
    
    async def _validate_other_schema_creation(
        self, 
        site_id: UUID, 
        schema_type: str, 
        parent_id: Optional[UUID]
    ) -> Tuple[bool, str]:
        """Validate creation of other schema types (SAS, NU, TMA, AT)."""
        
        # For other schema types, if parent_id is provided, validate it exists
        if parent_id:
            query = select(ICCDBaseRecord).where(
                and_(
                    ICCDBaseRecord.id == parent_id,
                    ICCDBaseRecord.site_id == site_id
                )
            )
            
            result = await self.db_session.execute(query)
            parent = result.scalar_one_or_none()
            
            if not parent:
                return False, f"Padre specificato non trovato per scheda {schema_type}"
        
        return True, ""
    
    async def get_possible_parents(self, site_id: UUID, schema_type: str) -> List[Dict[str, Any]]:
        """
        Get list of possible parent cards for a given schema type.
        
        Args:
            site_id: Site ID
            schema_type: Type of card being created
            
        Returns:
            List of possible parent cards with their details
        """
        try:
            if schema_type == 'SI':
                # SI cards have no parents
                return []
            
            elif schema_type in ['CA', 'MA']:
                # CA and MA can only have SI as parent (implicit, no direct parent_id)
                # But we return SI for reference
                query = select(ICCDBaseRecord).where(
                    and_(
                        ICCDBaseRecord.site_id == site_id,
                        ICCDBaseRecord.schema_type == 'SI'
                    )
                )
                
            elif schema_type == 'RA':
                # RA can have SI, CA, or MA as parent
                query = select(ICCDBaseRecord).where(
                    and_(
                        ICCDBaseRecord.site_id == site_id,
                        ICCDBaseRecord.schema_type.in_(['SI', 'CA', 'MA'])
                    )
                )
                
            else:
                # Other types can have any existing card as parent
                query = select(ICCDBaseRecord).where(
                    ICCDBaseRecord.site_id == site_id
                )
            
            result = await self.db_session.execute(query)
            parents = result.scalars().all()
            
            return [
                {
                    "id": str(parent.id),
                    "nct": parent.get_nct(),
                    "schema_type": parent.schema_type,
                    "object_name": parent.get_object_name(),
                    "status": parent.status,
                    "created_at": parent.created_at.isoformat() if parent.created_at else None
                }
                for parent in parents
            ]
            
        except Exception as e:
            logger.error(f"Error getting possible parents: {e}")
            return []
    
    async def get_hierarchy_tree(self, site_id: UUID) -> Dict[str, Any]:
        """
        Get the complete hierarchy tree for a site.
        
        Args:
            site_id: Site ID
            
        Returns:
            Hierarchical tree structure of all cards
        """
        try:
            # Get all records for the site
            query = select(ICCDBaseRecord).where(
                ICCDBaseRecord.site_id == site_id
            ).order_by(ICCDBaseRecord.created_at)
            
            result = await self.db_session.execute(query)
            records = result.scalars().all()
            
            # Build hierarchy tree
            tree = {
                "site_id": str(site_id),
                "total_records": len(records),
                "hierarchy": []
            }
            
            # Create record lookup
            record_dict = {str(record.id): record for record in records}
            
            # Find root records (no parent)
            root_records = [r for r in records if r.parent_id is None]
            
            def build_node(record):
                """Build a tree node with children."""
                node = {
                    "id": str(record.id),
                    "nct": record.get_nct(),
                    "schema_type": record.schema_type,
                    "object_name": record.get_object_name(),
                    "status": record.status,
                    "level": record.level,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "children": []
                }
                
                # Find children
                children = [r for r in records if r.parent_id == record.id]
                for child in children:
                    node["children"].append(build_node(child))
                
                return node
            
            # Build tree from root records
            for root in root_records:
                tree["hierarchy"].append(build_node(root))
            
            return tree
            
        except Exception as e:
            logger.error(f"Error building hierarchy tree: {e}")
            return {
                "site_id": str(site_id),
                "total_records": 0,
                "hierarchy": [],
                "error": str(e)
            }
    
    async def validate_hierarchy_integrity(self, site_id: UUID) -> Dict[str, Any]:
        """
        Validate the integrity of the ICCD hierarchy for a site.
        
        Args:
            site_id: Site ID to validate
            
        Returns:
            Validation result with any issues found
        """
        try:
            issues = []
            warnings = []
            
            # Get all records for the site
            query = select(ICCDBaseRecord).where(
                ICCDBaseRecord.site_id == site_id
            )
            
            result = await self.db_session.execute(query)
            records = result.scalars().all()
            
            # Check SI requirements
            si_records = [r for r in records if r.schema_type == 'SI']
            if len(si_records) == 0:
                issues.append("Nessuna scheda SI trovata. È necessario creare una Scheda Sito Archeologico")
            elif len(si_records) > 1:
                issues.append(f"Trovate {len(si_records)} schede SI. È consentita solo una scheda SI per sito")
            
            # Check CA/MA requirements
            ca_ma_records = [r for r in records if r.schema_type in ['CA', 'MA']]
            if ca_ma_records and len(si_records) == 0:
                issues.append("Schede CA/MA presenti senza scheda SI. Creare prima la scheda SI")
            
            # Check RA requirements
            ra_records = [r for r in records if r.schema_type == 'RA']
            for ra in ra_records:
                if not ra.parent_id:
                    issues.append(f"Scheda RA {ra.get_nct()} senza padre. Le schede RA devono avere un padre")
                else:
                    # Check if parent exists and is valid type
                    parent = next((r for r in records if r.id == ra.parent_id), None)
                    if not parent:
                        issues.append(f"Scheda RA {ra.get_nct()} ha un padre inesistente")
                    elif parent.schema_type not in ['SI', 'CA', 'MA']:
                        issues.append(f"Scheda RA {ra.get_nct()} ha un padre di tipo non valido ({parent.schema_type})")
            
            # Check for orphaned records (parent doesn't exist)
            for record in records:
                if record.parent_id:
                    parent = next((r for r in records if r.id == record.parent_id), None)
                    if not parent:
                        issues.append(f"Scheda {record.get_nct()} ha un padre inesistente")
            
            # Generate warnings for potential issues
            if len(records) == 0:
                warnings.append("Nessuna scheda ICCD presente nel sito")
            
            return {
                "site_id": str(site_id),
                "is_valid": len(issues) == 0,
                "total_records": len(records),
                "issues": issues,
                "warnings": warnings,
                "record_counts": {
                    "SI": len([r for r in records if r.schema_type == 'SI']),
                    "CA": len([r for r in records if r.schema_type == 'CA']),
                    "MA": len([r for r in records if r.schema_type == 'MA']),
                    "RA": len([r for r in records if r.schema_type == 'RA']),
                    "Other": len([r for r in records if r.schema_type not in ['SI', 'CA', 'MA', 'RA']])
                }
            }
            
        except Exception as e:
            logger.error(f"Error validating hierarchy integrity: {e}")
            return {
                "site_id": str(site_id),
                "is_valid": False,
                "total_records": 0,
                "issues": [f"Errore validazione: {str(e)}"],
                "warnings": [],
                "record_counts": {}
            }
    
    async def get_creation_options(self, site_id: UUID) -> Dict[str, Any]:
        """
        Get available card creation options based on current hierarchy state.
        
        Args:
            site_id: Site ID
            
        Returns:
            Available creation options with constraints
        """
        try:
            # Get current hierarchy status
            validation = await self.validate_hierarchy_integrity(site_id)
            
            options = {
                "site_id": str(site_id),
                "available_types": [],
                "recommendations": []
            }
            
            # Determine what can be created
            si_count = validation["record_counts"].get("SI", 0)
            
            if si_count == 0:
                # No SI exists - only SI can be created
                options["available_types"].append({
                    "type": "SI",
                    "name": "Scheda Sito Archeologico",
                    "description": "Scheda base del sito archeologico",
                    "requires_parent": False,
                    "constraint": "Prima scheda obbligatoria"
                })
                options["recommendations"].append("Creare prima la Scheda SI (Sito Archeologico)")
                
            elif si_count == 1:
                # SI exists - can create CA, MA, RA
                options["available_types"].extend([
                    {
                        "type": "CA",
                        "name": "Scheda Complesso Archeologico",
                        "description": "Per complessi archeologici multi-unitari",
                        "requires_parent": False,
                        "constraint": "Richiede scheda SI esistente"
                    },
                    {
                        "type": "MA",
                        "name": "Scheda Monumento Archeologico",
                        "description": "Per singoli monumenti architettonici",
                        "requires_parent": False,
                        "constraint": "Richiede scheda SI esistente"
                    },
                    {
                        "type": "RA",
                        "name": "Scheda Reperto Archeologico",
                        "description": "Per reperti mobili",
                        "requires_parent": True,
                        "constraint": "Richiede un padre (SI, CA o MA)"
                    }
                ])
                
                # Get possible parents for RA
                possible_parents = await self.get_possible_parents(site_id, "RA")
                if possible_parents:
                    options["possible_parents"] = possible_parents
                    # Non mostrare raccomandazione se ci sono padri disponibili
                # La raccomandazione "nessun padre" viene gestita dal frontend quando l'utente seleziona RA
                    
            else:
                # Multiple SI - error state
                options["recommendations"].append("ERRORE: Multiple schede SI presenti. Correggere prima questa situazione")
            
            return options
            
        except Exception as e:
            logger.error(f"Error getting creation options: {e}")
            return {
                "site_id": str(site_id),
                "available_types": [],
                "recommendations": [f"Errore: {str(e)}"]
            }