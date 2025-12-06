# app/models/harris_matrix_layout.py
"""
Modello SQLAlchemy per la tabella harris_matrix_layouts
Gestisce le posizioni X,Y dei nodi nella Harris Matrix per ogni sito archeologico
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin


class UnitTypeEnum(str, PyEnum):
    """Tipi di unità stratigrafica nella Harris Matrix"""
    US = "us"   # Unità Stratigrafica
    USM = "usm" # Unità Stratigrafica Muraria


class HarrisMatrixLayout(Base, TimestampMixin):
    """
    Modello per le posizioni dei nodi nella Harris Matrix
    Memorizza le coordinate X,Y di ogni unità stratigrafica per il layout della matrice
    """
    __tablename__ = "harris_matrix_layouts"

    # Chiave primaria
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), index=True)

    # Chiave esterna verso il sito archeologico
    site_id = Column(String(36), ForeignKey("archaeological_sites.id", ondelete="CASCADE"), 
                    nullable=False, index=True)

    # Identificativo dell'unità stratigrafica
    unit_id = Column(String(255), nullable=False, index=True)

    # Tipo di unità (US o USM)
    unit_type = Column(String(10), nullable=False, index=True)

    # Coordinate per il posizionamento nella matrice
    x = Column(Float, nullable=False, default=0.0)
    y = Column(Float, nullable=False, default=0.0)

    # Timestamp (ereditati da TimestampMixin ma ridefiniti per esplicitare)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # === RELAZIONI ===
    # site = relationship("ArchaeologicalSite", back_populates="harris_matrix_layouts")

    # Constraint per garantire unicità del layout per ogni unità all'interno di un sito
    __table_args__ = (
        UniqueConstraint('site_id', 'unit_id', name='uq_site_unit_layout'),
    )

    def __repr__(self):
        return f"<HarrisMatrixLayout(site_id={self.site_id}, unit_id={self.unit_id}, unit_type={self.unit_type}, x={self.x}, y={self.y})>"

    def __str__(self):
        return f"{self.unit_id} ({self.unit_type}) at ({self.x}, {self.y})"

    # === METODI HELPER ===

    @property
    def position(self) -> dict:
        """Coordinate come dizionario"""
        return {'x': self.x, 'y': self.y}

    @position.setter
    def position(self, coords: dict):
        """Imposta coordinate da dizionario"""
        if isinstance(coords, dict) and 'x' in coords and 'y' in coords:
            self.x = float(coords['x'])
            self.y = float(coords['y'])

    def set_position(self, x: float, y: float):
        """Imposta coordinate direttamente"""
        self.x = float(x)
        self.y = float(y)

    def move_by(self, dx: float, dy: float):
        """Sposta il nodo di un offset specificato"""
        self.x += float(dx)
        self.y += float(dy)

    def distance_from(self, other_x: float, other_y: float) -> float:
        """Calcola la distanza euclidea da un punto specificato"""
        return ((self.x - other_x) ** 2 + (self.y - other_y) ** 2) ** 0.5

    def is_us(self) -> bool:
        """Controlla se è un'Unità Stratigrafica"""
        return self.unit_type == UnitTypeEnum.US

    def is_usm(self) -> bool:
        """Controlla se è un'Unità Stratigrafica Muraria"""
        return self.unit_type == UnitTypeEnum.USM

    def get_unit_display_name(self) -> str:
        """Nome display dell'unità con prefisso"""
        prefix = "US" if self.is_us() else "USM"
        return f"{prefix}{self.unit_id}"

    def to_dict(self) -> dict:
        """Converte in dizionario per serializzazione JSON"""
        return {
            'id': self.id,
            'site_id': self.site_id,
            'unit_id': self.unit_id,
            'unit_type': self.unit_type,
            'display_name': self.get_unit_display_name(),
            'x': self.x,
            'y': self.y,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def create_for_unit(cls, site_id: str, unit_id: str, unit_type: str, x: float = 0.0, y: float = 0.0):
        """Factory method per creare un layout per una specifica unità"""
        return cls(
            site_id=site_id,
            unit_id=unit_id,
            unit_type=unit_type.lower(),  # Normalizza a lowercase
            x=float(x),
            y=float(y)
        )