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
    
    temp_id: str = Field(..., description="Temporary identifier for client-side mapping")
    unit_type: UnitTypeEnum = Field(..., description="Type of unit (us or usm)")
    code: Optional[str] = Field(None, description="Unit code (auto-generated if not provided)")
    definition: Optional[str] = Field(None, description="Unit definition")
    tipo: Optional[TipoUSEnum] = Field(None, description="US type (positive/negative)")
    localita: Optional[str] = Field(None, description="Location")
    datazione: Optional[str] = Field(None, description="Dating information")
    periodo: Optional[str] = Field(None, description="Period")
    fase: Optional[str] = Field(None, description="Phase")
    affidabilita_stratigrafica: Optional[str] = Field(None, description="Stratigraphic reliability")
    tecnica_costruttiva: Optional[str] = Field(None, description="Construction technique (USM only)")
    created_by: Optional[str] = Field(None, description="User ID who created the unit")
    
    @validator('code')
    def validate_code(cls, v):
        if v:
            v = v.strip().upper()
            if not v:
                raise ValueError('Unit code cannot be empty')
        return v
    
    class Config:
        json_encoders = {
            UUID: str
        }


class HarrisMatrixBulkCreateRelationship(BaseModel):
    """Schema for creating a single relationship in bulk operations."""
    
    temp_id: str = Field(..., description="Temporary identifier for client-side mapping")
    from_temp_id: str = Field(..., description="Temporary ID of source unit")
    to_temp_id: str = Field(..., description="Temporary ID of target unit")
    relation_type: StratigraphicRelation = Field(..., description="Type of relationship")
    
    @validator('from_temp_id', 'to_temp_id')
    def validate_temp_ids(cls, v):
        if not v or not v.strip():
            raise ValueError('Temporary IDs cannot be empty')
        return v.strip()


class HarrisMatrixBulkCreateRequest(BaseModel):
    """Schema for bulk creating units and relationships."""
    
    units: List[HarrisMatrixBulkCreateUnit] = Field(..., min_items=1, description="Units to create")
    relationships: List[HarrisMatrixBulkCreateRelationship] = Field(
        default=[], description="Relationships to create"
    )
    
    @validator('units')
    def validate_unique_temp_ids(cls, v):
        temp_ids = [unit.temp_id for unit in v]
        if len(temp_ids) != len(set(temp_ids)):
            raise ValueError('Duplicate temporary IDs found in units')
        return v
    
    @validator('relationships')
    def validate_relationship_temp_ids(cls, v, values):
        if 'units' not in values:
            return v
            
        unit_temp_ids = {unit.temp_id for unit in values['units']}
        
        for rel in v:
            if rel.from_temp_id not in unit_temp_ids:
                raise ValueError(f"Source unit temp_id '{rel.from_temp_id}' not found in units")
            if rel.to_temp_id not in unit_temp_ids:
                raise ValueError(f"Target unit temp_id '{rel.to_temp_id}' not found in units")
        
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
    units: List[Dict[str, Any]] = Field(..., description="Created units data")
    relationships: List[Dict[str, Any]] = Field(..., description="Created relationships data")
    validation_result: Optional[HarrisMatrixValidationResult] = Field(
        None, description="Validation results"
    )


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