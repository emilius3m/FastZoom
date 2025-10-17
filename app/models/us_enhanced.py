# app/models/us_enhanced.py
"""
Modelli US/USM aggiornati con gestione file (sezioni, fotografie)
Integrazione con il sistema MinIO/Photo esistente di FastZoom
"""

from __future__ import annotations
from datetime import datetime, date
from typing import Optional, List
from uuid import uuid4, UUID

from sqlalchemy import (
    Column, String, Text, Enum, Date, DateTime, Boolean, ForeignKey, 
    Numeric, Integer, Table
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# ===== TABELLE ASSOCIATIVE PER FILE =====

# US - File associazioni (many-to-many)
us_files_association = Table(
    'us_files_associations',
    Base.metadata,
    Column('us_id', PG_UUID(as_uuid=True), ForeignKey('unita_stratigrafiche.id'), primary_key=True),
    Column('file_id', PG_UUID(as_uuid=True), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),  # 'sezione', 'fotografia', 'pianta', 'prospetto'
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)  # Per ordinamento file dello stesso tipo
)

# USM - File associazioni  
usm_files_association = Table(
    'usm_files_associations',
    Base.metadata,
    Column('usm_id', PG_UUID(as_uuid=True), ForeignKey('unita_stratigrafiche_murarie.id'), primary_key=True),
    Column('file_id', PG_UUID(as_uuid=True), ForeignKey('us_files.id'), primary_key=True),
    Column('file_type', String(50), nullable=False),
    Column('created_at', DateTime, default=datetime.utcnow),
    Column('ordine', Integer, default=0)
)

# ===== MODELLO FILES US/USM =====

# USFile, UnitaStratigrafica e UnitaStratigraficaMuraria sono importate da app.models.stratigraphy per evitare duplicazione