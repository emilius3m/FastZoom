import os
from typing import List
from functools import lru_cache

from pydantic import field_validator  # v2
from pydantic_settings import BaseSettings, SettingsConfigDict  # v2


class Settings(BaseSettings):
    # Configurazioni esistenti
    database_url: str = "sqlite+aiosqlite:///./archaeological_catalog.db"
    secret_key: str = "archaeological-site-secret-key-2025"
    algorithm: str = "HS256"

    # MinIO Storage - Profile-based Configuration
    minio_config_profile: str = "local"
    
    # Local MinIO Configuration
    minio_local_url: str = "http://localhost:9000"
    minio_local_access_key: str = "minioadmin123456789"
    minio_local_secret_key: str = "miniosecret987654321xyz"
    minio_local_bucket: str = "archaeological-photos"
    minio_local_secure: bool = False
    
    # Remote MinIO Configuration
    minio_remote_url: str = "http://192.168.0.152:9000"
    minio_remote_access_key: str = "emilius3m"
    minio_remote_secret_key: str = "porcatr01a"
    minio_remote_bucket: str = "archaeological-photos"
    minio_remote_secure: bool = False
    
    # Legacy Configuration (fallback)
    minio_url: str = "http://localhost:9000"
    minio_access_key: str = "minioadmin123456789"
    minio_secret_key: str = "miniosecret987654321xyz"
    minio_bucket: str = "archaeological-photos"
    minio_secure: bool = False

    # CSRF Protection
    csrf_secret_key: str = "csrf-archaeological-protection-key-2025"
    cookie_samesite: str = "lax"
    cookie_secure: bool = False

    # Multi-Site Archaeological Configuration
    site_selection_enabled: bool = True
    default_site_redirect: bool = True
    jwt_multi_site_enabled: bool = True
    jwt_expires_hours: int = 24
    max_sites_per_user: int = 50

    # Storage Fotografico
    max_photo_size_mb: int = 100
    supported_formats: str = "jpg,jpeg,png,tiff,raw,dng,pdf,doc,docx"
    thumbnail_sizes: str = "200,800"
    auto_metadata_extraction: bool = True
    photos_per_page: int = 24
    upload_dir: str = "app/static/uploads"

    # Sistema Museale
    museum_name: str = "Direzione Regionale Museale"
    museum_code: str = "DRM-2025"
    backup_retention_days: int = 365
    catalog_version: str = "1.0"

    # Configurazioni Archeologiche
    #default_historical_periods: str = "Preistorico,Romano,Medievale,Rinascimentale,Moderno"
    #default_material_types: str = "Ceramica,Metallo,Pietra,Osso,Vetro,Legno,Tessuto"

    DEBUG: bool = False

    # Pydantic v2 settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # evita ValidationError se .env contiene chiavi extra
        populate_by_name=True,  # utile per alias/env
    )

    # Validator v2 (sostituisce @validator)
    @field_validator("minio_config_profile")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        if v not in ["local", "remote"]:
            raise ValueError("MINIO_CONFIG_PROFILE must be 'local' or 'remote'")
        return v
    
    @field_validator("supported_formats")
    @classmethod
    def validate_formats(cls, v: str) -> str:
        allowed = {"jpg", "jpeg", "png", "tiff", "raw", "dng", "cr2", "nef", "pdf", "doc", "docx"}
        formats = set(v.lower().split(","))
        if not formats.issubset(allowed):
            raise ValueError(f"Formati non supportati: {formats - allowed}")
        return v

    @field_validator("thumbnail_sizes")
    @classmethod
    def validate_thumbnail_sizes(cls, v: str) -> str:
        try:
            sizes = [int(size.strip()) for size in v.split(",")]
            if any(size <= 0 or size > 2000 for size in sizes):
                raise ValueError("Dimensioni thumbnail devono essere tra 1 e 2000px")
            return v
        except ValueError:
            raise ValueError("Formato thumbnail_sizes non valido. Usa: 200,800")

    # Helper properties
    @property
    def supported_formats_list(self) -> List[str]:
        return [fmt.strip().lower() for fmt in self.supported_formats.split(",")]

    @property
    def thumbnail_sizes_list(self) -> List[int]:
        return [int(size.strip()) for size in self.thumbnail_sizes.split(",")]
    
    # Profile-based MinIO properties
    @property
    def active_minio_url(self) -> str:
        """Get the active MinIO URL based on profile"""
        # Priority: Profile-based configuration first, then legacy
        if self.minio_config_profile == "local":
            return self.minio_local_url
        else:  # remote
            return self.minio_remote_url
    
    @property
    def active_minio_access_key(self) -> str:
        """Get the active MinIO access key based on profile"""
        # Priority: Profile-based configuration first, then legacy
        if self.minio_config_profile == "local":
            return self.minio_local_access_key
        else:  # remote
            return self.minio_remote_access_key
    
    @property
    def active_minio_secret_key(self) -> str:
        """Get the active MinIO secret key based on profile"""
        # Priority: Profile-based configuration first, then legacy
        if self.minio_config_profile == "local":
            return self.minio_local_secret_key
        else:  # remote
            return self.minio_remote_secret_key
    
    @property
    def active_minio_bucket(self) -> str:
        """Get the active MinIO bucket based on profile"""
        # Priority: Profile-based configuration first, then legacy
        if self.minio_config_profile == "local":
            return self.minio_local_bucket
        else:  # remote
            return self.minio_remote_bucket
    
    @property
    def active_minio_secure(self) -> bool:
        """Get the active MinIO secure setting based on profile"""
        # Priority: Profile-based configuration first, then legacy
        if self.minio_config_profile == "local":
            return self.minio_local_secure
        else:  # remote
            return self.minio_remote_secure

    #@property
    #def historical_periods_list(self) -> List[str]:
    #    return [period.strip() for period in self.default_historical_periods.split(",")]


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
