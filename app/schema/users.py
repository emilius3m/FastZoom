# app/schemas/users.py - SCHEMI PYDANTIC (il tuo file attuale)
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional
from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

# ===== SCHEMI USER SENZA FASTAPI-USERS =====

class UserBase(BaseModel):
    """Schema base per User"""
    email: EmailStr
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False

class UserCreate(BaseModel):
    """Schema per creazione utente"""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password minimo 8 caratteri")
    is_active: bool = True
    is_superuser: bool = False
    is_verified: bool = False

class UserUpdate(BaseModel):
    """Schema per aggiornamento utente"""
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=8)
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    is_verified: Optional[bool] = None

class UserRead(BaseModel):
    """Schema per lettura utente (risposta API)"""
    id: UUID4
    email: EmailStr
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class UserLogin(BaseModel):
    """Schema per login"""
    email: EmailStr
    password: str

class UserLoginResponse(BaseModel):
    """Schema per risposta login"""
    access_token: str
    token_type: str = "bearer"
    user: UserRead
    sites_count: int
    user_type: str

# ===== SCHEMI ARCHEOLOGICI =====

class SitePermissionRead(BaseModel):
    """Schema per permessi sui siti"""
    id: UUID4
    site_id: UUID4
    permission_level: str
    is_active: bool
    notes: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

class UserWithSitesRead(UserRead):
    """Schema utente con siti accessibili"""
    accessible_sites: List[Dict[str, Any]] = []
    sites_count: int = 0

# ===== MANTIENI I TUOI SCHEMI ESISTENTI =====

# Il resto del tuo file (RoleBase, ProfileBase, etc.) rimane uguale...
PasswordStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8)]

class RoleBase(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    role_name: str = Field(
        ...,
        title="Role Name",
        description="Role Name",
        min_length=3,
        max_length=50,
    )
    role_desc: Annotated[
        Optional[str],
        Field(
            min_length=5,
            max_length=200,
            examples=["Role description is provided here"],
            title="Role Description",
            default=None,
        ),
    ]
    role_id: Optional[UUID4] = Field(
        default_factory=uuid.uuid4,
        title="Role ID",
        description="Role ID",
    )

class ProfileBase(BaseModel):
    """Schema per profilo utente"""
    model_config = ConfigDict(hide_input_in_errors=True)
    first_name: str = Field(..., title="First Name", min_length=3, max_length=120)
    last_name: str = Field(..., title="Last Name", min_length=3, max_length=120)
    gender: Optional[str] = Field(None, min_length=3, max_length=10, title="Gender")
    date_of_birth: Optional[datetime] = Field(None, title="Date of Birth")
    city: Optional[str] = Field(None, min_length=0, max_length=50, title="City")
    country: Optional[str] = Field(None, min_length=0, max_length=50, title="Country")
    address: Optional[str] = Field(None, min_length=0, max_length=255, title="Address")
    phone: Optional[str] = Field(None, min_length=0, max_length=15, title="Phone Number")
    company: Optional[str] = Field(None, min_length=0, max_length=100, title="Company")
    user_id: Optional[UUID4] = Field(default_factory=uuid.uuid4, title="User ID")

class ProfileUpdate(BaseModel):
    """Schema for updating user profile"""
    model_config = ConfigDict(hide_input_in_errors=True)
    first_name: Optional[str] = Field(None, title="First Name", min_length=3, max_length=120)
    last_name: Optional[str] = Field(None, title="Last Name", min_length=3, max_length=120)
    gender: Optional[str] = Field(None, min_length=3, max_length=10, title="Gender")
    date_of_birth: Optional[datetime] = Field(None, title="Date of Birth")
    city: Optional[str] = Field(None, min_length=0, max_length=50, title="City")
    country: Optional[str] = Field(None, min_length=0, max_length=50, title="Country")
    address: Optional[str] = Field(None, min_length=0, max_length=255, title="Address")
    phone: Optional[str] = Field(None, min_length=0, max_length=15, title="Phone Number")
    company: Optional[str] = Field(None, min_length=0, max_length=100, title="Company")
