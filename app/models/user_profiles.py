# app/models/user_profiles.py - Modello per profili utente

from sqlalchemy import Column, String, Text
from sqlalchemy.orm import relationship
from app.database.base import Base

class UserProfile(Base):
    """Modello per profili utente"""
    __tablename__ = "user_profiles"

    # Chiave primaria UUID per sicurezza multi-tenant
    id = Column(String(36), primary_key=True, index=True)

    # Informazioni base profilo
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    bio = Column(Text, nullable=True)
    phone_number = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)

    # Relazioni
    user = relationship("User", back_populates="profile", uselist=False)

    def __repr__(self):
        return f"<UserProfile(first_name='{self.first_name}', last_name='{self.last_name}')>"

    def __str__(self):
        return f"{self.first_name} {self.last_name}" if self.first_name and self.last_name else "No Name"