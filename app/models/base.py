# app/models/base.py
"""
Modelli base per FastZoom Archaeological System
Importa Base e mixin da app.database.base per evitare duplicazione
"""

# Importa tutto da database.base per mantenere compatibilità
from app.database.base import (
    Base,
    BaseSQLModel,
    TimestampMixin,
    SiteMixin,
    UserMixin,
    SoftDeleteMixin
)

__all__ = [
    'Base',
    'BaseSQLModel',
    'TimestampMixin',
    'SiteMixin',
    'UserMixin',
    'SoftDeleteMixin'
]