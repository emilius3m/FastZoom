# app/models/roles.py - Modello per ruoli utente

from sqlalchemy import Column, String
from sqlalchemy.orm import relationship
from app.database.base import Base

class Role(Base):
    """Modello per ruoli utente"""
    __tablename__ = "roles"

    # Chiave primaria UUID per sicurezza multi-tenant
    id = Column(String(36), primary_key=True, index=True)

    # Nome del ruolo
    name = Column(String(100), unique=True, nullable=False)

    # Descrizione del ruolo
    description = Column(String(255), nullable=True)

    # Relazioni
    users = relationship("User", back_populates="role")

    def __repr__(self):
        return f"<Role(name='{self.name}')>"

    def __str__(self):
        return self.name