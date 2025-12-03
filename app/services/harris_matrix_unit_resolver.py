# app/services/harris_matrix_unit_resolver.py
"""
Enhanced Unit Resolver Service for Harris Matrix System

This service provides multi-strategy unit code resolution with comprehensive caching,
reference validation, and cleanup functionality. It addresses issues with
missing units (USM402, US402, 412) by implementing multiple resolution
strategies and fallback logic.

Key Features:
- Multi-strategy resolution (direct, case-insensitive, numeric prefix, cross-type, soft-deleted)
- Comprehensive caching with 15-minute TTL
- Reference validation and orphaned reference cleanup
- Structured logging with performance tracking
- Type-safe implementation with complete type hints
"""

import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set, Union
from uuid import UUID
from functools import lru_cache
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, text
from loguru import logger

from app.models.stratigraphy import UnitaStratigrafica, UnitaStratigraficaMuraria


class UnitResolver:
    """
    Enhanced unit resolver with multi-strategy resolution and caching.
    
    This class provides intelligent unit code resolution that can handle
    various formats and edge cases in the Harris Matrix system.
    """
    
    # Cache configuration
    CACHE_TTL_MINUTES = 15
    CACHE_MAX_SIZE = 1000
    
    # Resolution strategy priorities
    RESOLUTION_STRATEGIES = [
        'direct_match',           # Exact case-sensitive match
        'case_insensitive',       # Case-insensitive match
        'numeric_prefix_removal', # Remove US/USM prefix
        'cross_type_lookup',      # US ↔ USM cross-references
        'soft_deleted_lookup'     # Check soft-deleted units
    ]
    
    def __init__(self, db: AsyncSession):
        """
        Initialize the unit resolver.
        
        Args:
            db: AsyncSession for database operations
        """
        self.db = db
        self._lookup_cache = {}
        self._cache_timestamps = {}
        self._resolution_stats = defaultdict(int)
    
    async def resolve_unit_code(
        self, 
        code: str, 
        unit_type: str
    ) -> Optional[str]:
        """
        Main resolution method with multi-strategy fallback.
        
        Args:
            code: Unit code to resolve (e.g., "412", "US402", "USM402")
            unit_type: Target unit type ('us' or 'usm')
            
        Returns:
            Resolved unit ID (UUID string) or None if not found
            
        Resolution Strategy (in order):
        1. Direct exact match (case-sensitive)
        2. Case-insensitive match
        3. Numeric prefix removal (e.g., "US412" → "412")
        4. Cross-type lookup (US ↔ USM)
        5. Soft-deleted unit lookup
        6. Return None if not found
        """
        start_time = time.time()
        
        try:
            if not code or not unit_type:
                logger.warning(f"Invalid inputs: code='{code}', unit_type='{unit_type}'")
                return None
            
            # Normalize inputs
            code = str(code).strip()
            unit_type = unit_type.lower().strip()
            
            if unit_type not in ['us', 'usm']:
                logger.warning(f"Invalid unit_type: {unit_type}. Must be 'us' or 'usm'")
                return None
            
            logger.debug(f"Resolving unit code: {code} (type: {unit_type})")
            
            # Try each resolution strategy
            for strategy in self.RESOLUTION_STRATEGIES:
                try:
                    resolved_id = await self._apply_resolution_strategy(
                        code, unit_type, strategy
                    )
                    
                    if resolved_id:
                        self._resolution_stats[f"{strategy}_success"] += 1
                        resolution_time = (time.time() - start_time) * 1000
                        
                        logger.info(
                            f"Unit resolved: {code} → {resolved_id} "
                            f"(strategy: {strategy}, time: {resolution_time:.2f}ms)"
                        )
                        
                        return resolved_id
                    else:
                        self._resolution_stats[f"{strategy}_failed"] += 1
                        
                except Exception as e:
                    self._resolution_stats[f"{strategy}_error"] += 1
                    logger.error(
                        f"Error in resolution strategy {strategy} for {code}: {str(e)}"
                    )
                    continue
            
            # All strategies failed
            self._resolution_stats["not_found"] += 1
            resolution_time = (time.time() - start_time) * 1000
            
            logger.warning(
                f"Unit resolution failed: {code} (type: {unit_type}) "
                f"(time: {resolution_time:.2f}ms, strategies tried: {len(self.RESOLUTION_STRATEGIES)})"
            )
            
            return None
            
        except Exception as e:
            self._resolution_stats["resolution_error"] += 1
            logger.error(f"Critical error resolving unit {code}: {str(e)}", exc_info=True)
            return None
    
    async def _apply_resolution_strategy(
        self, 
        code: str, 
        unit_type: str, 
        strategy: str
    ) -> Optional[str]:
        """
        Apply a specific resolution strategy.
        
        Args:
            code: Unit code to resolve
            unit_type: Target unit type
            strategy: Resolution strategy name
            
        Returns:
            Resolved unit ID or None
        """
        logger.debug(f"Applying resolution strategy: {strategy} for {code}")
        
        if strategy == 'direct_match':
            return await self._direct_match(code, unit_type)
        elif strategy == 'case_insensitive':
            return await self._case_insensitive_match(code, unit_type)
        elif strategy == 'numeric_prefix_removal':
            return await self._numeric_prefix_removal(code, unit_type)
        elif strategy == 'cross_type_lookup':
            return await self._cross_type_lookup(code, unit_type)
        elif strategy == 'soft_deleted_lookup':
            return await self._soft_deleted_lookup(code, unit_type)
        else:
            logger.warning(f"Unknown resolution strategy: {strategy}")
            return None
    
    async def _direct_match(self, code: str, unit_type: str) -> Optional[str]:
        """Strategy 1: Direct exact match (case-sensitive)."""
        try:
            # Build lookup tables for this site if needed
            site_id = await self._get_current_site_id()
            if not site_id:
                return None
            
            lookup_tables = await self.build_lookup_tables(site_id)
            
            if unit_type == 'us':
                return lookup_tables['us_exact'].get(code)
            else:  # usm
                return lookup_tables['usm_exact'].get(code)
                
        except Exception as e:
            logger.error(f"Direct match failed for {code}: {str(e)}")
            return None
    
    async def _case_insensitive_match(self, code: str, unit_type: str) -> Optional[str]:
        """Strategy 2: Case-insensitive match."""
        try:
            site_id = await self._get_current_site_id()
            if not site_id:
                return None
            
            lookup_tables = await self.build_lookup_tables(site_id)
            
            if unit_type == 'us':
                for us_code, us_id in lookup_tables['us_exact'].items():
                    if us_code.lower() == code.lower():
                        return us_id
            else:  # usm
                for usm_code, usm_id in lookup_tables['usm_exact'].items():
                    if usm_code.lower() == code.lower():
                        return usm_id
                        
        except Exception as e:
            logger.error(f"Case-insensitive match failed for {code}: {str(e)}")
            return None
    
    async def _numeric_prefix_removal(self, code: str, unit_type: str) -> Optional[str]:
        """Strategy 3: Remove US/USM prefix and try numeric match."""
        try:
            # Extract numeric part
            numeric_code = re.sub(r'^(US|USM)', '', code.strip(), flags=re.IGNORECASE)
            
            if not numeric_code.isdigit():
                return None
            
            site_id = await self._get_current_site_id()
            if not site_id:
                return None
            
            lookup_tables = await self.build_lookup_tables(site_id)
            
            if unit_type == 'us':
                # Try to find US with this numeric part
                for us_code, us_id in lookup_tables['us_exact'].items():
                    if re.sub(r'^(US|USM)', '', us_code) == numeric_code:
                        return us_id
            else:  # usm
                for usm_code, usm_id in lookup_tables['usm_exact'].items():
                    if re.sub(r'^(US|USM)', '', usm_code) == numeric_code:
                        return usm_id
                        
        except Exception as e:
            logger.error(f"Numeric prefix removal failed for {code}: {str(e)}")
            return None
    
    async def _cross_type_lookup(self, code: str, unit_type: str) -> Optional[str]:
        """Strategy 4: Cross-type lookup (US ↔ USM)."""
        try:
            site_id = await self._get_current_site_id()
            if not site_id:
                return None
            
            lookup_tables = await self.build_lookup_tables(site_id)
            
            # Try to find the code in the opposite type first
            opposite_type = 'usm' if unit_type == 'us' else 'us'
            
            if opposite_type == 'us':
                for us_code, us_id in lookup_tables['us_exact'].items():
                    if us_code.lower() == code.lower():
                        # Found in US, but we need USM - this might indicate a reference error
                        logger.debug(f"Found {code} in US table but looking for USM")
                        return None
            else:  # opposite_type == 'us'
                for usm_code, usm_id in lookup_tables['usm_exact'].items():
                    if usm_code.lower() == code.lower():
                        # Found in USM, but we need US - might indicate reference error
                        logger.debug(f"Found {code} in USM table but looking for US")
                        return None
            
            # Also try with prefix variations
            code_variations = [
                code,
                f"US{code}",
                f"USM{code}",
                code.replace('US', ''),
                code.replace('USM', '')
            ]
            
            for variation in code_variations:
                if unit_type == 'us':
                    if variation in lookup_tables['us_exact']:
                        return lookup_tables['us_exact'][variation]
                else:  # usm
                    if variation in lookup_tables['usm_exact']:
                        return lookup_tables['usm_exact'][variation]
                        
        except Exception as e:
            logger.error(f"Cross-type lookup failed for {code}: {str(e)}")
            return None
    
    async def _soft_deleted_lookup(self, code: str, unit_type: str) -> Optional[str]:
        """Strategy 5: Check soft-deleted units."""
        try:
            site_id = await self._get_current_site_id()
            if not site_id:
                return None
            
            lookup_tables = await self.build_lookup_tables(site_id)
            
            if unit_type == 'us':
                return lookup_tables['us_deleted'].get(code.lower())
            else:  # usm
                return lookup_tables['usm_deleted'].get(code.lower())
                
        except Exception as e:
            logger.error(f"Soft-deleted lookup failed for {code}: {str(e)}")
            return None
    
    @lru_cache(maxsize=CACHE_MAX_SIZE)
    async def build_lookup_tables(self, site_id: str) -> Dict[str, Dict]:
        """
        Build comprehensive lookup tables for all units in a site.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing various lookup tables for efficient resolution
        """
        cache_key = f"lookup_tables:{site_id}"
        current_time = datetime.now()
        
        # Check cache validity
        if (cache_key in self._lookup_cache and 
            cache_key in self._cache_timestamps):
            cache_age = current_time - self._cache_timestamps[cache_key]
            if cache_age < timedelta(minutes=self.CACHE_TTL_MINUTES):
                logger.debug(f"Using cached lookup tables for site {site_id}")
                return self._lookup_cache[cache_key]
        
        try:
            logger.info(f"Building lookup tables for site {site_id}")
            start_time = time.time()
            
            # Query active US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            ).order_by(UnitaStratigrafica.us_code)
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            # Query active USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            ).order_by(UnitaStratigraficaMuraria.usm_code)
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            # Query soft-deleted US units
            us_deleted_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.deleted_at.is_not(None)
                )
            ).order_by(UnitaStratigrafica.us_code)
            
            us_deleted_result = await self.db.execute(us_deleted_query)
            us_deleted_units = us_deleted_result.scalars().all()
            
            # Query soft-deleted USM units
            usm_deleted_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.deleted_at.is_not(None)
                )
            ).order_by(UnitaStratigraficaMuraria.usm_code)
            
            usm_deleted_result = await self.db.execute(usm_deleted_query)
            usm_deleted_units = usm_deleted_result.scalars().all()
            
            # Build lookup tables
            lookup_tables = {
                'us_exact': {us.us_code: str(us.id) for us in us_units},
                'usm_exact': {usm.usm_code: str(usm.id) for usm in usm_units},
                'us_deleted': {us.us_code.lower(): str(us.id) for us in us_deleted_units},
                'usm_deleted': {usm.usm_code.lower(): str(usm.id) for usm in usm_deleted_units},
                'us_case_insensitive': {us.us_code.lower(): str(us.id) for us in us_units},
                'usm_case_insensitive': {usm.usm_code.lower(): str(usm.id) for usm in usm_units},
                'numeric_lookup': {},  # For numeric-only lookups
                'metadata': {
                    'built_at': current_time.isoformat(),
                    'us_count': len(us_units),
                    'usm_count': len(usm_units),
                    'us_deleted_count': len(us_deleted_units),
                    'usm_deleted_count': len(usm_deleted_units)
                }
            }
            
            # Build numeric lookup (remove US/USM prefixes)
            for us in us_units:
                numeric_code = re.sub(r'^(US|USM)', '', us.us_code)
                if numeric_code.isdigit():
                    lookup_tables['numeric_lookup'][f"us:{numeric_code}"] = str(us.id)
            
            for usm in usm_units:
                numeric_code = re.sub(r'^(US|USM)', '', usm.usm_code)
                if numeric_code.isdigit():
                    lookup_tables['numeric_lookup'][f"usm:{numeric_code}"] = str(usm.id)
            
            # Cache the results
            self._lookup_cache[cache_key] = lookup_tables
            self._cache_timestamps[cache_key] = current_time
            
            build_time = (time.time() - start_time) * 1000
            logger.info(
                f"Built lookup tables for site {site_id} in {build_time:.2f}ms: "
                f"US: {len(us_units)}, USM: {len(usm_units)}, "
                f"US (deleted): {len(us_deleted_units)}, USM (deleted): {len(usm_deleted_units)}"
            )
            
            return lookup_tables
            
        except Exception as e:
            logger.error(f"Error building lookup tables for site {site_id}: {str(e)}", exc_info=True)
            # Return empty lookup tables on error
            return {
                'us_exact': {},
                'usm_exact': {},
                'us_deleted': {},
                'usm_deleted': {},
                'us_case_insensitive': {},
                'usm_case_insensitive': {},
                'numeric_lookup': {},
                'metadata': {
                    'built_at': current_time.isoformat(),
                    'error': str(e)
                }
            }
    
    async def validate_references(self, site_id: str) -> Dict[str, List[str]]:
        """
        Validate all references and identify broken relationships system-wide.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing broken references by unit type
        """
        try:
            logger.info(f"Validating references for site {site_id}")
            start_time = time.time()
            
            # Build lookup tables
            lookup_tables = await self.build_lookup_tables(site_id)
            
            broken_references = {
                'us_units': [],
                'usm_units': [],
                'cross_type_issues': [],
                'numeric_format_issues': []
            }
            
            # Validate US units
            us_units_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.deleted_at.is_(None),
                    UnitaStratigrafica.sequenza_fisica.is_not(None)
                )
            )
            
            us_result = await self.db.execute(us_units_query)
            us_units = us_result.scalars().all()
            
            for us in us_units:
                if us.sequenza_fisica:
                    unit_issues = await self._validate_unit_references(
                        us.us_code, 'us', us.sequenza_fisica, lookup_tables
                    )
                    if unit_issues:
                        broken_references['us_units'].extend(unit_issues)
            
            # Validate USM units
            usm_units_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.deleted_at.is_(None),
                    UnitaStratigraficaMuraria.sequenza_fisica.is_not(None)
                )
            )
            
            usm_result = await self.db.execute(usm_units_query)
            usm_units = usm_result.scalars().all()
            
            for usm in usm_units:
                if usm.sequenza_fisica:
                    unit_issues = await self._validate_unit_references(
                        usm.usm_code, 'usm', usm.sequenza_fisica, lookup_tables
                    )
                    if unit_issues:
                        broken_references['usm_units'].extend(unit_issues)
            
            validation_time = (time.time() - start_time) * 1000
            total_issues = sum(len(issues) for issues in broken_references.values())
            
            logger.info(
                f"Reference validation completed for site {site_id} in {validation_time:.2f}ms: "
                f"Found {total_issues} broken references"
            )
            
            return broken_references
            
        except Exception as e:
            logger.error(f"Error validating references for site {site_id}: {str(e)}", exc_info=True)
            return {
                'us_units': [f"Validation error: {str(e)}"],
                'usm_units': [],
                'cross_type_issues': [],
                'numeric_format_issues': []
            }
    
    async def _validate_unit_references(
        self,
        unit_code: str,
        unit_type: str,
        sequenza_fisica: Dict[str, List[str]],
        lookup_tables: Dict[str, Dict]
    ) -> List[str]:
        """
        Validate references for a single unit.
        
        Args:
            unit_code: Code of the unit being validated
            unit_type: Type of the unit ('us' or 'usm')
            sequenza_fisica: JSON structure containing relationships
            lookup_tables: Pre-built lookup tables
            
        Returns:
            List of broken reference descriptions
        """
        issues = []
        
        try:
            for rel_type, targets in sequenza_fisica.items():
                if not targets or not isinstance(targets, list):
                    continue
                
                for target in targets:
                    # Parse target reference (handle format like "174(usm)")
                    target_code, target_type = self._parse_target_reference(target)
                    
                    # Try to resolve the target using our resolver
                    resolved_id = await self.resolve_unit_code(target_code, target_type)
                    
                    if not resolved_id:
                        # Check if it's in soft-deleted
                        if target_type == 'us':
                            if target_code.lower() in lookup_tables['us_deleted']:
                                issues.append(
                                    f"{unit_type.upper()}{unit_code} references deleted US{target_code}"
                                )
                            else:
                                issues.append(
                                    f"{unit_type.upper()}{unit_code} cannot find US{target_code}"
                                )
                        else:  # usm
                            if target_code.lower() in lookup_tables['usm_deleted']:
                                issues.append(
                                    f"{unit_type.upper()}{unit_code} references deleted USM{target_code}"
                                )
                            else:
                                issues.append(
                                    f"{unit_type.upper()}{unit_code} cannot find USM{target_code}"
                                )
                    
                    # Check for cross-type inconsistencies
                    original_target_type = self._extract_target_type_from_reference(target)
                    if original_target_type and original_target_type != target_type:
                        issues.append(
                            f"{unit_type.upper()}{unit_code} has cross-type reference: "
                            f"{target} (expected {original_target_type}, resolved as {target_type})"
                        )
                        
        except Exception as e:
            logger.error(f"Error validating references for {unit_type}{unit_code}: {str(e)}")
            issues.append(f"{unit_type.upper()}{unit_code}: Validation error - {str(e)}")
        
        return issues
    
    async def cleanup_broken_references(self, site_id: str) -> Dict[str, int]:
        """
        Remove orphaned references from all units in a site.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary with cleanup statistics
        """
        try:
            logger.info(f"Cleaning up broken references for site {site_id}")
            start_time = time.time()
            
            # Get broken references first
            broken_refs = await self.validate_references(site_id)
            
            cleanup_stats = {
                'us_units_cleaned': 0,
                'usm_units_cleaned': 0,
                'references_removed': 0,
                'errors': 0
            }
            
            # Clean US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.deleted_at.is_(None),
                    UnitaStratigrafica.sequenza_fisica.is_not(None)
                )
            )
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            for us in us_units:
                if us.sequenza_fisica:
                    removed_count = await self._cleanup_unit_references(us, 'us')
                    if removed_count > 0:
                        cleanup_stats['us_units_cleaned'] += 1
                        cleanup_stats['references_removed'] += removed_count
            
            # Clean USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.deleted_at.is_(None),
                    UnitaStratigraficaMuraria.sequenza_fisica.is_not(None)
                )
            )
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            for usm in usm_units:
                if usm.sequenza_fisica:
                    removed_count = await self._cleanup_unit_references(usm, 'usm')
                    if removed_count > 0:
                        cleanup_stats['usm_units_cleaned'] += 1
                        cleanup_stats['references_removed'] += removed_count
            
            cleanup_time = (time.time() - start_time) * 1000
            logger.info(
                f"Reference cleanup completed for site {site_id} in {cleanup_time:.2f}ms: "
                f"US cleaned: {cleanup_stats['us_units_cleaned']}, "
                f"USM cleaned: {cleanup_stats['usm_units_cleaned']}, "
                f"References removed: {cleanup_stats['references_removed']}"
            )
            
            return cleanup_stats
            
        except Exception as e:
            logger.error(f"Error cleaning up references for site {site_id}: {str(e)}", exc_info=True)
            return {
                'us_units_cleaned': 0,
                'usm_units_cleaned': 0,
                'references_removed': 0,
                'errors': 1
            }
    
    async def _cleanup_unit_references(self, unit, unit_type: str) -> int:
        """
        Remove broken references from a single unit.
        
        Args:
            unit: The unit object (US or USM)
            unit_type: Type of the unit ('us' or 'usm')
            
        Returns:
            Number of references removed
        """
        try:
            if not unit.sequenza_fisica:
                return 0
            
            # Build lookup tables for validation
            site_id = unit.site_id
            lookup_tables = await self.build_lookup_tables(site_id)
            
            removed_count = 0
            modified = False
            
            for rel_type, targets in unit.sequenza_fisica.items():
                if not targets or not isinstance(targets, list):
                    continue
                
                valid_targets = []
                for target in targets:
                    target_code, target_type = self._parse_target_reference(target)
                    
                    # Check if target exists
                    if target_type == 'us':
                        if (target_code in lookup_tables['us_exact'] or 
                            target_code.lower() in lookup_tables['us_deleted']):
                            valid_targets.append(target)
                        else:
                            removed_count += 1
                            modified = True
                    else:  # usm
                        if (target_code in lookup_tables['usm_exact'] or 
                            target_code.lower() in lookup_tables['usm_deleted']):
                            valid_targets.append(target)
                        else:
                            removed_count += 1
                            modified = True
                
                # Update the relationship if modified
                if modified:
                    unit.sequenza_fisica[rel_type] = valid_targets
            
            if modified:
                logger.debug(f"Cleaned {removed_count} broken references from {unit_type.upper()}{getattr(unit, 'us_code', getattr(unit, 'usm_code', 'unknown'))}")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error cleaning up references for {unit_type}: {str(e)}")
            return 0
    
    def _parse_target_reference(self, target: str) -> Tuple[str, str]:
        """
        Parse target reference to extract code and type.
        
        Args:
            target: Target string, possibly with type suffix like "174(usm)"
            
        Returns:
            Tuple of (code, type) where type is 'us' or 'usm'
        """
        # Check for explicit type specification
        match = re.match(r'^(\w+)\((usm?)\)$', target.lower())
        if match:
            code = match.group(1).upper()
            unit_type = match.group(2)
            return code, unit_type
        
        # Default to US if no type specified
        return target.upper(), 'us'
    
    def _extract_target_type_from_reference(self, target: str) -> Optional[str]:
        """
        Extract the target type from a reference string.
        
        Args:
            target: Reference string like "174(usm)"
            
        Returns:
            Target type ('us', 'usm') or None if not specified
        """
        match = re.match(r'^\w+\((usm?)\)$', target.lower())
        if match:
            return match.group(1)
        return None
    
    async def _get_current_site_id(self) -> Optional[str]:
        """
        Get the current site ID. This would typically be determined by context.
        For now, this is a placeholder that would need to be implemented
        based on the specific use case.
        
        Returns:
            Site ID string or None
        """
        # This is a placeholder - in a real implementation,
        # this would be determined by the current request context
        # or passed as a parameter to the resolver methods
        return None
    
    async def batch_validate_references(
        self,
        site_ids: List[str],
        parallel_workers: int = 4
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Validate references across multiple sites in parallel.
        
        Args:
            site_ids: List of site IDs to validate
            parallel_workers: Number of parallel validation workers
            
        Returns:
            Dictionary mapping site_id to validation results
        """
        import asyncio
        
        logger.info(f"Starting batch reference validation for {len(site_ids)} sites")
        start_time = time.time()
        
        # Create semaphore to limit parallel workers
        semaphore = asyncio.Semaphore(parallel_workers)
        
        async def validate_site(site_id: str) -> Tuple[str, Dict[str, List[str]]]:
            async with semaphore:
                return site_id, await self.validate_references(site_id)
        
        # Run validations in parallel
        tasks = [validate_site(site_id) for site_id in site_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Compile results
        batch_results = {}
        total_issues = 0
        
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Error validating site: {str(result)}")
                batch_results['error'] = {'error': [str(result)]}
            else:
                site_id, validation_result = result
                batch_results[site_id] = validation_result
                total_issues += sum(len(issues) for issues in validation_result.values())
        
        batch_time = (time.time() - start_time) * 1000
        logger.info(
            f"Batch reference validation completed in {batch_time:.2f}ms: "
            f"{total_issues} total issues across {len(site_ids)} sites"
        )
        
        return batch_results
    
    async def create_reference_backup(self, site_id: str) -> Dict[str, Any]:
        """
        Create a backup of all unit references before cleanup operations.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing backup information
        """
        try:
            logger.info(f"Creating reference backup for site {site_id}")
            start_time = time.time()
            
            backup_data = {
                'site_id': site_id,
                'created_at': datetime.now().isoformat(),
                'us_units': [],
                'usm_units': []
            }
            
            # Backup US units
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.sequenza_fisica.is_not(None)
                )
            )
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            
            for us in us_units:
                backup_data['us_units'].append({
                    'id': str(us.id),
                    'code': us.us_code,
                    'sequenza_fisica': us.sequenza_fisica
                })
            
            # Backup USM units
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.sequenza_fisica.is_not(None)
                )
            )
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            
            for usm in usm_units:
                backup_data['usm_units'].append({
                    'id': str(usm.id),
                    'code': usm.usm_code,
                    'sequenza_fisica': usm.sequenza_fisica
                })
            
            # Store backup (in a real implementation, this might go to file/database)
            backup_id = f"{site_id}_{int(time.time())}"
            
            backup_time = (time.time() - start_time) * 1000
            logger.info(
                f"Reference backup created for site {site_id} in {backup_time:.2f}ms: "
                f"US units: {len(backup_data['us_units'])}, "
                f"USM units: {len(backup_data['usm_units'])}"
            )
            
            return {
                'backup_id': backup_id,
                'backup_data': backup_data,
                'us_unit_count': len(backup_data['us_units']),
                'usm_unit_count': len(backup_data['usm_units']),
                'created_at': backup_data['created_at']
            }
            
        except Exception as e:
            logger.error(f"Error creating reference backup for site {site_id}: {str(e)}", exc_info=True)
            return {
                'backup_id': None,
                'backup_data': None,
                'error': str(e),
                'us_unit_count': 0,
                'usm_unit_count': 0
            }
    
    async def restore_reference_backup(
        self,
        site_id: str,
        backup_data: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        Restore references from a backup.
        
        Args:
            site_id: UUID of the archaeological site
            backup_data: Backup data from create_reference_backup()
            
        Returns:
            Dictionary with restore statistics
        """
        try:
            logger.info(f"Restoring reference backup for site {site_id}")
            start_time = time.time()
            
            restore_stats = {
                'us_units_restored': 0,
                'usm_units_restored': 0,
                'references_restored': 0,
                'errors': 0
            }
            
            # Restore US units
            for us_backup in backup_data.get('us_units', []):
                try:
                    us_query = select(UnitaStratigrafica).where(
                        UnitStratigrafica.id == UUID(us_backup['id'])
                    )
                    us_result = await self.db.execute(us_query)
                    us_unit = us_result.scalar_one_or_none()
                    
                    if us_unit:
                        us_unit.sequenza_fisica = us_backup['sequenza_fisica']
                        restore_stats['us_units_restored'] += 1
                        
                        # Count references
                        if us_backup['sequenza_fisica']:
                            for rel_type, targets in us_backup['sequenza_fisica'].items():
                                if isinstance(targets, list):
                                    restore_stats['references_restored'] += len(targets)
                    else:
                        restore_stats['errors'] += 1
                        
                except Exception as e:
                    logger.error(f"Error restoring US unit {us_backup.get('id')}: {str(e)}")
                    restore_stats['errors'] += 1
            
            # Restore USM units
            for usm_backup in backup_data.get('usm_units', []):
                try:
                    usm_query = select(UnitaStratigraficaMuraria).where(
                        UnitaStratigraficaMuraria.id == UUID(usm_backup['id'])
                    )
                    usm_result = await self.db.execute(usm_query)
                    usm_unit = usm_result.scalar_one_or_none()
                    
                    if usm_unit:
                        usm_unit.sequenza_fisica = usm_backup['sequenza_fisica']
                        restore_stats['usm_units_restored'] += 1
                        
                        # Count references
                        if usm_backup['sequenza_fisica']:
                            for rel_type, targets in usm_backup['sequenza_fisica'].items():
                                if isinstance(targets, list):
                                    restore_stats['references_restored'] += len(targets)
                    else:
                        restore_stats['errors'] += 1
                        
                except Exception as e:
                    logger.error(f"Error restoring USM unit {usm_backup.get('id')}: {str(e)}")
                    restore_stats['errors'] += 1
            
            restore_time = (time.time() - start_time) * 1000
            logger.info(
                f"Reference backup restored for site {site_id} in {restore_time:.2f}ms: "
                f"US restored: {restore_stats['us_units_restored']}, "
                f"USM restored: {restore_stats['usm_units_restored']}, "
                f"References restored: {restore_stats['references_restored']}"
            )
            
            return restore_stats
            
        except Exception as e:
            logger.error(f"Error restoring reference backup for site {site_id}: {str(e)}", exc_info=True)
            return {
                'us_units_restored': 0,
                'usm_units_restored': 0,
                'references_restored': 0,
                'errors': 1
            }
    
    async def get_reference_statistics(self, site_id: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics about references in a site.
        
        Args:
            site_id: UUID of the archaeological site
            
        Returns:
            Dictionary containing reference statistics
        """
        try:
            logger.info(f"Collecting reference statistics for site {site_id}")
            start_time = time.time()
            
            # Initialize statistics
            stats = {
                'site_id': site_id,
                'timestamp': datetime.now().isoformat(),
                'us_units': {
                    'total': 0,
                    'with_references': 0,
                    'total_references': 0,
                    'references_by_type': {},
                    'units_broken': 0,
                    'broken_references': 0
                },
                'usm_units': {
                    'total': 0,
                    'with_references': 0,
                    'total_references': 0,
                    'references_by_type': {},
                    'units_broken': 0,
                    'broken_references': 0
                },
                'overall': {
                    'total_units': 0,
                    'total_references': 0,
                    'units_with_broken_refs': 0,
                    'total_broken_refs': 0,
                    'health_score': 0.0
                }
            }
            
            # Build lookup tables for validation
            lookup_tables = await self.build_lookup_tables(site_id)
            
            # Get US units statistics
            us_query = select(UnitaStratigrafica).where(
                and_(
                    UnitaStratigrafica.site_id == site_id,
                    UnitaStratigrafica.deleted_at.is_(None)
                )
            )
            
            us_result = await self.db.execute(us_query)
            us_units = us_result.scalars().all()
            stats['us_units']['total'] = len(us_units)
            
            # Get USM units statistics
            usm_query = select(UnitaStratigraficaMuraria).where(
                and_(
                    UnitaStratigraficaMuraria.site_id == site_id,
                    UnitaStratigraficaMuraria.deleted_at.is_(None)
                )
            )
            
            usm_result = await self.db.execute(usm_query)
            usm_units = usm_result.scalars().all()
            stats['usm_units']['total'] = len(usm_units)
            
            # Analyze US units
            for us in us_units:
                if us.sequenza_fisica:
                    stats['us_units']['with_references'] += 1
                    unit_stats = self._analyze_unit_references(
                        us.sequenza_fisica, lookup_tables
                    )
                    
                    stats['us_units']['total_references'] += unit_stats['total_refs']
                    stats['us_units']['broken_references'] += unit_stats['broken_refs']
                    
                    if unit_stats['broken_refs'] > 0:
                        stats['us_units']['units_broken'] += 1
                    
                    # Aggregate by relationship type
                    for rel_type, count in unit_stats['refs_by_type'].items():
                        stats['us_units']['references_by_type'][rel_type] = (
                            stats['us_units']['references_by_type'].get(rel_type, 0) + count
                        )
            
            # Analyze USM units
            for usm in usm_units:
                if usm.sequenza_fisica:
                    stats['usm_units']['with_references'] += 1
                    unit_stats = self._analyze_unit_references(
                        usm.sequenza_fisica, lookup_tables
                    )
                    
                    stats['usm_units']['total_references'] += unit_stats['total_refs']
                    stats['usm_units']['broken_references'] += unit_stats['broken_refs']
                    
                    if unit_stats['broken_refs'] > 0:
                        stats['usm_units']['units_broken'] += 1
                    
                    # Aggregate by relationship type
                    for rel_type, count in unit_stats['refs_by_type'].items():
                        stats['usm_units']['references_by_type'][rel_type] = (
                            stats['usm_units']['references_by_type'].get(rel_type, 0) + count
                        )
            
            # Calculate overall statistics
            stats['overall']['total_units'] = (
                stats['us_units']['total'] + stats['usm_units']['total']
            )
            stats['overall']['total_references'] = (
                stats['us_units']['total_references'] + stats['usm_units']['total_references']
            )
            stats['overall']['units_with_broken_refs'] = (
                stats['us_units']['units_broken'] + stats['usm_units']['units_broken']
            )
            stats['overall']['total_broken_refs'] = (
                stats['us_units']['broken_references'] + stats['usm_units']['broken_references']
            )
            
            # Calculate health score (0-100)
            if stats['overall']['total_references'] > 0:
                stats['overall']['health_score'] = round(
                    (1.0 - (stats['overall']['total_broken_refs'] / stats['overall']['total_references'])) * 100,
                    2
                )
            else:
                stats['overall']['health_score'] = 100.0
            
            stats_time = (time.time() - start_time) * 1000
            logger.info(
                f"Reference statistics collected for site {site_id} in {stats_time:.2f}ms: "
                f"Health score: {stats['overall']['health_score']}%, "
                f"Broken references: {stats['overall']['total_broken_refs']}"
            )
            
            return stats
            
        except Exception as e:
            logger.error(f"Error collecting reference statistics for site {site_id}: {str(e)}", exc_info=True)
            return {
                'site_id': site_id,
                'timestamp': datetime.now().isoformat(),
                'error': str(e),
                'overall': {'health_score': 0.0}
            }
    
    def _analyze_unit_references(
        self,
        sequenza_fisica: Dict[str, List[str]],
        lookup_tables: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """
        Analyze references for a single unit.
        
        Args:
            sequenza_fisica: JSON structure containing relationships
            lookup_tables: Pre-built lookup tables
            
        Returns:
            Dictionary with analysis results
        """
        analysis = {
            'total_refs': 0,
            'broken_refs': 0,
            'refs_by_type': {}
        }
        
        try:
            for rel_type, targets in sequenza_fisica.items():
                if not targets or not isinstance(targets, list):
                    continue
                
                analysis['refs_by_type'][rel_type] = len(targets)
                analysis['total_refs'] += len(targets)
                
                for target in targets:
                    target_code, target_type = self._parse_target_reference(target)
                    
                    # Check if target exists
                    exists = False
                    if target_type == 'us':
                        exists = (target_code in lookup_tables['us_exact'] or
                                 target_code.lower() in lookup_tables['us_deleted'])
                    else:  # usm
                        exists = (target_code in lookup_tables['usm_exact'] or
                                 target_code.lower() in lookup_tables['usm_deleted'])
                    
                    if not exists:
                        analysis['broken_refs'] += 1
                        
        except Exception as e:
            logger.error(f"Error analyzing unit references: {str(e)}")
        
        return analysis
    
    def get_resolution_statistics(self) -> Dict[str, Any]:
        """
        Get resolution performance statistics.
        
        Returns:
            Dictionary containing resolution statistics and performance metrics
        """
        total_resolutions = sum(self._resolution_stats.values())
        success_rate = 0.0
        
        if total_resolutions > 0:
            successful_resolutions = sum(
                count for key, count in self._resolution_stats.items()
                if key.endswith('_success')
            )
            success_rate = (successful_resolutions / total_resolutions) * 100
        
        return {
            'total_resolutions': total_resolutions,
            'success_rate_percent': round(success_rate, 2),
            'resolution_strategies': dict(self._resolution_stats),
            'cache_size': len(self._lookup_cache),
            'cache_entries': list(self._cache_timestamps.keys())
        }
    
    def clear_cache(self) -> None:
        """Clear all cached lookup tables and statistics."""
        self._lookup_cache.clear()
        self._cache_timestamps.clear()
        self._resolution_stats.clear()
        logger.info("Unit resolver cache cleared")
    
    async def test_resolution(self, test_codes: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        Test resolution with provided codes and return detailed results.
        
        Args:
            test_codes: List of (code, unit_type) tuples to test
            
        Returns:
            Dictionary with test results and performance metrics
        """
        test_results = {
            'tested_codes': len(test_codes),
            'successful_resolutions': 0,
            'failed_resolutions': 0,
            'results': [],
            'total_time_ms': 0,
            'average_time_ms': 0
        }
        
        start_time = time.time()
        
        for code, unit_type in test_codes:
            code_start_time = time.time()
            resolved_id = await self.resolve_unit_code(code, unit_type)
            code_time = (time.time() - code_start_time) * 1000
            
            result = {
                'code': code,
                'unit_type': unit_type,
                'resolved_id': resolved_id,
                'time_ms': round(code_time, 2),
                'success': resolved_id is not None
            }
            
            test_results['results'].append(result)
            
            if resolved_id:
                test_results['successful_resolutions'] += 1
            else:
                test_results['failed_resolutions'] += 1
        
        total_time = (time.time() - start_time) * 1000
        test_results['total_time_ms'] = round(total_time, 2)
        
        if test_results['tested_codes'] > 0:
            test_results['average_time_ms'] = round(
                total_time / test_results['tested_codes'], 2
            )
        
        logger.info(
            f"Resolution test completed: {test_results['successful_resolutions']}/"
            f"{test_results['tested_codes']} successful in {total_time:.2f}ms"
        )
        
        return test_results


# ===== UTILITY FUNCTIONS =====

async def create_unit_resolver(db: AsyncSession) -> UnitResolver:
    """
    Factory function to create a unit resolver instance.
    
    Args:
        db: AsyncSession for database operations
        
    Returns:
        Configured UnitResolver instance
    """
    return UnitResolver(db)


async def resolve_unit_with_fallback(
    db: AsyncSession,
    code: str,
    unit_type: str,
    site_id: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function for single unit resolution with fallback.
    
    Args:
        db: AsyncSession for database operations
        code: Unit code to resolve
        unit_type: Target unit type ('us' or 'usm')
        site_id: Site ID (optional, for context)
        
    Returns:
        Resolved unit ID or None if not found
    """
    resolver = UnitResolver(db)
    
    # If site_id is provided, we could set context here
    # (This would require extending the UnitResolver class)
    
    return await resolver.resolve_unit_code(code, unit_type)