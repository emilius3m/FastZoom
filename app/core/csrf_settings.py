from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Tuple, Optional
from fastapi_csrf_protect import CsrfProtect


class CsrfSettings(BaseSettings):
    secret_key: str = Field(validation_alias="CSRF_SECRET_KEY")
    cookie_samesite: str = Field(validation_alias="COOKIE_SAMESITE")
    cookie_secure: bool = Field(validation_alias="COOKIE_SECURE")

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


crsf_settings = CsrfSettings()


def _csrf_tokens_optional() -> Tuple[Optional[str], Optional[str], Optional[CsrfProtect]]:
    """
    Generate CSRF tokens optionally - returns None values if CSRF is not available
    Returns: (csrf_token, signed_token, csrf_instance)
    """
    try:
        csrf_instance = CsrfProtect()
        csrf_token = csrf_instance.generate_csrf_token()
        signed_token = csrf_instance.generate_csrf_cookie_token()
        return csrf_token, signed_token, csrf_instance
    except Exception:
        # CSRF not available or configured, return None values
        return None, None, None
