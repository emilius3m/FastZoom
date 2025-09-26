# app/models/user_profiles.py - Modello per profili utente

from datetime import datetime
from typing import Optional
from uuid import uuid4, UUID

from sqlalchemy import String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql.schema import ForeignKey

from app.models.base import Base

class UserProfile(Base):
    """Modello per profili utente"""
    __tablename__ = "user_profiles"

    # Chiave primaria UUID
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign key to User
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )

    # Informazioni personali
    first_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    gender: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    date_of_birth: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    company: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relazioni
    user: Mapped["User"] = relationship(
        "User",
        back_populates="profile",
        uselist=False
    )

    def __repr__(self):
        return f"<UserProfile(user_id='{self.user_id}', first_name='{self.first_name}', last_name='{self.last_name}')>"

    def __str__(self):
        return f"{self.first_name} {self.last_name}" if self.first_name and self.last_name else "No Name"
    
    def get_full_name(self) -> str:
        """Restituisce il nome completo dell'utente"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return "No Name"