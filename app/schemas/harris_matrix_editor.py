# app/schemas/harris_matrix_editor.py
"""
Pydantic schemas for Harris Matrix Editor API.

These schemas define the request/response models for the graphical Harris Matrix editor,
including unit creation, relationship management, and validation structures.
"""

from enum import Enum
from typing import Dict, List, Any, Optional, Union
from uuid import UUID
from pydantic import BaseModel, Field, validator
from datetime import datetime
import re


class StratigraphicRelation(str, Enum):
    """Enum for valid stratigraphic relationship types."""
    
    UGUALE_A = "uguale_a"
    SI_LEGHE_A = "si_lega_a"
    GLI_SI_APPOGGIA = "gli_si_appoggia"
    SI_APPOGGIA_A = "si_appoggia_a"
    COPERTO_DA = "coperto_da"
    COPRE = "copre"
    TAGLIATO_DA = "tagliato_da"
    TAGLIA = "taglia"
    RIEMPITO_DA = "riempito_da"
    RIEMPIE = "riempie"


class UnitTypeEnum(str, Enum):
    """Enum for unit types."""
    
    US = "us"
    USM = "usm"


class TipoUSEnum(str, Enum):
    """Enum for US types."""
    
    POSITIVA = "positiva"
    NEGATIVA = "negativa"


class HarrisMatrixNode(BaseModel):
    """Schema for Harris Matrix graph node."""
    
    id: str = Field(..., description="Node unique identifier")
    type: UnitTypeEnum = Field(..., description="Unit type (us or usm)")
    label: str = Field(..., description="Display label for the node")
    definition: Optional[str] = Field(None, description="Unit definition")
    tipo: Optional[TipoUSEnum] = Field(None, description="US type (positive/negative)")
    data: Dict[str, Any] = Field(default_factory=dict, description="Additional node data")
    
    class Config:
        json_encoders = {
            UUID: str
        }


class HarrisMatrixEdge(BaseModel):
    """Schema for Harris Matrix graph edge."""
    
    id: Optional[str] = Field(None, description="Edge unique identifier")
    from_node: str = Field(..., description="Source node identifier")
    to_node: str = Field(..., description="Target node identifier")
    relation_type: StratigraphicRelation = Field(..., description="Type of relationship")
    label: str = Field(..., description="Display label for the edge")
    bidirectional: bool = Field(default=False, description="Whether relationship is bidirectional")
    description: Optional[str] = Field(None, description="Relationship description")
    
    @validator('from_node', 'to_node')
    def validate_node_ids(cls, v):
        if not v or not v.strip():
            raise ValueError('Node IDs cannot be empty')
        return v.strip()
    
    class Config:
        json_encoders = {
            UUID: str
        }


class HarrisMatrixBulkCreateUnit(BaseModel):
    """Schema for creating a single unit in bulk operations."""
    
    temp_id: str = Field(
        ...,
        description="Temporary identifier for client-side mapping",
        min_length=1,
        max_length=100,
        pattern=r'^[a-zA-Z0-9_-]+$',
        example="temp_unit_1"
    )
    unit_type: UnitTypeEnum = Field(
        ...,
        description="Type of unit (us or usm)",
        example="us"
    )
    code: Optional[str] = Field(
        None,
        description="Unit code (auto-generated if not provided)",
        min_length=1,
        max_length=20,
        example="US001"
    )
    definition: Optional[str] = Field(
        None,
        description="Unit definition",
        max_length=2000,
        example="Stratigraphic unit description"
    )
    tipo: Optional[TipoUSEnum] = Field(
        None,
        description="US type (positive/negative) - only applicable to US units",
        example="positiva"
    )
    localita: Optional[str] = Field(
        None,
        description="Location",
        max_length=500,
        example="Area A"
    )
    datazione: Optional[str] = Field(
        None,
        description="Dating information",
        max_length=500,
        example="Medioevo"
    )
    periodo: Optional[str] = Field(
        None,
        description="Period",
        max_length=200,
        example="XII secolo"
    )
    fase: Optional[str] = Field(
        None,
        description="Phase",
        max_length=200,
        example="Fase 1"
    )
    affidabilita_stratigrafica: Optional[str] = Field(
        None,
        description="Stratigraphic reliability",
        max_length=500,
        example="Alta"
    )
    tecnica_costruttiva: Optional[str] = Field(
        None,
        description="Construction technique (USM only)",
        max_length=500,
        example="Muratura a sacco"
    )
    created_by: Optional[str] = Field(
        None,
        description="User ID who created the unit",
        max_length=100
    )
    
    @validator('code')
    def validate_code(cls, v, values):
        if v:
            v = v.strip().upper()
            if not v:
                raise ValueError('Unit code cannot be empty')
            
            # Basic format validation
            if not re.match(r'^[A-Z0-9]+$', v):
                raise ValueError('Unit code must contain only uppercase letters and numbers')
            
            # Check length
            if len(v) < 2 or len(v) > 20:
                raise ValueError('Unit code must be between 2 and 20 characters')
            
            # Unit type specific validation
            unit_type = values.get('unit_type')
            if unit_type:
                if unit_type == UnitTypeEnum.US and not v.startswith('US'):
                    raise ValueError('US codes should start with US (e.g., US001)')
                elif unit_type == UnitTypeEnum.USM and not v.startswith('USM'):
                    raise ValueError('USM codes should start with USM (e.g., USM001)')
        
        return v
    
    @validator('tipo')
    def validate_tipo(cls, v, values):
        # USM units should not have tipo field
        unit_type = values.get('unit_type')
        if unit_type == UnitTypeEnum.USM and v is not None:
            raise ValueError('USM units should not have tipo field')
        return v
    
    @validator('tecnica_costruttiva')
    def validate_tecnica_costruttiva(cls, v, values):
        # Only USM units should have tecnica_costruttiva
        unit_type = values.get('unit_type')
        if unit_type == UnitTypeEnum.US and v is not None:
            raise ValueError('Only USM units should have tecnica_costruttiva field')
        return v
    
    class Config:
        json_encoders = {
            UUID: str
        }


class HarrisMatrixBulkCreateRelationship(BaseModel):
    """Schema for creating a single relationship in bulk operations."""
    
    temp_id: str = Field(
        ...,
        description="Temporary identifier for client-side mapping",
        min_length=1,
        max_length=100,
        pattern=r'^[a-zA-Z0-9_-]+$',
        example="temp_rel_1"
    )
    from_temp_id: str = Field(
        ...,
        description="Temporary ID of source unit",
        min_length=1,
        max_length=100,
        example="temp_unit_1"
    )
    to_temp_id: str = Field(
        ...,
        description="Temporary ID of target unit",
        min_length=1,
        max_length=100,
        example="temp_unit_2"
    )
    relation_type: StratigraphicRelation = Field(
        ...,
        description="Type of relationship",
        example=StratigraphicRelation.COPRE
    )
    
    @validator('from_temp_id', 'to_temp_id')
    def validate_temp_ids(cls, v):
        if not v or not v.strip():
            raise ValueError('Temporary IDs cannot be empty')
        
        v = v.strip()
        
        # Basic validation for temp_id format
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError('Temporary IDs can only contain letters, numbers, underscores, and hyphens')
        
        if len(v) > 100:
            raise ValueError('Temporary IDs cannot exceed 100 characters')
        
        return v
    
    @validator('to_temp_id')
    def validate_no_self_reference(cls, v, values):
        if 'from_temp_id' in values and v == values['from_temp_id']:
            raise ValueError('Unit cannot have relationship with itself')
        return v


class HarrisMatrixBulkCreateRequest(BaseModel):
    """Schema for bulk creating units and relationships."""
    
    units: List[HarrisMatrixBulkCreateUnit] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="Units to create (1-100 units per request)",
        example=[
            {
                "temp_id": "temp_unit_1",
                "unit_type": "us",
                "code": "US001",
                "definition": "Sample US unit",
                "tipo": "positiva"
            }
        ]
    )
    relationships: List[HarrisMatrixBulkCreateRelationship] = Field(
        default=[],
        max_items=500,
        description="Relationships to create (max 500 relationships)",
        example=[
            {
                "temp_id": "temp_rel_1",
                "from_temp_id": "temp_unit_1",
                "to_temp_id": "temp_unit_2",
                "relation_type": "copre"
            }
        ]
    )
    
    @validator('units')
    def validate_unique_temp_ids(cls, v):
        if not v:
            raise ValueError('At least one unit must be provided')
        
        temp_ids = [unit.temp_id for unit in v]
        if len(temp_ids) != len(set(temp_ids)):
            duplicates = [tid for tid in temp_ids if temp_ids.count(tid) > 1]
            raise ValueError(f'Duplicate temporary IDs found in units: {list(set(duplicates))}')
        
        # Check for empty or invalid temp_ids
        invalid_ids = [unit.temp_id for unit in v if not unit.temp_id or not unit.temp_id.strip()]
        if invalid_ids:
            raise ValueError(f'Invalid temporary IDs found: {invalid_ids}')
        
        return v
    
    @validator('relationships')
    def validate_relationship_temp_ids(cls, v, values):
        if not v:
            return v  # Empty relationships are allowed
            
        if 'units' not in values:
            return v
            
        unit_temp_ids = {unit.temp_id for unit in values['units']}
        relationship_temp_ids = [rel.temp_id for rel in v]
        
        # Check for duplicate relationship temp_ids
        if len(relationship_temp_ids) != len(set(relationship_temp_ids)):
            duplicates = [tid for tid in relationship_temp_ids if relationship_temp_ids.count(tid) > 1]
            raise ValueError(f'Duplicate relationship temporary IDs found: {list(set(duplicates))}')
        
        # Check relationship references
        invalid_refs = []
        self_refs = []
        
        for rel in v:
            if rel.from_temp_id not in unit_temp_ids:
                invalid_refs.append(f"Source unit '{rel.from_temp_id}'")
            if rel.to_temp_id not in unit_temp_ids:
                invalid_refs.append(f"Target unit '{rel.to_temp_id}'")
            if rel.from_temp_id == rel.to_temp_id:
                self_refs.append(f"Relationship '{rel.temp_id}'")
        
        if invalid_refs:
            raise ValueError(f'Referenced units not found: {list(set(invalid_refs))}')
        
        if self_refs:
            raise ValueError(f'Self-references found: {self_refs}')
        
        return v


class HarrisMatrixBulkUpdateRequest(BaseModel):
    """Schema for bulk updating relationships."""
    
    unit_id: UUID = Field(..., description="ID of the unit to update")
    unit_type: UnitTypeEnum = Field(..., description="Type of unit (us or usm)")
    relationships: Dict[StratigraphicRelation, List[str]] = Field(
        ..., description="Relationship updates by type"
    )
    
    @validator('relationships')
    def validate_relationships(cls, v):
        for rel_type, targets in v.items():
            if targets is None:
                v[rel_type] = []
            elif not isinstance(targets, list):
                raise ValueError(f"Relationship targets for {rel_type} must be a list")
        return v
    
    class Config:
        json_encoders = {
            UUID: str
        }


class HarrisMatrixDeleteRequest(BaseModel):
    """Schema for deleting a unit."""
    
    unit_id: UUID = Field(..., description="ID of the unit to delete")
    unit_type: UnitTypeEnum = Field(..., description="Type of unit (us or usm)")
    cleanup_references: bool = Field(
        default=True, description="Whether to cleanup references from other units"
    )
    
    class Config:
        json_encoders = {
            UUID: str
        }


class UnitResponse(BaseModel):
    """Schema for individual unit responses."""
    
    id: str = Field(..., description="Database ID")
    code: str = Field(..., description="Human readable code")
    type: Optional[str] = Field(None, description="Unit type (us or usm)")
    description: Optional[str] = Field(None, description="Unit definition/description")
    
    # ===== CRITICAL FIX: Include additional fields frontend needs =====
    site_id: Optional[str] = Field(None, description="Site ID")
    sequenzafisica: Optional[Dict[str, List[str]]] = Field(None, description="Sequenza fisica relationships")
    data: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional unit data")
    position: Optional[Dict[str, float]] = Field(None, description="X,Y position coordinates")
    
    # Unit-specific fields
    tipo: Optional[str] = Field(None, description="US type (positiva/negativa) for US units")
    localita: Optional[str] = Field(None, description="Location")
    datazione: Optional[str] = Field(None, description="Dating information")
    periodo: Optional[str] = Field(None, description="Period")
    fase: Optional[str] = Field(None, description="Phase")
    affidabilita_stratigrafica: Optional[str] = Field(None, description="Stratigraphic reliability")
    tecnica_costruttiva: Optional[str] = Field(None, description="Construction technique for USM units")
    
    # Metadata fields
    created_by: Optional[str] = Field(None, description="User ID who created the unit")
    updated_by: Optional[str] = Field(None, description="User ID who last updated the unit")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    temp_id: Optional[str] = Field(None, description="Temporary ID for frontend mapping")


class RelationshipResponse(BaseModel):
    """Schema for individual relationship responses."""
    
    id: str = Field(..., description="Relationship ID")
    from_unit_id: str = Field(..., description="Source unit ID")
    to_unit_id: str = Field(..., description="Target unit ID")
    relationship_type: str = Field(..., description="Type of relationship")
    resolved: bool = Field(default=False, description="Whether relationship is resolved")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    
    # ===== CRITICAL FIX: Include fields frontend uses =====
    from_tempid: Optional[str] = Field(None, description="For frontend mapping")
    to_tempid: Optional[str] = Field(None, description="For frontend mapping")
    tempid: Optional[str] = Field(None, description="For frontend mapping")
    bidirectional: bool = Field(default=False, description="Whether relationship is bidirectional")
    description: Optional[str] = Field(None, description="Relationship description")
    label: Optional[str] = Field(None, description="Display label")


class HarrisMatrixValidationResult(BaseModel):
    """Schema for validation results."""
    
    is_valid: bool = Field(..., description="Whether validation passed")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    cycles: List[List[str]] = Field(default_factory=list, description="Detected cycles")


class HarrisMatrixResponse(BaseModel):
    """Base schema for Harris Matrix API responses."""
    
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    site_id: Optional[UUID] = Field(None, description="Site ID if applicable")
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


class HarrisMatrixBulkCreateResponse(HarrisMatrixResponse):
    """Response schema for bulk create operations."""
    
    created_units: int = Field(..., description="Number of units created")
    created_relationships: int = Field(..., description="Number of relationships created")
    unit_mapping: Dict[str, str] = Field(..., description="Mapping from temp_id to actual unit ID")
    relationship_mapping: Dict[str, str] = Field(..., description="Mapping from temp_id to relationship ID")
    units: List[UnitResponse] = Field(..., description="Created units data")
    relationships: List[RelationshipResponse] = Field(..., description="Created relationships data")
    validation_result: Optional[HarrisMatrixValidationResult] = Field(
        None, description="Validation results"
    )
    processing_time_ms: Optional[float] = Field(
        None, description="Processing time in milliseconds"
    )
    warnings: List[str] = Field(
        default_factory=list, description="Processing warnings"
    )
    suggestions: List[str] = Field(
        default_factory=list, description="Suggestions for improvement"
    )
    
    # ===== CRITICAL FIX: Add compatibility aliases for frontend =====
    # Frontend expects 'units' but backend returns 'created_units'
    # Frontend expects 'relationships' but backend returns 'created_relationships'
    
    @property
    def created_units_data(self) -> Optional[List[UnitResponse]]:
        """Compatibility property for frontend - maps to units data"""
        return self.units
    
    @property
    def created_relationships_data(self) -> Optional[List[RelationshipResponse]]:
        """Compatibility property for frontend - maps to relationships data"""
        return self.relationships
    
    # Add serialization compatibility to ensure both formats work
    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        # Add aliases for frontend compatibility - ensure units field is always populated
        if hasattr(self, 'units') and self.units:
            data['created_units_data'] = [unit.dict() if hasattr(unit, 'dict') else unit for unit in self.units]
        if hasattr(self, 'relationships') and self.relationships:
            data['created_relationships_data'] = [rel.dict() if hasattr(rel, 'dict') else rel for rel in self.relationships]
        return data


class HarrisMatrixBulkUpdateResponse(HarrisMatrixResponse):
    """Response schema for bulk update operations."""
    
    unit_id: UUID = Field(..., description="Updated unit ID")
    unit_type: UnitTypeEnum = Field(..., description="Updated unit type")
    updated_relationships: int = Field(..., description="Number of relationships updated")
    old_relationships: Dict[str, List[str]] = Field(..., description="Previous relationships")
    new_relationships: Dict[str, List[str]] = Field(..., description="Updated relationships")


class HarrisMatrixDeleteResponse(HarrisMatrixResponse):
    """Response schema for delete operations."""
    
    deleted_unit: Dict[str, Any] = Field(..., description="Information about deleted unit")
    cleaned_references: bool = Field(..., description="Whether references were cleaned up")
    affected_units_count: int = Field(
        default=0, description="Number of other units that had references cleaned"
    )


class HarrisMatrixStatistics(BaseModel):
    """Schema for Harris Matrix statistics."""
    
    total_us: int = Field(..., description="Total US units")
    us_positive: int = Field(..., description="US positive units")
    us_negative: int = Field(..., description="US negative units")
    total_usm: int = Field(..., description="Total USM units")
    total_units: int = Field(..., description="Total units")
    total_edges: int = Field(..., description="Total relationships")
    total_levels: int = Field(..., description="Total chronological levels")
    max_depth: int = Field(..., description="Maximum stratigraphic depth")
    relationship_types: Dict[str, int] = Field(..., description="Count by relationship type")
    level_distribution: Dict[int, int] = Field(..., description="Units per chronological level")


class HarrisMatrixGraphData(BaseModel):
    """Complete Harris Matrix graph data structure."""
    
    nodes: List[HarrisMatrixNode] = Field(..., description="Graph nodes")
    edges: List[HarrisMatrixEdge] = Field(..., description="Graph edges")
    levels: Dict[str, int] = Field(..., description="Chronological levels")
    metadata: Dict[str, Any] = Field(..., description="Graph metadata")
    
    class Config:
        json_encoders = {
            UUID: str
        }


# Utility schemas for edge cases

class UnitCodeValidation(BaseModel):
    """Schema for unit code validation."""
    
    code: str = Field(..., description="Unit code to validate")
    unit_type: UnitTypeEnum = Field(..., description="Unit type")
    site_id: UUID = Field(..., description="Site ID")
    
    class Config:
        json_encoders = {
            UUID: str
        }


class RelationshipValidation(BaseModel):
    """Schema for individual relationship validation."""
    
    from_unit_code: str = Field(..., description="Source unit code")
    to_unit_code: str = Field(..., description="Target unit code")
    from_unit_type: UnitTypeEnum = Field(..., description="Source unit type")
    to_unit_type: UnitTypeEnum = Field(..., description="Target unit type")
    relation_type: StratigraphicRelation = Field(..., description="Relationship type")
    
    class Config:
        json_encoders = {
            UUID: str
        }


class CycleDetectionResult(BaseModel):
    """Schema for cycle detection results."""
    
    has_cycles: bool = Field(..., description="Whether cycles were detected")
    cycles: List[List[str]] = Field(..., description="List of detected cycles")
    cycle_count: int = Field(..., description="Total number of cycles")
    affected_units: List[str] = Field(..., description="Units involved in cycles")


class NodePosition(BaseModel):
    """Position data for a single Harris Matrix node"""
    unit_id: str = Field(..., description="Unit identifier (e.g., 'US001', 'USM002')")
    unit_type: str = Field(..., description="Unit type: 'us' or 'usm'")
    x: float = Field(..., description="X coordinate position")
    y: float = Field(..., description="Y coordinate position")

    class Config:
        schema_extra = {
            "example": {
                "unit_id": "US001",
                "unit_type": "us",
                "x": 150.5,
                "y": 200.0
            }
        }


class HarrisMatrixLayoutSaveRequest(BaseModel):
    """Request model for saving Harris Matrix node positions"""
    positions: List[NodePosition] = Field(..., description="List of node positions to save")

    class Config:
        schema_extra = {
            "example": {
                "positions": [
                    {
                        "unit_id": "US001",
                        "unit_type": "us",
                        "x": 150.5,
                        "y": 200.0
                    },
                    {
                        "unit_id": "USM002",
                        "unit_type": "usm",
                        "x": 300.0,
                        "y": 100.5
                    }
                ]
            }
        }


class HarrisMatrixLayoutResponse(BaseModel):
    """Response model for saved Harris Matrix layout"""
    site_id: UUID = Field(..., description="Site identifier")
    positions: List[NodePosition] = Field(default_factory=list, description="Saved node positions")
    saved_count: int = Field(default=0, description="Number of positions saved")
    success: bool = Field(default=True, description="Operation success status")

    class Config:
        schema_extra = {
            "example": {
                "site_id": "123e4567-e89b-12d3-a456-426614174000",
                "positions": [
                    {
                        "unit_id": "US001",
                        "unit_type": "us",
                        "x": 150.5,
                        "y": 200.0
                    }
                ],
                "saved_count": 1,
                "success": True
            }
        }


class SequenzaFisicaBulkUpdateRequest(BaseModel):
    """Request model for bulk updating sequenzafisica of existing units."""
    updates: Dict[str, Dict[str, List[str]]] = Field(
        ...,
        description="Map of unit_id -> sequenzafisica dictionary"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "updates": {
                    "550e8400-e29b-41d4-a716-446655440000": {
                        "copre": ["US002", "US003"],
                        "taglia": ["US001usm"]
                    }
                }
            }
        }


# ===== ATOMIC HARRIS MATRIX SAVE SCHEMAS =====

class HarrisMatrixAtomicSaveRequest(BaseModel):
    """Schema for atomic Harris Matrix save operation.
    
    This schema combines all Harris Matrix operations into a single atomic transaction
    to ensure complete data consistency and prevent partial database states.
    """
    
    new_units: Optional[HarrisMatrixBulkCreateRequest] = Field(
        None,
        description="New units and relationships to create (optional)"
    )
    
    existing_units_updates: Optional[SequenzaFisicaBulkUpdateRequest] = Field(
        None,
        description="Updates to existing units' sequenzafisica (optional)"
    )
    
    layout_positions: Optional[HarrisMatrixLayoutSaveRequest] = Field(
        None,
        description="Layout positions to save for all units (optional)"
    )
    
    @validator('new_units')
    def validate_new_units_section(cls, v):
        if v and (not v.units or len(v.units) == 0):
            raise ValueError("If new_units section is provided, it must contain at least one unit")
        return v
    
    @validator('existing_units_updates')
    def validate_existing_units_section(cls, v):
        if v and (not v.updates or len(v.updates) == 0):
            raise ValueError("If existing_units_updates section is provided, it must contain at least one update")
        return v
    
    @validator('layout_positions')
    def validate_layout_positions_section(cls, v):
        if v and (not v.positions or len(v.positions) == 0):
            raise ValueError("If layout_positions section is provided, it must contain at least one position")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "new_units": {
                    "units": [
                        {
                            "temp_id": "temp_unit_1",
                            "unit_type": "us",
                            "definition": "New positive US unit",
                            "tipo": "positiva"
                        }
                    ],
                    "relationships": [
                        {
                            "temp_id": "temp_rel_1",
                            "from_temp_id": "temp_unit_1",
                            "to_temp_id": "temp_unit_2",
                            "relation_type": "copre"
                        }
                    ]
                },
                "existing_units_updates": {
                    "updates": {
                        "550e8400-e29b-41d4-a716-446655440000": {
                            "copre": ["US002", "US003"],
                            "taglia": []
                        }
                    }
                },
                "layout_positions": {
                    "positions": [
                        {
                            "unit_id": "US001",
                            "unit_type": "us",
                            "x": 150.5,
                            "y": 200.0
                        }
                    ]
                }
            }
        }


class HarrisMatrixAtomicSaveResponse(BaseModel):
    """Response schema for atomic Harris Matrix save operation."""
    
    success: bool = Field(..., description="Whether the atomic save was successful")
    message: str = Field(..., description="Detailed message about the operation result")
    site_id: UUID = Field(..., description="Site identifier")
    operation_results: Dict[str, Any] = Field(..., description="Detailed results for each operation type")
    unit_mapping: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from temporary IDs to actual unit IDs (for new units)"
    )
    validation_performed: bool = Field(..., description="Whether comprehensive validation was performed")
    transaction_rolled_back: bool = Field(..., description="Whether transaction was rolled back on failure")
    processing_time_ms: Optional[float] = Field(
        None,
        description="Total processing time in milliseconds"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="Processing warnings"
    )
    
    class Config:
        json_encoders = {
            UUID: str
        }
        schema_extra = {
            "example": {
                "success": True,
                "message": "Atomic save completed successfully: 2 new units, 1 updated units, 3 layout positions",
                "site_id": "123e4567-e89b-12d3-a456-426614174000",
                "operation_results": {
                    "new_units_created": 2,
                    "existing_units_updated": 1,
                    "layout_positions_saved": 3,
                    "relationships_processed": 1
                },
                "unit_mapping": {
                    "temp_unit_1": "550e8400-e29b-41d4-a716-446655440001",
                    "temp_unit_2": "550e8400-e29b-41d4-a716-446655440002"
                },
                "validation_performed": True,
                "transaction_rolled_back": False,
                "processing_time_ms": 245.7,
                "warnings": []
            }
        }


class AtomicSaveHealthCheckResult(BaseModel):
    """Response schema for atomic save health check."""
    
    status: str = Field(..., description="Health status: 'healthy' or 'unhealthy'")
    site_id: UUID = Field(..., description="Site identifier that was checked")
    database_connection: str = Field(..., description="Database connection status")
    transaction_support: str = Field(..., description="Transaction support status")
    message: str = Field(..., description="Health check message")
    error: Optional[str] = Field(None, description="Error details if unhealthy")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat()
        }


# Error detail schemas for enhanced error responses

class AtomicSaveErrorDetail(BaseModel):
    """Detailed error information for atomic save failures."""
    
    step: str = Field(..., description="Which step failed")
    operation_type: str = Field(..., description="Type of operation that failed")
    error_type: str = Field(..., description="Category of error")
    details: str = Field(..., description="Detailed error message")
    suggestion: str = Field(..., description="Suggested resolution")
    affected_items: Optional[List[str]] = Field(
        None,
        description="List of affected items (units, relationships, etc.)"
    )
    rollback_applied: bool = Field(True, description="Whether rollback was applied")


class AtomicSaveTransactionInfo(BaseModel):
    """Information about the atomic transaction."""
    
    transaction_id: Optional[str] = Field(None, description="Transaction identifier")
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = Field(None, description="Transaction completion time")
    duration_ms: Optional[float] = Field(None, description="Transaction duration in milliseconds")
    steps_completed: List[str] = Field(default_factory=list, description="Completed steps before failure")
    failed_step: Optional[str] = Field(None, description="Step that caused failure")
    rollback_successful: bool = Field(True, description="Whether rollback was successful")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
# ===== COMPREHENSIVE VALIDATION AND ERROR HANDLING FIX #1 =====

class HarrisMatrixCreateRequest(BaseModel):
    """Enhanced request schema with comprehensive validation"""
    
    site_id: str
    units: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    
    @validator('site_id')
    def validate_site_id(cls, v):
        if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', v):
            raise ValueError('Invalid site_id format - must be UUID')
        return v
    
    @validator('units')
    def validate_units(cls, v):
        if not v:
            raise ValueError('At least one unit must be provided')
        
        # Check for duplicate codes
        codes = []
        for unit in v:
            if 'code' not in unit:
                raise ValueError('Each unit must have a code')
            code = unit['code']
            if code in codes:
                raise ValueError(f'Duplicate unit code: {code}')
            codes.append(code)
        
        return v
    
    @validator('relationships')
    def validate_relationships(cls, v):
        # Validate relationship types
        valid_types = ['copre', 'coperto_da', 'taglia', 'tagliatoda', 
                      'riempie', 'riempito_da', 'siappoggiaa', 'glisiappoggia',
                      'silegaa', 'ugualea']
        
        for rel in v:
            if 'relationship_type' not in rel:
                raise ValueError('Each relationship must have a relationship_type')
            
            rel_type = rel['relationship_type']
            if rel_type not in valid_types:
                raise ValueError(f'Invalid relationship_type: {rel_type}. Valid types: {valid_types}')
        
        return v


class HarrisMatrixValidationError(BaseModel):
    """Standardized validation error response"""
    
    error_type: str
    field: Optional[str] = None
    message: str
    severity: str = "error"  # error, warning, info
    suggestions: Optional[List[str]] = None