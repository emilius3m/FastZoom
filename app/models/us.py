# app/models/us.py
from __future__ import annotations
from datetime import datetime, date
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import (
    Column, String, Text, Enum, Date, DateTime, Boolean, ForeignKey, Numeric, Integer
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from sqlalchemy import JSON
JSONType = JSON
from sqlalchemy.orm import relationship
from app.database.base import Base

# Vocabolari controllati (estratti dalle schede)
ConsistenzaEnum = Enum(
    "COMPATTA", "MEDIA", "FRIABILE", name="consistenza_enum", native_enum=False
)
AffidabilitaEnum = Enum(
    "ALTA", "MEDIA", "BASSA", name="affidabilita_enum", native_enum=False
)
# Colori Munsell gestiti come stringa; materiali e lavorazioni come liste tipizzate

# UnitaStratigrafica e UnitaStratigraficaMuraria sono importate da app.models.stratigraphy per evitare duplicazione
