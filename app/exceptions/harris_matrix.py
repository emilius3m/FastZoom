"""
Harris Matrix specific exceptions for validation and error handling.

This module provides specialized exceptions for Harris Matrix operations,
including duplicate detection, relationship validation, and cycle detection.
"""

from typing import List, Dict, Any, Optional


class HarrisMatrixException(Exception):
    """Base exception for Harris Matrix operations."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class UnitCodeConflict(HarrisMatrixException):
    """Raised when duplicate unit codes are detected."""
    
    def __init__(
        self, 
        message: str, 
        existing_codes: List[str] = None,
        conflicts: Optional[Dict[str, Dict]] = None,
        suggestions: Optional[List[str]] = None
    ):
        self.existing_codes = existing_codes or []
        self.conflicts = conflicts or {}
        self.suggestions = suggestions or []
        
        # Enhance message with conflict details
        if existing_codes:
            message += f" (Duplicate codes: {', '.join(existing_codes)})"
        
        super().__init__(message, {
            "existing_codes": existing_codes,
            "conflicts": conflicts,
            "suggestions": suggestions
        })


class InvalidStratigraphicRelation(HarrisMatrixException):
    """Raised when invalid relationships are detected."""
    
    def __init__(
        self, 
        message: str, 
        invalid_relations: List[Dict] = None,
        missing_units: List[str] = None,
        circular_references: List[List[str]] = None
    ):
        self.invalid_relations = invalid_relations or []
        self.missing_units = missing_units or []
        self.circular_references = circular_references or []
        
        # Enhance message with validation details
        details = []
        if missing_units:
            details.append(f"Missing units: {', '.join(missing_units)}")
        if circular_references:
            details.append(f"Circular references detected: {len(circular_references)}")
        
        if details:
            message += f" ({'; '.join(details)})"
        
        super().__init__(message, {
            "invalid_relations": invalid_relations,
            "missing_units": missing_units,
            "circular_references": circular_references
        })


class CycleDetectionError(HarrisMatrixException):
    """Raised when potential cycles are detected in stratigraphic relationships."""
    
    def __init__(
        self, 
        message: str, 
        cycle_paths: List[List[str]] = None,
        affected_units: List[str] = None,
        severity: str = "error"  # "error", "warning", "info"
    ):
        self.cycle_paths = cycle_paths or []
        self.affected_units = affected_units or []
        self.severity = severity
        
        # Enhance message with cycle information
        if cycle_paths:
            message += f" ({len(cycle_paths)} cycle(s) detected)"
        
        super().__init__(message, {
            "cycle_paths": cycle_paths,
            "affected_units": affected_units,
            "severity": severity
        })


class BulkOperationError(HarrisMatrixException):
    """Raised when bulk operations encounter validation errors."""
    
    def __init__(
        self,
        message: str,
        operation_type: str,
        failed_items: List[Dict] = None,
        partial_success: bool = False,
        success_count: int = 0,
        total_count: int = 0
    ):
        self.operation_type = operation_type
        self.failed_items = failed_items or []
        self.partial_success = partial_success
        self.success_count = success_count
        self.total_count = total_count
        
        # Enhance message with operation statistics
        if partial_success:
            message += f" ({success_count}/{total_count} items processed successfully)"
        
        super().__init__(message, {
            "operation_type": operation_type,
            "failed_items": failed_items,
            "partial_success": partial_success,
            "success_count": success_count,
            "total_count": total_count
        })


class ValidationTimeoutError(HarrisMatrixException):
    """Raised when validation operations take too long (performance optimization)."""
    
    def __init__(
        self,
        message: str,
        operation: str,
        timeout_seconds: int,
        items_processed: int = 0,
        total_items: int = 0
    ):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        self.items_processed = items_processed
        self.total_items = total_items
        
        super().__init__(message, {
            "operation": operation,
            "timeout_seconds": timeout_seconds,
            "items_processed": items_processed,
            "total_items": total_items
        })


class StaleReferenceError(HarrisMatrixException):
    """Raised when references to non-existent units are detected during bulk updates."""
    
    def __init__(
        self,
        message: str,
        missing_units: List[str] = None,
        soft_deleted_units: List[str] = None,
        wrong_site_units: List[str] = None,
        recovery_suggestions: List[str] = None
    ):
        self.missing_units = missing_units or []
        self.soft_deleted_units = soft_deleted_units or []
        self.wrong_site_units = wrong_site_units or []
        self.recovery_suggestions = recovery_suggestions or []
        
        # Generate default recovery suggestions if not provided
        if not recovery_suggestions:
            default_suggestions = []
            if missing_units:
                default_suggestions.extend([
                    f"Remove references to missing units: {', '.join(missing_units)}",
                    "Verify unit IDs are correct and haven't been deleted"
                ])
            if soft_deleted_units:
                default_suggestions.extend([
                    f"Restore soft-deleted units: {', '.join(soft_deleted_units)}",
                    "Or remove references to soft-deleted units"
                ])
            if wrong_site_units:
                default_suggestions.append(
                    f"Units belong to different site: {', '.join(wrong_site_units)}"
                )
            self.recovery_suggestions = default_suggestions
        
        # Enhance message with stale reference details
        details = []
        if missing_units:
            details.append(f"Missing units: {len(missing_units)}")
        if soft_deleted_units:
            details.append(f"Soft-deleted units: {len(soft_deleted_units)}")
        if wrong_site_units:
            details.append(f"Wrong site units: {len(wrong_site_units)}")
        
        if details:
            message += f" ({'; '.join(details)})"
        
        super().__init__(message, {
            "missing_units": missing_units,
            "soft_deleted_units": soft_deleted_units,
            "wrong_site_units": wrong_site_units,
            "recovery_suggestions": self.recovery_suggestions,
            "total_issues": len(missing_units) + len(soft_deleted_units) + len(wrong_site_units)
        })