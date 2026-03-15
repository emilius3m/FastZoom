import os
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    minio_enabled: bool = Field(default=True, alias="MINIO_ENABLED")

    # Profile selector
    minio_config_profile: str = Field(default="local", alias="MINIO_CONFIG_PROFILE")
    
    # Local MinIO Configuration
    minio_local_url: str = Field(default="http://localhost:9000", alias="MINIO_LOCAL_URL")
    minio_local_access_key: str = Field(default="", alias="MINIO_LOCAL_ACCESS_KEY")
    minio_local_secret_key: str = Field(default="", alias="MINIO_LOCAL_SECRET_KEY")
    minio_local_bucket: str = Field(default="archaeological-photos", alias="MINIO_LOCAL_BUCKET")
    minio_local_secure: bool = Field(default=False, alias="MINIO_LOCAL_SECURE")
    
    # Remote MinIO Configuration
    minio_remote_url: str = Field(default="http://192.168.0.152:9000", alias="MINIO_REMOTE_URL")
    minio_remote_access_key: str = Field(default="", alias="MINIO_REMOTE_ACCESS_KEY")
    minio_remote_secret_key: str = Field(default="", alias="MINIO_REMOTE_SECRET_KEY")
    minio_remote_bucket: str = Field(default="archaeological-photos", alias="MINIO_REMOTE_BUCKET")
    minio_remote_secure: bool = Field(default=False, alias="MINIO_REMOTE_SECURE")
    
    # Legacy/Direct Configuration (fallback)
    minio_url: Optional[str] = Field(default=None, alias="MINIO_URL")
    minio_access_key: Optional[str] = Field(default=None, alias="MINIO_ACCESS_KEY")
    minio_secret_key: Optional[str] = Field(default=None, alias="MINIO_SECRET_KEY")
    minio_bucket: Optional[str] = Field(default=None, alias="MINIO_BUCKET")
    minio_secure: Optional[bool] = Field(default=None, alias="MINIO_SECURE")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )
    
    @field_validator("minio_config_profile")
    @classmethod
    def validate_profile(cls, v: str) -> str:
        if v not in ["local", "remote"]:
            raise ValueError("MINIO_CONFIG_PROFILE must be 'local' or 'remote'")
        return v
    
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


settings = Settings()
