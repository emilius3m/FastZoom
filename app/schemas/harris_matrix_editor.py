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
    
    updates: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Map of unit_id -> sequenzafisica dictionary with relationship types as keys"
    )
    
    @validator('updates')
    def validate_sequenza_fisica_structure(cls, v):
        """Validate that each sequenza_fisica has the correct structure."""
        valid_relationship_keys = {
            'uguale_a', 'si_lega_a', 'gli_si_appoggia', 'si_appoggia_a',
            'coperto_da', 'copre', 'tagliato_da', 'taglia', 'riempito_da', 'riempie'
        }
        
        for unit_id, unit_data in v.items():
            if not isinstance(unit_data, dict):
                raise ValueError(f"Data for unit {unit_id} must be a dictionary")
            
            # Check for sequenza_fisica key
            if 'sequenza_fisica' not in unit_data:
                raise ValueError(f"Missing 'sequenza_fisica' key for unit {unit_id}")
            
            sequenza_fisica = unit_data['sequenza_fisica']
            if not isinstance(sequenza_fisica, dict):
                raise ValueError(f"sequenza_fisica for unit {unit_id} must be a dictionary")
            
            # Check for invalid keys in sequenza_fisica
            invalid_keys = set(sequenza_fisica.keys()) - valid_relationship_keys
            if invalid_keys:
                raise ValueError(f"Invalid relationship types for unit {unit_id}: {invalid_keys}. Valid types: {valid_relationship_keys}")
            
            # Validate that all values are lists of strings
            for rel_type, targets in sequenza_fisica.items():
                if targets is None:
                    v[unit_id]['sequenza_fisica'][rel_type] = []
                elif not isinstance(targets, list):
                    raise ValueError(f"Relationship targets for {rel_type} in unit {unit_id} must be a list")
                else:
                    # Ensure all items in the list are strings
                    for i, target in enumerate(targets):
                        if not isinstance(target, str):
                            raise ValueError(f"Target {i} for {rel_type} in unit {unit_id} must be a string")
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "updates": {
                    "550e8400-e29b-41d4-a716-446655440000": {
                        "uguale_a": [],
                        "si_lega_a": [],
                        "gli_si_appoggia": [],
                        "si_appoggia_a": [],
                        "coperto_da": [],
                        "copre": ["US002", "US003"],
                        "tagliato_da": [],
                        "taglia": [],
                        "riempito_da": [],
                        "riempie": ["US001usm"]
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
    
    # NEW: Metadata for recovery and mapping tracking
    session_id: Optional[str] = Field(
        default=None,
        description="Session identifier for mapping tracking and recovery",
        min_length=1,
        max_length=255,
        pattern=r'^[a-zA-Z0-9_-]+$',
        example="atomic-save-20231209103000-user123"
    )
    transaction_id: Optional[str] = Field(
        default=None,
        description="Transaction identifier for audit trail",
        min_length=1,
        max_length=255,
        pattern=r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$',
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    created_units_count: Optional[int] = Field(
        default=0,
        description="Number of units created in this operation",
        ge=0,
        example=5
    )
    checkpoint_time: Optional[datetime] = Field(
        default=None,
        description="Timestamp when the operation completed",
        example="2023-12-09T10:30:45.123Z"
    )
    mapping_status: Optional[str] = Field(
        default="unknown",
        description="Status of mapping operations (committed, partial, failed, unknown)",
        pattern=r'^(committed|partial|failed|unknown)$',
        example="committed"
    )
    
    @validator('session_id')
    def validate_session_id(cls, v):
        if v and len(v.strip()) == 0:
            raise ValueError('session_id cannot be empty if provided')
        return v.strip() if v else v
    
    @validator('transaction_id')
    def validate_transaction_id(cls, v):
        if v:
            v = v.strip().lower()
            # Basic UUID format validation
            import re
            if not re.match(r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$', v):
                raise ValueError('transaction_id must be a valid UUID format')
        return v
    
    @validator('checkpoint_time')
    def validate_checkpoint_time(cls, v):
        if v and v > datetime.utcnow():
            raise ValueError('checkpoint_time cannot be in the future')
        return v
    
    class Config:
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
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
                "warnings": [],
                # NEW: Enhanced example with mapping metadata
                "session_id": "atomic-save-20231209103000-user123",
                "transaction_id": "550e8400-e29b-41d4-a716-446655440000",
                "created_units_count": 2,
                "checkpoint_time": "2023-12-09T10:30:45.123Z",
                "mapping_status": "committed"
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


# Enhanced error response schemas for duplicate detection validation

class HarrisMatrixOperationError(BaseModel):
    """Enhanced error response schema for Harris Matrix operations"""
    
    error_type: str = Field(..., description="Type of error: 'duplicate_codes', 'invalid_relations', 'cycle_detected'")
    message: str = Field(..., description="Main error message")
    details: Dict[str, Any] = Field(..., description="Detailed error information")
    conflicts: Optional[List[Dict]] = Field(None, description="Specific conflict details")
    recovery_suggestions: Optional[List[str]] = Field(None, description="Suggestions for recovery")
    severity: str = Field(default="error", description="Error severity: 'error', 'warning', 'info'")
    affected_items: Optional[List[str]] = Field(None, description="List of affected items")
    
    class Config:
        schema_extra = {
            "example": {
                "error_type": "duplicate_codes",
                "message": "Duplicate unit codes detected",
                "details": {
                    "duplicates": ["US001", "US002"],
                    "conflicts": {
                        "US001": {
                            "id": "550e8400-e29b-41d4-a716-446655440001",
                            "unit_type": "UnitStratigrafica",
                            "description": "Existing stratigraphic unit"
                        }
                    }
                },
                "conflicts": [
                    {
                        "code": "US001",
                        "existing_id": "550e8400-e29b-41d4-a716-446655440001",
                        "existing_type": "UnitStratigrafica"
                    }
                ],
                "recovery_suggestions": [
                    "Remove or rename duplicate codes: US001, US002",
                    "Consider using unit codes with prefixes (e.g., US1001, US1002)"
                ],
                "severity": "error",
                "affected_items": ["US001", "US002"]
            }
        }


class DuplicateCodeConflict(BaseModel):
    """Schema for duplicate unit code conflict information"""
    
    code: str = Field(..., description="The conflicting unit code")
    existing_unit: Dict[str, Any] = Field(..., description="Information about existing unit")
    suggestion: str = Field(..., description="Suggested resolution")
    severity: str = Field(default="error", description="Conflict severity")
    
    class Config:
        schema_extra = {
            "example": {
                "code": "US001",
                "existing_unit": {
                    "id": "550e8400-e29b-41d4-a716-446655440001",
                    "unit_type": "UnitStratigrafica",
                    "description": "Excavation trench unit",
                    "created_at": "2023-12-01T10:30:00Z"
                },
                "suggestion": "Use a different code like US1001 or modify the existing unit",
                "severity": "error"
            }
        }


class RelationshipValidationError(BaseModel):
    """Schema for relationship validation errors"""
    
    relationship_index: int = Field(..., description="Index of the invalid relationship")
    relationship_data: Dict[str, Any] = Field(..., description="The invalid relationship data")
    issues: List[str] = Field(..., description="List of issues found")
    missing_units: List[str] = Field(default_factory=list, description="Units that were not found")
    invalid_types: List[str] = Field(default_factory=list, description="Invalid relationship types")
    suggestions: List[str] = Field(default_factory=list, description="Suggestions for fixing the relationship")
    
    class Config:
        schema_extra = {
            "example": {
                "relationship_index": 0,
                "relationship_data": {
                    "from_temp_id": "temp_unit_1",
                    "to_temp_id": "temp_unit_999",
                    "relation_type": "copre"
                },
                "issues": ["Missing 'to_unit': temp_unit_999"],
                "missing_units": ["temp_unit_999"],
                "invalid_types": [],
                "suggestions": [
                    "Create the missing unit first: temp_unit_999",
                    "Remove the reference to non-existent unit"
                ]
            }
        }


class CycleDetectionResult(BaseModel):
    """Enhanced schema for cycle detection results"""
    
    has_cycles: bool = Field(..., description="Whether cycles were detected")
    cycle_paths: List[List[str]] = Field(..., description="List of detected cycle paths")
    affected_units: List[str] = Field(..., description="Units involved in cycles")
    cycle_count: int = Field(..., description="Total number of cycles detected")
    severity: str = Field(default="error", description="Cycle severity")
    suggestions: List[str] = Field(..., description="Suggestions for resolving cycles")
    analysis_time_ms: Optional[float] = Field(None, description="Time taken for cycle analysis")
    
    @validator('cycle_count')
    def validate_cycle_count(cls, v, values):
        if 'cycle_paths' in values and v != len(values['cycle_paths']):
            raise ValueError("cycle_count must match length of cycle_paths")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "has_cycles": True,
                "cycle_paths": [
                    ["US001", "US002", "US003", "US001"],
                    ["US004", "US005", "US004"]
                ],
                "affected_units": ["US001", "US002", "US003", "US004", "US005"],
                "cycle_count": 2,
                "severity": "error",
                "suggestions": [
                    "Review and remove cyclical relationships",
                    "Verify that 'earlier than' relationships are correct",
                    "Consider using 'equivalent to' relationships for units that represent the same context"
                ],
                "analysis_time_ms": 15.7
            }
        }


class BulkValidationResult(BaseModel):
    """Comprehensive validation result for bulk operations"""
    
    is_valid: bool = Field(..., description="Whether the bulk operation is valid")
    validation_time: float = Field(..., description="Total validation time in seconds")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="Validation errors")
    warnings: List[Dict[str, Any]] = Field(default_factory=list, description="Validation warnings")
    suggestions: List[str] = Field(default_factory=list, description="General suggestions")
    
    # Specific validation results
    duplicate_code_validation: Optional[Dict[str, Any]] = Field(None, description="Duplicate code validation results")
    relationship_validation: Optional[Dict[str, Any]] = Field(None, description="Relationship validation results")
    cycle_validation: Optional[Dict[str, Any]] = Field(None, description="Cycle detection results")
    
    can_proceed: bool = Field(..., description="Whether the operation can proceed")
    affected_items_count: int = Field(default=0, description="Number of items that would be affected")
    
    class Config:
        schema_extra = {
            "example": {
                "is_valid": False,
                "validation_time": 0.045,
                "errors": [
                    {
                        "type": "duplicate_codes",
                        "message": "Duplicate unit codes detected",
                        "details": {"duplicates": ["US001"]}
                    }
                ],
                "warnings": [],
                "suggestions": [
                    "Remove or rename duplicate codes: US001",
                    "Verify that the unit codes are correct for this site"
                ],
                "duplicate_code_validation": {
                    "is_valid": False,
                    "duplicates": ["US001"],
                    "conflicts": {
                        "US001": {
                            "id": "550e8400-e29b-41d4-a716-446655440001",
                            "unit_type": "UnitStratigrafica"
                        }
                    }
                },
                "relationship_validation": {"is_valid": True},
                "cycle_validation": {"is_valid": True},
                "can_proceed": False,
                "affected_items_count": 5
            }
        }


# ===== STALE REFERENCE VALIDATION SCHEMAS =====

class StaleReferenceDetail(BaseModel):
    """Schema for detailed stale reference information."""
    
    unit_id: str = Field(..., description="Unit ID with stale reference")
    reason: str = Field(
        ...,
        description="Reason for stale reference",
        pattern=r'^(not_found|soft_deleted|wrong_site|access_denied|invalid_format)$',
        example="not_found"
    )
    recovery_suggestion: str = Field(..., description="Suggested recovery action")
    additional_info: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional context information"
    )
    
    class Config:
        schema_extra = {
            "example": {
                "unit_id": "550e8400-e29b-41d4-a716-446655440001",
                "reason": "not_found",
                "recovery_suggestion": "Verify unit ID is correct and hasn't been deleted",
                "additional_info": {
                    "site_id": "123e4567-e89b-12d3-a456-426614174000",
                    "search_attempts": 3
                }
            }
        }


class StaleReferenceError(BaseModel):
    """Enhanced error response schema for stale reference validation."""
    
    error_type: str = Field(default="stale_references", description="Type of error")
    message: str = Field(..., description="Main error message")
    missing_units: List[str] = Field(
        default_factory=list,
        description="List of unit IDs that don't exist"
    )
    soft_deleted_units: List[str] = Field(
        default_factory=list,
        description="List of soft-deleted unit IDs"
    )
    invalid_site_units: List[str] = Field(
        default_factory=list,
        description="List of units from wrong site"
    )
    details: List[StaleReferenceDetail] = Field(
        default_factory=list,
        description="Detailed breakdown of stale reference issues"
    )
    recovery_suggestions: List[str] = Field(
        default_factory=list,
        description="Suggestions for recovery"
    )
    validation_time: Optional[float] = Field(
        None,
        description="Time taken for validation in seconds"
    )
    affected_operations: List[str] = Field(
        default_factory=list,
        description="Operations affected by stale references"
    )
    
    @validator('recovery_suggestions', always=True)
    def generate_default_suggestions(cls, v, values):
        if not v and any(values.get(key) for key in ['missing_units', 'soft_deleted_units', 'invalid_site_units']):
            suggestions = []
            
            if values.get('missing_units'):
                suggestions.extend([
                    "Remove references to non-existent units",
                    "Verify unit IDs are correct and haven't been deleted",
                    f"Check units: {', '.join(values['missing_units'])}"
                ])
            
            if values.get('soft_deleted_units'):
                suggestions.extend([
                    "Restore soft-deleted units if needed",
                    "Or remove references to soft-deleted units",
                    f"Soft-deleted units: {', '.join(values['soft_deleted_units'])}"
                ])
            
            if values.get('invalid_site_units'):
                suggestions.extend([
                    "Verify units belong to the correct site",
                    f"Wrong site units: {', '.join(values['invalid_site_units'])}"
                ])
            
            return suggestions
        
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "error_type": "stale_references",
                "message": "Some units cannot be updated due to stale references",
                "missing_units": [
                    "550e8400-e29b-41d4-a716-446655440001",
                    "550e8400-e29b-41d4-a716-446655440002"
                ],
                "soft_deleted_units": [
                    "550e8400-e29b-41d4-a716-446655440003"
                ],
                "invalid_site_units": [],
                "details": [
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440001",
                        "reason": "not_found",
                        "recovery_suggestion": "Check if unit was deleted or ID is correct"
                    },
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440003",
                        "reason": "soft_deleted",
                        "recovery_suggestion": "Restore unit or remove reference"
                    }
                ],
                "recovery_suggestions": [
                    "Remove references to non-existent units",
                    "Restore soft-deleted units if needed",
                    "Verify unit IDs are correct"
                ],
                "validation_time": 0.023,
                "affected_operations": ["bulk_update", "relationship_validation"]
            }
        }


class BulkUpdateResult(BaseModel):
    """Enhanced result schema for bulk update operations."""
    
    success: bool = Field(..., description="Whether the bulk update was successful")
    updated_count: int = Field(..., description="Number of units successfully updated", ge=0)
    total_requested: int = Field(..., description="Total number of units requested for update", ge=0)
    errors: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of errors encountered during update"
    )
    skipped_units: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Units that couldn't be updated with reasons"
    )
    validation_details: Dict[str, Any] = Field(
        ...,
        description="Detailed validation information from pre-update checks"
    )
    processing_time_ms: Optional[float] = Field(
        None,
        description="Total processing time in milliseconds"
    )
    operation_stats: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional operation statistics"
    )
    
    @validator('updated_count')
    def validate_updated_count(cls, v, values):
        total_requested = values.get('total_requested', v)
        if v > total_requested:
            raise ValueError('updated_count cannot exceed total_requested')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "success": True,
                "updated_count": 8,
                "total_requested": 10,
                "errors": [],
                "skipped_units": [
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440009",
                        "reason": "invalid_unit_object_type",
                        "unit_type": "<class 'str'>"
                    },
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440010",
                        "reason": "update_failed",
                        "error": "Database constraint violation"
                    }
                ],
                "validation_details": {
                    "stale_reference_validation": {
                        "is_valid": True,
                        "missing_ids": [],
                        "soft_deleted_ids": [],
                        "valid_ids": ["550e8400-e29b-41d4-a716-446655440001"],
                        "can_proceed": True,
                        "validation_time": 0.015
                    },
                    "integrity_validation": {
                        "is_valid": True,
                        "invalid_data": [],
                        "relationship_issues": [],
                        "can_proceed": True,
                        "validation_time": 0.008
                    }
                },
                "processing_time_ms": 245.7,
                "operation_stats": {
                    "validation_time_pct": 9.4,
                    "update_time_pct": 87.2,
                    "post_validation_time_pct": 3.4
                }
            }
        }


class BulkUpdateIntegrityResult(BaseModel):
    """Schema for comprehensive bulk update integrity validation results."""
    
    is_valid: bool = Field(..., description="Whether the bulk update passed integrity validation")
    missing_ids: List[str] = Field(
        default_factory=list,
        description="Unit IDs that don't exist"
    )
    soft_deleted_ids: List[str] = Field(
        default_factory=list,
        description="Soft-deleted unit IDs"
    )
    wrong_site_ids: List[str] = Field(
        default_factory=list,
        description="Units from wrong site"
    )
    valid_ids: List[str] = Field(
        default_factory=list,
        description="Valid unit IDs that can be updated"
    )
    invalid_data: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Units with invalid update data"
    )
    relationship_issues: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Issues in sequenza_fisica relationships"
    )
    can_proceed: bool = Field(..., description="Whether the operation can proceed")
    suggestions: List[str] = Field(
        default_factory=list,
        description="Suggestions for fixing issues"
    )
    validation_time: float = Field(..., description="Validation time in seconds", ge=0)
    
    @validator('can_proceed')
    def validate_can_proceed(cls, v, values):
        should_proceed = (
            len(values.get('missing_ids', [])) == 0 and
            len(values.get('soft_deleted_ids', [])) == 0 and
            len(values.get('wrong_site_ids', [])) == 0 and
            len(values.get('invalid_data', [])) == 0 and
            len(values.get('relationship_issues', [])) == 0
        )
        if v != should_proceed:
            raise ValueError('can_proceed must match the absence of validation issues')
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "is_valid": False,
                "missing_ids": ["550e8400-e29b-41d4-a716-446655440999"],
                "soft_deleted_ids": ["550e8400-e29b-41d4-a716-446655440888"],
                "wrong_site_ids": [],
                "valid_ids": ["550e8400-e29b-41d4-a716-446655440001"],
                "invalid_data": [
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440002",
                        "reason": "invalid_sequenza_format",
                        "suggestion": "sequenza_fisica must be a dictionary"
                    }
                ],
                "relationship_issues": [
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440003",
                        "referenced_code": "US999",
                        "relation_type": "copre",
                        "reason": "referenced_unit_not_found",
                        "suggestion": "Verify unit code 'US999' exists or remove reference"
                    }
                ],
                "can_proceed": False,
                "suggestions": [
                    "Remove references to non-existent units: US999",
                    "Fix invalid data format in sequenza_fisica updates"
                ],
                "validation_time": 0.042
            }
        }


class StaleReferenceValidationError(BaseModel):
    """Schema for stale reference validation errors in HTTP responses."""
    
    error_type: str = Field(default="stale_references", description="Error type identifier")
    message: str = Field(..., description="Error message describing the stale reference issue")
    missing_units: List[str] = Field(
        default_factory=list,
        description="List of missing unit IDs"
    )
    soft_deleted_units: List[str] = Field(
        default_factory=list,
        description="List of soft-deleted unit IDs"
    )
    invalid_site_units: List[str] = Field(
        default_factory=list,
        description="List of units from wrong site"
    )
    details: List[StaleReferenceDetail] = Field(
        default_factory=list,
        description="Detailed breakdown of issues"
    )
    recovery_suggestions: List[str] = Field(
        default_factory=list,
        description="Actionable suggestions for recovery"
    )
    validation_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Context about the validation operation"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    operation_id: Optional[str] = Field(
        None,
        description="Unique identifier for the operation that failed"
    )
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        schema_extra = {
            "example": {
                "error_type": "stale_references",
                "message": "References to non-existent units detected in bulk update operation",
                "missing_units": ["550e8400-e29b-41d4-a716-446655440999"],
                "soft_deleted_units": [],
                "invalid_site_units": [],
                "details": [
                    {
                        "unit_id": "550e8400-e29b-41d4-a716-446655440999",
                        "reason": "not_found",
                        "recovery_suggestion": "Verify unit ID is correct and hasn't been deleted"
                    }
                ],
                "recovery_suggestions": [
                    "Remove references to non-existent units",
                    "Verify unit IDs are correct",
                    "Check if units were recently deleted"
                ],
                "validation_context": {
                    "operation": "bulk_update_sequenza_fisica",
                    "site_id": "123e4567-e89b-12d3-a456-426614174000",
                    "total_units_requested": 5
                },
                "timestamp": "2023-12-09T10:30:45.123Z",
                "operation_id": "bulk-update-20231209103045"
            }
        }