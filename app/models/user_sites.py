# app/models/user_sites.py - VERSIONE CORRETTA
from sqlalchemy import Column, String, DateTime, Enum, ForeignKey, Boolean, func, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from uuid import uuid4
from enum import Enum as PyEnum
from datetime import datetime
from typing import Optional

from app.models.base import Base

class PermissionLevel(PyEnum):
    """Livelli di permesso per siti archeologici - FORMATO CONSISTENTE"""
    # Usa sempre UPPERCASE per compatibilità con codice esistente
    READ = "read"                    # Solo visualizzazione
    WRITE = "write"                  # Catalogazione foto e metadati  
    ADMIN = "admin"                  # Gestione utenti e configurazioni sito
    REGIONAL_ADMIN = "regional_admin"  # Amministrazione regionale
    
    # Alias lowercase per compatibilità
    read = "read"
    write = "write"
    admin = "admin"
    regional_admin = "regional_admin"

class UserSitePermission(Base):
    """Modello per permessi utenti sui siti archeologici"""
    __tablename__ = "user_site_permissions"
    
    # Chiave primaria
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Riferimenti esterni
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    site_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archaeological_sites.id"), nullable=False)
    
    # Livello di permesso
    permission_level: Mapped[PermissionLevel] = mapped_column(
        Enum(PermissionLevel), 
        nullable=False, 
        default=PermissionLevel.READ  # 🔧 USA UPPERCASE
    )
    
    # Metadati assegnazione
    assigned_by: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("users.id"), 
        nullable=True
    )
    
    # Stato permesso
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Note aggiuntive
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timestamp
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )
    
    # Scadenza opzionale
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True
    )
    
    # Relazioni
    user: Mapped["User"] = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="site_permissions"
    )
    site: Mapped["ArchaeologicalSite"] = relationship(
        "ArchaeologicalSite",
        back_populates="user_permissions"
    )
    assigned_by_user: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[assigned_by],
        back_populates="granted_permissions"
    )
    
    # Indici
    __table_args__ = (
        Index("idx_user_site_active", "user_id", "site_id", "is_active"),
        Index("idx_user_permissions", "user_id", "permission_level"),
        Index("idx_site_permissions", "site_id", "permission_level"),
    )
    
    def __repr__(self):
        return f"<UserSitePermission(user_id={self.user_id}, site_id={self.site_id}, level={self.permission_level.value})>"
    
    @property
    def is_expired(self) -> bool:
        """Controlla se il permesso è scaduto"""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)
    
    @property
    def is_valid(self) -> bool:
        """Controlla se il permesso è attivo e non scaduto"""
        return self.is_active and not self.is_expired
    
    def can_read(self) -> bool:
        """Controlla se ha permessi di lettura"""
        return self.is_valid and self.permission_level in [
            PermissionLevel.READ,     # 🔧 USA UPPERCASE
            PermissionLevel.WRITE, 
            PermissionLevel.ADMIN, 
            PermissionLevel.REGIONAL_ADMIN
        ]
    
    def can_write(self) -> bool:
        """Controlla se ha permessi di scrittura"""
        return self.is_valid and self.permission_level in [
            PermissionLevel.WRITE, 
            PermissionLevel.ADMIN, 
            PermissionLevel.REGIONAL_ADMIN
        ]
    
    def can_admin(self) -> bool:
        """Controlla se ha permessi di amministrazione"""
        return self.is_valid and self.permission_level in [
            PermissionLevel.ADMIN,
            PermissionLevel.REGIONAL_ADMIN
        ]

    @property
    def permission_display_name(self) -> str:
        """Restituisce il nome visualizzato del livello di permesso"""
        display_names = {
            PermissionLevel.READ: "Lettura",
            PermissionLevel.WRITE: "Scrittura",
            PermissionLevel.ADMIN: "Amministratore",
            PermissionLevel.REGIONAL_ADMIN: "Amministratore Regionale"
        }
        return display_names.get(self.permission_level, str(self.permission_level.value))
