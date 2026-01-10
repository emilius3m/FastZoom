# app/schemas/photos.py - Pydantic schemas for Photo API validation and documentation

from fastapi import Form
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from uuid import UUID
from datetime import datetime


class PhotoUploadRequest(BaseModel):
    """
    Schema for photo upload request with comprehensive archaeological metadata.
    This replaces multiple Form() parameters with a structured, validated approach.
    """
    
    # Basic metadata
    title: Optional[str] = Field(None, description="Photo title")
    description: Optional[str] = Field(None, description="Photo description")
    photo_type: Optional[str] = Field(None, description="Photo type (general, detail, context, etc.)")
    photographer: Optional[str] = Field(None, description="Photographer name")
    keywords: Optional[Union[str, List[str]]] = Field(None, description="Keywords (string or comma-separated)")
    
    # Archaeological context
    inventory_number: Optional[str] = Field(None, description="Museum inventory number")
    catalog_number: Optional[str] = Field(None, description="Catalog number")
    excavation_area: Optional[str] = Field(None, description="Excavation area")
    stratigraphic_unit: Optional[str] = Field(None, description="Stratigraphic unit reference")
    grid_square: Optional[str] = Field(None, description="Grid square location")
    depth_level: Optional[float] = Field(None, description="Depth level in meters")
    find_date: Optional[str] = Field(None, description="Date of discovery (ISO format)")
    finder: Optional[str] = Field(None, description="Person who found the item")
    excavation_campaign: Optional[str] = Field(None, description="Excavation campaign name")
    
    # Material and object information
    material: Optional[str] = Field(None, description="Material type")
    material_details: Optional[str] = Field(None, description="Material specific details")
    object_type: Optional[str] = Field(None, description="Type of object")
    object_function: Optional[str] = Field(None, description="Object function/use")
    
    # Physical dimensions
    length_cm: Optional[float] = Field(None, ge=0, description="Length in centimeters")
    width_cm: Optional[float] = Field(None, ge=0, description="Width in centimeters")
    height_cm: Optional[float] = Field(None, ge=0, description="Height in centimeters")
    diameter_cm: Optional[float] = Field(None, ge=0, description="Diameter in centimeters")
    weight_grams: Optional[float] = Field(None, ge=0, description="Weight in grams")
    
    # Chronology and dating
    chronology_period: Optional[str] = Field(None, description="Chronological period")
    chronology_culture: Optional[str] = Field(None, description="Associated culture")
    dating_from: Optional[str] = Field(None, description="Dating start year or period")
    dating_to: Optional[str] = Field(None, description="Dating end year or period")
    dating_notes: Optional[str] = Field(None, description="Dating interpretation notes")
    
    # Conservation information
    conservation_status: Optional[str] = Field(None, description="Conservation status")
    conservation_notes: Optional[str] = Field(None, description="Conservation details")
    restoration_history: Optional[str] = Field(None, description="Restoration history")
    
    # References and documentation
    bibliography: Optional[str] = Field(None, description="Bibliographic references")
    comparative_references: Optional[str] = Field(None, description="Comparative examples")
    external_links: Optional[Union[str, List[str]]] = Field(None, description="External reference links")
    
    # Rights and licensing
    copyright_holder: Optional[str] = Field(None, description="Copyright holder")
    license_type: Optional[str] = Field(None, description="License type")
    usage_rights: Optional[str] = Field(None, description="Usage restrictions")
    
    # Queue control
    use_queue: Optional[bool] = Field(False, description="Use queue processing")
    priority: Optional[str] = Field("normal", description="Processing priority")
    
    @validator('find_date', 'dating_from', 'dating_to')
    def validate_date_fields(cls, v):
        """Validate date fields can be parsed as ISO dates or years (for archaeological context)"""
        if v is None or v == '' or v == 'null' or v == 'None':
            return None
        try:
            # Try ISO format first
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            try:
                # Try YYYY-MM-DD format
                datetime.strptime(v, '%Y-%m-%d')
                return v
            except ValueError:
                try:
                    # Try YYYY format or negative years (common for archaeological dating)
                    # Handle BCE formats like "3000 BCE"
                    if isinstance(v, str) and v.upper().endswith(' BCE'):
                        try:
                            year = int(v.replace(' BCE', '').replace(' bce', '').strip())
                            if -9999 <= year <= 9999:
                                return v
                            else:
                                raise ValueError(f"Year out of range: {year}")
                        except ValueError:
                            pass
                    
                    year = int(v)
                    if -9999 <= year <= 9999:
                        return v
                    else:
                        raise ValueError(f"Year out of range: {year}")
                except ValueError:
                    raise ValueError(f"Invalid date format: {v}. Use ISO format, YYYY-MM-DD, YYYY, or BCE years")
    
    @validator('keywords')
    def validate_keywords(cls, v):
        """Normalize keywords to string format"""
        if v is None:
            return None
        if isinstance(v, list):
            return ', '.join(str(k).strip() for k in v if str(k).strip())
        return str(v)
    
    @validator('external_links')
    def validate_external_links(cls, v):
        """Normalize external links to JSON string"""
        if v is None:
            return None
        if isinstance(v, list):
            return str(v)  # Will be JSON encoded later
        return str(v)
    
    @validator('priority')
    def validate_priority(cls, v):
        """Validate priority field"""
        if v is None or v == '' or v == 'null' or v == 'None':
            return 'normal'
        allowed_priorities = ['critical', 'high', 'normal', 'low', 'bulk']
        if v.lower() not in allowed_priorities:
            raise ValueError(f"Priority must be one of: {allowed_priorities}")
        return v.lower()
    
    @validator('*', pre=True)
    def convert_empty_strings_to_none(cls, v):
        """Convert empty strings and null-like values to None"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.strip() == '' or v.lower() in ['null', 'none', 'undefined']:
                return None
        return v
    
    class Config:
        extra = "ignore"  # Allow backward compatibility with additional fields
        
        json_schema_extra = {  # Updated for Pydantic V2 compatibility
            "example": {
                "title": "Decorated pottery fragment from Sector A",
                "description": "Fine example of decorated ceramic with geometric patterns, recovered from context B3 during systematic excavation",
                "photo_type": "detail",
                "photographer": "Dr. Maria Rossi",
                "keywords": "pottery, decoration, ceramic, bronze age",
                
                # Archaeological context
                "inventory_number": "INV-2023-001",
                "catalog_number": "CAT-2023-A-042",
                "excavation_area": "Sector A",
                "stratigraphic_unit": "US 1234",
                "grid_square": "A3-B4",
                "depth_level": 2.5,
                "find_date": "2023-05-15",
                "finder": "Prof. John Smith",
                "excavation_campaign": "Spring Campaign 2023",
                
                # Material and object information
                "material": "ceramic",
                "material_details": "Fine paste, fired at high temperature",
                "object_type": "vessel fragment",
                "object_function": "storage container",
                
                # Physical dimensions
                "length_cm": 8.5,
                "width_cm": 6.2,
                "height_cm": 1.1,
                "diameter_cm": None,
                "weight_grams": 45.7,
                
                # Chronology and dating
                "chronology_period": "Late Bronze Age",
                "chronology_culture": "Terramare culture",
                "dating_from": "-1200",
                "dating_to": "-1100",
                "dating_notes": "Based on stratigraphic context and typology (Late Bronze Age, approx. 1200-1100 BCE)",
                
                # Conservation information
                "conservation_status": "good",
                "conservation_notes": "Minor surface abrasion, stable condition",
                "restoration_history": "No restoration performed",
                
                # References and documentation
                "bibliography": "Rossi, M. (2023). Archaeological Survey of Sector A. Journal of Excavation Studies, 45(2), 123-145.",
                "comparative_references": "Similar specimens found at nearby sites",
                "external_links": "https://example.com/catalog/12345",
                
                # Rights and licensing
                "copyright_holder": "Archaeological Institute",
                "license_type": "CC BY-SA 4.0",
                "usage_rights": "Educational and research purposes",
                
                # Queue control
                "use_queue": True,
                "priority": "normal"
            }
        }


class PhotoUpdateRequest(BaseModel):
    """
    Schema for photo update operations with field validation
    """
    
    # Updatable basic fields
    title: Optional[str] = Field(None, description="Photo title")
    description: Optional[str] = Field(None, description="Photo description")
    keywords: Optional[Union[str, List[str]]] = Field(None, description="Keywords (string or list)")
    photo_type: Optional[str] = Field(None, description="Photo type")
    photographer: Optional[str] = Field(None, description="Photographer name")
    
    # Archaeological fields
    inventory_number: Optional[str] = Field(None, description="Museum inventory number")
    catalog_number: Optional[str] = Field(None, description="Catalog number")
    excavation_area: Optional[str] = Field(None, description="Excavation area")
    stratigraphic_unit: Optional[str] = Field(None, description="Stratigraphic unit")
    grid_square: Optional[str] = Field(None, description="Grid square")
    depth_level: Optional[float] = Field(None, ge=0, description="Depth level")
    find_date: Optional[str] = Field(None, description="Date of discovery")
    finder: Optional[str] = Field(None, description="Finder name")
    excavation_campaign: Optional[str] = Field(None, description="Excavation campaign")
    
    # Material and object
    material: Optional[str] = Field(None, description="Material type")
    material_details: Optional[str] = Field(None, description="Material details")
    object_type: Optional[str] = Field(None, description="Object type")
    object_function: Optional[str] = Field(None, description="Object function")
    
    # Dimensions
    length_cm: Optional[float] = Field(None, ge=0, description="Length in cm")
    width_cm: Optional[float] = Field(None, ge=0, description="Width in cm")
    height_cm: Optional[float] = Field(None, ge=0, description="Height in cm")
    diameter_cm: Optional[float] = Field(None, ge=0, description="Diameter in cm")
    weight_grams: Optional[float] = Field(None, ge=0, description="Weight in grams")
    
    # Chronology
    chronology_period: Optional[str] = Field(None, description="Chronological period")
    chronology_culture: Optional[str] = Field(None, description="Associated culture")
    dating_from: Optional[str] = Field(None, description="Dating start")
    dating_to: Optional[str] = Field(None, description="Dating end")
    dating_notes: Optional[str] = Field(None, description="Dating notes")
    
    # Conservation
    conservation_status: Optional[str] = Field(None, description="Conservation status")
    conservation_notes: Optional[str] = Field(None, description="Conservation notes")
    restoration_history: Optional[str] = Field(None, description="Restoration history")
    
    # References
    bibliography: Optional[str] = Field(None, description="Bibliographic references")
    comparative_references: Optional[str] = Field(None, description="Comparative references")
    external_links: Optional[Union[str, List[str]]] = Field(None, description="External links")
    
    # Rights
    copyright_holder: Optional[str] = Field(None, description="Copyright holder")
    license_type: Optional[str] = Field(None, description="License type")
    usage_rights: Optional[str] = Field(None, description="Usage rights")
    
    # Notes
    validation_notes: Optional[str] = Field(None, description="Validation notes")
    
    @validator('find_date', 'dating_from', 'dating_to')
    def validate_date_fields(cls, v):
        """Validate date fields - supports ISO dates, YYYY-MM-DD, or YYYY (archaeological)"""
        if v is None or v == '' or v == 'null' or v == 'None':
            return None
        try:
            # Try ISO format first
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            try:
                # Try YYYY-MM-DD format
                datetime.strptime(v, '%Y-%m-%d')
                return v
            except ValueError:
                try:
                    # Try YYYY format (common for archaeological dating)
                    year = int(v)
                    if 1 <= year <= 9999:
                        return v
                    else:
                        raise ValueError(f"Year out of range: {year}")
                except ValueError:
                    raise ValueError(f"Invalid date format: {v}. Use ISO format, YYYY-MM-DD, or YYYY")
    
    @validator('keywords')
    def validate_keywords(cls, v):
        """Normalize keywords to string format"""
        if v is None:
            return None
        if isinstance(v, list):
            return ', '.join(str(k).strip() for k in v if str(k).strip())
        return str(v)
    
    @validator('external_links')
    def validate_external_links(cls, v):
        """Normalize external links to JSON string"""
        if v is None:
            return None
        if isinstance(v, list):
            return str(v)  # Will be JSON encoded later
        return str(v)


class BulkUpdateRequest(BaseModel):
    """
    Schema for bulk update operations on multiple photos
    """
    
    photo_ids: List[UUID] = Field(..., description="List of photo IDs to update")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Metadata to apply to all photos")
    add_tags: List[str] = Field(default_factory=list, description="Tags to add to all photos")
    remove_tags: List[str] = Field(default_factory=list, description="Tags to remove from all photos")
    
    @validator('photo_ids')
    def validate_photo_ids(cls, v):
        """Ensure at least one photo ID is provided"""
        if not v:
            raise ValueError("At least one photo ID must be provided")
        return v
    
    class Config:
        schema_extra = {
            "example": {
                "photo_ids": ["550e8400-e29b-41d4-a716-446655440000", "550e8400-e29b-41d4-a716-446655440001"],
                "metadata": {
                    "conservation_status": "good",
                    "photo_type": "detail"
                },
                "add_tags": ["excavation", "pottery"],
                "remove_tags": ["temporary"]
            }
        }


class BulkDeleteRequest(BaseModel):
    """
    Schema for bulk delete operations on multiple photos
    """
    
    photo_ids: List[UUID] = Field(..., description="List of photo IDs to delete")
    confirm: bool = Field(False, description="Confirmation flag for destructive operation")
    
    @validator('photo_ids')
    def validate_photo_ids(cls, v):
        """Ensure at least one photo ID is provided"""
        if not v:
            raise ValueError("At least one photo ID must be provided")
        return v
    
    @validator('confirm')
    def validate_confirmation(cls, v, values):
        """Require confirmation for bulk delete operations"""
        if not v:
            raise ValueError("Bulk delete requires explicit confirmation (confirm: true)")
        return v


class PhotoQueryFilters(BaseModel):
    """
    Schema for photo query parameters with comprehensive archaeological filtering
    """
    
    # Basic filters
    search: Optional[str] = Field(None, description="Search in filename, title, description")
    photo_type: Optional[str] = Field(None, description="Photo type filter")
    
    # Archaeological filters
    material: Optional[str] = Field(None, description="Material type filter")
    conservation_status: Optional[str] = Field(None, description="Conservation status filter")
    excavation_area: Optional[str] = Field(None, description="Excavation area filter")
    stratigraphic_unit: Optional[str] = Field(None, description="Stratigraphic unit filter")
    chronology_period: Optional[str] = Field(None, description="Chronological period filter")
    object_type: Optional[str] = Field(None, description="Object type filter")
    
    # Status filters
    is_published: Optional[bool] = Field(None, description="Published status filter")
    is_validated: Optional[bool] = Field(None, description="Validation status filter")
    has_deep_zoom: Optional[bool] = Field(None, description="Deep zoom availability filter")
    
    # Date range filters
    upload_date_from: Optional[str] = Field(None, description="Upload date start (ISO)")
    upload_date_to: Optional[str] = Field(None, description="Upload date end (ISO)")
    photo_date_from: Optional[str] = Field(None, description="Photo date start (ISO)")
    photo_date_to: Optional[str] = Field(None, description="Photo date end (ISO)")
    find_date_from: Optional[str] = Field(None, description="Find date start (ISO)")
    find_date_to: Optional[str] = Field(None, description="Find date end (ISO)")
    
    # Dimension filters
    min_width: Optional[int] = Field(None, ge=0, description="Minimum width in pixels")
    max_width: Optional[int] = Field(None, ge=0, description="Maximum width in pixels")
    min_height: Optional[int] = Field(None, ge=0, description="Minimum height in pixels")
    max_height: Optional[int] = Field(None, ge=0, description="Maximum height in pixels")
    min_file_size_mb: Optional[float] = Field(None, ge=0, description="Minimum file size in MB")
    max_file_size_mb: Optional[float] = Field(None, ge=0, description="Maximum file size in MB")
    
    # Metadata presence filters
    has_inventory: Optional[bool] = Field(None, description="Has inventory number filter")
    has_description: Optional[bool] = Field(None, description="Has description filter")
    has_photographer: Optional[bool] = Field(None, description="Has photographer filter")
    
    # Sorting
    sort_by: Optional[str] = Field("created_desc", description="Sort order")
    
    @validator('sort_by')
    def validate_sort_by(cls, v):
        """Validate sort_by parameter"""
        allowed_sorts = [
            "created_desc", "created_asc",
            "filename_asc", "filename_desc", 
            "size_desc", "size_asc",
            "photo_date_desc", "photo_date_asc",
            "inventory_asc", "inventory_desc",
            "material_asc", "find_date_desc"
        ]
        if v not in allowed_sorts:
            raise ValueError(f"Invalid sort_by. Allowed values: {allowed_sorts}")
        return v
    
    @validator('min_file_size_mb', 'max_file_size_mb')
    def validate_file_sizes(cls, v):
        """Validate file size values"""
        if v is not None and v <= 0:
            raise ValueError("File size values must be positive")
        return v


class PhotoResponse(BaseModel):
    """
    Standardized photo response schema
    """
    
    id: str
    site_id: str
    filename: str
    original_filename: Optional[str]
    title: Optional[str]
    description: Optional[str]
    photo_type: Optional[str]
    material: Optional[str]
    conservation_status: Optional[str]
    width: Optional[int]
    height: Optional[int]
    file_size: Optional[int]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    # URLs
    thumbnail_url: str
    full_url: str
    file_url: str
    download_url: str
    
    # Archaeological metadata
    inventory_number: Optional[str]
    excavation_area: Optional[str]
    stratigraphic_unit: Optional[str]
    chronology_period: Optional[str]
    object_type: Optional[str]
    
    # Additional metadata
    tags: List[str] = Field(default_factory=list)
    photographer: Optional[str]
    photo_date: Optional[datetime]
    has_deep_zoom: bool = False
    
    class Config:
        from_attributes = True
        schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "filename": "photo_001.jpg",
                "title": "Excavation photo",
                "photo_type": "context",
                "width": 1920,
                "height": 1080,
                "file_size": 2048576,
                "thumbnail_url": "/api/v1/photos/550e8400-e29b-41d4-a716-446655440000/thumbnail",
                "full_url": "/api/v1/photos/550e8400-e29b-41d4-a716-446655440000/full",
                "file_url": "/api/v1/photos/550e8400-e29b-41d4-a716-446655440000/view",
                "download_url": "/api/v1/photos/550e8400-e29b-41d4-a716-446655440000/download"
            }
        }


class BulkOperationResponse(BaseModel):
    """
    Standardized response for bulk operations
    """
    
    message: str
    operation_count: int
    successful_count: int
    failed_count: int = 0
    operation_type: str
    timestamp: str
    
    # Optional details
    updated_fields: Optional[List[str]] = None
    failed_items: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        schema_extra = {
            "example": {
                "message": "Bulk update completed successfully",
                "operation_count": 5,
                "successful_count": 5,
                "failed_count": 0,
                "operation_type": "bulk_update",
                "timestamp": "2023-11-17T10:30:00Z",
                "updated_fields": ["conservation_status", "photo_type"]
            }
        }